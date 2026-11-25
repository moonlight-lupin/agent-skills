#!/usr/bin/env python3
"""Measure a photo before (and after) editing.

    python photo_analyze.py photo.jpg            # JSON report + suggested recipe
    python photo_analyze.py photo.jpg --brief    # short human-readable summary

Numbers, not adjectives: exposure percentiles and clipping, colour cast of
near-neutral pixels, saturation, contrast, sharpness, noise, tilt. The
`suggested_recipe` is deliberately conservative - a starting point that a
judgement pass (vision check + taste rules) should confirm or tone down.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import photo_core as C  # noqa: E402


def _r(x, n=2):
    return None if x is None else round(float(x), n)


def estimate_tilt(gray, max_deg=10.0):
    """Projection-profile deskew: find the rotation that best aligns edges.

    Horizontal edges are projected onto rows and vertical edges onto columns;
    the correct angle makes those profiles sharpest. Returns
    (straighten_deg, confidence 0..1) where straighten_deg is exactly the value
    to pass to photo_edit.py `straighten` (positive = rotate counter-clockwise).
    """
    from PIL import Image

    g = gray.astype(np.float32)
    s = 900 / max(g.shape)
    if s < 1:
        g = np.asarray(Image.fromarray(g, "F").resize((round(g.shape[1] * s), round(g.shape[0] * s)),
                                                       Image.BILINEAR), dtype=np.float32)
    ey = np.abs(g[2:, 1:-1] - g[:-2, 1:-1])  # responds to horizontal lines
    ex = np.abs(g[1:-1, 2:] - g[1:-1, :-2])  # responds to vertical lines
    for e in (ey, ex):  # keep only strong edges, so texture doesn't vote
        e[e < np.percentile(e, 90)] = 0
    if ey.sum() + ex.sum() <= 0:
        return 0.0, 0.0
    h, w = ey.shape
    m = int(min(h, w) * 0.12)  # ignore borders, which rotation fills with zeros
    imy, imx = Image.fromarray(ey, "F"), Image.fromarray(ex, "F")

    def score(theta):
        ry = np.asarray(imy.rotate(theta, Image.BILINEAR), dtype=np.float32)[m:-m, m:-m]
        rx = np.asarray(imx.rotate(theta, Image.BILINEAR), dtype=np.float32)[m:-m, m:-m]
        py, px = ry.sum(axis=1), rx.sum(axis=0)
        return float(np.var(py) / (py.mean() ** 2 + 1e-9) + np.var(px) / (px.mean() ** 2 + 1e-9))

    coarse = np.arange(-max_deg, max_deg + 1e-6, 0.5)
    sc = np.array([score(t) for t in coarse])
    best = float(coarse[int(np.argmax(sc))])
    fine = np.arange(best - 0.5, best + 0.5001, 0.05)
    sf = np.array([score(t) for t in fine])
    best = float(fine[int(np.argmax(sf))])
    peak, base = sf.max(), np.median(sc)
    conf = float(np.clip((peak - base) / (peak + 1e-9), 0, 1))
    return round(best, 2), conf


def noise_sigma(gray255):
    """Immerkaer (1996) fast noise estimate on a 0..255 grey image."""
    g = gray255.astype(np.float32)
    h, w = g.shape
    if h < 8 or w < 8:
        return 0.0
    conv = (g[:-2, :-2] - 2 * g[:-2, 1:-1] + g[:-2, 2:]
            - 2 * g[1:-1, :-2] + 4 * g[1:-1, 1:-1] - 2 * g[1:-1, 2:]
            + g[2:, :-2] - 2 * g[2:, 1:-1] + g[2:, 2:])
    # ignore strong edges so texture doesn't read as noise
    edges = np.abs(conv) > np.percentile(np.abs(conv), 90)
    vals = np.abs(conv[~edges])
    return float(math.sqrt(math.pi / 2) * vals.mean() / 6.0)


def gains_from_region(rgb, box):
    """WB gains that make the mean of a region neutral. box = [x0,y0,x1,y1] relative 0..1."""
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = box
    xa, xb = int(x0 * w), max(int(x0 * w) + 1, int(x1 * w))
    ya, yb = int(y0 * h), max(int(y0 * h) + 1, int(y1 * h))
    patch = C.srgb_to_linear(rgb[ya:yb, xa:xb]).reshape(-1, 3)
    ok = patch.max(axis=1) < 0.97  # ignore clipped pixels
    if ok.sum() < 4:
        raise SystemExit("WB region is clipped or empty; pick a mid-grey/white area that isn't blown out.")
    mean = patch[ok].mean(axis=0)
    lab = C.linear_to_lab(mean[None, None, :])[0, 0]
    return mean[1] / np.maximum(mean, 1e-6), (float(lab[1]), float(lab[2]))


def estimate_cast(work, L, a, b, chroma, mx):
    """Find the dominant cluster of near-neutral pixels and the gains to neutralise it.

    Blue pixels in the upper half are excluded (sky is legitimately blue and is
    the classic way auto-WB goes wrong). The runner-up cluster is reported so
    the caller can tell when the estimate is ambiguous.
    """
    h, w = L.shape
    rows = np.repeat(np.arange(h)[:, None] / h, w, axis=1)
    skyish = (rows < 0.5) & (b < -4) & (a < 4)
    cand = (mx < 0.97) & (L > 25) & (L < 92) & (chroma < 22) & ~skyish
    out = {"a": None, "b": None, "reliable": False, "gains_rgb": None,
           "neutral_pct": _r(cand.mean() * 100, 1), "alternative": None}
    if cand.sum() < 500:
        return out
    bins = np.arange(-22, 23, 1.0)
    hist, _, _ = np.histogram2d(a[cand], b[cand], bins=[bins, bins])
    k = np.exp(-np.arange(-3, 4) ** 2 / 4.0)
    k /= k.sum()
    hist = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 0, hist)
    hist = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 1, hist)
    centers = []
    hcopy = hist.copy()
    for _ in range(2):
        i, j = np.unravel_index(np.argmax(hcopy), hcopy.shape)
        if hcopy[i, j] <= 0:
            break
        centers.append((bins[i] + 0.5, bins[j] + 0.5))
        hcopy[max(0, i - 6):i + 7, max(0, j - 6):j + 7] = 0
    lin = C.srgb_to_linear(work)
    clusters = []
    for ca, cb in centers:
        sel = cand & (np.hypot(a - ca, b - cb) < 6)
        if sel.sum() < 200:
            continue
        mean = lin[sel].mean(axis=0)
        ys, xs = np.nonzero(sel)
        clusters.append({
            "a": _r(a[sel].mean(), 1), "b": _r(b[sel].mean(), 1),
            "share_pct": _r(sel.mean() * 100, 1),
            "where_xy": [_r(xs.mean() / w, 2), _r(ys.mean() / h, 2)],
            "gains_rgb": [_r(g, 3) for g in mean[1] / np.maximum(mean, 1e-6)],
        })
    if not clusters:
        return out
    best = clusters[0]
    out.update(a=best["a"], b=best["b"], gains_rgb=best["gains_rgb"], neutral_pct=best["share_pct"],
               where_xy=best["where_xy"], reliable=best["share_pct"] > 2)
    if len(clusters) > 1 and clusters[1]["share_pct"] > best["share_pct"] * 0.4:
        out["alternative"] = clusters[1]
        out["reliable"] = False  # two competing "neutrals": needs a visual decision
    return out


def measure(rgb, full=None):
    """Metrics on a working copy. `full` (full-res array) is used for noise."""
    work = C.working_copy(rgb, 1600)
    lab = C.srgb_to_lab(work)
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    chroma = np.hypot(a, b)
    hue = np.degrees(np.arctan2(b, a)) % 360
    mx = work.max(axis=-1)
    p = np.percentile(L, [0.5, 1, 5, 25, 50, 75, 95, 99, 99.5])
    m = {
        "exposure": {
            "L_median": _r(p[4], 1), "L_mean": _r(L.mean(), 1),
            "L_p1": _r(p[1], 1), "L_p5": _r(p[2], 1), "L_p25": _r(p[3], 1),
            "L_p75": _r(p[5], 1), "L_p95": _r(p[6], 1), "L_p99": _r(p[7], 1),
            "clip_highlights_pct": _r((mx >= 254.5 / 255).mean() * 100, 2),
            "clip_shadows_pct": _r((mx <= 2.5 / 255).mean() * 100, 2),
            "key": "low-key" if p[4] < 35 else "high-key" if p[4] > 68 else "normal",
        },
        "contrast": {
            "L_range_p5_p95": _r(p[6] - p[2], 1),
            "L_std": _r(L.std(), 1),
        },
        "color": {
            "chroma_mean": _r(chroma.mean(), 1),
            "chroma_p95": _r(np.percentile(chroma, 95), 1),
            "oversaturated_pct": _r((chroma > 85).mean() * 100, 2),
            "skin_like_pct": _r(((hue >= 20) & (hue <= 65) & (chroma >= 12) & (chroma <= 45)
                                  & (L >= 25) & (L <= 85)).mean() * 100, 1),
            "scene_mean_a": _r(a.mean(), 1), "scene_mean_b": _r(b.mean(), 1),
        },
    }
    m["cast"] = estimate_cast(work, L, a, b, chroma, mx)

    gray = C.luma(work) * 255
    lap = (gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * gray[1:-1, 1:-1])
    sharp = float(lap.var())
    m["detail"] = {"laplacian_var_1600px": _r(sharp, 0),
                   "verdict": "soft" if sharp < 60 else "ok" if sharp < 600 else "crisp/busy"}
    src = full if full is not None else rgb
    h, w = src.shape[:2]
    cy, cx, s = h // 2, w // 2, 1000
    crop = src[max(0, cy - s):cy + s, max(0, cx - s):cx + s]
    m["detail"]["noise_sigma_full_res"] = _r(noise_sigma(C.luma(crop) * 255), 2)
    tilt, conf = estimate_tilt(gray)
    m["geometry"] = {"tilt_deg": _r(tilt, 2), "tilt_confidence": _r(conf, 2)}
    return m


# Per-scene intent. The analyzer can't see what the photo is *for*; the agent
# decides the scene (with vision) and passes it, and targets follow.
SCENES = {
    #            median L* target, WB strength (0 = leave), vibrance cap, lift shadows?, want true whites?
    "general":   dict(target=50, wb=0.7, vib=15, lift=True, whites=True),
    "landscape": dict(target=48, wb=0.6, vib=15, lift=True, whites=True),
    "portrait":  dict(target=54, wb=0.6, vib=8, lift=True, whites=True),
    "food":      dict(target=55, wb=0.5, vib=10, lift=True, whites=True),
    "product":   dict(target=62, wb=1.0, vib=5, lift=True, whites=True),
    "interior":  dict(target=58, wb=0.8, vib=5, lift=True, whites=True),
    "document":  dict(target=70, wb=1.0, vib=0, lift=True, whites=True),
    "street":    dict(target=46, wb=0.5, vib=8, lift=False, whites=True),
    "sunset":    dict(target=None, wb=0.0, vib=10, lift=False, whites=False),
    "night":     dict(target=None, wb=0.3, vib=5, lift=False, whites=False),
    "low-key":   dict(target=None, wb=0.5, vib=8, lift=False, whites=False),
    "high-key":  dict(target=72, wb=0.8, vib=5, lift=True, whites=True),
}


def _lin(L_):
    return ((L_ + 16) / 116) ** 3 if L_ > 8 else L_ / 903.3


def suggest(m, info, size, scene="general"):
    """Conservative auto recipe + plain-language notes explaining each choice."""
    sc = SCENES.get(scene, SCENES["general"])
    ex, co, col, cast, geo = m["exposure"], m["contrast"], m["color"], m["cast"], m["geometry"]
    rec, notes = {}, [f"Scene intent: {scene}."]
    # Straighten only when straight lines clearly agree.
    if geo["tilt_confidence"] >= 0.5 and 0.2 <= abs(geo["tilt_deg"]) <= 8:
        rec["straighten"] = round(geo["tilt_deg"], 2)
        notes.append(f"Straight lines agree: straighten {geo['tilt_deg']:+.2f} deg (confirm the horizon/verticals visually).")
    elif abs(geo["tilt_deg"]) >= 0.2:
        notes.append(f"Possible tilt {geo['tilt_deg']:+.2f} deg, low confidence ({geo['tilt_confidence']}); "
                     "fix only if a horizon or vertical is visibly off. Organic scenes need no levelling.")

    if cast["reliable"] and cast["a"] is not None:
        mag = math.hypot(cast["a"], cast["b"])
        if mag >= 4 and sc["wb"] > 0:
            s = sc["wb"] if mag < 10 else min(1.0, sc["wb"] + 0.1)
            rec["white_balance"] = {"mode": "auto", "strength": round(s, 2)}
            notes.append(f"Neutrals carry a cast (a*={cast['a']}, b*={cast['b']}); auto WB at strength {s:.2f}.")
        elif mag >= 4:
            notes.append(f"Cast a*={cast['a']} b*={cast['b']} left alone: for a {scene} the colour of the light is the mood.")
    elif cast.get("alternative"):
        alt = cast["alternative"]
        notes.append(f"Two candidate neutrals disagree: a*={cast['a']} b*={cast['b']} around xy={cast.get('where_xy')} "
                     f"vs a*={alt['a']} b*={alt['b']} around xy={alt['where_xy']}. Look at both spots; use "
                     "white_balance mode 'region' on the one that is truly grey/white.")
    else:
        notes.append("Few neutral pixels: white-balance estimate unreliable; leave WB alone unless the cast is obvious.")

    med, p99 = ex["L_median"], ex["L_p99"]
    headroom = math.log2(_lin(96) / max(_lin(p99), 1e-4)) if ex["clip_highlights_pct"] < 0.2 else 0.0
    if sc["target"] is not None:
        gap = math.log2(_lin(sc["target"]) / max(_lin(med), 1e-4))
        if gap > 0.15:  # too dark: brighten, but never beyond what the highlights can take
            ev = min(gap * 0.7, max(headroom, 0.0) + 0.15, 1.2)
            if ev >= 0.1:
                rec["exposure"] = round(ev, 2)
                notes.append(f"Median L*={med} vs {sc['target']} target, {headroom:.2f} EV highlight headroom: exposure {ev:+.2f} EV.")
        elif gap < -0.3:
            ev = max(gap * 0.5, -1.0)
            rec["exposure"] = round(ev, 2)
            notes.append(f"Median L*={med} is bright for a {scene}: exposure {ev:+.2f} EV.")
    elif med < 15:
        rec["exposure"] = 0.3
        notes.append(f"Even for a {scene}, median L*={med} is murky: small +0.3 EV.")
    if ex["clip_highlights_pct"] > 0.5 or p99 > 97:
        rec["highlights"] = -35 if ex["clip_highlights_pct"] > 2 else -20
        notes.append(f"{ex['clip_highlights_pct']}% highlights clipped / p99 L*={p99}: pull highlights (clipped detail can't be recovered).")
    if ex["L_p5"] < 8 and sc["lift"]:
        rec["shadows"] = 20
        notes.append(f"Shadows dense (p5 L*={ex['L_p5']}): lift shadows a little.")
    rng = co["L_range_p5_p95"]
    if rng < 55 and scene not in ("high-key", "document"):
        rec["contrast"] = 15 if rng < 45 else 8
        notes.append(f"Flat tonal range (p5-p95 = {rng} L*): gentle contrast.")
    elif rng > 85:
        notes.append(f"Already high contrast (p5-p95 = {rng}); do not add contrast.")
    if ex["L_p1"] > 10 and scene != "high-key":
        rec["blacks"] = -10
        notes.append(f"Washed-out blacks (p1 L*={ex['L_p1']}): set a black point.")
    exp_gain = rec.get("exposure", 0)
    if sc["whites"] and p99 < 85 and exp_gain < 0.3:
        rec["whites"] = 10
        notes.append(f"No true whites (p99 L*={p99}): extend whites slightly.")

    if col["chroma_mean"] < 14 and sc["vib"] > 0:
        rec["vibrance"] = sc["vib"]
        notes.append(f"Muted colour (mean chroma {col['chroma_mean']}): vibrance +{sc['vib']}, not saturation.")
    elif col["oversaturated_pct"] > 1.5:
        rec["vibrance"] = -10
        notes.append(f"{col['oversaturated_pct']}% of pixels very saturated: reduce vibrance slightly.")
    if col["skin_like_pct"] > 8:
        notes.append(f"Skin-hued pixels cover {col['skin_like_pct']}% (could also be wood, sand, warm light): "
                     "if people are present, protect skin - vibrance only, natural WB.")
    nz = m["detail"]["noise_sigma_full_res"]
    if nz and nz > 4:
        rec["denoise_chroma"] = 40 if nz < 8 else 60
        notes.append(f"Visible noise (sigma {nz}): chroma denoise; avoid clarity and heavy sharpening.")
    if m["detail"]["verdict"] == "soft":
        notes.append("Image is soft. Sharpening cannot fix missed focus or motion blur; do not oversharpen to compensate.")
    if info.get("converted_to_srgb"):
        notes.append(f"Source profile '{info.get('icc')}' converted to sRGB for editing; output is tagged sRGB.")
    if not rec:
        notes.append("Measurements look healthy. A good edit here may be no edit, or only a crop.")
    return rec, notes


def analyze(path, scene="general", subject_hint=None, overlay=None):
    import photo_frames as Fr
    import photo_subject as S

    rgb, alpha, info = C.load(path)
    h, w = rgb.shape[:2]
    m = measure(rgb)
    rec, notes = suggest(m, info, (w, h), scene)
    subj = S.find_subject(rgb, subject_hint)
    comp = S.composition(rgb, subj)
    faces = bool(subj.get("faces"))
    # ready-made reframes for common deliverables, so the agent can compare them
    crops, crop_px = {}, {}
    for name, aspect in (("4:5", "4:5"), ("1:1", "1:1"), ("16:9", "16:9"), ("9:16", "9:16")):
        box, rep = Fr.plan_crop(w, h, subj["box"], aspect, place="thirds", tightness=0.25, faces=faces)
        crops[name] = {k: rep[k] for k in ("subject_centre_in_crop", "subject_area_pct",
                                            "kept_of_source_pct", "subject_clipped")}
        crop_px[name] = [box[0] / w, box[1] / h, box[2] / w, box[3] / h]
    out_overlay = None
    if overlay:
        out_overlay = S.draw_overlay(rgb, subj, comp, overlay, crops=crop_px)
    if subj["confidence"] < 0.35 and subj["source"] == "saliency":
        comp["notes"].insert(0, "Subject detection is uncertain: confirm with vision on the overlay, "
                                "then pass --subject x0,y0,x1,y1 (relative) to photo_edit.py reframe.")
    g = math.gcd(w, h)
    return {
        "file": str(path),
        "size": {"width": w, "height": h, "megapixels": round(w * h / 1e6, 2),
                 "aspect": f"{w // g}:{h // g}" if g > 1 and w // g < 50 else round(w / h, 4),
                 "has_alpha": alpha is not None},
        "source": {"format": info["format"], "mode": info["mode"], "icc": info["icc"],
                   "converted_to_srgb": info["converted_to_srgb"]},
        "metrics": m,
        "subject": {k: subj.get(k) for k in ("box", "centroid", "source", "confidence", "faces", "candidates")},
        "composition": comp,
        "reframe_previews": crops,
        "overlay": out_overlay,
        "notes": notes,
        "suggested_recipe": rec,
    }


def brief(r):
    m = r["metrics"]
    ex, cast = m["exposure"], m["cast"]
    lines = [
        f"{Path(r['file']).name}: {r['size']['width']}x{r['size']['height']} ({r['size']['aspect']}), {r['source']['icc'] or 'no ICC (assumed sRGB)'}",
        f"Exposure: median L*={ex['L_median']} p1={ex['L_p1']} p99={ex['L_p99']} | clipped hi {ex['clip_highlights_pct']}% lo {ex['clip_shadows_pct']}% | {ex['key']}",
        f"Contrast: p5-p95 {m['contrast']['L_range_p5_p95']} L*",
        f"Colour: mean chroma {m['color']['chroma_mean']}, oversat {m['color']['oversaturated_pct']}%, skin-like {m['color']['skin_like_pct']}%",
        f"Cast (neutrals): a*={cast['a']} b*={cast['b']} reliable={cast['reliable']}",
        f"Detail: {m['detail']['verdict']} (lapvar {m['detail']['laplacian_var_1600px']}), noise sigma {m['detail']['noise_sigma_full_res']}",
        f"Tilt: {m['geometry']['tilt_deg']} deg (confidence {m['geometry']['tilt_confidence']})",
        f"Subject ({r['subject']['source']}, confidence {r['subject']['confidence']}): box {r['subject']['box']}, "
        f"faces {len(r['subject']['faces'] or [])}",
        f"Composition: centre {r['composition']['subject_centre']}, {r['composition']['placement']}, "
        f"{r['composition']['subject_area_pct']}% of frame, horizon {r['composition']['horizon_y']}",
        *[f"  - {n}" for n in r["composition"]["notes"]],
        "Reframe previews: " + "; ".join(f"{k}: centre {v['subject_centre_in_crop']} area {v['subject_area_pct']}%"
                                         f"{' CLIPS SUBJECT' if v['subject_clipped'] else ''}"
                                         for k, v in r["reframe_previews"].items()),
        *([f"Overlay: {r['overlay']}"] if r.get("overlay") else []),
        "Notes:", *[f"  - {n}" for n in r["notes"]],
        "Suggested recipe: " + json.dumps(r["suggested_recipe"]),
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+")
    ap.add_argument("--brief", action="store_true", help="human-readable summary instead of JSON")
    ap.add_argument("--scene", default="general", choices=sorted(SCENES),
                    help="what the photo is; sets exposure/WB/colour targets (default: general)")
    ap.add_argument("--subject", help="trusted subject box x0,y0,x1,y1 (relative 0..1), e.g. from vision")
    ap.add_argument("--overlay", help="write a preview PNG with thirds grid, subject box, horizon and "
                                      "proposed crops (one image only)")
    args = ap.parse_args()
    hint = [float(v) for v in args.subject.split(",")] if args.subject else None
    out = []
    for p in args.images:
        r = analyze(p, args.scene, hint, args.overlay if len(args.images) == 1 else None)
        out.append(brief(r) if args.brief else r)
    if args.brief:
        print("\n\n".join(out))
    else:
        print(json.dumps(out[0] if len(out) == 1 else out, indent=2))


if __name__ == "__main__":
    main()
