"""Round-4 confirmation-review fixes. Each test calls the plugin the way a turn does."""

import importlib
import importlib.util
import os
import sys
import types
from pathlib import Path

import bm25_retriever as br

_PLUGIN_DIR = Path(__file__).resolve().parent.parent


def _load_plugin(name="skill_retrieval_round4"):
    spec = importlib.util.spec_from_file_location(name, _PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_skill(root, rel, name, description):
    skill_dir = Path(root) / rel
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: "{description}"\n---\n\n# {name}\n'
    )


def _point_legacy(monkeypatch, tmp_path):
    skills = tmp_path / "skills"
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    cfg = tmp_path / "config.yaml"
    cfg.write_text("skills:\n  disabled: []\n")
    br.clear_index_cache()
    monkeypatch.setattr(br, "SKILLS_ROOT", skills)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins)
    monkeypatch.setattr(br, "CONFIG_PATH", cfg)
    return skills


def _install_discovery(monkeypatch, *, skills_dirs, disabled, plugins_root):
    pb = types.ModuleType("agent.prompt_builder")
    pb._current_session_platform_hint = lambda: ""
    pb.extract_skill_conditions = lambda fm: {}
    pb._skill_should_show = lambda *a, **k: True

    def _parse(skill_file):
        name, desc = br._parse_skill_md(skill_file)
        return True, {"name": name}, desc

    def _entry(skill_file, skill_root, frontmatter, description):
        return {
            "category": "general",
            "skill_name": skill_file.parent.name,
            "frontmatter_name": frontmatter["name"],
            "description": description,
        }

    pb._parse_skill_file = _parse
    pb._build_snapshot_entry = _entry

    su = types.ModuleType("agent.skill_utils")
    su.get_disabled_skill_names = lambda platform=None: set(disabled)
    su.get_project_skills_dirs = lambda: []
    su.get_all_skills_dirs = lambda: list(skills_dirs)
    su.iter_project_skill_files = lambda root: sorted(Path(root).rglob("SKILL.md"))
    su.iter_skill_index_files = lambda root, filename: sorted(Path(root).rglob(filename))
    su.skill_matches_platform = lambda fm: True
    agent_pkg = types.ModuleType("agent")
    agent_pkg.prompt_builder = pb
    agent_pkg.skill_utils = su
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.prompt_builder", pb)
    monkeypatch.setitem(sys.modules, "agent.skill_utils", su)

    plugins = types.ModuleType("hermes_cli.plugins")
    plugins.discover_plugins = lambda: None
    plugins.get_plugin_manager = lambda: None
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins)
    monkeypatch.setattr(br, "get_plugins_dir", lambda: plugins_root)
    monkeypatch.setattr(br, "SKILLS_ROOT", None)
    monkeypatch.setattr(br, "CONFIG_PATH", None)


def _stub_manifest_roots(monkeypatch, root, tmp_path):
    su = types.ModuleType("agent.skill_utils")
    su.get_all_skills_dirs = lambda: [root]
    su.get_project_skills_dirs = lambda: []
    agent_pkg = types.ModuleType("agent")
    agent_pkg.skill_utils = su
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.skill_utils", su)
    monkeypatch.setattr(br, "get_plugins_dir", lambda: tmp_path / "plugins-missing")
    monkeypatch.setattr(br, "get_config_path", lambda: tmp_path / "no-config.yaml")


def _marker_entry(manifest, root):
    marker = os.path.join(str(root), "_org", ".active_org")
    for path, sig in manifest:
        if path == marker:
            return sig
    return None


def _skill_paths(manifest):
    return {path for path, _sig in manifest if str(path).endswith("SKILL.md")}


# ─── FIX 1: org-mirror invalidation ──────────────────────────────────────────


def test_org_marker_create_switch_and_delete_change_manifest(monkeypatch, tmp_path):
    importlib.reload(br)
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root / "_org" / "acme", "demo", "acme-demo", "acme org skill")
    _write_skill(root / "_org" / "beta", "demo", "beta-demo", "beta org skill")
    _stub_manifest_roots(monkeypatch, root, tmp_path)

    absent = br._corpus_manifest()
    assert _marker_entry(absent, root) == ("absent",)
    assert not any("_org" in path for path in _skill_paths(absent))

    marker = root / "_org" / ".active_org"
    marker.write_text("acme\n")
    active_acme = br._corpus_manifest()
    assert active_acme != absent
    acme_paths = _skill_paths(active_acme)
    assert any(path.endswith(os.path.join("_org", "acme", "demo", "SKILL.md")) for path in acme_paths)
    assert not any("_org" + os.sep + "beta" in path for path in acme_paths)

    marker.write_text("beta\n")
    active_beta = br._corpus_manifest()
    assert active_beta != active_acme
    beta_paths = _skill_paths(active_beta)
    assert any(path.endswith(os.path.join("_org", "beta", "demo", "SKILL.md")) for path in beta_paths)
    assert not any("_org" + os.sep + "acme" in path for path in beta_paths)

    marker.unlink()
    deleted = br._corpus_manifest()
    assert deleted != active_beta
    assert _marker_entry(deleted, root) == ("absent",)
    assert not any("_org" in path for path in _skill_paths(deleted))


