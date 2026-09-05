---
name: atlas-image-generation
description: >
  Generate an AI image through Atlas Cloud when the user explicitly chooses
  Atlas Cloud or provides ATLASCLOUD_API_KEY. Uses a live public model catalog
  and schema check, one non-retried paid submission, bounded GET polling, and
  local image validation. Do not use for stock-photo search, image editing, or
  when the host requires its native image tool.
license: MIT
metadata:
  version: 1.0.0
  author: binyangzhu000-sudo
  platforms: [linux, macos, windows]
  tags: [image-generation, atlas-cloud, text-to-image]
  related_skills: [image-studio, pexels-stock-photos]
---

# Atlas Image Generation

Generate one image through Atlas Cloud and save it locally. This is an opt-in
provider route: keep `image-studio` as the fal.ai workflow, and use
`pexels-stock-photos` when the user wants a real stock photo.

## Before the paid request

1. Confirm that the user chose Atlas Cloud and accepts third-party egress.
2. Confirm the prompt contains no confidential or sensitive information.
3. Set `ATLASCLOUD_API_KEY` in the environment; never place it in arguments,
   files, logs, or committed content.
4. Run `--dry-run` to inspect the request without making any network call.
5. Review the current model and price in the Atlas Cloud catalog. The default
   model was verified against the live catalog and schema on 2026-08-31, but
   model availability, fields, and pricing can change.

## Generate

Run from this skill directory:

```bash
export ATLASCLOUD_API_KEY="..."
python scripts/generate_image.py \
  "Editorial illustration of a solar-powered city block, clean geometric forms" \
  --aspect-ratio 16:9 \
  --resolution 1k \
  --output ./outputs/solar-city.png \
  --dry-run
```

Remove `--dry-run` only after the user approves the prompt and cost. The helper:

- fetches the public model catalog and the selected model's live schema;
- rejects hidden, non-image, missing, or incompatible models;
- submits the paid generation POST exactly once, with no automatic retry;
- polls prediction status using bounded GET retries;
- downloads the first output and validates PNG, JPEG, or WebP bytes before
  writing the destination file.

The default model is
`google/nano-banana-pro/text-to-image-developer`. Override it with `--model`
only when the live schema supports the supplied options.

## Cost and retry safety

- A generation POST is billable and must never be retried automatically.
- A failed or ambiguous submission is reported to the user; do not submit a
  replacement request without fresh confirmation.
- Only catalog, schema, and prediction GET requests use bounded retries.
- Use one image for the first run. Batch generation belongs in a separately
  approved workflow with an explicit budget.

## Verification

After completion, check that:

- the printed output path exists and is non-empty;
- the file opens as the expected image;
- its composition matches the approved prompt;
- no key, temporary URL, or local absolute path was written into tracked files.

