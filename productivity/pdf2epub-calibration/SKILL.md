---
name: pdf2epub-calibration
description: "Use when a converted PDF→EPUB misclassifies lines or covers, e.g. 'footnote links broken', 'page numbers became endnotes', 'cover came out as texture fragment', 'chapter headings resolve to wrong pages', 'endnote links dangle'. Calibration threshold rules for the pdf2epub pipeline: folio/fnref/footnote classification, endnote-section books, caption handling, front-matter language."
license: MIT
metadata:
  version: 1.2.1
  author: moonlight-lupin
  platforms: [linux]
  hermes:
    tags: ['pdf', 'epub', 'calibration', 'font-classification']
    related_skills: ['pdf2epub']
---

# PDF→EPUB Classifier Calibration

## When to Use

- A converted EPUB has citations in body text, page numbers as phantom endnotes, or broken/duplicate footnote links
- Chapter headings resolve to wrong PDF pages
- The cover image comes out as a texture fragment or a naked photo without typography

## Span-merge reality (check the dump, not the flag)

- `page.get_text("dict")` gives lines whose spans merge text at different font sizes. A body line can contain a 5pt footnote-ref span inside 12pt text — text extraction sees ONE line at the max span size.
- Superscript flags are unreliable: several authoring tools (QuarkXPress-style CJK exports included) emit footnote refs as STANDALONE 6pt lines with the sup flag UNSET, and emit the note's own number as a leading 5pt span merged into the note's first line. Gate ref detection on size + position, never on the sup flag alone.
- Before changing any threshold, dump per-page lines with text/size/flags/y-ratio. Most classification misses are span-merge artifacts, not wrong thresholds.

## Classification order and thresholds (validated values)

1. FOLIO first: bare 1-4 digit (or roman i-vi) number, font < 0.85*body, y > 0.90. Rules run in order; if the footnote rule runs before the folio rule, page numbers become phantom notes.
2. FNREF: whole line is a bare digit, font < 0.75*body, any y.
3. FOOTNOTE: font < 0.92*body, y > 0.60, not a list marker. Long note blocks climb to 2/3 page height — a fixed 'footnotes below 80%' y-cut loses note starts. Use the largest threshold that still excludes body text.
4. BODY: everything else.
5. Body font size is LEARNED (2-char-mode of line sizes), never hard-coded. Books legitimately differ.

## Footnote block grouping

- A note starts at a line whose first token is a bare digit followed by body text; bare-digit strays are dropped. Continuations attach unconditionally to the previous block.
- Per-chapter note numbering restarts are normal in books — scope anchor ids by chapter or duplicate ids fail the link check.
- Glued CJK note numbers need a monotonic matcher (see Endnotes-section books below), not a whitespace-required regex.

## Printed-TOC page resolution (probes)

- Never probe with a fixed `title[:16]` slice against `clean()` page text: CJK chapter titles break across lines (the body page inserts a space/newline mid-title), the TOC may spell 章一 (Chinese numerals) while the body prints 20 (digits), and 2-char titles like 注释 fall under any ≥4-char filter. Probe instead against whitespace-COLLAPSED page text with title variants: full title de-spaced, title without the leading 第N章/部分/Part marker, and accept probes ≥2 chars.
- The probe's own match window (printed-3 … printed+40) REACHES THE TOC PAGES for early chapters — a chapter title matches its own TOC line and the section resolves to the TOC page itself. Pass the TOC-run page indexes as an exclusion set to the resolver.
- Trust the actual matched page over majority-offset arithmetic per entry; same-page sections (part title + chapter 1 sharing a start page) are LEGITIMATE output — a seen-set on page alone (or a strictly-increasing idx guard) silently drops chapter entries whose printed page equals their part title's.
- Probe order matters: try the FULL stripped title as a standalone short line (≤34 chars, per-line whitespace-collapsed) across the whole window FIRST, then loose variants (title minus chapter marker, prefix cut at '·' for parenthetical insertions), then whole-page substring. A mid-sentence body fragment of a 2-3 word title matches earlier pages than the real heading and wins the substring pass — probe the full title first to starve that false positive. Lines keep internal spaces ('第十三章 预防性管教' does not contain '第十三章预防性管教') — collapse whitespace INSIDE each line, not just page-wide.

