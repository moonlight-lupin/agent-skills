"""Issue #39 — durable session capability snapshots.

The plugin module is re-instantiated between turns (plugin manager rebuild);
module globals cannot carry a snapshot across that boundary. The fix mirrors
the snapshot LRU into a plugin_storage-backed sqlite row set so the next
instance recovers it. Each test exercises the seam across two module
instances (I1/I2).

The storage factory is resolved via ``sys.modules.get`` FIRST, so each test
installs a ``plugins.plugin_storage`` stub backed by a tmp dir and never
touches the host's real ``plugin-data``.
"""
import importlib.util
import sqlite3
import sys
import time
import types
from pathlib import Path

import pytest

_PLUGIN_DIR = Path(__file__).resolve().parent.parent
_STUB = "plugins.plugin_storage"
_DB_NAME = "skill-retrieval"


@pytest.fixture()
def storage_stub(tmp_path, monkeypatch):
    """Install a plugins.plugin_storage stub whose plugin_db() opens a
    per-test tmp sqlite file. Restored after the test even if a real entry
    existed."""
    def factory(name, filename="data.db"):
        return sqlite3.connect(tmp_path / f"{name}-{filename}")

    stub = types.ModuleType(_STUB)
    stub.plugin_db = factory
    had = _STUB in sys.modules
    previous = sys.modules.get(_STUB)
    monkeypatch.setitem(sys.modules, _STUB, stub)
    yield factory
    if had:
        monkeypatch.setitem(sys.modules, _STUB, previous)


@pytest.fixture()
def stub_db_path(tmp_path):
    return tmp_path / f"{_DB_NAME}-data.db"


def _exec_instance(monkeypatch, tag):
    """Execute the plugin's __init__.py as a fresh, distinct module object
    (the issue's I1/I2 shape)."""
    monkeypatch.syspath_prepend(str(_PLUGIN_DIR / "scripts"))
    name = f"sr39_{tag}"
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ─── Row 1: first sight ─────────────────────────────────────────────────────

def test_fresh_store_named_miss_returns_none(storage_stub, monkeypatch):
    """No snapshot was ever captured: a named lookup returns None so the
    existing skip/fail-open gate keeps its shape."""
    mod = _exec_instance(monkeypatch, "i1")
    assert mod._capability_kwargs_for_session("sess-39") is None


# ─── Row 2 (+ row 8): durability across module re-instantiation ─────────────

def test_named_snapshot_survives_module_reinstantiation(
    storage_stub, monkeypatch
):
    """I1 captures a named session's snapshot; I1's module object is dropped
    and a NEW instance (I2) must still resolve it — THE issue-39 bug."""
    i1 = _exec_instance(monkeypatch, "i1")
    i1._remember_capability_snapshot(
        "sess-39", frozenset({"alpha-skill", "beta-skill"}), "telegram"
    )

    i2 = _exec_instance(monkeypatch, "i2")
    kwargs = i2._capability_kwargs_for_session("sess-39")
    assert kwargs is not None, "rebuilt instance lost the previous turn's snapshot"
    assert kwargs["visible_names"] == {"alpha-skill", "beta-skill"}
    assert kwargs["platform_hint"] == "telegram"  # row 8: platform hint durable


# ─── Row 3: anonymous reuse across instances (< 30s) ────────────────────────

def test_anonymous_snapshot_reused_across_instances(storage_stub, monkeypatch):
    i1 = _exec_instance(monkeypatch, "i1")
    i1._remember_capability_snapshot("", frozenset({"anon-skill"}))

    i2 = _exec_instance(monkeypatch, "i2")
    kwargs = i2._capability_kwargs_for_session("")
    assert kwargs is not None
    assert kwargs["visible_names"] == {"anon-skill"}


# ─── Row 4: anonymous staleness window still bounds durable reuse ───────────

def test_anonymous_snapshot_stale_across_instances_is_dropped(
    storage_stub, monkeypatch, stub_db_path
):
    i1 = _exec_instance(monkeypatch, "i1")
    i1._remember_capability_snapshot("", frozenset({"old-skill"}))

    # Age the durable row beyond the 30s staleness window.
    conn = sqlite3.connect(stub_db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE capability_snapshots SET captured_at = ? WHERE sid = ''",
                (time.time() - 31.0,),
            )
    finally:
        conn.close()

    i2 = _exec_instance(monkeypatch, "i2")
    assert i2._capability_kwargs_for_session("") is None


# ─── Row 5: storage factory unavailable → 0.8.0 behavior, no crash ──────────

def test_unavailable_storage_degrades_to_in_memory(monkeypatch):
    monkeypatch.setitem(sys.modules, _STUB, None)  # import raises ImportError
    i1 = _exec_instance(monkeypatch, "i1")
    i1._remember_capability_snapshot("sess-39", frozenset({"alpha-skill"}))
    assert i1._capability_kwargs_for_session("sess-39") == {
        "visible_names": {"alpha-skill"}
    }

    i2 = _exec_instance(monkeypatch, "i2")
    assert i2._capability_kwargs_for_session("sess-39") is None


# ─── Row 6: last write wins ─────────────────────────────────────────────────

def test_durable_capture_latest_write_wins(storage_stub, monkeypatch):
    i1 = _exec_instance(monkeypatch, "i1")
    i1._remember_capability_snapshot("sess-39", frozenset({"first"}))
    i1._remember_capability_snapshot("sess-39", frozenset({"second", "final"}))

    i2 = _exec_instance(monkeypatch, "i2")
    assert i2._capability_kwargs_for_session("sess-39") == {
        "visible_names": {"second", "final"}
    }


# ─── Row 7: the durable store keeps the 256-session bound ───────────────────

def test_durable_store_bounded_at_256_sessions(
    storage_stub, monkeypatch, stub_db_path
):
    i1 = _exec_instance(monkeypatch, "i1")
    limit = getattr(i1, "_MAX_SNAPSHOT_SESSIONS", 256)
    for n in range(limit + 1):
        i1._remember_capability_snapshot(f"sess-{n:03d}", frozenset({f"n{n:03d}"}))

    conn = sqlite3.connect(stub_db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM capability_snapshots").fetchone()[0]
    finally:
        conn.close()
    assert count <= limit

    i2 = _exec_instance(monkeypatch, "i2")
    assert i2._capability_kwargs_for_session("sess-000") is None  # oldest evicted
    kept = i2._capability_kwargs_for_session(f"sess-{limit:03d}")
    assert kept is not None
    assert kept["visible_names"] == {f"n{limit:03d}"}


# ─── Row 9: broken store never breaks the request path ──────────────────────

def test_broken_store_never_breaks_capture(tmp_path, monkeypatch):
    def broken_factory(name, filename="data.db"):
        raise sqlite3.OperationalError("disk full (simulated)")

    stub = types.ModuleType(_STUB)
    stub.plugin_db = broken_factory
    monkeypatch.setitem(sys.modules, _STUB, stub)

    i1 = _exec_instance(monkeypatch, "i1")
    i1._remember_capability_snapshot("sess-39", frozenset({"alpha-skill"}))
    assert i1._capability_kwargs_for_session("sess-39") == {
        "visible_names": {"alpha-skill"}
    }
