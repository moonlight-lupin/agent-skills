"""Regression tests for Issue #8 round 2 findings (audaimousa, 2026-09-06).

Written by Hermes BEFORE the fix (honest RED contract). Each test encodes
the corpus-parity invariant from the issue:

    set(BM25 corpus identities) == set(Hermes resolved identities)

Divergence 1 — capability gates: load_active_skills() passed
available_tools=None/available_toolsets=None to _skill_should_show, which
fails open, so requires_tools/requires_toolsets/fallback_for_tools/
fallback_for_toolsets conditions were never evaluated. Hermes hides those
skills; the corpus indexed them.

Divergence 2 — plugin-skill extras: the plugin scan walked the plugins
directory directly, indexing skills from DISABLED plugins and skills that
Hermes' own registry filter (platform match + disabled list) would exclude.
Hermes' resolved set comes from get_plugin_manager().list_plugin_skill_metadata()
(see tools/skills_tool.py:245-250), filtered by skill_matches_platform and
_is_skill_disabled. The corpus must match that, not the raw directory.
"""

import importlib
import sys
import types

import pytest

import bm25_retriever as br


def _load_fresh():
    importlib.reload(br)
    return br


def _write_skill(root, rel, name, description, extra_frontmatter=""):
    skill_dir = root / rel
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    fm = f'name: {name}\ndescription: "{description}"'
    if extra_frontmatter:
        fm += "\n" + extra_frontmatter
    skill_md.write_text(f"---\n{fm}\n---\n\n# {name}\n")
    return skill_md


def _install_hermes_stubs(monkeypatch, *, conditions_map=None):
    """Stub agent.prompt_builder / agent.skill_utils with controllable gates.

    conditions_map: {skill_name: conditions_dict}. _skill_should_show
    evaluates the four tool/toolset condition families exactly like
    agent/prompt_builder.py:1158-1176 (fail-open only when BOTH sets are None).
    """
    pb = types.ModuleType("agent.prompt_builder")
    pb._current_session_platform_hint = lambda: ""
    pb.extract_skill_conditions = lambda fm: (conditions_map or {}).get(
        fm.get("name", ""), {}
    )

    def _should_show(conditions, available_tools, available_toolsets, platform=None):
        if available_tools is None and available_toolsets is None:
            return True  # fail-open, same as Hermes
        at, ats = available_tools or set(), available_toolsets or set()
        return not (
            any(ts in ats for ts in conditions.get("fallback_for_toolsets", []))
            or any(t in at for t in conditions.get("fallback_for_tools", []))
            or any(ts not in ats for ts in conditions.get("requires_toolsets", []))
            or any(t not in at for t in conditions.get("requires_tools", []))
        )

    pb._skill_should_show = _should_show

    def _parse_like_hermes(skill_file):
        name, desc = br._parse_skill_md(skill_file)
        return True, {"name": name}, desc

    pb._parse_skill_file = _parse_like_hermes

    def _build_snapshot_entry(skill_file, root, frontmatter, description):
        rel = skill_file.relative_to(root)
        return {
            "category": "general",
            "skill_name": rel.parent.name,
            "frontmatter_name": frontmatter["name"],
            "description": description,
        }

    pb._build_snapshot_entry = _build_snapshot_entry

    su = types.ModuleType("agent.skill_utils")
    su.get_disabled_skill_names = lambda platform=None: set()
    su.get_project_skills_dirs = lambda: []
    su.get_all_skills_dirs = lambda: []
    su.iter_project_skill_files = lambda root: sorted(root.rglob("SKILL.md"))
    su.iter_skill_index_files = lambda root, filename: sorted(root.rglob(filename))

    agent_pkg = types.ModuleType("agent")
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.prompt_builder", pb)
    monkeypatch.setitem(sys.modules, "agent.skill_utils", su)
    return {"su": su, "pb": pb}


def _point_discovery_at(monkeypatch, stubs, *roots):
    """Point the stubbed discovery helpers at fixture roots."""
    su = stubs["su"]
    monkeypatch.setattr(su, "get_all_skills_dirs", lambda: list(roots))


# ─── Divergence 1: capability gates must be evaluated ───────────────────────


