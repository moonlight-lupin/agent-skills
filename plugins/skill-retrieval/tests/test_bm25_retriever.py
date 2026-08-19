"""Tests for BM25 skill retriever — no real Hermes install required."""

from pathlib import Path

import pytest

import bm25_retriever as br


# ─── tokenize ────────────────────────────────────────────────────────────────

def test_tokenize_lowercases():
    assert br.tokenize("Hello WORLD") == ["hello", "world"]


def test_tokenize_removes_punctuation():
    assert br.tokenize("foo, bar! baz?") == ["foo", "bar", "baz"]


def test_tokenize_splits_whitespace():
    assert br.tokenize("  a   b\tc\n") == ["a", "b", "c"]


def test_tokenize_empty():
    assert br.tokenize("") == []
    assert br.tokenize("   ") == []


def test_tokenize_mixed():
    assert br.tokenize("Skill-Retrieval: BM25 (Okapi)") == [
        "skill", "retrieval", "bm25", "okapi"
    ]


# ─── _parse_skill_md ─────────────────────────────────────────────────────────

def test_parse_skill_md_basic(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: deep-research\n"
        'description: "Autonomous research loop"\n'
        "---\n"
        "\n# Body\n"
    )
    name, desc = br._parse_skill_md(skill_md)
    assert name == "deep-research"
    assert desc == "Autonomous research loop"


def test_parse_skill_md_multiline_description(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: skill-retrieval\n"
        "description: >-\n"
        "  BM25-based skill retrieval plugin.\n"
        "  Saves tokens per turn.\n"
        "author: MH\n"
        "---\n"
    )
    name, desc = br._parse_skill_md(skill_md)
    assert name == "skill-retrieval"
    assert "BM25-based skill retrieval plugin." in desc
    assert "Saves tokens per turn." in desc


def test_parse_skill_md_missing_fields(tmp_path):
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\nversion: 1.0\n---\n# No name\n")
    name, desc = br._parse_skill_md(skill_md)
    assert name == ""
    assert desc == ""


# ─── BM25Index ───────────────────────────────────────────────────────────────

@pytest.fixture
def small_index():
    ids = ["alpha", "beta", "gamma"]
    texts = [
        "image generation and photo editing with fal.ai",
        "deep research think search extract synthesize",
        "travel itinerary planning flights hotels calendar",
    ]
    index = br.BM25Index()
    index.build(ids, texts)
    return index


def test_bm25_build_and_retrieve(small_index):
    results = small_index.retrieve("image photo generation", top_k=3)
    assert results
    assert results[0][0] == "alpha"
    assert results[0][1] > 0


def test_bm25_scores_descending(small_index):
    results = small_index.retrieve("research search extract", top_k=3)
    assert results
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)


def test_bm25_respects_top_k(small_index):
    results = small_index.retrieve("planning travel research image", top_k=2)
    assert len(results) <= 2


def test_bm25_empty_corpus():
    index = br.BM25Index()
    index.build([], [])
    assert index.retrieve("anything") == []


def test_bm25_empty_query(small_index):
    assert small_index.retrieve("") == []
    assert small_index.retrieve("   !!!") == []


def test_bm25_no_matches(small_index):
    # Tokens absent from vocabulary → no hits
    assert small_index.retrieve("zzzzzyyyyxxxqqq") == []


def test_bm25_single_document():
    """Single-doc corpus: Lucene-clipped IDF is 0, so scores are all zero.

    Build must succeed; retrieve returns [] because idf.clip(min=0) zeros
    the only term's IDF when n_docs == df == 1.
    """
    index = br.BM25Index()
    index.build(["only"], ["unique widget factory"])
    assert index._built
    assert index.retrieve("widget", top_k=5) == []

    # Need n_docs >= 3 for a df=1 term to get positive Lucene IDF.
    index2 = br.BM25Index()
    index2.build(
        ["only", "other", "third"],
        [
            "unique widget factory",
            "unrelated travel planning",
            "calendar flights hotels",
        ],
    )
    results = index2.retrieve("widget", top_k=5)
    assert len(results) == 1
    assert results[0][0] == "only"
    assert results[0][1] > 0