# ─── FIX 2: local colon paths are not plugin-owned ───────────────────────────


def test_local_colon_directory_is_not_indexed(monkeypatch, tmp_path):
    importlib.reload(br)
    skills = _point_legacy(monkeypatch, tmp_path)
    _write_skill(skills, "foo:bar", "foo:bar", "local colon skill")
    _write_skill(skills, "other", "other", "listed skill")
    loaded = br.load_active_skills(visible_names=frozenset({"other"}))
    names = {s["name"] for s in loaded}
    assert names == {"other"}


# ─── FIX 3: directory fallback honors qualified disabled names ───────────────


def test_directory_fallback_excludes_qualified_disabled_name(monkeypatch, tmp_path):
    importlib.reload(br)
    plugins_root = tmp_path / "plugins"
    _write_skill(plugins_root / "foo" / "skills", "hidden", "hidden", "disabled qualified")
    _write_skill(plugins_root / "foo" / "skills", "shown", "shown", "kept plugin skill")
    _install_discovery(
        monkeypatch,
        skills_dirs=[],
        disabled={"foo:hidden"},
        plugins_root=plugins_root,
    )
    loaded = br.load_active_skills()
    names = {s["name"] for s in loaded}
    assert "foo:shown" in names
    assert "foo:hidden" not in names


# ─── FIX 4: category descriptions are current-format ─────────────────────────


def test_category_description_compacts_descriptionless_skill():
    mod = _load_plugin()
    prompt = (
        "<available_skills>\n"
        "  tools: A category description\n"
        "    - demo\n"
        "</available_skills>"
    )
    req = {"messages": [{"role": "system", "content": prompt}]}
    result = mod._on_llm_request(request=req, session_id="cat-desc")
    assert result is not None and "request" in result
    text = result["request"]["messages"][0]["content"]
    assert "A category description" not in text
    assert "- demo" in text
    assert mod._COMPACT_SENTINEL in text

    legacy = (
        "<available_skills>\n"
        "    - demo\n"
        "    - vendor:demo\n"
        "</available_skills>"
    )
    legacy_req = {"messages": [{"role": "system", "content": legacy}]}
    assert mod._on_llm_request(request=legacy_req, session_id="legacy-still") is None
    assert legacy_req["messages"][0]["content"] == legacy


def test_legacy_demoted_category_is_byte_stable():
    mod = _load_plugin("skill_retrieval_round5_legacy")
    block = (
        "<available_skills>\n"
        "  creative:\n"
        "    - ascii-art\n"
        "  devops [names only]: docker, k8s\n"
        "</available_skills>"
    )
    assert mod._is_legacy_names_only(block) is True
    req = {"messages": [{"role": "system", "content": block}]}
    assert mod._on_llm_request(request=req, session_id="legacy-demoted") is None
    assert req["messages"][0]["content"] == block


# ─── FIX 5: per-home cap keys are LRU ────────────────────────────────────────


def test_cap_key_hit_refreshes_lru_order(monkeypatch, tmp_path):
    importlib.reload(br)
    br.clear_index_cache()
    monkeypatch.setattr(br, "_MAX_CACHED_CAP_KEYS_PER_HOME", 2)
    monkeypatch.setattr(br, "_runtime_paths_are_overridden", lambda: False)
    monkeypatch.setattr(br, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(br, "_corpus_manifest", lambda: ("stable",))
    monkeypatch.setattr(br, "_session_platform_key_parts", lambda: (None, None))
    monkeypatch.setattr(
        br,
        "load_active_skills",
        lambda *_a, **_k: [{
            "skill_id": "s",
            "name": "s",
            "description": "alpha widgets",
            "text": "s: alpha widgets",
        }],
    )
    idx_a = br.get_index(visible_names=frozenset({"a"}))
    idx_b = br.get_index(visible_names=frozenset({"b"}))
    assert br.get_index(visible_names=frozenset({"a"})) is idx_a
    idx_c = br.get_index(visible_names=frozenset({"c"}))
    assert idx_c is not None
    assert br.get_index(visible_names=frozenset({"a"})) is idx_a
    rebuilt_b = br.get_index(visible_names=frozenset({"b"}))
    assert rebuilt_b is not idx_b
    assert rebuilt_b is not None
    br.clear_index_cache()
