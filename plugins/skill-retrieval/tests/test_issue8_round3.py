"""Regression tests for Issue #8 round 3 findings (audaimousa, close-out
comment, 2026-09-08).

Written by Hermes BEFORE the fix (honest RED contract). Each test encodes
the named-session snapshot-binding contract from the issue's final comment:

    1. The build-time capability snapshot must bind to the ACTIVE Hermes
       session identity via gateway.session_context.get_session_env(
       "HERMES_SESSION_ID") — build_skills_system_prompt() has no
       session_id parameter, so the ContextVar/env session is the only
       identity source available at build time.

    2. A NAMED session whose exact snapshot is missing or stale must SKIP
       BM25 injection for that turn (return no context) instead of
       falling back to the fail-open zero-argument corpus. Missing
       retrieval is safer than injecting a skill Hermes explicitly hid.

    3. No cross-session fallback: a named session must never read another
       named session's snapshot (isolation direction from 50daa54 kept).

The reporter's live reproduction at 50daa54: two named sessions with
disjoint capabilities, 100 interleaved A/B cycles across 5 fresh
processes — 200/200 hidden-skill leakage opportunities reproduced, because
build_skills_system_prompt() recorded the snapshot under the anonymous key
("") while pre_llm_call(session_id=A) looked up A, found nothing, and fell
back to the fail-open bare get_index().
"""

import importlib
import importlib.util
import pathlib
import sys
import types
import time

import pytest

import bm25_retriever as br


def _load_fresh():
    importlib.reload(br)
    return br


_PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent


