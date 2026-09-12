---
name: receipt-compiler
description: "Use when compiling phone-camera photos of receipts into an A4 PDF expense-claim pack — straighten, B&W scan look, optional cover/numbering/captions."
license: MIT
metadata:
  version: 1.0.0
  author: moonlight-lupin
  platforms: [linux]
  tags: [receipts, expense-claims, pdf, ocr, scanify]
  related_skills: [pdf, document-toolkit]
---

# Receipt Compiler

## Overview

Receipt Compiler turns a folder of phone-camera receipt photos into one A4 PDF that looks like a
photocopied expense-claim pack: each receipt is straightened (perspective warp,
deskew), converted to a B&W "scanned" look, tiled on A4 with uniform visual scale,
numbered, and summarised on an optional cover page.

Four subcommands with an enforced **confirmation gate**:

1. `scan` — straighten + scanify + OCR each photo → `manifest.json`
2. `review` — print the extracted expense table
3. `confirm` — stamp user approval + bind the reviewed data (digest)
4. `pack` — build the A4 PDF (refuses to run until `confirm` has run)

## When to Use

- "Compile my receipts into a PDF for expense claim"
- "Make a claim pack from these receipt photos"
- "Straighten and B&W these receipts and line them up on A4"
- Not for: scanning via flatbed scanner, or PDFs of invoices (use `pdf` skill).

## Prerequisites

```
pip install opencv-python-headless pillow pillow-heif pytesseract reportlab numpy
# PyMuPDF is needed only to run the self-test (tests/), not the script itself
```
Plus system `tesseract-ocr` on PATH. Check with `tesseract --version`.

## Workflow (agent must follow the gate)

### Step 1 — scan

```bash
python3 ~/.hermes/skills/productivity/receipt-compiler/scripts/receipt_compiler.py \
    scan <photos_dir> -o <workdir> [--mode bw|photo]
```

Default `--mode bw` gives the photocopy look the user asked for. Use `--mode photo`
for grayscale. Completion criterion: manifest exists with one entry per photo;
`ocr_confidence` and `needs_review` flags set.

### Step 2 — review + confirm (MANDATORY, user in the loop)

```bash
python3 .../receipt_compiler.py review <workdir>
# ... apply any corrections to manifest.json, THEN re-run review so the user
# ... sees the corrected table ...
python3 .../receipt_compiler.py review <workdir>
# ... after the user approves the corrected table ...
python3 .../receipt_compiler.py confirm <workdir>
```

Present the printed table to the user in chat. Ask:
1. Are the extracted dates/merchants/amounts right? Fix `manifest.json` fields.
2. Optional requirements — ask every time, do not assume:
   - cover page (with claimant/period/notes)
   - per-receipt numbering badges
   - per-receipt captions (date · merchant · amount)
   - currency symbol on totals
3. Exclusions — any receipt to drop (`"include": false`)?
4. Purpose/notes text for the cover.

Only after the user approves: run `confirm <workdir>`. This sets
`confirmed: true` AND binds a `review_digest` of the exact reviewed fields at
approval time. Any edit after `confirm` (dates, amounts, currency, inclusion)
makes `pack` refuse until you re-run `confirm` — which means showing the user
the changed table again. There is no bypass flag. Apply user corrections to
`manifest.json` BEFORE running `confirm`.

### Step 3 — pack

```bash
python3 .../receipt_compiler.py pack <workdir> -o claim.pdf \
    [--cover --number --captions] \
    --title "Expense Claim — <purpose>" --claimant "MH" --period "..." --notes "..."
```

Completion criterion: PDF exists, page count reported in JSON output.
Then send the PDF to the user as a document/file on the active channel.

## Layout rules (how receipts line up)

- A4 portrait, 15 mm margins, 5 mm gaps.
- Very tall receipts (aspect ≥ 2.2) are packed 3-per-row full-height;
  normal receipts 2-per-row, capped at 52% of content height (≈47% of the
  page). Scale is per-cell
  (each receipt fills its cell); rows with fewer receipts get wider cells.
- Every image is scaled to preserve aspect ratio — no distortion, no cropping.
- Receipts flow across pages; 30+ receipts pack fine.
- Tall receipts print before normal ones; re-order via the manifest if needed.

## Common Pitfalls

1. **Skipping the confirmation gate** — `pack` hard-fails on `confirmed: false`,
   non-boolean confirmation values, and post-confirmation edits (digest check).
   There is no bypass flag; the user must see the table first.
2. **Dark/shadowed photos** — the 2/98 percentile stretch handles most; if OCR
   confidence is < 55, or no amount was extracted, the entry is flagged
   `needs_review`; surface these to the user.
3. **Perspective warp failure** — glossy/wrinkled receipts may not produce a clean
   quad; the script falls back to small-angle deskew of the full frame. Check
   `method` in the manifest; if `deskew` on a receipt that clearly needs
   cropping, fix the crop manually with PIL or accept the framing.
4. **HEIC photos** — iPhone photos arrive as .heic; `pillow-heif` handles them if
   installed. If missing, ask the user for JPGs or install `pillow-heif`.
5. **Multiple currencies** — totals are grouped per currency (review output and
   cover page print one line per currency, no combined total). For a cleaner
   claim, keep one currency per pack; never zero or edit valid amounts to force
   a combined total.
6. **Long descriptions in cover table** — descriptions truncate at 70 chars; keep
   cover notes short or put detail in `notes`.

## Verification Checklist

- [ ] `scan` produced manifest.json with an entry per photo
- [ ] `review` table shown to user; corrections applied to manifest
- [ ] Optional requirements asked each time (cover/numbering/captions)
- [ ] `confirm` run only after user approval (never hand-edit `confirmed`)
- [ ] `pack` output PDF exists, page count matches expectation
- [ ] PDF sent to the user with the correct output path