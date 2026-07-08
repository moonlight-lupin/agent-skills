#!/usr/bin/env python3
"""ADR-style decision log CLI.

Creates, lists, searches, supersedes, and reviews Markdown decision records.
The implementation intentionally uses only the Python standard library so it can
travel with a skill repository without extra installation steps.
"""

import argparse
import datetime as dt
import glob
import os
import re
from pathlib import Path
from typing import Any, Iterable


VALID_STATUSES = ("accepted", "proposed", "superseded", "deprecated")
CADENCES = ("monthly", "quarterly", "annually", "on-trigger")
DEFAULT_DECISIONS_DIR = "./decisions"

ADR_TEMPLATE = """# ADR-NNN: Decision Title

## Status
proposed

## Date
YYYY-MM-DD

## Context
[Why this decision is needed — problem statement, constraints, background]

## Options Considered

### Option A: [name]
- Pros:
- Cons:

### Option B: [name]
- Pros:
- Cons:

## Decision
[What we chose and why]

## Consequences
- Positive:
- Negative:
- Neutral:

## Review
- Cadence: quarterly
- Next review: YYYY-MM-DD (auto-computed from date + cadence)
- Trigger: [optional condition that should prompt re-evaluation]
"""


class DecisionLogError(Exception):
    """Raised when a decision-log operation cannot be completed."""


def resolve_decisions_dir(value: str | None = None) -> Path:
    """Return the decisions directory from an argument, environment, or default."""
    chosen = value or os.environ.get("DECISIONS_DIR") or DEFAULT_DECISIONS_DIR
    return Path(chosen).expanduser()


def slugify(title: str) -> str:
    """Convert a title to a filesystem-safe kebab-case slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "decision"


def adr_glob(decisions_dir: Path) -> list[Path]:
    """Return all ADR Markdown files in numeric order."""
    paths = [Path(p) for p in glob.glob(str(decisions_dir / "ADR-[0-9][0-9][0-9]-*.md"))]
    return sorted(paths, key=lambda p: parse_adr_number(p) or 0)


def parse_adr_number(path: Path) -> int | None:
    """Extract an ADR number from a file path or return None."""
    match = re.search(r"ADR-(\d{3})", path.name)
    if not match:
        return None
    return int(match.group(1))


def next_adr_number(decisions_dir: Path) -> int:
    """Return the next available ADR number for a directory."""
    numbers = [n for n in (parse_adr_number(path) for path in adr_glob(decisions_dir)) if n]
    return (max(numbers) + 1) if numbers else 1


def add_months(date_value: dt.date, months: int) -> dt.date:
    """Add calendar months to a date, clamping the day at month end."""
    month_index = date_value.month - 1 + months
    year = date_value.year + month_index // 12
    month = month_index % 12 + 1
    days_in_month = [31, 29 if is_leap_year(year) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(date_value.day, days_in_month[month - 1])
    return dt.date(year, month, day)


def is_leap_year(year: int) -> bool:
    """Return True when a year is a Gregorian leap year."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def compute_next_review(date_value: dt.date, cadence: str) -> str:
    """Compute the next review date for a cadence, or blank for on-trigger."""
    if cadence == "monthly":
        return add_months(date_value, 1).isoformat()
    if cadence == "quarterly":
        return add_months(date_value, 3).isoformat()
    if cadence == "annually":
        return add_months(date_value, 12).isoformat()
    if cadence == "on-trigger":
        return ""
    raise DecisionLogError(f"Unsupported review cadence: {cadence}")


def render_template(number: int, title: str, context: str, date_value: dt.date, cadence: str) -> str:
    """Render a new ADR Markdown document from the embedded template."""
    number_text = f"{number:03d}"
    next_review = compute_next_review(date_value, cadence)
    next_review_text = next_review if next_review else ""
    context_text = context or "[Why this decision is needed — problem statement, constraints, background]"
    return (
        ADR_TEMPLATE.replace("ADR-NNN", f"ADR-{number_text}")
        .replace("Decision Title", title)
        .replace("YYYY-MM-DD (auto-computed from date + cadence)", next_review_text)
        .replace("YYYY-MM-DD", date_value.isoformat(), 1)
        .replace("Cadence: quarterly", f"Cadence: {cadence}")
        .replace("[Why this decision is needed — problem statement, constraints, background]", context_text)
    )


