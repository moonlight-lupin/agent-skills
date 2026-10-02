"""Regression tests for the four pre-release bugs (A1-A4) + coverage gaps (B).

These tests were written BEFORE the fixes. Each test encodes the correct
behaviour described in the fix brief. They fail against the buggy code and
pass after the fixes land.
"""

import importlib
import sys
import types
from pathlib import Path

import pytest

import bm25_retriever as br

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
PLUGIN_DIR = Path(__file__).resolve().parent.parent


# ═══════════════════════════════════════════════════════════════════════════════
# A1 — frontmatter parser bleeds later YAML keys into the description
# ═══════════════════════════════════════════════════════════════════════════════

def test_parse_skill_md_does_not_bleed_later_keys(tmp_path):
    """Nested YAML keys after ``description:`` must NOT enter the description."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: demo\n"
        "description: Convert CSV files to JSON.\n"
        "allowed-tools:\n"
        "  - Bash\n"
        "  - Read\n"
        "metadata:\n"
        "  category: sausage-manufacturing\n"
        "  owner: bob\n"
        "---\n"
    )
    name, desc = br._parse_skill_md(skill_md)
    assert name == "demo"
    assert desc == "Convert CSV files to JSON."
    assert "sausage" not in desc.lower()
    assert "Bash" not in desc
    assert "category" not in desc
    assert "owner" not in desc


def test_parse_skill_md_own_plugin_skilmd_no_bleed():
    """The plugin's own SKILL.md must not bleed ``plugin_type`` / ``hooks``."""
    skill_md = PLUGIN_DIR / "SKILL.md"
    name, desc = br._parse_skill_md(skill_md)
    assert name == "skill-retrieval"
    assert "plugin_type" not in desc
    assert "hooks" not in desc
    assert "[pre_llm_call]" not in desc


