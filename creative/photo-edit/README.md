# photo-edit

Local, deterministic photo editing for AI agents, built to give an agent taste and precision. Scripts
measure the photo (exposure percentiles, clipping, colour cast, saturation, sharpness, noise, tilt, subject
and composition), apply a recipe of Lightroom-style adjustments in a fixed order, and build blind A/B sheets
so a vision model judges the result without knowing which panel is the edit. Includes subject-aware
reframing and frames: mats, polaroids and shaped cut-outs (heart, circle, star, ellipse, hexagon, diamond,
arch, any polygon or mask). The frame never hides the subject: visibility is measured and the crop
loosens or pads until it passes. No paid API; for generative edits use `image-studio`.

## Structure

```
photo-edit/
├── SKILL.md                    # Workflow: intent → measure → recipe → frame → render → blind check → deliver
├── requirements.txt            # Pillow, NumPy
├── scripts/
│   ├── photo_analyze.py        # CLI: metrics, subject, composition, overlay, suggested recipe
│   ├── photo_edit.py           # CLI: apply a recipe (tone, colour, straighten, reframe, resize, frame)
│   ├── photo_compare.py        # CLI: labelled or blind A/B sheets, 1:1 detail crops
│   ├── photo_core.py           # Colour-managed I/O, sRGB/Lab maths, filters
│   ├── photo_subject.py        # Saliency + optional face detection, composition metrics
│   └── photo_frames.py         # Reframe planner, shape library, visibility check, frame renderer
├── references/
│   ├── recipe.md               # Every recipe key, range, default, scene preset, auto rule
│   ├── taste.md                # Target numbers, amateur tells, per-scene advice, crop sizes, frames
│   └── vision-checks.md        # The exact questions for the vision model, per stage
├── templates/looks/*.json      # natural, bright-airy, moody, warm-film, clean-product, bw-classic
├── tests/
│   ├── test_photo_edit_skill.py  # Synthetic-image tests + docs↔code parity
│   └── eval-scenarios.md         # Behavioural eval scenarios and model scope
└── examples/
    └── example-run.md          # Worked end-to-end example
```

## Requirements

- Python 3.9+ and `pip install -r requirements.txt`
- Optional: `pillow-heif` (HEIC input), `opencv-python-headless<5` (face detection)
- A vision-capable model or image-viewing tool for the judgement steps

## License

MIT
