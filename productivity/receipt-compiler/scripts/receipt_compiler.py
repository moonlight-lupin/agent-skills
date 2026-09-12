#!/usr/bin/env python3
"""receipt_compiler — phone-camera receipts → straightened B&W scans → A4 expense-claim PDF.

Subcommands:
  scan    INPUT_DIR -o workdir     process photos, OCR, write manifest.json
  review  workdir                  print the expense table for user confirmation
  confirm workdir                  stamp user approval + bind reviewed data (digest)
  pack    workdir -o out.pdf       build A4 PDF from a CONFIRMED manifest

The confirmation gate is enforced in code: `pack` refuses to run unless the
manifest carries "confirmed": true (set by the confirm subcommand).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pytesseract
    from pytesseract import Output
except ImportError:
    pytesseract = None

from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIF_OK = True
except ImportError:
    HEIF_OK = False

IMG_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".bmp", ".tif", ".tiff"}
MANIFEST_VERSION = 1

AMOUNT_RE = re.compile(
    # currency code/symbol glued to the number (RM12.50, S$1,234.56, $12.50),
    # or a standalone number with word boundaries (no preceding word char).
    # (?<![A-Za-z]): TERM 30 / CONFIRM 1 must not read as "RM 30";
    # (?<=\d): trailing "." / "," must not be swallowed (RM12.50.)
    r"(?<![A-Za-z])(?:S?\$|SGD|RM|USD|EUR|GBP)\s?\d[\d.,]*(?<=\d)"
    r"|\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?"
    r"|\b\d{1,6}(?:[.,]\d{1,2})(?!\d)"
    r"|\b\d{1,6}(?![.,\d])",
    re.IGNORECASE
)
DATE_RES = [
    re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b"),
    re.compile(r"\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b"),
    re.compile(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*(\d{2,4})\b", re.IGNORECASE),
]
NOISE_WORDS = {"receipt", "invoice", "tax", "gst", "subtotal", "total", "cash", "change",
               "thank", "you", "please", "come", "again", "visa", "master", "net"}


# --------------------------------------------------------------------------- io
def load_image(path: Path) -> np.ndarray | None:
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)  # always; not HEIF-conditional
            im = im.convert("RGB")
            # cap input size; phone cameras are 12MP+, we only need ~2000px
            im.thumbnail((2200, 2200), Image.LANCZOS)
            return np.ascontiguousarray(np.asarray(im)[:, :, ::-1])  # RGB->BGR for cv2
    except Exception as exc:
        print(f"WARN cannot read {path.name}: {exc}", file=sys.stderr)
        return None


# -------------------------------------------------------------------- geometry
def _order_quad(pts: np.ndarray) -> np.ndarray:
    """Order 4 points: TL, TR, BR, BL."""
    pts = pts.reshape(4, 2).astype(np.float32)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)],
                     pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def find_receipt_quad(gray: np.ndarray) -> np.ndarray | None:
    """Largest plausible quadrilateral contour, or None."""
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape
    img_area = h * w
    best = None
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
        area = cv2.contourArea(c)
        if area < 0.20 * img_area:
            break
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4 and cv2.isContourConvex(approx):
            best = approx
            break
        if best is None and area > 0.35 * img_area:
            rect = cv2.minAreaRect(c)
            best = cv2.boxPoints(rect).astype(np.int32).reshape(4, 1, 2)
    if best is None:
        return None
    quad = _order_quad(best)
    # reject degenerate quads (thin slivers)
    if cv2.contourArea(quad) < 0.15 * img_area:
        return None
    return quad


def warp_receipt(bgr: np.ndarray, quad: np.ndarray) -> np.ndarray:
    tl, tr, br, bl = quad
    wA = np.linalg.norm(br - bl)
    wB = np.linalg.norm(tr - tl)
    hA = np.linalg.norm(tr - br)
    hB = np.linalg.norm(tl - bl)
    out_w = int(max(wA, wB))
    out_h = int(max(hA, hB))
    M = cv2.getPerspectiveTransform(
        quad.astype(np.float32),
        np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]],
                 dtype=np.float32))
    out = cv2.warpPerspective(bgr, M, (out_w, out_h))
    # quad-corner ordering is only reliable for |rotation| < 45deg; beyond that
    # the warp comes out rotated 90deg. Detect by text-ink orientation, not
    # aspect: text lines create more ink variance between ROWS (line gaps) than
    # between COLUMNS. Rotate only when the ink says the text is vertical.
    if _text_is_vertical(out):
        out = cv2.rotate(out, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return out


def _text_is_vertical(gray: np.ndarray) -> bool:
    """True if the image's ink rows look like vertical text lines."""
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    if min(gray.shape) < 20:
        return False
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = bw.astype(np.float64) / 255.0
    row_var = np.var(ink.mean(axis=1))  # variance across horizontal text lines
    col_var = np.var(ink.mean(axis=0))  # if text is vertical, columns vary more
    return col_var > row_var * 1.3


