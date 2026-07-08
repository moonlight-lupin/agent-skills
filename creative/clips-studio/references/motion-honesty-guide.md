# Motion honesty guide — animating real subjects without misrepresenting them

A moving clip is more persuasive — and therefore more capable of misleading — than a still. This
guide is the discipline that keeps an AI clip honest. Read it before Stage 1; it's the video
counterpart to `image-studio`'s faithful-edit discipline. The discipline **scales with how real the
subject is** — a real place, a real product, real people. **Property / real estate is a common worked
example below**, but the same rules apply to any real subject.

**Text-to-video invents the entire scene**, so never use `generate` to depict a real, identifiable
place, product or person — `animate` a real photo instead. The rules below assume a real subject; for
a purely fictional/abstract brand-mood clip the honesty bar is lower, but never imply it shows
something real.

## The one rule

> **Show motion and atmosphere; never invent space, features, or facts about the subject.**

An AI video model *hallucinates* everything it can't see in the start frame. That is fine for
**how light moves** or **how a space feels** — and dangerous when it starts inventing **what the
place is**: rooms that don't exist, a view that isn't there, a finish the subject doesn't have, a
crowd that implies an occupancy it doesn't have.

## Animating people (`animate`)

People bring a space to life, but they also imply things. Keep it **illustrative lifestyle**, not a
documentary claim:

- **Do** — natural, relaxed activity at believable density: a couple of people chatting, someone
  reading, a person walking through. Genuine interaction reads better than posed smiling.
- **Don't** — imply a specific **demographic, occupancy level or activity** the subject doesn't
  actually have (a packed, buzzing room for a half-occupied space; a particular clientele).
- **Don't** — animate **identifiable real people** (likeness + egress). Generated, non-identifiable
  figures only; never upload a private person's photo.
- **Faces & hands deform in motion** — prefer fewer, larger, mid-distance figures; if a face warps,
  reduce the crowd and re-draft rather than chasing it.

## Hands & fine object interaction — the believability ceiling

The single hardest motion for **every** current image-to-video model (Kling, Veo, Seedance alike) is
**hands articulating around small objects** — pouring or holding a kettle, gripping a cup, typing,
handling a phone, working a door handle. Models tend to **exaggerate the gesture** and **morph the
hand or the object** mid-action. A better / production model *reduces* this but does **not** eliminate
it — so **don't pay for the quality render to fix hands; fix the brief on the cheap model first.**
(Observed repeatedly in testing: a sofa pair told to "chat" came out with unnatural, over-large
gestures; restraining them to small micro-motion fixed it, while a background figure asked to use a
kitchenette kept "pouring" something unconvincingly. On a busier frame the ceiling was harder still: a
*focal* seated person with a snack bowl kept raising a hand toward their face across **three**
re-drafts — even with the bowl parked aside, hands placed in the lap, and explicit negatives. Text has
a hard limit against a determined hand-to-face prior on a focal figure.)

**The rule: design the hard motion *out* — don't rely on the model to nail it.**

- **Park object-handling figures as static**, explicitly: *"stands facing the counter, hands at their
  sides, glancing down; does not touch, lift, hold or pour anything — no cup, no kettle."* Naming the
  non-action works better than hoping the model skips it.
- **Keep foreground people small and restrained** — a slight nod, a small smile, a gentle shift of
  weight; **hands resting, no large gestures.** Name the action *small*. Restrained motion also reads
  more premium, and is the more honest frame.
- **Negatives are a soft steer, not a guarantee** — include
  `exaggerated gestures, morphing or distorted hands and fingers, warping objects, fast jerky motion`,
  but it's the prompt *parking the action* that does the real work, not the negative.
- **Distance forgives.** A far/background figure's imperfection is far less obvious than a focal one —
  so put any unavoidable fiddly motion in the background and keep the **focal** subject's hands
  simple (resting, still, no object).

This is the practical face of the skill's "**a better prompt before a pricier model**" rule (SKILL.md,
Stage 2): re-draft cheaply with the motion designed down, *then* spend on the final.

### The fallback — when people won't behave, move the camera instead

If a **focal** figure's hand/object motion still won't behave after a cheap re-draft or two, **stop
animating the people and move the camera instead.** A **camera move** (people held, only the camera
drifts) sidesteps the hand-to-face and object problems entirely, and its motion *masks* residual
jitter in tricky elements (a fidgety on-screen TV, a far figure). Observed: a slow camera push-in held
a struggling figure — and everyone — still where three `animate` re-drafts couldn't.

**This is a fallback, not a default.** The default for a "bring it to life with people" brief stays
`animate`; reach for the camera move only when people-animation hits this ceiling. (The `camera` mode
remains a *first-class* mode in its own right for camera/3D briefs you actually want — it's just not
the first answer to a struggling people-clip.) And if a clip genuinely *needs* believable object
handling, it's the wrong tool altogether — use a real shoot.

## Screens, TVs & projected content

