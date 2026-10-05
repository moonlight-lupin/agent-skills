#!/usr/bin/env python3
"""pdf2epub — PDF → EPUB with cover, sections, footnotes, and 目录 (TOC).

TOC sources, in priority order:
1. embedded TOC (doc.get_toc) — most reliable when present
2. printed TOC page (目录/Contents, dot-leader lines: "title ..... N"),
   resolved to PDF page indices via a learned offset
3. heading detection (font-size outliers)

Per-page line classification separates running folios (page-number footers),
footnote blocks (smaller font, bottom zone), and footnote references
(superscript digits) from body text. Body lines are re-sorted by y per page
(fixes pymupdf's fragmented block order), footnotes render at the end of
their chapter with anchor links, superscript refs become clickable
noterefs, page-number footers are dropped.

Body font size is learned per book (2-char-mode median), never hard-coded —
works for CJK SimSun 12pt as well as Latin 10-11pt books.

Cover: largest image on page 1 (≥ 25k px², filters logos/stamps), else
page 1 rendered at 150 DPI.

Scanned PDFs (no text layer) are refused — run the document-toolkit OCR
path first, or pass --scan.

Usage:
  pdf2epub.py input.pdf [-o out.epub] [--title T] [--author A] [--lang L]
                        [--no-footnotes] [--scan] [-v]
"""
import argparse
import hashlib
import io
import os
import re
import unicodedata
from collections import Counter

import pymupdf
from ebooklib import epub

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

DOTS_RE = re.compile(r"[.·…․]{2,}\s*([0-9]+|[ivxlcdmIVXLCDM]+)\s*$")
NUM_RE = re.compile(r"^[0-9]{1,4}$")
FNREF_RE = re.compile(r"^[0-9]{1,2}$")


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


ROMAN_RE = re.compile(r"^[ivxlcdm]{1,6}$", re.IGNORECASE)


def clean(s: str) -> str:
    return unicodedata.normalize("NFC", " ".join((s or "").split())).strip()


def detect_scanned(doc):
    empty, has_text = [], False
    for i, page in enumerate(doc):
        t = page.get_text().strip()
        if len(t) < 20 and not page.get_images():
            empty.append(i)
        if len(t) >= 20:
            has_text = True
    return not has_text, empty


def extract_cover(doc, out_dir: str, min_area: int = 25_000) -> str:
    """Cover strategy, in order of reliability:

    1. SINGLE page-1 image that covers most of the page area → that image at
       native resolution (real cover art as one asset).
    2. Anything else — multiple large images, a big background texture with
       text layers painted over it, or no image at all — → render the full
       page at 200 DPI. Page 1 is a composed cover only when the components
       (texture + framed photo + typography) are drawn together; extracting
       any single image then yields a fragment (bare texture, naked photo).

    min_area is the threshold for considering an embedded image at all."""
    path = os.path.join(out_dir, "cover.png")
    page = doc[0]
    page_area = abs(page.rect)
    images = []
    for xref in {img[0] for img in page.get_images(full=True)}:
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        if not rects:
            continue
        r = max(rects, key=lambda rc: abs(rc))
        images.append((xref, abs(r) / page_area if page_area else 0.0))
    full_bleed = [i for i in images if i[1] >= 0.85]
    if len(images) == 1 and full_bleed:
        xref = images[0][0]
        try:
            pix = pymupdf.Pixmap(doc, xref)
            if pix.colorspace is None or pix.colorspace.n > 3:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            pix.save(path)
            return path
        except Exception:
            pass  # fall through to render
    pix = page.get_pixmap(dpi=200)
    pix.save(path)
    return path


# ---------- inline images (illustrations) ----------

IMG_MIN_AREA_FRAC = 0.03     # ≥ 3% of page area = real illustration, not icon
IMG_CROP_DPI = 140           # render/crop DPI; print-grade, keeps file sizes sane
IMG_MAX_DIM = 1600           # PIL LANCZOS downscale cap (koreyba)