def deskew(gray: np.ndarray) -> np.ndarray:
    """Small-angle deskew for full-frame fallback scans."""
    # binarize first: desk/background pixels dominate on dark desks otherwise
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = np.column_stack(np.nonzero(bw))
    if len(coords) < 100 or len(coords) > 0.9 * bw.size:
        return gray  # too little or too much foreground: geometry unreliable
    angle = cv2.minAreaRect(coords[:, ::-1].astype(np.float32))[-1]
    # normalize to [-45, 45]: minAreaRect returns [-90, 0); a portrait
    # foreground reads near -90 but the *page* itself is near-axis-aligned
    if angle <= -45:
        angle += 90
    elif angle > 45:
        angle -= 90
    if abs(angle) < 0.4 or abs(angle) > 15:
        return gray
    h, w = gray.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


# -------------------------------------------------------------------- scanify
def scanify(gray: np.ndarray, mode: str) -> tuple[np.ndarray, np.ndarray]:
    """Returns (display, ocr_input).

    display = photo: grayscale+stretch; bw: photocopy-style threshold.
    ocr_input = the stretched grayscale for BOTH modes: tesseract binarizes
    internally, and thresholding first can erase faint thermal print — so the
    extracted amounts must not depend on the user's look choice.
    """
    lo, hi = np.percentile(gray, (2, 98))
    if hi > lo:
        gray = np.clip((gray - lo) * 255.0 / (hi - lo), 0, 255).astype(np.uint8)
    ocr_in = gray
    if mode == "photo":
        return gray, ocr_in
    thr = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                cv2.THRESH_BINARY, 31, 15)
    return thr, ocr_in


# ------------------------------------------------------------------------ ocr
def _extract_date(text: str):
    m = DATE_RES[2].search(text)
    if m:
        months = {n: i + 1 for i, n in enumerate(
            ["jan", "feb", "mar", "apr", "may", "jun",
             "jul", "aug", "sep", "oct", "nov", "dec"])}
        mon = months.get(m.group(2).lower()[:3])
        if mon is not None:
            day, yr = int(m.group(1)), m.group(3)
            yr = int(yr) + (2000 if int(yr) < 100 else 0)
            try:
                return date(yr, mon, day).isoformat()
            except ValueError:
                pass
    m = DATE_RES[0].search(text)
    if m:
        d_, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if mo <= 12:
            y = int(y) + (2000 if int(y) < 100 else 0)
            try:
                return date(y, mo, d_).isoformat()
            except ValueError:
                pass
    m = DATE_RES[1].search(text)
    if m:
        y, mo, d_ = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return date(y, mo, d_).isoformat()
        except ValueError:
            pass
    return None


def _to_float(amt: str):
    """Normalize an OCR amount token to float, or None.

    Handles currency prefixes (case-insensitive), thousands separators
    (1,234.56 → 1234.56), and comma-decimal (12,30 → 12.30).
    """
    s = amt.upper().strip()
    s = re.sub(r"(SGD|USD|EUR|GBP|RM|S\$|\$)", "", s).strip()
    s = s.replace(" ", "")
    # reject 3-decimal fractions (per-litre prices: 1.899) — they'd read as a
    # thousands group and inflate 1000x; KWD/BHD/OMR 3-decimal currencies are
    # out of scope for SGD/MYR claims
    if re.search(r"[.,]\d{3}$", s) and len(s) <= 5:
        return None
    if not re.fullmatch(r"\d{1,7}([.,]\d{3})*([.,]\d{1,2})?", s):
        return None
    # decide separators: rightmost group of 2 digits = decimal, groups of 3 = thousands
    if re.search(r"[.,]\d{1,2}$", s):
        dec_sep = "." if s.rfind(".") > s.rfind(",") else ","
        head, _, tail = s.rpartition(dec_sep)
        head = re.sub(r"[.,]", "", head)
        s = f"{head}.{tail}"
    else:
        s = re.sub(r"[.,]", "", s)
    try:
        return float(s)
    except ValueError:
        return None