def test_bm25_not_built_returns_empty():
    index = br.BM25Index()
    assert index.retrieve("query") == []


# ─── load_active_skills ──────────────────────────────────────────────────────

def _write_skill(root: Path, rel: str, name: str, description: str) -> Path:
    skill_dir = root / rel
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\nname: {name}\ndescription: \"{description}\"\n---\n\n# {name}\n"
    )
    return skill_md


def test_load_active_skills_standalone_and_plugin(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    config_path = tmp_path / "config.yaml"

    _write_skill(skills_root, "research/deep-research", "deep-research",
                 "Autonomous research engine")
    _write_skill(skills_root, "creative/image-studio", "image-studio",
                 "fal.ai image generation")

    plugin_skills = plugins_root / "chief-of-staff" / "skills"
    _write_skill(plugin_skills, "briefing", "daily-briefing",
                 "Morning briefing compilation")

    config_path.write_text("skills:\n  disabled: []\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    skills = br.load_active_skills()
    ids = {s["skill_id"] for s in skills}
    assert "research/deep-research" in ids
    assert "creative/image-studio" in ids
    assert "chief-of-staff:briefing" in ids

    by_id = {s["skill_id"]: s for s in skills}
    assert by_id["research/deep-research"]["name"] == "deep-research"
    assert "Autonomous research" in by_id["research/deep-research"]["description"]
    assert by_id["chief-of-staff:briefing"]["leaf_name"] == "briefing"


def test_load_active_skills_respects_disabled(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    config_path = tmp_path / "config.yaml"

    _write_skill(skills_root, "a/keep-me", "keep-me", "Should load")
    _write_skill(skills_root, "a/drop-me", "drop-me", "Should skip")
    plugins_root.mkdir()
    config_path.write_text("skills:\n  disabled:\n    - drop-me\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    skills = br.load_active_skills()
    ids = {s["skill_id"] for s in skills}
    assert "a/keep-me" in ids
    assert "a/drop-me" not in ids


def test_load_active_skills_skips_archive_dirs(tmp_path, monkeypatch):
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    config_path = tmp_path / "config.yaml"

    _write_skill(skills_root, "live/ok", "ok", "Live skill")
    _write_skill(skills_root, ".archive/old", "old", "Archived")
    plugins_root.mkdir()
    config_path.write_text("skills:\n  disabled: []\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    skills = br.load_active_skills()
    ids = {s["skill_id"] for s in skills}
    assert "live/ok" in ids
    assert not any(".archive" in i for i in ids)


def test_load_active_skills_empty_roots(tmp_path, monkeypatch):
    monkeypatch.setattr(br, "SKILLS_ROOT", tmp_path / "missing-skills")
    monkeypatch.setattr(br, "PLUGINS_ROOT", tmp_path / "missing-plugins")
    monkeypatch.setattr(br, "CONFIG_PATH", tmp_path / "missing-config.yaml")
    assert br.load_active_skills() == []


def test_load_active_skills_empty_yaml_config(tmp_path, monkeypatch):
    """Empty or null YAML must not crash on `.get()`."""
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    config_path = tmp_path / "config.yaml"
    _write_skill(skills_root, "a/ok", "ok", "Still loads")
    plugins_root.mkdir()
    config_path.write_text("")  # yaml.safe_load → None

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    skills = br.load_active_skills()
    assert {s["skill_id"] for s in skills} == {"a/ok"}


# ─── plugin TOP_K parsing ────────────────────────────────────────────────────

def test_parse_top_k_defaults_and_rejects_invalid():
    import importlib
    import sys
    from pathlib import Path

    plugin_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(plugin_dir))
    # Import the package __init__ as a module under a unique name so we can
    # call the helper without requiring a Hermes runtime.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "skill_retrieval_plugin", plugin_dir / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod._parse_top_k(None) == 6
    assert mod._parse_top_k("") == 6
    assert mod._parse_top_k("8") == 8
    assert mod._parse_top_k("nope") == 6
    assert mod._parse_top_k("0") == 6
    assert mod._parse_top_k("-3") == 6
