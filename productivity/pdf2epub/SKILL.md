---
name: pdf2epub
description: "Use when converting a PDF book to EPUB, e.g. 'pdf to epub', 'convert this PDF book for my e-reader', 'EPUB with cover and TOC', 'pdf to ebook for kobo/kindle'. Builds a text-layer PDF into an EPUB with cover image, one section per chapter, a parsed 目录/Contents TOC, inline illustrations, and footnote endnotes. Text-layer PDFs only — scanned PDFs route to document-toolkit OCR."
license: MIT
metadata:
  version: 1.2.1
  author: moonlight-lupin
  platforms: [linux]
  hermes:
    tags: ['pdf', 'epub', 'ebook', 'conversion', 'documents']
    related_skills: ['document-toolkit', 'opendataloader-pdf']
---

# pdf2epub

## Overview

Convert a text-layer PDF to EPUB with real structure: cover image, one chapter per section, and a working 目录 (nav + ncx). Fully deterministic — no LLM in the conversion path. Engine: `scripts/pdf2epub.py` (pymupdf + ebooklib + Pillow).

## When to Use

- A text-layer PDF book should become an EPUB with cover + sections + TOC
- A printed 目录/Contents page needs parsing into real EPUB nav
- Footnote-heavy books (devotional/theological) need notes as linked endnotes, not body-text pollution

Don't use for: image-only scans (refused — route to document-toolkit OCR first) or PDF→Markdown extraction (that is opendataloader-pdf).

## Run

```bash
python scripts/pdf2epub.py \
  input.pdf [-o out.epub] [--title T] [--author A] [--lang zh] [-v]
```

Needs `pymupdf`, `ebooklib`, `Pillow` (see `requirements.txt`). Create a dedicated venv for them if your environment pins system packages.

Optional flags: `--no-footnotes` keeps footnote text in body flow; `--scan` forces conversion of a scanless PDF.

**Done when:** exit 0, the report prints `sections` ≥ 1 with the expected chapter titles (check `-v` output), and the EPUB opens with its TOC intact. Verify deeper by zip-inspecting (see Verification).

## TOC resolution order

1. **Embedded TOC** (`doc.get_toc()`) — used when present; most reliable.
2. **Printed 目录/Contents page** — first page in the first 15 pages matching `/^目录$/` or `/Contents$/`. Line parser strips dot leaders (`....... N`) and keeps `(title, printed_N)`. Resolution searches pages `printed-3 … printed+40` for the title's first 16 chars, learns a single offset (majority vote), then maps every entry. Works when printed page numbers differ from PDF indices.
3. **Heading fallback** — font-size outliers vs page median. Crude. Check `-v` output before accepting.

## Cover

Strategy, in order of reliability:

1. **Single page-1 image covering ≥ 85% of the page area** → extract that image at native resolution (real cover art as one asset).
2. **Anything else** (multiple large images, a background texture with typography painted over it, no image) → **render the full page at 200 DPI**.

Learned from the Beeke book: page 1 had a full-bleed wood-grain texture (1500×1000) + a framed photo + text layers. Largest-image extraction picked the bare texture (a fragment); the actual cover exists only as the rendered composite. Extracting a single image is safe ONLY when it is the sole image and covers the page.

## Refusals

- Image-only PDF (no text layer): exits with error. Route to document-toolkit OCR first. `--scan` forces anyway (each page becomes one image-less chapter of garbage — only useful for testing).
- Dutch Annotations 1657 library PDFs are all scans — expect refusal there until OCR'd.

## Language

`--lang zh` for the Beeke-style CJK outputs; default `en`. PDF metadata rarely carries a language.

**Done when:** opening the built EPUB's nav shows front matter titled for the book's language (Front Matter for en) and no empty pre-chapter section for books whose cover page has no body text.

## Common Pitfalls

- Superscript flags are unreliable for footnote refs; gate on size + position (see pdf2epub-calibration).
- Caption text visible at an illustration crop's top edge is usually part of the publisher's raster asset, not page bleed — don't crop art away to remove it.
- Run the engine inside an environment that has pymupdf, ebooklib, and PIL installed; a bare system python without them fails on import.
- Never classify lines before sections resolve — endnote-section detection needs the section list (classification gains an endnote-pages set from resolved sections).
- A bare-digit FNREF matching no note block renders as plain sup text, never as a dangling link.

## Footnotes

Per-page line classification with learned body font size (2-char-mode of line sizes, never hard-coded):