def _parse_ocr(lines: list[str]) -> dict:
    text = "\n".join(lines)
    amounts = []
    total_amount = None
    for i, ln in enumerate(lines):
        for amt in AMOUNT_RE.findall(ln):
            val = _to_float(amt)
            if val is None:
                continue
            # bare integers (no decimal part) on non-total lines are usually
            # years/quantities/phone fragments — only trust them in total context
            if (re.fullmatch(r"\d{1,6}", amt.strip())
                    and not _TOTAL_KW.search(ln.lower())):
                continue
            amounts.append((val, ln.lower(), i))
    total_amount = _pick_total(lines, amounts)
    d = _extract_date(text)
    merchant = None
    for ln in lines[:8]:
        words = re.findall(r"[A-Za-z]{3,}", ln)
        kept = [w for w in words if w.lower() not in NOISE_WORDS]
        if kept:
            # filter noise tokens out but keep the rest of the line
            cleaned = re.sub(r"\b(Tax|Invoice|Receipt|Bill|Statement|Official)\b",
                             "", ln, flags=re.IGNORECASE).strip()
            merchant = (cleaned or " ".join(kept))[:40]
            break
    return {"date": d, "merchant": merchant, "amount": total_amount}


_TOTAL_KW = re.compile(r"grand total|total amount|\btotal\b|\bamount due\b"
                       r"|\bbalance due\b|\bbalance\b")
_SUB_KW = re.compile(r"sub[- ]?total")
_TENDER_KW = re.compile(r"tender|\bchange\b|\bcash\b|\bpaid\b|visa|master"
                        r"|\bnets\b|paynow|paylah|debit|credit card")
_QTY_KW = re.compile(r"\bqty\b|\bquantity\b|\bitems?\b|\bno\.?\s*of\b|\bunits?\b")


def _pick_total(lines: list[str], amounts: list[tuple]) -> float | None:
    """Choose the receipt total from OCR amount candidates.

    Priority: (1) keyword-total lines excluding tender/change/subtotal/qty
    lines; (2) the amount on the line right after a lone 'TOTAL' keyword line
    (same exclusions, plus a qty check on the total line itself); (3)
    non-tender amounts; (4) anything.
    """
    totals = [a for a in amounts
              if _TOTAL_KW.search(a[1]) and not _SUB_KW.search(a[1])
              and not _TENDER_KW.search(a[1]) and not _QTY_KW.search(a[1])]
    if not totals:
        for i, ln in enumerate(lines):
            low = ln.lower()
            if (_TOTAL_KW.search(low) and not _SUB_KW.search(low)
                    and not _QTY_KW.search(low)):
                nxt = lines[i + 1].lower() if i + 1 < len(lines) else ""
                if _TENDER_KW.search(nxt) or _SUB_KW.search(nxt):
                    continue  # next line is a payment/subtotal row, not the total
                for amt in AMOUNT_RE.findall(nxt):
                    val = _to_float(amt)
                    if val is not None:
                        totals.append((val, nxt, i + 1))
    if totals:
        return max(totals, key=lambda a: a[0])[0]
    if not amounts:
        return None
    non_tender = [a for a in amounts if not _TENDER_KW.search(a[1])]
    pool = non_tender or amounts
    return max(pool, key=lambda a: a[0])[0]


def ocr_lines(gray: np.ndarray) -> tuple[list[str], float]:
    if pytesseract is None:
        return [], 0.0
    data = pytesseract.image_to_data(gray, output_type=Output.DICT)
    groups: dict[tuple, list] = {}
    confs = []
    n_low = 0  # dropped low-confidence words count toward the average
    for i in range(len(data["text"])):
        txt = data["text"][i].strip()
        conf = float(data["conf"][i])
        if not txt:
            continue
        if conf < 40:
            n_low += 1
            continue
        confs.append(conf)
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        groups.setdefault(key, []).append((data["word_num"][i], txt))
    lines = []
    for key in sorted(groups):
        words = [w for _, w in sorted(groups[key])]
        lines.append(" ".join(words))
    denom = len(confs) + n_low
    avg_conf = sum(confs) / denom if denom else 0.0
    return lines, round(avg_conf, 1)


# ----------------------------------------------------------------- digest
def _review_digest(manifest: dict, workdir: Path | None = None) -> str:
    """Stable hash of what the user reviewed: reviewed fields PLUS the SHA256
    of each processed image's bytes, so an in-place image swap after confirm
    invalidates the digest."""
    import hashlib
    h = hashlib.sha256()
    payload = {
        "mode": manifest.get("mode"),
        "receipts": [
            {k: e.get(k) for k in
             ("n", "date", "merchant", "description", "amount", "currency",
              "include")}
            for e in manifest.get("receipts", [])
        ],
    }
    h.update(json.dumps(payload, sort_keys=True,
                        ensure_ascii=False).encode("utf-8"))
    if workdir is not None:
        # image bytes bind the digest to actual reviewed content; sorted by n so
        # the byte-stream order is stable regardless of list order. Note: the
        # JSON payload itself keeps list order, so reordering receipts still
        # forces re-confirmation (fail-closed, intentional).
        for e in sorted(manifest.get("receipts", []), key=lambda e: e.get("n", 0)):
            p = workdir / e.get("processed", "")
            try:
                h.update(p.read_bytes())
            except OSError:
                h.update(b"<missing>")
    return h.hexdigest()


