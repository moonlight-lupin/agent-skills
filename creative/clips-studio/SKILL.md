---
name: clips-studio
description: >
  Generate short marketing/social VIDEO clips via fal.ai through a staged studio
  workflow — brainstorm the motion, draft cheaply, then produce the final at
  quality. Three modes: text-to-video (a clip from a prompt, no source image);
  animate (bring a still image to life — a product, people, b-roll, a space); and
  camera-move (a gentle push-in, pan, tilt or shallow orbit over a still, including
  an interior "3D view"). Use when the user wants to "make a video/clip", "generate
  a video from text", "animate this image/photo", "create a marketing reel / social
  video / teaser", "do a 3D / parallax move", "pan/zoom/orbit a shot", or when they
  mention fal.ai, Kling, Veo or Seedance for video. Do not use for still images (use
  image-studio), Canva-style template designs, slide decks, data charts/dashboards,
  or flowcharts/diagrams. Carries an honesty discipline for real subjects: never use
  text-to-video to depict a real, identifiable place, product or person. Do not
  override platform-native video tools where the host environment requires them.
version: 1.1.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
---

# Clips Studio

Generate a short video clip through deliberate stages — **brainstorm → draft cheaply → produce the
final at quality** — using fal.ai. The moving-image sibling of `image-studio`. The point of the
staging is cost and control: video is the dearest thing on fal (roughly **10–100× a still**), so you
lock the idea on a cheap model first, then spend on a quality model only once, on the agreed clip.

This skill **generates files locally** for the user to review and use. It never posts, publishes, or
sends anything as final collateral.

## Scope and routing

Use this skill only when all of the following are true:

1. The task is generative video — a clip from a prompt, animating a still, or a camera move over a
   still — not slide/deck production, charting, dashboarding, or design-template automation.
2. The user is comfortable with fal.ai egress and paid API usage.
3. The local helper workflow is available, or the user is asking you to prepare the brief for it.

Do **not** use this skill for:

- Still images (use `image-studio`), Canva-style templates, slide decks, data charts, dashboards,
  flowcharts or diagrams.
- Confidential or sensitive image/document processing.
- Any host environment where a native video-generation tool is explicitly mandated.

## Three modes — choose this first

Pick the one that matches what the user has and wants:

- **Text-to-video** (`generate`) — a clip **from a prompt, with no source image**. Best for concept,
  abstract/motion-graphic, brand-mood or b-roll-style clips with no still to start from. It
  **invents everything**, so it is **never** the way to depict a *real* place, product or person —
  `animate` a real photo for that.
- **Animate a still** (`animate`) — bring an **existing image** to life: a product turning, people
  interacting, a scene, foliage/water/light. The clip animates **what is in the frame**.
  - **Adding a new subject to an EMPTY scene (people to a room, product to a set) is a two-step job.**
    Video models animate what they see; they don't reliably *invent* believable new subjects. So
    **first add the subject to the still** with `image-studio` (an instruction edit), review it,
    **then animate the populated still here.**
- **Camera move** (`camera`) — extrapolate a **camera motion** over a still: a slow push-in, pan,
  tilt, shallow orbit or pull-out (a "3D"/parallax feel; an interior "3D view"). The subject can be
  static; the *camera* moves. This is the riskiest mode for honesty (it invents unseen geometry) —
  keep moves **gentle** and read `references/motion-honesty-guide.md` first.

All three use the same staging below and the same `scripts/falvid.py` helper (`generate` / `animate`
/ `camera`).

## Before you start — egress and preflight

Generating a clip sends the **prompt** (and for `animate`/`camera`, the **start image you provide**)
to fal.ai, a third-party US service, and the result clip is downloaded from its CDN. That is external
data egress.

Before any API call:

1. Confirm the task is in scope.
2. Confirm explicit user go-ahead for fal.ai egress and paid API usage before the first generation in
   a session.
3. Confirm explicit user go-ahead again before the costlier Stage-3 production run — **quote the
   estimated cost** (video clips can be several dollars each).
4. Check that `scripts/falvid.py` exists, dependencies are installed, `FAL_KEY` is set, and the
   working directory is writable.
5. For `animate`/`camera`, use only non-confidential images the user has rights to process through
   fal.ai.
6. Use the exact output paths printed by `falvid.py`; do **not** infer filenames from examples.

Never feed confidential or sensitive imagery to fal.ai — e.g. a private person's photo, confidential
documents, or anything under NDA. If the user asks to animate something sensitive, stop and flag the
egress issue rather than uploading it.

Brainstorming in Stage 1 is pure chat and has no egress, so you can always draft the brief first and
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

## Stage 1 — Brainstorm the brief (no API call)

