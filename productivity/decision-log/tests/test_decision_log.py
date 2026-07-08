#!/usr/bin/env python3
"""Tests for the decision-log skill CLI and helpers."""

import datetime as dt
import sys
import tempfile
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import decision_log  # noqa: E402


class TempDecisionLog:
    """Temporary decisions directory fixture helper."""

    def __init__(self) -> None:
        """Create a temporary directory wrapper."""
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name)

    def cleanup(self) -> None:
        """Remove the temporary directory."""
        self._tmp.cleanup()


def make_log() -> TempDecisionLog:
    """Return a temporary decision log directory helper."""
    return TempDecisionLog()


def set_status(path: Path, status: str) -> None:
    """Set an ADR status in-place for tests."""
    text = path.read_text(encoding="utf-8")
    path.write_text(decision_log.replace_status(text, status), encoding="utf-8")


def set_next_review(path: Path, next_review: str) -> None:
    """Set an ADR next review date in-place for tests."""
    text = path.read_text(encoding="utf-8")
    updated = decision_log.re.sub(
        r"Next review:\s*\d{4}-\d{2}-\d{2}",
        f"Next review: {next_review}",
        text,
        count=1,
    )
    path.write_text(updated, encoding="utf-8")


def test_create_and_list(capsys: pytest.CaptureFixture[str]) -> None:
    """Creating three decisions yields sequential numbers and list output."""
    log = make_log()
    try:
        decision_log.create_decision("Use SQLite", decisions_dir=log.path)
        decision_log.create_decision("Use Postgres", decisions_dir=log.path)
        decision_log.create_decision("Use Object Storage", decisions_dir=log.path)

        decisions = decision_log.load_decisions(log.path)
        assert [d["adr"] for d in decisions] == ["ADR-001", "ADR-002", "ADR-003"]
        assert len(list(log.path.glob("ADR-*.md"))) == 3

        assert decision_log.main(["list", "--decisions-dir", str(log.path)]) == 0
        out = capsys.readouterr().out
        assert "ADR-001" in out
        assert "ADR-002" in out
        assert "ADR-003" in out
    finally:
        log.cleanup()


def test_supersede() -> None:
    """Superseding updates the old ADR status and appends a link."""
    log = make_log()
    try:
        first = decision_log.create_decision("Use SQLite", decisions_dir=log.path)
        second = decision_log.create_decision("Use Postgres", decisions_dir=log.path)
        decision_log.supersede_decision(1, 2, log.path)

        text = first.read_text(encoding="utf-8")
        assert "superseded by ADR-002" in text
        assert f"[ADR-002]({second.name})" in text
        assert decision_log.parse_status(text) == "superseded by ADR-002"
    finally:
        log.cleanup()


def test_search() -> None:
    """Full-text search returns matching ADRs and skips non-matches."""
    log = make_log()
    try:
        decision_log.create_decision("Use SQLite", context="Local durable database", decisions_dir=log.path)
        decision_log.create_decision("Use Queue", context="Asynchronous worker backlog", decisions_dir=log.path)

        results = decision_log.search_decisions("durable", log.path)
        assert len(results) == 1
        assert results[0][0]["adr"] == "ADR-001"
        assert "durable" in results[0][1].lower()
    finally:
        log.cleanup()


def test_due_review(capsys: pytest.CaptureFixture[str]) -> None:
    """A decision with a past review date appears in due-review output."""
    log = make_log()
    try:
        path = decision_log.create_decision("Review stale storage", decisions_dir=log.path)
        set_status(path, "accepted")
        set_next_review(path, "2000-01-01")

        assert decision_log.main(["due-review", "--decisions-dir", str(log.path)]) == 0
        out = capsys.readouterr().out
        assert "1 decisions due for review:" in out
        assert "ADR-001" in out
        assert "Review stale storage" in out
    finally:
        log.cleanup()


def test_timeline(capsys: pytest.CaptureFixture[str]) -> None:
    """Timeline output follows a superseding chain from oldest to newest."""
    log = make_log()
    try:
        for i in range(12):
            decision_log.create_decision(f"Decision {i + 1}", decisions_dir=log.path)
        decision_log.supersede_decision(1, 5, log.path)
        decision_log.supersede_decision(5, 12, log.path)

        assert decision_log.main(["timeline", "--decisions-dir", str(log.path)]) == 0
        out = capsys.readouterr().out
        assert "ADR-001 → ADR-005 → ADR-012" in out
    finally:
        log.cleanup()


def test_review_cadence() -> None:
    """Review cadence computation handles monthly, quarterly, and annually."""
    start = dt.date(2026, 1, 31)
    assert decision_log.compute_next_review(start, "monthly") == "2026-02-28"
    assert decision_log.compute_next_review(start, "quarterly") == "2026-04-30"
    assert decision_log.compute_next_review(start, "annually") == "2027-01-31"
    assert decision_log.compute_next_review(start, "on-trigger") == ""


def test_status_filter(capsys: pytest.CaptureFixture[str]) -> None:
    """Status filtering returns only decisions with the requested status family."""
    log = make_log()
    try:
        accepted = decision_log.create_decision("Accepted decision", decisions_dir=log.path)
        proposed = decision_log.create_decision("Proposed decision", decisions_dir=log.path)
        deprecated = decision_log.create_decision("Deprecated decision", decisions_dir=log.path)
        set_status(accepted, "accepted")
        set_status(proposed, "proposed")
        set_status(deprecated, "deprecated")

        assert decision_log.main(["list", "--status", "accepted", "--decisions-dir", str(log.path)]) == 0
        out = capsys.readouterr().out
        assert "ADR-001" in out
        assert "Accepted decision" in out
        assert "Proposed decision" not in out
        assert "Deprecated decision" not in out
    finally:
        log.cleanup()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
