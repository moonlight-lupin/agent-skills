---
name: marp-deck
description: "Use when the user asks for Marp or a deck kept as Markdown/version-controlled text, wants a .pptx rebuilt as Markdown slides, or hands over an existing Marp .md deck to change — Marp decks with slides kept as one Markdown file."
license: MIT
metadata:
  version: "2.2"
---

# Marp Deck

The deck is one `.md` file; everything else is rendered from it.

## The render command

Every render in this skill — previews, the render check, exports — is this command plus its output flags:

```bash
npx --yes @marp-team/marp-cli <deck.md> --html --allow-local-files <output flags>
```

- `--html` lets inline `<svg>` and HTML components render. Without it, every chart prints as literal markup text in PDF and PNG output.
- `--allow-local-files` resolves relative image paths.
- Output flags: `--images png` (one PNG per slide), `--pdf`, `--pptx`, `--pptx --pptx-editable`, `-o deck.html`.
- If it cannot find a browser, set `CHROME_PATH` to a Chrome/Chromium binary.

`scripts/preview.sh <dir>` (Step 2) and `scripts/export.sh <deck.md> pdf|pptx|html|all [--editable]` (Step 5) wrap this command.

## Step 0 — Route

Pick the branch, then follow only its steps:

| Branch | When | Steps |
|---|---|---|
| **New** | Topic, notes or content to turn into a deck | 1 → 2 → 3 → 4 → 5 |
| **Quick** | Vague ask ("make it look good"), low stakes, or nobody to answer questions | 1 and 2 without asking: infer the brief, pick the preset from the Quick table, state both in one line → 3 → 4 → 5 |
| **Import** | A `.pptx` to rebuild as Markdown | Import → 1 (content and length come from the file; ask purpose and density) → 2 → 3 → 4 → 5 |
| **Edit** | An existing Marp `.md` | read it; keep its frontmatter, theme and density → 3 on the requested slides only → 4 → 5 |

## Step 1 — Brief

Ask these together in one message (a structured-question UI if available):

1. **Purpose** — pitch / board or investor reporting / teaching / conference talk / internal.
2. **Length** — talk duration or slide count. Guide: 5 min ≈ 5–8 slides, 10 min ≈ 10–15, 20 min ≈ 15–25.
3. **Content** — ready / rough notes / topic only. If ready, get it; if they supply images, judge each (usable? subject? dominant colours) and plan the outline around text and images together.
4. **Density** — the deck's governing choice:
   - **Speaker-led**: one idea per slide, large type, 1–3 short lines, statement and quote slides, more slides.
   - **Reading-first**: self-contained slides, grids and tables, 4–8 bullets or 4–6 cards, annotated diagrams.

Done when all four are answered (or, on Quick, inferred and stated back in one line).

## Step 2 — Style (show, don't tell)

People recognise a look faster than they can name one, so show rendered options.

1. Read `references/themes.md`. Pick **3 genuinely different candidates** for this brief: one restrained preset, one expressive preset, one wildcard (another preset, or a custom palette block written to the variable contract). High-stakes decks: all three restrained.
2. Write each as a single-slide Marp file in `.marp-deck/previews/` (`style-a.md`, `style-b.md`, `style-c.md`): the real title slide of *this* deck — its title, subtitle, presenter, date, and the user's logo if given — dressed in that candidate's theme (Base rules + its palette block). Everything on the slide is deck content; preset names belong only in your message.
3. Render with `bash scripts/preview.sh .marp-deck/previews/`, show the PNGs, and ask which one (offer "mix elements").

Done when the user has picked. On **Quick**, take the first row that matches the audience:

| Audience / content | Preset |
|---|---|
| Finance, corporate, board | Swiss Modern or Electric Studio |
| Data, dashboards, metrics | Dark starter |
| Technical, developer | Terminal Green or Neon Cyber |
| Teaching, editorial, research | Paper & Ink or Notebook Tabs |
| Creative, event, launch | Creative Voltage or Split Pastel |

## Import (PPTX branch)

1. `python scripts/extract-pptx.py <input.pptx> <out_dir>` → `extracted-slides.json` + `assets/` (install `python-pptx` if missing).
2. Show the user each slide's title, content summary and image count; confirm before styling.
3. Continue at Step 1. In Step 3, keep all text, slide order, images (as `./assets/...`) and speaker notes (as HTML comments).

## Step 3 — Generate

Read `references/components.md`, Base rules and the chosen palette block in `references/themes.md`, and the one file in `examples/` closest to the brief (`showcase-components.md` when none is closer). That example is the quality bar for composition, spacing and density.

Outline the deck (one line per slide, sized to the Step 1 length), then write it:

