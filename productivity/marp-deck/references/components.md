# Component Library

Reusable building blocks for Marp decks. Everything here is plain HTML + inline
SVG embedded in Markdown — it works because `enableHtml` is on. Read this when
you're generating content slides and want charts, dashboards, icons, or layout
patterns rather than plain bullet lists.

Adapted from marp-slides (robonuggets/marp-slides, MIT). The richest single
reference is `examples/showcase-components.md` — open it to see most of these
rendered in context.

## Table of contents
- [Images & backgrounds](#images--backgrounds)
- [Dashboard components](#dashboard-components)
- [SVG charts](#svg-charts)
- [Interactive elements](#interactive-elements)
- [Layout components](#layout-components)
- [SVG icons](#svg-icons)
- [Animations](#animations)

---

## Images & backgrounds

CRITICAL: use **relative paths only** (`./image.png`). Absolute paths break in
the VS Code preview and in export. Always pass `--allow-local-files` when
exporting (the bundled `scripts/export.sh` does this for you, along with the
`--html` flag every inline SVG and HTML component here depends on).

- Logo header (frontmatter): `header: '![w:100](./logo.png)'`
  - Hide on one slide: `<!-- _header: '' -->`
- Photo background: `![bg brightness:0.15](https://images.unsplash.com/photo-ID?w=1400)`
- Split background: `![bg right:35% brightness:0.2 blur:3px](url)` or `![bg left:30%](url)`
- CDN logos: `<img src="https://cdn.jsdelivr.net/gh/homarr-labs/dashboard-icons/png/name.png" style="width:200px;" />`
- Centered inline image: wrap in `<div style="display:flex; justify-content:center;">` with `border-radius` + `border`.

## Dashboard components

### Metric card (gradient top border)
Card with `position:relative; overflow:hidden;` and an absolutely-positioned div
at the top: `background:linear-gradient(90deg, var(--accent), transparent); height:2px;`.
Inside: icon + label + big number + trend arrow.

### Status dots
Inline SVG circles — green `#22c55e` = active, yellow `#f5a623` = learning,
red `#ef4444` = paused:
```html
<svg width="8" height="8" viewBox="0 0 8 8"><circle cx="4" cy="4" r="4" fill="#22c55e"/></svg>
```

### Verdict tags
```html
<span class="tag" style="background:#22c55e12; color:var(--green); border:1px solid #22c55e22;">Scale</span>
```
Swap colors for red (kill) / yellow (review).

### Hover rows
Wrap content in `<div class="row">` for the hover-highlight effect (the `.row`
styles live in the theme starter).

## SVG charts

Prefer charts over bare numbers, and vary chart types across slides so the deck
doesn't feel monotonous.

### Line / area chart
SVG `polyline` for the line + a `polygon` with a `linearGradient` fill for the
area beneath it. Add grid lines, a dashed target line, and circle data points.
Use `viewBox="0 0 900 240"` with `preserveAspectRatio="none"`.

### Pie / donut chart
Each segment is a separate `circle` using `stroke-dasharray` + `stroke-dashoffset`.
Math: circumference = 2·π·r. For r=110, circ ≈ 691; a segment length = (pct/100)·691.
Offsets accumulate negatively. `stroke-width` controls ring thickness. Always
`transform="rotate(-90 cx cy)"` so segments start at 12 o'clock.

### Gauge / half-circle meter
SVG `path` arc for the background + a colored value arc. A needle `line` from the
center plus a pivot `circle`. For scores 0–100. Use `stroke-linecap="round"`.

### Donut ring (single value)
One `circle` with `stroke-dasharray`. circ = 2·π·r. `offset = circ − circ·pct/100`.
For r=74, circ≈465; 89% → offset≈51.

### Sparkline (inline mini)
```html
<svg width="50" height="16"><polyline points="0,14 8,12 16,10 24,8 50,2" fill="none" stroke="#22c55e" stroke-width="1.2"/></svg>
```

### Stacked bar
A flex div with colored width-percent segments, `border-radius`, `overflow:hidden`.

### Vertical bar chart
Flex container `align-items:flex-end`. Gradient bars:
`background:linear-gradient(180deg, var(--accent), #cc5515); border-radius:3px 3px 0 0;`

### Radar / spider
SVG `polygon` for the hexagonal grid + a data shape with `fill-opacity:0.1` and a
stroke outline.

## Interactive elements

These render in the **preview and HTML export only** — PDF/PPTX flatten them.

- Collapsible: `<details><summary>Title</summary><p>Content</p></details>`
- Tooltip: `<abbr title="Full text">TERM</abbr>`
- Slider: `<input type="range" style="accent-color:var(--accent);" />`
- Checkbox: `<input type="checkbox" checked style="accent-color:var(--accent);" />`
- Progress: `<progress value="76" max="100" style="accent-color:var(--accent);"></progress>`

## Layout components

- **Before/after split** — two flex panels, `border-top` red vs green.
- **Terminal mockup** — traffic-light dots + monospace body.
- **Browser mockup** — dots + a URL-bar div.
- **Chat bubbles** — user (left) + agent (right, accent-tinted).
- **Flowchart** — boxes + SVG arrow connectors.
- **Timeline** — vertical `border-left` + dot circles.
- **Card row** — `display:flex; gap:14px;` with `flex:1` children.

## SVG icons

Wrap each in:
`<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="1.5">`
Sizes: inline = 16, cards = 44, feature = 32.

| Icon | Path / shape |
|---|---|
| Dollar | `d="M12 2v20M17 5H9.5a3.5 3.5 0 1 0 0 7h5a3.5 3.5 0 1 1 0 7H6"` |
| Heartbeat | `polyline points="22 12 18 12 15 21 9 3 6 12 2 12"` |
| Check (`#22c55e`) | `d="M22 11.08V12a10 10 0 1 1-5.93-9.14"` + `polyline points="22 4 12 14.01 9 11.01"` |
| Arrow up (`#22c55e`) | `polyline points="18 15 12 9 6 15"` |
| Arrow down (`#ef4444`) | `polyline points="18 9 12 15 6 9"` |
| X circle (`#ef4444`) | `circle cx=12 cy=12 r=10` + two crossing lines |
| Clock | `circle cx=12 cy=12 r=10` + `polyline points="12 6 12 12 16 14"` |
| Eye | `d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"` + `circle cx=12 cy=12 r=3` |
| Lightning | `d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"` |
| Warning (`#f5a623`) | triangle path |
| Search | `circle cx=11 cy=11 r=8` + line to corner |
| Users | silhouette path + circle |
| Globe | circle + horizontal line + vertical ellipse path |
| Lock | rect + arch path |
| Book | two paths for the book shape |

## Animations

HTML export + preview only. Stagger with a delay to sequence reveals.

- `float`: `translateY(0)` ↔ `-8px`
- `glow`: `box-shadow` pulse in the accent color
- `blink`: `border-color` toggle (cursors)

Example: `animation: float 4s ease-in-out 0.5s infinite;`