def extract_inline_images(doc, cover_page_idx=0, min_area_frac=IMG_MIN_AREA_FRAC):
    """Every non-cover illustration as a page-surface crop (marker's method).

    marker crops figures from a rendered page instead of pulling raw xref
    XObjects — survives composed/vector art and CMYK/mask oddities. Geometry
    comes from PDF structure directly (page.get_image_info), so no AI layout
    model is needed. Identical art dedups by pixel hash (pdf-craft's move).

    Returns [(page_idx, y0_frac, filename)] in reading order.
    """
    if PILImage is None:
        return []
    out, seen = [], set()
    for i, page in enumerate(doc):
        page_area = abs(page.rect) or 1.0
        ph = page.rect.height or 1.0
        for info in page.get_image_info():
            bx = info["bbox"]
            w, h = bx[2] - bx[0], bx[3] - bx[1]
            if w <= 0 or h <= 0:
                continue
            if (w * h) / page_area < min_area_frac:
                continue  # icons / stamps / decorative dots
            if i == cover_page_idx and bx[1] <= 0.10 and \
                    (w * h) / page_area >= 0.85:
                continue  # region already used as the cover
            clip = pymupdf.Rect(bx) & page.rect
            if clip.is_empty:
                continue
            # top-strip caption guard: page text lines that overlap only the
            # top ~15% of the image are page-level captions bleeding in —
            # lower the clip top below them
            cut = clip.y0
            for b in page.get_text("dict")["blocks"]:
                if b.get("type") != 0:
                    continue
                for l in b.get("lines", []):
                    lb = pymupdf.Rect(l["bbox"])
                    t = "".join(s["text"] for s in l["spans"]).strip()
                    if not t:
                        continue
                    ov = lb & clip
                    if ov.is_empty:
                        continue
                    depth = ov.y1 - clip.y0
                    if depth < clip.height * 0.15 and lb.y0 < clip.y0:
                        cut = max(cut, lb.y1 + 2)
            if cut >= clip.y1:
                continue
            clip = pymupdf.Rect(clip.x0, cut, clip.x1, clip.y1)
            zoom = IMG_CROP_DPI / 72.0
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom),
                                  clip=clip, alpha=False)
            data = pix.tobytes("png")
            sha = hashlib.sha256(data).hexdigest()
            if sha in seen:
                continue
            seen.add(sha)
            out.append((i, bx[1] / ph, data))
    return out


def optimize_image(data):
    """Downscale + JPEG q85 (koreyba's optimizer). PNG→JPEG on white."""
    if PILImage is None:
        return data, "png"
    try:
        im = PILImage.open(io.BytesIO(data))
        if im.mode in ("RGBA", "LA", "P"):
            bg = PILImage.new("RGB", im.size, (255, 255, 255))
            im = im.convert("RGBA")
            bg.paste(im, mask=im.split()[3])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")
        w, h = im.size
        if w > IMG_MAX_DIM or h > IMG_MAX_DIM:
            s = min(IMG_MAX_DIM / w, IMG_MAX_DIM / h)
            im = im.resize((int(w * s), int(h * s)), PILImage.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85, optimize=True)
        return buf.getvalue(), "jpg"
    except Exception:
        return data, "png"


def save_inline_images(doc, imgs, epub_dir):
    """Optimize + write under {epub_dir}/images/ (zip gets its own copy via
    EpubImage); return [(page_idx, y0f, fn, data)]."""
    d = os.path.join(epub_dir, "images")
    os.makedirs(d, exist_ok=True)
    kept = []
    for k, (page_idx, y0f, data) in enumerate(imgs):
        data, ext = optimize_image(data)
        if len(data) < 2_000:
            continue  # near-blank crops (solid color / noise) — drop
        fn = f"i{page_idx:03d}-{k:03d}.{ext}"
        with open(os.path.join(d, fn), "wb") as f:
            f.write(data)
        kept.append((page_idx, y0f, fn, data))
    return kept


# ---------- line collection + classification ----------

def collect_lines(doc):
    """(page_idx, y_top_ratio, size, is_sup, text) for every text line.
    y_top_ratio = line top / page height."""
    out = []
    for i, page in enumerate(doc):
        h = page.rect.height or 1.0
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if s["text"].strip()]
                if not spans:
                    continue
                txt = clean("".join(s["text"] for s in spans))
                size = max(s["size"] for s in spans)
                sup = any(s["flags"] & 1 for s in spans)
                out.append([i, line["bbox"][1] / h, size, sup, txt])
    return out


def body_font_size(doc, lines) -> float:
    """Two-char-mode of line font sizes: robust when footnotes outnumber
    body lines on TOC/blank pages."""
    sizes = Counter(round(size, 1) for _, _, size, _, txt in lines if len(txt) > 8)
    return sizes.most_common(1)[0][0] if sizes else 12.0


