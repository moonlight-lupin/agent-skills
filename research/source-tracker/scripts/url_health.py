#!/usr/bin/env python3
"""Cron-compatible link health checker for source-tracker databases."""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional, Sequence

DEFAULT_DB_PATH = "./sources.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    url_normalized TEXT NOT NULL,
    title TEXT,
    topic TEXT NOT NULL,
    source_type TEXT DEFAULT 'web',
    accessed_at TEXT NOT NULL,
    notes TEXT,
    verified INTEGER DEFAULT 1,
    last_checked TEXT,
    session_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_topic ON sources(topic);
CREATE INDEX IF NOT EXISTS idx_normalized ON sources(url_normalized);
"""


def resolve_db_path(db_path: Optional[str]) -> str:
    """Resolve DB path from CLI option, environment, or default."""
    return db_path or os.environ.get("SOURCE_TRACKER_DB") or DEFAULT_DB_PATH


def connect(db_path: str) -> sqlite3.Connection:
    """Open a SQLite connection and ensure the source schema exists."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def is_alive(url: str, timeout: int) -> bool:
    """Return True when a HEAD request receives HTTP 200-399.

    Servers that reject HEAD (405/501) get one GET retry so they aren't
    misreported as dead. Non-web schemes are never probed.
    """
    if urllib.parse.urlsplit(url).scheme.lower() not in ("http", "https"):
        return False
    for method in ("HEAD", "GET"):
        try:
            request = urllib.request.Request(url, method=method, headers={"User-Agent": "source-tracker/1.0"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                code = getattr(response, "status", None)
                if code is None:
                    code = response.getcode()
                return 200 <= int(code) <= 399
        except urllib.error.HTTPError as exc:
            if method == "HEAD" and int(exc.code) in (405, 501):
                continue
            return 200 <= int(exc.code) <= 399
        except Exception:
            return False
    return False


def stale_cutoff(stale_days: int) -> str:
    """Return the ISO date before which link checks are considered stale."""
    return (_dt.date.today() - _dt.timedelta(days=stale_days)).isoformat()


def select_stale_sources(conn: sqlite3.Connection, stale_days: int, batch_size: int) -> list[sqlite3.Row]:
    """Select sources that have never been checked or are older than the cutoff."""
    cutoff = stale_cutoff(stale_days)
    return conn.execute(
        """
        SELECT id, url
          FROM sources
         WHERE last_checked IS NULL OR last_checked < ?
         ORDER BY COALESCE(last_checked, ''), id
         LIMIT ?
        """,
        (cutoff, batch_size),
    ).fetchall()


def check_sources(conn: sqlite3.Connection, stale_days: int = 30, timeout: int = 10, batch_size: int = 50) -> dict[str, int]:
    """Check a batch of stale sources and update verified/last_checked fields."""
    rows = select_stale_sources(conn, stale_days, batch_size)
    checked = alive = dead = 0
    today = _dt.date.today().isoformat()
    for row in rows:
        ok = is_alive(row["url"], timeout)
        conn.execute(
            "UPDATE sources SET verified = ?, last_checked = ? WHERE id = ?",
            (1 if ok else 0, today, int(row["id"])),
        )
        checked += 1
        if ok:
            alive += 1
        else:
            dead += 1
    conn.commit()
    return {"checked": checked, "alive": alive, "dead": dead}


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Check stale URLs in a source-tracker SQLite database.")
    parser.add_argument("--db-path", help="SQLite database path (default: SOURCE_TRACKER_DB or ./sources.db)")
    parser.add_argument("--stale-days", type=int, default=30, help="Only check URLs not checked in this many days (default: 30).")
    parser.add_argument("--timeout", type=int, default=10, help="HTTP HEAD timeout per URL in seconds (default: 10).")
    parser.add_argument("--batch-size", type=int, default=50, help="Maximum URLs to check per run (default: 50).")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the URL health checker and always exit successfully."""
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = resolve_db_path(args.db_path)
    try:
        with connect(db_path) as conn:
            result = check_sources(conn, args.stale_days, args.timeout, args.batch_size)
        print(f"Checked {result['checked']} URLs: {result['alive']} alive, {result['dead']} dead")
    except Exception as exc:
        print(f"Checked 0 URLs: 0 alive, 0 dead", file=sys.stdout)
        print(f"warning: health check failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
