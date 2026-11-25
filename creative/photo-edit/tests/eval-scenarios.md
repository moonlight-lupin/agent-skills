# Eval scenarios (behaviour, not code)

Run each prompt in a fresh Hermes session with this skill loaded and a real photo of the stated kind.
Score every rubric line pass/fail; a scenario passes at 100%. Re-run after any change to SKILL.md or the
references.

**Model scope:** the skill is judgement-heavy and needs vision. Test with the main model the user runs
day to day, with `vision_analyze` available (native or auxiliary). Do not score small or text-only models;
their failures are noise, not signal.

## 1. "Fix this photo" (indoor portrait, tungsten-lit, slightly dark)

- [ ] Runs `photo_analyze.py` with `--scene portrait` before choosing values.
- [ ] Confirms the subject on the overlay with `vision_analyze`.
- [ ] Recipe has a reason per value; vibrance ≤ 10, saturation untouched; WB not fully neutralised.
- [ ] Uses `photo_compare.py --blind` and asks the vision model before reading the key.
- [ ] Original untouched; output is `_v1` (or later); summary cites numbers from the `photo_edit.py` JSON.

## 2. "Make it ready for Instagram" (landscape, tilted horizon, person off-centre)

- [ ] Straightens using analyze's `tilt_deg` sign as given (no sign flip).
- [ ] 4:5 reframe at 1080×1350; the person is not clipped (`subject_clipped` false).
- [ ] Horizon is not left through the middle when the crop allows a third.
- [ ] Sharpening only from `"auto"` on the downscale; no manual oversharpening.

## 3. "Put our photo in a heart for an anniversary card" (two faces)

- [ ] Output is `.png` (or a background colour is set).
- [ ] `applied.reframe.visibility_ok` true; both faces ≥ 99% in `faces_visible_pct`.
- [ ] Checks the `--check` image with `vision-checks.md` §3 and acts on a "no".
- [ ] Stroke and shadow are subtle (stroke ≤ 0.015, shadow opacity ≤ 0.4).

## 4. "Make the sunset pop" (sunset, warm cast, dark foreground)

- [ ] Uses `--scene sunset`; does not neutralise the warmth.
- [ ] Protects the sun: `after.clip_hi_pct` ≤ before + 0.5.
- [ ] Vibrance over saturation; stays within taste limits without `--allow-extreme`.

## 5. "This product shot looks yellow" (white backdrop, tungsten cast)

- [ ] Uses `white_balance` region on the backdrop (or auto at strength 1.0 after vision confirms the
      backdrop is the neutral).
- [ ] Backdrop ends near-neutral (|a*|, |b*| ≤ 3) without clipping the product.
- [ ] No look, vignette or clarity applied.
