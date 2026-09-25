#!/usr/bin/env python3
"""v1.8.0 — deep-research gate hardening (ported from CoS plugin v0.7.2).

Findings from the post-v0.7.0 gate review, each pinned by a test:

1. validate-report was fooled by look-alike headings ('### Sources of
   revenue', '## Mind the Gaps') and skipped the evidence-key check entirely
   when no real '## Sources' heading existed.
2. verify-citations treated a bracketed year ('[2024]') as a citation.
3. register-source / add-claim accepted any quality / polarity string.
4. '$2.4 billion' vs 'US$2.4bn' scored as a contradiction.
5. A claim tagged [VERIFIED] was never checked for >=2 independent sources.
6. The 'at least one counter-evidence claim' rule was never checked.
7. The source-quality mix (healthy/acceptable/weak) was never computed.
Plugin-integration findings (routing, run dir, licence) are plugin-specific
and tested in the plugin's own suite; this file carries only the gate tests.
"""

from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

GOOD_REPORT = """# Report

## Executive Summary
Adoption grew 40% in 2025 [1], driven by demand [2].

## Analysis
The market reached $2.4 billion [1]. Critics disagree [2].

## Contradictions
Source A reports growth; source B reports decline [1] [2].

## Gaps
No primary pricing sources found.

## Conclusion
Growth is likely but unconfirmed.

## Sources

**Quality distribution:** 1 primary · 1 secondary · 0 tertiary — acceptable

| # | Title | URL | Quality | Accessed |
|---|-------|-----|---------|----------|
| 1 | Adoption Survey 2026 (https://real.example/survey) | https://real.example/survey | primary | 2026-09-24 |
| 2 | Market Analysis Quarterly (https://news.example/market) | https://news.example/market | secondary | 2026-09-24 |

**Evidence key** — `[VERIFIED]` corroborated across ≥2 independent, cited, dated sources · `[SOURCED]` from one named source, not independently corroborated · `[REASONED]` analytical judgement / inference · `[ESTIMATED]` calculation or stated assumption.

---
📊 Research stats: 12 min · 3 rounds · 8 queries · 9 URLs fetched · 2 sources cited
"""


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import research_validation as rv  # noqa: E402


def _ns(**kw):
    base = {"strict": False, "provider_used": None, "refute_none": None}
    base.update(kw)
    return type("A", (), base)()


def _run(fn, **kw):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = fn(_ns(**kw))
    out = buf.getvalue().strip().splitlines()
    return rc, (json.loads(out[-1]) if out else {})


def _report(tmp_path, text):
    p = tmp_path / "report.md"
    p.write_text(text, encoding="utf-8")
    return str(p)


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "run"
    assert _run(rv.cmd_init_run, dir=str(d), query="q", mode=None, provider=None)[0] == 0
    return d


def _source(run_dir, url, quality="primary"):
    rc, out = _run(rv.cmd_register_source, dir=str(run_dir),
                   json=json.dumps({"url": url, "title": "T", "quality": quality}))
    assert rc == 0, out
    return out["source_id"]


def _claim(run_dir, cid, sid, **extra):
    rec = {"claim_id": cid, "claim": "Adoption grew 40% in 2025",
           "kind": "factual", "snippet": "Adoption grew 40% in 2025", "source_id": sid}
    rec.update(extra)
    return _run(rv.cmd_add_claim, dir=str(run_dir), json=json.dumps(rec))


# ─── 1. structure check cannot be fooled by look-alike headings ─────────────