def classify_lines(doc, lines, body, endnote_pages=None):
    """Label each line BODY / FOLIO / FOOTNOTE / FNREF.

    Rules (conservative, validated on the Beeke sample):
    - FOLIO: bare 1-4 digit number (or roman i-vi), font < 0.85*body, bottom
      8% of the page.
    - FNREF: the WHOLE line is a bare digit with font < 0.75*body sitting in
      the body zone (y <= 0.78). QuarkXPress-style books emit the footnote
      marker as its own tiny line before the paragraph that cites it; the
      superscript flag is unreliable and often unset.
    Rule refinement (learned from the Beeke sample): a footnote block can be
    WIDE — 10+ lines — and climb up to 2/3 page height. Classify a small-font
    line as FOOTNOTE when it sits below every BODY line with a larger font on
    the same page (small-font-below-body rule). Simpler robust variant used
    here: y > 0.60 and font < 0.92*body and the line is not a list marker
    (body lists at small size are rare).

    endnote_pages: set of page indexes belonging to an endnotes/注释 section.
    Those pages carry notes at SMALL font from the very TOP of the page —
    the y > 0.60 cut would classify them BODY. On endnote pages the y test
    drops out (any y)."""
    endnote_pages = endnote_pages or set()
    out = []
    for (page, yr, size, sup, txt) in lines:
        in_notes = page in endnote_pages
        if (NUM_RE.fullmatch(txt) or ROMAN_RE.fullmatch(txt)) \
                and size < body * 0.85 and yr > 0.90:
            out.append((page, yr, size, sup, txt, "FOLIO"))
            continue
        if FNREF_RE.fullmatch(txt) and size < body * 0.75 and not in_notes:
            out.append((page, yr, size, sup, txt, "FNREF"))
            continue
        if size < body * 0.92 and (yr > 0.60 or in_notes) \
                and not re.match(r"^([0-9]{1,2}[.、．]|[-•–—])\s", txt):
            out.append((page, yr, size, sup, txt, "FOOTNOTE"))
            continue
        out.append((page, yr, size, sup, txt, "BODY"))
    return out


def group_footnote_blocks(fnotes):
    """fnotes already in page+y reading order → note blocks.

    A new note starts at a line whose leading bare digit token is the next
    expected note number (prev + 1, or 1 for the first) — the number may be
    GLUED to the text ('1查尔斯…') or space-separated ('1 查尔斯…'), both
    are note starts. Continuation lines attach to the previous note. Guards:
    - a bare-digit line with no body is a stray superscript ref → dropped
    - a continuation line whose leading digits do NOT continue the run is
      text (dates, page cites like '1996 年版') → attaches as continuation
    - note numbering runs monotonically within one notes section; a number
      ≤ prev means a numbering restart (per-chapter restart books) → start
      the new run only when number == 1, else treat as continuation."""
    blocks = []
    expect = 1
    for page, yr, size, sup, txt, kind in fnotes:
        m = re.match(r"^(\d{1,3})(\s+.*|)$", txt) or re.match(r"^(\d{1,3})()\S.*$", txt)
        num = int(m.group(1)) if m else None
        body_txt = (m.group(2).strip() if m and m.re.pattern.endswith("$") else "") \
            if m else ""
        if m:
            rest = txt[len(m.group(1)):].strip()
            has_body = len(rest) >= 2
            prev = blocks[-1] if blocks else None
            if num == expect and has_body:
                blocks.append((page, num, rest))
                expect = num + 1
                continue
            if has_body and prev is None and num == 1:
                blocks.append((page, num, rest))
                expect = 2
                continue
            # not the expected number → continuation (dates, citations)
        if blocks:
            pg, num2, t = blocks[-1]
            blocks[-1] = (pg, num2, (t + " " + txt).strip())
        # lines before any note start are stray — drop
    return blocks


# ---------- sections ----------

ENDNOTE_TITLE_RE = re.compile(r"^(注释|註釋|脚注|尾注|Notes|Endnotes|Notes and References)$")