# ----------------------------------------------------------------- sub: scan
def cmd_scan(args) -> int:
    if cv2 is None:
        print("ERROR opencv-python-headless is required: pip install opencv-python-headless")
        return 2
    # preflight OCR: silently-degraded scan (exit 0, blank table) is worse
    # than a hard failure
    if pytesseract is None:
        print("ERROR pytesseract is required: pip install pytesseract")
        return 2
    try:
        pytesseract.get_tesseract_version()
    except Exception:
        print("ERROR tesseract binary not found on PATH: install tesseract-ocr "
              "(e.g. apt install tesseract-ocr)")
        return 2
    src = Path(args.input_dir).expanduser()
    outdir = Path(args.out).expanduser()
    proc_dir = outdir / "processed"
    if not src.is_dir():
        print(f"ERROR input dir not found or not a directory: {src}")
        return 1
    files = sorted(p for p in src.iterdir()
                   if p.suffix.lower() in IMG_EXTS and p.is_file())
    if not files:
        print(f"ERROR no images found in {src}")
        return 1
    heif_needed = any(p.suffix.lower() in (".heic", ".heif") for p in files)
    if heif_needed and not HEIF_OK:
        print("ERROR pillow-heif is required for .heic/.heif photos: "
              "pip install pillow-heif (or ask the user for JPGs)")
        return 1
    proc_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    failures = []
    for path in files:
        bgr = load_image(path)
        if bgr is None:
            failures.append(str(path))
            continue
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        quad = find_receipt_quad(gray)
        if quad is not None:
            bgr = warp_receipt(bgr, quad)
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            method = "perspective_warp"
        else:
            gray = deskew(gray)
            method = "deskew"
        scan, ocr_in = scanify(gray, args.mode)
        idx = len(entries) + 1  # sequential n, no gaps from skipped files
        out_png = proc_dir.resolve() / f"{idx:02d}_{path.stem}.png"
        Image.fromarray(scan).save(out_png)
        try:
            lines, conf = ocr_lines(ocr_in)
        except Exception as exc:
            print(f"WARN OCR failed for {path.name}: {exc}", file=sys.stderr)
            lines, conf = [], 0.0
        ocr = _parse_ocr(lines)
        h, w = scan.shape
        entries.append({
            "n": idx, "source": str(path), "processed": str(out_png),
            "width": w, "height": h, "aspect": round(h / w, 3),
            "method": method, "ocr_confidence": conf,
            "ocr": ocr,
            # editable caption fields (agent/user fills; all optional)
            "date": ocr.get("date") or "",
            "merchant": ocr.get("merchant") or "",
            "description": "",
            "amount": ocr.get("amount"),
            "currency": "SGD",
            "include": True,
            "needs_review": conf < 55 or ocr.get("amount") is None,
        })

    if not entries:
        print(f"ERROR no images could be decoded from {src}; failures: {failures}")
        return 1

    manifest = {
        "version": MANIFEST_VERSION,
        "mode": args.mode,
        "created": date.today().isoformat(),
        "receipts": entries,
        "unreadable": failures,
        # confirmation gate — set true only after the user approves the table
        "confirmed": False,
        "confirmations": {},
    }
    mpath = outdir / "manifest.json"
    # NOTE: review_digest is stamped ONLY by the confirm subcommand, never at
    # scan time — otherwise hand-editing confirmed=true would pass the gate.
    mpath.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(json.dumps({"manifest": str(mpath), "receipts": len(entries),
                      "unreadable": [Path(f).name for f in failures],
                      "needs_review": [e["n"] for e in entries if e["needs_review"]]}))
    return 0


# --------------------------------------------------------------- sub: review
def cmd_review(args) -> int:
    mpath = Path(args.workdir).expanduser() / "manifest.json"
    m = json.loads(mpath.read_text())
    unreadable = m.get("unreadable") or []
    if unreadable:
        print(f"WARNING {len(unreadable)} photo(s) could not be read and are NOT "
              "in this claim: " + ", ".join(Path(f).name for f in unreadable))
        print("If those receipts should be claimed, fix/convert them and re-run scan.")
    print(f"{'#':>3}  {'date':<11} {'amount':>9}  merchant / description   (src)")
    tot_by_ccy = {}
    for e in m["receipts"]:
        if not e.get("include", True):
            print(f"{e['n']:>3}  -- excluded --   {Path(e['source']).name}")
            continue
        amt = e.get("amount")
        if amt is not None and (isinstance(amt, bool)
                                or not isinstance(amt, (int, float))):
            print(f"ERROR receipt #{e['n']} amount is not a number: {amt!r}. "
                  "Fix manifest.json (JSON number, no currency text), then re-run review.")
            return 1
        flag = " ?" if e.get("needs_review") else ""
        desc = e.get("description") or e.get("merchant") or ""
        print(f"{e['n']:>3}  {e.get('date') or '-':<11} "
              f"{(e.get('currency', '') + ' ' + ('%.2f' % amt)) if amt is not None else '-':>9}"
              f"  {desc[:44]}{flag}   ({Path(e['source']).name})")
        if isinstance(amt, (int, float)):
            ccy = e.get("currency", "SGD")
            tot_by_ccy[ccy] = tot_by_ccy.get(ccy, 0.0) + amt
    if len(tot_by_ccy) == 1:
        ccy, tot = next(iter(tot_by_ccy.items()))
        print(f"\nTotal: {ccy} {tot:.2f}")
    elif tot_by_ccy:
        print("\nTotals (mixed currencies — no combined total):")
        for ccy in sorted(tot_by_ccy):
            print(f"  {ccy}: {tot_by_ccy[ccy]:.2f}")
    print(f"confirmed={m.get('confirmed')}")
    return 0


