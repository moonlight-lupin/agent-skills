#!/usr/bin/env python3
"""Build a labelled comparison sheet for visual review, plus metric deltas.

    python photo_compare.py before.jpg after.jpg -o cmp.png
    python photo_compare.py orig.jpg v1.jpg v2.jpg v3.jpg -o variants.png --labels orig,natural,moody,film
    python photo_compare.py before.jpg after.jpg -o detail.png --detail 0.5,0.4 --detail-size 600

Panels are scaled to a common height. --detail adds a 1:1 pixel crop from each
image around the given relative point (x,y in 0..1) - use it to judge
sharpening halos, noise and banding, which are invisible at thumbnail size.

--blind shuffles the panels and labels them A, B, C... with no file names or
sizes, and writes the answer key to <output>.key.json (not to stdout). Ask the
vision model to judge the sheet BEFORE reading the key, so the verdict is not
biased towards "the edit".
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import photo_core as C  # noqa: E402
import photo_analyze as A  # noqa: E402

BG = (24, 24, 24)
FG = (235, 235, 235)


def _font(size):
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "Helvetica.ttc", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _label(img, text, font):
    pad = 10
    bar = Image.new("RGB", (img.width, font.size + pad * 2), BG)
    ImageDraw.Draw(bar).text((pad, pad), text, fill=FG, font=font)
    out = Image.new("RGB", (img.width, img.height + bar.height), BG)
    out.paste(bar, (0, 0))
    out.paste(img, (0, bar.height))
    return out


def _row(panels, gap=12):
    w = sum(p.width for p in panels) + gap * (len(panels) - 1)
    h = max(p.height for p in panels)
    row = Image.new("RGB", (w, h), BG)
    x = 0
    for p in panels:
        row.paste(p, (x, 0))
        x += p.width + gap
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--labels", help="comma-separated labels (default: file names)")
    ap.add_argument("--height", type=int, default=0,
                    help="panel height in px (default: fits the sheet within ~2400 px wide)")
    ap.add_argument("--detail", help="relative point x,y for a 1:1 crop row, e.g. 0.5,0.4")
    ap.add_argument("--detail-size", type=int, default=500, help="1:1 crop size in px")
    ap.add_argument("--blind", action="store_true",
                    help="shuffle panels, label A/B/C, write the key to <output>.key.json")
    args = ap.parse_args()

    labels = args.labels.split(",") if args.labels else [Path(p).name for p in args.images]
    if len(labels) != len(args.images):
        raise SystemExit("--labels count must match the number of images")
    key = None
    if args.blind:
        import random
        order = list(range(len(args.images)))
        random.SystemRandom().shuffle(order)
        letters = [chr(65 + i) for i in range(len(order))]
        key = {letters[i]: {"file": str(Path(args.images[j]).resolve()), "label": labels[j]}
               for i, j in enumerate(order)}
        args.images = [args.images[j] for j in order]
        labels = letters
    loaded = [C.load(p) for p in args.images]
    arrays = [x[0] for x in loaded]
    font = _font(22)

    if args.height:
        ph = args.height
    else:  # fit total width ~2400
        ratios = sum(a.shape[1] / a.shape[0] for a in arrays)
        ph = int(min(1200, (2400 - 12 * (len(arrays) - 1)) / ratios))
    panels = []
    for arr, lab in zip(arrays, labels):
        h, w = arr.shape[:2]
        im = Image.fromarray(C.to_uint8(arr, dither=False)).resize((max(1, round(w * ph / h)), ph), Image.LANCZOS)
        panels.append(_label(im, lab if key else f"{lab}  ({w}x{h})", font))
    rows = [_row(panels)]

    if args.detail:
        fx, fy = [float(v) for v in args.detail.split(",")]
        s = args.detail_size
        crops = []
        for arr, lab in zip(arrays, labels):
            h, w = arr.shape[:2]
            cs = min(s, w, h)
            x0 = int(min(max(fx * w - cs / 2, 0), w - cs))
            y0 = int(min(max(fy * h - cs / 2, 0), h - cs))
            im = Image.fromarray(C.to_uint8(arr[y0:y0 + cs, x0:x0 + cs], dither=False))
            crops.append(_label(im, f"{lab} 1:1" if key else f"{lab} 1:1 @ ({x0},{y0})", font))
        rows.append(_row(crops))

    sheet_w = max(r.width for r in rows)
    sheet = Image.new("RGB", (sheet_w, sum(r.height for r in rows) + 12 * (len(rows) - 1)), BG)
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height + 12
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(args.output)

    table = []
    for arr, lab in zip(arrays, labels):
        m = A.measure(arr)
        table.append({"label": lab, "L_median": m["exposure"]["L_median"], "L_p1": m["exposure"]["L_p1"],
                      "L_p99": m["exposure"]["L_p99"], "clip_hi_pct": m["exposure"]["clip_highlights_pct"],
                      "clip_lo_pct": m["exposure"]["clip_shadows_pct"],
                      "contrast": m["contrast"]["L_range_p5_p95"], "chroma": m["color"]["chroma_mean"],
                      "cast_ab": [m["cast"]["a"], m["cast"]["b"]],
                      "sharpness": m["detail"]["laplacian_var_1600px"]})
    if key:
        kp = Path(str(args.output) + ".key.json")
        kp.write_text(json.dumps({"key": key, "metrics": table}, indent=2), encoding="utf-8")
        print(json.dumps({"sheet": str(Path(args.output).resolve()), "panels": labels,
                          "key_file": str(kp.resolve()),
                          "instruction": "Get the vision verdict first; read the key file only afterwards."},
                         indent=2))
        return
    print(json.dumps({"sheet": str(Path(args.output).resolve()), "metrics": table}, indent=2))


if __name__ == "__main__":
    main()
