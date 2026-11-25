# Vision checks (`vision_analyze`)

Numbers catch clipping and casts; only eyes catch "wrong subject", "weird skin" or "looks fake". Ask
specific, closed questions. "Does it look good?" gets flattery. Always name what you expect and ask for
coordinates or yes/no with a reason.

Use `region: [x1, y1, x2, y2]` (original-pixel coordinates) to inspect detail at full resolution: faces,
edges after sharpening, skies for banding, the shape edge on frames.

## §1 Before editing: understand the photo (`photo_analyze.py --overlay` image)

1. "Describe this photo in one sentence: subject, setting, light source and time of day. Is anything
   deliberately dark, bright or coloured (silhouette, golden hour, neon, candlelight)?"
2. "The red rectangle marks the detected main subject. Does it contain the main subject a viewer would
   care about (name it)? If not, give its bounding box as fractions of width and height: x0,y0,x1,y1."
3. "Blue rectangles are alternative candidates. Which, if any, is part of the subject?"
4. If notes report competing neutrals: "Is the area around (x, y) truly white or grey in real life (wall,
   paper, road, cloud), or is it coloured?"
5. If tilt is low confidence: "Is there a horizon or architectural vertical that is visibly tilted?"

## §2 After rendering (`photo_compare.py --blind` sheet)

Never tell the vision model which panel is the original or the edit. Ask, then open the key file.

1. "These panels show the same photo processed differently. Rank them from most to least natural and
   pleasing. For each, name its single biggest flaw, if any."
2. "In which panel, if any, do skin tones look unnatural (orange, red, grey, green, magenta)?" (people only)
3. "In which panels are bright areas (sky, windows, white clothes) blown to flat white, or dark areas
   crushed to flat black?"
4. "Which panels show a colour cast? Describe it (warm, cool, green, magenta)."
5. For looks: "Which panel reads as <look name> without looking like a filter?"

Then read `<sheet>.key.json`. Accept the edit only if it ranks first, or ties with the original on
naturalness while fixing the measured problem.

Detail pass (use `photo_compare.py --detail x,y` or `region`):
- "At 100% zoom, are there bright or dark halos along edges, or blotchy noise in flat areas?"
- "Any visible banding (stepped bands) in the sky gradient?"

## §3 After framing/reframing (`photo_edit.py --check` image)

1. "The red box marks <subject>. Is <subject> entirely visible inside the frame/shape: not cut by its edge,
   the outline stroke or the canvas border? Answer yes/no, then name any part that is cut."
2. If faces: "Are all faces (yellow boxes) completely visible with some space around them, with no face
   touching the shape edge?"
3. "Is the subject placed pleasingly (on a third or at the visual centre of the shape), or does it feel
   cramped or adrift?"
4. For padded results: "Does the blurred extension at the edges look like a natural continuation, or is
   there a visible seam or a ghosted duplicate?"
5. "Does the frame colour complement the photo, or compete with it?"

Act on the answers: wrong subject → pass `reframe.subject`; cut → lower `tightness`, enlarge `padding`,
use a roomier shape (circle/ellipse instead of star), or `fit: "blur"`; cramped → raise `margin`.
