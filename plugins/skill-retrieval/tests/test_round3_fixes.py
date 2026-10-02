"""Round-3 review fixes. Each test calls the plugin the way a turn does."""

import ast
import importlib
import importlib.util
import logging
import sys
import types
from pathlib import Path

import bm25_retriever as br

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_FORBIDDEN_ROOTS = {"agent", "prompt_builder", "run_agent"}


def _load_plugin(name="skill_retrieval_round3"):
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
    br._index = None
    br._skills_by_id = {}
    br.clear_index_cache()
    monkeypatch.setattr(br, "SKILLS_ROOT", skills)
    monkeypatch.setattr(br, "PLUGINS_ROOT", plugins)
    monkeypatch.setattr(br, "CONFIG_PATH", cfg)
    return skills


# ─── BLOCKING 1: developer role ──────────────────────────────────────────────


def test_developer_role_request_is_rewritten():
    mod = _load_plugin()
    prompt = (
        "<available_skills>\n"
        "  tools:\n"
        "    - demo: Performs several operations.\n"
        "</available_skills>"
    )
    req = {
        "messages": [
            {"role": "developer", "content": prompt},
            {"role": "user", "content": "hi"},
        ]
    }
    result = mod._on_llm_request(request=req, session_id="dev1")
    assert result is not None and "request" in result
    text = result["request"]["messages"][0]["content"]
    assert result["request"]["messages"][0]["role"] == "developer"
    assert "Performs several operations" not in text
    assert "- demo" in text
    assert mod._session_capability_snaps["dev1"][1] == frozenset({"demo"})
    assert req["messages"][0]["content"] == prompt


# ─── MAJOR 2: qualified names and org category labels ────────────────────────


def test_qualified_name_and_org_category_stay_intact():
    mod = _load_plugin()
    inner = (
        "  org:acme: Shared org skills\n"
        "    - vendor:demo: Useful work: keep the tail\n"
    )
    compact = mod.compact_available_skills_block(inner, True)
    lines = compact.split("\n")
    assert "    - vendor:demo" in lines
    assert "  org:acme:" in lines
    assert "  org:" not in lines
    assert "Useful work" not in compact
    assert mod._extract_visible_skill_names(inner) == frozenset({"vendor:demo"})


def test_colon_and_slash_suffixes_do_not_admit_local_skills():
    qualified = {
        "leaf_name": "vendor:demo",
        "name": "vendor:demo",
        "frontmatter_name": "vendor:demo",
        "skill_id": "tools/vendor:demo",
    }
    assert br._skill_doc_is_visible(qualified, frozenset({"demo"})) is False
    assert br._skill_doc_is_visible(qualified, frozenset({"vendor:demo"})) is True
    slashed = {
        "leaf_name": "other",
        "name": "other",
        "frontmatter_name": "other",
        "skill_id": "tools/demo",
    }
    assert br._skill_doc_is_visible(slashed, frozenset({"demo"})) is False
    assert br._skill_doc_is_visible(slashed, frozenset({"other"})) is True


# ─── MAJOR 3: first turn without a snapshot fail-opens ───────────────────────


def test_first_turn_without_snapshot_retrieves_later_turn_skips(monkeypatch, tmp_path):
    mod = _load_plugin("skill_retrieval_round3_first")
    skills = _point_legacy(monkeypatch, tmp_path)
    _write_skill(skills, "demo", "demo", "quasarneedle9z retrieval target")
    mod._session_capability_snaps.clear()

    first = mod._on_pre_llm_call("sess-fresh", "quasarneedle9z", is_first_turn=True)
    assert first is not None
    assert "demo" in first["context"]
    assert "quasarneedle9z" in first["context"]

    later = mod._on_pre_llm_call("sess-later", "quasarneedle9z", is_first_turn=False)
    assert later is None


# ─── MAJOR 4: plugin skills survive a snapshot that omits them ───────────────


