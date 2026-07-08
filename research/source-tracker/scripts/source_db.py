#!/usr/bin/env python3
"""Persistent source tracker CLI for research citations.

Stores cited URLs in SQLite, performs URL variant deduplication, and exports
bibliographies in Markdown, BibTeX, CSV, or JSON. The tool is intentionally
stdlib-only so it can be copied into any agent workflow.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import html.parser
import io
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Optional, Sequence

DEFAULT_DB_PATH = "./sources.db"
SOURCE_TYPES = ("web", "pdf", "api", "dataset", "book", "news", "report")
EXPORT_FORMATS = ("markdown", "bibtex", "csv", "json")

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


class TitleParser(html.parser.HTMLParser):
    """Small HTML parser that captures the first <title> element."""

    def __init__(self) -> None:
        """Initialise title parsing state."""
        super().__init__()
        self.in_title = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        """Record entry into a title tag."""
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        """Record exit from a title tag."""
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        """Collect title text while inside a title tag."""
        if self.in_title:
            self.parts.append(data)

    def title(self) -> Optional[str]:
        """Return the parsed title text, or None if no title was found."""
        text = " ".join(part.strip() for part in self.parts if part.strip())
        text = re.sub(r"\s+", " ", text).strip()
        return text or None


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


def canonicalize_url(url: str) -> str:
    """Normalise a URL for storage while preserving its scheme and www host.

    Rules: lowercase scheme and host, strip fragments, strip default ports, and
    strip a trailing slash from non-root paths. Query strings are preserved.
    """
    parsed = urllib.parse.urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"URL must include scheme and host: {url!r}")
    if parsed.scheme.lower() not in ("http", "https"):
        # Only web URLs belong in the DB — and fetch_title/url_health would
        # otherwise urlopen() whatever scheme lands here (file://, ftp://, …).
        raise ValueError(f"Only http/https URLs are supported: {url!r}")

    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError(f"URL must include host: {url!r}")

    port = parsed.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    else:
        netloc = host

    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    return urllib.parse.urlunsplit((scheme, netloc, path, parsed.query, ""))


def dedup_key(url: str) -> str:
    """Return a comparison key that collapses common URL variants.

    The key ignores http vs https, strips a leading www. host prefix, strips
    fragments, lowercases host/path-insensitive parts, and strips trailing slash
    except for root.
    """
    canonical = canonicalize_url(url)
    parsed = urllib.parse.urlsplit(canonical)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    port = parsed.port
    netloc = f"{host}:{port}" if port else host
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urllib.parse.urlunsplit(("", netloc, path, parsed.query, ""))


def fetch_title(url: str, timeout: int = 10) -> Optional[str]:
    """Fetch a URL and parse the first HTML <title> tag.

    Any network, decoding, or parsing failure returns None; title lookup should
    never block adding a source record.
    """
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "source-tracker/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(262_144)
            charset = response.headers.get_content_charset() if response.headers else None
            text = raw.decode(charset or "utf-8", errors="replace")
    except Exception:
        return None

    parser = TitleParser()
    try:
        parser.feed(text)
    except Exception:
        return None
    return parser.title()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Convert a SQLite row into a plain JSON-serialisable dictionary."""
    data = dict(row)
    if "verified" in data and data["verified"] is not None:
        data["verified"] = bool(data["verified"])
    return data


def parse_bool(value: str) -> bool:
    """Parse a permissive boolean CLI value."""
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"expected boolean, got {value!r}")


def get_existing_by_url(conn: sqlite3.Connection, canonical_url: str) -> Optional[dict[str, Any]]:
    """Return an existing source with the exact canonical URL, if any."""
    row = conn.execute("SELECT * FROM sources WHERE url = ?", (canonical_url,)).fetchone()
    return row_to_dict(row) if row else None


