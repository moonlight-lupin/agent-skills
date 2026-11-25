"""Subject detection and composition measurement (numpy only; OpenCV optional).

The subject finder fuses four cues on a small working copy:
  * colour distinctness (frequency-tuned saliency, Achanta 2009)
  * spectral-residual saliency (Hou & Zhang 2007)
  * focus: where fine detail lives (subjects are usually the sharp part)
  * faces, when OpenCV is installed (strongest cue; people are the subject)
with a mild centre prior. It is a proposal, not ground truth: the agent should
confirm it with `vision_analyze` on the overlay image, or pass a box it trusts.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np
from PIL import Image, ImageDraw

import photo_core as C

try:
    import cv2  # type: ignore
except Exception:
    cv2 = None

POWER_POINTS = [(1 / 3, 1 / 3), (2 / 3, 1 / 3), (1 / 3, 2 / 3), (2 / 3, 2 / 3)]
PHI = 0.382  # golden-section lines at 0.382 / 0.618


def _norm(a):
    a = a.astype(np.float32)
    lo, hi = np.percentile(a, 1), np.percentile(a, 99.5)
    return np.clip((a - lo) / max(hi - lo, 1e-6), 0, 1)


def _small(rgb, long_edge):
    h, w = rgb.shape[:2]
    s = long_edge / max(h, w)
    if s >= 1:
        return rgb
    return C.resize_float(rgb, max(8, round(w * s)), max(8, round(h * s)))


def detect_faces(rgb):
    """Return list of [x0,y0,x1,y1] relative boxes (largest first). Needs OpenCV."""
    # Haar cascades ship with OpenCV 4.x (removed from the main package in 5.x).
    if cv2 is None or not hasattr(cv2, "CascadeClassifier") or not hasattr(cv2, "data"):
        return []
    g = (C.luma(_small(rgb, 1000)) * 255).astype(np.uint8)
    h, w = g.shape
    found = []
    for name in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
        casc = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        if casc.empty():
            continue
        boxes = casc.detectMultiScale(g, scaleFactor=1.1, minNeighbors=6,
                                      minSize=(max(20, w // 40), max(20, w // 40)))
        for (x, y, bw, bh) in (boxes if len(boxes) else []):
            box = [x / w, y / h, (x + bw) / w, (y + bh) / h]
            if not any(_iou(box, f) > 0.3 for f in found):
                found.append(box)
    found.sort(key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))
    return found[:8]


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


def saliency_map(rgb):
    """Return a saliency map (float32, ~256 px long edge) in 0..1."""
    small = _small(rgb, 256)
    h, w = small.shape[:2]
    lab = C.srgb_to_lab(small)
    # 1. colour distinctness vs the image mean (on a lightly blurred copy)
    lb = C.gaussian(lab, 1.5)
    ft = np.sqrt(((lb - lab.reshape(-1, 3).mean(0)) ** 2 * np.array([0.5, 1, 1], np.float32)).sum(-1))
    # 2. spectral residual on a 64 px grey copy
    g = C.luma(_small(rgb, 64))
    F = np.fft.fft2(g)
    logamp = np.log(np.abs(F) + 1e-8)
    k = np.ones((3, 3), np.float32) / 9
    pad = np.pad(logamp, 1, mode="wrap")
    avg = sum(pad[i:i + logamp.shape[0], j:j + logamp.shape[1]] * k[i, j] for i in range(3) for j in range(3))
    sr = np.abs(np.fft.ifft2(np.exp(logamp - avg + 1j * np.angle(F)))) ** 2
    sr = C.resize_channel(C.gaussian(sr.astype(np.float32), 2.0), w, h)
    # 3. focus: local fine-detail energy (only trusted if it varies across the frame)
    mid = _small(rgb, 768)
    y = C.luma(mid)
    lap = np.abs(y[1:-1, 1:-1] * 4 - y[:-2, 1:-1] - y[2:, 1:-1] - y[1:-1, :-2] - y[1:-1, 2:])
    foc = C.resize_channel(C.gaussian(lap, 6.0), w, h)
    focus_spread = float(np.percentile(foc, 95) / (np.median(foc) + 1e-6))
    wf = 0.35 if focus_spread > 6 else 0.15 if focus_spread > 3 else 0.0
    # 4. centre-surround (difference of Gaussians, two scales) - compact standouts like a sun or a face
    wl = np.array([1.0, 0.7, 0.7], np.float32)
    cs = np.zeros((h, w), np.float32)
    for s_in, s_out in ((2.0, 12.0), (4.0, 24.0)):
        cs += np.sqrt((((C.gaussian(lab, s_in) - C.gaussian(lab, s_out)) * wl) ** 2).sum(-1))
    s = 0.30 * _norm(ft) + 0.30 * _norm(cs) + (0.40 - wf) * _norm(sr) + wf * _norm(foc)
    # 5. mild centre prior
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    prior = np.exp(-(((xx / w - 0.5) ** 2) / 0.18 + ((yy / h - 0.5) ** 2) / 0.18))
    s = _norm(C.gaussian(s * (0.65 + 0.35 * prior), 2.0))
    return s, {"focus_spread": round(focus_spread, 1), "focus_weight": wf}


def _otsu(v):
    hist, edges = np.histogram(v, bins=64, range=(0, 1))
    p = hist / max(hist.sum(), 1)
    omega = np.cumsum(p)
    mu = np.cumsum(p * (edges[:-1] + edges[1:]) / 2)
    mt = mu[-1]
    sb = (mt * omega - mu) ** 2 / (omega * (1 - omega) + 1e-9)
    return float(edges[int(np.argmax(sb)) + 1])


def _components(mask):
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    comps = []
    n = 0
    for y0 in range(h):
        for x0 in range(w):
            if mask[y0, x0] and not lab[y0, x0]:
                n += 1
                q = deque([(y0, x0)])
                lab[y0, x0] = n
                pts = []
                while q:
                    y, x = q.popleft()
                    pts.append((y, x))
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                            lab[ny, nx] = n
                            q.append((ny, nx))
                comps.append(np.array(pts))
    return comps


def find_subject(rgb, hint=None):
    """Locate the main subject. `hint` = relative [x0,y0,x1,y1] to trust instead."""
    h0, w0 = rgb.shape[:2]
    faces = detect_faces(rgb)
    if hint is not None:
        return {"box": [round(float(v), 4) for v in hint], "source": "hint", "confidence": 1.0,
                "faces": faces, "candidates": []}
    s, cues = saliency_map(rgb)
    h, w = s.shape
    thr = max(_otsu(s), 0.35)
    comps = _components(s >= thr)
    cands = []
    for pts in comps:
        if len(pts) < max(6, h * w * 0.002):
            continue
        ys, xs = pts[:, 0], pts[:, 1]
        mass = float(s[ys, xs].sum())
        box = [xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h]
        cands.append({"box": [round(float(v), 4) for v in box], "mass": mass,
                      "centroid": [round(float(np.average(xs, weights=s[ys, xs]) / w), 4),
                                   round(float(np.average(ys, weights=s[ys, xs]) / h), 4)]})
    cands.sort(key=lambda c: -c["mass"])
    total = sum(c["mass"] for c in cands) or 1.0
    for c in cands:
        c["share"] = round(c.pop("mass") / total, 3)
    inside = s >= thr
    contrast = float(s[inside].mean() / (s[~inside].mean() + 1e-6)) if inside.any() and (~inside).any() else 1.0
    conf = float(np.clip((contrast - 1.5) / 4.0, 0, 1))
    if faces:  # people are the subject: union of faces, extended down to shoulders
        fx0 = min(f[0] for f in faces)
        fy0 = min(f[1] for f in faces)
        fx1 = max(f[2] for f in faces)
        fy1 = max(f[3] for f in faces)
        fh = fy1 - fy0
        box = [max(0, fx0 - 0.15 * (fx1 - fx0)), max(0, fy0 - 0.25 * fh),
               min(1, fx1 + 0.15 * (fx1 - fx0)), min(1, fy1 + 0.6 * fh)]
        return {"box": [round(v, 4) for v in box], "source": "faces", "confidence": 0.9,
                "faces": [[round(v, 4) for v in f] for f in faces],
                "centroid": [round((fx0 + fx1) / 2, 4), round((fy0 + fy1) / 2, 4)],
                "candidates": cands[:3], "cues": cues}
    if not cands:
        return {"box": [0.25, 0.25, 0.75, 0.75], "source": "none (fallback centre)", "confidence": 0.0,
                "faces": [], "candidates": [], "cues": cues}
    main = cands[0]
    box = list(main["box"])
    peak = np.unravel_index(int(np.argmax(s)), s.shape)
    focal = [round(peak[1] / w, 4), round(peak[0] / h, 4)]
    n_edges = sum(v < 0.02 for v in (box[0], box[1], 1 - box[2], 1 - box[3]))
    if ((box[2] - box[0]) > 0.85 and (box[3] - box[1]) < 0.7) or n_edges >= 3:
        # scene-wide "subject" (landscape band, pattern): use the compact peak region instead
        tight = s >= max(np.percentile(s, 97), thr)
        for pts in _components(tight):
            if any((y == peak[0] and x == peak[1]) for y, x in pts[:: max(1, len(pts) // 4000)]) or                     np.any((pts[:, 0] == peak[0]) & (pts[:, 1] == peak[1])):
                ys, xs = pts[:, 0], pts[:, 1]
                box = [xs.min() / w, ys.min() / h, (xs.max() + 1) / w, (ys.max() + 1) / h]
                main = {"centroid": [round(float(xs.mean() / w), 4), round(float(ys.mean() / h), 4)]}
                conf = conf * 0.6
                break
    for c in cands[1:]:  # merge nearby strong pieces of the same subject
        if c["share"] > 0.25 and _gap(box, c["box"]) < 0.05:
            box = [min(box[0], c["box"][0]), min(box[1], c["box"][1]),
                   max(box[2], c["box"][2]), max(box[3], c["box"][3])]
    return {"box": [round(float(v), 4) for v in box], "source": "saliency", "confidence": round(conf, 2),
            "centroid": main["centroid"], "focal_point": focal, "faces": [], "candidates": cands[:3], "cues": cues}


def _gap(a, b):
    dx = max(0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def horizon(rgb):
    """Row (0..1) of the strongest long, near-horizontal edge, or None."""
    g = C.luma(_small(rgb, 600))
    ey = np.abs(g[2:, :] - g[:-2, :])
    prof = ey.mean(axis=1)
    cover = (ey > np.percentile(ey, 90)).mean(axis=1)
    i = int(np.argmax(prof * cover))
    strength = float(prof[i] / (np.median(prof) + 1e-6))
    if strength < 4 or cover[i] < 0.5:
        return None
    return round((i + 1) / g.shape[0], 3)


def composition(rgb, subj):
    x0, y0, x1, y1 = subj["box"]
    cx, cy = subj.get("centroid") or [(x0 + x1) / 2, (y0 + y1) / 2]
    area = (x1 - x0) * (y1 - y0)
    d = [(math.hypot(cx - px, cy - py), (px, py)) for px, py in POWER_POINTS]
    dist, pp = min(d)
    centred = abs(cx - 0.5) < 0.06 and abs(cy - 0.5) < 0.08
    placement = "centred" if centred else "on a thirds point" if dist < 0.07 else \
        "on a thirds line" if min(abs(cx - 1 / 3), abs(cx - 2 / 3), abs(cy - 1 / 3), abs(cy - 2 / 3)) < 0.04 else "off-grid"
    edges = [n for n, v in (("left", x0), ("top", y0), ("right", 1 - x1), ("bottom", 1 - y1)) if v < 0.02]
    notes = []
    if edges:
        notes.append(f"Subject touches the {', '.join(edges)} edge(s): it may look cut off or cramped.")
    if area < 0.04:
        notes.append(f"Subject is small ({area * 100:.1f}% of frame); a tighter crop would strengthen it if resolution allows.")
    elif area > 0.6:
        notes.append(f"Subject fills {area * 100:.0f}% of the frame: little room to crop.")
    if placement == "off-grid":
        notes.append(f"Subject sits off the grid; nearest thirds point {tuple(round(v, 2) for v in pp)} is {dist:.2f} away.")
    hz = horizon(rgb)
    if hz is not None and 0.45 <= hz <= 0.55:
        notes.append(f"Horizon at {hz:.2f} splits the frame in half; consider placing it on a third (0.33 sky-light / 0.67 sky-heavy).")
    if subj.get("faces"):
        top = min(f[1] for f in subj["faces"])
        headroom = top
        if headroom < 0.04:
            notes.append("Faces are jammed against the top edge; add headroom if possible.")
        elif headroom > 0.35:
            notes.append(f"Lots of headroom above faces ({headroom:.2f}); eyes usually sit near the upper third.")
    return {
        "subject_centre": [round(cx, 3), round(cy, 3)],
        "subject_area_pct": round(area * 100, 1),
        "placement": placement,
        "nearest_power_point": [round(pp[0], 3), round(pp[1], 3)],
        "distance_to_power_point": round(dist, 3),
        "touching_edges": edges,
        "horizon_y": hz,
        "notes": notes,
    }


def draw_overlay(rgb, subj, comp, path, crops=None):
    """Preview with thirds grid, subject box/centre, faces, horizon and proposed crops."""
    small = _small(rgb, 1400)
    im = Image.fromarray(C.to_uint8(small, dither=False)).convert("RGB")
    w, h = im.size
    d = ImageDraw.Draw(im, "RGBA")
    for t in (1 / 3, 2 / 3):
        d.line([(t * w, 0), (t * w, h)], fill=(255, 255, 255, 110), width=1)
        d.line([(0, t * h), (w, t * h)], fill=(255, 255, 255, 110), width=1)
    bx = subj["box"]
    d.rectangle([bx[0] * w, bx[1] * h, bx[2] * w, bx[3] * h], outline=(255, 60, 60, 255), width=3)
    for f in subj.get("faces", []):
        d.rectangle([f[0] * w, f[1] * h, f[2] * w, f[3] * h], outline=(255, 210, 0, 255), width=2)
    cx, cy = comp["subject_centre"]
    d.ellipse([cx * w - 7, cy * h - 7, cx * w + 7, cy * h + 7], outline=(255, 60, 60, 255), width=3)
    for c in subj.get("candidates", [])[1:]:
        b = c["box"]
        d.rectangle([b[0] * w, b[1] * h, b[2] * w, b[3] * h], outline=(80, 170, 255, 200), width=2)
    if comp.get("horizon_y") is not None:
        y = comp["horizon_y"] * h
        d.line([(0, y), (w, y)], fill=(0, 230, 120, 200), width=2)
    for name, box in (crops or {}).items():
        d.rectangle([box[0] * w, box[1] * h, box[2] * w, box[3] * h], outline=(200, 120, 255, 230), width=2)
        d.text((box[0] * w + 6, box[1] * h + 4), name, fill=(200, 120, 255, 255))
    im.save(path)
    return path
