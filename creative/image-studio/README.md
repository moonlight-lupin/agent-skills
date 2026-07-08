# image-studio

fal.ai image generation, editing and clean-up skill for AI agents. Three modes: **create** from
scratch (brainstorm → prototype cheaply → produce the final), **edit/overlay** on an existing image,
and **clean up / enhance** an amateur photo into a professional shot.

## Structure

```
image-studio/
├── SKILL.md                    # Workflow doc: three modes, egress checks, model guidance
├── scripts/
│   └── falgen.py               # CLI: generate, edit, upscale, removebg, costs
├── references/
│   ├── fal-models.md           # Model registry with verified pricing
│   └── cleanup-checklist.md    # Path C: common amateur-photo issues + fix phrasing
└── examples/
    └── example-run.md          # Worked end-to-end example
```

## Requirements

- Python 3.8+
- `pip install fal-client requests`
- `FAL_KEY` environment variable (get one at https://fal.ai)
- Optional: `FAL_ADMIN_KEY` for live balance display

## License

MIT