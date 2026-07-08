---
name: image-studio
description: >
  Generate, edit and upscale AI images via fal.ai through a three-stage studio
  workflow — brainstorm a strong prompt with the user, prototype cheaply and
  iterate on feedback, then produce a finalised image. Use when the user wants
  image generation or editing through the local fal.ai helper workflow, including
  requests to "generate an image", "make an image/picture/illustration/graphic
  of…", "create an AI image", "edit/change this image", "make a variation",
  "upscale this", create a "production-ready image", "clean up / enhance a photo",
  "make this phone shot look professional", create imagery "for the
  deck/post/website/newsletter", or when they explicitly mention fal.ai or
  nano-banana. Do not use for Canva template designs, branded PowerPoint decks,
  data charts/dashboards, or flowcharts/diagrams — those are layout, data, or
  structure tasks, not generative imagery. Video generation is out of scope. Do
  not override platform-native image generation tools where the host environment
  requires them.
version: 1.2.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
---

# Image Studio

Turn an idea into a finished image through three deliberate stages — **brainstorm → prototype
cheaply → produce the final** — using fal.ai. The point of the staging is cost and control: iterate
cheaply on a fast model, lock the concept with the user, then spend on a quality model only once, on
the agreed image.

This skill **generates files locally** for the user to review and use. It never posts, publishes, or
sends anything as final brand collateral.

## Scope and routing

Use this skill only when all of the following are true:

1. The task is generative imagery or image editing, not layout/design automation, charting,
   dashboarding, flowcharting, or slide/deck production.
2. The user is comfortable with fal.ai egress and paid API usage.
3. The local helper workflow is available or the user is asking you to prepare the prompt/brief for
   that workflow.

Do **not** use this skill for:

- Canva templates, PowerPoint decks, branded presentation layouts, data charts, dashboards,
  flowcharts, architecture diagrams, or process diagrams.
- Video generation.
- Confidential or sensitive image/document processing.
- Any host environment where a native image-generation/editing tool is explicitly mandated.

## Three modes — choose first

The workflow depends on whether you are **creating** an image, **changing** an existing one, or
**cleaning up** an existing one — they do not use the same steps:

- **Path A · Create from scratch** (no source image). The composition is unknown, so prototype
  cheaply to explore it, then finalise at quality — use **Stage 1 → 2 → 3** below.
- **Path B · Edit / overlay on an existing image** (populate a room with people, restyle a photo,
  add or remove an element). The composition is already fixed by the source photo, so a cheap
  prototype only adds drift and artefacts that do not predict the quality result — **skip it.**
  Brainstorm and **confirm the prompt** (Stage 1), then quality-edit the **original** directly
  (Stage 3). For cost-sensitive multi-iteration work, iterate on the same-family
  `fal-ai/nano-banana/edit` (a faithful preview) rather than on Kontext dev. The "prototype" is the
  agreed prompt, not an image.
- **Path C · Clean up / enhance an existing photo** (turn an amateur/phone shot professional — fix
  flare, reflections, white balance, exposure, perspective/warp, noise, clutter). Same mechanics as
  Path B (no prototype; quality-edit the original in one comprehensive pass), but the intent is
  **faithful correction, not change** — build the prompt from `references/cleanup-checklist.md` and
  keep every real feature exactly. Works for any subject — interiors, portraits, products, food,
  landscapes. One checklist-driven pass usually suffices. See the Clean-up section below.

Stages 1–3 describe Path A in full; Paths B and C reuse Stage 1 (brainstorm/confirm) then go straight
to Stage 3 (quality-edit the original), skipping the Stage-2 prototype.

## Before you start — egress and preflight

Generating an image sends the **prompt** to fal.ai. Editing, upscaling, or background removal also
sends the **image you provide** to fal.ai. fal.ai is a third-party US service, and result images are
downloaded from its CDN. That is external data egress.

Before any API call:

1. Confirm the task is within scope.
2. Confirm explicit user go-ahead for fal.ai egress and paid API usage before the first generation in
   a session.
