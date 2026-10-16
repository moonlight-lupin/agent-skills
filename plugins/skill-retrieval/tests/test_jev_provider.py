"""Rerank provider selection: TypeSafe (default) or OpenRouter.

OpenRouter serves Jev on the same System One contract, so only the URL, the key
env var and the model id change. Everything else (request shape, fallback,
logging, key handling) is shared and covered by test_jev_rerank.py.
"""
import importlib
import io
import json
import logging
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _fresh_mod():
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return importlib.reload(importlib.import_module("jev_rerank"))


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _capture_request(monkeypatch, mod, answers):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["auth"] = req.headers.get("Authorization")
        seen["body"] = json.loads(req.data)
        return _Resp(json.dumps({"answers": answers, "usage": {"input_tokens": 42}}).encode())

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    return seen


def _clear(monkeypatch):
    for name in ("SKILL_RETRIEVAL_RERANK_PROVIDER", "SKILL_RETRIEVAL_RERANK_MODEL",
                 "TYPESAFE_API_KEY", "TYPESAFE_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_default_provider_is_typesafe(monkeypatch):
    _clear(monkeypatch)
    mod = _fresh_mod()
    assert mod.RERANK_PROVIDER == "typesafe"
    assert mod._endpoint() == ("https://api.typesafe.ai/v1/systemone", "jev-latest")


def test_openrouter_provider_endpoint_and_default_model(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK_PROVIDER", "OpenRouter")
    mod = _fresh_mod()
    assert mod.RERANK_PROVIDER == "openrouter"
    assert mod._endpoint() == ("https://openrouter.ai/api/v1/systemone", "~typesafe/jev-latest")


def test_model_override_applies_to_either_provider(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK_MODEL", "typesafe/jev-1.14")
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK_PROVIDER", "openrouter")
    assert _fresh_mod()._endpoint()[1] == "typesafe/jev-1.14"
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK_PROVIDER", "typesafe")
    assert _fresh_mod()._endpoint()[1] == "typesafe/jev-1.14"


def test_invalid_provider_falls_back_to_typesafe(monkeypatch, caplog):
    _clear(monkeypatch)
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK_PROVIDER", "anthropic")
    with caplog.at_level(logging.WARNING):
        mod = _fresh_mod()
    assert mod.RERANK_PROVIDER == "typesafe"
    assert any("SKILL_RETRIEVAL_RERANK_PROVIDER" in r.message for r in caplog.records)


def test_openrouter_reads_only_its_own_key(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK_PROVIDER", "openrouter")
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-key")
    mod = _fresh_mod()
    assert mod._load_key() is None  # never sends a TypeSafe key to OpenRouter
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    assert mod._load_key() == "or-key"


def test_typesafe_ignores_openrouter_key(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    assert _fresh_mod()._load_key() is None


def test_openrouter_call_hits_openrouter_with_same_contract(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK_PROVIDER", "openrouter")
    mod = _fresh_mod()
    seen = _capture_request(monkeypatch, mod, {"rel_a": {"type": "noul", "noul": 0.9},
                                               "rel_b": {"type": "noul", "noul": 0.1}})
    probs, usage, error = mod._jev_rerank_call([("a", "Alpha"), ("b", "Beta")], "q", "or-key")
    assert error is None and probs == {"a": 0.9, "b": 0.1}
    assert seen["url"] == "https://openrouter.ai/api/v1/systemone"
    assert seen["auth"] == "Bearer or-key"
    assert seen["body"]["model"] == "~typesafe/jev-latest"
    assert set(seen["body"]["questions"]) == {"rel_a", "rel_b"}
    assert "state" in seen["body"]


def test_typesafe_call_unchanged(monkeypatch):
    _clear(monkeypatch)
    mod = _fresh_mod()
    seen = _capture_request(monkeypatch, mod, {"rel_a": {"probability": 0.7}})
    probs, _usage, error = mod._jev_rerank_call([("a", "Alpha")], "q", "ts-key")
    assert error is None and probs == {"a": 0.7}
    assert seen["url"] == "https://api.typesafe.ai/v1/systemone"
    assert seen["body"]["model"] == "jev-latest"
