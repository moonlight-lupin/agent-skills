#!/usr/bin/env python3
"""Tests for source-tracker scripts.

Run: python -m pytest research/source-tracker/tests/test_source_db.py -v
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import source_db  # noqa: E402
import url_health  # noqa: E402


class FakeHeadResponse:
    """Context-manager response object for mocked HEAD requests."""

    def __init__(self, status: int) -> None:
        """Store an HTTP status code."""
        self.status = status

    def __enter__(self) -> "FakeHeadResponse":
        """Return the fake response."""
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Close the fake response context."""
        return None

    def getcode(self) -> int:
        """Return the HTTP status code."""
        return self.status


def temp_db_path() -> str:
    """Create a temporary SQLite file path for a test."""
    handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    handle.close()
    return handle.name


def connect_temp() -> tuple[str, sqlite3.Connection]:
    """Create and connect to a temporary source database."""
    db_path = temp_db_path()
    return db_path, source_db.connect(db_path)


def test_add_and_search() -> None:
    """Add three sources, search by topic, and verify only matching rows return."""
    _db_path, conn = connect_temp()
    with conn:
        source_db.add_source(conn, "https://example.com/alpha", "topic-a", "Alpha", "first", "web")
        source_db.add_source(conn, "https://example.com/beta", "topic-a", "Beta", "second", "pdf")
        source_db.add_source(conn, "https://example.com/gamma", "topic-b", "Gamma", "third", "news")

        results = source_db.search_sources(conn, "topic-a")
        assert len(results) == 2
        assert {row["title"] for row in results} == {"Alpha", "Beta"}
        assert all(row["topic"] == "topic-a" for row in results)

        pdf_results = source_db.search_sources(conn, "topic-a", source_type="pdf", verified=True)
        assert len(pdf_results) == 1
        assert pdf_results[0]["title"] == "Beta"


def test_dedup() -> None:
    """Add http/www/trailing-slash variants and verify dedup merges them."""
    _db_path, conn = connect_temp()
    with conn:
        source_db.add_source(conn, "http://example.com", "dedup-topic", "HTTP", "note one", "web")
        source_db.add_source(conn, "https://www.example.com/", "dedup-topic", "HTTPS", "note two", "web")
        before = source_db.search_sources(conn, "dedup-topic")
        assert len(before) == 2

        summary = source_db.deduplicate_sources(conn)
        after = source_db.search_sources(conn, "dedup-topic")

        assert summary["merged_groups"] == 1
        assert summary["removed_rows"] == 1
        assert len(after) == 1
        assert "note one" in after[0]["notes"]
        assert "note two" in after[0]["notes"]


def test_export_markdown() -> None:
    """Export sources as Markdown and verify bibliography formatting."""
    _db_path, conn = connect_temp()
    with conn:
        source_db.add_source(conn, "https://example.com/report", "exports", "Report Title", "useful note", "report")
        output = source_db.export_sources(conn, "exports", "markdown")

    assert "## exports" in output
    assert "- [Report Title](https://example.com/report) — useful note (" in output


def test_export_bibtex() -> None:
    """Export sources as BibTeX and verify required fields."""
    _db_path, conn = connect_temp()
    with conn:
        source_db.add_source(conn, "https://example.com/report", "exports", "Report Title", "useful note", "report")
        output = source_db.export_sources(conn, "exports", "bibtex")

    assert "@misc{" in output
    assert "title={Report Title}" in output
    assert "url={https://example.com/report}" in output
    assert "note={useful note}" in output
    assert "urldate={" in output


def test_stats() -> None:
    """Add sources across topics/types and verify stats counts."""
    _db_path, conn = connect_temp()
    with conn:
        source_db.add_source(conn, "https://example.com/a", "topic-a", "A", "", "web")
        source_db.add_source(conn, "https://example.com/b", "topic-a", "B", "", "pdf")
        source_db.add_source(conn, "https://example.com/c", "topic-b", "C", "", "pdf")
        conn.execute("UPDATE sources SET verified = 0 WHERE url = ?", ("https://example.com/c",))
        conn.commit()

        data = source_db.stats(conn)

    assert data["total"] == 3
    assert data["by_topic"] == {"topic-a": 2, "topic-b": 1}
    assert data["by_type"] == {"pdf": 2, "web": 1}
    assert data["by_verification"] == {"verified": 2, "unverified": 1}


def test_url_normalization() -> None:
    """Verify fragment stripping, lowercase host/scheme, and trailing slash rules."""
    assert source_db.canonicalize_url("HTTPS://WWW.Example.COM/path/#frag") == "https://www.example.com/path"
    assert source_db.canonicalize_url("https://Example.com/path/") == "https://example.com/path"
    assert source_db.canonicalize_url("https://Example.com/") == "https://example.com/"
    assert source_db.dedup_key("HTTPS://WWW.Example.COM/path/#frag") == "//example.com/path"
    assert source_db.dedup_key("http://example.com/") == source_db.dedup_key("https://www.example.com/")


def test_health_check() -> None:
    """Mock URL requests and verify url_health updates verified flags."""
    db_path, conn = connect_temp()
    with conn:
        source_db.add_source(conn, "https://alive.example.com", "health", "Alive", "", "web")
        source_db.add_source(conn, "https://dead.example.com", "health", "Dead", "", "web")

    def fake_urlopen(request: object, timeout: int = 10) -> FakeHeadResponse:
        url = getattr(request, "full_url", "")
        if "alive" in url:
            return FakeHeadResponse(204)
        return FakeHeadResponse(404)

    with patch("url_health.urllib.request.urlopen", side_effect=fake_urlopen):
        with url_health.connect(db_path) as health_conn:
            summary = url_health.check_sources(health_conn, stale_days=0, timeout=1, batch_size=10)

    with source_db.connect(db_path) as check_conn:
        rows = {row["url"]: row for row in source_db.search_sources(check_conn, "health")}

    assert summary == {"checked": 2, "alive": 1, "dead": 1}
    assert rows["https://alive.example.com/"]["verified"] is True
    assert rows["https://dead.example.com/"]["verified"] is False
    assert rows["https://alive.example.com/"]["last_checked"] is not None


def test_cli_json_search_roundtrip() -> None:
    """Exercise CLI-style JSON output generation for search results."""
    _db_path, conn = connect_temp()
    with conn:
        source_db.add_source(conn, "https://example.com/json", "json-topic", "JSON", "note", "api")
        rendered = json.dumps(source_db.search_sources(conn, "json-topic"), sort_keys=True)
    assert '"source_type": "api"' in rendered


def test_csv_export_header() -> None:
    """Verify CSV export uses the documented compact field order."""
    _db_path, conn = connect_temp()
    with conn:
        source_db.add_source(conn, "https://example.com/csv", "csv-topic", "CSV", "note", "dataset")
        rendered = source_db.export_sources(conn, "csv-topic", "csv")
    rows = list(csv.reader(rendered.splitlines()))
    assert rows[0] == ["id", "url", "title", "topic", "source_type", "accessed_at", "notes", "verified", "last_checked"]
    assert rows[1][4] == "dataset"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