3. Confirm explicit user go-ahead again before the costlier Stage-3 production run.
4. Check that `scripts/falgen.py` exists, dependencies are installed, `FAL_KEY` is set, and the working
   directory is writable.
5. For edits, upscales, and background removal, use only non-confidential, non-sensitive images that
   the user has rights to process through fal.ai.
6. Use the exact output paths printed by `falgen.py`; do **not** infer filenames from examples.

Never feed confidential or sensitive imagery or documents to fal.ai — e.g. a person's photo,
confidential report, deal materials, financial documents, investor materials, tenant materials,
valuation materials, or anything under NDA. If the user asks to edit something sensitive, stop and
flag the egress issue rather than uploading it.

Brainstorming in Stage 1 is pure chat and has no egress, so you can always draft the prompt first and
confirm the send afterwards.

**Setup needed:** a fal.ai account with billing, and the `FAL_KEY` — either the environment variable,
**or just saved in a text file in the working folder** (any filename, e.g. `fal key.txt`). The helper
finds the key automatically — env var first, then any small text file in the working folder (a
`FAL_KEY=your-key` line, or a raw key matching fal's `id:secret` shape), then the home dir (only
files whose name mentions fal/key/api/env, and only an explicit `FAL_KEY=…` line — bare tokens are
never taken from home, so other services' credentials can't be picked up). So **don't ask the user
for a key before checking**; only prompt if none is found. It uses the `fal-client`
package (`pip install fal-client requests`). If no key is found the helper fails with a clear message —
generation cannot proceed without it, but Stage 1 still works. (Keep any key file local; never commit it.)

## Stage 1 — Brainstorm the prompt (no API call)

Good output starts with a good prompt, so invest here before spending anything. Interview the user and
build a structured prompt brief covering:

- **Subject** — what is in the image, concretely.
- **Style / medium** — photoreal, 3D render, flat illustration, line art, watercolour, etc.
- **Composition** — framing, focal point, layout, and where any text or negative space sits.
- **Lighting / mood** — soft, dramatic, corporate-clean, warm, moody.
- **Colour palette** — whatever the user wants, without confidential detail.
- **Aspect ratio** — anchor to the destination: 16:9 deck/hero, 1:1 or 4:5 social, 9:16 story,
  2:3/3:4 portrait, or custom banner proportions.
- **Quality modifiers & negatives** — e.g. "high detail, sharp focus"; "no text, no watermark, no
  extra fingers".

Offer two or three distinct prompt directions rather than one, so the user can react to options. Save
the agreed brief to `_workings/` (for example, `_workings/prompt-brief_[slug].md`) so the run is
auditable. Keep prompts free of confidential detail.

For Paths B and C this is the step that replaces prototyping, so confirm the prompt with the user
before the first paid call. When the subject is people or an overlay onto a real scene, two craft
notes:

- **Name the action, not the mood.** "Sitting smiling" reads stiff and posed. Specify genuine
  interaction — "mid-conversation, one gesturing, two looking at each other, one showing a laptop
  screen to a friend" — so people relate to each other, not the camera.
- **Protect faces.** Distant/small faces deform easily — prefer fewer, larger people, add "clear,
  natural faces and hands", and re-edit just a bad region rather than re-rolling the whole image.

## Stage 2 — Prototype cheaply and iterate

Generate with a cheap, fast text-to-image model so iteration is inexpensive, then refine on the user's
feedback until they approve a prototype.

**First render** — text-to-image with FLUX schnell:

```bash
python scripts/falgen.py generate \
  --prompt "[the agreed prompt]" \
  --aspect 16:9 --num 2 \
  --run-log _workings/run-log_[slug].md \
  --out-dir _workings --name image_[slug]_v1
```

`--num 2` gives the user a couple of variations to choose from. The helper may save multiple files
such as `image_[slug]_v1_1.png` and `image_[slug]_v1_2.png`; always use the exact saved paths printed
by the helper.

On feedback, choose the cheaper move:

