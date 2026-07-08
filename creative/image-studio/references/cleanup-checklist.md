# Photo clean-up checklist — amateur / phone shot → professional

For **Path C (clean up / enhance)**: turning a mobile/phone/messaging-app photo into a clean,
professional-looking shot. Don't iterate blindly — **scan this list, pick every issue the photo
actually has, drop every issue it does not, and put the rest into ONE correction instruction** so a
single quality edit (`nano-banana-pro/edit`) fixes them together. Iterate only if a specific issue
remains.

## Subject types — what "faithful" means for each

The discipline below is universal, but the features you must keep and the issues you typically fix
depend on what the photo is of. Pick the row that matches the photo:

| Subject | Keep exactly | Common issues (by row #) |
|---|---|---|
| Interiors / real estate | Walls, fittings, fixtures, furniture, layout, view out windows | 1–6, 9, 10, 12 |
| Portrait / people | Face, identity, clothing, pose, natural background | 1, 2, 3, 6, 7, 9 |
| Product / object | The object itself, label/text, original background | 1, 2, 3, 7, 9 |
| Food | The dish, garnish, plate, table setting | 1, 2, 6, 7 |
| Landscape / outdoor | Landforms, sky, buildings, vegetation | 1, 2, 3, 4, 7 |

(The row shows which issues are common for that subject — still apply only the ones the photo
*actually* has.)

## The discipline (read first)

- **Faithful correction, not a redesign.** Fix how the photo was *captured* — light, colour,
  geometry, noise — never what the subject *is*. Keep every real feature and the layout exactly:
  the things that define what the photo is of (see the subject table above for what to protect).
- **Declutter only genuinely temporary items** — a stray remote, cables, bins, cleaning kit,
  personal effects, retail/price tags, the photographer's reflection. **Never** remove or alter a
  real feature to flatter the subject, and **never invent** a nicer view, finish or fixture — that
  misrepresents the subject. For property/real-estate or product shots especially, accuracy is
  non-negotiable.
- **It's a generative re-render**, so it can subtly drift (smoothed textures, simplified detail).
  Review against the original before use. **For a listing or anywhere literal accuracy matters, a
  non-generative edit (Lightroom/Photoshop) is the faithful gold standard** — treat this as a fast
  first pass / draft, not a document of record.
- **One comprehensive pass.** Build the instruction from the items below; don't re-roll repeatedly.

## Common issues to check (and the fix phrasing)

| # | Issue | Tell-tale signs | Fix to ask for |
|---|---|---|---|
| 1 | **White balance / colour cast** | Orange (tungsten) or blue cast; muddy walls; mixed lighting | "Neutralise to accurate white balance; true neutral greys/whites" |
| 2 | **Exposure & dynamic range** | Too dark/bright; blown windows, lights or screens; crushed shadows | "Balance exposure, recover blown highlights, gently lift shadows, even the lighting" |
| 3 | **Flare / reflections / glare** | Bright reflections on TVs, screens, glass, mirrors, glossy surfaces; sun flare | "Remove flare and reflections; clean dark screens; tame window glare" |
| 4 | **Perspective / geometry** | Converging (leaning) verticals, tilted horizon, keystoning | "Straighten the verticals, level the horizon, correct the keystone/perspective" |
| 5 | **Lens distortion / warp** | Bowed straight lines, wide-angle stretch at edges | "Correct lens distortion; straighten bowed lines" |
| 6 | **Noise / grain** | Speckle in shadows, low-light mush | "Reduce noise and grain while keeping real detail" |
| 7 | **Softness / sharpness** | Soft focus, slight motion blur, messaging-app softness | "Increase clarity and sharpness for a crisp professional look (don't over-sharpen)" |
| 8 | **Chromatic aberration** | Purple/green fringes on high-contrast edges | "Remove colour fringing / chromatic aberration" |
| 9 | **Compression artefacts** | JPEG blockiness (common from messaging apps) | "Clean up compression artefacts and banding" |
| 10 | **Clutter / distractions** | Stray remotes, cables, bins, tags, personal items, photographer's reflection | "Remove only small stray clutter: [list them]. Keep all real features and contents" |
| 11 | **Crop / level / composition** | Wonky framing, dutch tilt, too much floor/ceiling | "Level and lightly straighten the crop" (optional — confirm before cropping out content) |
| 12 | **Dust / sensor spots / smudges** | Soft dark blobs, lens smudge haze | "Spot-clean dust marks and lens smudges" |

## Prompt skeleton

> "Professionally correct this amateur phone photo of [subject] — a FAITHFUL photographic
> correction, NOT a redesign. [Pick the relevant fixes from the table, e.g. neutralise the warm
> colour cast …; recover the blown highlights and lift shadows …; remove the glare …; straighten
> the verticals …; reduce noise and add clarity …]. KEEP [subject-appropriate fixed features — see
> the subject table] exactly as they are and in their positions. Do not add, move, remove or
> restyle [subject elements] or change the layout. Remove only small stray clutter: [list].
> Professional photography, natural even lighting, true-to-life colours. No text, no logos, no
> watermarks."

## What NOT to do — over-application is an honesty violation

Including a fix for a problem the photo doesn't have is **not** harmless — it is an active
transformation that changes a correct image. Rows 4, 5, 8, 11 and 12 are the most dangerous to
over-apply: straightening verticals that are already level, correcting lens distortion on a
rectilinear lens, removing chromatic aberration with no fringing, recropping a photo the user
wanted as-is, or spot-cleaning a clean sensor — each *changes* the image on an axis the original
got right.

❌ "Neutralise the colour cast; recover blown highlights; remove flare; straighten the verticals;
   correct lens distortion; reduce noise; remove chromatic aberration; clean compression
   artefacts; remove clutter." — applied to a well-lit, level, clean photo, this *changes* a
   correct image on 6 of 9 axes. It violates the "faithful correction" discipline.

✅ "Neutralise the slight warm colour cast; recover the blown window highlights; reduce the shadow
   noise on the left wall — issues 1, 2, 6 only." — three fixes the photo needs, nothing it doesn't.

**Rule:** if you cannot see the tell-tale sign for a row, do not include that fix.

## Run it (one pass, Path C)

```bash
python scripts/falgen.py edit \
  --prompt "[the assembled correction prompt]" \
  --image "_workings/[the-phone-photo].jpg" \
  --model fal-ai/nano-banana-pro/edit --arg resolution=2K \
  --out-dir . --name [slug]_cleaned \
  --run-log _workings/run-log_[slug].md
```

(2K is ample for screen/web/most print; see SKILL.md for 2K-vs-4K. Keep the source aspect — don't
pass `--aspect` unless you intend to recrop.)
