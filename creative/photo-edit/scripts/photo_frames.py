"""Reframing (subject-aware crops) and frames: mats, polaroids, shaped cut-outs.

Shapes are rasterised 4x supersampled for clean anti-aliased edges. For every
shape (built-in, polygon or mask image) the planner computes:
  * sweet spot - the point deepest inside the shape (pole of inaccessibility),
    where the subject's centre goes;
  * safe box   - the largest box of the subject's aspect, centred there, that
    stays fully inside the shape, so the subject is never sliced by the edge.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import photo_core as C

SS = 4  # supersampling factor for shape edges


# ---------------------------------------------------------------- shapes

def _heart(n=400):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    x = 16 * np.sin(t) ** 3
    y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
    return np.stack([x, y], 1)


def _ngon(n, rot=-90):
    t = np.radians(np.arange(n) * 360 / n + rot)
    return np.stack([np.cos(t), np.sin(t)], 1)


def _star(points=5, inner=0.48):
    t = np.radians(np.arange(points * 2) * 180 / points - 90)
    r = np.where(np.arange(points * 2) % 2 == 0, 1.0, inner)
    return np.stack([np.cos(t) * r, np.sin(t) * r], 1)


def _arch(aspect=0.75, n=120):
    # rectangle w=aspect, h=1 with a semicircular top of radius aspect/2
    r = aspect / 2
    t = np.linspace(np.pi, 2 * np.pi, n)
    top = np.stack([r + r * np.cos(t), r + r * np.sin(t)], 1)
    return np.vstack([top, [[aspect, 1.0], [0.0, 1.0]]])


def _rounded(aspect, radius, n=24):
    r = radius * min(aspect, 1.0)
    pts = []
    for cx, cy, a0 in ((aspect - r, r, -90), (aspect - r, 1 - r, 0), (r, 1 - r, 90), (r, r, 180)):
        t = np.radians(np.linspace(a0, a0 + 90, n))
        pts.append(np.stack([cx + r * np.cos(t), cy + r * np.sin(t)], 1))
    return np.vstack(pts)


def shape_polygon(spec):
    """Return (normalised polygon points in 0..1 of its bbox, natural aspect w/h) or (None, aspect) for masks."""
    name = spec.get("shape", "rect")
    if name in ("rect", "none"):
        a = spec.get("aspect")
        return None, (None if a is None else _ratio(a))
    if name == "rounded":
        a = _ratio(spec.get("aspect", 1.0)) if spec.get("aspect") else None
        return ("rounded", a), a
    if name == "mask":
        m = Image.open(spec["mask"])
        return None, m.width / m.height
    raw = {
        "heart": _heart,
        "circle": lambda: _ngon(256),
        "ellipse": lambda: _ngon(256) * np.array([_ratio(spec.get("aspect", 0.8)), 1.0]),
        "hexagon": lambda: _ngon(6),
        "octagon": lambda: _ngon(8, rot=-90 + 22.5),
        "diamond": lambda: _ngon(4) * np.array([_ratio(spec.get("aspect", 0.8)), 1.0]),
        "star": lambda: _star(int(spec.get("points", 5)), float(spec.get("inner", 0.48))),
        "arch": lambda: _arch(_ratio(spec.get("aspect", 0.75))),
        "polygon": lambda: np.array(spec["points"], dtype=np.float64),
    }
    if name not in raw:
        raise SystemExit(f"Unknown frame shape '{name}'. Use rect, rounded, circle, ellipse, heart, star, "
                         "hexagon, octagon, diamond, arch, polygon (points) or mask (path to PNG).")
    p = raw[name]().astype(np.float64)
    p -= p.min(0)
    wh = p.max(0)
    return p / wh, float(wh[0] / wh[1])


def _ratio(s):
    if isinstance(s, (int, float)):
        return float(s)
    a, _, b = str(s).replace("x", ":").partition(":")
    return float(a) / float(b)


def shape_mask(spec, w, h):
    """Anti-aliased float mask (h, w) in 0..1 for a frame spec at a given size."""
    name = spec.get("shape", "rect")
    if name == "mask":
        m = Image.open(spec["mask"])
        m = m.getchannel("A") if "A" in m.getbands() else m.convert("L")
        return np.asarray(m.resize((w, h), Image.LANCZOS), np.float32) / 255.0
    poly, _ = shape_polygon(spec)
    big = Image.new("L", (w * SS, h * SS), 0)
    d = ImageDraw.Draw(big)
    if poly is None:
        d.rectangle([0, 0, w * SS, h * SS], fill=255)
    elif isinstance(poly, tuple):  # rounded rect
        r = float(spec.get("radius", 0.06)) * min(w, h) * SS
        d.rounded_rectangle([0, 0, w * SS - 1, h * SS - 1], radius=r, fill=255)
    else:
        pts = [(x * (w * SS - 1), y * (h * SS - 1)) for x, y in poly]
        d.polygon(pts, fill=255)
    return np.asarray(big.resize((w, h), Image.BOX), np.float32) / 255.0


def sweet_and_safe(spec, subject_aspect=1.0, res=240):
    """Pole of inaccessibility (rel x, y) and largest subject-aspect box (rel) centred on it."""
    _, aspect = shape_polygon(spec)
    aspect = aspect or 1.0
    w, h = (res, max(8, round(res / aspect))) if aspect >= 1 else (max(8, round(res * aspect)), res)
    m = shape_mask(spec, w, h) > 0.5
    # chessboard distance transform by iterative erosion
    dist = np.zeros(m.shape, np.int32)
    cur = m.copy()
    k = 0
    while cur.any() and k < max(w, h):
        k += 1
        dist[cur] = k
        p = np.pad(cur, 1, constant_values=False)
        cur = (p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:])
    ys, xs = np.nonzero(dist == dist.max())
    sx, sy = xs.mean() / w, ys.mean() / h
    # grow a box of the subject's aspect (in pixel terms) around the sweet spot
    lo, hi = 0.0, 1.0
    for _ in range(20):
        s = (lo + hi) / 2
        bw = s * w if subject_aspect >= 1 else s * h * subject_aspect
        bh = bw / subject_aspect
        x0, x1 = int(sx * w - bw / 2), int(math.ceil(sx * w + bw / 2))
        y0, y1 = int(sy * h - bh / 2), int(math.ceil(sy * h + bh / 2))
        ok = x0 >= 0 and y0 >= 0 and x1 <= w and y1 <= h and m[y0:y1, x0:x1].all()
        lo, hi = (s, hi) if ok else (lo, s)
    bw = lo * w if subject_aspect >= 1 else lo * h * subject_aspect
    bh = bw / subject_aspect
    safe = [(sx * w - bw / 2) / w, (sy * h - bh / 2) / h, (sx * w + bw / 2) / w, (sy * h + bh / 2) / h]
    return (round(sx, 4), round(sy, 4)), [round(v, 4) for v in safe], aspect


# ---------------------------------------------------------------- reframe planner

def plan_crop(W, H, subj_box, aspect, place="thirds", tightness=0.35, margin=0.05,
              sweet=None, safe=None, faces=False, allow_pad=False, force_cw=None):
    """Choose a crop (pixel box, may extend past the image when allow_pad) for `aspect`.

    subj_box: relative [x0,y0,x1,y1] of the subject in the source.
    place:    'thirds' | 'center' | 'golden' | 'keep' | 'sweet' (shapes)
    tightness: 0 = widest crop of this aspect, 1 = as tight as the subject allows.
    """
    r = _ratio(aspect) if aspect not in (None, "original") else W / H
    sx0, sy0, sx1, sy1 = subj_box[0] * W, subj_box[1] * H, subj_box[2] * W, subj_box[3] * H
    sw, sh = max(sx1 - sx0, 1), max(sy1 - sy0, 1)
    scx, scy = (sx0 + sx1) / 2, (sy0 + sy1) / 2
    safe = safe or [0.0, 0.0, 1.0, 1.0]
    safe_w = max(safe[2] - safe[0] - 2 * margin, 0.05)
    safe_h = max(safe[3] - safe[1] - 2 * margin, 0.05)
    max_cw = min(W, H * r)
    min_cw = max(sw / safe_w, sh * r / safe_h)  # tightest crop that still holds the subject
    notes = []
    if force_cw is not None:
        cw = float(force_cw)
    elif min_cw > max_cw:
        if allow_pad:
            cw = min_cw
            notes.append("Subject needs more room than the image has in this aspect: canvas padded.")
        else:
            cw = max_cw
            notes.append("Subject cannot fully fit this aspect without padding; it will be clipped. "
                         "Use reframe.fit='blur' or 'color', or a different aspect.")
    else:
        cw = max_cw - float(tightness) * (max_cw - min_cw)
    ch = cw / r

    # where the subject centre should land inside the crop
    rx, ry = scx / W, scy / H
    if place == "sweet" and sweet:
        tx, ty = sweet
    elif place == "center":
        tx, ty = 0.5, 0.5
    elif place == "keep":
        tx, ty = rx, ry
    else:
        lines = (1 / 3, 2 / 3) if place == "thirds" else (0.382, 0.618)
        tx = 0.5 if abs(rx - 0.5) < 0.05 else (lines[0] if rx < 0.5 else lines[1])
        if faces:
            ty = 0.40  # face centre slightly below the upper third puts eyes on it
        else:
            ty = 0.5 if abs(ry - 0.5) < 0.05 else (lines[0] if ry < 0.5 else lines[1])
    x0, y0 = scx - tx * cw, scy - ty * ch
    # keep the whole subject inside the safe area of the crop
    x0 = min(max(x0, sx1 - (safe[2] - margin) * cw), sx0 - (safe[0] + margin) * cw) if cw * safe_w >= sw else x0
    y0 = min(max(y0, sy1 - (safe[3] - margin) * ch), sy0 - (safe[1] + margin) * ch) if ch * safe_h >= sh else y0
    if not allow_pad:
        x0 = min(max(x0, 0), W - cw)
        y0 = min(max(y0, 0), H - ch)
    box = [x0, y0, x0 + cw, y0 + ch]
    inside = [(sx0 - x0) / cw, (sy0 - y0) / ch, (sx1 - x0) / cw, (sy1 - y0) / ch]
    clipped = inside[0] < -0.005 or inside[1] < -0.005 or inside[2] > 1.005 or inside[3] > 1.005
    pad = [max(0, -x0), max(0, -y0), max(0, x0 + cw - W), max(0, y0 + ch - H)]
    return box, {
        "box_px": [int(round(v)) for v in box], "aspect": round(r, 4),
        "subject_in_crop": [round(float(v), 3) for v in inside],
        "subject_centre_in_crop": [round(float((scx - x0) / cw), 3), round(float((scy - y0) / ch), 3)],
        "subject_area_pct": round(float(sw * sh / (cw * ch) * 100), 1),
        "kept_of_source_pct": round(float(min(cw, W) * min(ch, H) / (W * H) * 100), 1),
        "subject_clipped": bool(clipped), "padding_px": [int(round(v)) for v in pad], "notes": notes,
    }


def apply_crop(rgb, alpha, box, fit="blur", fit_color=None, fill="zoom"):
    """Crop to a pixel box; areas outside the image are filled.

    fit="blur" with fill="zoom": the photo scaled to cover the canvas, heavily blurred and dimmed
    (the familiar story/banner background; right for rectangles).
    fit="blur" with fill="mirror": the photo's own edges mirrored outward and blurred (right for shaped
    cut-outs, where the mask hides most of the padding and a zoomed copy would ghost).
    fit="color": a flat colour (fit_color).
    """
    H, W = rgb.shape[:2]
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    cw, ch = x1 - x0, y1 - y0
    if x0 >= 0 and y0 >= 0 and x1 <= W and y1 <= H:
        return rgb[y0:y1, x0:x1], (alpha[y0:y1, x0:x1] if alpha is not None else None)
    if fit == "blur" and fill == "zoom":
        s_ = max(cw / W, ch / H)
        small_s = min(1.0, 600 / max(cw, ch))
        zw, zh = max(8, round(W * s_ * small_s)), max(8, round(H * s_ * small_s))
        bg = C.resize_float(rgb, zw, zh)
        sw_, sh_ = max(8, round(cw * small_s)), max(8, round(ch * small_s))
        oy, ox = (zh - sh_) // 2, (zw - sw_) // 2
        bg = C.gaussian(bg[oy:oy + sh_, ox:ox + sw_], max(sw_, sh_) / 25)
        canvas = C.resize_float(bg, cw, ch) * 0.8
    elif fit == "blur":
        # mirror the photo's own edges outward, then blur: reads as a soft continuation
        pl, pt_ = max(0, -x0), max(0, -y0)
        pr, pb = max(0, x1 - W), max(0, y1 - H)
        ext = np.pad(rgb, ((pt_, pb), (pl, pr), (0, 0)), mode="symmetric")
        ext = ext[y0 + pt_:y0 + pt_ + ch, x0 + pl:x0 + pl + cw]  # padded array starts at (-pl, -pt_)
        small_s = min(1.0, 600 / max(cw, ch))
        sw_, sh_ = max(8, round(cw * small_s)), max(8, round(ch * small_s))
        blurred = C.resize_float(C.gaussian(C.resize_float(ext, sw_, sh_), max(sw_, sh_) / 45), cw, ch)
        canvas = blurred * 0.96
    else:
        col = parse_color(fit_color or "auto-dark", rgb)
        canvas = np.ones((ch, cw, 3), np.float32) * np.array(col, np.float32)
    canvas = canvas.copy()
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(W, x1), min(H, y1)
    piece = rgb[sy0:sy1, sx0:sx1]
    if fit == "blur":  # feather the seam on padded sides so the photo melts into its blurred extension
        ph, pw = piece.shape[:2]
        f = max(2, int(min(cw, ch) * 0.04))
        ramp_x = np.ones(pw, np.float32)
        ramp_y = np.ones(ph, np.float32)
        r = np.linspace(0, 1, f, dtype=np.float32)
        if x0 < 0:
            ramp_x[:f] = np.minimum(ramp_x[:f], r)
        if x1 > W:
            ramp_x[-f:] = np.minimum(ramp_x[-f:], r[::-1])
        if y0 < 0:
            ramp_y[:f] = np.minimum(ramp_y[:f], r)
        if y1 > H:
            ramp_y[-f:] = np.minimum(ramp_y[-f:], r[::-1])
        wgt = (ramp_y[:, None] * ramp_x[None, :])[..., None]
        region = canvas[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
        piece = piece * wgt + region * (1 - wgt)
    canvas[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = piece
    a = None
    if alpha is not None:
        a = np.ones((ch, cw), np.float32)
        a[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = alpha[sy0:sy1, sx0:sx1]
    return canvas, a


# ---------------------------------------------------------------- colours

def parse_color(c, rgb=None):
    """Hex '#rrggbb', [r,g,b] 0-255, 'transparent', or auto-light / auto-dark / auto-accent from the photo."""
    if c is None or c == "transparent":
        return None
    if isinstance(c, (list, tuple)):
        return [v / 255.0 for v in c[:3]]
    c = str(c)
    if c.startswith("#") and len(c) in (4, 7):
        if len(c) == 4:
            c = "#" + "".join(ch * 2 for ch in c[1:])
        return [int(c[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    named = {"white": "#ffffff", "black": "#000000", "warm-white": "#f4f1ea", "off-white": "#f7f6f2",
             "charcoal": "#2b2b2b", "cream": "#efe8d8"}
    if c in named:
        return parse_color(named[c])
    if c.startswith("auto") and rgb is not None:
        lab = C.srgb_to_lab(C.working_copy(rgb, 256)).reshape(-1, 3)
        a_, b_ = float(np.median(lab[:, 1])), float(np.median(lab[:, 2]))
        if c == "auto-light":
            L, k = 94.0, 0.25
        elif c == "auto-dark":
            L, k = 16.0, 0.35
        else:  # auto-accent: the most common clearly-coloured hue, muted
            ch = np.hypot(lab[:, 1], lab[:, 2])
            sel = lab[ch > 20]
            if len(sel) < 50:
                return parse_color("auto-dark", rgb)
            hue = np.degrees(np.arctan2(sel[:, 2], sel[:, 1])) % 360
            hist, edges = np.histogram(hue, bins=24, range=(0, 360))
            hh = np.radians(edges[np.argmax(hist)] + 7.5)
            L, a_, b_, k = 42.0, 30 * math.cos(hh), 30 * math.sin(hh), 1.0
        ta, tb = a_ * k, b_ * k
        cap = {"auto-light": 2.5, "auto-dark": 5.0}.get(c, 40.0)  # mats must read as near-neutral
        mag = math.hypot(ta, tb)
        if mag > cap:
            ta, tb = ta * cap / mag, tb * cap / mag
        lab1 = np.array([[[L, ta, tb]]], np.float32)
        return [float(v) for v in np.clip(C.linear_to_srgb(C.lab_to_linear(lab1))[0, 0], 0, 1)]
    raise SystemExit(f"Unrecognised colour '{c}'. Use #rrggbb, a name, transparent or auto-light/auto-dark/auto-accent.")


# ---------------------------------------------------------------- subject visibility

def photo_mask(spec, w, h):
    """The part of the photo a frame leaves visible (1) vs hides (0)."""
    shape = spec.get("shape", "rect")
    if shape == "rect":
        if spec.get("corner_radius"):
            return shape_mask({"shape": "rounded", "radius": spec["corner_radius"]}, w, h)
        return np.ones((h, w), np.float32)
    return shape_mask(spec, w, h)


def visibility(spec, box_px, W, H, subj_box, sal, faces=(), res=320):
    """How much of the subject survives a frame, for a crop box on a W x H image.

    subject_visible_pct - saliency-weighted share of the subject inside the crop AND the mask
    subject_comfort_pct - same, against a mask shrunk ~2% (subject not touching the edge/stroke)
    faces_visible_pct   - coverage of each face box (people must never be cut)
    """
    x0, y0, x1, y1 = box_px
    cw, ch = x1 - x0, y1 - y0
    a = cw / ch
    mw, mh = (res, max(8, round(res / a))) if a >= 1 else (max(8, round(res * a)), res)
    m = photo_mask(spec, mw, mh)
    shrink = max(1.0, 0.02 * min(mw, mh))
    mc = np.clip((C.gaussian(m, shrink) - 0.97) / 0.03, 0, 1)
    sh, sw = sal.shape

    def sample(X, Y):
        return sal[np.clip((Y * sh).astype(int), 0, sh - 1), np.clip((X * sw).astype(int), 0, sw - 1)]

    # sample the subject box densely in image space; map each sample into the mask
    sx = np.linspace(subj_box[0], subj_box[2], 96)
    sy = np.linspace(subj_box[1], subj_box[3], 96)
    SX, SY = np.meshgrid(sx, sy)
    wgt = sample(SX, SY) + 1e-3  # tiny floor so flat subjects still count
    u = (SX * W - x0) / cw
    v = (SY * H - y0) / ch
    inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    iu = np.clip((u * mw).astype(int), 0, mw - 1)
    iv = np.clip((v * mh).astype(int), 0, mh - 1)
    mv = np.where(inside, m[iv, iu], 0.0)
    mcv = np.where(inside, mc[iv, iu], 0.0)
    tot = float(wgt.sum())
    out = {"subject_visible_pct": round(100 * float((wgt * mv).sum()) / tot, 1),
           "subject_comfort_pct": round(100 * float((wgt * mcv).sum()) / tot, 1),
           "faces_visible_pct": []}
    for f in faces:
        fx = np.linspace(f[0], f[2], 32)
        fy = np.linspace(f[1], f[3], 32)
        FX, FY = np.meshgrid(fx, fy)
        fu, fv = (FX * W - x0) / cw, (FY * H - y0) / ch
        fin = (fu >= 0) & (fu < 1) & (fv >= 0) & (fv < 1)
        cov = np.where(fin, m[np.clip((fv * mh).astype(int), 0, mh - 1), np.clip((fu * mw).astype(int), 0, mw - 1)], 0)
        out["faces_visible_pct"].append(round(100 * float(cov.mean()), 1))
    return out


# ---------------------------------------------------------------- frame render

def render_frame(rgb, alpha, spec):
    """Composite the photo into a frame. Returns (rgb, alpha or None, report)."""
    h, w = rgb.shape[:2]
    short = min(w, h)
    style = spec.get("style", "mat" if spec.get("shape", "rect") in ("rect", "rounded") else "cutout")
    rep = {"style": style, "shape": spec.get("shape", "rect")}

    m = photo_mask(spec, w, h)
    if alpha is not None:
        m = m * alpha

    # border sizes (fractions of the photo's short edge)
    if style == "polaroid":
        t = float(spec.get("border", 0.06))
        pads = [t, t, t, float(spec.get("bottom", 0.22))]  # l, t, r, b
        bg_default = "warm-white"
    elif style == "mat":
        t = float(spec.get("border", 0.06))
        pads = [t, t, t, t * float(spec.get("bottom_weight", 1.0))]
        bg_default = "off-white"
    else:  # cutout shapes float on a background (transparent by default)
        t = float(spec.get("padding", 0.06 if spec.get("shadow") or spec.get("stroke") else 0.0))
        pads = [t, t, t, t]
        bg_default = "transparent"
    pl, pt, pr, pb = [int(round(p * short)) for p in pads]
    W, H = w + pl + pr, h + pt + pb
    bgc = parse_color(spec.get("background", spec.get("color", bg_default)), rgb)
    # premultiplied layers composited with the "over" operator
    if bgc is not None:
        c = np.zeros((H, W, 3), np.float32) + np.array(bgc, np.float32)
        a = np.ones((H, W), np.float32)
    else:
        c = np.zeros((H, W, 3), np.float32)
        a = np.zeros((H, W), np.float32)

    def over(c, a, color, alpha_):
        s = alpha_[..., None]
        return color * s + c * (1 - s), alpha_ + a * (1 - alpha_)

    full_m = np.zeros((H, W), np.float32)
    full_m[pt:pt + h, pl:pl + w] = m

    stroke = float(spec.get("stroke", 0) or 0)
    stroke_m = None
    if stroke > 0:  # band just outside the shape edge
        sw = max(1.0, stroke * short)
        outer = np.clip((C.gaussian(full_m, sw / 2.0) - 0.02) / 0.06, 0, 1)
        stroke_m = np.clip(np.maximum(outer, full_m) - full_m, 0, 1)
        rep["stroke_px"] = round(sw)

    if spec.get("shadow"):
        base = np.maximum(full_m, stroke_m) if stroke_m is not None else full_m
        r = short * float(spec.get("shadow_size", 0.025))
        sh = C.gaussian(np.roll(base, int(r * 0.6), axis=0), r) * float(spec.get("shadow_opacity", 0.35))
        c, a = over(c, a, np.zeros(3, np.float32), sh)
        rep["shadow_px"] = round(r)

    if stroke_m is not None:
        sc = np.array(parse_color(spec.get("stroke_color", "auto-dark"), rgb), np.float32)
        c, a = over(c, a, sc, stroke_m)

    if spec.get("keyline"):  # thin line hugging the photo edge (mats/polaroids)
        kw = max(1, round(float(spec["keyline"]) * short))
        kc = np.array(parse_color(spec.get("keyline_color", "auto-dark"), rgb), np.float32)
        ring = np.zeros((H, W), np.float32)
        ring[max(0, pt - kw):pt + h + kw, max(0, pl - kw):pl + w + kw] = 1
        ring[pt:pt + h, pl:pl + w] = 0
        c, a = over(c, a, kc, ring)

    photo = np.zeros((H, W, 3), np.float32)
    photo[pt:pt + h, pl:pl + w] = rgb
    c, a = over(c, a, photo, full_m)
    canvas = c / np.maximum(a, 1e-6)[..., None]
    canvas_a = a
    rep["canvas"] = [W, H]
    rep["photo_offset"] = [pl, pt]
    transparent = bgc is None
    return canvas, (canvas_a if transparent or alpha is not None else None), rep