def test_plugin_skill_retrieved_when_snapshot_omits_it(monkeypatch, tmp_path):
    importlib.reload(br)
    root = tmp_path / "skills"
    _write_skill(root, "plain", "plain-skill", "always listed")
    _write_skill(root, "hidden", "hidden-skill", "not in the snapshot")

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

    disabled = {"foo:hidden"}
    su = types.ModuleType("agent.skill_utils")
    su.get_disabled_skill_names = lambda platform=None: set(disabled)
    su.get_project_skills_dirs = lambda: []
    su.get_all_skills_dirs = lambda: [root]
    su.iter_project_skill_files = lambda r: sorted(Path(r).rglob("SKILL.md"))
    su.iter_skill_index_files = lambda r, filename: sorted(Path(r).rglob(filename))
    su.skill_matches_platform = lambda fm: True
    agent_pkg = types.ModuleType("agent")
    agent_pkg.prompt_builder = pb
    agent_pkg.skill_utils = su
    monkeypatch.setitem(sys.modules, "agent", agent_pkg)
    monkeypatch.setitem(sys.modules, "agent.prompt_builder", pb)
    monkeypatch.setitem(sys.modules, "agent.skill_utils", su)

    class FakePM:
        def list_plugin_skill_metadata(self):
            return [
                {
                    "name": "foo:bar",
                    "description": "plugin work that is not in the prompt",
                    "frontmatter": {"name": "bar"},
                },
                {
                    "name": "foo:hidden",
                    "description": "disabled plugin skill",
                    "frontmatter": {"name": "hidden"},
                },
            ]

    plugins = types.ModuleType("hermes_cli.plugins")
    plugins.discover_plugins = lambda: None
    plugins.get_plugin_manager = lambda: FakePM()
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins)
    monkeypatch.setattr(br, "SKILLS_ROOT", None)
    monkeypatch.setattr(br, "CONFIG_PATH", None)

    skills = br.load_active_skills(visible_names=frozenset({"plain-skill"}))
    names = {s["name"] for s in skills}
    assert "foo:bar" in names
    assert "plain-skill" in names
    assert "hidden-skill" not in names
    assert "foo:hidden" not in names


# ─── MAJOR 5: manifest ignores cache/support churn, sees new skills ─────────


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
    monkeypatch.setattr(br, "get_hermes_home", lambda: tmp_path / "home")
    monkeypatch.setattr(br, "_runtime_paths_are_overridden", lambda: False)
    monkeypatch.setattr(br, "_session_platform_key_parts", lambda: (None, None))


def test_pycache_churn_does_not_invalidate_new_skill_does(monkeypatch, tmp_path):
    importlib.reload(br)
    br.clear_index_cache()
    root = tmp_path / "skills"
    _write_skill(root, "demo", "demo", "alpha widgets")
    _stub_manifest_roots(monkeypatch, root, tmp_path)
    calls = {"n": 0}

    def counting(*_a, **_k):
        calls["n"] += 1
        return [{
            "skill_id": "demo",
            "name": "demo",
            "description": "alpha widgets",
            "text": "demo: alpha widgets",
        }]

    monkeypatch.setattr(br, "load_active_skills", counting)
    assert br.get_index() is not None
    assert calls["n"] == 1
    before = br._corpus_manifest()

    pyc = root / "demo" / "__pycache__"
    pyc.mkdir()
    (pyc / "mod.pyc").write_bytes(b"\x00\x01changed")
    scripts = root / "demo" / "scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text("print(1)\n")
    assert br._corpus_manifest() == before
    assert br.get_index() is not None
    assert calls["n"] == 1

    _write_skill(root, "other", "other", "beta widgets")
    assert br._corpus_manifest() != before
    assert br.get_index() is not None
    assert calls["n"] == 2
    br.clear_index_cache()


def test_manifest_walk_stops_on_symlink_cycle(monkeypatch, tmp_path):
    importlib.reload(br)
    root = tmp_path / "skills"
    root.mkdir()
    _write_skill(root, "nested", "nested", "inside")
    (root / "loop").symlink_to(root, target_is_directory=True)
    _stub_manifest_roots(monkeypatch, root, tmp_path)
    manifest = br._corpus_manifest()
    assert manifest is not None
    assert any(str(path).endswith("SKILL.md") for path, _sig in manifest)


# ─── MAJOR 6: legacy names-only blocks keep their bytes ─────────────────────


