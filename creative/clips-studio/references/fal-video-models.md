# fal.ai VIDEO model registry — Clips Studio

Endpoint IDs the helper (`scripts/falvid.py`) uses, by mode. **fal.ai's catalogue changes often** —
if an ID errors, check the live gallery at https://fal.ai/models (filter to *Text to Video* /
*Image to Video*).

These are **text-to-video** (`generate`, a prompt → an MP4) and **image-to-video**
(`animate` / `camera`, a start image + a prompt → an MP4) endpoints. They run **async** —
`falvid.py` uses `fal_client.subscribe`, which polls the queue and blocks until the clip is ready
(often a few minutes per clip).

**Cost is an estimate, not live-exact.** Video is billed per-second (Kling, Veo) or per-clip/
per-token (Seedance, Hailuo), and the exact charge depends on output **duration × fps × resolution ×
audio**, which the API does **not** return. `falvid.py` therefore computes a **verified-rate
estimate** from the rates below × the *requested* duration and flags it as an estimate (it does not
query a live pricing API for video). **The fal dashboard is the authoritative charge.** Rates
verified against fal's pricing pages on **24 Jun 2026**; *(verify)* marks anything not confirmed live
this build.

## Text-to-video — `generate` (a clip from a prompt, no source image)

Rates here are **`(verify)`** — t2v IDs/prices move and weren't all confirmed live this build; the
helper's estimate is deliberately conservative, and the fal dashboard is authoritative. **Never use
text-to-video to depict a real, identifiable subject** (it invents everything) — `animate` a real
photo instead.

| Model | Endpoint id | Role | Rate | Notes |
|---|---|---|---|---|
| Wan 2.2 | `fal-ai/wan/v2.2-a14b/text-to-video` | **Draft (default for `generate`)** | ~$0.10 / s *(verify)* | Cheap t2v draft. If the ID errors, try `fal-ai/wan-pro` or fall back to a Kling/LTX t2v. |
| Veo 3.1 | `fal-ai/veo3.1` | **Quality final** | $0.20/s no-audio · $0.40/s audio · ×2 4K | Veo 3.1 text-to-video — best realism + native audio. (The base id is the t2v endpoint; `…/image-to-video` is the i2v one.) |
| Kling 2.5 Turbo Pro | `fal-ai/kling-video/v2.5-turbo/pro/text-to-video` | Alt | ~$0.224/s no-audio · ~$0.28/s audio *(verify)* | Note: Kling **t2v prices higher than its i2v** ($0.07/s). 1080p. |
| Kling 3.0 Pro | `fal-ai/kling-video/v3/pro/text-to-video` | Alt (cinematic) | ~$0.224–0.336/s *(verify)* | Up to 15s, native audio. |
| LTX-2 | `fal-ai/ltx-2-19b/text-to-video` *(verify)* | Alt (very cheap) | ~$0.0018 / MP | Per-megapixel; cheap, lower fidelity. `falvid.py` estimates ~249 MP for 5s/1080p@24fps → ~$0.45. |
| Wan-Pro | `fal-ai/wan-pro` *(verify)* | Alt (fallback) | ~$0.10 / s *(verify)* | Fallback if the default Wan 2.2 ID errors. |
| Seedance 1.5 Pro | `fal-ai/bytedance/seedance/v1.5/pro/text-to-video` | Alt | ~$0.26 / clip *(verify)* | Per-clip; 4–12s. *(verify)* — confirm endpoint exists on the live gallery. |
| Hailuo 2.3 Pro | `fal-ai/minimax/hailuo-2.3/pro/text-to-video` | Alt | ~$0.49 / clip *(verify)* | Per-clip; ~5s. *(verify)* — confirm endpoint exists on the live gallery. |

## Image-to-video — `animate` (bring a still to life: product, people, a space, motion)

| Model | Endpoint id | Role | Rate | Notes |
|---|---|---|---|---|
| Kling 2.5 Turbo Pro | `fal-ai/kling-video/v2.5-turbo/pro/image-to-video` | **Draft (default for `animate`)** | **$0.07 / s** | Cheap workhorse for iterating on motion. Up to 10s, 1080p. `image_url`; `duration` is a **string** enum. |
| Veo 3.1 | `fal-ai/veo3.1/image-to-video` | **Quality final (default)** | **$0.20/s** no-audio · **$0.40/s** audio · **×2 at 4K** | Google Veo 3.1 — best human motion + realism + native audio. ~8s. `image_url`, `aspect_ratio` (default `auto`). A 5s/1080p clip ≈ $1 (no audio) / $2 (audio). |
| Veo 3.1 Fast | `fal-ai/veo3.1/fast/image-to-video` | Quality (cheaper) | ~$0.10/s no-audio · ~$0.20/s audio *(verify)* | Faster/cheaper Veo tier for budget runs. |
| Kling 3.0 Pro | `fal-ai/kling-video/v3/pro/image-to-video` | Quality (leaner) | ~$0.11–0.20 / s | Cinematic, fluid motion, native audio; up to 15s, 1080p. Uses `start_image_url`. `falvid.py` uses the midpoint ($0.15/s) for estimates — the dashboard is authoritative. |

