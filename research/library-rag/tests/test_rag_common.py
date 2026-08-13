import math
import struct

import pytest

import rag_common as rc


@pytest.fixture(autouse=True)
def _reset_embedding_config():
    """Keep module-level provider config isolated across tests."""
    rc.API_URL = rc._NVIDIA_API_URL
    rc.EMBEDDING_MODEL = rc._NVIDIA_EMBEDDING_MODEL
    rc.EMBEDDING_DIMS = rc._NVIDIA_EMBEDDING_DIMS
    rc.API_KEY_ENV = "NVIDIA_API_KEY"
    yield
    rc.API_URL = rc._NVIDIA_API_URL
    rc.EMBEDDING_MODEL = rc._NVIDIA_EMBEDDING_MODEL
    rc.EMBEDDING_DIMS = rc._NVIDIA_EMBEDDING_DIMS
    rc.API_KEY_ENV = "NVIDIA_API_KEY"


def test_normalize_unit_length():
    v = rc.normalize_vec([3.0, 4.0])
    assert math.isclose(math.hypot(*v), 1.0, rel_tol=1e-6)
    assert math.isclose(v[0], 0.6, rel_tol=1e-6)
    assert math.isclose(v[1], 0.8, rel_tol=1e-6)


def test_normalize_zero_vector_is_unchanged():
    assert rc.normalize_vec([0.0, 0.0]) == [0.0, 0.0]


def test_float_to_blob_normalizes_and_packs_float32():
    blob = rc.float_to_blob([3.0, 4.0])
    assert len(blob) == 2 * 4  # 2 float32 values
    vals = struct.unpack("2f", blob)
    assert math.isclose(math.hypot(*vals), 1.0, rel_tol=1e-6)


def test_get_embedding_wraps_batch(monkeypatch):
    monkeypatch.setattr(rc, "get_embeddings",
                        lambda texts, key, retries=3, input_type=None: (
                            [[1.0, 2.0]], {"prompt_tokens": 1}))
    assert rc.get_embedding("hello", "key") == [1.0, 2.0]


def test_get_embeddings_includes_input_type(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "data": [{"embedding": [0.1, 0.2]}],
                "usage": {},
            }

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr(rc.requests, "post", fake_post)
    embs, _ = rc.get_embeddings(["q"], "k", input_type="query")
    assert embs == [[0.1, 0.2]]
    assert captured["url"] == rc.API_URL
    assert captured["json"]["model"] == rc.EMBEDDING_MODEL
    assert captured["json"]["input_type"] == "query"


def test_get_embeddings_omits_input_type_when_unset(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "data": [{"embedding": [0.1]}],
                "usage": {},
            }

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return FakeResp()

    monkeypatch.setattr(rc.requests, "post", fake_post)
    rc.get_embeddings(["q"], "k")
    assert "input_type" not in captured["json"]


def test_load_api_key_from_env(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-test")
    assert rc.load_api_key() == "nvapi-test"


def test_load_api_key_falls_back_to_openrouter(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fallback")
    monkeypatch.setenv("HERMES_ENV", "/nonexistent/path.env")
    assert rc.load_api_key() == "sk-or-fallback"
    # Must switch off the NVIDIA endpoint so the OpenRouter key is not
    # sent to integrate.api.nvidia.com by accident.
    assert rc.API_URL == rc._OPENROUTER_API_URL
    assert rc.EMBEDDING_MODEL == rc._OPENROUTER_EMBEDDING_MODEL
    assert rc.EMBEDDING_DIMS == rc._OPENROUTER_EMBEDDING_DIMS


def test_load_api_key_nvidia_restores_after_openrouter_fallback(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fallback")
    monkeypatch.setenv("HERMES_ENV", "/nonexistent/path.env")
    rc.load_api_key()
    assert rc.API_URL == rc._OPENROUTER_API_URL

    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-preferred")
    assert rc.load_api_key() == "nvapi-preferred"
    assert rc.API_URL == rc._NVIDIA_API_URL
    assert rc.EMBEDDING_MODEL == rc._NVIDIA_EMBEDDING_MODEL


def test_load_api_key_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text('# comment\nNVIDIA_API_KEY="nvapi-from-file"\n')
    monkeypatch.setenv("HERMES_ENV", str(env))
    assert rc.load_api_key() == "nvapi-from-file"


def test_load_api_key_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("HERMES_ENV", str(tmp_path / "does-not-exist.env"))
    with pytest.raises(ValueError):
        rc.load_api_key()
    assert rc.load_api_key(required=False) == ""


def test_embedding_config_defaults():
    assert rc.EMBEDDING_MODEL == "nvidia/nemotron-3-embed-1b"
    assert rc.EMBEDDING_DIMS == 2048
    assert rc.API_URL == "https://integrate.api.nvidia.com/v1/embeddings"
    assert rc.API_KEY_ENV == "NVIDIA_API_KEY"