# --------------------------------------------------------------- sub: confirm
def _validate_amounts(m: dict) -> str | None:
    """Return an error message if any non-excluded receipt has a non-numeric
    amount, else None. bool is an int subclass — reject it explicitly."""
    for e in m["receipts"]:
        if not e.get("include", True):
            continue
        amt = e.get("amount")
        if amt is not None and (isinstance(amt, bool)
                                or not isinstance(amt, (int, float))):
            return (f"receipt #{e.get('n', '?')} amount is not a number: {amt!r}. "
                    "Fix manifest.json (JSON number, no currency text), then "
                    "re-run review before confirming.")
    return None


def cmd_confirm(args) -> int:
    """Stamp user approval: sets confirmed=true and binds review_digest to the
    manifest's CURRENT reviewed fields. Any later edit breaks the digest."""
    mpath = Path(args.workdir).expanduser() / "manifest.json"
    m = json.loads(mpath.read_text())
    err = _validate_amounts(m)
    if err:
        print(f"ERROR {err}")
        return 1
    m.pop("review_digest", None)
    m["confirmed"] = True
    m["review_digest"] = _review_digest(m, Path(args.workdir).expanduser())
    mpath.write_text(json.dumps(m, indent=2, ensure_ascii=False))
    n_inc = sum(1 for e in m["receipts"] if e.get("include", True))
    print(json.dumps({"confirmed": True, "receipts": n_inc,
                      "review_digest": m["review_digest"]}))
    return 0


