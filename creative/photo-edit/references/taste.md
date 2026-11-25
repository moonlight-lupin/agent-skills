# Taste rules

Good editing is mostly restraint. The viewer should notice the photo, not the edit.

## Principles

1. **Serve the photo's intent.** A sunset is warm, a night street is dark, a product shot is clean and
   neutral. Correct towards the intent, not towards a mid-grey average.
2. **Smallest change that works.** If two small moves fix it, don't make four. Re-measure after each round.
3. **Protect what can't come back:** highlights (clipping), skin tones (hue and saturation), and the
   subject's edges (cropping and frames).
4. **Global before local, light before colour, geometry first.** Straighten and crop first. Colour judgements
   change once exposure is right.
5. **One look per photo, applied lightly.** A look is seasoning; at full strength most presets are too much.
   Halve values that feel heavy.
6. **When unsure, compare.** Render two candidates, put them side by side with `photo_compare.py`, and pick with
   `vision_analyze`. Pick the more natural one unless the user asked for a style.

## Numbers that look right

| Target | Natural range | Red flag |
|---|---|---|
| Median L* (normal scene) | 45–58 | < 35 murky, > 68 washed (unless high-key) |
| p1 L* (black point) | 2–8 | > 12 milky, 0 with > 2% clipped = crushed |
| p99 L* (white point) | 88–98 | < 80 dull; clip_hi > 1% blown |
| p5–p95 range | 55–80 L* | < 45 flat, > 88 harsh |
| Neutral cast \|a*\|, \|b*\| | ≤ 3 | ≥ 6 visible cast (fine if intended warmth) |
| Mean chroma | 12–30 | > 35 or oversaturated_pct > 2% looks fake |
| Skin | hue ≈ 25–55° in Lab, chroma 15–35 | green/magenta skin is the worst failure |

## Common amateur tells (avoid)

- Saturation pushed instead of vibrance; neon skies; orange skin.
- "HDR" look: shadows +60, highlights -100, clarity +60 → grey halos and flat mud.
- Over-sharpening: white outlines around edges at 100%. Sharpen only for output size.
- Crushed blacks from too much contrast; lifted matte blacks on every photo.
- Heavy vignettes (> -20) and teal-orange grading on everything.
- Neutralising a golden-hour or candle-lit scene into clinical grey.
- Tilted horizons by 1–2°: worse than 10° deliberate. Level or commit.
- Crops through joints (wrists, knees, ankles), the chin or the top of the head at forehead level; cramped
  headroom; the subject facing out of the frame with no lead room.
- Frames that compete: saturated mat colours, thick black outlines, drop shadows on a white web page.

## By scene

- **Portrait:** WB from skin and whites, vibrance ≤ 10, no clarity on faces (≤ 5), shadows +10–20 to open
  eyes. Crop: eyes on the upper third; don't cut at joints; leave space in front of the face.
- **Landscape:** level the horizon; horizon on a third (sky-heavy if the sky is the story). Highlights
  -20–40 for sky detail; vibrance 10–20; clarity ≤ 15.
- **Sunset / night / low-key:** keep the mood: no auto WB, don't lift shadows to grey; protect the light
  source from clipping; median L* 20–35 is fine.
- **Food:** warm, bright, appetising: exposure +0.2–0.4, slight warmth OK, vibrance ≤ 10; avoid green
  or blue casts; crop tight, 4:5 or 1:1.
- **Product / e-commerce:** WB strength 1.0, or a region on the white backdrop; backdrop L* 95–98 but not
  clipped on the product; accurate colour over pretty colour; no vignette or looks.
- **Interior / real estate:** verticals straight (straighten, then check door frames), bright and neutral,
  shadows +20–35, highlights -40 for windows.
- **Document / whiteboard:** high-key, WB strength 1.0, contrast via `blacks` and `whites`; B&W if colour
  carries no meaning.
- **B&W:** yellow filter default, red for dramatic skies, contrast +15–25, true blacks (p1 L* ≈ 3).

## Crops and sizes by destination

| Destination | Aspect | Pixels |
|---|---|---|
| Instagram feed portrait | 4:5 | 1080×1350 |
| Instagram square | 1:1 | 1080×1080 |
| Story / Reel / TikTok | 9:16 | 1080×1920 (use `contain` + `fit: blur` if the subject would be cut) |
| X / web landscape | 16:9 | 1600×900 |
| LinkedIn / OG link image | 1.91:1 | 1200×627 |
| Print 4×6 / 6×9 | 2:3 | long edge 300 ppi × inches |
| Print 8×10 | 4:5 | 2400×3000 |
| Web gallery | original | long edge 2048, quality 85–90 |

## Frames

- **Mats:** off-white or `auto-light` (near-neutral, tuned to the photo); 5–8% of the short edge; gallery
  look = `bottom_weight` 1.2–1.4. A 0.003–0.005 keyline in `auto-dark` adds polish.
- **Polaroid:** square or 4:5 photo, warm-white, bottom 0.22. Pair with `warm-film` at reduced strength.
- **Shapes:** the subject must be fully inside: never a face cut by the heart's cleft or a star's arm.
  Hearts and circles suit single subjects (one face, one object). Stars and diamonds waste most of the
  image, so use them only on request. A white or `auto-light` stroke of 0.008–0.012 separates the shape
  from busy backgrounds; a shadow of 0.02–0.03 lifts it off a light page. Save as PNG.
- **Colours:** `auto-accent` gives a muted colour pulled from the photo, good for a thin stroke and rarely
  for a mat. Avoid pure black mats except for gallery-style dark presentations.