- **Frontmatter**: `marp: true`, `paginate`, `size` if not 16:9, and in `style:` the Base rules block followed by the chosen palette block, both verbatim. Logo goes in `header:`.
- **Density** from Step 1 governs every slide. A slide that outgrows its density becomes two slides; type size stays put.
- **Components** earn their place over bullets: a chart instead of a bare number, metric cards, status dots, timelines, mockups. Vary chart types across the deck. Keep every `<div>`/`<svg>` block free of blank lines — a blank line ends the HTML block, and indented lines after it render as a code block.
- **One style** from first slide to last: the palette's fonts, one dominant colour, the accent reserved for data highlights, and the signature classes named in the palette's CSS comments.
- **Contrast**: the shipped palettes clear the floors in `themes.md` → Variable contract; any colour you change or add is checked against `--dark` before rendering.

Done when every slide in the outline exists in the file.

## Step 4 — Render check

Render every slide with `--images png` and look at every PNG. Fix and re-render until each slide is **clean**:

- all content sits inside the canvas — nothing cut off at the bottom or right edge (Marp clips overflow without warning);
- every chart and icon draws as a graphic, never as visible `<svg …>` text;
- no text fades into its background;
- nothing overlaps.

Done when every slide is clean. Delete the PNGs and `.marp-deck/previews/`.

## Step 5 — Deliver

1. Report file location, preset (or kept theme), slide count.
2. Offer export, with honest trade-offs:
   - **PDF** — pixel-faithful and static; email and print. Add `--pdf-notes` to carry speaker notes, `--pdf-outlines` for bookmarks.
   - **PPTX** — one image per slide, so text is not editable. `--pptx-editable` gives real text boxes, needs LibreOffice, and is less faithful to the CSS.
   - **Editable PPTX without LibreOffice** — when `--pptx-editable` fails (LibreOffice 24.2+ dropped the Impress HTML import filter), export via `officecli` instead:

     ```bash
     # Install officecli (single binary, no Office installation needed):
     curl -fsSL https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.sh | bash

     # Build the editable deck from the same Markdown source:
     python3 scripts/md2pptx-officecli.py deck.md deck-editable.pptx
     # or: bash scripts/export.sh deck.md pptx --editable  (auto-falls back to officecli)
     ```

     `md2pptx-officecli.py` parses the deck structurally — headings, bullets, numbered lists, tables, blockquotes, and simple header-tag rows (`<div class="peg-row">`-style markup becomes a small square + label) — and writes native text boxes, tables and shapes. It carries the deck's theme colours over from the `:root` variables when present, and uses neutral defaults otherwise. Fidelity is intentionally lower than the Marp render: HTML components and SVG charts become placeholder text. Treat the PDF/HTML export as the visual master and this as the editable companion.
   - **Full-fidelity editable decks** — for house-style decks with signature components (numbered tags, callouts, accent bands), build the PPTX directly with officecli commands (`officecli create`, `add`, `batch` — see `officecli help pptx`). This is the route used when a brand system must survive into the editable file; it needs a per-deck builder script.
   - **HTML** — the only format that keeps animations, `<details>`, and `*` fragment reveals.
3. To edit by hand: VS Code with "Marp for VS Code", settings `markdown.marp.enableHtml: true` and `markdown.marp.allowLocalFiles: true`. Colours live in the `:root`/`section` variables, fonts in the `@import`.

## Marp syntax reference

The parts that differ from plain Markdown:

- **Slides** split on `---`. Canvas 1280×720 by default; `size: 4:3` gives 960×720.
- **Directives**: global in frontmatter; `<!-- key: value -->` applies from this slide onward; the `_` prefix (`<!-- _class: lead -->`, `<!-- _paginate: false -->`, `<!-- _header: '' -->`, `<!-- _backgroundColor: #111 -->`) applies to this slide only.
- **Slide-only CSS**: `<style scoped>…</style>` inside the slide.
- **Fitted headline**: `# <!-- fit --> Big statement` scales the heading to the slide width — made for speaker-led statement slides.
- **Fragments**: `*` bullets (instead of `-`) reveal one at a time in HTML presentation mode.
- **Speaker notes**: any HTML comment that is not a directive.
- **Images**: `![w:600](./x.png)` sizes inline; `![bg](./x.png)` fills the slide (`fit`, `cover`, `contain`, or `80%`); `![bg left:40%](./x.png)` splits the slide and leaves the rest for text; several `![bg]` lines tile side by side, and `![bg vertical]` on the first stacks them. Filters chain in the same brackets: `brightness:0.4 blur:4px grayscale sepia contrast:1.2 saturate:1.5 opacity:0.5`. Paths are always relative (`./`).
- **Page numbers in CSS**: `section::after { content: attr(data-marpit-pagination) ' / ' attr(data-marpit-pagination-total); }`.
- **Full-slide decorations**: draw them as extra `background` layers on `section`; a `section::before` stretched by `top`/`bottom` insets renders at zero height.
- **Negating a CSS function**: `calc(-1 * clamp(...))` — a bare `-clamp(...)` is silently dropped.
