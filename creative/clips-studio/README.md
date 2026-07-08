# clips-studio

Staged fal.ai **video** generation skill for AI agents — the moving-image sibling of `image-studio`: brainstorm the motion → draft cheaply → produce the final at quality. Three modes: text-to-video, animate a still, and camera move.

## Structure

```text
clips-studio/
├── SKILL.md                       # Workflow doc: 3 modes, staged pipeline, egress checks, honesty discipline
├── scripts/
│   └── falvid.py                  # CLI: generate (text-to-video), animate, camera, costs, dry-run
├── references/
│   ├── fal-video-models.md        # Video model registry with rates (text- & image-to-video; some *(verify)*)
│   └── motion-honesty-guide.md    # Discipline for animating real subjects without misrepresenting them
└── examples/
    └── example-run.md             # Worked end-to-end examples (animate, camera, image→video combo, t2v)
```

## Requirements

- Python 3.8+
- `pip install fal-client requests`
- `FAL_KEY` environment variable (get one at https://fal.ai)
- Optional: `FAL_ADMIN_KEY` for live balance display after real calls
- A video clip can take **several minutes** to render, and video is the dearest fal use — keep drafts short and cheap, run `--dry-run` first, and confirm cost before the final.

## Useful commands

```bash
python scripts/falvid.py generate --prompt "abstract light sweep" --duration 5 --dry-run
python scripts/falvid.py animate --image still.png --prompt "slow light sweep across the product" --duration 5 --aspect 16:9 --dry-run
python scripts/falvid.py costs
```

## Notes

- **Text-to-video rates are marked *(verify)*** in the model registry — confirm the first `generate` cost on the fal dashboard.
- This skill writes **local draft files only** — it never posts, publishes or sends. It is not a substitute for a real shoot or a measured 3D tour where literal accuracy matters.

## License

MIT