def test_legacy_names_only_block_is_not_rewritten_and_names_are_captured():
    mod = _load_plugin("skill_retrieval_round3_legacy")
    legacy = (
        "<available_skills>\n"
        "  tools:\n"
        "    - demo\n"
        "    - vendor:demo\n"
        "</available_skills>"
    )
    req = {"messages": [{"role": "system", "content": legacy}]}
    result = mod._on_llm_request(request=req, session_id="old-sess")
    assert result is None
    assert req["messages"][0]["content"] == legacy
    assert mod._session_capability_snaps["old-sess"][1] == frozenset({"demo", "vendor:demo"})


# ─── minors ──────────────────────────────────────────────────────────────────


def test_llm_request_rewrite_failure_warns_once(monkeypatch, caplog):
    mod = _load_plugin("skill_retrieval_round3_warn")
    mod._llm_request_warned = False

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(mod, "_rewrite_request", boom)
    with caplog.at_level(logging.DEBUG):
        assert mod._on_llm_request(request={"messages": []}, session_id="a") is None
        assert mod._on_llm_request(request={"messages": []}, session_id="b") is None
    warnings = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "rewrite failed" in r.getMessage()
    ]
    assert len(warnings) == 1
    assert not any(r.levelno >= logging.ERROR for r in caplog.records)


def test_fallback_reloads_when_cached_module_file_differs(monkeypatch):
    foreign = types.ModuleType("bm25_retriever")
    foreign.__file__ = "/tmp/other-bm25_retriever.py"
    foreign.get_index = lambda *_a, **_k: "foreign"
    foreign.clear_index_cache = lambda: None
    foreign.get_skill_info = lambda *_a, **_k: None
    monkeypatch.setitem(sys.modules, "bm25_retriever", foreign)
    mod = _load_plugin("skill_retrieval_round3_fallback")
    assert mod.get_index is not foreign.get_index
    assert mod.get_index() != "foreign"
    loaded = Path(mod.get_index.__code__.co_filename).resolve()
    assert loaded == (_PLUGIN_DIR / "scripts" / "bm25_retriever.py").resolve()


def test_index_cache_evicts_oldest_homes(monkeypatch, tmp_path):
    importlib.reload(br)
    br.clear_index_cache()
    current = {"home": tmp_path / "h0"}
    monkeypatch.setattr(br, "_runtime_paths_are_overridden", lambda: False)
    monkeypatch.setattr(br, "get_hermes_home", lambda: current["home"])
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
    first = None
    for i in range(br._MAX_CACHED_HOMES + 1):
        home = tmp_path / f"h{i}"
        home.mkdir()
        current["home"] = home
        assert br.get_index() is not None
        if i == 0:
            first = str(home.expanduser().resolve(strict=False))
    assert first not in br._cap_key_order_by_home
    assert len(br._home_order) == br._MAX_CACHED_HOMES
    newest = str((tmp_path / f"h{br._MAX_CACHED_HOMES}").resolve())
    assert newest in br._cap_key_order_by_home
    br.clear_index_cache()


def test_conftest_disabled_skills_patch_does_not_hide_a_missing_attribute():
    text = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")
    assert "raising=True" in text
    assert "raising=False" not in text


def test_plugin_yaml_describes_request_rewrite():
    text = (_PLUGIN_DIR / "plugin.yaml").read_text(encoding="utf-8")
    assert (
        "Rewrites the outgoing request's skills index to names-only "
        "and injects retrieved skills per turn."
    ) in text
    assert "replacing the full skill list" not in text


def _assignment_roots(tree):
    roots = []

    def walk_target(node):
        if isinstance(node, (ast.Tuple, ast.List)):
            for elt in node.elts:
                walk_target(elt)
            return
        if isinstance(node, ast.Starred):
            walk_target(node.value)
            return
        if not isinstance(node, ast.Attribute):
            return
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Subscript):
            root = root.value
        if isinstance(root, ast.Name) and root.id in _FORBIDDEN_ROOTS:
            roots.append(root.id)

    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign) and node.target is not None:
            targets = [node.target]
        elif isinstance(node, ast.AugAssign):
            targets = [node.target]
        for target in targets:
            walk_target(target)
    return roots


def test_no_assignment_targets_core_modules():
    paths = [_PLUGIN_DIR / "__init__.py"]
    paths += sorted((_PLUGIN_DIR / "scripts").glob("*.py"))
    offenders = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for root in _assignment_roots(tree):
            offenders.append(f"{path.name}: {root}")
    assert offenders == []
