#!/usr/bin/env python3
"""Apply a photo-edit recipe in a fixed, correct order. Never edits in place.

    python photo_edit.py in.jpg -o out.jpg --recipe '{"exposure":0.3,"contrast":10}'
    python photo_edit.py in.jpg -o out.jpg --recipe auto            # photo_analyze.py suggestion
    python photo_edit.py in.jpg -o out.jpg --look natural --set crop.aspect=4:5
    python photo_edit.py in.jpg -o out.jpg --recipe recipe.json --dry-run

Layering: --look < --recipe < --set. Values outside the taste limits are
clamped (with a warning) unless --allow-extreme. See references/recipe.md.
Pipeline: orient -> straighten -> crop -> WB -> exposure -> tone curve ->
clarity -> colour -> chroma denoise -> vignette -> B&W -> resize -> sharpen.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import photo_core as C  # noqa: E402
import photo_analyze as A  # noqa: E402
import photo_frames as Fr  # noqa: E402
import photo_subject as S  # noqa: E402

LOOKS_DIR = HERE.parent / "templates" / "looks"

# (min, max) the code accepts, and (min, max) taste allows without --allow-extreme
LIMITS = {
    "straighten": ((-45, 45), (-10, 10)),
    "exposure": ((-3, 3), (-1.5, 1.5)),
    "contrast": ((-100, 100), (-30, 35)),
    "highlights": ((-100, 100), (-70, 30)),
    "shadows": ((-100, 100), (-30, 50)),
    "whites": ((-100, 100), (-30, 30)),
    "blacks": ((-100, 100), (-40, 30)),
    "clarity": ((-100, 100), (-30, 30)),
    "vibrance": ((-100, 100), (-50, 35)),
    "saturation": ((-100, 100), (-100, 25)),
    "denoise_chroma": ((0, 100), (0, 80)),
    "vignette": ((-100, 100), (-30, 15)),
    "temp": ((-100, 100), (-40, 40)),
    "tint": ((-100, 100), (-30, 30)),
}


# ---------------------------------------------------------------- recipe

def _parse_value(v):
    try:
        return json.loads(v)
    except Exception:
        return v


def _set_path(d, dotted, value):
    keys = dotted.split(".")
    for k in keys[:-1]:
        if not isinstance(d.get(k), dict):
            d[k] = {"mode": d[k]} if isinstance(d.get(k), str) else {}
        d = d[k]
    d[keys[-1]] = value


def _merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _apply_look(recipe, look_name):
    p = LOOKS_DIR / f"{look_name}.json"
    if not p.exists():
        names = sorted(x.stem for x in LOOKS_DIR.glob("*.json"))
        raise SystemExit(f"Unknown look '{look_name}'. Available: {', '.join(names)}")
    look = json.loads(p.read_text(encoding="utf-8"))
    look.pop("_about", None)
    return _merge(recipe, look)


def load_recipe(args, src_path):
    """Layering: look (CLI or "look" key) < recipe (auto / file / inline JSON) < --set."""
    given = {}
    if args.recipe == "auto":
        given = A.analyze(src_path, args.scene)["suggested_recipe"]
    elif args.recipe and Path(args.recipe).exists():
        given = json.loads(Path(args.recipe).read_text(encoding="utf-8"))
    elif args.recipe:
        given = json.loads(args.recipe)
    look = args.look or given.pop("look", None)
    given.pop("look", None)
    recipe = _apply_look({}, look) if look else {}
    recipe = _merge(recipe, given)
    for s in args.set or []:
        k, _, v = s.partition("=")
        _set_path(recipe, k.strip(), _parse_value(v.strip()))
    return recipe


def validate(recipe, allow_extreme):
    warnings = []
    flat = dict(recipe)
    wb = recipe.get("white_balance")
    if isinstance(wb, dict):
        for k in ("temp", "tint"):
            if k in wb:
                flat[k] = wb[k]
    for key, ((lo, hi), (tlo, thi)) in LIMITS.items():
        if key not in flat or flat[key] is None:
            continue
        v = float(flat[key])
        nv = min(max(v, lo), hi)
        if not allow_extreme:
            nv = min(max(nv, tlo), thi)
        if nv != v:
            warnings.append(f"{key}={v:g} outside {'taste' if lo <= v <= hi else 'valid'} range "
                            f"[{tlo if not allow_extreme else lo}, {thi if not allow_extreme else hi}]; clamped to {nv:g}.")
        if key in ("temp", "tint"):
            recipe["white_balance"][key] = nv
        else:
            recipe[key] = nv
    known = set(LIMITS) - {"temp", "tint"} | {"white_balance", "crop", "resize", "sharpen", "bw", "reframe", "frame",
                                               "curve", "quality", "metadata", "format"}
    for k in recipe:
        if k not in known:
            warnings.append(f"Unknown recipe key '{k}' ignored (see references/recipe.md).")
    return warnings


# ---------------------------------------------------------------- geometry

def straighten(rgb, alpha, deg):
    h, w = rgb.shape[:2]
    t = math.radians(abs(deg))
    c, s = math.cos(t), math.sin(t)
    r = w / h
    cw = min(w / (c + s / r), h / (s + c / r))  # largest same-aspect rect inside rotation
    ch = cw / r
    cw, ch = int(cw) - 2, int(ch) - 2
    rot = C.rotate_float(rgb, deg)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    out = rot[y0:y0 + ch, x0:x0 + cw]
    if alpha is not None:
        alpha = C.rotate_float(alpha[..., None], deg)[y0:y0 + ch, x0:x0 + cw, 0]
    return out, alpha, {"rotated_deg": deg, "kept_pct": round(cw * ch / (w * h) * 100, 1),
                        "_map": (w, h, x0, y0, cw, ch)}


def map_box_through_straighten(box, deg, tf):
    """Map a relative box on the source onto the straightened, cropped image."""
    w, h, x0, y0, cw, ch = tf
    t = math.radians(deg)
    pts = []
    for X, Y in ((box[0], box[1]), (box[2], box[1]), (box[0], box[3]), (box[2], box[3])):
        x, y = X * w - w / 2, Y * h - h / 2
        # PIL rotates counter-clockwise on screen (y axis points down)
        xr, yr = x * math.cos(t) + y * math.sin(t), -x * math.sin(t) + y * math.cos(t)
        pts.append(((xr + w / 2 - x0) / cw, (yr + h / 2 - y0) / ch))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [max(0.0, min(xs)), max(0.0, min(ys)), min(1.0, max(xs)), min(1.0, max(ys))]


def _ratio(s):
    if isinstance(s, (int, float)):
        return float(s)
    a, _, b = str(s).replace("x", ":").partition(":")
    return float(a) / float(b)


def crop_box(w, h, spec):
    """Resolve a crop spec to (x0, y0, x1, y1) in pixels plus a report."""
    if "box" in spec:
        x0, y0, x1, y1 = [float(v) for v in spec["box"]]
        if max(x0, y0, x1, y1) <= 1.0:
            x0, x1, y0, y1 = x0 * w, x1 * w, y0 * h, y1 * h
        box = [int(round(v)) for v in (max(0, x0), max(0, y0), min(w, x1), min(h, y1))]
        return box, {"box": box}
    aspect = spec.get("aspect", "original")
    r = w / h if aspect == "original" else _ratio(aspect)
    zoom = max(1.0, float(spec.get("zoom", 1.0)))
    cw = min(w, h * r) / zoom
    ch = cw / r
    fx, fy = spec.get("focus", [0.5, 0.5])
    place = spec.get("place", "center")
    if place == "thirds":
        tx = 1 / 3 if fx < 0.5 else 2 / 3
        ty = 1 / 3 if fy < 0.55 else 2 / 3
    else:
        tx, ty = 0.5, 0.5
    x0 = min(max(fx * w - tx * cw, 0), w - cw)
    y0 = min(max(fy * h - ty * ch, 0), h - ch)
    box = [int(round(x0)), int(round(y0)), int(round(x0 + cw)), int(round(y0 + ch))]
    rep = {"box": box, "aspect": aspect, "focus_lands_at": [round((fx * w - box[0]) / (box[2] - box[0]), 3),
                                                             round((fy * h - box[1]) / (box[3] - box[1]), 3)]}
    return box, rep


# ---------------------------------------------------------------- tone & colour

def tone_lut(r):
    xs = [0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0]
    ys = list(xs)
    c = r.get("contrast", 0) / 100.0
    hi, sh = r.get("highlights", 0) / 100.0, r.get("shadows", 0) / 100.0
    wh, bl = r.get("whites", 0) / 100.0, r.get("blacks", 0) / 100.0
    ys[2] += -0.07 * c + 0.12 * sh
    ys[4] += 0.07 * c + 0.12 * hi
    ys[1] += -0.025 * c + 0.03 * sh + 0.045 * bl
    ys[5] += 0.025 * c + 0.03 * hi + 0.045 * wh
    ys[3] += 0.02 * sh + 0.02 * hi
    if bl > 0:
        ys[0] = 0.05 * bl  # lifted (matte) blacks
    if wh < 0:
        ys[6] = 1 + 0.06 * wh  # dulled whites
    if "curve" in r:  # explicit [[x, y], ...] in 0..1 overrides the parametric curve
        pts = sorted([(float(x), float(y)) for x, y in r["curve"]])
        if pts[0][0] > 0:
            pts.insert(0, (0.0, 0.0))
        if pts[-1][0] < 1:
            pts.append((1.0, 1.0))
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    ys = np.clip(np.maximum.accumulate(np.array(ys)), 0, 1)
    ys = ys + np.arange(len(ys)) * 1e-6  # strictly monotone
    grid = np.linspace(0, 1, 1025)
    return grid, np.clip(C.pchip(xs, ys, grid), 0, 1)


def wb_gains(rgb, wb):
    if wb in (None, False):
        return None, None
    if wb == "auto" or wb is True:
        wb = {"mode": "auto"}
    if isinstance(wb, str):
        raise SystemExit("white_balance must be 'auto' or {mode, strength, temp, tint}")
    g = np.ones(3, dtype=np.float32)
    rep = {}
    mode = wb.get("mode")
    if mode in ("region", "point"):
        if mode == "point":
            px, py = wb["point"]
            r_ = float(wb.get("radius", 0.01))
            box = [px - r_, py - r_, px + r_, py + r_]
        else:
            box = wb["box"]
        box = [min(max(float(v), 0.0), 1.0) for v in box]
        gains, ab = A.gains_from_region(rgb, box)
        s = float(wb.get("strength", 1.0))
        g *= np.asarray(gains, dtype=np.float32) ** s
        rep.update(neutral_region=[round(v, 3) for v in box], region_cast_ab=[round(ab[0], 1), round(ab[1], 1)],
                   strength=s)
    elif mode == "auto":
        cast = A.measure(rgb)["cast"]
        if cast.get("alternative") and not wb.get("force"):
            rep["auto"] = ("skipped: ambiguous neutrals; use mode 'region' on a known grey/white, "
                           "or force:true")
        elif cast["gains_rgb"]:
            s = float(wb.get("strength", 0.7))
            auto = np.array(cast["gains_rgb"], dtype=np.float32)
            g *= auto ** s
            rep.update(auto_from_cast=[cast["a"], cast["b"]], strength=s, reliable=cast["reliable"])
        else:
            rep["auto"] = "skipped: no reliable neutral pixels"
    t, m = float(wb.get("temp", 0)), float(wb.get("tint", 0))
    g *= np.array([2 ** (t * 0.004), 2 ** (-m * 0.004), 2 ** (-t * 0.004)], dtype=np.float32)
    g /= (g * np.array([0.2126, 0.7152, 0.0722])).sum()  # keep luminance constant
    rep["gains_rgb"] = [round(float(x), 4) for x in g]
    return g, rep


def apply(rgb, alpha, recipe):
    report = {}
    # geometry
    if recipe.get("straighten"):
        rgb, alpha, report["straighten"] = straighten(rgb, alpha, float(recipe["straighten"]))
    rs = recipe.get("resize") or {}
    crop = dict(recipe.get("crop") or {})
    frame = recipe.get("frame") or None
    shaped = bool(frame) and frame.get("shape", "rect") not in ("rect", "rounded")
    reframe = dict(recipe.get("reframe") or {})
    if shaped and not reframe:
        reframe = {"place": "sweet"}
    if reframe:
        if crop:
            report["note_crop"] = "crop ignored: reframe takes precedence."
            crop = {}
        rgb, alpha, report["reframe"] = do_reframe(rgb, alpha, reframe, frame if shaped else None,
                                                   recipe, report.get("straighten"))
        if rs.get("exact"):
            report["note_exact"] = "resize.exact after reframe: set reframe.aspect to the same ratio."
    if rs.get("exact") and not crop and not reframe:
        ew, eh = rs["exact"]
        crop = {"aspect": f"{ew}:{eh}"}
        report["note"] = f"resize.exact implies crop aspect {ew}:{eh} (centred; set crop.focus to steer)."
    if crop:
        h, w = rgb.shape[:2]
        (x0, y0, x1, y1), report["crop"] = crop_box(w, h, crop)
        rgb = rgb[y0:y1, x0:x1]
        alpha = alpha[y0:y1, x0:x1] if alpha is not None else None

    report["_geom"] = rgb  # "before" metrics use the same framing as "after"
    # linear-light ops
    lin = C.srgb_to_linear(rgb)
    g, rep = wb_gains(rgb, recipe.get("white_balance"))
    if g is not None:
        lin = lin * g
        report["white_balance"] = rep
    ev = float(recipe.get("exposure", 0) or 0)
    if ev:
        lin = lin * (2 ** ev)
        if ev > 0:  # soft shoulder instead of a hard clip
            k = 0.8
            over = lin > k
            lin = np.where(over, k + (1 - k) * np.tanh((lin - k) / (1 - k)), lin)
    lab = C.linear_to_lab(lin)
    del lin
    L = lab[..., 0] / 100.0

    tone_keys = ("contrast", "highlights", "shadows", "whites", "blacks", "curve")
    if any(recipe.get(k) for k in tone_keys):
        grid, lut = tone_lut(recipe)
        L = np.interp(np.clip(L, 0, 1), grid, lut).astype(np.float32)
        report["tone_curve_samples"] = {f"{x:.2f}": round(float(np.interp(x, grid, lut)), 3)
                                        for x in (0.05, 0.25, 0.5, 0.75, 0.95)}
    cl = float(recipe.get("clarity", 0) or 0) / 100.0
    if cl:
        h, w = L.shape
        base = C.gaussian(L, max(2.0, min(h, w) / 60.0))
        mid = 1 - np.abs(L - 0.5) * 2  # midtones only: protects highlights/shadows from halos
        L = L + cl * 0.6 * (L - base) * np.clip(mid, 0, 1)

    a, b = lab[..., 1], lab[..., 2]
    chroma = np.hypot(a, b)
    scale = np.ones_like(chroma)
    vib = float(recipe.get("vibrance", 0) or 0) / 100.0
    if vib:
        hue = np.degrees(np.arctan2(b, a)) % 360
        skin = (hue >= 20) & (hue <= 70)
        w_ = np.clip(1 - chroma / 70.0, 0, 1)  # boost muted colours most
        if vib > 0:
            w_ = np.where(skin, w_ * 0.4, w_)
        scale *= 1 + vib * w_
    sat = float(recipe.get("saturation", 0) or 0) / 100.0
    if sat:
        scale *= 1 + sat
    if vib or sat:
        a, b = a * scale, b * scale
    dn = float(recipe.get("denoise_chroma", 0) or 0) / 100.0
    if dn:
        sig = 0.5 + 3.5 * dn
        a = (1 - dn) * a + dn * C.gaussian(a, sig)
        b = (1 - dn) * b + dn * C.gaussian(b, sig)
    vg = float(recipe.get("vignette", 0) or 0) / 100.0
    if vg:
        h, w = L.shape
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        rr = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2)) / math.sqrt(2)
        fall = np.clip((rr - 0.35) / 0.65, 0, 1) ** 2
        L = L * (1 + vg * 0.35 * fall) if vg < 0 else L + (1 - L) * vg * 0.35 * fall

    bw = recipe.get("bw")
    if bw:
        filt = (bw.get("filter") if isinstance(bw, dict) else None) or "neutral"
        weights = {"neutral": (0.2126, 0.7152, 0.0722), "yellow": (0.35, 0.6, 0.05),
                   "orange": (0.45, 0.5, 0.05), "red": (0.6, 0.38, 0.02),
                   "green": (0.15, 0.75, 0.10), "blue": (0.1, 0.3, 0.6)}[filt]
        if filt != "neutral":  # re-derive luminance through a colour filter, keep tone edits
            lin2 = C.lab_to_linear(np.stack([L * 100, a, b], -1))
            y = np.clip((lin2 * np.array(weights, dtype=np.float32)).sum(-1), 0, None)
            L = (C.linear_to_lab(np.repeat(y[..., None], 3, -1))[..., 0] / 100.0)
        a = np.zeros_like(a)
        b = np.zeros_like(b)
        report["bw"] = filt

    rgb = C.linear_to_srgb(C.lab_to_linear(np.stack([np.clip(L, 0, 1) * 100, a, b], -1)))
    rgb = np.clip(rgb, 0, 1)
    del lab, L, a, b

    # resize
    h, w = rgb.shape[:2]
    nw, nh = w, h
    if rs:
        if rs.get("exact"):
            nw, nh = int(rs["exact"][0]), int(rs["exact"][1])
        elif rs.get("long_edge"):
            s = float(rs["long_edge"]) / max(w, h)
            nw, nh = round(w * s), round(h * s)
        elif rs.get("width"):
            nw, nh = int(rs["width"]), round(h * int(rs["width"]) / w)
        elif rs.get("height"):
            nw, nh = round(w * int(rs["height"]) / h), int(rs["height"])
        if (nw > w or nh > h) and not rs.get("allow_upscale"):
            report["resize"] = f"skipped upscale {w}x{h} -> {nw}x{nh} (set resize.allow_upscale)"
            nw, nh = w, h
    scale_down = max(w / nw, h / nh)
    if (nw, nh) != (w, h):
        rgb = C.resize_float(rgb, nw, nh)
        if alpha is not None:
            alpha = np.clip(C.resize_channel(alpha, nw, nh), 0, 1)
        report["resize"] = f"{w}x{h} -> {nw}x{nh} (Lanczos, linear light)"

    # output sharpening: only by default when we downscaled noticeably
    sp = recipe.get("sharpen", "auto")
    if sp == "auto":
        sp = {"amount": 35, "radius": 0.6, "threshold": 2} if scale_down >= 1.5 else None
    if sp:
        amt = min(float(sp.get("amount", 40)), 150) / 100.0
        rad = float(sp.get("radius", 0.8))
        thr = float(sp.get("threshold", 2)) / 255.0
        y = C.luma(rgb)
        detail = y - C.gaussian(y, rad)
        mask = np.clip((np.abs(detail) - thr) / max(thr, 1e-4), 0, 1) if thr > 0 else 1.0
        rgb = np.clip(rgb + (amt * detail * mask)[..., None], 0, 1)
        report["sharpen"] = {"amount": round(amt * 100), "radius": rad, "threshold": round(thr * 255)}
    report["_photo"] = rgb  # metrics are measured on the photo, not the frame
    if frame:
        rgb, alpha, report["frame"] = Fr.render_frame(rgb, alpha, frame)
    if "straighten" in report:
        report["straighten"].pop("_map", None)
    return rgb, alpha, report


def do_reframe(rgb, alpha, spec, shape_spec, recipe, st_report):
    h, w = rgb.shape[:2]
    subj = spec.get("subject", "auto")
    if subj == "auto":
        found = S.find_subject(rgb)
        box, face_boxes = found["box"], found.get("faces") or []
        src = f"{found['source']} (confidence {found['confidence']})"
    else:
        box = [float(v) for v in subj]
        if st_report:  # subject was given in source coordinates
            box = map_box_through_straighten(box, st_report["rotated_deg"], st_report["_map"])
        face_boxes = S.detect_faces(rgb)
        src = "given"
    faces = bool(face_boxes)
    fit = spec.get("fit", "crop")
    if spec.get("contain"):  # whole image inside the new aspect, padded
        r = Fr._ratio(spec.get("aspect", "1:1"))
        cw, ch = (w, w / r) if w / h > r else (h * r, h)
        x0, y0 = (w - cw) / 2, (h - ch) / 2
        rgb, alpha = Fr.apply_crop(rgb, alpha, [x0, y0, x0 + cw, y0 + ch], fit if fit != "crop" else "blur",
                                   spec.get("fit_color"))
        return rgb, alpha, {"mode": "contain", "aspect": spec.get("aspect"), "fill": fit, "size": [rgb.shape[1], rgb.shape[0]]}
    sweet = safe = None
    place = spec.get("place", "thirds")
    if shape_spec:
        subj_aspect = max(0.2, min(5.0, ((box[2] - box[0]) * w) / max((box[3] - box[1]) * h, 1)))
        sweet, safe, aspect = Fr.sweet_and_safe(shape_spec, subj_aspect)
        place = "sweet" if place in ("thirds", "sweet") else place
        if spec.get("aspect") and abs(Fr._ratio(spec["aspect"]) - aspect) > 0.01:
            pass  # the shape's own aspect wins; a stretched heart looks wrong
    else:
        aspect = spec.get("aspect", "original")
    tight = float(spec.get("tightness", 0.5 if shape_spec else 0.35))
    margin = float(spec.get("margin", 0.04 if shape_spec else 0.05))
    mask_spec = shape_spec or (recipe.get("frame") or {"shape": "rect"})
    sal, _ = S.saliency_map(rgb)
    # Shapes hide part of the photo, so they demand more; plain rectangles may trim a large subject's
    # edges rather than pad (padding a rectangle reads as a mistake), but never a face.
    need_subj = float(spec.get("min_visible", 97 if shape_spec else 90))
    need_face = 99.0

    def attempt(t, fit_mode, strict, force_cw=None):
        bpx, r = Fr.plan_crop(w, h, box, aspect, place=place, tightness=t, margin=margin if strict else 0.0,
                              sweet=sweet, safe=safe if strict else None, faces=faces,
                              allow_pad=fit_mode in ("blur", "color"), force_cw=force_cw)
        vis = Fr.visibility(mask_spec, bpx, w, h, box, sal, face_boxes)
        ok = vis["subject_visible_pct"] >= need_subj and all(v >= need_face for v in vis["faces_visible_pct"])
        r["tightness_used"] = round(t, 2)
        r["placement_mode"] = "safe-box" if strict else "visibility-search"
        return ok, bpx, r, vis, fit_mode

    # Search order (first that keeps the subject and every face visible wins):
    #  1. plain crops, tight -> loose, judged only by measured visibility through the mask
    #  2. strict placement inside the shape's safe box, tight -> loose
    #  3. pad the canvas (feathered blur) - last resort, it shrinks the photo inside the frame
    steps = sorted({tight, *[x for x in (tight - 0.15, tight - 0.3, tight - 0.45) if x > 0], 0.0}, reverse=True)
    tries = [(t, fit, False, None) for t in steps] + [(t, fit, True, None) for t in steps]
    if fit == "crop" and spec.get("auto_pad", bool(shape_spec) or faces):
        # grow the canvas only as much as needed: from the largest in-image crop
        # towards the strict safe-box fit, stopping at the first that passes
        r_ = Fr._ratio(aspect) if aspect not in (None, "original") else w / h
        max_cw = min(w, h * r_)
        _, strict_rep = Fr.plan_crop(w, h, box, aspect, place=place, tightness=tight, margin=margin,
                                     sweet=sweet, safe=safe, faces=faces, allow_pad=True)
        strict_cw = strict_rep["box_px"][2] - strict_rep["box_px"][0]
        for k in (0.1, 0.2, 0.3, 0.45, 0.6, 0.8, 1.0):
            tries.append((0.0, "blur", False, max_cw + k * max(0.0, strict_cw - max_cw)))
        tries.append((tight, "blur", True, None))
    best = None
    for t, fm, strict, fcw in tries:
        res = attempt(t, fm, strict, fcw)
        if best is None or res[3]["subject_visible_pct"] > best[3]["subject_visible_pct"]:
            best = res
        if res[0]:
            best = res
            break
    ok, box_px, rep, vis, used_fit = best
    rgb, alpha = Fr.apply_crop(rgb, alpha, box_px, used_fit, spec.get("fit_color"),
                               fill="mirror" if shape_spec else "zoom")
    rep["visibility"] = vis
    rep["visibility_ok"] = ok
    if not ok:
        rep["notes"].append("Subject is still partly hidden by the frame. Try another shape, fit='blur', "
                            "or confirm the subject box with vision and pass reframe.subject.")
    if used_fit != fit:
        rep["notes"].append(f"Canvas padded ({used_fit}) so the subject fits inside the frame.")
    if rep["tightness_used"] != round(tight, 2):
        rep["notes"].append(f"Loosened tightness {tight} -> {rep['tightness_used']} to keep the subject visible.")
    # subject/face boxes in output-photo coordinates, for the --check image
    x0, y0, x1, y1 = box_px

    def to_crop(b):
        return [round((b[0] * w - x0) / (x1 - x0), 4), round((b[1] * h - y0) / (y1 - y0), 4),
                round((b[2] * w - x0) / (x1 - x0), 4), round((b[3] * h - y0) / (y1 - y0), 4)]

    rep["_check_boxes"] = {"subject": to_crop(box), "faces": [to_crop(f) for f in face_boxes]}
    rep.update(subject_source=src, subject_box_source=[round(v, 4) for v in box], place=place)
    if shape_spec:
        rep.update(shape_sweet_spot=sweet, shape_safe_box=safe)
    return rgb, alpha, rep


def write_check(out, alpha, photo_shape, report, boxes, path):
    """Final image on a grey checkerboard (so transparency is visible) with boxes drawn."""
    from PIL import Image, ImageDraw
    h, w = out.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    board = np.where(((yy // 24 + xx // 24) % 2)[..., None] == 0, 0.62, 0.74).astype(np.float32)
    a = alpha[..., None] if alpha is not None else 1.0
    im = Image.fromarray(C.to_uint8(out * a + board * (1 - a), dither=False))
    d = ImageDraw.Draw(im)
    ox, oy = (report.get("frame") or {}).get("photo_offset", [0, 0])
    ph, pw = photo_shape[:2]
    lw = max(2, round(min(w, h) / 300))
    if boxes:
        b = boxes["subject"]
        d.rectangle([ox + b[0] * pw, oy + b[1] * ph, ox + b[2] * pw, oy + b[3] * ph], outline=(255, 40, 40), width=lw)
        for f in boxes["faces"]:
            d.rectangle([ox + f[0] * pw, oy + f[1] * ph, ox + f[2] * pw, oy + f[3] * ph], outline=(255, 210, 0), width=lw)
    s = 1400 / max(w, h)
    if s < 1:
        im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return str(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--recipe", help="JSON string, path to .json, or 'auto'")
    ap.add_argument("--scene", default="general", choices=sorted(A.SCENES),
                    help="scene intent used by --recipe auto")
    ap.add_argument("--look", help="preset from templates/looks (e.g. natural, moody)")
    ap.add_argument("--set", action="append", metavar="KEY=VALUE",
                    help="override one value, dotted keys allowed: --set crop.aspect=4:5")
    ap.add_argument("--allow-extreme", action="store_true", help="bypass taste limits")
    ap.add_argument("--overwrite", action="store_true", help="allow output to replace an existing file")
    ap.add_argument("--dry-run", action="store_true", help="print the resolved recipe and exit")
    ap.add_argument("--check", metavar="PNG", help="also write a review image with the subject (red) and "
                                                  "face (yellow) boxes drawn on the final output")
    args = ap.parse_args()

    src, dst = Path(args.input), Path(args.output)
    if src.resolve() == dst.resolve():
        raise SystemExit("Refusing to overwrite the original. Write to a new file.")
    if dst.exists() and not args.overwrite:
        raise SystemExit(f"{dst} exists. Use a new name (e.g. _v2) or pass --overwrite.")
    recipe = load_recipe(args, src)
    warnings = validate(recipe, args.allow_extreme)
    if args.dry_run:
        print(json.dumps({"recipe": recipe, "warnings": warnings}, indent=2))
        return

    rgb, alpha, info = C.load(src)
    before = None
    out, alpha, report = apply(rgb, alpha, recipe)
    warnings += C.save(out, alpha, dst, exif=info.get("exif"),
                       quality=recipe.get("quality", 90), metadata=recipe.get("metadata", "keep"))
    photo = report.pop("_photo")
    before = A.measure(report.pop("_geom"))
    after = A.measure(photo)
    boxes = (report.get("reframe") or {}).pop("_check_boxes", None)
    if args.check:
        report["check_image"] = write_check(out, alpha, photo.shape, report, boxes, args.check)

    def key(m):
        return {"L_median": m["exposure"]["L_median"], "L_p1": m["exposure"]["L_p1"],
                "L_p99": m["exposure"]["L_p99"], "clip_hi_pct": m["exposure"]["clip_highlights_pct"],
                "clip_lo_pct": m["exposure"]["clip_shadows_pct"],
                "contrast_p5_p95": m["contrast"]["L_range_p5_p95"],
                "chroma_mean": m["color"]["chroma_mean"], "cast_ab": [m["cast"]["a"], m["cast"]["b"]],
                "tilt_deg": m["geometry"]["tilt_deg"]}

    if after["exposure"]["clip_highlights_pct"] > before["exposure"]["clip_highlights_pct"] + 0.5:
        warnings.append("Edit increased highlight clipping; reduce exposure/whites or pull highlights.")
    if after["exposure"]["clip_shadows_pct"] > before["exposure"]["clip_shadows_pct"] + 1.0:
        warnings.append("Edit crushed more shadows; reduce blacks/contrast or lift shadows.")
    if after["color"]["oversaturated_pct"] > max(2.0, before["color"]["oversaturated_pct"] * 2):
        warnings.append("Colours now look oversaturated in places; lower vibrance/saturation.")
    print(json.dumps({"output": str(dst), "size": [out.shape[1], out.shape[0]], "recipe": recipe,
                      "applied": report, "before": key(before), "after": key(after),
                      "warnings": warnings}, indent=2))


if __name__ == "__main__":
    main()