A good clip starts from a precise brief, so invest here before spending. Interview the user and agree:

- **The source** — for `animate`/`camera`, which **still** are we using? (For `animate` of an empty
  scene, has the subject been added via `image-studio` yet?) For `generate`, there's no still — agree
  the scene to describe. Keep any original in `_workings/` untouched.
- **The motion / subject** — *name the action, not a mood.* "A nice product video" is vague; "the
  bottle slowly rotates on a plinth, soft studio light sweeping across the label" is concrete. For
  `camera`, name the move in cinematographic terms ("slow dolly push-in", "pan left", "shallow orbit").
- **Length** — default **5 seconds**. Keep it short; cost scales with every second. 4–6s suits a
  social/web loop.
- **Aspect & orientation** — anchor to the destination: 16:9 web/hero, 9:16 reel/story, 1:1 social.
  **For `animate`/`camera`, match the output to the source's orientation and pass `--aspect`
  explicitly** (see the check below). For `generate` there's no source, so choose the target aspect.
- **Audio** — **off by default.** Don't fabricate ambient sound or voices for a real subject; the
  user can add music in their editor. (Audio also adds cost on the models that support it.)

**Aspect & orientation — check the source before you generate** *(applies to `animate`/`camera`)*.
Compare the **source still's orientation** to the **intended video frame** (usually 16:9 for web,
9:16 for reels). If they differ — e.g. a **portrait or square phone shot** for a 16:9 video —
**don't just generate**:

1. **First, ask the user for a properly-oriented photo** — a landscape shot for a landscape clip, a
   vertical shot for a vertical clip. A source that already matches the target frame is the cleanest,
   most honest result.
2. **If the user wants to proceed with the mismatched source anyway, check in on which approach** —
   never decide it silently:
   - **(2) Pillarbox / letterbox** — keep the source's orientation and place the clip inside the
     target frame with side/top fill (bars, or a soft blur of the same shot). **Honest — nothing is
     invented**; you just get bars. Usually a step in the user's video editor.
   - **(3) Generatively extend (outpaint) the still to the target aspect first, then animate** —
     full-bleed, but the model **invents the surroundings that weren't photographed**. Combo with
     `image-studio` (an instruction edit at the target `--aspect`). Two **musts** before any video
     spend: (a) **ground the extension** — ask the user for reference images of what's actually around
     the subject so the model *reconstructs* the real context rather than inventing it; (b) **confirm
     the extended still with the user BEFORE animating** — take corrections, re-edit, approve, *then*
     animate. Illustrative only; never present it as the real setting.
3. **Never (1) force-crop to the target aspect** — on a mismatched source the model centre-crops and
   discards most of the subject (a tall building loses its top and bottom). It is **off the table**.

When the orientation **does** match, still pass `--aspect` to match the source so the helper doesn't
fall back to 16:9 and crop.

Save the agreed brief to `_workings/` (for example `_workings/brief_[slug].md`) so the run is
auditable. Keep prompts free of confidential detail. **This step replaces a cheap prototype for the
idea — confirm the brief (and the start image, for `animate`/`camera`) before the first paid call.**

## Stage 2 — Draft cheaply

Render a draft on the cheap model so you can react for a fraction of the final cost.

- **`animate`** — default **Kling 2.5 Turbo Pro** (`fal-ai/kling-video/v2.5-turbo/pro/image-to-video`,
  ~$0.07/s → ~$0.35 for 5s):

  ```bash
  python scripts/falvid.py animate \
    --prompt "[the agreed motion]" \
    --image _workings/[source-still].png \
    --duration 5 --aspect 16:9 \
    --run-log _workings/run-log_[slug].md \
    --out-dir _workings --name vid_[slug]_draft
  ```

- **`camera`** — default **Seedance 1.5 Pro**; `--move` offers gentle presets (`push-in`, `pull-out`,
  `pan-left/right`, `tilt-up/down`, `orbit`, `crane-up`), and `--static` locks the camera entirely:

  ```bash
  python scripts/falvid.py camera --move push-in \
    --image _workings/[still].png --duration 5 --aspect 16:9 \
    --out-dir _workings --name vid_[slug]_draft
  ```

- **`generate`** (text-to-video) — default a cheap t2v draft model (e.g. **Wan 2.2**); no `--image`:

  ```bash
  python scripts/falvid.py generate \
    --prompt "[the scene to create]" \
    --duration 5 --aspect 16:9 \
    --out-dir _workings --name vid_[slug]_draft
  ```

