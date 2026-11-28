import re
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]

def _skill_md(skill: str):
    return PLUGIN_DIR / "skills" / skill / "SKILL.md"

def test_always_loaded_skill_files_stay_under_the_hard_cap():
    """v0.6.0 acceptance: the always-loaded SKILL.md bodies of build, spec, and
    test-evals are at or under the 8 KB hard cap (bytes asserted, not timestamps,
    so a re-inlined rule re-fails the cap). Debug ships small by design."""
    budget = 8192
    for skill in ("build", "spec", "test-evals", "debug", "repo-context"):
        size = _skill_md(skill).stat().st_size
        assert size <= budget, f"{skill}/SKILL.md is {size} bytes (cap {budget})"

def test_repo_context_skill_cites_engine():
    """v0.6.1: the skill must reference its deterministic engine by path and
    by BOTH modes, plus the survey-stamp wording it shares with review-commit."""
    body = _skill_md("repo-context").read_text()
    for probe in ("scripts/inventory.py", "survey", "check", "survey stamp"):
        assert probe in body, f"repo-context/SKILL.md missing {probe!r}"

def test_debug_attack_the_premise():
    """v0.6.1: attack-the-premise (Lauren Tan's pstack pack, MIT, verified
    2026-11-28) lands as a stop rule: two failed fixes sharing one premise must
    test the premise before fix #3 — plus one Red Flag line."""
    body = _skill_md("debug").read_text()
    assert "test the premise" in body
    assert "same premise" in body
    assert "before fix #3" in body
    reds = body.split("## Red Flags")[1].split("## ")[0]
    assert "premise" in reds

def test_principles_index_wired():
    """v0.6.1: the six-entry pstack principles index exists, carries the
    attribution line without machine-local paths, and the orchestrator
    references list points at it."""
    idx = PLUGIN_DIR / "skills" / "orchestrator" / "references" / "principles-index.md"
    assert idx.exists()
    body = idx.read_text()
    assert "attack-the-premise" in body and "sequence-verifiable-units" in body
    assert "Lauren Tan" in body and "MIT" in body
    for forbidden in ("/root/", ".cursor", "192.168.", ".hermes"):
        assert forbidden not in body
    assert "references/principles-index.md" in _skill_md("orchestrator").read_text()

def test_bootstrap_route_wired():
    """v0.6.1: the orchestrator routes existing-repo starts to the repo-context
    bootstrap before spec/build planning."""
    body = _skill_md("orchestrator").read_text()
    assert "repo-context" in body and "bootstrap" in body

def test_maintenance_wired():
    """v0.6.1: review-commit's commit-gate step runs the inventory check and
    carries the named-skip rule — at the gate, not post-ship."""
    body = _skill_md("review-commit").read_text()
    assert "inventory.py check" in body and "skip" in body

def test_router_skills_do_not_grow_past_their_drift_allowance():
    """orchestrator and review-commit were 'not the problem' per the signed brief
    (0.5.0 sizes 8,598 / 9,761 bytes incl. frontmatter). The debug route and the
    CI-loop pointer must not open-endedly grow them: bound each at its 0.5.0 size
    plus 1 KB. grill stays uncapped this rung (the brief only allows, not
    mandates, trimming it)."""
    allowances = {"orchestrator": 8598 + 1024, "review-commit": 9761 + 1024}
    for skill, cap in allowances.items():
        size = _skill_md(skill).stat().st_size
        assert size <= cap, f"{skill}/SKILL.md is {size} bytes (allowance {cap})"

def _rule_landed(skill: str, target_ref: str, probes: list):
    """A moved rule must exist in the NAMED REFERENCE FILE ONLY, so 'shrink'
    cannot mean 'delete' AND the skill's own pointer prose cannot satisfy the
    check by mentioning the probe strings."""
    ref = PLUGIN_DIR / "skills" / skill / "references" / target_ref
    assert ref.exists(), f"{ref} missing"
    body = ref.read_text()
    missing = [p for p in probes if p not in body]
    return missing

def test_moved_build_rules_survive():
    missing = _rule_landed("build", "build-doctrine.md", [
        "Stamped briefs",
        "SDK-style interfaces",
        "Cadenced inner/outer loop",
        "Treat review reports as final proof",
        "Continuous execution",
        "Dispatch multiple implementation subagents in parallel",
    ])
    assert not missing, f"build rules dropped by the shrink: {missing}"
    ledger = (PLUGIN_DIR / "skills/build/references/ledger-orchestration-adaptation.md").read_text()
    assert "no-progress guard" in ledger, "ledger curation rules lost 'no-progress guard'"

def test_moved_spec_rules_survive():
    missing = _rule_landed("spec", "spec-doctrine.md", [
        "highest seam possible",
        "use React",
        "Zoom Out",
        "verbatim, as data",
        "Complexity Tracking",
        "Path A",
        "Do not plan on top of ambiguity",
        "batching related ones",
    ])
    assert not missing, f"spec rules dropped by the shrink: {missing}"

def test_moved_test_rules_survive():
    missing = _rule_landed("test-evals", "test-doctrine.md", [
        "Iron Law",
        "RED",
        "Beyonce",
        "DAMP",
        "mock",
    ])
    assert not missing, f"test rules dropped by the shrink: {missing}"

def test_debug_skill_is_bundled_and_routed():
    """The ninth bundled skill exists, is registered, and the orchestrator routes
    bug-shaped work to it."""
    assert (_skill_md("debug")).exists()
    text = (_skill_md("debug")).read_text()
    for probe in ("Reproduce", "highest public seam", "Minimal fix", "full acceptance suite", "risk-derived tier"):
        assert probe in text, f"debug/SKILL.md lost: {probe}"
    orch = (_skill_md("orchestrator")).read_text()
    assert "debug" in orch, "orchestrator stage table lost the debug route"
    routing = (PLUGIN_DIR / "skills" / "orchestrator" / "references" / "risk-routing.md").read_text()
    assert "debug" in routing, "risk-routing lost the bug-shaped-work route"

def test_review_commit_has_the_ci_loop_home():
    ref = PLUGIN_DIR / "skills" / "review-commit" / "references" / "ci-loop-and-pr-hygiene.md"
    text = ref.read_text()
    for probe in ("Watch CI", "Reproduce locally", "confirm budget", "pre-existing",
                  "force-push"):
        assert probe in text, f"ci-loop-and-pr-hygiene.md lost: {probe}"
    ws = (PLUGIN_DIR / "skills" / "review-commit" / "references" / "workflow-steps.md").read_text()
    assert "ci-loop-and-pr-hygiene.md" in ws
    sk = (_skill_md("review-commit")).read_text()
    assert "ci-loop-and-pr-hygiene.md" in sk


def test_goal_binding_reference_is_wired():
    """The /goal integration: single-home reference with contract template, a
    hard-gate rule, and a DERIVED (not fixed) turn budget."""
    ref = PLUGIN_DIR / "skills" / "orchestrator" / "references" / "goal-binding.md"
    text = ref.read_text()
    for probe in ("outcome:", "verify:", "/goal gate add", "goals.max_turns",
                  "never the target", "stop_when:", "fallback"):
        assert probe in text, f"goal-binding.md lost: {probe}"
    assert "N ≈" in text or "N =" in text or "base(" in text, "no budget formula"
    orch = (_skill_md("orchestrator")).read_text()
    assert "goal-binding.md" in orch, "orchestrator SKILL lost the goal-binding pointer"
    for s in ("build", "review-commit"):
        assert f"goal-binding.md" in (_skill_md(s)).read_text(), f"{s} lost the goal-binding pointer"
