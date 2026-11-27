"""Issue #39 round-2 contract — findings from R1 review (deleg_3074a191).

Rows 10–15 of the case-table addendum in
`.hermes/specs/issue39/durable-snapshot-case-table.md`. RED rows against the
round-1 fix: R1-1 (durable recency), R1-2 (pending evictions), R1-3 (platform
stickiness). GREEN coverage rows: R1-6 (read-through repopulates memory),
R1-7 (named rows never expire).

The storage factory is resolved via ``sys.modules.get`` FIRST, so a
``plugins.plugin_storage`` stub keeps every test hermetic.
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
    """Stub plugins.plugin_storage against a tmp sqlite file."""

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


# ─── R1-1: durable recency follows use, not capture time ────────────────────

def test_r1_1_durable_recency_touched_on_named_read_through(
    storage_stub, monkeypatch
):
    """Capture 256 sids → rebuild → read THROUGH the oldest → capture one
    new sid → rebuild → the oldest must still resolve.

    The durable prune must evict by use time (last capture OR last
    read-through), never by capture time alone: a session at the bound that
    is in active use must not lose its row while unused ones are kept.
    """
    i1 = _exec(monkeypatch, "i1")
    limit = getattr(i1, "_MAX_SNAPSHOT_SESSIONS", 256)
    for n in range(limit):
        i1._remember_capability_snapshot(f"sess-{n:03d}", frozenset({f"n{n:03d}"}))

    i2 = _exec(monkeypatch, "i2")
    assert i2._capability_kwargs_for_session("sess-000") is not None  # touch

    i2._remember_capability_snapshot("sess-new", frozenset({"new"}))  # 257th → prune

    i3 = _exec(monkeypatch, "i3")
    assert i3._capability_kwargs_for_session("sess-000") is not None, (
        "active session at the 256-bound lost its durable row: prune orders "
        "by capture time instead of use time"
    )


# ─── R1-2: a transient store failure at eviction time ────────────────────────

def test_r1_2_transient_store_failure_still_deletes_evicted_row(
    tmp_path, monkeypatch, stub_db_path
):
    """One transient open failure must not leave the evicted sid's row in the
    store: the next successful durable operation flushes pending evictions.

    Sequence: capture e000 (store ok), capture 255 more (store ok), capture
    one more with the store breaking exactly once (this trigger evicts e000
    from the memory LRU), then capture again with the store recovered — the
    final rebuild must find NO row for e000 (eviction = skip, invariant 2).
    """
    opens = {"n": 0}
    fail_at = 257  # the open attempt that coincides with e000's eviction

    def flaky(name, filename="data.db"):
        opens["n"] += 1
        if opens["n"] == fail_at:
            raise sqlite3.OperationalError("transient failure (simulated)")
        return sqlite3.connect(stub_db_path)

    stub = types.ModuleType(_STUB)
    stub.plugin_db = flaky
    monkeypatch.setitem(sys.modules, _STUB, stub)

    i1 = _exec(monkeypatch, "i1")
    limit = getattr(i1, "_MAX_SNAPSHOT_SESSIONS", 256)
    i1._remember_capability_snapshot("e000", frozenset({"e"}))
    for n in range(limit - 1):
        i1._remember_capability_snapshot(f"sess-{n:03d}", frozenset({f"n{n:03d}"}))
    # 257th capture: memory evicts e000; the store breaks on this open.
    i1._remember_capability_snapshot("tail-a", frozenset({"t"}))
    # Store recovered: the next capture flushes the pending eviction.
    i1._remember_capability_snapshot("tail-b", frozenset({"t"}))

    conn = sqlite3.connect(stub_db_path)
    try:
        row = conn.execute(
            "SELECT sid, captured_at FROM capability_snapshots WHERE sid = 'e000'"
        ).fetchone()
        assert row is None, (
            "evicted sid kept a durable row after a transient store failure — "
            "a rebuilt instance would resurrect its injection (invariant 2)"
        )
    finally:
        conn.close()

    i3 = _exec(monkeypatch, "i3")
    assert i3._capability_kwargs_for_session("e000") is None


# ─── R1-3: platform hint survives a platform-less recapture ─────────────────

def test_r1_3_platform_hint_survives_platform_less_recapture(
    storage_stub, monkeypatch
):
    """Memory keeps the old platform when a recapture carries none; the
    durable row must do the same (COALESCE), or a rebuilt instance silently
    degrades platform-preferred retrieval."""
    i1 = _exec(monkeypatch, "i1")
    i1._remember_capability_snapshot("sid-p", frozenset({"first"}), "telegram")
    i1._remember_capability_snapshot("sid-p", frozenset({"second"}))  # no platform

    i2 = _exec(monkeypatch, "i2")
    kwargs = i2._capability_kwargs_for_session("sid-p")
    assert kwargs is not None
    assert kwargs["visible_names"] == {"second"}
    assert kwargs["platform_hint"] == "telegram"


# ─── R1-6 (coverage): read-through repopulates BOTH memory dicts ────────────

def test_r1_6_read_through_repopulates_memory_lru(storage_stub, monkeypatch):
    i1 = _exec(monkeypatch, "i1")
    i1._remember_capability_snapshot("sess-6", frozenset({"alpha-skill"}), "telegram")

    i2 = _exec(monkeypatch, "i2")
    assert "sess-6" not in i2._session_capability_snaps
    assert i2._capability_kwargs_for_session("sess-6") is not None
    assert "sess-6" in i2._session_capability_snaps
    assert i2._session_platforms.get("sess-6") == "telegram"


# ─── R1-7 (coverage): a named row aged beyond the window still applies ──────

def test_r1_7_named_row_aged_beyond_window_still_applies(
    storage_stub, monkeypatch, stub_db_path
):
    i1 = _exec(monkeypatch, "i1")
    i1._remember_capability_snapshot("sid-old", frozenset({"old-skill"}))

    conn = sqlite3.connect(stub_db_path)
    try:
        with conn:
            conn.execute(
                "UPDATE capability_snapshots SET captured_at = ? WHERE sid = 'sid-old'",
                (time.time() - 3600.0,),
            )
    finally:
        conn.close()

    i2 = _exec(monkeypatch, "i2")
    kwargs = i2._capability_kwargs_for_session("sid-old")
    assert kwargs is not None, "named rows must never expire"


# ─── shared loader (same shape as the round-1 contract file) ────────────────

def _exec(monkeypatch, tag):
    monkeypatch.syspath_prepend(str(_PLUGIN_DIR / "scripts"))
    name = f"sr39r2_{tag}"
    if name in sys.modules:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod
