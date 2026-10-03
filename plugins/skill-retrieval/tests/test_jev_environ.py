# ═══════════════════════════════════════════════════════════════════════════════
# Environ-only resolution (code-review finding #1 on PR 131290)
# ═══════════════════════════════════════════════════════════════════════════════

import importlib
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _fresh_mod():
    """Import (or re-import) the reranker module from scripts/."""
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    mod = importlib.import_module("jev_rerank")
    return importlib.reload(mod)


def test_load_key_reads_environ_only(monkeypatch, tmp_path):
    """_load_key must read os.environ only.

    Hazard: reading the Hermes .env file directly fails the security scan and,
    under a non-default profile whose startup env differs, can read another
    profile's secrets. Hermes loads the active profile's .env into os.environ
    at startup, so environ is the single correct source.
    """
    import os
    env_file = tmp_path / ".env"
    env_file.write_text("TYPESAFE_API_KEY=from-file\nTYPESAFE_KEY=legacy-from-file\n")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_KEY", raising=False)
    mod = _fresh_mod()
    assert mod._load_key() is None  # file must NOT be consulted


def test_load_key_environ_primary(monkeypatch, tmp_path):
    """TYPESAFE_API_KEY wins over legacy TYPESAFE_KEY; None when absent."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("TYPESAFE_KEY", "legacy-k")
    mod = _fresh_mod()
    assert mod._load_key() == "legacy-k"
    monkeypatch.setenv("TYPESAFE_API_KEY", "primary-k")
    assert mod._load_key() == "primary-k"


def test_rerank_env_flag_environ_only(monkeypatch, tmp_path):
    """SKILL_RETRIEVAL_RERANK is read from environ only, never from a .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("SKILL_RETRIEVAL_RERANK=jev\n")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SKILL_RETRIEVAL_RERANK", raising=False)
    mod = _fresh_mod()
    assert mod.RERANK_MODE == "off"  # file must NOT enable rerank


def test_env_log_path_uses_hermes_home_helper(monkeypatch, tmp_path):
    """Default A/B log path resolves through hermes_constants.get_hermes_home().

    Hazard: a hardcoded Path.home()/.hermes path ignores profile homes and the
    HERMES_HOME override, so logs for different profiles can collide or land
    outside the profile's data dir.
    """
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("SKILL_RETRIEVAL_RERANK_LOG", raising=False)
    mod = _fresh_mod()
    p = mod._env_log_path()
    assert str(p).endswith("data/jev-trial/rerank_ab_log.jsonl") or str(
        p
    ).endswith("data\\jev-trial\\rerank_ab_log.jsonl")
    assert str(tmp_path) in str(p)


def test_ab_log_rotates_when_over_cap(monkeypatch, tmp_path):
    """A/B log past LOG_MAX_BYTES rotates to <name>.1 (one older generation).

    Hazard: an unattended install could accumulate an unbounded JSONL file.
    """
    log_path = tmp_path / "rerank_ab_log.jsonl"
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK", "jev")
    monkeypatch.setenv("SKILL_RETRIEVAL_RERANK_LOG", str(log_path))
    mod = _fresh_mod()
    mod.LOG_MAX_BYTES = 100  # shrink the cap for the test
    old = {"ts": "t0", "query": "x" * 40}
    new = {"ts": "t1", "query": "y" * 40}
    mod._write_log(old)
    mod._write_log(new)  # should push past the 100-byte cap
    mod._write_log(new)  # triggers rotation
    rotated = tmp_path / "rerank_ab_log.jsonl.1"
    assert log_path.exists()
    assert rotated.exists(), "log must rotate once over the cap"
    assert "t0" in rotated.read_text()  # pre-rotation content survived