"""Mid-scan fallback regression (code-review note on PR 131290).

Hazard: bm25_retriever imports read-only Hermes helpers
(_build_snapshot_entry, _parse_skill_file...). A Hermes upgrade that changes
their signatures raises TypeError mid-scan. Before the guard, the exception
propagated and the index stayed empty while the llm_request middleware still
stripped all descriptions from the prompt — skills silently undiscoverable.
The guard must fall back to the standalone loader instead.
"""

import importlib
import sys
import types
from pathlib import Path

import bm25_retriever as br


def _fresh_retriever():
    mod = importlib.import_module("bm25_retriever")
    return importlib.reload(mod)


def test_mid_scan_signature_change_falls_back_to_legacy(monkeypatch, tmp_path):
    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    (skills_root / "alpha").mkdir()
    (skills_root / "alpha" / "SKILL.md").write_text(
        "---\nname: alpha\ndescription: Alpha skill\n---\nbody"
    )

    # Hermetic legacy fallback: the standalone loader resolves paths from
    # HERMES_HOME/HOME when hermes_constants is unavailable.
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    # No legacy path overrides → the Hermes branch runs.
    monkeypatch.setattr(br, "SKILLS_ROOT", None)
    monkeypatch.setattr(br, "PLUGINS_ROOT", None)
    monkeypatch.setattr(br, "CONFIG_PATH", None)

    # Fake Hermes helpers where _build_snapshot_entry has a CHANGED signature.
    prompt_builder = types.ModuleType("agent.prompt_builder")
    prompt_builder._current_session_platform_hint = lambda: ""
    prompt_builder.extract_skill_conditions = lambda frontmatter: {}
    prompt_builder._skill_should_show = lambda *a, **k: True
    prompt_builder._parse_skill_file = lambda f: (True, {"name": "x"}, "d")

    def broken_snapshot_entry(*args, **kwargs):
        raise TypeError("_build_snapshot_entry() takes 6 positional arguments")

    prompt_builder._build_snapshot_entry = broken_snapshot_entry

    skill_utils = types.ModuleType("agent.skill_utils")
    skill_utils.get_disabled_skill_names = lambda platform=None: set()
    skill_utils.get_project_skills_dirs = lambda: []
    skill_utils.get_all_skills_dirs = lambda: [skills_root]
    skill_utils.iter_project_skill_files = lambda root: []
    skill_utils.iter_skill_index_files = lambda root, filename: sorted(
        root.rglob(filename)
    )

    agent = types.ModuleType("agent")
    monkeypatch.setitem(sys.modules, "agent", agent)
    monkeypatch.setitem(sys.modules, "agent.prompt_builder", prompt_builder)
    monkeypatch.setitem(sys.modules, "agent.skill_utils", skill_utils)

    skills = br.load_active_skills()
    # The standalone loader picked the skill up — corpus is NOT empty.
    assert any(s["name"] == "alpha" for s in skills)