def endnote_page_set(sections, n_pages, doc=None):
    """Page indexes of an endnotes section. Preferred: resolved section list
    with a title like 注释/Notes. Fallback (sections unresolved): any late
    page whose first non-folio line matches the endnote title regex."""
    out = set()
    if sections:
        for k, (level, title, start) in enumerate(sections):
            if ENDNOTE_TITLE_RE.match(title.strip()):
                end = sections[k + 1][2] if k + 1 < len(sections) else n_pages
                out.update(range(start, min(end, n_pages)))
        return out
    if doc is None:
        return out
    for i in range(max(0, n_pages - 60), n_pages):
        first = doc[i].get_text().strip().split("\n")[0].strip()
        if ENDNOTE_TITLE_RE.match(first):
            out.update(range(i, n_pages))
            break
    return out


def sections_from_embedded(doc):
    out, seen = [], set()
    for level, title, page1 in doc.get_toc(simple=True):
        if not (1 <= level <= 3) or not (1 <= page1 <= len(doc)):
            continue
        key = (title, page1)
        if key in seen:
            continue
        seen.add(key)
        out.append((level, clean(title), page1 - 1))
    return out


def cover_page_title(doc):
    page = doc[0]
    best, best_size = [], 0.0
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            txt = clean("".join(s["text"] for s in spans))
            size = max(s["size"] for s in spans)
            if txt and size >= best_size - 0.5:
                if size > best_size + 0.5:
                    best, best_size = [], size
                best.append((line["bbox"][1], txt))
    if not best or best_size < 8:
        return None
    return " ".join(t for _, t in sorted(best)[:4])


def find_toc_page(doc):
    for i in range(min(15, len(doc))):
        t = doc[i].get_text()
        if re.search(r"^目录\s*$", t, re.M) or re.match(r"\s*(Table of )?Contents\s*$", t, re.M):
            return i
    return None


def parse_printed_toc(doc, toc_page):
    out = []
    for raw in doc[toc_page].get_text().splitlines():
        m = DOTS_RE.search(raw)
        if not m:
            continue
        title = clean(re.sub(r"[.·…․]{2,}\s*[0-9ivx]+\s*$", "", raw))
        if title and len(title) < 120:
            out.append((1, title, m.group(1)))
    return out


def parse_printed_toc_run(doc, toc_page):
    """Parse a printed TOC that may span several pages. A TOC page belongs to
    the run only while it yields dot-leader entries; the first page without
    any ends the run (front-matter pages yield none)."""
    out = list(parse_printed_toc(doc, toc_page))
    i = toc_page + 1
    while i < len(doc):
        more = parse_printed_toc(doc, i)
        if not more:
            break
        out.extend(more)
        i += 1
    return out


def _body_search_text(doc):
    """Cached per-page search text: whitespace collapsed away (page line
    breaks insert spaces/newlines inside titles)."""
    texts = []
    for page in doc:
        texts.append(re.sub(r"\s+", "", page.get_text()))
    return texts


def _probe_variants(title):
    """Search keys for a TOC title: full title (no spaces) + title without a
    leading 第N章/第N部分/第N篇/Part N marker (body headings may spell the
    number differently, e.g. TOC '第二十章' vs body '第20 章')."""
    t = re.sub(r"\s+", "", title)
    variants = [t]
    m = re.match(r"^第[0-9一二三四五六七八九十百]+(章|部分|篇|回)(.*)$", t)
    if m and m.group(2):
        variants.append(m.group(2))
    m2 = re.match(r"^(Part|Chapter)\s*\d+[.:：]?\s*(.*)$", title, re.I)
    if m2 and m2.group(2):
        variants.append(re.sub(r"\s+", "", m2.group(2)))
    # parenthetical insertions: body headings add (English name) between the
    # name and the rest — add the segment before the first '·' as a variant
    if "·" in t:
        variants.append(t.split("·")[0])
    return [v[:30] for v in variants if len(v) >= 2]


def _heading_page_hit(doc, page_texts, probes, guess_range, exclude_pages=None):
    """Find the first page in guess_range carrying a standalone short heading
    line for this TOC entry. Probes are ORDERED: probe[0] is the full
    stripped title; later probes are loose variants (tail after the chapter
    marker, parenthetical-cut prefixes). The full title is tried across the
    whole window FIRST — body prose quoting a phrase fragment ('…既包括预
    防性管教…') must not shadow the real heading page — then loose variants.
    Falls back to whole-page substring."""
    exclude_pages = set(exclude_pages or ())
    for probe in probes:
        for guess in guess_range:
            if guess in exclude_pages:
                continue
            for line in doc[guess].get_text().split("\n"):
                line = re.sub(r"\s+", "", line.strip())
                if line and len(line) <= 34 and probe in line:
                    return guess
    for probe in probes:
        for guess in guess_range:
            if guess in exclude_pages:
                continue
            if probe in page_texts[guess]:
                return guess
    return None


