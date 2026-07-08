# fal.ai model registry — Marketing Image Studio

Endpoint IDs the helper (`scripts/falgen.py`) uses, by stage. **fal.ai's catalogue changes
often** — if an ID errors, check the live gallery at https://fal.ai/models.

**Pricing is live, not hardcoded.** `falgen.py` fetches each model's unit price from fal's pricing
API (`GET /v1/models/pricing`) on every run and computes the cost from the *actual output
resolution*. Read the **unit** carefully — it differs by model:

- **per megapixel** (schnell, flux dev, Clarity) — cost scales with resolution; a 4K/upscaled image
  costs many times a 1MP one.
- **per image** (nano-banana family, Kontext pro) — flat per output.
- **per compute-second** (Kontext **dev**) — varies by run time, and fal does **not** return the
  run time, so the exact cost can't be shown locally; `falgen` flags it and the fal dashboard has
  the real figure.

All figures below are the **unit prices verified against the live pricing API on 23 Jun 2026**;
*(verify)* marks IDs not confirmed live this build.

## Stage 2 — cheap prototyping (text-to-image)

| Model | Endpoint id | Unit price | Notes |
|---|---|---|---|
| FLUX.1 [schnell] | `fal-ai/flux/schnell` | **$0.003 / MP** | Default. Fast, very cheap; 1–4 steps. Uses `image_size` enum (not `aspect_ratio`). |
| FLUX.1 [dev] | `fal-ai/flux/dev` | **$0.025 / MP** | Higher quality than schnell. |

**FLUX `image_size` presets:** `square_hd`, `square`, `portrait_4_3`, `portrait_16_9`,
`landscape_4_3`, `landscape_16_9`, or a custom `{"width": W, "height": H}`. The helper maps
`--aspect 16:9 → landscape_16_9`, `1:1 → square_hd`, `9:16 → portrait_16_9`, `4:3 → landscape_4_3`,
`3:4 → portrait_4_3`. For anything else pass `--arg image_size=...`.

FLUX text-to-image inputs: `prompt`, `image_size`, `num_images`, `num_inference_steps` (default 4),
`guidance_scale` (default 3.5), `seed`, `output_format` (`jpeg`/`png`), `enable_safety_checker`.

## Stage 2/3 — editing (image-to-image, instruction edits)

| Model | Endpoint id | Stage | Unit price | Notes |
|---|---|---|---|---|
| FLUX Kontext [dev] | `fal-ai/flux-kontext/dev` | **2 (default)** | **$0.00125 / compute-second** (≈ a few tenths of a cent per quick edit — the cheapest editor, but variable and not shown locally) | Instruction edit; **preserves the input image's dimensions** (no `image_size`/`aspect_ratio`). Single `image_url`. |
| Nano Banana Pro edit | `fal-ai/nano-banana-pro/edit` | **3 (default)** | **$0.15 / image (1K), $0.30 / image (4K)** | Gemini 3 Pro Image. Highest fidelity, accurate text, `resolution` 1K/2K/4K. `image_urls` (list). 4K doubles the per-image cost. |
| Nano Banana edit | `fal-ai/nano-banana/edit` | alt | **$0.0398 / image** | Gemini 2.5 Flash Image. Conversational edit; `image_urls` (list). |
| FLUX Kontext [pro] | `fal-ai/flux-pro/kontext` | alt | **$0.04 / image** | Higher quality than dev; flat per image (not cheaper than nano-banana). Single `image_url`. |
| GPT Image 2 edit | `openai/gpt-image-2/edit` | alt | **tiered** — high-q 1024² ~$0.13, up to ~$0.40 at 4K, **+ the input image is always billed at the high-fidelity rate** so edits cost more than the figure suggests; + token charges | **The "accurate in-image text" option.** `image_urls` (list), `image_size` (default `auto`), `quality` (default high), optional `mask_url` for region edits. Pricier and multi-component → helper cost is a rough estimate; exact on the dashboard. |

**Default edit chain:** Stage 2 → `fal-ai/flux-kontext/dev` (cheapest; dimension-preserving); Stage 3
→ `fal-ai/nano-banana-pro/edit` (quality, up to 4K).

- **Kontext (dev/pro)** inputs: `prompt`, **`image_url`** (single), `guidance_scale`,
  `num_inference_steps`, `seed`. No `num_images`/`aspect_ratio`/`image_size` — output follows the
  input. (The helper sends `num_images` only when `--num > 1`, and skips aspect for Kontext.)
- **Nano Banana Pro edit** inputs: `prompt`, **`image_urls`** (list), `num_images` (1–4), `seed`,
  `aspect_ratio` (`auto`/`21:9`…/`9:16`), `output_format`, **`resolution`** (`1K`/`2K`/`4K`, via
  `--arg resolution=2K`), `safety_tolerance`. Output: `images[]` with `url`/`file_name`/`content_type`.

## Stage 3 — quality render (text-to-image)