Watch the draft **for motion problems** — warping faces/hands (the hardest thing for every model; see
`references/motion-honesty-guide.md`), the camera drifting through walls, objects morphing, jittery
motion. On feedback, the **first move is a better prompt, not a pricier model**: tighten the action,
reduce the number of moving subjects, slow the camera, then re-draft. Loop cheaply until the motion is
right. Always use the exact saved paths printed by the helper.

## Stage 3 — Produce the final

Once the motion is approved on the draft, **confirm the go-ahead and the cost again** — this is the
main spend. Put the estimate to the user explicitly, e.g. *"final as a 5s Veo 3.1 clip at 1080p, no
audio, ~$1.00 — go ahead?"*

- **`animate` / `generate` (people, product, general realism)** → **Veo 3.1**
  (`fal-ai/veo3.1/image-to-video`, or `fal-ai/veo3.1` for text-to-video) — best motion and realism;
  ~$0.20/s (no audio) / $0.40/s (audio), ×2 at 4K. Leaner: **Kling 3.0 Pro** (`fal-ai/kling-video/v3/pro/...`).
- **`camera` (camera move)** → **Seedance 1.5 Pro** (`fal-ai/bytedance/seedance/v1.5/pro/image-to-video`)
  is already the `camera` default — strongest camera control and a true `camera_fixed` lock; ~$0.26
  for a 720p/5s clip. For a premium native 4K move, **Kling v3 4K** (`fal-ai/kling-video/v3/4k/image-to-video`).

```bash
python scripts/falvid.py animate \
  --prompt "[the approved motion]" --image _workings/[source-still].png \
  --model fal-ai/veo3.1/image-to-video --duration 5 --resolution 1080p --aspect 16:9 \
  --run-log _workings/run-log_[slug].md \
  --out-dir . --name vid_[slug]_final
```

Save the finished clip at the work-folder root as `vid_[slug]_final.mp4`, or whatever exact filename
the helper prints. Tell the user the file path and remind them it is a **draft clip for review** — not
published material, and not a literal record of a real place, product or person.

## The honesty line

A moving clip is more persuasive than a still, so the discipline scales with how *real* the subject
is (full detail in `references/motion-honesty-guide.md`):

- **Don't fabricate facts about a real thing.** Don't invent a feature, finish, view or capability a
  real product/space doesn't have; don't imply an occupancy, clientele or popularity that isn't real.
  **Text-to-video invents everything** → never use it to depict a real, identifiable subject;
  `animate` a real photo instead.
- **Camera moves invent geometry the camera never saw.** A slow push-in or a locked camera invents
  almost nothing; an aggressive orbit or fly-through hallucinates whole spaces. Prefer gentle moves,
  prefer `--static` where it works, and never present an extrapolated clip as a real walkthrough or a
  faithful layout.
- **People & likeness.** Use generated, non-identifiable people for mood; never animate an
  identifiable real person without consent, and never upload a private person's photo.
- **When literal accuracy matters** (a listing, a spec claim), a real shoot or a proper 3D capture is
  the faithful gold standard — this is a fast first-pass marketing draft.

## Model choices

The helper defaults to sensible models per mode; override with `--model [endpoint-id]`. The current
verified endpoint IDs, their role and approximate cost live in `references/fal-video-models.md`.
fal.ai's catalogue changes — if a model ID errors, check that reference and the fal.ai model gallery
rather than guessing. Anything marked *(verify)* there has not been confirmed against the live gallery
in this build (several **text-to-video** IDs/rates are *(verify)* — confirm before relying on the
cost). Stick with the proven defaults unless a result is genuinely unsatisfactory; the first fix is a
better prompt or a gentler move, not a model hunt.

## The helper — `scripts/falvid.py`

One script, three generation subcommands plus `costs`. It reads `FAL_KEY` from the environment,
uploads any local `--image` to fal storage, calls the model via `fal_client.subscribe` (**which polls
the async video queue and blocks until the clip is ready — this can take several minutes; don't
interrupt it**), downloads the MP4 locally, and prints the saved path plus an estimated cost. Run
`python scripts/falvid.py -h` or `python scripts/falvid.py [subcommand] -h` for all options.

Key flags:

- `generate` (text-to-video) — `--prompt` (required), `--duration`, `--resolution`, `--aspect`,
  `--audio`, `--seed`, `--model`, `--out-dir`, `--name`. **No `--image`.**
- `animate` — `--prompt` (required), `--image` (required), then `--duration`/`--resolution`/`--aspect`/
  `--audio`/`--seed`/`--model`/`--out-dir`/`--name`.
- `camera` — `--move` (gentle preset) and/or `--prompt`, `--static` (lock the camera), `--image`
  (required), then the same flags.