def resolve_printed_toc(doc, entries, exclude_pages=None):
    resolved, offsets = [], {}
    page_texts = _body_search_text(doc)
    exclude_pages = set(exclude_pages or ())
    for level, title, label in entries:
        if not str(label).isdigit():
            continue  # roman numerals → front matter, skip
        printed = int(label)
        found = None
        probes = _probe_variants(title)
        if probes:
            found = _heading_page_hit(
                doc, page_texts, probes,
                range(max(0, printed - 3), min(len(doc), printed + 40)),
                exclude_pages)
        if found is not None:
            off = found - (printed - 1)
            offsets[off] = offsets.get(off, 0) + 1
            resolved.append((level, title, printed, found))
    if not resolved:
        return []
    best_off = max(offsets, key=offsets.get)
    out, seen, prev_idx = [], set(), -1
    for level, title, printed, found in resolved:
        # prefer the actual matched page; fall back to majority offset when
        # the probe found nothing. Same-page sections (part title + chapter
        # on one page) are legit — only drop strictly-backwards idx.
        idx = found if found is not None and found >= prev_idx \
            else printed - 1 + best_off
        if not (0 <= idx < len(doc)) or idx < prev_idx:
            continue
        key = (idx, title)
        if key in seen:
            continue
        seen.add(key)
        out.append((level, title, idx))
        prev_idx = idx
    return out


def sections_from_headings(doc, classified, body):
    toc_page = find_toc_page(doc)
    big = sorted({s for _, _, s, _, _ in classified if s >= body + 2.0}, reverse=True)[:3]
    by_page = {}
    for page, yr, size, sup, txt, kind in classified:
        if kind != "BODY" or size not in big:
            continue
        if toc_page is not None and page == toc_page:
            continue
        if yr > 0.25:
            continue
        if page in by_page and by_page[page][1] >= size:
            continue
        by_page[page] = (1 if size == big[0] else 2, txt)
    return [(l, t, p) for p, (l, t) in sorted(by_page.items())]


# ---------- html ----------

def _anchor(tgt: str) -> str:
    """Inline href target: fragment anchors get '#' prepended; cross-file
    targets ('sec030.xhtml#fnc30-4') already carry their '#' — a leading
    '#' would turn them into a same-document fragment that exists nowhere."""
    return tgt if '.xhtml#' in tgt else f'#{tgt}'


def _noteref_html(tgt: str, ref_id: str, num: int) -> str:
    return (f'<a epub:type="noteref" href="{_anchor(tgt)}" '
            f'id="{ref_id}" role="doc-noteref"><sup>{num}</sup></a>')

def render_body(classified, page_start, page_end, fnrefs_by_page, chap_key,
                ref_target=None):
    """Body lines in page order, per-page y-sorted, → paragraph HTML.

    chap_key: per-chapter string prefix for footnote anchors, so per-chapter
    note numbering restarts cannot collide.

    ref_target: optional callable (num, chap_key) → anchor id or None.
    Defaults to chapter-local fn{chap_key}-{num}.

    Paragraph break rules:
    - list-marker lines (n./-/•, < 60 chars) start a new paragraph
    - a vertical gap between consecutive lines (> 1.8 line steps) starts a
      new paragraph
    - footnote refs (<a noteref>) attach inline at their y position."""
    if ref_target is None:
        ref_target = lambda num, ck: f"fn{ck}-{num}"  # noqa: E731
    paras, cur = [], []
    last_yr = None

    def flush():
        if cur:
            paras.append(" ".join(cur))
            cur.clear()

    pending = list(fnrefs_by_page)
    pi = 0
    for (page, yr, size, sup, txt, kind) in classified:
        if not (page_start <= page <= page_end) or kind != "BODY":
            continue
        while pi < len(pending) and pending[pi][1] <= yr:
            num = int(pending[pi][4])
            tgt = ref_target(num, chap_key)
            if tgt:
                cur.append(_noteref_html(tgt, f"ref{chap_key}-{num}", num))
            else:
                cur.append(f'<sup>{num}</sup>')
            pi += 1
        is_marker = re.match(r"^([0-9]{1,2}[.、．]|[-•–—])", txt) and len(txt) < 60
        big_gap = last_yr is not None and (yr - last_yr) > 0.045 and cur
        if is_marker or big_gap:
            flush()
        cur.append(txt)
        last_yr = yr
    while pi < len(pending):
        num = int(pending[pi][4])
        tgt = ref_target(num, chap_key)
        if tgt:
            cur.append(_noteref_html(tgt, f"ref{chap_key}-{num}", num))
        else:
            cur.append(f'<sup>{num}</sup>')
        pi += 1
    flush()
    return [f"<p>{p}</p>" for p in paras]


