#!/usr/bin/env python3
"""Tests for the fact-checker verification helper."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import verify  # noqa: E402


def test_structure_statistic() -> None:
    """Structure a statistical GDP claim with key terms and targeted queries."""
    data = verify.structure_claim("Singapore's GDP grew 4.1% in 2025")
    assert data["claim_type"] == "statistic"
    assert "Singapore" in data["key_terms"]
    assert "GDP" in data["key_terms"]
    assert "4.1%" in data["key_terms"]
    assert data["time_period"] == "2025"
    assert data["metric"] == "GDP growth rate"
    assert data["value"] == "4.1%"
    assert len(data["search_queries"]) >= 3
    assert any("official" in query.lower() for query in data["search_queries"])


def test_structure_event() -> None:
    """Structure an acquisition claim as an event."""
    data = verify.structure_claim("Acme acquired BetaCo in 2024")
    assert data["claim_type"] == "event"
    assert "Acme" in data["key_terms"]
    assert "BetaCo" in data["key_terms"]


def test_structure_quote() -> None:
    """Structure a quoted claim as a quote."""
    data = verify.structure_claim('Ada Lovelace said "the engine weaves algebraic patterns"')
    assert data["claim_type"] == "quote"
    assert any("original source" in query for query in data["search_queries"])


def test_structure_date() -> None:
    """Structure a date claim as a date."""
    data = verify.structure_claim("The iPhone launched on June 29, 2007")
    assert data["claim_type"] == "date"
    assert data["time_period"] == "June 29, 2007"


def test_report_verified() -> None:
    """Three confirming independent sources with no contradiction produce Verified."""
    claim = verify.structure_claim("Singapore's GDP grew 4.1% in 2025")
    sources = [
        {"url": "https://mti.gov.sg/report", "title": "MTI report", "passage": "GDP grew 4.1% in 2025.", "stance": "confirm", "source_type": "official", "accessed_at": "2026-07-06"},
        {"url": "https://worldbank.org/data", "title": "World Bank data", "passage": "Singapore GDP growth was 4.1%.", "stance": "confirm", "source_type": "report", "accessed_at": "2026-07-06"},
        {"url": "https://example-news.com/story", "title": "Economic story", "passage": "The economy expanded 4.1%.", "stance": "confirm", "source_type": "news", "accessed_at": "2026-07-06"},
    ]
    report = verify.build_report(claim, sources)
    assert "## Verdict: ✅ Verified" in report
    assert "Confidence: High" in report


def test_report_disputed() -> None:
    """Confirming and refuting sources produce Disputed."""
    claim = verify.structure_claim("Exampleland GDP grew 4.1% in 2025")
    sources = [
        {"url": "https://stats.example/old", "title": "Stats", "passage": "GDP grew 4.1%.", "stance": "confirm", "source_type": "official", "accessed_at": "2026-01-01"},
        {"url": "https://news.example/story", "title": "News", "passage": "GDP grew 4.1%.", "stance": "confirm", "source_type": "news", "accessed_at": "2026-01-01"},
        {"url": "https://centralbank.example/update", "title": "Update", "passage": "GDP grew 3.8%, not 4.1%.", "stance": "refute", "source_type": "report", "accessed_at": "2026-01-01"},
    ]
    report = verify.build_report(claim, sources)
    assert "## Verdict: ⚖️ Disputed" in report
    assert "GDP grew 3.8%" in report


def test_report_unverified() -> None:
    """No supplied sources produce Unverified."""
    claim = verify.structure_claim("Exampleland GDP grew 4.1% in 2025")
    report = verify.build_report(claim, [])
    assert "## Verdict: ❓ Unverified" in report
    assert "No sources supplied." in report


def test_report_likely_true() -> None:
    """One authoritative source produces Likely true."""
    claim = verify.structure_claim("Exampleland GDP grew 4.1% in 2025")
    sources = [
        {"url": "https://stats.example/release", "title": "Official release", "passage": "GDP grew 4.1%.", "stance": "confirm", "source_type": "official", "accessed_at": "2026-07-06"},
    ]
    report = verify.build_report(claim, sources)
    assert "## Verdict: ⚠️ Likely true" in report
    assert "One authoritative source" in report


def test_report_outdated() -> None:
    """Older confirming sources plus newer contradiction produce Outdated."""
    claim = verify.structure_claim("Exampleland GDP grew 4.1% in 2025")
    sources = [
        {"url": "https://stats.example/prelim", "title": "Preliminary release", "passage": "GDP grew 4.1%.", "stance": "confirm", "source_type": "official", "published_at": "2026-01-10", "accessed_at": "2026-07-06"},
        {"url": "https://centralbank.example/prelim", "title": "Preliminary note", "passage": "GDP grew 4.1%.", "stance": "confirm", "source_type": "report", "published_at": "2026-01-11", "accessed_at": "2026-07-06"},
        {"url": "https://stats.example/final", "title": "Final release", "passage": "Final GDP growth was revised to 3.9%.", "stance": "refute", "source_type": "official", "published_at": "2026-05-01", "accessed_at": "2026-07-06"},
    ]
    report = verify.build_report(claim, sources)
    assert "## Verdict: 📅 Outdated" in report
    assert "superseded" in report


def test_assess_independence() -> None:
    """Same-domain URLs are not independent; different domains pass first-pass independence."""
    same = verify.assess_urls([
        "https://example.com/a",
        "https://www.example.com/b",
        "https://news.example.com/c",
    ])
    assert same["is_independent"] is False
    assert same["independence_count"] == 1

    different = verify.assess_urls([
        "https://alpha.example/a",
        "https://beta.test/b",
        "https://gamma.org/c",
    ])
    assert different["is_independent"] is True
    assert different["independence_count"] == 3


def test_assess_wire_service() -> None:
    """URLs with the same wire-service marker are flagged as syndication risk."""
    assessment = verify.assess_urls([
        "https://localnews.example/world/reuters-market-update",
        "https://regional.example/business/reuters-market-update",
        "https://another.example/article/reuters-market-update",
    ])
    assert assessment["is_independent"] is False
    assert assessment["wire_service_clusters"] == {"reuters": 3}
    assert any("wire service" in note for note in assessment["notes"])


def test_report_command_writes_output() -> None:
    """The report command writes Markdown to the requested output path."""
    claim = verify.structure_claim("Exampleland GDP grew 4.1% in 2025")
    sources = [
        {"url": "https://stats.example/release", "title": "Official release", "passage": "GDP grew 4.1%.", "stance": "confirm", "source_type": "official", "accessed_at": "2026-07-06"},
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        claim_path = Path(tmpdir) / "claim.json"
        sources_path = Path(tmpdir) / "sources.json"
        output_path = Path(tmpdir) / "report.md"
        claim_path.write_text(json.dumps(claim), encoding="utf-8")
        sources_path.write_text(json.dumps(sources), encoding="utf-8")
        rc = verify.main(["report", "--claim", str(claim_path), "--sources", str(sources_path), "--output", str(output_path)])
        assert rc == 0
        assert "# Verification Report" in output_path.read_text(encoding="utf-8")