# ═══════════════════════════════════════════════════════════════════════════════
# A2 — YAML block-scalar indicators land in the corpus
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("indicator", [">-", ">", "|-", "|"])
def test_parse_skill_md_block_scalar_indicator_stripped(tmp_path, indicator):
    """Block-scalar indicators (``>-``, ``>``, ``|-``, ``|``) must not appear."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: demo\n"
        f"description: {indicator}\n"
        "  A multi-line description.\n"
        "  Second line.\n"
        "---\n"
    )
    _, desc = br._parse_skill_md(skill_md)
    assert not desc.startswith((">", "|"))
    assert "multi-line description" in desc
    assert "Second line" in desc


# ═══════════════════════════════════════════════════════════════════════════════
# A3 — _SKIP_DIRS substring-matches the absolute path, silently zeroing the index
# ═══════════════════════════════════════════════════════════════════════════════

def test_skip_dirs_ancestor_hub_workspace_still_indexes(tmp_path, monkeypatch):
    """An ancestor dir named ``.hub-workspace`` must NOT skip skills inside it."""
    skills_root = tmp_path / ".hub-workspace" / "skills"
    plugins_root = tmp_path / "plugins"
    config_path = tmp_path / "config.yaml"

    skill_dir = skills_root / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: Test skill\n---\n\n# Body\n"
    )
    plugins_root.mkdir()
    config_path.write_text("skills:\n  disabled: []\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    skills = br.load_active_skills()
    ids = {s["skill_id"] for s in skills}
    assert "my-skill" in ids


def test_skip_dirs_github_hub_not_skipped(tmp_path, monkeypatch):
    """``github.hub`` as a parent dir must not be skipped (only ``.hub`` as a path component)."""
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    config_path = tmp_path / "config.yaml"

    skill_dir = skills_root / "github.hub" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: gh-skill\ndescription: GH skill\n---\n\n# Body\n"
    )
    plugins_root.mkdir()
    config_path.write_text("skills:\n  disabled: []\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    skills = br.load_active_skills()
    ids = {s["skill_id"] for s in skills}
    assert "github.hub/my-skill" in ids


def test_skip_dirs_archive_live_not_skipped(tmp_path, monkeypatch):
    """``notes.archive-live`` must not be skipped."""
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    config_path = tmp_path / "config.yaml"

    skill_dir = skills_root / "notes.archive-live" / "other-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: other\ndescription: Other skill\n---\n\n# Body\n"
    )
    plugins_root.mkdir()
    config_path.write_text("skills:\n  disabled: []\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    skills = br.load_active_skills()
    ids = {s["skill_id"] for s in skills}
    assert "notes.archive-live/other-skill" in ids


def test_skip_dirs_genuine_archive_still_skipped(tmp_path, monkeypatch):
    """A genuine ``.archive/old`` component must still be skipped."""
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    config_path = tmp_path / "config.yaml"

    live = skills_root / "live" / "ok"
    live.mkdir(parents=True)
    (live / "SKILL.md").write_text("---\nname: ok\ndescription: Live\n---\n\n# Body\n")

    arch = skills_root / ".archive" / "old"
    arch.mkdir(parents=True)
    (arch / "SKILL.md").write_text("---\nname: old\ndescription: Old\n---\n\n# Body\n")

    plugins_root.mkdir()
    config_path.write_text("skills:\n  disabled: []\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    skills = br.load_active_skills()
    ids = {s["skill_id"] for s in skills}
    assert "live/ok" in ids
    assert not any(".archive" in i for i in ids)


# ═══════════════════════════════════════════════════════════════════════════════
# A4 — Phase 1 compaction mangles multi-line skill entries
# ═══════════════════════════════════════════════════════════════════════════════

def _load_plugin_module():
    """Load the plugin __init__.py as a module under a unique name."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(
        "_sr_test_plugin", PLUGIN_DIR / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _compact_block(plugin_mod, full_prompt):
    """Run names-only compaction through the public pure function + note."""
    import re

    match = re.search(r"<available_skills>(.*?)</available_skills>", full_prompt, re.DOTALL)
    if not match:
        return full_prompt, True
    compact_inner = plugin_mod.compact_available_skills_block(match.group(1), True)
    output = (
        full_prompt[: match.start()]
        + "<available_skills>\n"
        + compact_inner
        + "\n</available_skills>"
        + full_prompt[match.end() :]
    )
    note = plugin_mod._compaction_note()
    if "Skill descriptions are injected per-turn" not in output:
        output += note
    return output, True


def test_compact_wrapped_description_one_line():
    """A wrapped skill description must produce exactly one output line for the entry."""
    mod = _load_plugin_module()
    prompt = (
        "<available_skills>\n"
        "  creative:\n"
        "    - deep-research: Think, search, extract, synthesize a cited report.\n"
        '      Use when the user asks for a literature review, market scan, or\n'
        '      "research X thoroughly". Produces citations.\n'
        "    - image-studio: fal.ai image generation\n"
        "  research:\n"
        "    - arxiv: Search arxiv papers\n"
        "</available_skills>"
    )
    output, ok = _compact_block(mod, prompt)
    assert ok is True

    # Extract the skills block
    import re
    m = re.search(r"<available_skills>(.*?)</available_skills>", output, re.DOTALL)
    assert m
    block = m.group(1)
    lines = [l for l in block.strip().split("\n") if l.strip()]

    # deep-research must be a single line
    dr_lines = [l for l in lines if "deep-research" in l]
    assert len(dr_lines) == 1, f"Expected 1 line for deep-research, got {dr_lines}"
    assert dr_lines[0].strip() == "- deep-research"

    # No orphaned continuation lines about "literature review"
    lit_lines = [l for l in lines if "literature" in l.lower()]
    assert lit_lines == [], f"Orphaned continuation line survived: {lit_lines}"