- FOLIO: bare 1-4 digit (or roman i-vi) number, font < 0.85*body, bottom 8% → dropped.
- FNREF: whole line is a bare digit, font < 0.75*body, any y → clickable `noteref` anchor at that spot. This book style (QuarkXPress CJK) emits refs as standalone 6pt lines; superscript flags unreliable.
- FOOTNOTE: font < 0.92*body, y > 0.60, not a list marker → grouped into note blocks (start = leading digit + body; continuations attach; bare-digit strays dropped) and rendered at the END of the containing chapter with `[n]` back-links. Ids are chapter-scoped (`fnc0-N`) because note numbering restarts per chapter.
- Body font size can exceed footnote-block height — footnote blocks may climb to 2/3 page.

Known limit: refs embedded INSIDE body lines as 5pt spans (merged into the text) don't get anchors; their notes still appear in the chapter footnote list. On the Beeke book: 41 anchored / 58 notes.

`--no-footnotes` keeps footnote text in body flow as plain text.

## Inline illustrations

Every non-cover illustration is extracted as a page-surface CROP, not a raw xref: render the page at 140 DPI and cut the image bbox (`page.get_pixmap(matrix=…, clip=…)`, the marker approach without its AI layer). Crops survive composed/vector art and CMYK/mask oddities. Raw-xref extraction stays only for the cover.

- Geometry from `page.get_image_info()` — no AI layout model needed.
- Filters: area ≥ 3% of page (drops icons/logos), pixel-sha256 dedup (drops art shared across pages, pdf-craft's move), optimized crops < 2 KB dropped (near-blank).
- PIL optimizer: LANCZOS downscale to ≤ 1600 px, alpha compositing onto white, JPEG q85.
- Figures interleave per page, after that page's body text, as `<figure class="illus">`.
- Top-of-image caption text that looks clipped ("letters cut at the crop edge", different typeface) is usually INSIDE the publisher's raster asset — not bleed from the page. Check PDF text-line intersection first; if no overlap, the caption is part of the artwork and must ship with it. Do not cut art away trying to remove it.
- The cover page's ≥ 85% image is excluded (it ships as the cover).

## Verification Checklist

```bash
python3 - <<'EOF'
import zipfile, re, collections
z = zipfile.ZipFile("OUT.epub")
ok = True
for n in z.namelist():
    if not n.endswith(".xhtml") or "/nav" in n or "cover" in n:
        continue
    c = z.read(n).decode()
    ids = set(re.findall(r'id="([\w-]+)"', c))
    dup = [k for k, v in collections.Counter(re.findall(r'id="([\w-]+)"', c)).items() if v > 1]
    bad = []
    for h in re.findall(r'href="#([^"]+)"', c):
        if ".xhtml#" in h:  # cross-file: secNNN.xhtml#anchor
            f, aid = h.split(".xhtml#")
            full = "EPUB/" + f + ".xhtml"
            if full not in z.namelist() or aid not in ids | set(re.findall(r'id="([\w-]+)"', z.read(full).decode())):
                bad.append(h)
        elif h not in ids:
            bad.append(h)
    if bad or dup:
        ok = False
        print(n, "bad", bad, "dup", dup)
print("LINK CHECK:", "PASS" if ok else "FAIL")
EOF
```

- [ ] report: `sections ≥ 1`, `toc_source` matches the book (embedded vs printed)
- [ ] `-v` lists every expected chapter at a sane PDF page
- [ ] link check above: 0 missing targets, 0 duplicate ids
- [ ] cover renders complete (texture + titles + credits all present) — eyeball it once per new book

## Verified on

BEEKE-Covenant-Children (96 pp, CJK QuarkXPress-style): printed 目录 page 3 → 5 chapters resolved; cover = full-page 200-DPI render, visually verified complete; title from cover fonts; 58 notes dense per chapter (23/5/25/5); 41 noterefs all resolve, 0 broken targets, 0 duplicate ids; 94 folios dropped.

BEEKE-Parenting-zh (405 pp, CJK): global-endnotes book — 127 notes in one 注释 chapter (sec030), 50 cross-file noterefs secNNN.xhtml#fnc30-N + back-links; 32 nav sections 前言→注释 incl 第二十/二十一章 + 附录1; 4 inline crops; cover 200-DPI render. Cross-file hrefs must not double-#'d (see calibration).

Engine A/B: koreyba/Claude-Skill-pdf-to-epub was trialed on the same book and lost on TOC (3 chapters), nav, cover, title, and endnote cleanliness — not adopted. Alternatives live upstream, not in this skill's tree.