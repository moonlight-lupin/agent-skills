#!/usr/bin/env python3
"""Tests for the scheduled-summary CLI."""

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import summarize  # noqa: E402

NOW = "2026-07-06T22:30:00Z"
RECENT = "2026-07-06T10:00:00Z"
OLD = "2026-06-20T10:00:00Z"


class MockSources:
    """Temporary mock data sources for digest tests."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.sessions_db = self.root / "sessions.sqlite"
        self.cron_dir = self.root / "cron"
        self.memory_dir = self.root / "memory"
        self.log_file = self.root / "agent.log"
        self.decisions_dir = self.root / "decisions"
        self.cron_dir.mkdir()
        self.memory_dir.mkdir()
        self.decisions_dir.mkdir()
        self._make_sessions()
        self._make_cron()
        self._make_memory()
        self._make_log()
        self._make_decisions()

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def args(self, *extra: str) -> list[str]:
        base = [
            "generate",
            "--since",
            "24h",
            "--now",
            NOW,
            "--sessions-db",
            str(self.sessions_db),
            "--cron-dir",
            str(self.cron_dir),
            "--memory-dir",
            str(self.memory_dir),
            "--log-file",
            str(self.log_file),
            "--decisions-dir",
            str(self.decisions_dir),
        ]
        return base + list(extra)

    def _make_sessions(self) -> None:
        conn = sqlite3.connect(self.sessions_db)
        conn.execute(
            "CREATE TABLE sessions (id TEXT PRIMARY KEY, title TEXT, created_at TEXT, ended_at TEXT, status TEXT)"
        )
        conn.execute(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, created_at TEXT, content TEXT)"
        )
        conn.executemany(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
            [
                ("s1", "agent_skills repo expansion", RECENT, RECENT, "completed"),
                ("s2", "NAS docker cleanup", RECENT, RECENT, "completed"),
                ("s3", "old archive cleanup", OLD, OLD, "completed"),
            ],
        )
        conn.executemany(
            "INSERT INTO messages (session_id, created_at, content) VALUES (?, ?, ?)",
            [
                ("s2", RECENT, "TODO: recheck tunnel config"),
                ("s3", OLD, "TODO: old ignored task"),
            ],
        )
        conn.commit()
        conn.close()

    def _make_cron(self) -> None:
        (self.cron_dir / "backup.txt").write_text(
            "job: backup\nfinished_at: %s\nstatus: success\n" % RECENT,
            encoding="utf-8",
        )
        (self.cron_dir / "news-monitoring.txt").write_text(
            "job: news-monitoring\nfinished_at: %s\nstatus: failed\nerror: timeout\n" % RECENT,
            encoding="utf-8",
        )
        overdue = self.cron_dir / "weekly-review.txt"
        overdue.write_text(
            "job: weekly-review\nstatus: overdue\nlast ran 9 days ago\n",
            encoding="utf-8",
        )
        old_epoch = 1_750_000_000  # ~2025-06 — genuinely before the mocked NOW (2026-07)
        os.utime(overdue, (old_epoch, old_epoch))

    def _make_memory(self) -> None:
        (self.memory_dir / "new.json").write_text(
            json.dumps({"timestamp": RECENT, "action": "new", "memory": "new project preference"}),
            encoding="utf-8",
        )
        (self.memory_dir / "updated.json").write_text(
            json.dumps({"updated_at": RECENT, "action": "updated", "fact": "VM RAM 6GB"}),
            encoding="utf-8",
        )
        (self.memory_dir / "old.json").write_text(
            json.dumps({"timestamp": OLD, "action": "new", "memory": "old memory"}),
            encoding="utf-8",
        )

    def _make_log(self) -> None:
        self.log_file.write_text(
            "\n".join(
                [
                    '{"timestamp":"%s","tool":"terminal","status":"success"}' % RECENT,
                    '{"timestamp":"%s","tool":"terminal","status":"success"}' % RECENT,
                    '{"timestamp":"%s","tool":"web_search","error":"rate limit"}' % RECENT,
                    "%s tool=read_file status=success" % OLD,
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def _make_decisions(self) -> None:
        (self.decisions_dir / "ADR-001-use-sqlite.md").write_text(
            "# Use SQLite for source tracker\n\n## Status\naccepted\n\n## Review\nNext review: 2026-07-06\n",
            encoding="utf-8",
        )
        (self.decisions_dir / "ADR-002-newer.md").write_text(
            "# Future decision\n\n## Status\naccepted\n\n## Review\nNext review: 2026-12-01\n",
            encoding="utf-8",
        )


def make_sources() -> MockSources:
    return MockSources()


def test_generate_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    """Generate Markdown with mock data sources."""
    src = make_sources()
    try:
        assert summarize.main(src.args()) == 0
        out = capsys.readouterr().out
        assert "## 📋 Activity Digest — Last 24h" in out
        assert "### Sessions" in out
        assert "2 sessions completed" in out
        assert '"agent_skills repo expansion"' in out
        assert "news-monitoring failed" in out
        assert "weekly-review overdue" in out
        assert "2 new memories" not in out
        assert "1 new memory saved" in out
        assert 'Updated: "VM RAM 6GB"' in out
        assert "terminal (2)" in out
        assert "Errors: 1 (1 rate limit)" in out
        assert "1 decision due for review" in out
        assert 'TODO from NAS docker cleanup: "recheck tunnel config"' in out
    finally:
        src.cleanup()


def test_generate_json(capsys: pytest.CaptureFixture[str]) -> None:
    """Generate JSON with mock data sources."""
    src = make_sources()
    try:
        assert summarize.main(src.args("--format", "json")) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["template_mode"] is False
        assert data["sessions"]["completed"] == 2
        assert data["cron"]["success"] == 1
        assert data["cron"]["failed"][0]["job"] == "news-monitoring"
        assert data["memory"]["new"] == 1
        assert data["memory"]["updated"] == 1
        assert data["tools"]["tools"][0] == ["terminal", 2]
        assert len(data["outstanding"]["decisions_due"]) == 1
    finally:
        src.cleanup()


def test_generate_text(capsys: pytest.CaptureFixture[str]) -> None:
    """Generate plain text with mock data sources."""
    src = make_sources()
    try:
        assert summarize.main(src.args("--format", "text")) == 0
        out = capsys.readouterr().out
        assert "Activity Digest - Last 24h" in out
        assert "Sessions: 2 completed, 2 started" in out
        assert "Cron Jobs: 1 succeeded, 1 failed, 1 overdue" in out
        assert "Memory: 1 new, 1 updated" in out
        assert "Tool Usage: 3 calls" in out
        assert "Outstanding: 1 decisions due, 1 TODOs" in out
    finally:
        src.cleanup()


def test_section_filter(capsys: pytest.CaptureFixture[str]) -> None:
    """Including only sessions excludes all other sections."""
    src = make_sources()
    try:
        assert summarize.main(src.args("--sections", "sessions")) == 0
        out = capsys.readouterr().out
        assert "### Sessions" in out
        assert "### Cron Jobs" not in out
        assert "### Memory" not in out
        assert "### Tool Usage" not in out
        assert "### Outstanding" not in out
    finally:
        src.cleanup()


def test_since_window(capsys: pytest.CaptureFixture[str]) -> None:
    """The since window filters old sessions, memories, and log tool calls."""
    src = make_sources()
    try:
        assert summarize.main(src.args("--format", "json")) == 0
        data = json.loads(capsys.readouterr().out)
        assert "old archive cleanup" not in data["sessions"]["topics"]
        assert data["memory"]["new"] == 1
        assert [tool for tool, _ in data["tools"]["tools"]] == ["terminal", "web_search"]
        assert all(todo["item"] != "old ignored task" for todo in data["outstanding"]["todos"])
    finally:
        src.cleanup()


def test_init_config(capsys: pytest.CaptureFixture[str]) -> None:
    """Init writes a JSON config file with all source keys."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "summary-config.json"
        assert summarize.main(["init", "--output", str(path)]) == 0
        out = capsys.readouterr().out
        assert "Wrote config template" in out
        data = json.loads(path.read_text(encoding="utf-8"))
        for key in ["sessions_db", "cron_dir", "memory_dir", "log_file", "decisions_dir"]:
            assert key in data
        assert data["default_since"] == "24h"
        assert "outstanding" in data["sections"]


def test_empty_sources(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """With no configured data sources, template placeholders are emitted."""
    for env in summarize.SOURCE_ENV.values():
        monkeypatch.delenv(env, raising=False)
    assert summarize.main(["generate", "--since", "24h", "--now", NOW]) == 0
    out = capsys.readouterr().out
    assert "Template mode" in out
    assert "_fill in recent session titles_" in out
    assert "Generated at 2026-07-06T22:30:00Z" in out


def test_cron_status() -> None:
    """Cron parsing identifies succeeded, failed, and overdue jobs."""
    src = make_sources()
    try:
        since_dt = summarize.parse_datetime(NOW) - summarize.parse_since("24h")
        result = summarize.load_cron_status(str(src.cron_dir), since_dt)
        assert result["success"] == 1
        assert result["failed"] == [{"job": "news-monitoring", "reason": "failed"}]
        assert result["overdue"] == [{"job": "weekly-review", "detail": "last ran 9 days ago"}]
    finally:
        src.cleanup()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