def test_compact_wrapped_description_with_colon_in_continuation():
    """A wrapped continuation line containing ':' must be dropped, not
    misclassified as a category header."""
    mod = _load_plugin_module()
    prompt = (
        "<available_skills>\n"
        "  tools:\n"
        "    - demo: Performs several operations.\n"
        "      Use when: the user requests conversion.\n"
        "    - other: Another tool.\n"
        "</available_skills>"
    )
    output, ok = _compact_block(mod, prompt)
    assert ok is True

    import re
    m = re.search(r"<available_skills>(.*?)</available_skills>", output, re.DOTALL)
    assert m
    block = m.group(1)
    lines = [l for l in block.strip().split("\n") if l.strip()]

    # "Use when" must NOT appear as a category header
    uw_lines = [l for l in lines if "Use when" in l]
    assert uw_lines == [], f"Continuation with colon became category header: {uw_lines}"

    # demo and other must both be present as skill entries
    demo_lines = [l for l in lines if "demo" in l]
    assert len(demo_lines) == 1
    assert demo_lines[0].strip() == "- demo"

    other_lines = [l for l in lines if "other" in l]
    assert len(other_lines) == 1
    assert other_lines[0].strip() == "- other"


def test_compact_keeps_names_only_category_line():
    """Hermes' demoted-category line (agent/prompt_builder.py
    _render_skills_index) already lists names only; the skill names after
    the colon must survive compaction."""
    mod = _load_plugin_module()
    names_only = "  devops [names only]: docker-deploy, k8s-rollout"
    prompt = (
        "<available_skills>\n"
        f"{names_only}\n"
        "  research: Research helpers\n"
        "    - arxiv: Search arXiv papers\n"
        "</available_skills>"
    )
    output, ok = _compact_block(mod, prompt)
    assert ok is True
    assert names_only in output.split("\n")
    assert "  research:" in output.split("\n")
    assert "    - arxiv" in output.split("\n")


def test_compact_no_available_skills_block_returns_unchanged():
    """A prompt with no <available_skills> block must be left untouched."""
    mod = _load_plugin_module()
    prompt = "This is a system prompt with no skills block.\nJust text.\n"
    result = mod._on_llm_request(
        request={"messages": [{"role": "system", "content": prompt}]},
        session_id="",
    )
    assert result is None


def test_compact_idempotence():
    """Rewriting an already-rewritten request must not double-append the trailing note."""
    mod = _load_plugin_module()
    prompt = (
        "<available_skills>\n"
        "  test:\n"
        "    - foo: Bar\n"
        "</available_skills>"
    )
    first = mod._on_llm_request(
        request={"messages": [{"role": "system", "content": prompt}]},
        session_id="",
    )
    assert first is not None
    output1 = first["request"]["messages"][0]["content"]
    note_text = "Skill descriptions are injected per-turn"
    count1 = output1.count(note_text)
    assert count1 == 1, f"First rewrite produced {count1} notes, expected 1"

    second = mod._on_llm_request(request=first["request"], session_id="")
    assert second is None
    count2 = first["request"]["messages"][0]["content"].count(note_text)
    assert count2 == 1, f"Second rewrite produced {count2} notes, expected 1 (idempotent)"


# ═══════════════════════════════════════════════════════════════════════════════
# B — coverage gaps: hook, compaction, singleton
# ═══════════════════════════════════════════════════════════════════════════════

# These hook tests use the anonymous session (""): a named session without a
# capability snapshot skips injection before reaching the index at all.

def test_on_pre_llm_call_empty_index(monkeypatch):
    """_on_pre_llm_call returns None when the index is empty / not built."""
    mod = _load_plugin_module()
    # Reset singleton state
    br._index = None
    br._skills_by_id = {}

    # Point to empty roots
    monkeypatch.setattr(br, "SKILLS_ROOT", Path("/nonexistent-sr-test"))
    monkeypatch.setattr(br, "PLUGINS_ROOT", Path("/nonexistent-sr-test-plugins"))
    monkeypatch.setattr(br, "CONFIG_PATH", Path("/nonexistent-sr-test-config.yaml"))

    result = mod._on_pre_llm_call("", "search for images")
    assert result is None