def test_requires_tools_hidden_when_tool_absent(monkeypatch, tmp_path):
    """requires_tools skill with tool absent: Hermes hides it, corpus must too."""
    br = _load_fresh()
    root = tmp_path / "skills"
    _write_skill(root, "gated", "gated-skill", "quasarneedle9z unique token")
    stubs = _install_hermes_stubs(
        monkeypatch,
        conditions_map={"gated-skill": {"requires_tools": ["special_tool"]}},
    )
    _point_discovery_at(monkeypatch, stubs, root)
    skills = br.load_active_skills(
        available_tools={"other_tool"}, available_toolsets=set()
    )
    ids = {s["frontmatter_name"] for s in skills}
    assert "gated-skill" not in ids


def test_requires_tools_visible_when_tool_present(monkeypatch, tmp_path):
    br = _load_fresh()
    root = tmp_path / "skills"
    _write_skill(root, "gated", "gated-skill", "needs tool")
    stubs = _install_hermes_stubs(
        monkeypatch,
        conditions_map={"gated-skill": {"requires_tools": ["special_tool"]}},
    )
    _point_discovery_at(monkeypatch, stubs, root)
    skills = br.load_active_skills(
        available_tools={"special_tool"}, available_toolsets=set()
    )
    ids = {s["frontmatter_name"] for s in skills}
    assert "gated-skill" in ids


def test_requires_toolsets_hidden_when_toolset_absent(monkeypatch, tmp_path):
    br = _load_fresh()
    root = tmp_path / "skills"
    _write_skill(root, "gated", "gated-skill", "needs toolset")
    stubs = _install_hermes_stubs(
        monkeypatch,
        conditions_map={"gated-skill": {"requires_toolsets": ["special_set"]}},
    )
    _point_discovery_at(monkeypatch, stubs, root)
    skills = br.load_active_skills(
        available_tools=set(), available_toolsets={"other_set"}
    )
    ids = {s["frontmatter_name"] for s in skills}
    assert "gated-skill" not in ids


def test_fallback_for_tools_hidden_when_target_present(monkeypatch, tmp_path):
    br = _load_fresh()
    root = tmp_path / "skills"
    _write_skill(root, "fb", "fallback-skill", "fallback for primary")
    stubs = _install_hermes_stubs(
        monkeypatch,
        conditions_map={"fallback-skill": {"fallback_for_tools": ["primary_tool"]}},
    )
    _point_discovery_at(monkeypatch, stubs, root)
    skills = br.load_active_skills(
        available_tools={"primary_tool"}, available_toolsets=set()
    )
    ids = {s["frontmatter_name"] for s in skills}
    assert "fallback-skill" not in ids


def test_no_capability_args_fails_open(monkeypatch, tmp_path):
    """Backward compat: called without capability args, corpus keeps
    everything (same fail-open semantics Hermes uses for unknown state)."""
    br = _load_fresh()
    root = tmp_path / "skills"
    _write_skill(root, "gated", "gated-skill", "needs tool")
    stubs = _install_hermes_stubs(
        monkeypatch,
        conditions_map={"gated-skill": {"requires_tools": ["special_tool"]}},
    )
    _point_discovery_at(monkeypatch, stubs, root)
    skills = br.load_active_skills()
    ids = {s["frontmatter_name"] for s in skills}
    assert "gated-skill" in ids


# ─── Divergence 2: plugin skills from Hermes' registry, not raw dirs ───────


def test_disabled_plugin_skills_excluded(monkeypatch, tmp_path):
    """Skills of a disabled plugin must not enter the corpus. Hermes resolves
    plugin skills via list_plugin_skill_metadata() on the live registry; a
    raw directory walk would index disabled plugins' skills."""
    br = _load_fresh()
    plugins_root = tmp_path / "plugins"
    _write_skill(
        plugins_root / "ponytail" / "skills", "audit", "ponytail-audit",
        "ponytail audit unique token zebraquill7x",
    )
    _install_hermes_stubs(monkeypatch)

    registry = {
        "other-plugin:real-skill": {
            "name": "other-plugin:real-skill",
            "description": "Registered skill from an enabled plugin",
            "category": "plugin",
            "frontmatter": {"name": "real-skill", "description": "x"},
            "bare_name": "real-skill",
        }
    }

    class FakePM:
        def list_plugin_skill_metadata(self):
            return [
                {
                    "name": q,
                    "description": e["description"],
                    "category": "plugin",
                    "frontmatter": dict(e["frontmatter"]),
                }
                for q, e in registry.items()
            ]

    monkeypatch.setattr(br, "get_plugins_dir", lambda: plugins_root)

    pm_mod = types.ModuleType("hermes_cli.plugins")
    pm_mod.discover_plugins = lambda: None
    pm_mod.get_plugin_manager = lambda: FakePM()
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", pm_mod)

    skills = br.load_active_skills()
    names = {s["name"] for s in skills}
    assert "ponytail-audit" not in names
    assert "other-plugin:real-skill" in names