def build_footnote_html(fn_blocks, pages_in_chapter, chap_key, notes_back=None):
    """Footnotes whose first-line page is inside the chapter → end-of-chapter
    HTML. Ids are chapter-scoped: fn{chap_key}-{num}.

    notes_back: optional callable (num, this_chap_key) → back-link target for
    the [n] anchor. When the citing ref lives in another spine file the
    target must carry that file's name; when it does not exist at all the
    anchor degrades to plain text."""
    mine = [(num, text) for (page, num, text) in fn_blocks
            if page in pages_in_chapter and text and num is not None]
    if not mine:
        return ""
    items = []
    for num, text in mine:
        back = notes_back(num, chap_key) if notes_back else f"ref{chap_key}-{num}"
        if back:
            items.append(
                f'<p id="fn{chap_key}-{num}"><a href="{_anchor(back)}">'
                f'[{num}]</a> {esc(text)}</p>')
        else:
            items.append(f'<p id="fn{chap_key}-{num}">[{num}] {esc(text)}</p>')
    return f'<div class="footnotes">{"".join(items)}</div>'


# ---------- main ----------

def convert(input_pdf, output, title, author, lang, scan, no_footnotes, verbose):
    doc = pymupdf.open(input_pdf)
    base = os.path.splitext(os.path.basename(input_pdf))[0]

    scanned, empty_pages = detect_scanned(doc)
    if scanned and not scan:
        raise SystemExit(
            f"{input_pdf}: no text layer (image-only scans). "
            "Run OCR first (document-toolkit skill) or pass --scan.")

    meta = doc.metadata or {}
    if not title and not (meta.get("title") or "").strip():
        title = cover_page_title(doc)
    book_title = clean(title or meta.get("title") or base)
    book_author = clean(author or meta.get("author") or "Unknown")
    book_lang = lang or "en"

    book = epub.EpubBook()
    book.set_identifier("pdf2epub-" + base)
    book.set_title(book_title)
    book.set_language(book_lang)
    book.add_author(book_author)
    book.add_item(epub.EpubItem(
        uid="style", file_name="style.css", media_type="text/css",
        content="body{font-family:serif;line-height:1.6}"
                "h1,h2,h3{font-family:sans-serif;line-height:1.3}"
                "a[epub\\:type~='noteref'],a.noteref{text-decoration:none}"
                ".footnotes{font-size:0.85em;margin-top:2em;"
                "border-top:1px solid #999;padding-top:0.6em}"
                ".footnotes p{margin:0.35em 0}"
                "figure.illus{margin:1.2em 0;text-align:center;padding:0}"
                "figure.illus img{max-width:100%;height:auto}"))

    cover_path = extract_cover(doc, os.path.dirname(os.path.abspath(output or base + ".epub")))
    if cover_path and os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            book.set_cover("cover.png", f.read())

    # --- inline illustrations (page-surface crops, marker-style) ---
    epub_dir = os.path.dirname(os.path.abspath(output or base + ".epub"))
    inline_imgs = save_inline_images(
        doc, extract_inline_images(doc, cover_page_idx=0), epub_dir)
    n_inline = 0
    imgs_by_page = {}
    for pg, y0f, fn, data in inline_imgs:
        it = epub.EpubImage(uid=fn, file_name=f"images/{fn}",
                            media_type=f"image/jpeg" if fn.endswith(".jpg") else "image/png",
                            content=data)
        book.add_item(it)
        imgs_by_page.setdefault(pg, []).append((y0f, f"images/{fn}"))
        n_inline += 1

    # --- sections (resolve BEFORE classification: endnote-section detection
    # needs the section list, and TOC parsing needs no classified lines) ---
    sections = sections_from_embedded(doc)
    source = "embedded-toc"
    if not sections:
        tp = find_toc_page(doc)
        if tp is not None:
            toc_run = parse_printed_toc_run(doc, tp)
            # exclude every page of the TOC run from probe matching
            run_last = tp
            i = tp + 1
            while i < len(doc) and parse_printed_toc(doc, i):
                run_last = i
                i += 1
            toc_pages = set(range(tp, run_last + 1))
            sections = resolve_printed_toc(
                doc, toc_run, exclude_pages=toc_pages)
            source = "printed-toc"
    if not sections:
        sections = sections_from_headings(doc, collect_lines(doc), body)
        source = "heading-fallback"

    # --- classify everything once ---
    raw_lines = collect_lines(doc)
    body = body_font_size(doc, raw_lines)
    classified = classify_lines(doc, raw_lines, body,
                                endnote_pages=endnote_page_set(sections, len(doc), doc))
    # per-page y-sort for reading order (fixes fragmented PDF blocks)
    classified.sort(key=lambda l: (l[0], l[1]))

    folios = [l for l in classified if l[5] == "FOLIO"]
    fnotes = [l for l in classified if l[5] == "FOOTNOTE"]
    fnrefs = [l for l in classified if l[5] == "FNREF"]

    if no_footnotes:
        # demote: footnotes stay in body as plain text, refs become plain [n]
        reclass = []
        for (page, yr, size, sup, txt, kind) in classified:
            if kind == "FOOTNOTE":
                kind = "BODY"
            elif kind == "FNREF":
                txt = f"[{txt}]"
                kind = "BODY"
            reclass.append((page, yr, size, sup, txt, kind))
        classified = reclass
        fn_blocks, fnrefs = [], []
        fnrefs_by_page = {}
    else:
        fn_blocks = group_footnote_blocks(fnotes)
        fnrefs_by_page = {}
        for ref in fnrefs:
            fnrefs_by_page.setdefault(ref[0], []).append(ref)

    # --- chapter build ---
    fm_title = "前言" if book_lang == "zh" else "Front Matter"

    # Global endnote anchor table: numbers provided by the endnotes section
    # (chapter-scoped refs fall back to these — endnote numbering in books
    # like this Beeke translation is GLOBAL across chapters, 1..127).
    notes_sec_idx = next((i for i, (_, t, _) in enumerate(sections)
                          if ENDNOTE_TITLE_RE.match(t.strip())), None)
    notes_chap_key = f"c{notes_sec_idx}" if notes_sec_idx is not None else None
    global_note_nums = set()
    chap_note_keys = {}
    for (pg, num, _) in fn_blocks:
        if num is None:
            continue
        chap = next((f"c{i}" for i, (_, _, st) in enumerate(sections + [(1, "", len(doc))])
                     if st <= pg), "c0") if sections else "c0"
        chap_note_keys.setdefault(chap, set()).add(num)
    if notes_sec_idx is not None:
        ns, ne = sections[notes_sec_idx][2], len(doc)
        global_note_nums = {num for (pg, num, _) in fn_blocks if ns <= pg < ne}
        chap_note_keys.setdefault(notes_chap_key, set()).update(global_note_nums)

    def ref_href(num, chap_key):
        """noteref target: chapter-local anchor when that chapter carries the
        note; else the global endnotes-section anchor — CROSS-FILE, so the
        href carries the section file name (EPUB same-document '#id' links
        don't navigate between spine files). Body refs without any matching
        note render as bare sup (still readable)."""
        if num is None:
            return None
        if f"{chap_key}-{num}" in chap_note_keys.get(chap_key, set()):
            return f"fn{chap_key}-{num}"
        if notes_chap_key is not None and num in global_note_nums:
            if notes_chap_key == chap_key:
                return f"fn{notes_chap_key}-{num}"
            return f"sec{notes_sec_idx:03d}.xhtml#fn{notes_chap_key}-{num}"
        return None

    # back-link map: which spine file cites each note (for the notes
    # section's [n] back-anchors). First citation wins; ambiguous when a
    # chapter-restart book reuses numbers — chapter-local back-links only.
    ref_page_by_num = {}
    if notes_sec_idx is not None and notes_sec_idx < len(sections):
        ns = sections[notes_sec_idx][2]
        for refpg, refs in fnrefs_by_page.items():
            if refpg < ns:
                for ref in refs:
                    ref_page_by_num.setdefault(int(ref[4]), refpg)
        ref_sec_by_num = {}
        for num, pg in ref_page_by_num.items():
            si = max((i for i, (_, _, st) in enumerate(sections) if st <= pg),
                     default=None)
            if si is not None:
                ref_sec_by_num[num] = si

        def notes_back(num, this_chap):
            si = ref_sec_by_num.get(num)
            if si is None:
                return None  # no citing ref found → plain text
            if si == notes_sec_idx:
                return f"ref{this_chap}-{num}"
            return f"sec{si:03d}.xhtml#refc{si}-{num}"
    else:
        notes_back = None

    def render_pages(start, end, chap_key):
        """Body HTML (str) + footnote HTML for pages [start, end]. Illustration
        <figure> blocks are appended per page, after that page's body (the
        illustrations in this conversion family are full-width art between
        text blocks; exact intra-page interleaving needs text-side bbox
        comparison, which render_body does not carry yet)."""
        parts = []
        for p in range(start, end + 1):
            parts.extend(render_body(
                classified, p, p, fnrefs_by_page.get(p, []), chap_key,
                ref_target=ref_href))
            parts.append("".join(
                f'<figure class="illus"><img src="{fn}" alt="Illustration"/></figure>'
                for _, fn in sorted(imgs_by_page.get(p, []))))
        body_html = "".join(parts)
        fn_html = build_footnote_html(fn_blocks, set(range(start, end + 1)), chap_key,
                                      notes_back=notes_back)
        return body_html, fn_html

    chapters = []
    if sections:
        first = sections[0][2]
        if first > 0:
            fm_parts = []
            for p in range(first):
                fm_parts.extend(render_body(classified, p, p,
                                            fnrefs_by_page.get(p, []), "front",
                                            ref_target=ref_href))
                fm_parts.append("".join(
                    f'<figure class="illus"><img src="{fn}" alt="Illustration"/></figure>'
                    for _, fn in sorted(imgs_by_page.get(p, []))))
            if fm_parts:  # skip empty front-matter section entirely
                fm = epub.EpubHtml(title=fm_title, file_name="front.xhtml", lang=book_lang)
                fm.content = f"<h1>{esc(fm_title)}</h1>" + "".join(fm_parts)
                fm.add_item(book.get_item_with_id("style"))
                book.add_item(fm)
                chapters.append(fm)
        for idx, (level, sec_title, start) in enumerate(sections):
            end = sections[idx + 1][2] - 1 if idx + 1 < len(sections) else len(doc) - 1
            end = max(end, start)
            body_html, fn_html = render_pages(start, end, f"c{idx}")
            ch = epub.EpubHtml(title=sec_title, file_name=f"sec{idx:03d}.xhtml", lang=book_lang)
            ch.content = f"<h1>{esc(sec_title)}</h1>" + body_html + fn_html
            ch.add_item(book.get_item_with_id("style"))
            book.add_item(ch)
            chapters.append(ch)
    else:
        fm_parts = []
        for p in range(len(doc)):
            fm_parts.extend(render_body(classified, p, p,
                                        fnrefs_by_page.get(p, []), "c0"))
        ch = epub.EpubHtml(title=book_title, file_name="all.xhtml", lang=book_lang)
        ch.content = "".join(fm_parts) + build_footnote_html(
            fn_blocks, set(range(len(doc))), "c0")
        ch.add_item(book.get_item_with_id("style"))
        book.add_item(ch)
        chapters.append(ch)

    book.toc = chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["cover", "nav"] + [c.id for c in chapters]

    if output is None:
        output = base + ".epub"
    epub.write_epub(output, book, {"epub3_pages": False})

    report = {
        "output": output,
        "title": book_title,
        "pages": len(doc),
        "sections": len(sections),
        "toc_source": source,
        "footnotes": len(fn_blocks),
        "fnrefs_linked": sum(len(v) for v in fnrefs_by_page.values()),
        "folios_dropped": len(folios),
        "cover": bool(cover_path),
        "inline_images": n_inline,
        "body_font_size": body,
        "empty_text_pages": empty_pages[:10],
    }
    if verbose:
        for level, t, p in sections[:25]:
            print(f"    {'  ' * (level - 1)}[L{level}] pdf-page {p + 1}: {t}")
    return report


def main():
    ap = argparse.ArgumentParser(description="PDF → EPUB with cover + sections + footnotes + TOC")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--title")
    ap.add_argument("--author")
    ap.add_argument("--lang")
    ap.add_argument("--no-footnotes", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    rep = convert(a.input, a.output, a.title, a.author, a.lang, a.scan, a.no_footnotes, a.verbose)
    for k, v in rep.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()