- **Concept or big composition change** → refine the prompt wording and re-run `generate` as the next
  version (`--name image_[slug]_v2`, etc.).
- **Targeted tweak to a chosen image** — for example, "make the sky warmer", "remove the building on
  the left", or "add more negative space top-right" → use `edit`.

The Stage-2 default editor is **FLUX Kontext [dev]** (`fal-ai/flux-kontext/dev`). It is a cheap
instruction editor billed per compute-second; fal does not return exact runtime locally, so the helper
flags the cost as time-billed and the fal dashboard remains the source of truth. Kontext preserves the
input image's dimensions and changes only what you name.

```bash
python scripts/falgen.py edit \
  --prompt "make the sky warmer and add negative space top-right" \
  --image _workings/[actual_saved_prototype_path].png \
  --run-log _workings/run-log_[slug].md \
  --out-dir _workings --name image_[slug]_v3
```

Do not pass `--aspect` to Kontext edits; Kontext keeps the source dimensions. Kontext accepts a single
image. If multiple reference images are required, use a model that supports `image_urls`, such as
`fal-ai/nano-banana/edit`, and confirm the cost trade-off.

Save every iteration to `_workings/` with an incrementing version so nothing is lost. Loop until the
user says "that's the one".

> Why two paths: a prompt re-roll explores fresh compositions; an edit holds the composition the user
> already likes and changes only what they named. Pick the one that matches the feedback.

## Stage 3 — Produce the final

Once the user approves a prototype, **confirm the go-ahead again**. This is the main spend.

Render the agreed concept at quality and at the resolution the user actually needs. Usually, getting
the final at target size removes the need for a separate upscale.

**Confirm the resolution — 2K or 4K?** It changes the price, so ask:

- **2K** (sensible default). Good for on-screen and in-hand use — decks, social, web, email, digital
  PDFs — and standard print to ~A4. Not ideal for large-format print read up close, or heavy
  crop-and-enlarge.
- **4K** — Nano Banana Pro bills this at **2× the base** (see `references/fal-models.md`). Good for
  large-format/close-viewed print (posters, banners, exhibition panels) or future-proofing a reusable
  hero. Not worth it for screen/social, which downscale anyway.

Pass it via `--arg resolution=2K` (or `4K`); the helper reflects the 4K surcharge in the reported cost.

1. **Quality render at target resolution** — edit the approved prototype with **Nano Banana Pro**
   (`fal-ai/nano-banana-pro/edit`, flat per image) to stay faithful to it, asking for the output size
   up front via `resolution` (up to 4K):

   ```bash
   python scripts/falgen.py edit \
     --prompt "[full locked prompt]. Use the supplied prototype as the COMPOSITION reference only. Reproduce at high fidelity — keep the subject, framing, palette and mood — and CORRECT the prototype's generative flaws: render natural anatomy (fix malformed hands, fingers and limbs; no extra or missing fingers/limbs), fix distorted faces and eyes, straighten warped objects and lines, remove artefacts. Name the specific ones you see, e.g. 'the left hand has six fingers — render a natural five-fingered hand'. Crisp clean edges, photorealistic." \
     --image _workings/[actual_approved_prototype_path].png \
     --model fal-ai/nano-banana-pro/edit --aspect 16:9 \
     --arg resolution=4K \
     --run-log _workings/run-log_[slug].md \
     --out-dir . --name image_[slug]_final
   ```

   The final prompt must include the full locked prompt, not just a generic enhancement instruction —
   and it must **name the flaws to fix**. "Improve/upscale this" does not fix them: Nano Banana Pro
   won't correct a defect it isn't told about, and telling it to "preserve everything" locks the
   defect in. Preserve the **concept** (subject, framing, palette, mood); fix the **execution**
   (anatomy, warped objects, artefacts). Treat the prototype as a composition reference, not a
   substitute for the prompt brief. If a flaw survives, re-edit just that region, not the whole image.

   **Editing an existing photo (Path B/C)? Anchor on the ORIGINAL, not just a prototype.** Cheap
   prototype models drift on detail, so feed Nano Banana Pro the **original** photo (the source of
   truth for the real scene) and, where you made one, the approved prototype — `edit` accepts
   multiple `--image` (sent as `image_urls`). Pass the original **first**, then the prototype, and
   say which is which in the prompt:

   ```bash
   python scripts/falgen.py edit \
     --prompt "Use the FIRST image as the true scene — keep its room, materials, lighting and layout exactly — and the SECOND as the intended change. Produce the change at high fidelity." \
     --image _workings/[original_photo].jpg \
     --image _workings/[approved_prototype].png \
     --model fal-ai/nano-banana-pro/edit --arg resolution=2K \
     --run-log _workings/run-log_[slug].md \
     --out-dir . --name image_[slug]_final
   ```

   Or, for a fresh high-quality render from the locked prompt, use:

   ```bash
   python scripts/falgen.py generate \
     --prompt "[full locked prompt]" \
     --model fal-ai/nano-banana-pro \
     --aspect 16:9 --arg resolution=4K \
     --run-log _workings/run-log_[slug].md \
     --out-dir . --name image_[slug]_final
   ```