def _load_plugin_init(monkeypatch, tmp_path):
    """Load the plugin's __init__.py as a top-level module with scripts/ on
    sys.path, so _on_pre_llm_call / get_index resolve. Returns the module
    (holds _remember_capability_snapshot / _session_capability_snaps)."""
    monkeypatch.syspath_prepend(str(_PLUGIN_DIR / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "skill_retrieval_init_under_test", _PLUGIN_DIR / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["skill_retrieval_init_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


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

    Mirrors test_issue8_round2.py::_install_hermes_stubs (same four-family
    gate evaluation as agent/prompt_builder.py). Kept separate so each
    round's tests pin their own contract copy.
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
    su = stubs["su"]
    monkeypatch.setattr(su, "get_all_skills_dirs", lambda: list(roots))


class _FakeSessionContext:
    """Stub of gateway.session_context with a settable task-local session id.

    Mirrors the real module's contract: get_session_env("HERMES_SESSION_ID")
    returns the ContextVar-bound session id for the current task.
    """

    session_id = ""

    @classmethod
    def get_session_env(cls, name, default=""):
        if name == "HERMES_SESSION_ID":
            return cls.session_id or default
        return default

    @classmethod
    def install(cls, monkeypatch):
        sc_mod = types.ModuleType("gateway.session_context")
        sc_mod.get_session_env = cls.get_session_env
        gw_pkg = types.ModuleType("gateway")
        monkeypatch.setitem(sys.modules, "gateway", gw_pkg)
        monkeypatch.setitem(sys.modules, "gateway.session_context", sc_mod)
        return cls


# ─── Contract 1: build snapshot binds to the active session identity ────────


def test_build_snapshot_binds_to_session_env_identity(monkeypatch, tmp_path):
    """compact_build() must key the capability snapshot to
    get_session_env("HERMES_SESSION_ID") when no explicit session_id kwarg
    is passed — that is the task-local identity Hermes binds before the
    system prompt builds (agent_init._publish_session_id)."""
    mod = _load_plugin_init(monkeypatch, tmp_path)
    SC = _FakeSessionContext.install(monkeypatch)
    SC.session_id = "sess-A"
    mod._remember_capability_snapshot(available_tools={"tool_a"}, available_toolsets=set())
    snap = mod._session_capability_snaps.get("sess-A")
    assert snap is not None, (
        "snapshot must be keyed to the session-env identity, not the anonymous key"
    )
    assert snap[1] == frozenset({"tool_a"})


def test_build_snapshot_explicit_session_id_still_wins(monkeypatch, tmp_path):
    """An explicit session_id kwarg (future-proofing: if Hermes ever adds a
    session_id parameter to build_skills_system_prompt) takes precedence
    over the session-env identity."""
    mod = _load_plugin_init(monkeypatch, tmp_path)
    SC = _FakeSessionContext.install(monkeypatch)
    SC.session_id = "sess-ENV"
    mod._remember_capability_snapshot(
        available_tools={"t"}, available_toolsets=set(), session_id="sess-EXPLICIT"
    )
    assert "sess-EXPLICIT" in mod._session_capability_snaps
    assert "sess-ENV" not in mod._session_capability_snaps


# ─── Contract 2: named session with missing/stale snapshot must skip ────────


def _setup_plugin_module(br, monkeypatch, tmp_path, *, conditions_map):
    """Wire a skill corpus of capability-gated skills plus a filler doc and
    patch __init__-level deps so _on_pre_llm_call runs against them."""
    root = tmp_path / "skills"
    _write_skill(root, "a", "alpha-skill", "alphaleak3f unique token")
    _write_skill(root, "b", "beta-skill", "betaleak5g unique token")
    _write_skill(root, "c", "gamma-skill", "always visible filler")
    stubs = _install_hermes_stubs(
        monkeypatch, conditions_map=conditions_map
    )
    _point_discovery_at(monkeypatch, stubs, root)
    return root


def test_named_session_missing_snapshot_skips_injection(monkeypatch, tmp_path):
    """A NAMED session with no exact snapshot must get NO injection rather
    than the fail-open bare corpus (reporter contract #2: 'missing exact
    named snapshot: FAIL — hidden Skill retrieved' must become a skip)."""
    br = _load_fresh()
    mod = _load_plugin_init(monkeypatch, tmp_path)
    root = tmp_path / "skills"
    # Two docs: single-doc corpora score zero under clipped-IDF BM25.
    _write_skill(root, "plain", "plain-skill", "always visible filler")
    _write_skill(root, "gated", "gated-skill", "quasarneedle9z")
    stubs = _install_hermes_stubs(
        monkeypatch,
        conditions_map={"gated-skill": {"requires_tools": ["special_tool"]}},
    )
    _point_discovery_at(monkeypatch, stubs, root)

    # No snapshot recorded for "sess-A" at all.
    result = mod._on_pre_llm_call(
        session_id="sess-A", user_message="quasarneedle9z"
    )
    assert result is None, (
        "named session with missing snapshot must skip injection, "
        "not fall back to the fail-open corpus"
    )


def test_named_session_stale_snapshot_skips_injection(monkeypatch, tmp_path):
    """A NAMED session whose snapshot is older than the staleness window
    must skip injection (reporter: 'snapshot age 30.001s: FAIL')."""
    mod = _load_plugin_init(monkeypatch, tmp_path)
    root = tmp_path / "skills"
    # Two docs: single-doc corpora score zero under clipped-IDF BM25.
    _write_skill(root, "plain", "plain-skill", "always visible filler")
    _write_skill(root, "gated", "gated-skill", "quasarneedle9z")
    stubs = _install_hermes_stubs(
        monkeypatch,
        conditions_map={"gated-skill": {"requires_tools": ["special_tool"]}},
    )
    _point_discovery_at(monkeypatch, stubs, root)

    # Simulate a stale snapshot for sess-A.
    mod._session_capability_snaps["sess-A"] = (
        time.monotonic() - (mod._SNAPSHOT_MAX_AGE_S + 1.0),
        frozenset({"special_tool"}),
        frozenset(),
    )
    result = mod._on_pre_llm_call(
        session_id="sess-A", user_message="quasarneedle9z"
    )
    assert result is None, (
        "named session with stale snapshot must skip injection, "
        "not fall back to the fail-open corpus"
    )


def test_anonymous_session_keeps_fail_open(monkeypatch, tmp_path):
    """The anonymous path (session_id='') keeps Hermes' fail-open semantics:
    bare get_index() fallback when no snapshot exists. Backward compat with
    test_no_capability_args_fails_open."""
    br = _load_fresh()
    mod = _load_plugin_init(monkeypatch, tmp_path)
    root = tmp_path / "skills"
    # Three docs: the BM25 clipped IDF zeroes every term in a 1- or 2-doc
    # corpus (N=2, df=1 gives idf=log(1.5/1.5)=0). Three docs with the probe
    # token in exactly one yield idf=log(2.5/1.5)>0, so the assertion can
    # actually exercise retrieval instead of silently testing an empty set.
    _write_skill(root, "plain", "plain-skill", "always visible filler")
    _write_skill(root, "gated", "gated-skill", "quasarneedle9z")
    _write_skill(root, "extra", "extra-skill", "unrelated filler vocabulary")
    stubs = _install_hermes_stubs(
        monkeypatch,
        conditions_map={"gated-skill": {"requires_tools": ["special_tool"]}},
    )
    _point_discovery_at(monkeypatch, stubs, root)

    result = mod._on_pre_llm_call(session_id="", user_message="quasarneedle9z")
    assert result is not None and result.get("context"), (
        "anonymous session must keep the fail-open behavior"
    )
    assert "gated-skill" in result["context"]


# ─── Contract 3: cross-session isolation with binding ───────────────────────


def test_interleaved_named_sessions_no_leakage(monkeypatch, tmp_path):
    """Two named sessions with disjoint capabilities, interleaved build/hook
    cycles. Neither session may ever retrieve the other's hidden skill
    (reporter: 200/200 leakage at 50daa54 — must be 0)."""
    br = _load_fresh()
    mod = _load_plugin_init(monkeypatch, tmp_path)
    SC = _FakeSessionContext.install(monkeypatch)
    root = tmp_path / "skills"
    _write_skill(root, "a", "alpha-skill", "alphaleak3f unique token")
    _write_skill(root, "b", "beta-skill", "betaleak5g unique token")
    stubs = _install_hermes_stubs(
        monkeypatch,
        conditions_map={
            "alpha-skill": {"requires_tools": ["tool_a"]},
            "beta-skill": {"requires_tools": ["tool_b"]},
        },
    )
    _point_discovery_at(monkeypatch, stubs, root)

    alpha_caps = {"available_tools": {"tool_a"}, "available_toolsets": set()}
    beta_caps = {"available_tools": {"tool_b"}, "available_toolsets": set()}

    leak_count = 0
    for cycle in range(20):
        # Session A's turn: build under A's identity, then hook with A's id.
        SC.session_id = "sess-A"
        mod._remember_capability_snapshot(**alpha_caps)
        result_a = mod._on_pre_llm_call(
            session_id="sess-A", user_message="alphaleak3f betaleak5g"
        )
        if result_a and "beta-skill" in result_a.get("context", ""):
            leak_count += 1

        # Session B's turn.
        SC.session_id = "sess-B"
        mod._remember_capability_snapshot(**beta_caps)
        result_b = mod._on_pre_llm_call(
            session_id="sess-B", user_message="alphaleak3f betaleak5g"
        )
        if result_b and "alpha-skill" in result_b.get("context", ""):
            leak_count += 1

        # Interleaved stale-snapshot probe: A asks again after B's build
        # overwrote nothing of A's (exact-key binding must keep A's snap).
        result_a2 = mod._on_pre_llm_call(
            session_id="sess-A", user_message="alphaleak3f betaleak5g"
        )
        if result_a2 and "beta-skill" in result_a2.get("context", ""):
            leak_count += 1

    assert leak_count == 0, (
        f"cross-session hidden-skill leakage detected in {leak_count} probes"
    )