def create_decision(title: str, context: str = "", decisions_dir: Path | None = None, cadence: str = "quarterly") -> Path:
    """Create a new sequential ADR file and return its path."""
    if cadence not in CADENCES:
        raise DecisionLogError(f"Unsupported review cadence: {cadence}")
    directory = decisions_dir or resolve_decisions_dir(None)
    directory.mkdir(parents=True, exist_ok=True)
    number = next_adr_number(directory)
    path = directory / f"ADR-{number:03d}-{slugify(title)}.md"
    if path.exists():
        raise DecisionLogError(f"Refusing to overwrite existing ADR: {path}")
    path.write_text(render_template(number, title, context, dt.date.today(), cadence), encoding="utf-8")
    return path


def read_text(path: Path) -> str:
    """Read UTF-8 text from a file."""
    return path.read_text(encoding="utf-8")


def section_after_heading(text: str, heading: str) -> str:
    """Return the body text immediately following a Markdown level-2 heading."""
    pattern = rf"^##\s+{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^##\s+|\Z)"
    match = re.search(pattern, text, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    return match.group("body").strip() if match else ""


def parse_status(text: str) -> str:
    """Parse the status value from an ADR document."""
    body = section_after_heading(text, "Status")
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return first or "unknown"


def normalized_status(status: str) -> str:
    """Normalize concrete status text into a filterable status family."""
    lower = status.strip().lower()
    if lower.startswith("superseded by adr-"):
        return "superseded"
    return lower


def parse_date(text: str) -> str:
    """Parse the decision date from an ADR document."""
    body = section_after_heading(text, "Date")
    first = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return first


def parse_title(text: str, path: Path) -> str:
    """Parse the ADR title from the H1 heading, falling back to the filename."""
    match = re.search(r"^#\s+ADR-\d{3}:\s+(.+?)\s*$", text, flags=re.MULTILINE)
    if match:
        return match.group(1).strip()
    return path.stem


def parse_next_review(text: str) -> str:
    """Parse the next review date from an ADR document."""
    review = section_after_heading(text, "Review")
    match = re.search(r"Next review:\s*(\d{4}-\d{2}-\d{2})", review, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def parse_supersedes_to(status: str) -> int | None:
    """Extract the ADR number that a status supersedes to, if present."""
    match = re.search(r"superseded\s+by\s+ADR-(\d{3})", status, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def parse_decision(path: Path) -> dict[str, Any]:
    """Parse a single ADR file into metadata used by CLI commands."""
    text = read_text(path)
    number = parse_adr_number(path)
    status = parse_status(text)
    return {
        "number": number,
        "adr": f"ADR-{number:03d}" if number else "ADR-???",
        "title": parse_title(text, path),
        "status": status,
        "status_family": normalized_status(status),
        "date": parse_date(text),
        "next_review": parse_next_review(text),
        "superseded_by": parse_supersedes_to(status),
        "path": path,
        "text": text,
    }


def load_decisions(decisions_dir: Path) -> list[dict[str, Any]]:
    """Load all ADR metadata from a decisions directory."""
    return [parse_decision(path) for path in adr_glob(decisions_dir)]


def filter_decisions(
    decisions: Iterable[dict[str, Any]], status: str | None = None, topic: str | None = None
) -> list[dict[str, Any]]:
    """Filter decision metadata by status family and free-text topic."""
    filtered: list[dict[str, Any]] = []
    topic_lower = topic.lower() if topic else None
    for decision in decisions:
        if status and decision["status_family"] != status:
            continue
        if topic_lower and topic_lower not in decision["text"].lower() and topic_lower not in decision["title"].lower():
            continue
        filtered.append(decision)
    return filtered


def format_table(decisions: list[dict[str, Any]]) -> str:
    """Format decisions as a simple Markdown-like table."""
    if not decisions:
        return "No decisions found."
    rows = [(d["adr"], d["date"], d["status"], d["title"], str(d["path"])) for d in decisions]
    headers = ("ADR", "Date", "Status", "Title", "Path")
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(widths[i], len(row[i])) for i in range(len(headers))]
    line = "  ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))
    sep = "  ".join("-" * widths[i] for i in range(len(headers)))
    body = ["  ".join(row[i].ljust(widths[i]) for i in range(len(headers))) for row in rows]
    return "\n".join([line, sep, *body])


def find_adr_path(decisions_dir: Path, number: int) -> Path:
    """Find the ADR file path for a number or raise a clear error."""
    pattern = decisions_dir / f"ADR-{number:03d}-*.md"
    matches = sorted(Path(p) for p in glob.glob(str(pattern)))
    if not matches:
        raise DecisionLogError(f"ADR-{number:03d} not found in {decisions_dir}")
    if len(matches) > 1:
        raise DecisionLogError(f"Multiple files found for ADR-{number:03d}: {matches}")
    return matches[0]


def replace_status(text: str, new_status: str) -> str:
    """Replace the content of the Status section with a new status value."""
    pattern = r"(^##\s+Status\s*$\n)(.*?)(?=^##\s+|\Z)"
    replacement = rf"\1{new_status}\n\n"
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if count != 1:
        raise DecisionLogError("Could not locate a unique ## Status section")
    return updated


def add_supersede_link(text: str, by_number: int, by_path: Path) -> str:
    """Add or update a link from a superseded ADR to the replacing ADR."""
    link = f"Superseded by: [ADR-{by_number:03d}]({by_path.name})"
    if re.search(r"^Superseded by:\s+\[ADR-\d{3}\]", text, flags=re.MULTILINE):
        return re.sub(r"^Superseded by:.*$", link, text, count=1, flags=re.MULTILINE)
    return text.rstrip() + "\n\n" + link + "\n"


def supersede_decision(number: int, by_number: int, decisions_dir: Path) -> Path:
    """Mark one ADR as superseded by another ADR and add a backlink."""
    target_path = find_adr_path(decisions_dir, number)
    by_path = find_adr_path(decisions_dir, by_number)
    text = read_text(target_path)
    updated = replace_status(text, f"superseded by ADR-{by_number:03d}")
    updated = add_supersede_link(updated, by_number, by_path)
    target_path.write_text(updated, encoding="utf-8")
    return target_path


def search_decisions(query: str, decisions_dir: Path) -> list[tuple[dict[str, Any], str]]:
    """Search ADR files for a query and return matching decisions with context snippets."""
    query_lower = query.lower()
    results: list[tuple[dict[str, Any], str]] = []
    for decision in load_decisions(decisions_dir):
        text_lower = decision["text"].lower()
        index = text_lower.find(query_lower)
        if index == -1:
            continue
        start = max(0, index - 80)
        end = min(len(decision["text"]), index + len(query) + 80)
        snippet = re.sub(r"\s+", " ", decision["text"][start:end]).strip()
        results.append((decision, snippet))
    return results


def due_reviews(decisions_dir: Path, accepted_only: bool = False, today: dt.date | None = None) -> list[dict[str, Any]]:
    """Return ADRs with a next review date on or before today."""
    current = today or dt.date.today()
    due: list[dict[str, Any]] = []
    for decision in load_decisions(decisions_dir):
        if accepted_only and decision["status_family"] != "accepted":
            continue
        if decision["status_family"] in {"superseded", "deprecated"}:
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


def build_timeline_chains(decisions: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Build superseding chains from parsed ADR metadata."""
    by_number = {d["number"]: d for d in decisions if d["number"] is not None}
    outgoing = {d["number"]: d["superseded_by"] for d in decisions if d.get("superseded_by")}
    incoming = {target for target in outgoing.values() if target in by_number}
    starts = sorted(number for number in by_number if number in outgoing and number not in incoming)
    chains: list[list[dict[str, Any]]] = []
    seen_edges: set[tuple[int, int]] = set()
    for start in starts:
        chain: list[dict[str, Any]] = []
        current = start
        seen_nodes: set[int] = set()
        while current in by_number and current not in seen_nodes:
            chain.append(by_number[current])
            seen_nodes.add(current)
            next_number = outgoing.get(current)
            if next_number is None or next_number not in by_number:
                break
            seen_edges.add((current, next_number))
            current = next_number
        if len(chain) > 1:
            chains.append(chain)
    for source, target in sorted(outgoing.items()):
        if (source, target) not in seen_edges and source in by_number and target in by_number:
            chains.append([by_number[source], by_number[target]])
    return chains


def format_timeline(chains: list[list[dict[str, Any]]]) -> str:
    """Format superseding chains for CLI output."""
    if not chains:
        return "No superseding chains found."
    lines = []
    for chain in chains:
        lines.append(" → ".join(decision["adr"] for decision in chain))
    return "\n".join(lines)


def command_new(args: argparse.Namespace) -> int:
    """Handle the new subcommand."""
    path = create_decision(args.title, args.context or "", resolve_decisions_dir(args.decisions_dir), args.cadence)
    print(f"Created {path}")
    print(f"Edit this decision record at: {path}")
    return 0


def command_list(args: argparse.Namespace) -> int:
    """Handle the list subcommand."""
    decisions = load_decisions(resolve_decisions_dir(args.decisions_dir))
    print(format_table(filter_decisions(decisions, args.status, args.topic)))
    return 0


def command_supersede(args: argparse.Namespace) -> int:
    """Handle the supersede subcommand."""
    path = supersede_decision(args.number, args.by, resolve_decisions_dir(args.decisions_dir))
    print(f"Updated {path}: superseded by ADR-{args.by:03d}")
    return 0


def command_search(args: argparse.Namespace) -> int:
    """Handle the search subcommand."""
    results = search_decisions(args.query, resolve_decisions_dir(args.decisions_dir))
    if not results:
        print("No matching decisions found.")
        return 0
    for decision, snippet in results:
        print(f"{decision['adr']}  {decision['title']}  ({decision['path']})")
        print(f"  ...{snippet}...")
    return 0


def command_due_review(args: argparse.Namespace) -> int:
    """Handle the due-review subcommand."""
    due = due_reviews(resolve_decisions_dir(args.decisions_dir), accepted_only=False)
    if not due:
        print("No decisions due for review.")
        return 0
    print(f"{len(due)} decisions due for review:")
    for decision in due:
        print(f"- {decision['adr']} ({decision['next_review']}): {decision['title']} — {decision['path']}")
    return 0


def command_timeline(args: argparse.Namespace) -> int:
    """Handle the timeline subcommand."""
    decisions = load_decisions(resolve_decisions_dir(args.decisions_dir))
    # Build chains over ALL decisions, then keep chains where any member
    # matches the topic — filtering first would break a chain whenever a
    # middle ADR doesn't mention the topic text.
    chains = build_timeline_chains(decisions)
    if args.topic:
        matching = {d["path"] for d in filter_decisions(decisions, topic=args.topic)}
        chains = [chain for chain in chains if any(d["path"] in matching for d in chain)]
    print(format_timeline(chains))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build and return the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Manage an ADR-style Markdown decision log.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    new_p = sub.add_parser("new", help="create a new numbered decision record")
    new_p.add_argument("--title", required=True, help="decision title")
    new_p.add_argument("--context", help="initial context/problem statement")
    new_p.add_argument("--cadence", choices=CADENCES, default="quarterly", help="review cadence")
    new_p.add_argument("--decisions-dir", help="directory holding ADR Markdown files")
    new_p.set_defaults(func=command_new)

    list_p = sub.add_parser("list", help="list decisions as a table")
    list_p.add_argument("--status", choices=VALID_STATUSES, help="filter by status family")
    list_p.add_argument("--topic", help="filter by topic text")
    list_p.add_argument("--decisions-dir", help="directory holding ADR Markdown files")
    list_p.set_defaults(func=command_list)

    supersede_p = sub.add_parser("supersede", help="mark an ADR as superseded by another ADR")
    supersede_p.add_argument("number", type=int, metavar="NNN", help="ADR number to supersede")
    supersede_p.add_argument("--by", type=int, required=True, metavar="MMM", help="ADR number that replaces it")
    supersede_p.add_argument("--decisions-dir", help="directory holding ADR Markdown files")
    supersede_p.set_defaults(func=command_supersede)

    search_p = sub.add_parser("search", help="full-text search across ADR files")
    search_p.add_argument("query", help="search query")
    search_p.add_argument("--decisions-dir", help="directory holding ADR Markdown files")
    search_p.set_defaults(func=command_search)

    due_p = sub.add_parser("due-review", help="list decisions whose review date is due")
    due_p.add_argument("--decisions-dir", help="directory holding ADR Markdown files")
    due_p.set_defaults(func=command_due_review)

    timeline_p = sub.add_parser("timeline", help="show superseding chains")
    timeline_p.add_argument("--topic", help="filter chains by topic text")
    timeline_p.add_argument("--decisions-dir", help="directory holding ADR Markdown files")
    timeline_p.set_defaults(func=command_timeline)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the decision-log CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except DecisionLogError as exc:
        parser.exit(2, f"error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
