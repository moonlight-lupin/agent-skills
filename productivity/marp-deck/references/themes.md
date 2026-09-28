# Themes & Style Presets

How to dress a Marp deck. Every theme is two CSS blocks pasted into the deck's
frontmatter `style:` in this order: **Base rules**, then **one palette block**
(a starter or a preset). Base carries the structure (type scale, tables, cards,
pagination); the palette block carries fonts, colours and the signature device.

Sources: the starters and tested font pairings come from marp-slides
(robonuggets/marp-slides, MIT); the 12 presets are ported from frontend-slides
(zarazhangrui/frontend-slides, MIT) and re-expressed as Marp CSS.

## Table of contents
- [Variable contract](#variable-contract)
- [Base rules](#base-rules)
- [Dark starter (default)](#dark-starter-default)
- [Light starter](#light-starter)
- [Heading hierarchy](#heading-hierarchy)
- [Tested font pairings](#tested-font-pairings)
- [The 12 presets](#the-12-presets)
- [Aim for](#aim-for)

---

## Variable contract

Every palette block defines these, so components (`references/components.md`)
work under any theme. Names are roles, not literal colours:

| Variable | Role | Contrast floor against `--dark` |
|---|---|---|
| `--dark` | the surface text sits on | — |
| `--light` | headings, big numbers | 4.5:1 |
| `--body` | body text (also ≥ 4.5:1 on `--card`) | 4.5:1 |
| `--label`, `--muted` | labels, captions, subtitles | 3:1 |
| `--accent`, `--accent-hover` | highlights, rules, `strong` | 3:1 (accent) |
| `--card`, `--border` | card fill and hairlines | — |
| `--green`, `--red`, `--yellow` | status | — |
| `--font-head`, `--font-body`, `--head-weight`, `--body-weight` | type | — |

When you customise a palette, keep those floors: check each changed text
colour against `--dark` before rendering.

## Base rules

```css
section { background: var(--dark); color: var(--body); font-family: var(--font-body); font-weight: var(--body-weight); font-size: 26px; line-height: 1.5; padding: 60px 80px; }
h1, h2, h3 { font-family: var(--font-head); border: none; padding: 0; margin: 0 0 0.3em; line-height: 1.12; }
h1 { font-size: 2.1em; font-weight: var(--head-weight); color: var(--light); letter-spacing: -0.02em; }
h2 { font-family: var(--font-body); font-size: 1.05em; font-weight: var(--body-weight); color: var(--muted); }
h3 { font-size: 0.6em; font-weight: 700; color: var(--label); text-transform: uppercase; letter-spacing: 0.18em; margin-bottom: 0.6em; }
p, li { color: var(--body); }
strong { color: var(--accent); font-weight: 600; }
a { color: var(--accent); }
section.lead { display: flex; flex-direction: column; justify-content: center; }
section.lead h1 { font-size: 3em; }
section.lead h2 { font-size: 1.15em; }
header, footer { color: var(--label); font-size: 0.55em; }
header { text-align: right; } header img { margin: 0; }
section::after { color: var(--label); font-size: 0.55em; font-family: var(--font-body); }
table { border-collapse: collapse; width: 100%; font-size: 0.72em; border: none; }
table thead, table tbody { border: none; }
table tr { background: transparent !important; }
table th, table td { border: none; border-bottom: 1px solid var(--border); padding: 8px 14px; text-align: left; color: var(--body); background: transparent; }
table th { color: var(--label); font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em; font-size: 0.8em; border-bottom: 2px solid var(--accent); }
blockquote { border-left: 3px solid var(--accent); background: var(--card); color: var(--body); padding: 14px 22px; margin: 0.8em 0; font-style: italic; }
blockquote::before, blockquote::after { content: none; }
code { background: var(--card); color: var(--accent); border-radius: 4px; padding: 0.1em 0.35em; }
pre { background: var(--card); border: 1px solid var(--border); border-radius: 8px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; }
.tag { font-family: var(--font-head); font-weight: 600; font-size: 0.55em; letter-spacing: 0.12em; text-transform: uppercase; padding: 3px 10px; border-radius: 4px; }
.row { transition: background 0.2s; border-radius: 6px; } .row:hover { background: var(--card); }
details { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 18px; margin-top: 8px; }
details summary { color: var(--accent); font-family: var(--font-head); font-weight: 600; font-size: 0.8em; cursor: pointer; }
abbr { text-decoration: none; border-bottom: 1px dotted var(--muted); cursor: help; }
```

## Dark starter (default)

Outfit 800 headings, Raleway 200 body. Dashboard and data decks.

```css
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;700;800&family=Raleway:wght@100;200;300&display=swap');
:root {
  --accent: #ff6b1a; --accent-hover: #ff8c4a;
  --dark: #000000; --card: #0a0a0a; --border: #1c1c1c;
  --body: #a3a3a3; --label: #7a7a7a; --muted: #8a8a8a; --light: #ffffff;
  --green: #22c55e; --red: #ef4444; --yellow: #f5a623;
  --font-head: 'Outfit', sans-serif; --font-body: 'Raleway', sans-serif; --head-weight: 800; --body-weight: 200;
}
h2 { font-weight: 100; }
strong { font-weight: 300; }
```

## Light starter

Space Grotesk 700 headings, IBM Plex Mono 300 body. Light, travel, product decks.

```css
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600;700&family=IBM+Plex+Mono:wght@300;400&display=swap');
:root {
  --accent: #2563eb; --accent-hover: #1d4ed8;
  --dark: #fafafa; --card: #ffffff; --border: #e5e5e5;
  --body: #4a4a4a; --label: #737373; --muted: #7a7a7a; --light: #1a1a1a;
  --green: #16a34a; --red: #dc2626; --yellow: #b45309;
  --font-head: 'Space Grotesk', sans-serif; --font-body: 'IBM Plex Mono', monospace; --head-weight: 700; --body-weight: 300;
}
section { font-size: 24px; }
```

## Heading hierarchy
- `h1` = slide title (largest; bigger still on `lead` slides)
- `h2` = subtitle under the title (body font, thin, muted)
- `h3` = section label above the title (small, uppercase, letter-spaced)

## Tested font pairings

| Heading | Body | Use |
|---|---|---|
| Outfit 800 | Raleway 100 | Dashboard / data (default) |
| DM Serif Display | DM Sans 300 | Recipes, editorial |
| Space Grotesk 700 | IBM Plex Mono 300 | Travel, light themes |
| Sora 700 | Sora 200 | Product comparisons |
| Urbanist 800 | Urbanist 100 | Music, Spotify-style |
| Plus Jakarta Sans 800 | Plus Jakarta Sans 200 | Retros, team decks |

## The 12 presets

Each preset is a palette block: paste it after Base rules. The first line under
each heading is the brief (mood, fonts, signature device) you pick from in
style discovery; the CSS implements it. Presets that need extra markup for their
signature device name the class in a CSS comment.

### Dark

### 1. Bold Signal
Confident, high-impact. Archivo Black + Space Grotesk; charcoal gradient, one orange focal card, big section numbers, breadcrumb header.

```css
@import url('https://fonts.googleapis.com/css2?family=Archivo+Black&family=Space+Grotesk:wght@300;400;600;700&display=swap');
:root {
  --accent: #ff5722; --accent-hover: #ff7a50;
  --dark: #1a1a1a; --card: #262626; --border: #383838;
  --body: #d4d4d4; --label: #9e9e9e; --muted: #a8a8a8; --light: #ffffff;
  --green: #4ade80; --red: #f87171; --yellow: #fbbf24;
  --font-head: 'Archivo Black', sans-serif; --font-body: 'Space Grotesk', sans-serif; --head-weight: 400; --body-weight: 400;
}
section { background: linear-gradient(135deg, #1a1a1a 0%, #2d2d2d 100%); }
h1 { text-transform: uppercase; letter-spacing: -0.01em; }
h3 { color: var(--accent); }
header { text-align: left; text-transform: uppercase; letter-spacing: 0.2em; }
/* Signature: <div class="card focus"> for the one focal card; <div class="num">01</div> for section numbers */
.card.focus { background: var(--accent); border-color: var(--accent); }
.card.focus, .card.focus * { color: #1a1a1a !important; }
.num { font-family: var(--font-head); font-size: 4.5em; line-height: 1; color: var(--accent); }
```

### 2. Electric Studio
Clean, high-contrast. Manrope 800/400; near-black with electric-blue accent edge bar, two-panel split, quote as hero.

```css
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;800&display=swap');
:root {
  --accent: #4361ee; --accent-hover: #6b83f2;
  --dark: #0a0a0a; --card: #151515; --border: #2a2a2a;
  --body: #c9c9c9; --label: #8f8f8f; --muted: #9a9a9a; --light: #ffffff;
  --green: #22c55e; --red: #ef4444; --yellow: #f5a623;
  --font-head: 'Manrope', sans-serif; --font-body: 'Manrope', sans-serif; --head-weight: 800; --body-weight: 400;
}
section { background: linear-gradient(var(--accent), var(--accent)) left top / 12px 100% no-repeat, var(--dark); }
strong { color: #8ea0f5; }
blockquote { font-style: normal; font-size: 1.5em; font-weight: 800; line-height: 1.25; color: var(--light); background: transparent; border-left-width: 6px; }
/* Signature: <div class="split"><div>…</div><div class="panel">…</div></div> for the two-panel layout */
.split { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; align-items: center; }
.panel { background: #ffffff; border-radius: 12px; padding: 28px; }
.panel, .panel * { color: #0a0a0a !important; }
```

### 3. Creative Voltage
Energetic, retro-modern. Syne 700/800 + Space Mono; midnight slides, electric-blue halftone title slides, neon badges.

```css
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=Space+Mono:wght@400;700&display=swap');
:root {
  --accent: #d4ff00; --accent-hover: #e4ff5c;
  --dark: #1a1a2e; --card: #24244a; --border: #34345e;
  --body: #dcdcf0; --label: #a3a3c8; --muted: #a9a9cc; --light: #ffffff;
  --green: #4ade80; --red: #ff6b8a; --yellow: #ffd23f;
  --font-head: 'Syne', sans-serif; --font-body: 'Space Mono', monospace; --head-weight: 800; --body-weight: 400;
}
section { font-size: 23px; background: radial-gradient(circle, rgba(255,255,255,0.07) 1.5px, transparent 2px) 0 0 / 18px 18px, var(--dark); }
section.lead { background: radial-gradient(circle, rgba(255,255,255,0.18) 2px, transparent 2.5px) 0 0 / 16px 16px, #0066ff; }
section.lead h1, section.lead h2, section.lead h3 { color: #ffffff; }
h3 { color: var(--accent); }
/* Signature: <span class="badge">NEW</span> for neon badges */
.badge { background: var(--accent); color: #1a1a2e; font-family: var(--font-body); font-weight: 700; font-size: 0.6em; padding: 4px 12px; border-radius: 999px; text-transform: uppercase; }
```

### 4. Dark Botanical
Elegant, premium. Cormorant italic headings + IBM Plex Sans; warm dark with blurred overlapping gradient circles (abstract shapes only).

```css
@import url('https://fonts.googleapis.com/css2?family=Cormorant:ital,wght@0,500;1,500;1,600&family=IBM+Plex+Sans:wght@300;400;500&display=swap');
:root {
  --accent: #d4a574; --accent-hover: #e8b4b8;
  --dark: #0f0f0f; --card: #1a1918; --border: #2e2b28;
  --body: #cfc9c1; --label: #a39e97; --muted: #aaa39b; --light: #e8e4df;
  --green: #9cc5a1; --red: #e8a0a0; --yellow: #c9b896;
  --font-head: 'Cormorant', serif; --font-body: 'IBM Plex Sans', sans-serif; --head-weight: 600; --body-weight: 300;
}
section { background:
  radial-gradient(circle at 88% 18%, rgba(212,165,116,0.22) 0, transparent 26%),
  radial-gradient(circle at 78% 34%, rgba(232,180,184,0.16) 0, transparent 22%),
  radial-gradient(circle at 94% 42%, rgba(201,184,150,0.14) 0, transparent 18%),
  var(--dark); }
h1 { font-style: italic; font-size: 2.5em; letter-spacing: 0; }
section.lead h1 { font-size: 3.6em; }
h3 { color: var(--accent); }
```

### Light

### 5. Notebook Tabs
Editorial, tactile. Bodoni Moda + DM Sans; cream paper on a charcoal desk, binder holes left, coloured section tabs on the right edge.

```css
@import url('https://fonts.googleapis.com/css2?family=Bodoni+Moda:wght@500;700&family=DM+Sans:wght@400;500;700&display=swap');
:root {
  --accent: #b5475d; --accent-hover: #cf6a7e;
  --dark: #f8f6f1; --card: #ffffff; --border: #e4dfd5;
  --body: #3a3a3a; --label: #6b6660; --muted: #726c65; --light: #1f1f1f;
  --green: #2f855a; --red: #c53030; --yellow: #b7791f;
  --font-head: 'Bodoni Moda', serif; --font-body: 'DM Sans', sans-serif; --head-weight: 700; --body-weight: 400;
}
section { padding: 70px 130px 70px 110px; background:
  radial-gradient(circle, #2d2d2d 8px, transparent 9px) 36px 20px / 32px 96px repeat-y,
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Crect width='100%25' height='100%25' rx='6' fill='%23f8f6f1'/%3E%3C/svg%3E") 26px 26px / calc(100% - 76px) calc(100% - 52px) no-repeat,
  linear-gradient(rgba(0,0,0,0.35), rgba(0,0,0,0.35)) 32px 36px / calc(100% - 76px) calc(100% - 52px) no-repeat,
  linear-gradient(#a8e6cf, #a8e6cf) right 14px top 90px / 44px 64px no-repeat,
  linear-gradient(#cdb4f0, #cdb4f0) right 14px top 164px / 44px 64px no-repeat,
  linear-gradient(#f7b7c8, #f7b7c8) right 14px top 238px / 44px 64px no-repeat,
  linear-gradient(#a7d3f5, #a7d3f5) right 14px top 312px / 44px 64px no-repeat,
  linear-gradient(#f3e3b0, #f3e3b0) right 14px top 386px / 44px 64px no-repeat,
  #2d2d2d; }
section::after { right: 80px; bottom: 44px; }
header { right: 80px; top: 40px; }
```

### 6. Pastel Geometry
Friendly, approachable. Plus Jakarta Sans 700/800; soft-blue backdrop, rounded cream card, five pastel pills (short→tall→short) on the right edge.

```css
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;700;800&display=swap');
:root {
  --accent: #6d4fc2; --accent-hover: #8a70d6;
  --dark: #faf9f7; --card: #eef3f7; --border: #dde3e8;
  --body: #3d4852; --label: #66717c; --muted: #6c7782; --light: #1e2a36;
  --green: #2f855a; --red: #c53030; --yellow: #b7791f;
  --font-head: 'Plus Jakarta Sans', sans-serif; --font-body: 'Plus Jakarta Sans', sans-serif; --head-weight: 800; --body-weight: 400;
}
section { padding: 70px 270px 70px 90px; background:
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='330'%3E%3Crect y='110' width='28' height='110' rx='14' fill='%23f7b7c8'/%3E%3C/svg%3E") right 188px center / 28px 330px no-repeat,
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='330'%3E%3Crect y='60' width='28' height='210' rx='14' fill='%23b8e0d2'/%3E%3C/svg%3E") right 148px center / 28px 330px no-repeat,
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='330'%3E%3Crect y='0' width='28' height='330' rx='14' fill='%23c5d8b5'/%3E%3C/svg%3E") right 108px center / 28px 330px no-repeat,
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='330'%3E%3Crect y='60' width='28' height='210' rx='14' fill='%23d9c9f0'/%3E%3C/svg%3E") right 68px center / 28px 330px no-repeat,
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='330'%3E%3Crect y='110' width='28' height='110' rx='14' fill='%23a78bdb'/%3E%3C/svg%3E") right 28px center / 28px 330px no-repeat,
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Crect width='100%25' height='100%25' rx='28' fill='%23faf9f7'/%3E%3C/svg%3E") 36px 36px / calc(100% - 272px) calc(100% - 72px) no-repeat,
  #c8d9e6; }
section::after { right: 262px; bottom: 54px; }
.card { border-radius: 18px; border: none; }
```

### 7. Split Pastel
Playful, creative. Outfit 700/800; peach ⟋ lavender vertical split, grid overlay on the lavender panel, badge pills.

```css
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;700;800&display=swap');
:root {
  --accent: #b4386b; --accent-hover: #cf5a8a;
  --dark: #e4dff0; --card: #fbf8f6; --border: #d6cde3;
  --body: #3b3346; --label: #635a6e; --muted: #675e72; --light: #221c2b;
  --green: #2f855a; --red: #c53030; --yellow: #a16207;
  --font-head: 'Outfit', sans-serif; --font-body: 'Outfit', sans-serif; --head-weight: 800; --body-weight: 400;
}
section { background:
  repeating-linear-gradient(0deg, rgba(60,40,90,0.08) 0 1px, transparent 1px 32px) right top / 45% 100% no-repeat,
  repeating-linear-gradient(90deg, rgba(60,40,90,0.08) 0 1px, transparent 1px 32px) right top / 45% 100% no-repeat,
  linear-gradient(90deg, #f5e6dc 55%, #e4dff0 55%); }
/* Signature: <span class="pill mint">…</span> (mint | yellow | pink) for badge pills */
.pill { display: inline-block; font-weight: 700; font-size: 0.6em; padding: 5px 14px; border-radius: 999px; color: #221c2b; background: #fff; }
.pill.mint { background: #b8e0d2; } .pill.yellow { background: #f6e39a; } .pill.pink { background: #f7b7c8; }
```

### 8. Vintage Editorial
Witty, personality-driven. Fraunces 700/900 + Work Sans; cream page, geometric corner mark (circle outline + line + dot), bold bordered CTA boxes.

```css
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,700;9..144,900&family=Work+Sans:wght@400;500;600&display=swap');
:root {
  --accent: #a0522d; --accent-hover: #c06a3e;
  --dark: #f5f3ee; --card: #efe3d6; --border: #d9cbbb;
  --body: #3a342d; --label: #6e665c; --muted: #71685e; --light: #1c1a17;
  --green: #2f6f4e; --red: #b23a2e; --yellow: #9a6b12;
  --font-head: 'Fraunces', serif; --font-body: 'Work Sans', sans-serif; --head-weight: 900; --body-weight: 400;
}
section { background:
  url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='160'%3E%3Ccircle cx='150' cy='70' r='52' fill='none' stroke='%231c1a17' stroke-width='3'/%3E%3Cline x1='20' y1='140' x2='200' y2='140' stroke='%231c1a17' stroke-width='3'/%3E%3Ccircle cx='60' cy='70' r='10' fill='%23a0522d'/%3E%3C/svg%3E") right 50px top 40px / 220px 160px no-repeat,
  var(--dark); }
h1 { letter-spacing: -0.03em; }
/* Signature: <div class="cta">…</div> for bold bordered call-out boxes */
.cta { border: 3px solid var(--light); box-shadow: 8px 8px 0 var(--light); background: var(--card); padding: 18px 24px; font-weight: 600; color: var(--light); }
```

### Specialty

### 9. Neon Cyber
Futuristic, techy. Clash Display + Satoshi (Fontshare); deep navy, cyan and magenta neon glow over a faint grid and particle field.

```css
@import url('https://api.fontshare.com/v2/css?f[]=clash-display@500,600,700&f[]=satoshi@400,500,700&display=swap');
:root {
  --accent: #00ffcc; --accent-hover: #ff00aa;
  --dark: #0a0f1c; --card: #111a2e; --border: #1f2d4a;
  --body: #c7d2e0; --label: #8b97aa; --muted: #95a1b4; --light: #ffffff;
  --green: #00ffcc; --red: #ff4d8d; --yellow: #ffd60a;
  --font-head: 'Clash Display', sans-serif; --font-body: 'Satoshi', sans-serif; --head-weight: 600; --body-weight: 400;
}
section { background:
  radial-gradient(circle, rgba(0,255,204,0.35) 1px, transparent 1.5px) 0 0 / 97px 83px,
  radial-gradient(circle, rgba(255,0,170,0.3) 1px, transparent 1.5px) 40px 30px / 131px 109px,
  linear-gradient(rgba(0,255,204,0.05) 1px, transparent 1px) 0 0 / 40px 40px,
  linear-gradient(90deg, rgba(0,255,204,0.05) 1px, transparent 1px) 0 0 / 40px 40px,
  var(--dark); }
h1 { text-shadow: 0 0 18px rgba(0,255,204,0.55); }
h3 { color: var(--accent); }
.card { box-shadow: 0 0 0 1px rgba(0,255,204,0.15), 0 0 24px rgba(0,255,204,0.08); }
```

### 10. Terminal Green
Hacker aesthetic. JetBrains Mono only; GitHub-dark, terminal green, scan lines, prompt-style headings, blinking cursor (HTML export).

```css
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;700;800&display=swap');
:root {
  --accent: #39d353; --accent-hover: #56e36c;
  --dark: #0d1117; --card: #161b22; --border: #30363d;
  --body: #c9d1d9; --label: #8b949e; --muted: #8b949e; --light: #f0f6fc;
  --green: #3fb950; --red: #f85149; --yellow: #d29922;
  --font-head: 'JetBrains Mono', monospace; --font-body: 'JetBrains Mono', monospace; --head-weight: 800; --body-weight: 400;
}
section { font-size: 23px; background: repeating-linear-gradient(0deg, rgba(255,255,255,0.025) 0 1px, transparent 1px 3px), var(--dark); }
h1 { font-size: 1.8em; letter-spacing: -0.03em; }
h1::before { content: '> '; color: var(--accent); }
h1::after { content: '▌'; color: var(--accent); margin-left: 0.15em; animation: blink 1s steps(1) infinite; }
h3::before { content: '// '; }
h3 { text-transform: none; letter-spacing: 0.02em; color: var(--muted); }
@keyframes blink { 50% { opacity: 0; } }
```

### 11. Swiss Modern
Bauhaus precision. Archivo 800 + Nunito; pure white, black type, red accent, visible 12-column grid, asymmetric left-weighted layout, red square mark.

```css
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;800;900&family=Nunito:wght@400;600;700&display=swap');
:root {
  --accent: #ff3300; --accent-hover: #ff5c33;
  --dark: #ffffff; --card: #f4f4f4; --border: #dedede;
  --body: #222222; --label: #555555; --muted: #666666; --light: #000000;
  --green: #15803d; --red: #ff3300; --yellow: #b45309;
  --font-head: 'Archivo', sans-serif; --font-body: 'Nunito', sans-serif; --head-weight: 800; --body-weight: 400;
}
section { padding: 60px 100px 60px 186px; background: repeating-linear-gradient(90deg, rgba(0,0,0,0.045) 0 1px, transparent 1px calc(100% / 12)), var(--dark); }
section::before { content: ''; position: absolute; left: 80px; top: 64px; width: 48px; height: 48px; background: var(--accent); }
h1 { letter-spacing: -0.035em; }
section.lead { justify-content: flex-end; padding-bottom: 90px; }
section.lead h1 { font-size: 3.6em; line-height: 1; }
```

### 12. Paper & Ink
Literary, thoughtful. Cormorant Garamond + Source Serif 4; warm cream, charcoal ink, crimson rules, pull quotes, drop caps.

```css
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,600;0,700;1,500&family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,600&display=swap');
:root {
  --accent: #c41e3a; --accent-hover: #d9435c;
  --dark: #faf9f7; --card: #f1eee8; --border: #ddd8cf;
  --body: #2e2e2e; --label: #6b6560; --muted: #6f6a64; --light: #1a1a1a;
  --green: #2f6f4e; --red: #c41e3a; --yellow: #946200;
  --font-head: 'Cormorant Garamond', serif; --font-body: 'Source Serif 4', serif; --head-weight: 700; --body-weight: 400;
}
h1 { font-size: 2.5em; letter-spacing: 0; }
h1::after { content: ''; display: block; width: 72px; height: 2px; background: var(--accent); margin-top: 0.25em; }
section.lead h1::after { width: 120px; }
blockquote { background: transparent; border: none; border-top: 1px solid var(--accent); border-bottom: 1px solid var(--accent); font-family: var(--font-head); font-size: 1.35em; color: var(--light); padding: 14px 0; }
/* Signature: <p class="lede">…</p> for a drop-capped opening paragraph */
.lede::first-letter { float: left; font-family: var(--font-head); font-weight: 700; font-size: 3.4em; line-height: 0.8; color: var(--accent); padding: 0.06em 0.1em 0 0; }
```

## Aim for

Style discovery exists to get a deck with a point of view:

- **Type:** a display face from the chosen preset or the pairings table, with a
  clearly contrasting body face.
- **Colour:** one dominant colour with sharp accents; the accent reserved for
  data highlights.
- **Layout:** left-weighted, asymmetric compositions and varied slide
  structures from one slide to the next.
- **Decoration:** the preset's signature device, used consistently; abstract
  shapes rather than illustrations.
- **Range:** alternate light and dark across decks so successive decks don't
  converge on one safe look.