def test_plugin_registry_skills_pass_capability_gate(monkeypatch, tmp_path):
    """Registry-sourced plugin skills must also pass the capability gate."""
    br = _load_fresh()
    plugins_root = tmp_path / "plugins"
    _write_skill(plugins_root / "p1" / "skills", "a", "a-skill", "alpha wobble9q")
    _install_hermes_stubs(
        monkeypatch,
        conditions_map={"a-skill": {"requires_tools": ["missing_tool"]}},
    )

    class FakePM:
        def list_plugin_skill_metadata(self):
            return [
                {
                    "name": "p1:a-skill",
                    "description": "alpha wobble9q",
                    "category": "plugin",
                    "frontmatter": {
                        "name": "a-skill", "description": "alpha wobble9q",
                        "requires_tools": ["missing_tool"],
                    },
                }
            ]

    monkeypatch.setattr(br, "get_plugins_dir", lambda: plugins_root)
    pm_mod = types.ModuleType("hermes_cli.plugins")
    pm_mod.discover_plugins = lambda: None
    pm_mod.get_plugin_manager = lambda: FakePM()
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", pm_mod)

    skills = br.load_active_skills(
        available_tools=set(), available_toolsets={"some_set"}
    )
    names = {s["name"] for s in skills}
    assert "p1:a-skill" not in names


def test_registry_unavailable_falls_back_to_dir_scan(monkeypatch, tmp_path):
    """If the Hermes plugin registry cannot be reached, keep the current
    directory scan so the corpus never silently empties."""
    br = _load_fresh()
    plugins_root = tmp_path / "plugins"
    _write_skill(plugins_root / "p1" / "skills", "a", "a-skill", "alpha token")
    _install_hermes_stubs(monkeypatch)
    monkeypatch.setattr(br, "get_plugins_dir", lambda: plugins_root)

    pm_mod = types.ModuleType("hermes_cli.plugins")
    pm_mod.discover_plugins = lambda: None

    def _boom():
        raise RuntimeError("no registry in standalone context")

    pm_mod.get_plugin_manager = _boom
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", pm_mod)

    skills = br.load_active_skills()
    names = {s["name"] for s in skills}
    assert "p1:a-skill" in names  # dir-scan fallback kept it


# ─── Corpus-parity smoke: both divergences at once ──────────────────────────


def test_corpus_parity_gated_and_plugin(monkeypatch, tmp_path):
    """The invariant from the issue, both divergence classes combined:
    no gated skill indexed, no disabled-plugin skill indexed, registry
    skills present."""
    br = _load_fresh()
    root = tmp_path / "skills"
    plugins_root = tmp_path / "plugins"
    _write_skill(root, "ok", "plain-skill", "always visible")
    _write_skill(root, "gated", "gated-skill", "quasarneedle9z")
    _write_skill(
        plugins_root / "ponytail" / "skills", "audit", "ponytail-audit",
        "zebraquill7x",
    )
    stubs = _install_hermes_stubs(
        monkeypatch,
        conditions_map={"gated-skill": {"requires_tools": ["special_tool"]}},
    )
    _point_discovery_at(monkeypatch, stubs, root)

    class FakePM:
        def list_plugin_skill_metadata(self):
            return [
                {
                    "name": "helper:bundled",
                    "description": "bundled from enabled plugin",
                    "category": "plugin",
                    "frontmatter": {"name": "bundled", "description": "x"},
                }
            ]

    monkeypatch.setattr(br, "get_plugins_dir", lambda: plugins_root)
    pm_mod = types.ModuleType("hermes_cli.plugins")
    pm_mod.discover_plugins = lambda: None
    pm_mod.get_plugin_manager = lambda: FakePM()
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", pm_mod)

    skills = br.load_active_skills(
        available_tools={"terminal"}, available_toolsets={"core"}
    )
    names = {s["name"] for s in skills}
    ids = {s["skill_id"] for s in skills}
    assert "gated-skill" not in names          # capability gate enforced
    assert "ponytail-audit" not in names       # disabled-plugin skill excluded
    assert "helper:bundled" in names           # registry skill present
    assert "helper:bundled" in ids             # and keyed for retrieval