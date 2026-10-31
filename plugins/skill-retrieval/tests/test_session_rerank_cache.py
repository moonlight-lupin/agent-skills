"""Session-scoped Jev rerank cache tests.

The cache is an opt-in optimization for phase-continuous conversations. It
must reduce redundant external reranks without leaking state across sessions
or changing the fail-soft BM25 fallback behavior.
"""

import importlib.util
import os
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parent.parent


def _fresh_plugin(**env_vars):
    old = {key: os.environ.get(key) for key in env_vars}
    try:
        for key, value in env_vars.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        spec = importlib.util.spec_from_file_location(
            "skill_retrieval_session_cache_test", PLUGIN_DIR / "__init__.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class _SequenceIndex:
    def __init__(self, candidate_orders):
        self._orders = list(candidate_orders)
        self._calls = 0

    def retrieve(self, query, top_k=6):
        pos = min(self._calls, len(self._orders) - 1)
        self._calls += 1
        return [
            (skill_id, 1.0 - rank * 0.01)
            for rank, skill_id in enumerate(self._orders[pos][:top_k])
        ]


def _configure(mod, candidate_orders, rerank_orders):
    index = _SequenceIndex(candidate_orders)
    calls = []

    mod.RERANK_MODE = "jev"
    mod.get_index = lambda **_kwargs: index
    mod.get_skill_info = lambda skill_id, **_kwargs: {
        "name": skill_id,
        "description": f"{skill_id} description",
    }

    def fake_rerank(query, shortlist):
        calls.append((query, [row[0] for row in shortlist]))
        result = rerank_orders[min(len(calls) - 1, len(rerank_orders) - 1)]
        if isinstance(result, dict):
            return result
        return {
            "order": result,
            "skipped": False,
            "input_tokens": 20,
            "latency_ms": 1,
        }

    mod._jev_rerank = fake_rerank
    return calls


def _new_enabled_plugin():
    return _fresh_plugin(
        SKILL_RETRIEVAL_TOP_K="4",
        SKILL_RETRIEVAL_INJECT_K="2",
        SKILL_RETRIEVAL_RERANK="jev",
        SKILL_RETRIEVAL_RERANK_SESSION_CACHE="1",
    )


def _prime_snapshot(mod, session_id):
    mod._remember_capability_snapshot(
        session_id,
        frozenset({"a", "b", "c", "d", "e", "f"}),
    )


def test_cache_is_opt_in_and_defaults_off():
    mod = _fresh_plugin(SKILL_RETRIEVAL_RERANK_SESSION_CACHE=None)
    assert mod.RERANK_SESSION_CACHE is False


def test_first_rerank_freezes_workset_then_local_bm25_reuses_it():
    mod = _new_enabled_plugin()
    calls = _configure(
        mod,
        candidate_orders=[["a", "b", "c", "d"], ["a", "c", "e", "f"]],
        rerank_orders=[["b", "a", "c", "d"]],
    )
    _prime_snapshot(mod, "session-a")

    mod._on_pre_llm_call("session-a", "first turn")
    second = mod._on_pre_llm_call("session-a", "same scene")

    assert len(calls) == 1
    assert "**a**" in second["context"]
    assert "**c**" in second["context"]
    assert "jev rerank" not in second["context"]


def test_outside_candidate_triggers_rerank_and_selected_fallback_is_reused():
    mod = _new_enabled_plugin()
    calls = _configure(
        mod,
        candidate_orders=[
            ["a", "b", "c", "d"],
            ["e", "a", "c", "d"],
            ["e", "a", "f", "d"],
        ],
        rerank_orders=[
            ["b", "a", "c", "d"],
            ["e", "a", "c", "d"],
        ],
    )
    _prime_snapshot(mod, "session-a")

    mod._on_pre_llm_call("session-a", "first turn")
    mod._on_pre_llm_call("session-a", "new subtask")
    third = mod._on_pre_llm_call("session-a", "same subtask")

    assert len(calls) == 2
    assert "**e**" in third["context"]
    workset, fallbacks = mod._session_rerank_states["session-a"]
    assert "e" not in workset
    assert "e" in fallbacks


def test_failed_rerank_does_not_confirm_outside_candidate():
    mod = _new_enabled_plugin()
    calls = _configure(
        mod,
        candidate_orders=[
            ["a", "b", "c", "d"],
            ["e", "a", "c", "d"],
            ["e", "a", "c", "d"],
        ],
        rerank_orders=[
            ["b", "a", "c", "d"],
            {"skipped": True, "fallback_reason": "timeout"},
            {"skipped": True, "fallback_reason": "timeout"},
        ],
    )
    _prime_snapshot(mod, "session-a")

    mod._on_pre_llm_call("session-a", "first turn")
    mod._on_pre_llm_call("session-a", "new subtask")
    mod._on_pre_llm_call("session-a", "retry subtask")

    assert len(calls) == 3
    assert "e" not in mod._session_rerank_states["session-a"][1]


def test_named_sessions_are_isolated_and_anonymous_requests_never_reuse():
    mod = _new_enabled_plugin()
    calls = _configure(
        mod,
        candidate_orders=[["a", "b", "c", "d"]] * 4,
        rerank_orders=[["b", "a", "c", "d"]] * 4,
    )
    _prime_snapshot(mod, "session-a")
    _prime_snapshot(mod, "session-b")

    mod._on_pre_llm_call("session-a", "one")
    mod._on_pre_llm_call("session-a", "two")
    mod._on_pre_llm_call("session-b", "one")
    mod._on_pre_llm_call("", "anonymous one", is_first_turn=True)
    mod._on_pre_llm_call("", "anonymous two", is_first_turn=True)

    assert len(calls) == 4
    assert "session-a" in mod._session_rerank_states
    assert "session-b" in mod._session_rerank_states
    assert "" not in mod._session_rerank_states


def test_skill_mutation_clears_cache_but_load_does_not():
    mod = _new_enabled_plugin()
    mod.clear_index_cache = lambda: None
    mod._remember_session_rerank("session-a", ["a", "b"], ["a"])

    mod._on_skill_lifecycle("loaded")
    assert "session-a" in mod._session_rerank_states

    mod._on_skill_lifecycle("installed")
    assert not mod._session_rerank_states


def test_session_state_is_lru_bounded():
    mod = _new_enabled_plugin()
    mod._MAX_RERANK_SESSION_STATES = 2

    for session_id in ("one", "two", "three"):
        mod._remember_session_rerank(session_id, ["a", "b"], ["a"])

    assert list(mod._session_rerank_states) == ["two", "three"]
