# Recipe schema (`photo_edit.py`)

## Contents

- Geometry (`straighten`, `crop`, `reframe`, `resize`)
- Colour and tone
- Output
- `frame`
- Scene presets (`--scene`)
- Auto-suggestion rules (`suggested_recipe`, `--recipe auto`)

A recipe is JSON. Layering: `--look` (or a `"look"` key) < `--recipe` (`auto`, a file, or inline JSON)
< `--set key=value` (dotted keys, JSON values: `--set crop.focus=[0.4,0.5]`).

Processing order is fixed and correct; the order of keys in the JSON does not matter:
orient (EXIF) → straighten → reframe/crop → white balance → exposure → tone curve → clarity → vibrance /
saturation → chroma denoise → vignette → B&W → resize → sharpen → frame → save.

## Geometry

| Key | Value | Notes |
|---|---|---|
| `straighten` | degrees, -10..10 (max ±45) | Positive = counter-clockwise. Auto-crops to the largest rectangle of the **same aspect**. Use `tilt_deg` from analyze (it is already the correction). |
| `crop` | `{"aspect": "4:5", "focus": [x,y], "place": "center"\|"thirds", "zoom": 1.0}` or `{"box": [x0,y0,x1,y1]}` | Manual crop. `box` is relative (0..1) or pixels. Ignored when `reframe` is set. |
| `reframe` | object, below | Subject-aware crop. Preferred over `crop`. |
| `resize` | `{"long_edge": 2048}` \| `{"width": 1200}` \| `{"height": 800}` \| `{"exact": [1080,1350]}` | Lanczos in linear light. No upscaling unless `"allow_upscale": true`. `exact` without a crop/reframe implies a centred crop of that aspect. |

### `reframe`

| Key | Default | Meaning |
|---|---|---|
| `aspect` | `"original"` | `"4:5"`, `"1:1"`, `"16:9"`, `"9:16"`, `"2:3"`, `"1.91:1"` or a number. Shapes use their own aspect. |
| `subject` | `"auto"` | `"auto"` (faces → saliency) or a relative box `[x0,y0,x1,y1]` on the **input** image (mapped through `straighten`). |
| `place` | `"thirds"` | `thirds` (subject centre on the nearest third; centred subjects stay centred; faces put eyes near the upper third), `center`, `golden`, `keep` (same relative position). Shapes use their sweet spot. |
| `tightness` | 0.35 (shapes 0.5) | 0 = widest crop of that aspect, 1 = as tight as the subject allows. |
| `margin` | 0.05 (shapes 0.04) | Breathing room around the subject, as a fraction of the crop. |
| `fit` | `"crop"` | `crop`; `blur` or `color` to pad the canvas instead of cutting the subject. |
| `fit_color` | `auto-dark` | Colour for `fit: "color"`. |
| `contain` | false | Fit the **whole** image into the aspect and pad (stories, banners). |
| `min_visible` | 97 shapes / 90 rectangles | Required saliency-weighted % of the subject left visible by crop + frame mask. Faces always need 99. |
| `auto_pad` | true for shapes or when faces are present | When no crop reaches the targets, pad with the smallest feathered extension that does (mirrored edges for shapes, zoomed blur for rectangles). |

Report fields: `subject_centre_in_crop`, `subject_area_pct`, `kept_of_source_pct`, `subject_clipped`,
`visibility {subject_visible_pct, subject_comfort_pct, faces_visible_pct}`, `visibility_ok`,
`tightness_used`, `placement_mode`, `padding_px`, `notes`.

## Colour and tone (Lightroom-like units)

| Key | Range (taste / max) | What it does |
|---|---|---|
| `white_balance` | see below | Per-channel gains in linear light, luminance preserved. |
| `exposure` | -1.5..1.5 EV (max ±3) | Multiplies linear light by 2^EV; soft shoulder protects highlights when brightening. |
| `contrast` | -30..35 (max ±100) | Symmetric S-curve on L*. |
| `highlights` | -70..30 | Moves the 3/4-tone point; negative recovers bright areas. |
| `shadows` | -30..50 | Moves the 1/4-tone point; positive opens dark areas. |
| `whites` | -30..30 | White point. Negative dulls whites (film look). |
| `blacks` | -40..30 | Black point. Negative deepens; positive lifts to a matte black. |
| `curve` | `[[x,y],...]` 0..1 | Explicit monotone curve on L* (replaces the parametric one). |
| `clarity` | -30..30 | Midtone local contrast (large-radius, halo-guarded). |
| `vibrance` | -50..35 | Boosts muted colours most and skin hues (20–70° hue) at 40%. |
| `saturation` | -100..25 | Uniform chroma scale. |
| `denoise_chroma` | 0..80 | Blurs colour noise only; luminance detail untouched. |
| `vignette` | -30..15 | Negative darkens edges (subtle; ≤ -20 starts to look like a filter). |
| `bw` | `true` or `{"filter": "neutral"\|"yellow"\|"orange"\|"red"\|"green"\|"blue"}` | B&W with a lens-filter channel mix. Yellow is the safe default; red = dramatic skies; green = kind to foliage, hard on skin. |

`white_balance` forms:
- `"auto"` or `{"mode": "auto", "strength": 0.7}`: neutralise the dominant near-neutral cluster (sky excluded).
  Skipped automatically when two clusters disagree, unless `"force": true`.
