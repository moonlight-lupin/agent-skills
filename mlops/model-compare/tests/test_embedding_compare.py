#!/usr/bin/env python3
"""Tests for embedding_compare.py — cosine, providers, test data, mocked HTTP.

No network calls. All API interactions are mocked via monkeypatch.
Run: python3 -m pytest tests/test_embedding_compare.py -v
"""

import json
import math
import os
import sys

import pytest

# Add scripts dir to path
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import embedding_compare as ec


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    """Ensure no real API keys leak into tests."""
    for key in ("NVIDIA_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)


# ─── Cosine ──────────────────────────────────────────────────────────────────

class TestCosine:
    def test_identical_vectors(self):
        v = [1.0, 0.0, 0.0]
        assert ec.cosine(v, v) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert ec.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert ec.cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_known_angle(self):
        # 45 degrees between [1,0] and [1,1]
        a = [1.0, 0.0]
        b = [1.0, 1.0]
        expected = 1.0 / math.sqrt(2)
        assert ec.cosine(a, b) == pytest.approx(expected)

    def test_zero_vector(self):
        assert ec.cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


# ─── polygon (optional) ──────────────────────────────────────────────────────

class TestPolygon:
    def test_polygon_if_exists(self):
        if not hasattr(ec, "polygon"):
            pytest.skip("polygon() not defined")
        # If present, just ensure it's callable
        assert callable(ec.polygon)


# ─── Providers ───────────────────────────────────────────────────────────────

class TestProviders:
    def test_providers_defined(self):
        assert "nvidia" in ec.PROVIDERS
        assert "openrouter" in ec.PROVIDERS

    def test_provider_fields(self):
        for name, cfg in ec.PROVIDERS.items():
            assert "url" in cfg, f"{name} missing url"
            assert "key_env" in cfg, f"{name} missing key_env"
            assert cfg["url"].startswith("https://"), f"{name} url not https"
            assert "/embeddings" in cfg["url"], f"{name} url should target embeddings"

    def test_nvidia_key_env(self):
        assert ec.PROVIDERS["nvidia"]["key_env"] == "NVIDIA_API_KEY"

    def test_openrouter_key_env(self):
        assert ec.PROVIDERS["openrouter"]["key_env"] == "OPENROUTER_API_KEY"

    def test_get_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="No API key"):
            ec.get_api_key("nvidia")

    def test_get_api_key_present(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nv-test")
        assert ec.get_api_key("nvidia") == "nv-test"

    def test_get_api_key_unknown(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            ec.get_api_key("nonexistent")


# ─── Test data ───────────────────────────────────────────────────────────────

class TestTestData:
    def test_pairs_count(self):
        assert len(ec.TEST_PAIRS) == 8

    def test_pairs_shape(self):
        for a, b, expected in ec.TEST_PAIRS:
            assert isinstance(a, str) and len(a) > 0
            assert isinstance(b, str) and len(b) > 0
            assert expected in ("similar", "dissimilar")

    def test_pairs_have_both_kinds(self):
        kinds = {p[2] for p in ec.TEST_PAIRS}
        assert kinds == {"similar", "dissimilar"}

    def test_retrieval_docs(self):
        assert len(ec.RETRIEVAL_DOCS) == 6
        for doc in ec.RETRIEVAL_DOCS:
            assert isinstance(doc, str) and len(doc) > 10

    def test_retrieval_queries(self):
        assert len(ec.RETRIEVAL_QUERIES) == 3

    def test_expected_matches_valid(self):
        assert len(ec.EXPECTED_MATCHES) == len(ec.RETRIEVAL_QUERIES)
        for idx in ec.EXPECTED_MATCHES:
            assert 0 <= idx < len(ec.RETRIEVAL_DOCS)

    def test_default_models_use_correct_slug(self):
        """OpenRouter bge-m3 must use uppercase BAAI/."""
        assert any("BAAI/bge-m3" in m for m in ec.DEFAULT_MODELS)
        assert not any("baai/bge-m3" in m for m in ec.DEFAULT_MODELS)


# ─── Model spec parsing ──────────────────────────────────────────────────────

class TestParseModelSpec:
    def test_valid(self):
        assert ec.parse_model_spec("nvidia:nvidia/nemotron-3-embed-1b") == (
            "nvidia",
            "nvidia/nemotron-3-embed-1b",
        )

    def test_openrouter_slug(self):
        assert ec.parse_model_spec("openrouter:BAAI/bge-m3") == (
            "openrouter",
            "BAAI/bge-m3",
        )

    def test_missing_colon(self):
        with pytest.raises(ValueError, match="provider:model_id"):
            ec.parse_model_spec("bge-m3")

    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="unknown provider"):
            ec.parse_model_spec("foo:bar")


# ─── Env loading ─────────────────────────────────────────────────────────────

class TestLoadEnv:
    def test_load_env_no_file(self, tmp_path):
        ec.load_env(str(tmp_path / "missing.env"))  # should not crash

    def test_load_env_reads_file(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("EMBED_TEST_KEY=hello\n# comment\nNVIDIA_API_KEY=fromfile\n")
        monkeypatch.delenv("EMBED_TEST_KEY", raising=False)
        monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
        ec.load_env(str(env_file))
        assert os.environ.get("EMBED_TEST_KEY") == "hello"
        assert os.environ.get("NVIDIA_API_KEY") == "fromfile"

    def test_env_vars_take_precedence(self, monkeypatch, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("NVIDIA_API_KEY=fromfile\n")
        monkeypatch.setenv("NVIDIA_API_KEY", "fromenv")
        ec.load_env(str(env_file))
        assert os.environ["NVIDIA_API_KEY"] == "fromenv"


# ─── get_embeddings (mocked HTTP) ────────────────────────────────────────────

def _mock_response(embeddings):
    """Build a fake urlopen context manager returning embedding JSON."""
    payload = {
        "data": [{"embedding": e, "index": i} for i, e in enumerate(embeddings)],
        "usage": {"prompt_tokens": 10, "total_tokens": 10},
    }
    raw = json.dumps(payload).encode("utf-8")

    class _Resp:
        def read(self):
            return raw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return _Resp()


class TestGetEmbeddings:
    def test_nvidia_url_and_input_type(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nv-key")
        captured = {}

        def fake_urlopen(req, timeout=30):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            captured["headers"] = dict(req.headers)
            return _mock_response([[0.1, 0.2, 0.3]])

        monkeypatch.setattr(ec.urllib.request, "urlopen", fake_urlopen)
        embs, usage, latency = ec.get_embeddings(
            "nvidia", "nvidia/nemotron-3-embed-1b", ["hello"], input_type="query"
        )
        assert captured["url"] == ec.PROVIDERS["nvidia"]["url"]
        assert captured["body"]["input_type"] == "query"
        assert captured["body"]["model"] == "nvidia/nemotron-3-embed-1b"
        assert captured["body"]["encoding_format"] == "float"
        assert embs == [[0.1, 0.2, 0.3]]
        assert usage["prompt_tokens"] == 10
        assert latency >= 0

    def test_openrouter_url_no_input_type(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        captured = {}

        def fake_urlopen(req, timeout=30):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _mock_response([[0.5, 0.5]])

        monkeypatch.setattr(ec.urllib.request, "urlopen", fake_urlopen)
        embs, _, _ = ec.get_embeddings(
            "openrouter", "BAAI/bge-m3", ["hi"], input_type="query"
        )
        assert captured["url"] == ec.PROVIDERS["openrouter"]["url"]
        assert "input_type" not in captured["body"]
        assert captured["body"]["model"] == "BAAI/bge-m3"
        assert embs == [[0.5, 0.5]]

    def test_nvidia_default_input_type_passage(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_API_KEY", "nv-key")
        captured = {}

        def fake_urlopen(req, timeout=30):
            captured["body"] = json.loads(req.data.decode("utf-8"))
            return _mock_response([[1.0]])

        monkeypatch.setattr(ec.urllib.request, "urlopen", fake_urlopen)
        ec.get_embeddings("nvidia", "nvidia/nemotron-3-embed-1b", ["doc"])
        assert captured["body"]["input_type"] == "passage"

    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            ec.get_embeddings("nope", "model", ["x"])


# ─── CLI ─────────────────────────────────────────────────────────────────────

class TestCLI:
    def test_help(self):
        with pytest.raises(SystemExit) as exc:
            ec.main(["--help"])
        assert exc.value.code == 0

    def test_default_models_include_baai(self):
        assert "openrouter:BAAI/bge-m3" in ec.DEFAULT_MODELS