- `costs` — print the running cost tally for the session, with `--reset` to clear it.
- `recommend` — the recommended default model per mode (generate/animate/camera), with **live
  pricing**. Read-only, no spend.
- `search "term"` — search the **live** fal catalogue (`--category`, `--limit`); each hit shown with
  its live price, category and licence. Read-only. Find a model the defaults don't cover — then still
  prefer the default unless it genuinely falls short.
- `--arg key=value` / `--arg-json '{...}'` — escape hatch to pass a raw model parameter the flags
  don't cover (e.g. `--arg negative_prompt='blurry, distorted'`, `--arg end_image_url=...`).
- `--run-log _workings/run-log_[slug].md` — append a human-readable markdown audit log.
- `--verbose` — stream the model's own progress logs. Off by default.

The helper maps the start-image argument per model (`image_url`, or `start_image_url` for Kling v3),
casts `--duration` to the type each model wants, only sends `generate_audio` to models that accept it,
and applies `camera_fixed` for `--static` on Seedance (or adds a "static shot" instruction for models
without the parameter). If a call fails because the fal balance is exhausted, it prints clear guidance
rather than a raw stack trace. A worked end-to-end run is in `examples/example-run.md`.

## Costs and balance

Video billing is messy — per-second (Kling, Veo) or per-clip/per-token (Seedance, Hailuo), and the
exact figure depends on output duration, fps, resolution and audio, which the API does **not** return.
So `falvid.py` leads with a **verified-rate estimate** from its registry (mirrors
`references/fal-video-models.md`) computed from the requested duration and clearly flagged as an estimate
(there is no live pricing-API lookup for video). **The fal dashboard is the authoritative
charge.** Each run is appended to `./_falvid-costs.jsonl`; run `python scripts/falvid.py costs` for the
session breakdown. Quote the estimate before the final render and keep drafts cheap and short. Balance
is shown only if a fal **Admin** key is set in `FAL_ADMIN_KEY`; the normal `FAL_KEY` cannot read
billing (HTTP 403).

## Principles

- **Drafts, not advice** — outputs are drafts for a person to review, not finished published material.
- **Never invent** — do not fabricate costs, model IDs, capabilities, or output paths. If uncertain,
  say so. Don't fabricate facts about a real subject in a clip.
- **Deterministic where it counts** — cost tracking, file naming and model routing are deterministic;
  the LLM handles creative judgment only.
- **Honesty and calibration** — flag uncertainty, don't overstate quality, show costs.
- **Workspace hygiene** — deliverables at the work-folder root; interim files in `_workings/`;
  superseded versions in `_superseded/`.

## Data handling

Prompts and any start image sent to fal.ai leave the user's control to a third-party tool, so follow a
PII / data-egress rule: **do not send confidential or sensitive content** to fal.ai. Keep real source
and output files on the local machine. When in doubt, do not egress; ask the user first.

## Pitfalls

1. **Match the source orientation** — the models don't reliably inherit it; Seedance defaults to 16:9
   and centre-crops a portrait/square still. Pass `--aspect` to match (a 3:4 source → `--aspect 3:4`).
2. **Hands and fine object interaction break** — holding/pouring/gripping is the hardest motion for
   every model. Design it out (park object-handling subjects), don't pay a pricier model to fix it.
3. **Screens/TVs fabricate content** — any "alive" cue makes the model cut/zoom the on-screen image;
   keep screen motion out of the brief, or let a camera move mask it.
4. **Confirm before Stage 3** — that's the main spend; a 5s Veo clip with audio is ~$2.
5. **Use actual saved paths** — examples are placeholders; use the paths printed by `falvid.py`.
6. **Text-to-video is never for a real subject** — it invents everything; `animate` a real photo.
7. **Video is slow** — a single clip can take several minutes; the helper blocks while fal renders it.
8. **Text-to-video rates are *(verify)*** — sanity-check the first `generate` cost on the dashboard.

## Verification checklist

- [ ] Scope is video generation, not deck/chart/diagram/design-template work.
- [ ] User confirmed fal.ai egress and paid API usage before the first API call.
- [ ] Source orientation checked; `--aspect` passed to match (or the mismatch handled via pillarbox /
      grounded+confirmed outpaint — never a force-crop).
- [ ] Brief saved to `_workings/`; drafted cheaply and iterated before the quality render.
- [ ] Actual printed output paths were used, not inferred paths.
- [ ] User confirmed go-ahead and saw the cost estimate before Stage 3.
- [ ] Text-to-video was not used to depict a real, identifiable subject.
- [ ] Final clip saved at the work-folder root; user told the path and reminded it is a draft.
- [ ] `--run-log` used, or the JSONL cost log reviewed; cost summary printed via `falvid.py costs`.
