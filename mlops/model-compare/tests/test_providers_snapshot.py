#!/usr/bin/env python3
"""Keep references/providers.json honest.

The canonical provider registry is `PROVIDERS` in scripts/compare.py. The JSON
snapshot is a human-facing convenience; this test fails if the two drift apart
(a provider added/removed/renamed in code but not the snapshot, or a mismatched
env var / endpoint / cost). It also validates the snapshot's shape. Pure stdlib.
"""

import json
import os
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import compare  # noqa: E402

SNAPSHOT_PATH = SKILL_DIR / "references" / "providers.json"


def _load_snapshot():
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def test_snapshot_is_valid_json_with_required_keys():
    snap = _load_snapshot()
    for key in ("snapshot_date", "routing_order", "providers"):
        assert key in snap, f"providers.json missing top-level key: {key}"
    assert isinstance(snap["providers"], dict) and snap["providers"]


def test_provider_set_matches_code():
    snap = _load_snapshot()
    assert set(snap["providers"]) == set(compare.PROVIDERS), (
        "providers.json is out of sync with PROVIDERS in compare.py — "
        f"snapshot={sorted(snap['providers'])} code={sorted(compare.PROVIDERS)}"
    )


def test_routing_order_covers_every_provider_exactly_once():
    snap = _load_snapshot()
    assert sorted(snap["routing_order"]) == sorted(compare.PROVIDERS)
    assert len(snap["routing_order"]) == len(set(snap["routing_order"]))


def test_each_provider_env_endpoint_and_cost_match_code():
    snap = _load_snapshot()
    for name, p in snap["providers"].items():
        cfg = compare.PROVIDERS[name]
        assert p["env"] == cfg["key_env"], f"{name}: env mismatch"
        assert p["endpoint"] == cfg["base_url"], f"{name}: endpoint mismatch"
        expected_cost = "paid" if cfg.get("paid") else "free"
        assert p["cost"] == expected_cost, f"{name}: cost mismatch"


def test_each_provider_lists_representative_example_models():
    snap = _load_snapshot()
    for name, p in snap["providers"].items():
        assert isinstance(p.get("example_models"), list) and p["example_models"], (
            f"{name}: example_models must be a non-empty list"
        )
        assert all(isinstance(m, str) and m for m in p["example_models"])


def test_snapshot_carries_no_hardcoded_model_counts():
    """The whole point of the snapshot is to avoid drift-prone counts."""
    raw = SNAPSHOT_PATH.read_text(encoding="utf-8")
    # No "<provider>: 121 models"-style integers in the model fields.
    for name, p in _load_snapshot()["providers"].items():
        assert "count" not in p and "model_count" not in p, f"{name}: drop model counts"
    assert raw  # sanity


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