## Image-to-video — `camera` (extrapolated camera motion over a still)

| Model | Endpoint id | Role | Rate | Notes |
|---|---|---|---|---|
| Seedance 1.5 Pro | `fal-ai/bytedance/seedance/v1.5/pro/image-to-video` | **Default for `camera`** | **~$0.26 / clip** (720p/5s w/audio; scales with tokens) | ByteDance — strongest **camera granularity** (pan, zoom, dolly, orbit) and a true **`camera_fixed`** lock (used by `--static`). `image_url` + optional `end_image_url`; `resolution` 480p/720p (helper defaults 720p); `duration` 4–12 int; `generate_audio`. |
| Kling v3 4K | `fal-ai/kling-video/v3/4k/image-to-video` | Premium native 4K | **$0.42 / s** | Native 4K, no upscaling; `duration` "3"–"15"; uses **`start_image_url`**; camera via prompt language. The dearest option — reach for it only when 4K is genuinely needed. |
| Hailuo 2.3 Pro | `fal-ai/minimax/hailuo-2.3/pro/image-to-video` | Alt | ~$0.49 / clip | MiniMax; 1080p, ~5s; camera via prompt. |

## Common inputs (and how `falvid.py` maps the flags)

- **Start image** — `image_url` for most models; **`start_image_url`** for the Kling v3 family. The
  helper picks the right key automatically; override with `--arg`.
- **`prompt`** — describes the action *and* the camera move. Name moves in cinematographic terms
  ("slow dolly push-in", "pan left", "shallow orbit"); say "static shot, locked-off camera" to hold
  still on models without a `camera_fixed` parameter.
- **`duration`** — seconds. Kling wants a **string** ("5"); Seedance/Veo take an **int**. The helper
  casts per model. Keep it short — cost scales with every second.
- **`resolution`** — model-dependent (Seedance 480p/720p; Veo 720p/1080p/4K; Kling v3 native 4K).
  Only sent when you pass `--resolution`, except Seedance defaults to `720p`.
- **`aspect_ratio`** — for `animate`/`camera`, only sent when you pass `--aspect`; the models do
  **not** reliably inherit the still's framing (Seedance defaults to 16:9 and centre-crops a
  portrait/square still), so **pass `--aspect` to match the source**. For `generate` there's no
  source, so the helper sends the target aspect (default 16:9).
- **`generate_audio`** — **default OFF** (don't fabricate ambience). Only sent to models that accept
  it (Veo, Kling v3, Seedance). Turning it on raises Veo's per-second rate.
- **`camera_fixed`** — Seedance only; set by `--static`. Other models get a "static shot" instruction
  in the prompt instead.
- **`seed`** — `--seed` for repeatability. **`negative_prompt`** — via `--arg negative_prompt='…'`
  (Kling defaults to `"blur, distort, and low quality"`).
- **Output** — every model returns a `video` object with a `url` (MP4); the helper downloads it to
  `--out-dir` as `[name].mp4`.

## Cost reality check

A full **brainstorm → draft → final** run is dominated by the **final clip**:

- Drafts on **Kling 2.5 Turbo Pro** are ~$0.35 for 5s — iterate freely.
- A **Veo 3.1** people-final is ~$1 (5s/1080p, no audio) to ~$2 (with audio); **4K roughly doubles**
  it. A **Seedance** camera-final is ~$0.26.
- Keep finals **short** (4–6s) and audio **off** unless asked. Quote the estimate before the final
  render — see the SKILL.md "Costs & balance" section.

## Deferred / not wired here

- **End-frame / first-last-frame** transitions, **multi-shot** prompts, **lip-sync / dialogue**,
  **LoRA-trained styles**, and **dedicated 3D / Gaussian-splat tour** generators — possible later
  via `--arg`/new models, but not defaults. For a faithful walkthrough, a real shoot or a proper 3D
  tour is the gold standard (see `motion-honesty-guide.md`).
