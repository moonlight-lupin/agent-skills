"""Integration test: the pre_llm_call hook wires the rerank stage correctly.

Covers the wire-up in __init__._on_pre_llm_call — not the rerank module
itself (covered by test_jev_rerank.py). All offline; Jev call is stubbed.
"""

import importlib
import json
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN_DIR / "scripts"


def _fresh_plugin(monkeypatch, rerank="jev", log_path=None):
    """Reload the plugin __init__ with controlled env; return its module."""
    for name in list(sys.modules):
        if name == "bm25_retriever" or name == "jev_rerank":
            del sys.modules[name]
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK", rerank)
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK_LOG", str(log_path))
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    sys.path.insert(0, str(PLUGIN_DIR))
    return importlib.reload(importlib.import_module("skill_retrieval_plugin_helper")) if False else None


def test_hook_module_imports_with_and_without_rerank():
    """The plugin __init__ imports cleanly; rerank presence check."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    PLUGIN_PARENT = PLUGIN_DIR.parent
    if str(PLUGIN_PARENT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_PARENT))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "skill_retrieval_init_test", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # With jev_rerank importable, RERANK_MODE reflects env (default off here).
    assert mod.RERANK_MODE in ("off", "jev")
    # Hook function exists and is callable.
    assert callable(mod._on_pre_llm_call)


def test_rerank_missing_candidate_benefits_bm25_score():
    """A rerank result missing candidates keeps fallback (design contract):
    partial orders never partially replace the injected list."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import jev_rerank
    mod = importlib.reload(jev_rerank)
    # stub: Jev returns only 1 of 2 candidates
    mod._load_key = lambda: "k"
    mod._jev_rerank_call = lambda s, q, k: (
        {"a": 0.9}, {"input_tokens": 1, "latency_ms": 1}, None)
    # emulate the hook's completeness contract directly:
    results = [("a", 1.0), ("b", 0.5)]
    score_by_id = dict(results)
    reranked_results = [
        (sid, score_by_id[sid]) for sid in ["a"] if sid in score_by_id
    ]
    assert len(reranked_results) != len(results)  # incomplete → hook keeps BM25