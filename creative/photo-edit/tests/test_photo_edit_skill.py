"""Offline tests for the photo-edit skill (stdlib + pytest + numpy/Pillow; no network)."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import photo_core as C  # noqa: E402
import photo_analyze as A  # noqa: E402
import photo_frames as Fr  # noqa: E402


def scene(path, w=1200, h=800):
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h // 2):
        c = int(120 + 100 * y / (h // 2))
        d.line([(0, y), (w, y)], fill=(c - 40, c - 10, c + 30))  # blue sky
    d.rectangle([0, h // 2, w, h], fill=(90, 110, 70))
    for i, x in enumerate(range(120, w - 150, 120)):
        d.rectangle([x, 240 + (i % 3) * 30, x + 70, h // 2 + 80], fill=(150, 150, 150) if i % 2 else (200, 200, 200))
    for i, v in enumerate([40, 90, 128, 170, 215, 245]):
        d.rectangle([80 + i * 64, 600, 136 + i * 64, 680], fill=(v, v, v))
    d.ellipse([700, 560, 860, 720], fill=(210, 60, 40))  # a clear subject
    a = np.asarray(im, np.float32) / 255
    a = a + np.random.default_rng(1).normal(0, 0.01, a.shape).astype(np.float32)
    Image.fromarray(C.to_uint8(a)).save(path, quality=95)
    return np.clip(a, 0, 1)


def run(*args):
    out = subprocess.run([sys.executable, str(SCRIPTS / "photo_edit.py"), *map(str, args)],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.fixture()
def ref(tmp_path):
    p = tmp_path / "ref.jpg"
    return p, scene(p)


@pytest.mark.parametrize("deg", [-3.0, 1.5, 4.0])
def test_tilt_estimate_is_exact_correction(ref, deg):
    _, a = ref
    rot = C.rotate_float(a, deg)
    h, w = rot.shape[:2]
    rot = rot[h // 6:-h // 6, w // 6:-w // 6]
    est, conf = A.estimate_tilt(C.luma(rot) * 255)
    assert abs(est - (-deg)) <= 0.15 and conf > 0.5


def test_auto_wb_ignores_blue_sky_and_reduces_cast(ref, tmp_path):
    _, a = ref
    lin = C.srgb_to_linear(a) * np.array([1.18, 1.0, 0.80], np.float32)
    bad = tmp_path / "warm.jpg"
    Image.fromarray(C.to_uint8(C.linear_to_srgb(lin))).save(bad, quality=95)
    cast = A.measure(C.load(bad)[0])["cast"]
    assert cast["b"] > 4  # detects the warm cast on the greys, not the sky
    res = run(bad, "-o", tmp_path / "fixed.jpg", "--recipe", '{"white_balance":{"mode":"auto","strength":1.0}}')
    assert abs(res["after"]["cast_ab"][1]) < abs(res["before"]["cast_ab"][1]) / 2


def test_refuses_to_overwrite_original(ref):
    p, _ = ref
    out = subprocess.run([sys.executable, str(SCRIPTS / "photo_edit.py"), str(p), "-o", str(p), "--recipe", "{}"],
                         capture_output=True, text=True)
    assert out.returncode != 0 and "Refusing" in (out.stderr + out.stdout)


def test_taste_limits_clamp(ref, tmp_path):
    p, _ = ref
    out = subprocess.run([sys.executable, str(SCRIPTS / "photo_edit.py"), str(p), "-o", str(tmp_path / "x.jpg"),
                          "--recipe", '{"saturation": 80}', "--dry-run"], capture_output=True, text=True)
    d = json.loads(out.stdout)
    assert d["recipe"]["saturation"] == 25 and d["warnings"]


def test_exact_resize_and_reframe(ref, tmp_path):
    p, _ = ref
    res = run(p, "-o", tmp_path / "ig.jpg", "--recipe",
              '{"reframe":{"aspect":"4:5","subject":[0.58,0.7,0.72,0.9]},"resize":{"exact":[400,500]}}')
    assert res["size"] == [400, 500]
    assert not res["applied"]["reframe"]["subject_clipped"]


@pytest.mark.parametrize("shape", ["heart", "circle", "star"])
def test_shape_frame_keeps_subject_visible(ref, tmp_path, shape):
    p, _ = ref
    out = tmp_path / f"{shape}.png"
    res = run(p, "-o", out, "--recipe",
              json.dumps({"reframe": {"subject": [0.58, 0.7, 0.72, 0.9]}, "frame": {"shape": shape}}))
    vis = res["applied"]["reframe"]["visibility"]
    assert res["applied"]["reframe"]["visibility_ok"] and vis["subject_visible_pct"] >= 97
    im = Image.open(out)
    assert im.mode == "RGBA" and im.getchannel("A").getextrema()[0] == 0  # transparent corners


def test_sweet_spot_inside_heart():
    (sx, sy), safe, aspect = Fr.sweet_and_safe({"shape": "heart"}, 1.0)
    m = Fr.shape_mask({"shape": "heart"}, 220, round(220 / aspect))
    assert m[int(sy * m.shape[0]), int(sx * m.shape[1])] > 0.99
    assert safe[0] < sx < safe[2] and safe[1] < sy < safe[3]


# ---------------------------------------------------------------- docs <-> code parity

SKILL = SCRIPTS.parent


def _recipe_md():
    return (SKILL / "references" / "recipe.md").read_text(encoding="utf-8")


def test_scene_table_matches_code():
    import re
    rows = re.findall(r"^\| ([a-z-]+) \| (\d+|none) \| ([\d.]+) \| (\d+) \| (yes|no) \| (yes|no) \|$",
                      _recipe_md(), re.M)
    doc = {r[0]: r[1:] for r in rows}
    assert set(doc) == set(A.SCENES)
    for name, sc in A.SCENES.items():
        t, wb, vib, lift, wh = doc[name]
        assert (None if t == "none" else int(t)) == sc["target"], name
        assert float(wb) == sc["wb"] and int(vib) == sc["vib"], name
        assert (lift == "yes") == sc["lift"] and (wh == "yes") == sc["whites"], name


def test_taste_limits_documented():
    import re
    import photo_edit as E
    md = _recipe_md()
    for key, (_, (lo, hi)) in E.LIMITS.items():
        if key in ("temp", "tint"):
            continue
        row = re.search(rf"^\| `{key}` \|([^|]*)\|", md, re.M)
        assert row, f"{key} missing from recipe.md"
        assert f"{lo:g}" in row.group(1) or f"{hi:g}" in row.group(1), (key, row.group(1))


def test_skill_md_scenes_and_looks_match_code():
    import re
    md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    scenes = {s.strip() for s in re.search(r"Scenes: (.*?)\.", md, re.S).group(1).replace("\n", " ").split(",")}
    assert scenes == set(A.SCENES)
    looks = {p.stem for p in (SKILL / "templates" / "looks").glob("*.json")}
    cited = set(re.findall(r"`([a-z]+(?:-[a-z]+)*)`", re.search(r"\| Look preset \|(.*)\|", md).group(1)))
    assert looks <= cited | {"natural"}


def test_blind_compare_hides_labels(ref, tmp_path):
    p, _ = ref
    out = subprocess.run([sys.executable, str(SCRIPTS / "photo_compare.py"), str(p), str(p), "-o",
                          str(tmp_path / "b.png"), "--blind"], capture_output=True, text=True)
    d = json.loads(out.stdout)
    assert d["panels"] == ["A", "B"] and "metrics" not in d
    key = json.loads(Path(d["key_file"]).read_text(encoding="utf-8"))
    assert set(key["key"]) == {"A", "B"}