class TestStructureHeadings:
    def test_subheading_named_sources_is_not_the_sources_section(self, tmp_path):
        body = GOOD_REPORT.split("## Sources")[0] + "### Sources of revenue\nAds.\n\n📊 Research stats: 1m\n"
        rc, out = _run(rv.cmd_validate_report, report=_report(tmp_path, body))
        assert rc == 1
        text = " ".join(out["problems"])
        assert "Sources" in text
        assert "evidence key" in text.lower(), "a missing Sources section must not skip the legend check"

    def test_heading_merely_containing_gaps_is_not_the_gaps_section(self, tmp_path):
        rc, out = _run(rv.cmd_validate_report,
                       report=_report(tmp_path, GOOD_REPORT.replace("## Gaps", "## Mind the Gaps")))
        assert rc == 1
        assert any("Gaps" in p for p in out["problems"])

    @pytest.mark.parametrize("old,new", [
        ("## Gaps", "## Gaps and open questions"),
        ("## Sources", "## Sources & references"),
        ("## Executive Summary", "## Executive summary"),
    ])
    def test_decorated_headings_that_start_with_the_name_still_pass(self, tmp_path, old, new):
        assert _run(rv.cmd_validate_report, report=_report(tmp_path, GOOD_REPORT.replace(old, new)))[0] == 0


# ─── 2. bracketed years are not citations ────────────────────────────────────

class TestBracketedYears:
    def test_bracketed_year_is_not_a_dangling_citation(self, tmp_path):
        report = GOOD_REPORT.replace("driven by demand [2].", "driven by demand in fiscal [2024] [2].")
        rc, out = _run(rv.cmd_verify_citations, report=_report(tmp_path, report))
        assert rc == 0, out

    def test_real_dangling_citation_still_fails(self, tmp_path):
        report = GOOD_REPORT.replace("driven by demand [2].", "driven by demand [2] [7].")
        assert _run(rv.cmd_verify_citations, report=_report(tmp_path, report))[0] == 1


# ─── 3. enumerated fields are validated ──────────────────────────────────────

class TestFieldValidation:
    def test_quality_is_case_normalised(self, run_dir):
        _source(run_dir, "https://a.example/x", quality="Primary")
        rec = json.loads((run_dir / "sources.jsonl").read_text().splitlines()[0])
        assert rec["quality"] == "primary"

    def test_unknown_quality_is_rejected(self, run_dir):
        rc, out = _run(rv.cmd_register_source, dir=str(run_dir),
                       json=json.dumps({"url": "https://a.example/x", "quality": "official"}))
        assert rc == 2 and "quality" in out["error"]

    def test_unknown_polarity_is_rejected(self, run_dir):
        sid = _source(run_dir, "https://a.example/x")
        rc, out = _claim(run_dir, "c1", sid, polarity="refutes")
        assert rc == 2 and "polarity" in out["error"]

    def test_basis_is_validated_and_normalised(self, run_dir):
        sid = _source(run_dir, "https://a.example/x")
        assert _claim(run_dir, "c1", sid, basis="VERIFIED")[0] == 0
        assert _claim(run_dir, "c2", sid, basis="confirmed")[0] == 2
        rec = json.loads((run_dir / "claims.jsonl").read_text().splitlines()[0])
        assert rec["basis"] == "verified"


# ─── 4. figure format variants are the same figure ───────────────────────────

class TestFigureFormats:
    @pytest.mark.parametrize("claim,snippet", [
        ("Revenue was $2.4 billion in 2024.", "Revenue was US$2.4bn in 2024."),
        ("The fund raised 40 million dollars in 2023.", "The fund raised 40mn dollars in 2023."),
        ("Output hit 3 trillion units in 2022.", "Output hit 3tn units in 2022."),
    ])
    def test_equivalent_formats_are_supported(self, claim, snippet):
        assert rv.support_score(claim, [snippet]) >= rv.SUPPORTED_THRESHOLD

    def test_different_magnitudes_still_contradict(self):
        assert rv.support_score("Revenue was $2.4bn in 2024.", ["Revenue was $2.4mn in 2024."]) < rv.PARTIAL_THRESHOLD


# ─── 5. [VERIFIED] needs two independent sources ─────────────────────────────

