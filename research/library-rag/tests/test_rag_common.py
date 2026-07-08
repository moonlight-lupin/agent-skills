import math
import struct

import pytest

import rag_common as rc


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
                        lambda texts, key, retries=3: ([[1.0, 2.0]], {"prompt_tokens": 1}))
    assert rc.get_embedding("hello", "key") == [1.0, 2.0]


def test_load_api_key_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert rc.load_api_key() == "sk-test"


def test_load_api_key_from_env_file(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text('# comment\nOPENROUTER_API_KEY="sk-from-file"\n')
    monkeypatch.setenv("HERMES_ENV", str(env))
    assert rc.load_api_key() == "sk-from-file"


def test_load_api_key_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("HERMES_ENV", str(tmp_path / "does-not-exist.env"))
    with pytest.raises(ValueError):
        rc.load_api_key()
    assert rc.load_api_key(required=False) == ""
