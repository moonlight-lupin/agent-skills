"""Shared image math for the photo-edit scripts.

Everything works on float32 arrays in [0, 1], sRGB (D65). Colour-managed
inputs (Display P3, Adobe RGB, CMYK with a profile) are converted to sRGB on
load so that every number the scripts report means the same thing.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

try:
    from PIL import ImageCms
except Exception:  # pragma: no cover - Pillow built without littlecms
    ImageCms = None

try:  # optional: iPhone HEIC/HEIF
    import pillow_heif  # type: ignore

    pillow_heif.register_heif_opener()
except Exception:
    pass

F32 = np.float32
_M_RGB2XYZ = np.array(
    [[0.4124564, 0.3575761, 0.1804375],
     [0.2126729, 0.7151522, 0.0721750],
     [0.0193339, 0.1191920, 0.9503041]], dtype=F32)
_M_XYZ2RGB = np.linalg.inv(_M_RGB2XYZ).astype(F32)
_WHITE = np.array([0.95047, 1.0, 1.08883], dtype=F32)
_EPS = (6 / 29) ** 3


# ---------------------------------------------------------------- load / save

def srgb_icc_bytes():
    if ImageCms is None:
        return None
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def load(path):
    """Return (rgb float32 HxWx3 sRGB, alpha float32 HxW or None, info dict)."""
    src = Image.open(path)
    info = {"path": str(path), "format": src.format, "mode": src.mode,
            "icc": None, "converted_to_srgb": False}
    icc = src.info.get("icc_profile")
    im = ImageOps.exif_transpose(src)  # bake EXIF orientation into pixels
    info["exif"] = im.getexif()

    alpha = None
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        alpha = np.asarray(im.getchannel("A"), dtype=F32) / 255.0
        im = im.convert("RGB")
    elif im.mode in ("I;16", "I;16B", "I;16L", "I"):
        a = np.asarray(im, dtype=np.float64)
        a = a / (65535.0 if a.max() > 255 else 255.0)
        im = Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8), "L")

    if icc and ImageCms is not None:
        try:
            prof = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            name = (ImageCms.getProfileDescription(prof) or "").strip()
            info["icc"] = name
            if "srgb" not in name.lower() or im.mode == "CMYK":
                if im.mode not in ("RGB", "CMYK", "L"):
                    im = im.convert("RGB")
                im = ImageCms.profileToProfile(
                    im, prof, ImageCms.createProfile("sRGB"),
                    renderingIntent=0, outputMode="RGB")
                info["converted_to_srgb"] = True
        except Exception as exc:  # broken profile: fall back to assuming sRGB
            info["icc_error"] = str(exc)
    if im.mode != "RGB":
        im = im.convert("RGB")
    rgb = np.asarray(im, dtype=F32) / 255.0
    return rgb, alpha, info


def to_uint8(rgb, dither=True):
    a = np.clip(rgb, 0.0, 1.0) * 255.0
    if dither:  # triangular dither (+-1 LSB) prevents banding in skies/gradients
        rng = np.random.default_rng(0)
        a = a + (rng.random(a.shape, dtype=F32) - rng.random(a.shape, dtype=F32))
    return np.clip(a + 0.5, 0, 255).astype(np.uint8)


def save(rgb, alpha, path, exif=None, quality=90, metadata="keep"):
    """Save with an embedded sRGB profile. Returns list of warnings."""
    path = Path(path)
    warnings = []
    fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP",
           ".tif": "TIFF", ".tiff": "TIFF"}.get(path.suffix.lower())
    if fmt is None:
        raise SystemExit(f"Unsupported output extension: {path.suffix} (use .jpg .png .webp .tif)")
    arr = to_uint8(rgb)
    if alpha is not None and fmt == "JPEG":
        warnings.append("JPEG has no transparency; flattened onto white. Use .png/.webp to keep alpha.")
        a = alpha[..., None]
        arr = to_uint8(rgb * a + (1 - a))
        alpha = None
    im = Image.fromarray(arr, "RGB")
    if alpha is not None:
        im.putalpha(Image.fromarray((np.clip(alpha, 0, 1) * 255 + 0.5).astype(np.uint8), "L"))

    kw = {}
    icc = srgb_icc_bytes()
    if icc:
        kw["icc_profile"] = icc
    if exif is not None and metadata != "strip" and fmt in ("JPEG", "WEBP", "PNG", "TIFF"):
        exif[0x0112] = 1  # orientation already baked into pixels
        if metadata == "no-gps" and 0x8825 in exif:
            del exif[0x8825]
        try:
            kw["exif"] = exif.tobytes()
        except Exception:
            warnings.append("Could not re-encode EXIF; metadata dropped.")
    if fmt == "JPEG":
        kw.update(quality=int(quality), optimize=True, progressive=True,
                  subsampling=0 if quality >= 90 else 2)
    elif fmt == "WEBP":
        kw.update(quality=int(quality), method=6)
    elif fmt == "PNG":
        kw.update(optimize=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, fmt, **kw)
    return warnings


# ---------------------------------------------------------------- colour math

def srgb_to_linear(c):
    c = c.astype(F32, copy=False)
    return np.where(c <= 0.04045, c / 12.92, np.power((c + 0.055) / 1.055, 2.4)).astype(F32)


def linear_to_srgb(c):
    c = np.clip(c, 0.0, None).astype(F32, copy=False)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055).astype(F32)


def linear_to_lab(rgb):
    xyz = (rgb @ _M_RGB2XYZ.T) / _WHITE
    f = np.where(xyz > _EPS, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29).astype(F32)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1).astype(F32)


def lab_to_linear(lab):
    fy = (lab[..., 0] + 16) / 116
    fx = fy + lab[..., 1] / 500
    fz = fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], axis=-1)
    xyz = np.where(f > 6 / 29, f ** 3, 3 * (6 / 29) ** 2 * (f - 4 / 29)) * _WHITE
    return (xyz @ _M_XYZ2RGB.T).astype(F32)


def srgb_to_lab(rgb):
    return linear_to_lab(srgb_to_linear(rgb))


def luma(rgb):
    """Rec.709 luma of gamma-encoded RGB (fast perceptual-ish brightness)."""
    return (rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722).astype(F32)


# ---------------------------------------------------------------- filters

def _shift_sum(a, kernel, axis):
    r = len(kernel) // 2
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r, r)
    p = np.pad(a, pad, mode="edge")
    out = np.zeros_like(a, dtype=F32)
    n = a.shape[axis]
    for i, k in enumerate(kernel):
        sl = [slice(None)] * a.ndim
        sl[axis] = slice(i, i + n)
        out += k * p[tuple(sl)]
    return out


def _box(a, r, axis):
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
    n = 2 * r + 1
    hi = [slice(None)] * a.ndim
    lo = [slice(None)] * a.ndim
    hi[axis] = slice(n, None)
    lo[axis] = slice(0, -n)
    return ((c[tuple(hi)] - c[tuple(lo)]) / n).astype(F32)


def gaussian(a, sigma):
    """Gaussian blur over the first two axes (exact kernel when small, 3x box when large)."""
    if sigma <= 0.05:
        return a.astype(F32, copy=True)
    if sigma <= 3.0:
        r = max(1, int(math.ceil(3 * sigma)))
        x = np.arange(-r, r + 1, dtype=F32)
        k = np.exp(-(x * x) / (2 * sigma * sigma))
        k /= k.sum()
        return _shift_sum(_shift_sum(a.astype(F32), k, 0), k, 1)
    r = max(1, int((math.sqrt(12 * sigma * sigma / 3 + 1) - 1) / 2 + 0.5))
    out = a.astype(F32)
    for _ in range(3):
        out = _box(_box(out, r, 0), r, 1)
    return out


def resize_float(rgb, w, h):
    """High-quality Lanczos resize of a float image, done in linear light."""
    lin = srgb_to_linear(rgb)
    chans = []
    for c in range(lin.shape[2]):
        im = Image.fromarray(np.ascontiguousarray(lin[..., c]), mode="F")
        chans.append(np.asarray(im.resize((w, h), Image.LANCZOS), dtype=F32))
    return linear_to_srgb(np.stack(chans, axis=-1))


def resize_channel(a, w, h):
    im = Image.fromarray(np.ascontiguousarray(a.astype(F32)), mode="F")
    return np.asarray(im.resize((w, h), Image.LANCZOS), dtype=F32)


def rotate_float(rgb, degrees):
    chans = []
    for c in range(rgb.shape[2]):
        im = Image.fromarray(np.ascontiguousarray(rgb[..., c]), mode="F")
        chans.append(np.asarray(im.rotate(degrees, resample=Image.BICUBIC, expand=False), dtype=F32))
    return np.stack(chans, axis=-1)


def working_copy(rgb, long_edge=1600):
    """Downscaled copy for measurement (fast, and stable across resolutions)."""
    h, w = rgb.shape[:2]
    s = long_edge / max(h, w)
    if s >= 1:
        return rgb
    return resize_float(rgb, max(1, round(w * s)), max(1, round(h * s)))


def pchip(xs, ys, x):
    """Monotone cubic (Fritsch-Carlson) interpolation; never overshoots."""
    xs = np.asarray(xs, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)
    h = np.diff(xs)
    d = np.diff(ys) / h
    m = np.zeros_like(ys)
    for i in range(1, len(xs) - 1):
        if d[i - 1] * d[i] <= 0:
            m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    m[0], m[-1] = d[0], d[-1]
    x = np.asarray(x, dtype=np.float64)
    i = np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2)
    t = (x - xs[i]) / h[i]
    h00 = (2 * t ** 3 - 3 * t ** 2 + 1)
    h10 = (t ** 3 - 2 * t ** 2 + t)
    h01 = (-2 * t ** 3 + 3 * t ** 2)
    h11 = (t ** 3 - t ** 2)
    return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]
