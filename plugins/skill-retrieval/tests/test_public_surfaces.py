"""Public-surface contract extras: llm_request rewrite shapes and lifecycle."""
import types

import bm25_retriever as br


def _load_plugin():
    import importlib.util
    from pathlib import Path

    plugin_dir = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "skill_retrieval_public_surfaces", plugin_dir / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _skills_prompt(extra=""):
    return (
        "preamble\n"
        "<available_skills>\n"
        "  tools:\n"
        "    - demo: Performs several operations.\n"
        "    - other: Another tool.\n"
        "</available_skills>\n"
        + extra
    )


def test_llm_request_chat_completions_rewrites_system_message():
    mod = _load_plugin()
    prompt = _skills_prompt()
    tools = [{"name": "skill_view"}]
    req = {
        "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": "hi"}],
        "tools": tools,
    }
    result = mod._on_llm_request(request=req, session_id="s1", platform="cli")
    assert result is not None
    new = result["request"]
    text = new["messages"][0]["content"]
    assert mod._COMPACT_SENTINEL in text
    assert "- demo" in text
    assert "Performs several operations" not in text
    assert new["tools"] is tools
    assert req["messages"][0]["content"] == prompt  # original not mutated
    snap = mod._session_capability_snaps["s1"]
    assert snap[1] == frozenset({"demo", "other"})
    assert mod._session_platforms["s1"] == "cli"


def test_llm_request_codex_rewrites_instructions_and_system_message():
    mod = _load_plugin()
    prompt = _skills_prompt()
    req = {
        "instructions": prompt,
        "messages": [{"role": "system", "content": prompt}],
    }
    result = mod._on_llm_request(request=req, session_id="")
    assert result is not None
    assert mod._COMPACT_SENTINEL in result["request"]["instructions"]
    assert mod._COMPACT_SENTINEL in result["request"]["messages"][0]["content"]


def test_llm_request_anthropic_preserves_cache_control_identity():
    mod = _load_plugin()
    prompt = _skills_prompt()
    cache_control = {"type": "ephemeral"}
    block = {"type": "text", "text": prompt, "cache_control": cache_control}
    req = {"system": [block], "messages": [{"role": "user", "content": "hi"}]}
    result = mod._on_llm_request(request=req, session_id="anth")
    assert result is not None
    new_block = result["request"]["system"][0]
    assert new_block["cache_control"] is cache_control
    assert mod._COMPACT_SENTINEL in new_block["text"]
    assert block["text"] == prompt


def test_llm_request_missing_block_returns_none():
    mod = _load_plugin()
    assert mod._on_llm_request(
        request={"messages": [{"role": "system", "content": "no skills here"}]},
        session_id="",
    ) is None


def test_llm_request_does_not_touch_tools():
    mod = _load_plugin()
    tools = [{"name": "terminal", "desc": "run"}]
    req = {
        "messages": [{"role": "system", "content": _skills_prompt()}],
        "tools": tools,
    }
    result = mod._on_llm_request(request=req, session_id="")
    assert result["request"]["tools"] is tools


def test_register_installs_three_surfaces():
    mod = _load_plugin()
    seen = {"hooks": [], "mw": []}

    class Ctx:
        def register_hook(self, name, func):
            seen["hooks"].append(name)

        def register_middleware(self, name, func):
            seen["mw"].append(name)

    mod.register(Ctx())
    assert "pre_llm_call" in seen["hooks"]
    assert "on_skill_lifecycle" in seen["hooks"]
    assert seen["mw"] == ["llm_request"]


def test_lifecycle_unknown_action_invalidates(monkeypatch):
    mod = _load_plugin()
    called = []
    monkeypatch.setattr(mod, "clear_index_cache", lambda: called.append(1))
    mod._on_skill_lifecycle(action="brand-new-action", skill_name="x")
    assert called == [1]
    mod._on_skill_lifecycle(action="loaded", skill_name="x")
    assert called == [1]


def test_get_index_visible_names_filters_corpus(monkeypatch, tmp_path):
    br._indexes_by_home.clear()
    br._skills_by_home_and_id.clear()
    br._manifest_by_key.clear()
    root = tmp_path / "skills"
    for rel, name, desc in (
        ("a", "alpha", "alpha token zebra"),
        ("b", "beta", "beta token yak"),
        ("c", "gamma", "gamma filler words"),
    ):
        d = root / rel
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f'---\nname: {name}\ndescription: "{desc}"\n---\n\n# {name}\n'
        )
    pb = types.ModuleType("agent.prompt_builder")
    pb._current_session_platform_hint = lambda: ""
    pb.extract_skill_conditions = lambda fm: {}
    pb._skill_should_show = lambda *a, **k: True
    pb._parse_skill_file = lambda f: (True, {"name": br._parse_skill_md(f)[0]}, br._parse_skill_md(f)[1])
    pb._build_snapshot_entry = lambda f, r, fm, desc: {
        "category": "general",
        "skill_name": f.parent.name,
        "frontmatter_name": fm["name"],
        "description": desc,
    }
    su = types.ModuleType("agent.skill_utils")
    su.get_disabled_skill_names = lambda platform=None: set()
    su.get_project_skills_dirs = lambda: []
    su.get_all_skills_dirs = lambda: [root]
    su.iter_project_skill_files = lambda r: sorted(r.rglob("SKILL.md"))
    su.iter_skill_index_files = lambda r, filename: sorted(r.rglob(filename))
    monkeypatch.setitem(__import__("sys").modules, "agent", types.ModuleType("agent"))
    monkeypatch.setitem(__import__("sys").modules, "agent.prompt_builder", pb)
    monkeypatch.setitem(__import__("sys").modules, "agent.skill_utils", su)

    idx = br.get_index(visible_names=frozenset({"alpha", "gamma"}))
    ids = [i for i, _ in idx.retrieve("alpha token beta token")]
    assert "a" in ids
    assert "b" not in ids