2. **Upscale only if needed** — a separate upscale is optional, for when you must exceed 4K or enlarge
   an external image. The default upscaler is **Recraft Crisp** (`fal-ai/recraft/upscale/crisp`), a
   faithful flat-cost upscaler:

   ```bash
   python scripts/falgen.py upscale \
     --image _workings/[actual_image_to_upscale].png \
     --run-log _workings/run-log_[slug].md \
     --out-dir . --name image_[slug]_final
   ```

   For a creative enlargement that adds detail and costs far more, opt in with
   `--model fal-ai/clarity-upscaler`.

Save the finished image at the work-folder root as `image_[slug]_final.png` or whatever exact filename
the helper prints. Tell the user the file path and remind them it is a **draft asset for their review**,
not published material.

## Clean up / enhance an existing photo (Path C)

Turn an amateur / phone / messaging-app shot into a professional-looking image. It reuses Stage 3's
mechanics — quality-edit the original with `nano-banana-pro/edit`, no prototype — but the intent is
**faithful correction, not change**, and the method is a **checklist, not iteration**. It works for
any subject — interiors, portraits, products, food, landscapes — so first check the **subject-types
table** in `references/cleanup-checklist.md` to learn what "faithful" means for this photo.

1. **Scan** `references/cleanup-checklist.md` — for each row, check the "tell-tale signs" against the
   photo. Keep only rows where you can name the sign you see. **Drop every issue the photo does not
   have** — including a fix for a problem that isn't there is an active transformation that changes a
   correct image (see "What NOT to do" in the checklist).