## Verification loops

- Link check: for every xhtml, the set of `href="#fn..."` targets must equal the set of `id="fn..."` anchors; no duplicates. With endnote chapters the check must also handle `secNNN.xhtml#anchor` cross-file forms (resolve the referenced file from the zip and match the id inside it). Re-run after EVERY classifier change.
- Chapter-count sanity against the printed TOC: sections == number of non-roman TOC entries. A silent drop (probe miss, dedupe) shows up as a missing chapter in nav — diff nav titles against the entry list before accepting a build.
- Whole-section figures: a chapter can render with 0 `<figure>` refs while the zip contains the images — images extracted into `imgs_by_page` must have EVERY consuming render path (front-matter section included) append them; the front-matter render path bypasses the chapter `render_pages` helper.
- One threshold change per iteration, against the span dump. Debug script shape: classify → group → report dups/missing → dump the suspect page's raw lines. Run the resolution stage standalone (`parse_printed_toc_run` → `resolve_printed_toc`) and eyeball the (title, idx) tuples when nav looks wrong.

## Cover extraction

- Extracting the largest page-1 image is safe ONLY when it is the SOLE image and covers ≥ 85% of the page area. Composite covers (full-bleed texture + framed photo + paint-op typography) exist only as the rendered composite — render the page at 200 DPI in every other case.

## Inline illustration crops

- Extract body figures as RENDERED page-surface crops (`page.get_pixmap(matrix=Matrix(dpi/72), clip=bbox)` from `get_image_info()` geometry), never raw xref XObjects — composed/vector art and CMYK/mask oddities yield fragments or color-broken extractions; the rendered surface always matches what the reader saw. Geometry from PDF structure keeps the pipeline deterministic; no AI layout model needed.
- Filter ≥ 3% page area (drops icons/logos), drop < 2 KB crops (blank/noise), dedup by pixel sha256 (books reuse identical art), skip the cover region, normalize RGBA→RGB on white, LANCZOS cap 1600 px, JPEG q85.
- Page-margin caption text sitting on a figure's top edge bleeds into the crop and appears clipped (its line bbox overlaps the clip's top strip). Fix: shrink the clip top below the y1 of any text line overlapping the top strip — and guard for pages with NO figure in the same loop, or the fix crashes on plain-text pages (image_info() returns an empty list, indexing [0] raises IndexError).
- Caption text that appears CLIPPED at a figure crop's top edge (mid-letter cuts, typeset italic unlike the art) is usually part of the publisher's raster asset, not page bleed. Verify against PDF text-line intersection with the image bbox: no overlap = caption lives inside the image = ship it. Do not raise the crop line further — you will amputate real art.
- Verify by vision-checking the LARGEST and one mid-book crop per book, checking panel borders intact and no clipped margin text at edges.

## Common Pitfalls

- ebooklib's default `epub3_pages: True` builds a nav `page-list` from EVERY element carrying both `epub:type` and an id — noteref anchors qualify, so a notes-heavy book grows a hidden "Pages" nav listing 50+ raw anchor ids (`refc2-4`, `reffront-1`). Some readers surface that hidden nav as a second TOC page. Fix: `epub.write_epub(path, book, {"epub3_pages": False})` — pdf2epub never emits a real page map, so the list is garbage in every build.
- Spine + cross-file href defects validated in the reader only: a lenient reader and the zip-level link check both passed while Kobo still failed per-chapter. Strict-reader validation (Kobo device or epubcheck) belongs in the verification loop.
- Fixing a bleed by shrinking the clip top needs the no-figure-page guard — plain-text pages crash on `image_info()[0]` indexing otherwise.
- Do not remove clipped captions by cutting higher: verify against PDF text-line intersection first; captions inside the raster asset ship with the art.
- Resolution regressions cascade: dropping one TOC entry (e.g. 注释) also drops the endnote-section detection, which reclassifies all notes to BODY and kills every anchor — a nav-title diff against the TOC entry list catches it in one step, a link check alone shows only the dangling-ref symptom.