# ------------------------------------------------------------------ sub: pack
def cmd_pack(args) -> int:
    workdir = Path(args.workdir).expanduser()
    m = json.loads((workdir / "manifest.json").read_text())
    if m.get("version") != MANIFEST_VERSION:
        print(f"ERROR manifest version {m.get('version')!r} not supported "
              f"(expected {MANIFEST_VERSION}) — re-run scan.")
        return 1
    if m.get("confirmed") is not True:
        print("ERROR manifest not confirmed. Run review, get user approval, then "
              "the confirm subcommand.")
        return 1
    if "review_digest" not in m:
        print("ERROR manifest has no review_digest — confirmation must be stamped "
              "by the confirm subcommand, not hand-edited.")
        return 1
    if _review_digest(m, workdir) != m["review_digest"]:
        print("ERROR manifest or processed images changed after confirmation "
              "(review_digest mismatch). Re-review the table, get fresh "
              "approval, then pack.")
        return 1
    err = _validate_amounts(m)
    if err:
        print(f"ERROR {err}")
        return 1
    missing = [e.get("processed", "") for e in m["receipts"]
               if e.get("include", True) and not (workdir / e.get("processed", "")).is_file()]
    if missing:
        print(f"ERROR processed images missing (re-run scan, then review + "
              f"confirm again): {missing}")
        return 1
    # required entry keys — hand-edited manifests must fail cleanly, not KeyError
    required = ("n", "aspect", "processed", "source")
    for e in m["receipts"]:
        if e.get("include", True):
            for k in required:
                if k not in e:
                    print(f"ERROR manifest entry missing required key {k!r} "
                          f"(re-run scan): {e}")
                    return 1
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    receipts = [e for e in m["receipts"] if e.get("include", True)]
    if not receipts:
        print("ERROR no receipts marked include=true")
        return 1
    seen_n = set()
    for e in receipts:
        if e["n"] in seen_n:
            print(f"ERROR duplicate receipt number #{e['n']} in manifest — "
                  "renumber and re-run confirm.")
            return 1
        seen_n.add(e["n"])

    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    PW, PH = A4
    MARGIN = 15 * mm
    FOOTER = 10 * mm
    content_w = PW - 2 * MARGIN
    content_h = PH - MARGIN - FOOTER
    gap = 5 * mm

    c = canvas.Canvas(str(out), pagesize=A4)
    c.setTitle(args.title or "Expense receipts")

    # ---- Unicode-capable font: built-in Helvetica is WinAnsi-only, so CJK/etc
    # text needs a TTF (some reportlab builds substitute .notdef boxes silently
    # instead of raising — both outcomes are unacceptable for claim text).
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    def _find_ttf() -> str | None:
        cands = [
            # CJK-capable faces first (SGD/MYR claims can carry Chinese merchant
            # names); DejaVu has Latin/Cyrillic only
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"]
        try:
            from PIL import ImageFont as _IF
            for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
                p = _IF.truetype(name, 10).path
                if p and Path(p).is_file():
                    cands.append(p)
        except Exception:
            pass
        return next((p for p in cands if Path(p).is_file()), None)

    _uni_path = _find_ttf()
    uni_font = None
    uni_bold = None
    if _uni_path:
        try:
            pdfmetrics.registerFont(TTFont("ReceiptUni", _uni_path))
            uni_font = "ReceiptUni"
            bold_path = (_uni_path.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
                         if _uni_path.endswith("DejaVuSans.ttf") else _uni_path)
            if bold_path != _uni_path and Path(bold_path).is_file():
                pdfmetrics.registerFont(TTFont("ReceiptUni-Bold", bold_path))
                uni_bold = "ReceiptUni-Bold"
        except Exception:
            uni_font = None

    def _txt(s, bold=False):
        """(fontname, text) — route through the Unicode font when needed."""
        s = "" if s is None else str(s)
        if s.isascii():
            return ("Helvetica-Bold" if bold else "Helvetica"), s
        if uni_font:
            f = (uni_bold or uni_font) if bold else uni_font
            return f, s
        # no Unicode font available: sanitize non-WinAnsi chars with a warning
        cleaned = s.encode("latin-1", "replace").decode("latin-1")
        print(f"WARN non-Latin text unavailable (no TTF found): {s!r} -> {cleaned!r}",
              file=sys.stderr)
        return ("Helvetica-Bold" if bold else "Helvetica"), cleaned

    # ---- layout: compute receipt pages FIRST so page numbers are known
    TALL_RATIO = 2.2
    normals = [e for e in receipts if e["aspect"] < TALL_RATIO]
    talls = [e for e in receipts if e["aspect"] >= TALL_RATIO]

    def cell_for(e, cell_w, cell_h):
        """Largest box preserving aspect that fits cell."""
        a = e["aspect"]
        w_ = cell_w
        h_ = w_ * a
        if h_ > cell_h:
            h_ = cell_h
            w_ = h_ / a
        return w_, h_

    BADGE_H = 5 * mm
    ann_h = (12 * mm if args.number else 0) + (8 * mm if args.captions else 0)

    # pack rows: talls go 3-per-row (they are narrow), normals 2-per-row
    rows = []
    i = 0
    while i < len(talls):
        rows.append(talls[i:i + 3])
        i += 3
    i = 0
    while i < len(normals):
        rows.append(normals[i:i + 2])
        i += 2

    # assign rows to pages; row_h covers image + reserved annotation strip
    pages = []
    cur, cur_h = [], 0.0
    for row in rows:
        tall = row[0]["aspect"] >= TALL_RATIO
        img_h = (content_h - ann_h) if tall else min(
            max(cell_for(e, (content_w - gap) / 2, content_h)[1] for e in row),
            content_h * 0.52)
        row_h = img_h + ann_h
        if cur_h + row_h + gap > content_h and cur:
            pages.append(cur)
            cur, cur_h = [], 0.0
        cur.append((row, img_h, row_h, tall))
        cur_h += row_h + gap  # trailing gap tolerated (fits inside footer margin)
    if cur:
        pages.append(cur)

    # ---- cover plan: ONE break computation shared by count + render
    cover_plan = []  # list of (page_rows, has_title)
    if args.cover:
        ROW_H = 5.5 * mm
        # totals block height: one bold line per currency + clearance
        tot_by_ccy = {}
        for e in receipts:
            amt = e.get("amount")
            if isinstance(amt, (int, float)):
                ccy = e.get("currency", "SGD")
                tot_by_ccy[ccy] = tot_by_ccy.get(ccy, 0.0) + amt
        totals_h = (6 * mm * max(1, len(tot_by_ccy))) + 6 * mm
        # title block: heading + meta rows + gap (first page only).
        # CONSUME_* must mirror cover_table_header() exactly:
        #  with title: 10mm title + n_meta*7mm meta + 6mm gap + 6mm header row
        #  plain page: 6mm header row + 6mm return
        n_meta = 1 + (1 if args.claimant else 0) + (1 if args.period else 0) \
            + (1 if args.notes else 0)  # Receipts count always shown
        CONSUME_TITLE = 10 * mm + n_meta * 7 * mm + 12 * mm
        CONSUME_PLAIN = 12 * mm

        # capacity = rows that fit between the header and (MARGIN + totals)
        first_capacity = (PH - 40 * mm) - CONSUME_TITLE - MARGIN - totals_h
        plain_capacity = (PH - MARGIN) - CONSUME_PLAIN - MARGIN - totals_h

        cur_rows, room, has_title = [], first_capacity, True
        for e in receipts:
            if room < ROW_H:
                cover_plan.append((cur_rows, has_title))
                cur_rows, room, has_title = [], plain_capacity, False
            cur_rows.append(e)
            room -= ROW_H
        if cur_rows or not cover_plan:
            cover_plan.append((cur_rows, has_title))
        cover_pages = len(cover_plan)
    else:
        cover_pages = 0

    total_pages = len(pages) + cover_pages

    def page_footer(pn):
        c.setFont("Helvetica", 8)
        c.setFillGray(0.35)
        c.drawCentredString(PW / 2, FOOTER / 2, f"Page {pn} of {total_pages}")
        c.setFillGray(0)

    # ---- optional cover page(s): paginated expense index
    if args.cover:
        def cover_table_header(y, with_title):
            if with_title:
                f, t = _txt(args.title or "Expense Claim", bold=True)
                c.setFont(f, 20)
                c.drawString(MARGIN, y, t)
                y -= 10 * mm
                rows_meta = [("Claimant", args.claimant or ""),
                             ("Period", args.period or ""),
                             ("Receipts", str(len(receipts)))]
                if args.notes:
                    rows_meta.append(("Notes", args.notes))
                for k, v in rows_meta:
                    if v:
                        fk, tk = _txt(f"{k}:", bold=True)
                        c.setFont(fk, 11)
                        c.drawString(MARGIN, y, tk)
                        fv, tv = _txt(v)
                        # truncate to the printable width so nothing runs off-page
                        room = PW - MARGIN - (MARGIN + 75) - 6
                        shown = tv
                        while shown and c.stringWidth(shown, fv, 11) > room:
                            shown = shown[:-1].rstrip()
                        c.setFont(fv, 11)
                        c.drawString(MARGIN + 75, y, shown)
                        y -= 7 * mm
                y -= 6 * mm
            c.setFont("Helvetica-Bold", 10)
            c.drawString(MARGIN, y, "#")
            c.drawString(MARGIN + 12 * mm, y, "Date")
            c.drawString(MARGIN + 45 * mm, y, "Description")
            c.drawRightString(PW - MARGIN, y, "Amount")
            return y - 6 * mm

        pn = 1
        for page_rows, has_title in cover_plan:
            y = (PH - 40 * mm) if has_title else (PH - MARGIN)
            y = cover_table_header(y, has_title)
            for e in page_rows:
                amt = e.get("amount")
                fd, td = _txt(e.get("date") or "-")
                fdesc, tdesc = _txt(e.get("description") or e.get("merchant") or "-")
                c.setFont("Helvetica", 10)
                c.drawString(MARGIN, y, str(e["n"]))
                c.setFont(fd, 10)
                c.drawString(MARGIN + 12 * mm, y, td)
                c.setFont(fdesc, 10)
                c.drawString(MARGIN + 45 * mm, y, tdesc[:70])
                if isinstance(amt, (int, float)):
                    fa, ta = _txt(f"{e.get('currency','')}{amt:,.2f}")
                    c.setFont(fa, 10)
                    c.drawRightString(PW - MARGIN, y, ta)
                y -= ROW_H
            pn += 1
            if pn <= cover_pages:
                page_footer(pn - 1)
                c.showPage()
        # totals + page footer on the last cover page
        yy = y - 4 * mm
        if len(tot_by_ccy) == 1:
            ccy, tot = next(iter(tot_by_ccy.items()))
            ft, tt = _txt(f"Total: {ccy} {tot:,.2f}", bold=True)
            c.setFont(ft, 11)
            c.drawRightString(PW - MARGIN, yy, tt)
        elif tot_by_ccy:
            for ccy in sorted(tot_by_ccy):
                ft, tt = _txt(f"Total {ccy}: {tot_by_ccy[ccy]:,.2f}", bold=True)
                c.setFont(ft, 11)
                c.drawRightString(PW - MARGIN, yy, tt)
                yy -= 6 * mm
        page_footer(pn - 1)
        c.showPage()

    # ---- receipt pages
    pn = cover_pages  # receipt pages start after the cover
    for page in pages:
        y = PH - MARGIN
        for row, img_h, row_h, tall in page:
            n_cols = len(row)
            col_w = (content_w - gap * (n_cols - 1)) / n_cols
            x = MARGIN
            for e in row:
                w_, h_ = cell_for(e, col_w, img_h)
                img_path = workdir / e["processed"]  # same resolution as digest/missing checks
                c.drawImage(str(img_path), x, y - h_, width=w_, height=h_,
                            preserveAspectRatio=True)
                # numbering badge (drawn below image, inside reserved strip)
                if args.number:
                    badge_top = y - h_ - 1.5 * mm  # gap below the image edge
                    c.setFont("Helvetica-Bold", 10)
                    badge_w = c.stringWidth(f"#{e['n']}", "Helvetica-Bold", 10) + 6
                    c.rect(x, badge_top - BADGE_H, badge_w, BADGE_H, stroke=0, fill=1)
                    c.setFillGray(1)
                    c.drawString(x + 3, badge_top - BADGE_H + 3.2, f"#{e['n']}")
                    c.setFillGray(0)
                # caption (below badge; merchant truncated to fit, amount never cut)
                if args.captions:
                    amt_txt = (f"{e.get('currency','')}{e['amount']:,.2f}"
                               if isinstance(e.get("amount"), (int, float)) else None)
                    n_txt = f"#{e['n']}"
                    date_txt = e.get("date") or None
                    merch_txt = e.get("merchant") or e.get("description") or None
                    sep = "  ·  "
                    # resolve fonts ONCE for the whole caption; mixed-font
                    # captions aren't worth the complexity — if any part is
                    # non-Latin the whole caption uses the Unicode font
                    parts_all = [n_txt, date_txt or "", amt_txt or "",
                                 merch_txt or ""]
                    cap_font = "Helvetica"
                    cap_warn = False
                    if any(not p.isascii() for p in parts_all):
                        if uni_font:
                            cap_font = uni_font
                        else:
                            cap_warn = True  # _txt-equivalent sanitize fallback
                    amt_w = c.stringWidth(amt_txt, cap_font, 8.5) if amt_txt else 0
                    sep_w = c.stringWidth(sep, cap_font, 8.5)
                    # fixed fields (#n, date) and amount stay whole; only the
                    # merchant/description slot is ellipsized to fit
                    base = sep.join([p for p in (n_txt, date_txt) if p])
                    base_w = c.stringWidth(base, cap_font, 8.5)
                    avail = col_w - base_w - sep_w - amt_w - sep_w  # base·tail·amt
                    ell = "…"
                    tail = ""
                    if merch_txt:
                        tail = merch_txt
                        while tail and c.stringWidth(tail, cap_font, 8.5) > avail:
                            cut = max(len(tail) - 1 - len(ell), 0)
                            if cut <= 0:
                                tail = ""
                                break
                            tail = tail[:cut].rstrip() + ell
                    chunks = [p for p in (base, tail) if p]
                    if amt_txt:
                        chunks.append(amt_txt)
                    cap = sep.join(chunks)
                    if cap_warn:
                        # no Unicode font: same sanitize fallback as _txt()
                        cap = cap.encode("latin-1", "replace").decode("latin-1")
                        print(f"WARN non-Latin caption unavailable (no TTF found): "
                              f"{cap!r}", file=sys.stderr)
                    c.setFont(cap_font, 8.5)
                    c.setFillGray(0.3)
                    cap_y = y - h_ - BADGE_H - 14 if args.number else y - h_ - 12
                    c.drawString(x, cap_y, cap)
                    c.setFillGray(0)
                x += col_w + gap
            y -= row_h + gap
        pn += 1
        page_footer(pn)
        c.showPage()

    c.save()
    print(json.dumps({"out": str(out), "pages": total_pages, "receipts": len(receipts)}))
    return 0


# ----------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="process photos + OCR -> manifest.json")
    p.add_argument("input_dir")
    p.add_argument("-o", "--out", required=True, help="workdir for manifest+processed/")
    p.add_argument("--mode", choices=["bw", "photo"], default="bw",
                   help="bw = photocopy-style threshold (default), photo = grayscale")
    p.set_defaults(fn=cmd_scan)

    p = sub.add_parser("review", help="print expense table for confirmation")
    p.add_argument("workdir")
    p.set_defaults(fn=cmd_review)

    p = sub.add_parser("confirm", help="stamp user approval into the manifest "
                       "(run AFTER the user approves the reviewed table; edits "
                       "made before confirm are included, edits after are blocked)")
    p.add_argument("workdir")
    p.set_defaults(fn=cmd_confirm)

    p = sub.add_parser("pack", help="build A4 PDF from CONFIRMED manifest")
    p.add_argument("workdir")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--title", default="Expense Claim")
    p.add_argument("--claimant", default="")
    p.add_argument("--period", default="")
    p.add_argument("--notes", default="")
    p.add_argument("--cover", action="store_true")
    p.add_argument("--captions", action="store_true")
    p.add_argument("--number", action="store_true")
    p.set_defaults(fn=cmd_pack)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())