def test_on_pre_llm_call_no_results(monkeypatch):
    """_on_pre_llm_call returns None when BM25 finds no matches."""
    mod = _load_plugin_module()

    # Build a real index with unrelated skills
    br._index = None
    br._skills_by_id = {}

    skills_root = Path("/tmp/_sr_test_noresults")
    if skills_root.exists():
        import shutil
        shutil.rmtree(skills_root)
    skills_root.mkdir(parents=True)
    (skills_root / "a/SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (skills_root / "a/SKILL.md").write_text("---\nname: alpha\ndescription: travel planning\n---\n\n# Body\n")

    plugins_root = Path("/tmp/_sr_test_noresults_plugins")
    if plugins_root.exists():
        import shutil
        shutil.rmtree(plugins_root)
    plugins_root.mkdir(parents=True)
    config_path = Path("/tmp/_sr_test_noresults_config.yaml")
    config_path.write_text("skills:\n  disabled: []\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    try:
        result = mod._on_pre_llm_call("", "zzzzqqqqxxxx")
        assert result is None
    finally:
        import shutil
        shutil.rmtree(skills_root, ignore_errors=True)
        shutil.rmtree(plugins_root, ignore_errors=True)
        config_path.unlink(missing_ok=True)
        br._index = None
        br._skills_by_id = {}


def test_on_pre_llm_call_internal_exception(monkeypatch):
    """_on_pre_llm_call swallows internal exceptions and returns None, never raises."""
    mod = _load_plugin_module()

    # Force get_index to raise
    def boom():
        raise RuntimeError("simulated failure")
    monkeypatch.setattr(br, "get_index", boom)
    # Also patch the module-level reference in the plugin
    monkeypatch.setattr(mod, "get_index", boom)

    result = mod._on_pre_llm_call("", "search for images")
    assert result is None


def test_on_pre_llm_call_hit(monkeypatch):
    """_on_pre_llm_call returns a {'context': ...} dict with expected shape on a hit."""
    mod = _load_plugin_module()

    # Build a real index
    br._index = None
    br._skills_by_id = {}

    skills_root = Path("/tmp/_sr_test_hit")
    if skills_root.exists():
        import shutil
        shutil.rmtree(skills_root)
    skills_root.mkdir(parents=True)
    # Need >=3 docs for positive Lucene IDF on a df=1 term
    for rel, name, desc in [
        ("img/image-studio", "image-studio", "fal.ai image generation and photo editing"),
        ("travel/itinerary", "travel-itinerary", "plan trips flights hotels calendar"),
        ("research/arxiv", "arxiv", "search academic papers on arxiv"),
    ]:
        d = skills_root / rel
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\n\n# Body\n"
        )

    plugins_root = Path("/tmp/_sr_test_hit_plugins")
    if plugins_root.exists():
        import shutil
        shutil.rmtree(plugins_root)
    plugins_root.mkdir(parents=True)
    config_path = Path("/tmp/_sr_test_hit_config.yaml")
    config_path.write_text("skills:\n  disabled: []\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    try:
        result = mod._on_pre_llm_call("", "generate an image with fal.ai")
        assert result is not None
        assert isinstance(result, dict)
        assert "context" in result
        ctx = result["context"]
        assert "Retrieved Skills" in ctx
        assert "image-studio" in ctx
    finally:
        import shutil
        shutil.rmtree(skills_root, ignore_errors=True)
        shutil.rmtree(plugins_root, ignore_errors=True)
        config_path.unlink(missing_ok=True)
        br._index = None
        br._skills_by_id = {}


def test_register_does_not_patch_prompt_builder(monkeypatch):
    """register() must not assign any prompt_builder attribute (catalog rule 9)."""
    mod = _load_plugin_module()

    agent_mod = types.ModuleType("agent")
    agent_pb = types.ModuleType("agent.prompt_builder")

    def original(*a, **kw):
        return "<available_skills>\n  test:\n    - foo: Bar\n</available_skills>"

    agent_pb.build_skills_system_prompt = original
    agent_pb.clear_skills_system_prompt_cache = lambda **kw: None
    agent_mod.prompt_builder = agent_pb
    sys.modules["agent"] = agent_mod
    sys.modules["agent.prompt_builder"] = agent_pb

    class Ctx:
        def register_hook(self, name, func):
            pass

        def register_middleware(self, name, func):
            pass

    try:
        mod.register(Ctx())
        assert agent_pb.build_skills_system_prompt is original
        assert not getattr(agent_pb.build_skills_system_prompt, "_skill_retrieval_patched", False)
    finally:
        sys.modules.pop("agent", None)
        sys.modules.pop("agent.prompt_builder", None)


def test_compact_available_skills_block_is_pure():
    """compact_available_skills_block is deterministic and sentinel-idempotent."""
    mod = _load_plugin_module()
    inner = "  test:\n    - foo: Bar description\n"
    once = mod.compact_available_skills_block(inner, True)
    twice = mod.compact_available_skills_block(once, True)
    assert once == twice
    assert mod._COMPACT_SENTINEL in once
    assert "Bar description" not in once
    assert mod.compact_available_skills_block(inner, False) == inner


# ─── Singleton: get_index / get_skill_info ──────────────────────────────────

@pytest.fixture
def reset_singleton():
    """Reset module-level singleton state before and after each test."""
    br._index = None
    br._skills_by_id = {}
    yield
    br._index = None
    br._skills_by_id = {}


def test_get_index_builds_and_caches(tmp_path, monkeypatch, reset_singleton):
    """get_index builds on first call and returns the cached index on second."""
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    config_path = tmp_path / "config.yaml"

    # Two docs so the query term discriminates between documents
    (skills_root / "a/SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (skills_root / "a/SKILL.md").write_text(
        "---\nname: alpha\ndescription: travel planning flights\n---\n\n# Body\n"
    )
    (skills_root / "b/SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (skills_root / "b/SKILL.md").write_text(
        "---\nname: beta\ndescription: image generation editing\n---\n\n# Body\n"
    )
    plugins_root.mkdir()
    config_path.write_text("skills:\n  disabled: []\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    idx1 = br.get_index()
    assert idx1 is not None
    assert idx1._built

    idx2 = br.get_index()
    assert idx2 is idx1  # cached — same object


def test_get_index_returns_none_for_empty(monkeypatch, reset_singleton):
    """get_index returns None and logs a warning when no skills are found."""
    monkeypatch.setattr(br, "SKILLS_ROOT", Path("/nonexistent-gi-test"))
    monkeypatch.setattr(br, "PLUGINS_ROOT", Path("/nonexistent-gi-test-plugins"))
    monkeypatch.setattr(br, "CONFIG_PATH", Path("/nonexistent-gi-test-config.yaml"))

    assert br.get_index() is None


def test_get_skill_info_returns_none_for_unknown(reset_singleton):
    """get_skill_info returns None for an unknown skill id."""
    assert br.get_skill_info("nonexistent-skill-id") is None


def test_get_skill_info_returns_info_after_build(tmp_path, monkeypatch, reset_singleton):
    """get_skill_info returns skill metadata after the index is built."""
    skills_root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    config_path = tmp_path / "config.yaml"

    # Need >=3 docs for positive Lucene IDF
    (skills_root / "a/my-skill").mkdir(parents=True)
    (skills_root / "a/my-skill/SKILL.md").write_text(
        "---\nname: my-skill\ndescription: A test skill for things\n---\n\n# Body\n"
    )
    (skills_root / "b/other").mkdir(parents=True)
    (skills_root / "b/other/SKILL.md").write_text(
        "---\nname: other\ndescription: Another skill for testing\n---\n\n# Body\n"
    )
    (skills_root / "c/third").mkdir(parents=True)
    (skills_root / "c/third/SKILL.md").write_text(
        "---\nname: third\ndescription: Third skill for coverage\n---\n\n# Body\n"
    )
    plugins_root.mkdir()
    config_path.write_text("skills:\n  disabled: []\n")

    monkeypatch.setattr(br, "SKILLS_ROOT", skills_root)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins_root)
    monkeypatch.setattr(br, "CONFIG_PATH", config_path)

    br.get_index()
    info = br.get_skill_info("a/my-skill")
    assert info is not None
    assert info["name"] == "my-skill"
    assert "test skill" in info["description"].lower()