## Endnotes-section books (notes on their own pages)

- Two footnote architectures exist. Bottom-of-page footnotes: per-chapter numbering, the classic y > 0.60 path. Global endnotes: ONE 注释/Notes chapter near the book's end, numbering GLOBAL and continuous (e.g. 1..127 across all chapters), notes at small font from the very TOP of dedicated pages — the y > 0.60 cut classifies them BODY, so nearly all note blocks vanish and nearly all refs dangle.
- Fix: resolve sections BEFORE line classification, pass the endnote section's page range into the classifier, and drop the y-test on those pages. TOC parsing needs no classified lines, so the reorder is safe.
- TOC parse must read the WHOLE TOC RUN (continue while consecutive pages yield dot-leader entries). A single-page parse loses trailing entries (appendices, notes) and dumps every trailing PDF page into the last chapter.
- Glued note numbers: endnote entries may merge the number into the text with no space (`1查尔斯…`). Group blocks with a monotonic expected-number matcher: a block starts only when its leading number equals prev+1 or 1; anything else (dates like 1996, page cites) attaches as continuation. A regex that accepts any leading digits as a start re-splits on dates.
- Cross-file anchors: with the notes chapter on its own spine file, a same-document `#id` href does NOT navigate between files. Forward refs emit `sec{NNN}.xhtml#fn...`; the notes chapter's `[n]` back-links emit `sec{NNN}.xhtml#refc{N}-{num}` for the citing section (first citation wins; no citing ref → plain text). Link check must cover both directions and both forms.
- Cross-file hrefs must NOT get another '#' prepended: `href="#sec030.xhtml#fnc30-4"` is a same-document fragment pointing at an id that exists nowhere — a href-template `#{tgt}` blind-prepends it. Route every inline anchor through one helper that prepends '#' only when the target lacks `.xhtml#`. (epubcheck-style same-file link checks can miss this: the checker resolves `#{file}#{id}` as an internal fragment and fails only on 'fragment id not found'.)
- Spine entries must be MANIFEST IDS, never href strings: `book.spine = [...] + [c.file_name]` writes `<itemref idref="sec002.xhtml"/>` — an idref pointing at no manifest id. ebooklib accepts it silently, nav still works in lenient readers, but Kobo errors per chapter ('EPUB/sec002.xhtml does not exist in this book') and other strict readers drop the whole book. Spine by `c.id` ('chapter_N'), then verify every `<itemref idref>` exists in the manifest — nav working in one reader is NOT evidence the spine is valid.

## Language of generated labels

- Never hard-code a language's label in the conversion path — the pre-chapter front-matter title must follow the --lang flag (前言 for zh, Front Matter for en), and the section ships only when its rendered part list is non-empty (an otherwise-empty front section renders as a bare h1).

## Verification Checklist

- [ ] Link check PASS (script in pdf2epub SKILL.md): 0 missing targets, 0 duplicate ids, both href forms (same-file + `secNNN.xhtml#`)
- [ ] `<itemref idref>` spine check: every idref exists in the manifest (Kobo-style strict-reader failure mode)
- [ ] nav.xhtml: no `page-list` block, no raw `refc`/`reffront` ids in TOC entries
- [ ] nav titles diff against the printed-TOC entry list: every entry present, no stubs (<2000-char non-divider chapters)
- [ ] 127-note-style anchors: note-block count == anchor count == expected total
- [ ] Done when: all above green AND at least one strict-reader target opens the book (Kobo device, or epubcheck clean)