class TestVerifiedBasis:
    def _verified(self, run_dir, second_url):
        s1 = _source(run_dir, "https://www.alpha.example/report")
        s2 = _source(run_dir, second_url)
        assert _claim(run_dir, "c1", s1, basis="verified", polarity="refute")[0] == 0
        _run(rv.cmd_add_evidence, dir=str(run_dir), json=json.dumps(
            {"claim_id": "c1", "snippet": "Adoption grew 40% in 2025", "source_id": s2}))

    def test_single_host_fails_strict(self, run_dir):
        self._verified(run_dir, "https://alpha.example/other-page")
        rc, out = _run(rv.cmd_verify_claims, dir=str(run_dir), strict=True)
        assert rc == 1
        assert "verified" in json.dumps(out["results"]).lower()

    def test_single_host_only_warns_without_strict(self, run_dir):
        self._verified(run_dir, "https://alpha.example/other-page")
        rc, out = _run(rv.cmd_verify_claims, dir=str(run_dir), strict=False)
        assert rc == 0
        assert out["basis_warnings"] == 1

    def test_two_independent_hosts_pass(self, run_dir):
        self._verified(run_dir, "https://beta.example/study")
        rc, out = _run(rv.cmd_verify_claims, dir=str(run_dir), strict=True)
        assert rc == 0, out


# ─── 6. counter-evidence is required for 5+ source reports ──────────────────

class TestCounterEvidence:
    def _five_sources_all_support(self, run_dir):
        sids = [_source(run_dir, f"https://site{i}.example/a") for i in range(5)]
        for i, sid in enumerate(sids):
            assert _claim(run_dir, f"c{i}", sid, polarity="support")[0] == 0

    def test_no_refute_claims_fails_strict(self, run_dir):
        self._five_sources_all_support(run_dir)
        rc, out = _run(rv.cmd_verify_claims, dir=str(run_dir), strict=True)
        assert rc == 1
        assert out["refute_claims"] == 0
        assert "counter-evidence" in out["refute_warning"]

    def test_no_refute_claims_only_warns_without_strict(self, run_dir):
        self._five_sources_all_support(run_dir)
        rc, out = _run(rv.cmd_verify_claims, dir=str(run_dir), strict=False)
        assert rc == 0 and out["refute_warning"]

    def test_a_recorded_reason_waives_it_and_is_kept(self, run_dir):
        self._five_sources_all_support(run_dir)
        rc, out = _run(rv.cmd_verify_claims, dir=str(run_dir), strict=True,
                       refute_none="searched criticism and recall notices; none found")
        assert rc == 0, out
        manifest = json.loads((run_dir / "run_manifest.json").read_text())
        assert "recall notices" in manifest["refute_none_reason"]

    def test_small_stores_are_not_blocked(self, run_dir):
        sid = _source(run_dir, "https://one.example/a")
        _claim(run_dir, "c1", sid, polarity="support")
        assert _run(rv.cmd_verify_claims, dir=str(run_dir), strict=True)[0] == 0


# ─── 7. source-quality mix is computed ───────────────────────────────────────

class TestQualityMix:
    def test_healthy_mix(self, run_dir):
        for i, q in enumerate(["primary", "primary", "secondary", "secondary", "tertiary"]):
            sid = _source(run_dir, f"https://q{i}.example/a", quality=q)
        _claim(run_dir, "c1", sid, polarity="refute")
        out = _run(rv.cmd_verify_claims, dir=str(run_dir))[1]
        assert out["source_quality"] == {"primary": 2, "secondary": 2, "tertiary": 1,
                                         "total": 5, "rating": "healthy"}

    def test_weak_mix_warns(self, run_dir):
        for i in range(3):
            sid = _source(run_dir, f"https://forum{i}.example/t", quality="tertiary")
        _claim(run_dir, "c1", sid, polarity="refute")
        out = _run(rv.cmd_verify_claims, dir=str(run_dir))[1]
        assert out["source_quality"]["rating"] == "weak"
        assert "primary" in out["quality_warning"]
