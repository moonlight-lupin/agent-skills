#!/usr/bin/env python3
"""Cron-compatible review reminder for ADR decision logs."""

import argparse
import datetime as dt
import glob
import os
import re
from pathlib import Path
from typing import Any


DEFAULT_DECISIONS_DIR = "./decisions"


def resolve_decisions_dir(value: str | None = None) -> Path:
    """Return the decisions directory from an argument, environment, or default."""
    chosen = value or os.environ.get("DECISIONS_DIR") or DEFAULT_DECISIONS_DIR
    return Path(chosen).expanduser()


def adr_glob(decisions_dir: Path) -> list[Path]:
    """Return all ADR Markdown files in numeric order."""
    paths = [Path(p) for p in glob.glob(str(decisions_dir / "ADR-[0-9][0-9][0-9]-*.md"))]
    return sorted(paths, key=lambda p: p.name)


def section_after_heading(text: str, heading: str) -> str:
    """Return the body text immediately following a Markdown level-2 heading."""
    pattern = rf"^##\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return match.group("body").strip() if match else ""


def parse_status(text: str) -> str:
    """Parse the status value from an ADR document."""
    body = section_after_heading(text, "Status")
    return next((line.strip().lower() for line in body.splitlines() if line.strip()), "unknown")


def parse_title(text: str, path: Path) -> str:
    """Parse the ADR title from the H1 heading, falling back to the filename."""
    match = re.search(r"^#\s+(ADR-\d{3}):\s+(.+?)\s*$", text, flags=re.MULTILINE)
    if match:
        return f"{match.group(1)}: {match.group(2).strip()}"
    return path.stem


def parse_next_review(text: str) -> str:
    """Parse the next review date from the Review section."""
    review = section_after_heading(text, "Review")
    match = re.search(r"Next review:\s*(\d{4}-\d{2}-\d{2})", review, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def parse_decision(path: Path) -> dict[str, Any]:
    """Parse the fields needed for review reminders from one ADR file."""
    text = path.read_text(encoding="utf-8")
    return {
        "title": parse_title(text, path),
        "status": parse_status(text),
        "next_review": parse_next_review(text),
        "path": path,
    }


def due_accepted_decisions(decisions_dir: Path, today: dt.date | None = None) -> list[dict[str, Any]]:
    """Return accepted ADRs with next review date on or before today."""
    current = today or dt.date.today()
    due: list[dict[str, Any]] = []
    for path in adr_glob(decisions_dir):
        decision = parse_decision(path)
        if decision["status"] != "accepted":
            continue
        next_review = decision["next_review"]
        if not next_review:
            continue
        try:
            review_date = dt.date.fromisoformat(next_review)
        except ValueError:
            continue
        if review_date <= current:
            due.append(decision)
    return due


def format_due_message(decisions: list[dict[str, Any]]) -> str:
    """Format due decisions for delivery by a cron scheduler or messaging platform."""
    lines = [f"{len(decisions)} decisions due for review:"]
    for decision in decisions:
        lines.append(f"- {decision['title']} — next review {decision['next_review']} — {decision['path']}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Build and return the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Print accepted ADRs that are due for review. Silent when none are due.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--decisions-dir", help="directory holding ADR Markdown files")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the review checker and always exit successfully."""
    parser = build_parser()
    args = parser.parse_args(argv)
    due = due_accepted_decisions(resolve_decisions_dir(args.decisions_dir))
    if due:
        print(format_due_message(due))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
