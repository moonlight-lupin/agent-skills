# marp-deck

A Claude skill for building presentations where **Markdown is the single source
of truth**. It pairs a guided authoring workflow with a rich component library
and native export to PDF, PPTX, and HTML — all from one `.md` file.

## What it does

- **Guided workflow** — routes between a new deck, a quick deck (infers the
  brief when you just say "make it look good"), a PowerPoint import, or an
  edit; asks about purpose, length, and content density; generates; then
  renders every slide to PNG and checks it before delivery.
- **"Show, don't tell" style discovery** — instead of asking you to describe a
  look, it renders 3 candidate themes as preview images so you pick what you can
  actually see.
- **PowerPoint import** — extracts text, images, and speaker notes from a
  `.pptx` and rebuilds it as an editable Marp deck.
- **Component library** — SVG charts (line/area, pie/donut, gauge, radar,
  sparkline, bars), dashboard cards, status indicators, timelines, mockups, 16+
  icons, and 14 ready-to-paste themes (2 starters + 12 presets) on one shared
  base stylesheet and variable contract, each checked for text contrast.
- **Native export** — `marp-cli` to PDF (static), HTML (keeps animations and
  interactivity), or PPTX (image-per-slide, or editable shapes via LibreOffice
  or the bundled officecli fallback).

## Why Markdown source

One `.md` file is diff-able, reviewable, version-controllable, and hand-editable.
Marp renders it to HTML/CSS internally and exports from there — so you keep a
clean text source and still ship PowerPoint and PDF.

## Layout

```
marp-deck/
├── SKILL.md                     # the workflow + rules (entry point)
├── references/
│   ├── components.md            # charts, dashboards, icons, layouts
│   └── themes.md                # base rules, variable contract, 2 starters + 12 presets
├── scripts/
│   ├── extract-pptx.py          # PPTX → JSON + extracted images
│   ├── preview.sh               # render style previews to PNG
│   ├── export.sh                # deck.md → PDF / PPTX / HTML
│   └── md2pptx-officecli.py     # editable PPTX via officecli (no-LibreOffice fallback)
├── examples/                    # reference decks (the quality bar)
└── tests/                       # maintainer tests (not loaded by the skill)
```

## Requirements

- VS Code + "Marp for VS Code" (with `enableHtml` + `allowLocalFiles`) for
  hand editing. Every render passes `--html`; without it marp-cli prints
  inline `<svg>` charts as literal text.
- Node.js for export (`marp-cli` is fetched via `npx`).
- Python + `python-pptx` for PowerPoint import.
- LibreOffice (optional) for editable PPTX export. On machines where
  `--pptx-editable` fails (LibreOffice 24.2+ removed the Impress HTML import
  filter), `scripts/md2pptx-officecli.py` builds the editable PPTX with
  [officecli](https://github.com/iOfficeAI/OfficeCLI) instead — install it with
  `curl -fsSL https://raw.githubusercontent.com/iOfficeAI/OfficeCLI/main/install.sh | bash`,
  or read the [release notes](https://github.com/iOfficeAI/OfficeCLI/releases)
  for other install routes. `export.sh --editable` falls back to it
  automatically.

## Credits

marp-deck builds on three MIT-licensed open-source skills. It
would not exist without them:

- **[marp-slides](https://github.com/robonuggets/marp-slides)** by
  **robonuggets** — the Marp Markdown engine, the SVG chart / dashboard / icon
  component library, the tested font pairings, the dark/light theme starters, the
  example decks, and the `marp-cli` export pipeline.
- **[frontend-slides](https://github.com/zarazhangrui/frontend-slides)** by
  **Zara Zhang** — the phase-based workflow, the "show, don't tell" style
  discovery approach, the content-density model, the PowerPoint extraction
  script, and the named style presets (ported here into Marp CSS).
- **[marp-slide](https://github.com/softaworks/agent-toolkit/tree/main/skills/marp-slide)**
  in softaworks/agent-toolkit (MIT) — the quick path for vague requests,
  slide-count guidance, contrast floors, and the Marp syntax reference
  (fitted headings, fragments, speaker-note export, image splits and filters),
  each re-verified against marp-cli before inclusion.

What marp-deck adds is the synthesis: keeping Markdown as the source of truth
(from marp-slides) while adopting the discovery-driven workflow and PPT import
(from frontend-slides), with the presets re-expressed as Marp themes and the
style-preview step rendered through `marp-cli`.

See [LICENSE](LICENSE) for the full notices.

## Maintainer tests

```bash
python3 tests/test_themes.py     # every theme: contract variables + contrast floors
bash tests/test_scripts.sh       # export/preview scripts render inline SVG
bash tests/render_presets.sh     # renders a sample deck in every theme -> tests/renders/
```

Needs Node (npx), Python 3 and `pdftotext`; set `CHROME_PATH` if marp-cli can't find a browser.

## License

MIT — see [LICENSE](LICENSE). Incorporates MIT-licensed material from both
upstream projects, whose copyright notices are retained there.
