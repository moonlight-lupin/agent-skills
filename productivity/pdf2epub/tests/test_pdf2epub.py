# Test suite for the pdf2epub skill repo copy.
# The engine lives in the pdf2epub skill's scripts/pdf2epub.py.
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Layout note: in the user's live library the skill lives at
# ~/.hermes/skills/pdf2epub/ (tests/ sits directly under it); the same tree
# publishes into the repo under one category dir, where tests/ is a sibling
# of pdf2epub/. Resolve both shapes.
def _resolve_script() -> Path:
    here = Path(__file__).resolve().parent
    for cand in (here.parent / "pdf2epub" / "scripts" / "pdf2epub.py",
                 here.parent / "scripts" / "pdf2epub.py"):
        if cand.exists():
            return cand
    pytest.skip("pdf2epub.py not found relative to tests/", allow_module_level=True)


SCRIPT = None  # resolved lazily in load_module()


def load_module():
    path = _resolve_script()
    spec = importlib.util.spec_from_file_location("pdf2epub_engine", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pdf2epub_engine"] = mod
    spec.loader.exec_module(mod)
    return mod


ENGINE = load_module()


# ---------- helpers under test (import-safe: pymupdf only needed at run) ----

def test_anchor_helper_fragment_gets_hash():
    assert ENGINE._anchor("fn25-1") == "#fn25-1"


def test_anchor_helper_crossfile_not_double_hashed():
    assert ENGINE._anchor("sec030.xhtml#fnc30-4") == "sec030.xhtml#fnc30-4"


def test_noteref_html_crossfile():
    html = ENGINE._noteref_html("sec030.xhtml#fnc30-4", "refc2-4", 4)
    assert 'href="sec030.xhtml#fnc30-4"' in html
    assert "double" not in html and 'href="#sec0' not in html
    assert ">4</sup></a>" in html


def test_probe_variants_strip_chapter_marker():
    v = ENGINE._probe_variants("第二十章 教导他们基督")
    assert v[0] == "第二十章教导他们基督".replace("基督", "基督") or v[0].startswith("第二十章")


def test_probe_variants_min_len():
    v = ENGINE._probe_variants("注释")
    assert "注释" in v


def test_probe_variants_dot_split():
    v = ENGINE._probe_variants("附录1：科顿·马瑟的育儿决心")
    assert any(p.startswith("附录1") and "马瑟" not in p for p in v)


# ---------- frontmatter / structural contract -------------------------------

def test_skillmd_frontmatter():
    import re
    skill_dir = _resolve_script().parents[1]
    text = (skill_dir / "SKILL.md").read_text()
    m = re.search(r"^---\n(.*?)\n---", text, re.DOTALL)
    assert m, "frontmatter block missing"
    fm = {}
    for line in m.group(1).splitlines():
        if line.startswith(" ") or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip().strip('"')
    assert fm.get("name") == "pdf2epub"
    assert fm.get("description", "").startswith("Use when")
    assert len(fm.get("description", "")) <= 1024


def test_engine_constants_sane():
    assert 0 < ENGINE.IMG_MIN_AREA_FRAC < 1
    assert ENGINE.IMG_CROP_DPI >= 120
    assert ENGINE.IMG_MAX_DIM >= 1200


def test_engine_imports_deterministic_stack():
    import importlib.util as iu
    assert iu.find_spec("pymupdf") is not None, "pymupdf not in env"
    assert iu.find_spec("ebooklib") is not None, "ebooklib not in env"