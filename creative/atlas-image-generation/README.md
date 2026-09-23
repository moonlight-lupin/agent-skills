# atlas-image-generation

Opt-in text-to-image generation through Atlas Cloud. The dependency-free Python
helper validates the selected model against the live public catalog and schema,
submits one paid request without retrying it, polls with bounded GET retries,
and validates the downloaded image.

## Requirements

- Python 3.11+
- `ATLASCLOUD_API_KEY` in the environment
- No third-party Python dependencies

## Quick check

```bash
python scripts/generate_image.py \
  "A red paper kite above a green field" \
  --aspect-ratio 16:9 --resolution 1k \
  --output ./outputs/kite.png --dry-run
```

`--dry-run` performs no network calls. Remove it only after confirming the
prompt, external egress, and current Atlas Cloud price.

## Tests

```bash
python -m pytest creative/atlas-image-generation/tests/test_generate_image.py -q
```

## License

MIT