- `{"mode": "region", "box": [x0,y0,x1,y1], "strength": 1.0}`: eyedropper on an area you know is grey/white.
- `{"mode": "point", "point": [x,y], "radius": 0.01}`: same, small square.
- `{"temp": 10, "tint": -5}`: manual; may be combined with any mode. +temp warmer, +tint magenta.

## Output

| Key | Default | Notes |
|---|---|---|
| `sharpen` | `"auto"` | `auto` = only when downscaled ≥1.5x (35%, 0.6 px). Or `{"amount": 40, "radius": 0.8, "threshold": 2}`; `null` = off. Luminance only. |
| `quality` | 90 | JPEG/WebP. ≥90 uses 4:4:4 chroma. |
| `metadata` | `"keep"` | `keep`, `no-gps`, `strip`. Orientation is always reset (pixels are already rotated). |

## `frame`

| Key | Default | Notes |
|---|---|---|
| `shape` | `rect` | `rect`, `rounded`, `circle`, `ellipse` (`aspect`, default 0.8), `heart`, `star` (`points`, `inner`), `hexagon`, `octagon`, `diamond` (`aspect`), `arch` (`aspect`, default 0.75), `polygon` (`points` in any units), `mask` (`mask`: path to PNG; alpha or grey = visible area). |
| `style` | `mat` for rect/rounded, else `cutout` | `mat`, `polaroid`, `cutout`. |
| `border` | 0.06 | Mat/polaroid width, fraction of the photo's short edge. `bottom` (polaroid, 0.22), `bottom_weight` (mat, e.g. 1.3 for a gallery-style heavier bottom). |
| `color` / `background` | `off-white` (mat), `warm-white` (polaroid), `transparent` (cutout) | `#rrggbb`, `[r,g,b]`, `white`, `off-white`, `warm-white`, `cream`, `charcoal`, `black`, `transparent`, `auto-light`, `auto-dark`, `auto-accent` (derived from the photo; light/dark stay near-neutral). |
| `padding` | 0 (0.06 with stroke/shadow) | Space around a cut-out shape. |
| `stroke`, `stroke_color` | 0, `auto-dark` | Outline just outside the shape edge (never covers the photo). |
| `keyline`, `keyline_color` | 0, `auto-dark` | Thin line around the photo inside a mat (0.003–0.005). |
| `corner_radius` | 0 | Rounded photo corners on rect frames (fraction of short edge). |
| `shadow`, `shadow_size`, `shadow_opacity` | false, 0.025, 0.35 | Soft drop shadow. Needs padding/mat to show. |

When a non-rectangular shape is set and no `reframe` is given, `reframe: {"place": "sweet"}` is implied:
the subject centre goes to the shape's deepest interior point and the crop is searched until the subject is
visible through the shape.

## Scene presets (`--scene`)

Defined in `scripts/photo_analyze.py` `SCENES`; `tests/test_photo_edit_skill.py` fails if this table drifts.

| Scene | Median L* target | Auto-WB strength | Vibrance cap | Lift shadows | Extend whites |
|---|---|---|---|---|---|
| general | 50 | 0.7 | 15 | yes | yes |
| landscape | 48 | 0.6 | 15 | yes | yes |
| portrait | 54 | 0.6 | 8 | yes | yes |
| food | 55 | 0.5 | 10 | yes | yes |
| product | 62 | 1.0 | 5 | yes | yes |
| interior | 58 | 0.8 | 5 | yes | yes |
| document | 70 | 1.0 | 0 | yes | yes |
| street | 46 | 0.5 | 8 | no | yes |
| sunset | none | 0.0 | 10 | no | no |
| night | none | 0.3 | 5 | no | no |
| low-key | none | 0.5 | 8 | no | no |
| high-key | 72 | 0.8 | 5 | yes | yes |

"none" = keep the exposure (only a murky median below L* 15 gets +0.3 EV). Auto-WB strength 0 = leave the
colour of the light alone.

## Auto-suggestion rules (`suggested_recipe`, `--recipe auto`)

Conservative by design; each rule prints its reason in `notes`.

- **Straighten** when tilt confidence ≥ 0.5 and 0.2° ≤ |tilt| ≤ 8°.
- **White balance** when the neutral cluster is reliable (> 2% of pixels, no competing cluster ≥ 40% of its
  size) and the cast magnitude √(a*²+b*²) ≥ 4; strength = scene value (+0.1 when ≥ 10).
- **Exposure**: if the median is ≥ 0.15 EV below target, brighten by 70% of the gap, capped by highlight
  headroom (to p99 L* 96) + 0.15 and by 1.2 EV; if ≥ 0.3 EV above, darken by 50%, capped at -1 EV.
- **Highlights** -20 (p99 L* > 97 or > 0.5% clipped) or -35 (> 2% clipped).
- **Shadows** +20 when p5 L* < 8 and the scene lifts shadows.
- **Contrast** +15 when p5–p95 < 45 L*, +8 when < 55 (not for high-key/document).
- **Blacks** -10 when p1 L* > 10; **whites** +10 when p99 L* < 85 and exposure gain < 0.3.
- **Vibrance** = scene cap when mean chroma < 14; -10 when > 1.5% of pixels exceed chroma 85.
- **Chroma denoise** 40 (noise σ 4–8) or 60 (σ > 8).
