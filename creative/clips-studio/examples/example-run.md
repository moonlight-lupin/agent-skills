# Worked example — animate a space, a building push-in, a product clip and text-to-video

A fictional, illustrative run (no real people/places). It shows all three modes plus the
image→video combo. The work folder holds a clean photo of an empty lounge (`lounge.jpg`) and a
building shot (`building.jpg`).

## Stage 1 — brainstorm (chat, no egress)

Agreed briefs (saved to `_workings/brief_demo.md`):

- **Lounge (`animate`):** the room is **empty**, so populate first, then animate. Motion: *"two
  people on the sofa mid-conversation, one gesturing; a third walks past in the background; soft
  afternoon daylight, gentle and natural."* 5s, 16:9, **no audio**.
- **Building (`camera`):** *"slow, gentle dolly push-in toward the entrance; smooth and steady."* 5s,
  no audio. Gentle by design (see `motion-honesty-guide.md`) — a push-in invents almost no geometry.

Confirmed the start images and that egress to fal.ai is OK for these (non-confidential marketing
imagery).

## Stage 2 — populate the empty lounge (in image-studio), then draft cheaply

**Populate** the empty room with people using `image-studio` (it edits the still; this skill does the
video):

```bash
# in image-studio (run from the clips-studio skill directory, or cd to image-studio first)
python ../image-studio/scripts/falgen.py edit \
  --prompt "Add two people sitting on the sofa mid-conversation and one walking past — natural, relaxed, believable. Keep the room, furniture, finishes and daylight exactly as they are." \
  --image _workings/lounge.jpg \
  --model fal-ai/nano-banana-pro/edit --arg resolution=2K \
  --out-dir _workings --name lounge_populated
```

Review `_workings/lounge_populated.png`. Then **draft the motion cheaply** here (Kling 2.5 Turbo Pro,
~$0.35 for 5s):

```bash
python scripts/falvid.py animate \
  --prompt "Two people on the sofa mid-conversation, one gesturing; a third walks past in the background; soft afternoon daylight, gentle natural motion." \
  --image _workings/lounge_populated.png \
  --duration 5 --aspect 16:9 \
  --out-dir _workings --name vid_lounge_draft \
  --run-log _workings/run-log_demo.md
```

Watch the draft for warping faces/hands and unnatural sliding. If the walking figure morphs, drop to
two people and re-draft — cheaper than fixing it on the quality model.

For the **building**, draft the camera move (Seedance default, ~$0.26). Check the source orientation
first and pass `--aspect` to match it:

```bash
python scripts/falvid.py camera --move push-in \
  --image _workings/building.jpg --duration 5 --aspect 16:9 \
  --out-dir _workings --name vid_building_draft
```

Check it doesn't invent a new entrance or windows. If it drifts, add `--static` or shorten the move.

## Stage 3 — produce the finals (confirm cost first)

Motion approved. Put the spend to the user: *"Lounge final as a 5s Veo 3.1 clip at 1080p, no audio,
~$1.00; building stays on Seedance, ~$0.26 — go ahead?"* On the go-ahead:

```bash
# Lounge — quality people motion on Veo 3.1
python scripts/falvid.py animate \
  --prompt "Two people on the sofa mid-conversation, one gesturing; a third walks past; soft afternoon daylight, gentle natural motion." \
  --image _workings/lounge_populated.png \
  --model fal-ai/veo3.1/image-to-video \
  --duration 5 --resolution 1080p --aspect 16:9 \
  --out-dir . --name vid_lounge_final \
  --run-log _workings/run-log_demo.md

# Building — keep Seedance, the camera default
python scripts/falvid.py camera --move push-in \
  --image _workings/building.jpg --duration 5 --resolution 720p --aspect 16:9 \
  --out-dir . --name vid_building_final \
  --run-log _workings/run-log_demo.md
```

Outputs: `./vid_lounge_final.mp4` and `./vid_building_final.mp4`. Then:

```bash
python scripts/falvid.py costs    # session breakdown — tell the user the total
```

