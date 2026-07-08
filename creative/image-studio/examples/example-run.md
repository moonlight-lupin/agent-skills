# Worked example — a LinkedIn hero image

A fictional end-to-end run showing the three stages.

## The ask

> "I need a hero image for a LinkedIn post about our UK student-accommodation strategy. On-brand,
> 16:9, eye-catching but not cheesy."

## Stage 1 — Brainstorm (no API call, no egress)

Interviewed the user and agreed a brief:

- **Subject:** abstract architectural motif evoking modern student accommodation — no real building,
  no people.
- **Style:** clean, institutional, abstract-geometric with an architectural hint.
- **Composition:** focal motif left, generous negative space top-right for the headline.
- **Mood / palette:** navy blue + gold/cream accents, off-white ground.
- **Aspect:** 16:9. **Negatives:** no text, no watermark, no clutter.

Saved to `_workings/prompt-brief_pbsa-hero.md`. Confirmed with the user that we'll send this prompt
to fal.ai — **got the go-ahead.**

## Stage 2 — Prototype cheaply (FLUX schnell)

```bash
python scripts/falgen.py generate \
  --prompt "Abstract geometric architectural motif evoking modern student accommodation, deep navy and gold with soft cream accents on a clean off-white background, smooth gradients, modern elegant institutional aesthetic, generous negative space top-right, high detail, sharp focus — no text, no watermark, no clutter" \
  --aspect 16:9 --num 2 \
  --out-dir _workings --name image_pbsa-hero_v1
```

→ `_workings/image_pbsa-hero_v1_1.png`, `_workings/image_pbsa-hero_v1_2.png` (~$0.004 — two 0.59 MP images × $0.003/MP).

User liked v1_2's composition but wanted "warmer, less blue, a bit more depth." Targeted edit
with the cheap default editor (FLUX Kontext dev — holds the composition and dimensions, changes
only what was named):

```bash
python scripts/falgen.py edit \
  --prompt "make the palette warmer with golden amber tones, add subtle depth and shadow" \
  --image _workings/image_pbsa-hero_v1_2.png \
  --out-dir _workings --name image_pbsa-hero_v2
```

→ `_workings/image_pbsa-hero_v2.png` (a few tenths of a cent — Kontext dev is billed per
compute-second, so `falgen` flags it as time-billed rather than print a figure). User: **"That's the one."**

## Stage 3 — Produce the final (confirm the spend first)

Confirmed the production go-ahead. Re-rendered the approved concept faithfully at quality **and at
the final resolution (4K)** in one step — no separate upscale needed (16:9 4K is ample for the post):

```bash
python scripts/falgen.py edit \
  --prompt "same composition, refined to high fidelity, crisp clean edges, premium finish" \
  --image _workings/image_pbsa-hero_v2.png \
  --model fal-ai/nano-banana-pro/edit --aspect 16:9 \
  --arg resolution=4K \
  --out-dir . --name image_pbsa-hero_final
```

→ `image_pbsa-hero_final.png` at the work-folder root. The single **Nano Banana Pro edit (~$0.15)**
is essentially the whole cost of the run; everything before it was fractions of a cent.

## Run-log (appended)

| Stage | Model | Output | ~Cost |
|---|---|---|---|
| Prototype | `fal-ai/flux/schnell` | v1_1, v1_2 | ~$0.004 ($0.003/MP) |
| Edit | `fal-ai/flux-kontext/dev` | v2 | time-billed (~$0.00125/s) |
| Final (4K) | `fal-ai/nano-banana-pro/edit` | final | $0.15 (per image) |
| | | **Total** | **~$0.16** |

Handed to the user: *"`image_pbsa-hero_final.png` is ready — a draft asset for your review. It
hasn't been posted anywhere; place real headline text over the negative space in your post tool
when you're happy with it."*