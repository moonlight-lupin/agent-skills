"""BM25 index cache correctness (v0.3.1).

Bug 1: the cache key omitted the session platform. The corpus depends on it
(``skills.platform_disabled.<platform>`` and ``session_platforms`` gates), so
an index built by a discord session was reused by a telegram session and
suggested skills disabled for telegram.

Bug 2: the index was never invalidated for the process lifetime. New or
patched skills (``skill_manage``) and ``hermes skills disable`` were ignored
until restart. A zero-skill install also rescanned every root each turn.
"""

import importlib
import importlib.util
import logging
import pathlib
import sys
import types

import yaml

import bm25_retriever as br

_PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent


def _load_fresh():
    importlib.reload(br)
    return br


def _load_plugin_init():
    spec = importlib.util.spec_from_file_location(
        "skill_retrieval_init_cache_test", _PLUGIN_DIR / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["skill_retrieval_init_cache_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_skill(root, rel, name, description):
    skill_dir = root / rel
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: "{description}"\n---\n\n# {name}\n'
    )


def _install_hermes_stubs(monkeypatch, tmp_path, *roots):
    """Stub agent.prompt_builder / agent.skill_utils over a temp Hermes home.

    ``get_disabled_skill_names`` reads config.yaml on every call, like
    Hermes (global list ∪ ``platform_disabled.<platform>``).
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(home))

    pb = types.ModuleType("agent.prompt_builder")
    pb._current_session_platform_hint = lambda: ""
    pb.extract_skill_conditions = lambda fm: {}
    pb._skill_should_show = lambda conditions, tools, toolsets, platform=None: True

    def _parse(skill_file):
        name, desc = br._parse_skill_md(skill_file)
        return True, {"name": name}, desc

    def _entry(skill_file, root, frontmatter, description):
        return {
            "category": "general",
            "skill_name": skill_file.parent.name,
            "frontmatter_name": frontmatter["name"],
            "description": description,
        }

    pb._parse_skill_file = _parse
    pb._build_snapshot_entry = _entry
    pb.build_skills_system_prompt = lambda *a, **kw: ""
    pb.clear_calls = []
    pb.clear_skills_system_prompt_cache = (
        lambda *, clear_snapshot=False: pb.clear_calls.append(clear_snapshot)
    )

    def _disabled(platform=None):
        cfg_path = home / "config.yaml"
        if not cfg_path.exists():
            return set()
        skills_cfg = (yaml.safe_load(cfg_path.read_text()) or {}).get("skills") or {}
        out = set(skills_cfg.get("disabled") or [])
        if platform:
            out |= set((skills_cfg.get("platform_disabled") or {}).get(platform) or [])
        return out

    su = types.ModuleType("agent.skill_utils")
    su.get_disabled_skill_names = _disabled
    su.get_project_skills_dirs = lambda: []
    su.get_all_skills_dirs = lambda: list(roots)
    su.iter_project_skill_files = lambda root: sorted(root.rglob("SKILL.md"))
    su.iter_skill_index_files = lambda root, filename: sorted(root.rglob(filename))

    agent_pkg = types.ModuleType("agent")
    agent_pkg.prompt_builder = pb
    agent_pkg.skill_utils = su
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.prompt_builder", pb)
    monkeypatch.setitem(sys.modules, "agent.skill_utils", su)
    return {"pb": pb, "su": su, "home": home}


def _seed(root):
    _write_skill(root, "a", "secret-skill", "zorblat payroll")
    _write_skill(root, "b", "f1", "filler one")
    _write_skill(root, "c", "f2", "filler two things")


def _ids(index, query):
    return [skill_id for skill_id, _ in (index.retrieve(query) if index else [])]


# ─── Bug 1: platform-scoped cache key ────────────────────────────────────────

def test_platform_disabled_skill_not_reused_across_platforms(monkeypatch, tmp_path):
    br = _load_fresh()
    root = tmp_path / "skills"
    _seed(root)
    stubs = _install_hermes_stubs(monkeypatch, tmp_path, root)
    (stubs["home"] / "config.yaml").write_text(
        "skills:\n  platform_disabled:\n    telegram: [secret-skill]\n"
    )
    plat = {"v": "discord"}
    stubs["pb"]._current_session_platform_hint = lambda: plat["v"]

    assert "a" in _ids(br.get_index(), "zorblat")   # built by a discord session
    plat["v"] = "telegram"                           # skill is platform_disabled here
    assert "a" not in _ids(br.get_index(), "zorblat")
    plat["v"] = "discord"
    assert "a" in _ids(br.get_index(), "zorblat")


def test_skill_info_uses_platform_scoped_key(monkeypatch, tmp_path):
    """get_skill_info must resolve against the same corpus as get_index."""
    br = _load_fresh()
    root = tmp_path / "skills"
    _seed(root)
    stubs = _install_hermes_stubs(monkeypatch, tmp_path, root)
    (stubs["home"] / "config.yaml").write_text(
        "skills:\n  platform_disabled:\n    telegram: [secret-skill]\n"
    )
    plat = {"v": "discord"}
    stubs["pb"]._current_session_platform_hint = lambda: plat["v"]

    br.get_index()
    assert br.get_skill_info("a")["name"] == "secret-skill"
    plat["v"] = "telegram"
    br.get_index()
    assert br.get_skill_info("a") is None


def test_platform_key_failure_degrades(monkeypatch, tmp_path):
    """A failing platform hint / disabled lookup must not raise from the key."""
    br = _load_fresh()
    stubs = _install_hermes_stubs(monkeypatch, tmp_path)

    def boom(*_a, **_kw):
        raise RuntimeError("no session context")

    stubs["pb"]._current_session_platform_hint = boom
    stubs["su"].get_disabled_skill_names = boom
    assert br._session_platform_key_parts() == (None, None)


# ─── Bug 2: invalidation ─────────────────────────────────────────────────────

def test_new_skill_picked_up_without_restart(monkeypatch, tmp_path):
    br = _load_fresh()
    root = tmp_path / "skills"
    _seed(root)
    _install_hermes_stubs(monkeypatch, tmp_path, root)

    assert _ids(br.get_index(), "quuxify") == []
    # Dropped in by hand / another process: no clear_skills_system_prompt_cache.
    _write_skill(root, "c-new", "quuxify-helper", "quuxify widgets")
    assert "c-new" in _ids(br.get_index(), "quuxify")
    assert br.get_skill_info("c-new")["name"] == "quuxify-helper"


def test_skill_disabled_via_config_dropped(monkeypatch, tmp_path):
    br = _load_fresh()
    root = tmp_path / "skills"
    _seed(root)
    stubs = _install_hermes_stubs(monkeypatch, tmp_path, root)

    assert "a" in _ids(br.get_index(), "zorblat")
    (stubs["home"] / "config.yaml").write_text("skills:\n  disabled: [secret-skill]\n")
    assert "a" not in _ids(br.get_index(), "zorblat")


def test_clear_skills_system_prompt_cache_clears_index(monkeypatch, tmp_path):
    """skill_manage patches a nested SKILL.md, then clears Hermes' prompt cache.

    A content-only edit of a nested SKILL.md changes no directory mtime, so
    only the wrapped clear_skills_system_prompt_cache can invalidate it.
    """
    br = _load_fresh()
    root = tmp_path / "skills"
    _seed(root)
    _write_skill(root, "cat/deep", "deep-skill", "original words")
    stubs = _install_hermes_stubs(monkeypatch, tmp_path, root)
    mod = _load_plugin_init()
    mod.register(types.SimpleNamespace(register_hook=lambda *a, **kw: None))

    assert "deep" in _ids(br.get_index(), "original")
    _write_skill(root, "cat/deep", "deep-skill", "frobnicate spreadsheets")
    # Hermes callers import the function at call time (function-local import).
    from agent.prompt_builder import clear_skills_system_prompt_cache
    clear_skills_system_prompt_cache(clear_snapshot=True)

    assert stubs["pb"].clear_calls == [True]   # original still runs
    assert "deep" in _ids(br.get_index(), "frobnicate")
    assert "frobnicate" in br.get_skill_info("deep")["description"]


def test_empty_corpus_cached_and_warned_once(monkeypatch, tmp_path, caplog):
    br = _load_fresh()
    root = tmp_path / "skills"
    root.mkdir()
    _install_hermes_stubs(monkeypatch, tmp_path, root)
    calls = []
    real_loader = br.load_active_skills

    def counting_loader(*a, **kw):
        calls.append(1)
        return real_loader(*a, **kw)

    monkeypatch.setattr(br, "load_active_skills", counting_loader)
    with caplog.at_level(logging.WARNING, logger=br.logger.name):
        for _ in range(5):
            assert br.get_index() is None
    assert len(calls) == 1
    assert sum("No active skills" in r.getMessage() for r in caplog.records) == 1

    _seed(root)
    assert "a" in _ids(br.get_index(), "zorblat")
    assert len(calls) == 2