Hand over the file paths and the estimated total, and remind the user: these are **illustrative
drafts** for review — not published material, and not a literal record of a real place. If publishing,
suggest an "illustrative" note in the post.

---

## Combo example — a vertical photo for a 16:9 hero (image-studio → video)

The user has a **portrait phone shot** of a building (`building_portrait.jpg`, ~3:4) but wants a
**16:9** clip for a website hero. The target frame is wider than the source — so run the **Stage-1
aspect & orientation check** first.

**1. Flag the mismatch and offer the honest routes.** *"Your photo is vertical but the hero is 16:9.
Best is a landscape photo — can you supply one? If we must use this vertical shot, I can (2) pillarbox
it (bars, nothing invented) or (3) generatively extend it to 16:9 — which invents the surroundings.
Which?"* (Force-cropping to 16:9 is **off the table** — it would slice the top and bottom off the
building.)

**2. User picks (3). Ground it before inventing.** *"To make the extension reflect the real street,
drop in any reference images — a street-view, the neighbouring buildings, a wider shot — so I extend
to what's actually there, not a guess."* Use those to steer the outpaint.

**3. Outpaint the still to 16:9** (cheap image step, in `image-studio`):

```bash
python ../image-studio/scripts/falgen.py edit \
  --prompt "Extend this photo sideways to fill a 16:9 frame. Keep the building EXACTLY as it is; continue the street, sky and the real neighbouring buildings (see references) naturally to left and right. Photorealistic, consistent dusk light." \
  --image _workings/building_portrait.jpg \
  --model fal-ai/nano-banana-pro/edit --aspect 16:9 --arg resolution=2K \
  --out-dir _workings --name building_16x9_extended
```

**4. CONFIRM the extended still with the user — before any video spend.** Show the extended PNG, take
corrections (*"there's a building on the left, not empty space — fill it in"*, *"trim the extra sky"*),
re-edit on the cheap image model until they approve. **Only then** animate — never animate an
unconfirmed invented frame.

**5. Animate the approved 16:9 frame** (pass `--aspect 16:9` so it isn't re-cropped):

```bash
python scripts/falvid.py camera --move push-in --aspect 16:9 \
  --prompt "Very gentle slow push-in; the building stays exactly as it is; subtle motion only in the sky." \
  --image _workings/building_16x9_extended.png --duration 5 \
  --out-dir . --name building_hero_final --run-log _workings/run-log_demo.md
```

All-in ~$0.41 (≈$0.15 extend + ≈$0.26 clip). Output is **illustrative** — the extended surroundings
are invented and now in motion, so it can never stand as a record of the real street; label it.

> **Aspect lesson:** the video models do **not** reliably inherit the source's framing — Seedance
> defaults to **16:9** and **centre-crops** a portrait/square still (you'll see only the middle band).
> Always pass `--aspect` to match the still: a 3:4 source → `--aspect 3:4`.

---

## Other quick examples (general subjects)

The studio isn't space-only — the same staging works for any clip.

**Product `animate`** — bring a product photo to life (draft cheap, then Veo 3.1 final):

```bash
python scripts/falvid.py animate \
  --prompt "The bottle slowly rotates on the plinth; soft studio light sweeps across the label; the background stays still. Keep the product exactly as it is — do not alter the label, shape or colour." \
  --image _workings/product.png --duration 5 --aspect 1:1 \
  --out-dir _workings --name product_draft
```

Keep object/hand interactions out (a hand reaching for the bottle will fumble — see the hands ceiling
in `motion-honesty-guide.md`). Never change the product's real label/shape/colour.

**Text-to-video `generate`** — an abstract brand-mood clip with **no source image** (cheap Wan draft
→ Veo 3.1 final):

```bash
python scripts/falvid.py generate \
  --prompt "Soft abstract flowing gradient in deep burgundy and warm neutrals, slow elegant motion, premium and calm; no text, no logos, no recognisable place or person." \
  --duration 5 --aspect 16:9 \
  --out-dir _workings --name brandmood_draft
```

`generate` invents the whole scene, so keep it **abstract/fictional** — never use it to depict a real
place, a real product or a real person (use `animate` on a real photo for those).