2. **Verify** — list your selected issues to the user with evidence ("I see converging verticals on
   the left wall, blown highlights in the window, and a warm cast — issues 1, 2, 4"). This catches
   over-selection before you spend a paid call.
3. **Assemble** one comprehensive correction prompt from the verified items only (the checklist has a
   skeleton), naming the key fixed features to keep. Confirm it with the user — it replaces
   prototyping.
4. **Run one pass** at 2K (keep the source aspect — do not pass `--aspect` unless recropping).
   Iterate only on a specific residual issue, not the whole image.

Hold the line on honesty:

- **Correct how it was captured, never what the subject is.** Keep every real feature and the layout.
  **Declutter only genuinely temporary items** (a remote, cables, tags, the photographer's
  reflection); never remove/alter a real feature to flatter it, and **never invent** a nicer view or
  finish — that misrepresents the subject.
- It is a **generative re-render**, so it can subtly drift; review against the original. For a listing
  or anywhere literal accuracy matters, a non-generative edit (Lightroom/Photoshop) is the faithful
  gold standard — this is a fast first-pass draft, not a document of record.

## Run logs

The helper always writes a machine-readable cost/session log to `./_falgen-costs.jsonl`. Newer entries
include the command, model, redacted arguments, input image references, output paths, dimensions, seed,
cost basis, and estimated cost. Temporary uploaded/CDN image URLs are omitted from the log.

Pass `--run-log _workings/run-log_[slug].md` on generation/edit/upscale/removebg calls to append a
human-readable markdown audit log covering:

- final or intermediate output path;
- input image path, where applicable;
- prompt and non-URL model arguments;
- model endpoint;
- seed, if used;
- output dimensions;
- cost basis and estimated cost.

This makes the result auditable and easier to reproduce. If you do not pass `--run-log`, use
`python scripts/falgen.py costs` plus the JSONL file as the audit trail.

## Model choices

The helper defaults to sensible models per stage; override with `--model [endpoint-id]`. The current
verified endpoint IDs, their stage, and approximate cost live in `references/fal-models.md`. fal.ai's
catalogue changes — if a model ID errors, check that reference and the fal.ai model gallery rather
than guessing. Anything in that file marked *(verify)* has not been confirmed against the live gallery
in this build; confirm before relying on it.

## Trying other models / comparing — but default first

Stick with the proven defaults unless the result is genuinely unsatisfactory. They are chosen
deliberately: schnell for cheap prototyping, Kontext dev for cheap faithful edits, Nano Banana Pro for
the quality final at up to 4K — a tested balance of quality, cost, and predictability. The first move
when a result disappoints is usually a better prompt or a targeted edit, not a model hunt.

Only when the defaults still fall short — for example, a model genuinely cannot render the subject,
style, or required in-image text — switch models. Any stage takes `--model`; the registry lists the
verified alternatives.

- **To compare**, run the same prompt/image through 2–3 candidates with distinct `--name`s
  (`cmp_schnell`, `cmp_fluxdev`, etc.), show them side by side, and let the live per-model cost line
  plus `costs` summary frame the quality-vs-cost trade-off for the user. Keep the bake-off small;
  each call spends real money.
- **Unfamiliar models:** the convenience flags are tuned to the known set (`--aspect` → `image_size`
  for FLUX / `aspect_ratio` for nano-banana / skipped for Kontext; edits send `image_urls` except the
  Kontext family's single `image_url`). For an endpoint the helper does not know, check its API page
  and pass anything the flags do not map via `--arg key=value` or `--arg-json '{...}'`. Live cost +
  download work for any endpoint.

Land back on a default once the experiment is done, unless the alternative is clearly and repeatably
better for that use case.

## The helper — `scripts/falgen.py`

One script, five subcommands. It reads `FAL_KEY` from the environment, uploads any local `--image` to
fal storage automatically, calls the model via `fal_client.subscribe`, downloads the result image(s)
locally, and prints the saved paths plus an approximate cost. Run `python scripts/falgen.py -h` or
`python scripts/falgen.py [subcommand] -h` for all options.

Key flags:

- `generate` — `--prompt` (required), `--model`, `--aspect`, `--num`, `--seed`, `--out-dir`, `--name`.
- `edit` — `--prompt` (required), `--image` (repeatable), `--model`, `--aspect`, `--num`, `--seed`,
  `--out-dir`, `--name`.
- `upscale` — `--image` (required), `--model`, `--factor`, `--out-dir`, `--name`.
- `removebg` — `--image` (required), `--model`, `--out-dir`, `--name`. Cuts the subject out to a
  transparent PNG. A utility for compositing into a deck/social tile, not part of the main
  generate→edit→upscale flow.
- `costs` — print the running cost tally for the session, with `--reset` to clear it.
- `recommend` — the recommended default model per stage, with **live pricing**. Read-only, no spend.
- `search "term"` — search the **live** fal catalogue (`--category`, `--limit`); each hit shown with
  its live price, category and licence. Read-only. Find a model the defaults don't cover — then still
  prefer the default unless it genuinely falls short.
- `--arg key=value` — escape hatch on any generation/edit/upscale/removebg subcommand to pass a raw
  model parameter the flags do not cover. Values may be JSON scalars, arrays, or objects, e.g.
  `--arg image_size='{"width":1200,"height":800}'`.
- `--arg-json '{...}'` — pass several raw model parameters as one JSON object, useful for nested
  options.
- `--run-log path.md` — append a human-readable markdown run log for auditability.
- `--verbose` — stream the model's own progress logs. Off by default.

If a call fails because the fal balance is exhausted, the helper detects it and prints clear guidance
rather than a raw stack trace.

A worked end-to-end run is in `examples/example-run.md`.

## Costs and balance

The generation response carries no cost field, so on every run `falgen.py` queries fal's live pricing
API and computes the cost from the actual output resolution or output count where possible, then prints
the step cost and a running session total (appended to `./_falgen-costs.jsonl`). Run:

```bash
python scripts/falgen.py costs
```

to print the full breakdown at the end of a chain, and tell the user the total. Watch the units in
`references/fal-models.md`:

- **Per-image** models are flat per output.
- **Per-megapixel** models cost more at higher resolution.
- **Per-compute-second** models vary by run time. fal does not return the run time, so the helper flags
  the step as time-billed rather than guessing a figure.

Balance is shown only if a fal **Admin** API key is set in `FAL_ADMIN_KEY`; the normal `FAL_KEY` cannot
read billing and may receive HTTP 403. Without an admin key, balance is skipped with a one-line note.
Give the user the estimated spend per step plus the session total; offer a live balance only if they
add an admin key.

## Principles

- **Drafts, not advice** — outputs are drafts for a qualified person to review, not finished published
  material.
- **Never invent** — do not fabricate costs, model IDs, capabilities, or output paths. If uncertain,
  say so.
- **Deterministic where it counts** — cost tracking, file naming, and model routing are deterministic;
  the LLM handles creative judgment only.
- **Honesty and calibration** — flag uncertainty, do not overstate quality, show costs.
- **Workspace hygiene** — deliverables at the work-folder root; interim files in `_workings/`;
  superseded versions in `_superseded/`.

## Data handling

Prompts and any reference images sent to fal.ai leave the user's control to a third-party tool, so
follow a PII/data-egress rule: **do not send confidential or sensitive content** to fal.ai. Keep real
source and output files on the local machine. When in doubt, do not egress; ask the user first.

## Pitfalls

1. **Do not skip Stage 1** — a well-crafted prompt saves expensive iterations later.
2. **Always confirm before Stage 3** — that is where the main spend usually is.
3. **Use actual saved paths** — examples are placeholders; use the paths printed by `falgen.py`.
4. **Kontext ignores aspect ratio** — it preserves the input image's dimensions. Do not pass `--aspect`
   for Kontext edits.
5. **Kontext accepts one image and one output** — the helper now fails early if you pass multiple
   images or `--num > 1` to a Kontext model.
6. **Use JSON args intentionally** — quote nested JSON correctly for your shell, or use `--arg-json`.
7. **Clarity upscaler is expensive** — use Recraft Crisp unless you specifically want creative detail
   enhancement.
8. **Background removal returns transparent PNG** — convert to JPG with a white background for
   messaging app delivery.
9. **fal balance requires an admin key** — `FAL_KEY` is not enough for billing balance display.

## Verification checklist

- [ ] Scope is image generation/editing, not layout/chart/diagram/deck work.
- [ ] User confirmed fal.ai egress and paid API usage before first API call.
- [ ] Prompt brief saved to `_workings/`.
- [ ] Every iteration saved with incrementing version or exact helper-generated filename.
- [ ] Actual printed output paths were used, not inferred paths.
- [ ] User confirmed go-ahead before Stage 3.
- [ ] Final prompt included the full locked prompt, not just a generic enhancement instruction.
- [ ] Final image saved at the work-folder root, not only in `_workings/`.
- [ ] `--run-log _workings/run-log_[slug].md` used, or JSONL cost/session log reviewed.
- [ ] Cost summary printed via `falgen.py costs`.
- [ ] User told the file path and reminded it is a draft.
