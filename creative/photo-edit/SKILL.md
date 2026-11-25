---
name: photo-edit
description: "Use when editing an existing photo locally: \"fix this photo\", \"make it look better\", \"brighten it\", \"fix the colours\", \"straighten the horizon\", \"crop for Instagram\", \"resize for web or print\", \"put it in a frame\", \"heart-shaped frame\", \"polaroid\". Measured exposure, white balance, colour, crop, subject-aware reframe, resize, sharpen, mats and shaped cut-outs, with no paid API. Not for generating new images, AI/generative edits or upscaling (use image-studio)."
license: MIT
metadata:
  version: 1.1.0
  author: moonlight-lupin
  platforms: [linux, macos, windows]
  tags: [photo, image, editing, crop, reframe, frame, color-correction, white-balance, composition]
  related_skills: [image-studio, pexels-stock-photos]
---

# Photo Edit Skill

## Overview

Basic photo editing that is measured, not guessed: exposure, white balance, tone, colour, straightening,
subject-aware reframing, resizing/sharpening for delivery, and frames (mats, polaroids, shaped cut-outs such
as hearts, circles, stars). Scripts do the maths and report numbers; `vision_analyze` supplies judgement in a
blind comparison; the user approves the result. Out of scope: RAW development, local retouching
(blemish/object removal, brushes), generative fills.

## When to Use

The user asks to fix, improve, brighten, colour-correct, straighten, crop, reframe or resize a photo, prepare
it for Instagram/web/print, apply a look, or put it in a frame or a shape. Route elsewhere: new images,
generative edits (remove/replace objects, change content) and AI upscaling go to `image-studio`; finding
stock photos goes to `pexels-stock-photos`.

## Prerequisites

- Python 3.9+ with `pip install -r ${HERMES_SKILL_DIR}/requirements.txt` (Pillow, NumPy). On Windows run
  `python` where this file says `python3`.
- Optional: `pip install pillow-heif` (iPhone HEIC); `pip install "opencv-python-headless<5"` (face
  detection; OpenCV 5 dropped the detector used, so without 4.x people are found by saliency only).
- `vision_analyze`: native when the main model is multimodal, otherwise the auxiliary vision model. Its
  `region` argument crops at full resolution for 1:1 inspection. Without vision, stop after step 5 and send
  the comparison sheet to the user to judge.
- Other agents: `${HERMES_SKILL_DIR}` is this skill's folder; `vision_analyze` is any tool that looks at an
  image file; `[[as_document]]` is Hermes-only and can be dropped.

## How to Run

```
python3 ${HERMES_SKILL_DIR}/scripts/photo_analyze.py IN.jpg --scene SCENE --brief --overlay WORK/overlay.png
python3 ${HERMES_SKILL_DIR}/scripts/photo_edit.py IN.jpg -o WORK/OUT_v1.jpg --recipe WORK/recipe_v1.json --check WORK/check_v1.png
python3 ${HERMES_SKILL_DIR}/scripts/photo_compare.py IN.jpg WORK/OUT_v1.jpg -o WORK/blind_v1.png --blind --detail 0.5,0.4
```

`photo_analyze.py` without `--brief` prints JSON (metrics, subject, composition, reframe previews, notes,
`suggested_recipe`). `photo_edit.py` prints JSON (applied steps, before/after metrics, warnings); `--dry-run`
resolves the recipe without rendering. `photo_compare.py --blind` hides which panel is which and writes the key to
`<sheet>.key.json`. Every script answers `--help`.

## Quick Reference