def add_source(
    conn: sqlite3.Connection,
    url: str,
    topic: str,
    title: Optional[str] = None,
    notes: Optional[str] = None,
    source_type: str = "web",
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    """Add a source if its canonical URL is not already present.

    Returns the source object plus an ``inserted`` boolean flag.
    """
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of: {', '.join(SOURCE_TYPES)}")

    canonical_url = canonicalize_url(url)
    existing = get_existing_by_url(conn, canonical_url)
    if existing:
        existing["inserted"] = False
        return existing

    final_title = title if title is not None else fetch_title(canonical_url)
    accessed_at = _dt.date.today().isoformat()
    normalized = canonical_url
    cur = conn.execute(
        """
        INSERT INTO sources
            (url, url_normalized, title, topic, source_type, accessed_at, notes, verified, last_checked, session_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, NULL, ?)
        """,
        (canonical_url, normalized, final_title, topic, source_type, accessed_at, notes, session_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM sources WHERE id = ?", (cur.lastrowid,)).fetchone()
    data = row_to_dict(row)
    data["inserted"] = True
    return data


def search_sources(
    conn: sqlite3.Connection,
    topic: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    source_type: Optional[str] = None,
    verified: Optional[bool] = None,
) -> list[dict[str, Any]]:
    """Search sources by topic with optional date, type, and verification filters."""
    clauses = ["topic = ?"]
    params: list[Any] = [topic]
    if from_date:
        clauses.append("accessed_at >= ?")
        params.append(from_date)
    if to_date:
        clauses.append("accessed_at <= ?")
        params.append(to_date)
    if source_type:
        clauses.append("source_type = ?")
        params.append(source_type)
    if verified is not None:
        clauses.append("verified = ?")
        params.append(1 if verified else 0)

    sql = "SELECT * FROM sources WHERE " + " AND ".join(clauses) + " ORDER BY topic, accessed_at, id"
    return [row_to_dict(row) for row in conn.execute(sql, params).fetchall()]


def combine_text(values: Iterable[Optional[str]]) -> Optional[str]:
    """Combine non-empty text values while preserving order and removing exact duplicates."""
    seen: set[str] = set()
    parts: list[str] = []
    for value in values:
        text = (value or "").strip()
        if text and text not in seen:
            seen.add(text)
            parts.append(text)
    return "\n\n".join(parts) if parts else None


def latest_date(values: Iterable[Optional[str]]) -> Optional[str]:
    """Return the latest non-empty ISO date/date-time string from an iterable."""
    present = [value for value in values if value]
    return max(present) if present else None


def deduplicate_sources(conn: sqlite3.Connection) -> dict[str, Any]:
    """Merge source rows that differ only by common URL variants.

    Variants include http/https, leading www., fragments, and trailing slash.
    The survivor keeps the earliest ``accessed_at``; notes are combined.
    """
    rows = conn.execute("SELECT * FROM sources ORDER BY accessed_at, id").fetchall()
    groups: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        groups.setdefault(dedup_key(row["url"]), []).append(row)

    merged_groups = 0
    removed_ids: list[int] = []
    for group_rows in groups.values():
        if len(group_rows) < 2:
            continue
        ordered = sorted(group_rows, key=lambda r: (r["accessed_at"], r["id"]))
        survivor = ordered[0]
        duplicates = ordered[1:]
        survivor_id = int(survivor["id"])
        merged_groups += 1
        removed_ids.extend(int(row["id"]) for row in duplicates)

        title = survivor["title"] or next((row["title"] for row in ordered if row["title"]), None)
        notes = combine_text(row["notes"] for row in ordered)
        verified = 1 if any(int(row["verified"] or 0) for row in ordered) else 0
        last_checked = latest_date(row["last_checked"] for row in ordered)
        session_id = combine_text(row["session_id"] for row in ordered)
        url_normalized = survivor["url_normalized"] or canonicalize_url(survivor["url"])

        conn.execute(
            """
            UPDATE sources
               SET title = ?, notes = ?, verified = ?, last_checked = ?, session_id = ?, url_normalized = ?
             WHERE id = ?
            """,
            (title, notes, verified, last_checked, session_id, url_normalized, survivor_id),
        )
        conn.executemany("DELETE FROM sources WHERE id = ?", [(int(row["id"]),) for row in duplicates])

    conn.commit()
    return {"merged_groups": merged_groups, "removed_rows": len(removed_ids), "removed_ids": removed_ids}


def list_sources_for_export(conn: sqlite3.Connection, topic: str) -> list[dict[str, Any]]:
    """Return topic-filtered sources sorted for bibliography output."""
    rows = conn.execute(
        "SELECT * FROM sources WHERE topic = ? ORDER BY topic, COALESCE(title, url), accessed_at, id",
        (topic,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def bibtex_escape(value: Optional[str]) -> str:
    """Escape a string for conservative BibTeX field output."""
    text = value or ""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def bibtex_key(source: dict[str, Any]) -> str:
    """Create a stable BibTeX key from source id and title/url slug."""
    seed = source.get("title") or source.get("url") or "source"
    slug = re.sub(r"[^A-Za-z0-9]+", "_", str(seed)).strip("_").lower()[:32]
    return f"source{source.get('id')}_{slug or 'untitled'}"


def export_markdown(sources: Sequence[dict[str, Any]]) -> str:
    """Render sources as a Markdown bibliography."""
    lines: list[str] = []
    current_topic: Optional[str] = None
    for source in sources:
        topic = str(source.get("topic") or "untagged")
        if topic != current_topic:
            if lines:
                lines.append("")
            lines.append(f"## {topic}")
            current_topic = topic
        title = source.get("title") or source.get("url") or "Untitled source"
        notes = source.get("notes") or "No notes"
        accessed_at = source.get("accessed_at") or "unknown date"
        lines.append(f"- [{title}]({source['url']}) — {notes} ({accessed_at})")
    return "\n".join(lines) + ("\n" if lines else "")


def export_bibtex(sources: Sequence[dict[str, Any]]) -> str:
    """Render sources as BibTeX @misc entries."""
    entries: list[str] = []
    for source in sources:
        title = bibtex_escape(source.get("title") or source.get("url") or "Untitled source")
        url = bibtex_escape(source.get("url"))
        note = bibtex_escape(source.get("notes") or f"Topic: {source.get('topic', '')}")
        urldate = bibtex_escape(source.get("accessed_at"))
        entries.append(
            "@misc{" + bibtex_key(source) + ",\n"
            f"  title={{{title}}},\n"
            f"  url={{{url}}},\n"
            f"  note={{{note}}},\n"
            f"  urldate={{{urldate}}}\n"
            "}"
        )
    return "\n\n".join(entries) + ("\n" if entries else "")


def export_csv(sources: Sequence[dict[str, Any]]) -> str:
    """Render sources as CSV with the documented field order."""
    fields = ["id", "url", "title", "topic", "source_type", "accessed_at", "notes", "verified", "last_checked"]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for source in sources:
        row = dict(source)
        row["verified"] = 1 if source.get("verified") else 0
        writer.writerow(row)
    return buffer.getvalue()


def export_json(sources: Sequence[dict[str, Any]]) -> str:
    """Render sources as pretty-printed JSON."""
    return json.dumps(list(sources), indent=2, sort_keys=True) + "\n"


def export_sources(conn: sqlite3.Connection, topic: str, output_format: str) -> str:
    """Export sources for a topic in the requested format."""
    sources = list_sources_for_export(conn, topic)
    if output_format == "markdown":
        return export_markdown(sources)
    if output_format == "bibtex":
        return export_bibtex(sources)
    if output_format == "csv":
        return export_csv(sources)
    if output_format == "json":
        return export_json(sources)
    raise ValueError(f"unsupported export format: {output_format}")


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return counts by topic, source type, and verification status."""
    by_topic = {row["topic"]: row["count"] for row in conn.execute("SELECT topic, COUNT(*) AS count FROM sources GROUP BY topic ORDER BY topic")}
    by_type = {row["source_type"]: row["count"] for row in conn.execute("SELECT source_type, COUNT(*) AS count FROM sources GROUP BY source_type ORDER BY source_type")}
    verification = {"verified": 0, "unverified": 0}
    for row in conn.execute("SELECT verified, COUNT(*) AS count FROM sources GROUP BY verified"):
        verification["verified" if int(row["verified"] or 0) else "unverified"] = row["count"]
    total = conn.execute("SELECT COUNT(*) AS count FROM sources").fetchone()["count"]
    return {"total": total, "by_topic": by_topic, "by_type": by_type, "by_verification": verification}


def list_topics(conn: sqlite3.Connection) -> list[str]:
    """Return distinct topic names sorted alphabetically."""
    return [row["topic"] for row in conn.execute("SELECT DISTINCT topic FROM sources ORDER BY topic")]


def write_or_print(text: str, output: Optional[str]) -> None:
    """Write text to an output file or print it to stdout."""
    if output:
        with open(output, "w", encoding="utf-8", newline="" if output.endswith(".csv") else None) as handle:
            handle.write(text)
    else:
        print(text, end="")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(description="Persistent citation database for research source URLs.")
    parser.add_argument(
        "--db-path",
        dest="db_path_global",
        help="SQLite database path (default: SOURCE_TRACKER_DB or ./sources.db). May also be passed after a subcommand.",
    )
    db_parent = argparse.ArgumentParser(add_help=False)
    db_parent.add_argument("--db-path", dest="db_path", help="SQLite database path (default: SOURCE_TRACKER_DB or ./sources.db)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    add = subparsers.add_parser("add", parents=[db_parent], help="Add a cited URL to the source database.")
    add.add_argument("--url", required=True, help="Source URL to add.")
    add.add_argument("--topic", required=True, help="Topic tag for this source.")
    add.add_argument("--title", help="Source title. If omitted, the tool tries to fetch the page title.")
    add.add_argument("--notes", help="Short notes describing why the source matters.")
    add.add_argument("--type", default="web", choices=SOURCE_TYPES, dest="source_type", help="Source type.")
    add.add_argument("--session-id", help="Optional research session identifier.")

    search = subparsers.add_parser("search", parents=[db_parent], help="Search sources by topic and filters.")
    search.add_argument("--topic", required=True, help="Topic tag to search.")
    search.add_argument("--from", dest="from_date", help="Earliest accessed_at date, ISO format YYYY-MM-DD.")
    search.add_argument("--to", dest="to_date", help="Latest accessed_at date, ISO format YYYY-MM-DD.")
    search.add_argument("--type", choices=SOURCE_TYPES, dest="source_type", help="Filter by source type.")
    search.add_argument("--verified", type=parse_bool, help="Filter by verification status (true/false).")

    subparsers.add_parser("dedup", parents=[db_parent], help="Merge URL variants such as http/https, www, and trailing slash.")

    export = subparsers.add_parser("export", parents=[db_parent], help="Export a bibliography for a topic.")
    export.add_argument("--topic", required=True, help="Topic tag to export.")
    export.add_argument("--format", required=True, choices=EXPORT_FORMATS, dest="output_format", help="Export format.")
    export.add_argument("--output", help="Optional output file path. If omitted, writes to stdout.")

    subparsers.add_parser("stats", parents=[db_parent], help="Show counts by topic, type, and verification status.")
    subparsers.add_parser("list-topics", parents=[db_parent], help="List distinct topic tags.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the source tracker CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    db_path = resolve_db_path(getattr(args, "db_path", None) or getattr(args, "db_path_global", None))

    try:
        with connect(db_path) as conn:
            if args.command == "add":
                result = add_source(conn, args.url, args.topic, args.title, args.notes, args.source_type, args.session_id)
                print(json.dumps(result, indent=2, sort_keys=True))
            elif args.command == "search":
                result = search_sources(conn, args.topic, args.from_date, args.to_date, args.source_type, args.verified)
                print(json.dumps(result, indent=2, sort_keys=True))
            elif args.command == "dedup":
                print(json.dumps(deduplicate_sources(conn), indent=2, sort_keys=True))
            elif args.command == "export":
                text = export_sources(conn, args.topic, args.output_format)
                write_or_print(text, args.output)
            elif args.command == "stats":
                print(json.dumps(stats(conn), indent=2, sort_keys=True))
            elif args.command == "list-topics":
                print(json.dumps(list_topics(conn), indent=2, sort_keys=True))
            else:
                parser.error(f"unknown command {args.command!r}")
    except ValueError as exc:
        parser.error(str(exc))
    except sqlite3.Error as exc:
        print(f"database error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