| Model | Endpoint id | Unit price | Notes |
|---|---|---|---|
| Nano Banana | `fal-ai/nano-banana` | ~$0.039 / image *(verify)* | Strong instruction adherence; uses `aspect_ratio`. |
| Nano Banana Pro | `fal-ai/nano-banana-pro` | **$0.15 / image** | a.k.a. Nano Banana 2 (Gemini 3 Pro Image). 1K/2K/4K, accurate text, character consistency. Best quality. |
| GPT Image 2 | `openai/gpt-image-2` | **tiered** by `quality`×size — high-q 1024² ~$0.13, 4K ~$0.40; medium ~$0.034; + tokens | **Non-default alternative for accurate IN-IMAGE TEXT.** Uses `image_size` presets (like FLUX; custom must be multiples of 16, max edge 3840). `quality` defaults to **high** — pass `--arg quality=medium` to cut cost. Cost is multi-component → helper figure is a rough estimate. |
| Recraft V3 | `fal-ai/recraft/v3/text-to-image` (also `…/image-to-image`) | $0.04 / image ($0.08 for **vector**) | **Brand/design alternative** — brand-style control, **vector/SVG** output, strong text. `style` = `realistic_image` / `digital_illustration` / `vector_illustration` (set via `--arg style=…`); uses `image_size` presets. Best non-default for on-brand graphics / scalable print assets. (Newer **Recraft V4.1 Pro** exists — `fal-ai/recraft/v4.1/pro/text-to-image` — if you want the latest tier.) |
| FLUX Pro v1.1 | `fal-ai/flux-pro/v1.1` | *(verify)* | High-quality FLUX option (also `…/v1.1-ultra`). |

> **When to reach for GPT Image 2 (and only then):** when the image must contain **legible, correct
> text** baked in (a sign, badge, label) — its standout strength. Otherwise the defaults win on cost
> and predictability: Nano Banana Pro already renders most text adequately, and for brand headings
> you should place real text *after*. GPT Image 2 defaults to
> `quality=high` (dear) and its edit endpoint always bills the input image at the high-fidelity rate.

## Stage 3 — upscaling (usually optional)

**Prefer getting the final at the size you need straight from the Stage-3 edit:** Nano Banana Pro
edit outputs up to **4K at a flat $0.15** (`--arg resolution=4K`). 4K covers decks, social, web and
most print, so a separate upscale is **only** needed to exceed 4K or to enlarge an *external* image.

| Model | Endpoint id | Unit price | Notes |
|---|---|---|---|
| Recraft Crisp Upscale | `fal-ai/recraft/upscale/crisp` | **$0.004 / image (flat)** | **Default.** Faithful — enlarges without inventing detail; ~4× (1024→4096 verified). Predictable cost. Takes `image_url`; returns webp. |
| Aura SR | `fal-ai/aura-sr` | ~$0.0008 / compute-second | Faithful GAN super-res; very cheap but time-billed (cost not shown locally). |
| DRCT Super-Resolution | `fal-ai/drct-super-resolution` | $0.0045 / MP | Faithful; ~$0.08 at 16 MP. |
| Clarity Upscaler | `fal-ai/clarity-upscaler` | $0.03 / MP of output | **Creative** upscaler — *adds* detail (can alter the image); the dearest (~$0.48 at 16 MP). Use via `--model` only when you specifically want its embellishment. Takes `image_url` + `upscale_factor`. |
| ESRGAN | `fal-ai/esrgan` | ~$0.00111 / compute-second | Classic faithful GAN upscaler; cheap, time-billed. |

> **Cost reality check:** with the recraft-crisp default + 4K-from-edit, a full
> brainstorm→prototype→final→(optional)upscale run is dominated by the single **Nano Banana Pro
> edit (~$0.15)**; everything else — prototyping, the Kontext edit, the recraft upscale — is well
> under a cent. Spend once, on the agreed image, at the resolution you actually need.

## Background removal (utility — `falgen.py removebg`)

Cut a subject out to a transparent PNG for compositing into a deck/social tile. A separate capability
from the generate→edit→upscale spine; reach for it only when you need a cut-out.

| Model | Endpoint id | Unit price | Notes |
|---|---|---|---|
| Bria RMBG 2.0 | `fal-ai/bria/background/remove` | **$0.018 / image (flat)** | **Default.** Production-grade and **trained on licensed commercial data** (clean provenance — preferable for commercial use). Takes `image_url`. |
| BiRefNet v2 | `fal-ai/birefnet/v2` | compute-second (cheap, varies) | Very high-detail edges (hair / fine masks); time-billed so cost isn't shown locally. |
| rembg | `fal-ai/imageutils/rembg` | *(verify)* | Basic, fast remover. |

## Account balance

`falgen.py` shows your balance only if a fal **Admin** API key is set in **`FAL_ADMIN_KEY`** (a
normal generation `FAL_KEY` is **not** permitted — `GET /v1/account/billing` returns HTTP 403).
Create an Admin key in the fal dashboard if you want per-run balance display; otherwise balance is
skipped with a one-line note and only the computed cost + running total are shown.

## Deferred — video (NOT in v1)

Video models exist on fal.ai (e.g. Kling, Veo, Seedance families) but are **out of scope** for this
version — they need async job-polling and carry much higher per-clip cost. Planned for a later
version; do not wire them in here.