| Need | Recipe fragment (full schema: `references/recipe.md`) |
|---|---|
| Measured auto-fix | `--recipe auto --scene portrait` |
| Level horizon | `{"straighten": -1.4}` (analyze's `tilt_deg` is already the correction) |
| Neutralise a cast | `{"white_balance": {"mode": "auto", "strength": 0.7}}` |
| Eyedropper on a known grey/white | `{"white_balance": {"mode": "region", "box": [x0,y0,x1,y1]}}` (relative 0..1) |
| Brighten / tone | `{"exposure": 0.3, "highlights": -30, "shadows": 20, "contrast": 10}` |
| Colour | `{"vibrance": 15}`; saturation rarely, within ±15 |
| Instagram portrait | `{"reframe": {"aspect": "4:5"}, "resize": {"exact": [1080, 1350]}}` |
| Story without cutting | `{"reframe": {"aspect": "9:16", "contain": true, "fit": "blur"}}` |
| Look preset | `--look natural` (also `bright-airy`, `moody`, `warm-film`, `clean-product`, `bw-classic`) |
| Heart cut-out | `{"frame": {"shape": "heart", "stroke": 0.01, "stroke_color": "#ffffff"}}` → output `.png` |
| Mat / polaroid | `{"frame": {"style": "mat", "border": 0.06, "color": "auto-light"}}`, `{"frame": {"style": "polaroid"}}` |
| Own shape | `{"frame": {"shape": "mask", "mask": "/path/shape.png"}}` or `{"shape": "polygon", "points": [[x,y],...]}` |

Scenes: general, landscape, portrait, food, product, interior, document, street, sunset, night, low-key,
high-key. Default `general`; each scene's targets are in `references/recipe.md` §Scene presets. Taste limits
are enforced (e.g. saturation ≤ +25, clarity ≤ 30); `--allow-extreme` lifts them only when the user asks for
a stylised result.

## Procedure

Copy this checklist into your working notes and tick it off:

```
- [ ] 1 intent   - [ ] 2 measure   - [ ] 3 recipe   - [ ] 4 frame
- [ ] 5 render   - [ ] 6 blind check   - [ ] 7 deliver
```

1. **Intent.** What is the photo for (post, print, listing, gift)? If the destination changes the crop or
   size and is unknown, ask once; otherwise default to "a natural, better version of the same photo".
   Copy the input into a work folder; outputs are `_v1`, `_v2`…, never the original.
   Done when: destination (or the default) and work folder are fixed.
2. **Measure.** `vision_analyze` the photo with `references/vision-checks.md` §1 Q1, then pick `--scene`
   (default `general`). Run `photo_analyze.py --brief --overlay`, and `vision_analyze` the overlay with §1 Q2–Q5.
   If the red box is not the subject, pass the box vision gives as `--subject x0,y0,x1,y1` /
   `reframe.subject`. Done when: scene chosen, subject box confirmed by vision, tilt and WB questions
   answered.
3. **Recipe.** Start from `suggested_recipe`, apply `references/taste.md`, write `recipe_v1.json`. Give each
   value a one-line reason tied to a measurement ("p99 L*=99.1, 3% clipped → highlights -35"). Two competing
   neutrals in the notes → vision decides, then `white_balance.mode: region`. Done when: every key has a
   reason and `photo_edit.py --dry-run` prints no unknown-key or clamp warnings you did not intend.
4. **Frame / reframe** (only if asked or the destination needs an aspect). Choose the aspect or shape from
   `references/taste.md` §Crops and §Frames. The script puts the subject on thirds or the shape's sweet spot
   and loosens or pads until the subject is visible (≥97% in shapes, ≥90% in rectangles;
   `reframe.min_visible`) and every face ≥99%.
   Done when: the planned output format supports the frame (`.png` for transparent shapes).
5. **Render** with `--check`. Done when: `warnings` is empty or each is consciously accepted, and when
   framing, `applied.reframe.visibility_ok` is true.
6. **Blind check (feedback loop).** `photo_compare.py ORIGINAL OUT --blind --detail x,y` on the subject, then
   `vision_analyze` the sheet with §2 **before** opening the key file; then the `--check` image with §3.
   If the edit is not preferred, looks overdone, or anything is cut: change one or two values, render the
   next version, and repeat this step. Stop after 3 rounds and show the user the best two.
   Done when: vision prefers the edit (or rates it equally natural) blind, and §3 answers are all "yes".
7. **Deliver.** Send the final file and a 2–4 line summary with the key numbers ("+0.4 EV, highlights -30,
   WB b*=+9 → +2, 4:5 crop with the subject on the left third"). The user approves the result; offer one
   alternative only when it is meaningfully different. On chat platforms end the message with
   `[[as_document]]` to avoid recompression. Done when: the user has the file and the summary.

## Common Pitfalls

- **Auto white balance is a guess.** Sunsets, candlelight and tungsten interiors are warm on purpose:
  `--scene sunset`/`night` leaves WB alone. Blue sky is excluded from neutral detection, but snow, sand and
  coloured walls can still fool it; check skin and whites visually.
- **Clipped highlights are gone.** Pulling highlights recovers only what is below 255. Compare
  `after.clip_hi_pct` with `before`.
- **Sharpening is for output size.** Phone photos arrive sharpened; `sharpen: "auto"` acts only when
  downscaling ≥1.5x. Sharpening never rescues a soft or blurred photo.
- **Saturation is the amateur tell.** Use vibrance (protects skin); keep saturation within ±15.
- **Transparent shapes need PNG/WebP.** JPEG flattens transparent corners onto white; or set
  `frame.background`.
- **Subject detection is a proposal.** Saliency finds what stands out, not what matters (a bright window, a
  logo). Confirm on the overlay; faces need OpenCV 4.x.
- **A labelled comparison invites self-approval.** Judge with `--blind`; read the key only after the verdict.
- **Metadata.** EXIF is kept (orientation reset). For public posting set `"metadata": "no-gps"` or `"strip"`.
- **Colour profiles.** Display P3 / Adobe RGB inputs are converted to sRGB and outputs tagged sRGB.

## Verification Checklist

- [ ] Original file untouched; output opens at the expected size and format.
- [ ] `photo_edit.py` warnings empty or each accepted; `after.clip_hi_pct` ≤ before + 0.5.
- [ ] WB corrected → `after.cast_ab` closer to 0 (unless the warmth was intended).
- [ ] Framing → `applied.reframe.visibility_ok` true and §3 vision answers all "yes".
- [ ] Blind §2 verdict prefers the edit or rates it equally natural.
- [ ] Summary to the user cites the actual numbers from the `photo_edit.py` JSON.

## Files

| Path | Read when |
|---|---|
| `scripts/photo_analyze.py` | Step 2: metrics, subject, composition, `suggested_recipe`, `--overlay`. |
| `scripts/photo_edit.py` | Step 5: applies a recipe, `--check` review image, `--dry-run`. |
| `scripts/photo_compare.py` | Step 6: blind A/B sheets and 1:1 detail crops. |
| `scripts/photo_subject.py`, `scripts/photo_frames.py`, `scripts/photo_core.py` | Library modules used by the CLIs; read only to debug. |
| `references/recipe.md` | Writing any recipe: every key, range, default, scene preset and auto rule. |
| `references/taste.md` | Step 3–4: target numbers, amateur tells, per-scene advice, crop sizes, frame taste. |
| `references/vision-checks.md` | Steps 2 and 6: the exact `vision_analyze` questions. |
| `templates/looks/*.json` | Look presets (each has an `_about` line on when it suits). |
| `tests/test_photo_edit_skill.py` | Offline tests: `python3 -m pytest ${HERMES_SKILL_DIR}/tests -q`. |
| `tests/eval-scenarios.md` | Behavioural eval scenarios and model scope for checking the skill itself. |
| `examples/example-run.md` | A worked end-to-end run, if unsure what good output and a summary look like. |
| `requirements.txt` | Runtime dependencies (Pillow, NumPy). |
| `README.md` | Human-facing overview of the folder; agents can skip it. |