A screen in frame (a TV, a cinema/projector screen, a monitor) is its own trap: **any "alive" cue
makes the model fabricate motion on the screen** — it will cut to a different scene, then zoom, rather
than hold the image. That's both unnatural (it reads as a glitch) and a mild fabrication (invented
on-screen content).

- **Keep screen motion out of the brief.** Don't ask the screen to "play"; if anything, say *"the
  image on the screen stays the same, a faint steady glow; it does not change scene, cut or play new
  footage."*
- **Even "stays the same" is not a hard lock** — the model may still drift or zoom the screen
  (observed: cut scenes on one draft, zoomed on the next, despite the instruction). Don't keep
  fighting it with more prompt.
- **A camera move masks it.** Under a slow camera push-in the screen moves *with* the frame, so
  residual screen drift is far less obvious than when the camera is locked — another reason the camera
  fallback suits screen-heavy rooms.

## Camera moves invent geometry (`camera`) — the big one

A camera move asks the model to render **what the camera would see as it moves** — i.e. parts of the
scene that **were never in the photo**. The more the camera travels, the more the model invents.
Ranked from safest to riskiest:

| Move | What it invents | Verdict |
|---|---|---|
| **`--static`** (locked camera, subject moves) | almost nothing — only the moving subject | **Safest.** Prefer it when you just need life/motion. |
| **Slow push-in / pull-out** (small dolly) | a little edge detail; mild parallax | **Good.** Gentle and largely faithful. |
| **Slow pan / tilt** (small angle) | whatever rotates into frame at the edges | **OK if small.** Keep the angle modest. |
| **Shallow orbit** (a few degrees) | the near side of objects as they turn | **Caution.** Stay shallow; a wide orbit fabricates whole new faces of the space. |
| **Deep fly-through / big orbit / "walk the room"** | entire walls, rooms, the far side of a façade | **Avoid.** This is no longer the real place — it's an invented one. |

Practical rules:

- **Prefer gentle, slow, short.** A 5s slow push-in sells "premium and calm" and invents almost
  nothing. A sweeping orbit invents a building.
- **Speed and travel are prompt-driven** — there's no numeric speed control on these models, so you
  have to *spell out* the pace (a bare `--move push-in` tends to come out faster/larger than
  expected). **Match the pace to the scene** — a calm interior usually wants a slow, subtle drift; a
  façade or hero reveal can carry a more deliberate move. The only fixed point is the honesty
  trade-off: the faster and farther the camera travels, the more edge geometry it invents — so pick
  the *slowest move that still does the job*, not a one-size pace.
- **Use `--static` whenever it does the job** — it's the most honest motion there is.
- **Watch the draft for hallucination**: doorways that lead nowhere real, a window gaining a view,
  furniture multiplying, a corridor inventing an end. If the move reveals space the photo never
  showed, pull the move back.
- **Façades / exteriors**: a slow push-in or a small lateral drift is fine; orbiting a building
  invents elevations you don't have photos of.

## Extending a frame (outpaint to change aspect)

To fit a different aspect — a vertical photo into a 16:9 hero, say — the cheapest route is to
**outpaint** the still wider in `image-studio`, then animate. But outpainting **invents the
surroundings that weren't photographed** (the buildings next door, more street and sky). For a real
subject that's a misrepresentation risk, so:

- **Ground it in reality.** Ask the user for **reference images of the actual surroundings** —
  street-view, the neighbouring buildings, a wider shot — and use them so the extension *reconstructs*
  the real context instead of inventing it. Grounded beats invented, every time.
- **Confirm the extended still before animating.** It's a cheap image step before the video spend —
  show it, take corrections (*"that's a building, not empty space"*, *"trim the sky"*), re-edit, get
  approval, **then** animate. Don't animate an unconfirmed invented frame, and remember the invented
  context is then *in motion* — doubly illustrative.
- **Keep it illustrative.** Never present an outpainted clip as the real street or setting; label it.
- **Prefer a properly-oriented source photo** over outpainting at all (see SKILL.md, Stage 1).

## Never

- Never **add or improve** a feature, finish, fixture, view or amenity the subject doesn't have.
- Never **remove** a real, permanent feature to flatter the space.
- Never present the clip as a **measured tour, a real walkthrough, a floor-plan-accurate
  representation, or a record of the actual layout**. It is an **illustrative clip**.
- Never animate **confidential or sensitive content**, or an **identifiable real person** without
  consent.

## When this skill is the wrong tool

For anything where **literal accuracy matters** — a property listing, an offer document, a spec claim,
a measured tour — an **AI extrapolation is not appropriate**. Use:

- a **real video shoot** of the actual subject, or
- a **proper 3D tour / Matterport-style capture** built from real measurements.

This skill is a fast first-pass **marketing** draft for screens, posts and reels — clearly an
illustration, reviewed by a person, never a document of record.

## Label & review

- Treat every output as a **draft for review** by a person before any use.
- Where the clip will be published, recommend a visible **"illustrative" / "for marketing purposes"**
  note in the post or the asset itself (the skill produces the clip; the human decides distribution).
