"""Issue #14 regression: _skill_should_show arity across Hermes versions.

Hermes v0.20.x ships ``_skill_should_show`` with 3 positional parameters
(no ``session_platform``). v0.21.x adds a 4th ``session_platform`` param
with a default. The plugin calls the function with 4 arguments at two
call sites in ``load_active_skills`` (skill files + registry skills), so
a 3-arg host must be wrapped at load time or the BM25 index build dies
with TypeError and Phase 2 injection silently returns None every turn.
"""

import pathlib
import sys
import types

import pytest

import bm25_retriever as br


def _write_skill(root: pathlib.Path, name: str, description: str) -> None:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: \"{description}\"\n---\n\n# {name}\n"
    )


def _install_three_arg_hermes(monkeypatch, tmp_path):
    """Stub agent.* with a v0.20.5-shaped, 3-positional-arg _skill_should_show."""
    recorded = []

    def _should_show_v0205(conditions, available_tools, available_toolsets):
        # Exact v0.20.5 behavior: 3 positional params, positional-only
        # from the caller's perspective (no **kwargs, no 4th param).
        recorded.append((conditions, available_tools, available_toolsets))
        if available_tools is None and available_toolsets is None:
            return True
        return True

    pb = types.ModuleType("agent.prompt_builder")
    pb._current_session_platform_hint = lambda: ""
    pb.extract_skill_conditions = lambda frontmatter: {}
    pb._skill_should_show = _should_show_v0205

    def _parse_skill_file(skill_file):
        name, desc = br._parse_skill_md(skill_file)
        return True, {"name": name}, desc

    def _build_snapshot_entry(skill_file, root, frontmatter, description):
        rel = pathlib.Path(skill_file).relative_to(root)
        return {
            "category": "general",
            "skill_name": rel.parent.name,
            "frontmatter_name": frontmatter["name"],
            "description": description,
        }

    pb._parse_skill_file = _parse_skill_file
    pb._build_snapshot_entry = _build_snapshot_entry

    skills_root = tmp_path / "skills"
    skills_root.mkdir()
    _write_skill(skills_root, "alpha", "Alpha skill")

    su = types.ModuleType("agent.skill_utils")
    su.get_disabled_skill_names = lambda platform=None: set()
    su.get_project_skills_dirs = lambda: []
    su.get_all_skills_dirs = lambda: [skills_root]
    su.iter_project_skill_files = lambda root: sorted(pathlib.Path(root).rglob("SKILL.md"))
    su.iter_skill_index_files = lambda root, filename: sorted(pathlib.Path(root).rglob(filename))

    agent_pkg = types.ModuleType("agent")
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.prompt_builder", pb)
    monkeypatch.setitem(sys.modules, "agent.skill_utils", su)
    return pb, recorded


def _reset_index_caches():
    br._indexes_by_home.clear()
    br._skills_by_home_and_id.clear()
    br._cap_key_order_by_home.clear()
    br._override_indexes_by_cap.clear()
    br._override_skills_by_cap.clear()
    br._index = None
    br._skills_by_id = {}


def test_index_builds_against_three_arg_should_show(monkeypatch, tmp_path):
    """A 3-positional-arg host must not raise TypeError during index build."""
    pb, recorded = _install_three_arg_hermes(monkeypatch, tmp_path)
    _reset_index_caches()
    try:
        skills = br.load_active_skills()
        assert skills, "corpus must not silently empty against v0.20.5 host"
        assert [s["name"] for s in skills] == ["alpha"]
        assert recorded, "host _skill_should_show must actually be called"
    finally:
        _reset_index_caches()


def test_get_index_succeeds_with_three_arg_host(monkeypatch, tmp_path):
    """get_index() end-to-end against a 3-arg host, as the issue traceback hit."""
    _install_three_arg_hermes(monkeypatch, tmp_path)
    _reset_index_caches()
    try:
        index = br.get_index()
        assert index is not None
        assert index._corpus_ids, "index must contain documents, not an empty build"
    finally:
        _reset_index_caches()


def test_shim_not_applied_for_four_arg_host(monkeypatch, tmp_path):
    """A 4-arg host keeps its own function object (no needless wrapper)."""
    import inspect

    _install_three_arg_hermes(monkeypatch, tmp_path)
    # Upgrade the stub to the modern 4-arg shape.
    def _should_show_v021(conditions, available_tools, available_toolsets, session_platform=None):
        return True

    sys.modules["agent.prompt_builder"]._skill_should_show = _should_show_v021
    _reset_index_caches()
    try:
        skills = br.load_active_skills()
        assert skills  # loader ran
        assert sys.modules["agent.prompt_builder"]._skill_should_show is _should_show_v021
    finally:
        _reset_index_caches()


def test_shim_survives_inspection_failure(monkeypatch, tmp_path):
    """If inspect.signature raises, the loader must still not crash.

    A host object whose signature cannot be inspected is treated as the
    modern 4-arg form: the call may then legitimately raise TypeError,
    which add_skill_file catches per-skill (fail-soft), never aborting
    the whole index build.
    """
    pb, _ = _install_three_arg_hermes(monkeypatch, tmp_path)

    class _Opaque:
        def __call__(self, conditions, available_tools, available_toolsets):
            return True

    pb._skill_should_show = _Opaque()
    _reset_index_caches()
    try:
        skills = br.load_active_skills()
        assert skills, "opaque host object must not empty the corpus"
    finally:
        _reset_index_caches()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))