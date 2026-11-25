# Worked example: a tilted, warm, dark snapshot → Instagram post in a heart

A fictional run. The numbers are representative of what the scripts print on such a photo.

## The ask

> "Can you fix this photo and put it in a heart for my sister's birthday post?"

Destination: Instagram feed. A transparent heart needs PNG.

## 1. Measure

```
python3 scripts/photo_analyze.py party.jpg --scene portrait --brief --overlay work/overlay.png
```

```
Exposure: median L*=39.4 p1=0.0 p99=67.5 | clipped hi 0.0% lo 2.07% | normal
Cast (neutrals): a*=1.7 b*=8.4 reliable=True
Tilt: -2.5 deg (confidence 0.82)
Subject (faces, confidence 0.9): box [0.41, 0.22, 0.63, 0.71], faces 1
Suggested recipe: {"straighten": -2.5, "white_balance": {"mode": "auto", "strength": 0.6},
                   "exposure": 0.53, "contrast": 15}
```

Vision on the overlay: "The red box contains the woman holding the cake: yes. The door frame on the
left is visibly tilted." Subject and tilt confirmed.

## 2. Recipe (`work/recipe_v1.json`)

```json
{
  "straighten": -2.5,
  "white_balance": {"mode": "auto", "strength": 0.6},
  "exposure": 0.45,
  "contrast": 10,
  "shadows": 15,
  "vibrance": 8,
  "frame": {"shape": "heart", "stroke": 0.01, "stroke_color": "#ffffff", "padding": 0.05},
  "resize": {"long_edge": 1350},
  "metadata": "no-gps"
}
```

Reasons: lines agree on a -2.5° tilt; neutrals carry b*=+8.4 (tungsten), corrected at 0.6 to keep
party warmth; median L* 39 vs the 54 portrait target, with 1.3 EV of highlight headroom → +0.45 EV;
2% crushed shadows → shadows +15; portrait vibrance cap is 8.

## 3. Render

```
python3 scripts/photo_edit.py party.jpg -o work/party_v1.png --recipe work/recipe_v1.json --check work/check_v1.png
```

Key output: `after.cast_ab [0.5, 2.9]`, `after.clip_hi_pct 0.0`,
`reframe.visibility {subject_visible_pct: 99.4, faces_visible_pct: [100.0]}`, `visibility_ok: true`,
no warnings.

## 4. Blind check

```
python3 scripts/photo_compare.py party.jpg work/party_v1.png -o work/blind_v1.png --blind --detail 0.52,0.4
```

Vision, before the key was opened: "B is more natural: correct skin, no orange cast; A is dark and
yellow." Key: B = `party_v1.png`. On the check image: "The face is entirely inside the heart, clear of the
cleft and the white outline: yes."

## 5. Deliver

> Straightened 2.5°, brightened +0.45 EV, cut the tungsten cast from b*=+8 to +3 (kept a little warmth),
> opened shadows slightly, and cut it into a heart with a thin white outline. 1350 px PNG with a
> transparent background; location data removed.
