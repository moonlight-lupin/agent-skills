"""v0.3 risk/complexity routing contract regression checks.

These tests check routing documentation rather than asserting a nonexistent
automatic runtime router. The orchestrator is a skill-driven policy.
"""
from pathlib import Path
import re

BASE = Path(__file__).resolve().parents[1]
REF = BASE / "skills/orchestrator/references"
ROUTING = (REF / "risk-routing.md").read_text(encoding="utf-8")


def test_risk_mapping_has_explicit_all_bands():
    for token in ("S0", "S1", "S2", "S3", "R0", "R1", "R2", "R3"):
        assert token in ROUTING
    assert "R0 / S0" in ROUTING
    assert "R0 / S1–S3 or R1" in ROUTING
    assert "R2 | T2" in ROUTING
    assert "R3 | T3" in ROUTING


def test_small_high_risk_escalates_and_large_low_risk_does_not():
    assert "five-line auth edit is R3" in ROUTING
    assert "1,000-line internal refactor may be" in ROUTING
    assert "Complexity does **not** by" in ROUTING


def test_live_deployment_and_budget_exhaustion_still_block():
    assert "three-reviewer gate" in ROUTING
    assert "NOT SHIP" in ROUTING
    assert "full acceptance suite" in ROUTING


def test_authoritative_stage_router_links_risk_reference():
    orchestrator = (BASE / "skills/orchestrator/SKILL.md").read_text(encoding="utf-8")
    assert "references/risk-routing.md" in orchestrator
    assert "risk R0–R3" in orchestrator
    assert "size tier first (T0-T3)" not in orchestrator


def test_manifest_version_and_review_budget_unchanged():
    manifest = (BASE / "plugin.yaml").read_text(encoding="utf-8")
    assert re.search(r"(?m)^version: 0\.5\.0$", manifest)
    tiers = (REF / "size-tiers.md").read_text(encoding="utf-8")
    for expected in ("| T1 ", "| T2 ", "| T3 ", "three-reviewer gate"):
        assert expected in tiers
