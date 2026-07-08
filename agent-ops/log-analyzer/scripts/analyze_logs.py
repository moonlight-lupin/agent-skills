#!/usr/bin/env python3
"""Analyze agent-style log files for recurring error patterns and anomalies.

Pure-stdlib CLI with three subcommands:
  scan   -> JSON anomaly scan
  report -> Markdown report from scan JSON
  tail   -> recent-line view with anomaly markers
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, date, time, timedelta, timezone

LEVELS = {"ERROR", "WARN", "WARNING", "INFO", "DEBUG", "FATAL", "CRITICAL"}
ERROR_LEVELS = {"ERROR", "FATAL", "CRITICAL"}
WARNING_LEVELS = {"WARN", "WARNING"}
CLUSTER_THRESHOLD = 3

ISO_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+"
    r"(?P<level>ERROR|WARN|WARNING|INFO|DEBUG|FATAL|CRITICAL)\s+"
    r"(?:(?:\[(?P<bracket>[^\]]+)\])|(?P<colon>[A-Za-z0-9_.-]+):)?\s*"
    r"(?P<message>.*)$"
)
SPACE_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"(?P<level>ERROR|WARN|WARNING|INFO|DEBUG|FATAL|CRITICAL)\s+"
    r"(?:(?:\[(?P<bracket>[^\]]+)\])|(?P<colon>[A-Za-z0-9_.-]+):)?\s*"
    r"(?P<message>.*)$"
)
TIME_LINE_RE = re.compile(
    r"^(?P<ts>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>ERROR|WARN|WARNING|INFO|DEBUG|FATAL|CRITICAL)\s+"
    r"(?:(?:\[(?P<bracket>[^\]]+)\])|(?P<colon>[A-Za-z0-9_.-]+):)?\s*"
    r"(?P<message>.*)$"
)
UNSTRUCTURED_LEVEL_RE = re.compile(
    r"\b(?P<level>ERROR|WARN|WARNING|INFO|DEBUG|FATAL|CRITICAL)\b[:\s-]*(?P<message>.*)$",
    re.IGNORECASE,
)

URL_RE = re.compile(r"https?://\S+")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
NUMBER_RE = re.compile(r"\b\d+\b")
RATE_LIMIT_RE = re.compile(r"\b429\b|rate[ _-]?limit|too many requests|quota exceeded", re.IGNORECASE)
TIMEOUT_RE = re.compile(r"timed out|deadline exceeded|connection timeout|\btimeout\b", re.IGNORECASE)
CRASH_RE = re.compile(r"fatal|unhandled|Traceback|Exception|segfault", re.IGNORECASE)
PROVIDER_RE = re.compile(r"\bprovider[=: ]+([A-Za-z0-9_.-]+)", re.IGNORECASE)
KNOWN_PROVIDERS = (
    "openrouter", "openai", "anthropic", "google", "groq", "together",
    "mistral", "azure", "aws", "bedrock", "fal", "cohere",
)
TOOL_PATTERNS = [
    re.compile(r"\btool_call[=: ]+([A-Za-z0-9_.-]+)", re.IGNORECASE),
    re.compile(r"\btool[=: ]+([A-Za-z0-9_.-]+)", re.IGNORECASE),
    re.compile(r"\btool\s+([A-Za-z0-9_.-]+)\s+(?:failed|error|timeout)", re.IGNORECASE),
]
STACK_CONTINUATION_RE = re.compile(r"^(\s+|File \"|Traceback|[A-Za-z_][A-Za-z0-9_.]*Error:|Exception:)")


def utc_now():
    return datetime.now(timezone.utc)


def to_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def isoformat_z(dt):
    if dt is None:
        return None
    return to_utc(dt).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_timestamp(value, default_date=None):
    """Parse supported timestamp strings into timezone-aware UTC datetimes."""
    if not value:
        return None
    value = value.strip()
    if re.match(r"^\d{2}:\d{2}:\d{2}$", value):
        if default_date is None:
            base_date = utc_now().date()
        elif isinstance(default_date, datetime):
            base_date = default_date.date()
        else:
            base_date = default_date
        return datetime.combine(base_date, time.fromisoformat(value), tzinfo=timezone.utc)

    try:
        if "T" in value:
            normalized = value
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            if re.search(r"[+-]\d{4}$", normalized):
                normalized = normalized[:-5] + normalized[-5:-2] + ":" + normalized[-2:]
            return to_utc(datetime.fromisoformat(normalized))
        if "." in value:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_log_line(line, default_date=None):
    """Parse one log line into a dict; return best-effort fields for unstructured lines."""
    raw = line.rstrip("\n")
    for regex in (ISO_LINE_RE, SPACE_LINE_RE, TIME_LINE_RE):
        m = regex.match(raw)
        if m:
            level = m.group("level").upper()
            component = m.group("bracket") or m.group("colon") or "unknown"
            return {
                "timestamp": parse_timestamp(m.group("ts"), default_date=default_date),
                "timestamp_text": m.group("ts"),
                "level": level,
                "component": component.strip() if component else "unknown",
                "message": m.group("message").strip(),
                "raw": raw,
                "raw_lines": [raw],
                "line_count": 1,
            }

    m = UNSTRUCTURED_LEVEL_RE.search(raw)
    if m:
        return {
            "timestamp": None,
            "timestamp_text": None,
            "level": m.group("level").upper(),
            "component": "unknown",
            "message": m.group("message").strip(),
            "raw": raw,
            "raw_lines": [raw],
            "line_count": 1,
        }
    return None


def append_continuation(entry, line):
    raw = line.rstrip("\n")
    entry["raw_lines"].append(raw)
    entry["line_count"] += 1
    if raw:
        entry["message"] = entry["message"] + "\n" + raw if entry["message"] else raw
    entry["raw"] = "\n".join(entry["raw_lines"])


def read_entries(log_file, default_date=None):
    """Read and parse a log file, grouping multiline stack traces."""
    entries = []
    with open(log_file, "r", encoding="utf-8", errors="replace") as fh:
        physical_lines = [line.rstrip("\n") for line in fh]

    for idx, line in enumerate(physical_lines):
        parsed = parse_log_line(line, default_date=default_date)
        if parsed:
            parsed["start_line"] = idx
            parsed["end_line"] = idx
            entries.append(parsed)
            continue

        if entries and (STACK_CONTINUATION_RE.match(line) or "Traceback" in entries[-1].get("message", "")):
            append_continuation(entries[-1], line)
            entries[-1]["end_line"] = idx
        elif line.strip():
            entries.append({
                "timestamp": None,
                "timestamp_text": None,
                "level": "INFO",
                "component": "unknown",
                "message": line.strip(),
                "raw": line,
                "raw_lines": [line],
                "line_count": 1,
                "start_line": idx,
                "end_line": idx,
            })

    return entries, physical_lines


def parse_since(since):
    if not since:
        return None
    m = re.match(r"^\s*(\d+)\s*([hHdDwWmM])\s*$", since)
    if not m:
        raise ValueError("--since must look like 1h, 24h, 7d, 2w, or 30m")
    amount = int(m.group(1))
    unit = m.group(2).lower()
    if unit == "m":
        delta = timedelta(minutes=amount)
    elif unit == "h":
        delta = timedelta(hours=amount)
    elif unit == "d":
        delta = timedelta(days=amount)
    elif unit == "w":
        delta = timedelta(weeks=amount)
    else:
        raise ValueError("unsupported --since unit")
    return utc_now() - delta


def filter_by_since(entries, since):
    cutoff = parse_since(since) if since else None
    if cutoff is None:
        return list(entries)
    filtered = []
    for entry in entries:
        ts = entry.get("timestamp")
        # Unknown timestamps are retained so unstructured recent logs still scan.
        ts_utc = to_utc(ts)
        if ts_utc is None or ts_utc >= cutoff:
            filtered.append(entry)
    return filtered


def normalize_message(message):
    text = message.splitlines()[0] if message else ""
    text = URL_RE.sub("[URL]", text)
    text = IP_RE.sub("[IP]", text)
    text = NUMBER_RE.sub("[NUM]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "[empty message]"


def is_error(entry):
    return entry.get("level") in ERROR_LEVELS


def is_warning(entry):
    return entry.get("level") in WARNING_LEVELS


def is_crash(entry):
    return entry.get("level") in {"FATAL", "CRITICAL"} or bool(CRASH_RE.search(entry.get("message", "")))


def extract_provider(entry):
    text = f"{entry.get('component', '')} {entry.get('message', '')}".lower()
    m = PROVIDER_RE.search(text)
    if m:
        return m.group(1).lower()
    for provider in KNOWN_PROVIDERS:
        if provider in text:
            return provider
    component = (entry.get("component") or "").lower()
    return component if component not in ("", "unknown") else "unknown"


def extract_tool(entry):
    text = entry.get("message", "")
    for regex in TOOL_PATTERNS:
        m = regex.search(text)
        if m:
            tool = m.group(1).strip(".,;:[](){}").lower()
            if tool and tool not in {"failed", "error", "timeout"}:
                return tool
    component = (entry.get("component") or "").lower()
    if component in {"tools", "tool"}:
        m = re.match(r"([A-Za-z0-9_.-]+)[:\s-]", text.strip())
        if m:
            return m.group(1).lower()
        return "tools"
    if component.startswith("tool") and component not in {"tools", "tool"}:
        return component
    return "unknown"


def extract_urls(text):
    return URL_RE.findall(text or "")


def timeframe_for(entries):
    stamped = []
    for entry in entries:
        ts = to_utc(entry.get("timestamp"))
        if ts is not None:
            stamped.append(ts)
    if not stamped:
        return "unknown"
    first = min(stamped)
    last = max(stamped)
    if first == last:
        return isoformat_z(first)
    return f"{isoformat_z(first)}–{isoformat_z(last)}"


def crash_type(entry):
    msg = entry.get("message", "")
    level = entry.get("level")
    if "Traceback" in msg:
        return "stack_trace"
    if re.search(r"unhandled|Exception", msg, re.IGNORECASE):
        return "unhandled_exception"
    if re.search(r"segfault", msg, re.IGNORECASE):
        return "segfault"
    if level in {"FATAL", "CRITICAL"} or re.search(r"fatal", msg, re.IGNORECASE):
        return "fatal_error"
    return "crash"


def crash_message(entry):
    lines = [line.strip() for line in entry.get("message", "").splitlines() if line.strip()]
    if not lines:
        return ""
    for line in reversed(lines):
        if re.search(r"Error:|Exception:|KeyError|ValueError|TypeError|RuntimeError|segfault|fatal|unhandled", line, re.IGNORECASE):
            return line
    return lines[0]


def analyze_entries(entries, physical_lines=None, log_file=None, since=None):
    physical_lines = physical_lines or []
    error_entries = [e for e in entries if is_error(e)]
    warning_entries = [e for e in entries if is_warning(e)]

    component_counts = defaultdict(lambda: {"errors": 0, "warnings": 0})
    for entry in entries:
        component = (entry.get("component") or "unknown").lower()
        if is_error(entry):
            component_counts[component]["errors"] += 1
        if is_warning(entry):
            component_counts[component]["warnings"] += 1

    timeline = Counter()
    for entry in error_entries:
        ts = entry.get("timestamp")
        ts_utc = to_utc(ts)
        if ts_utc is not None:
            timeline[ts_utc.strftime("%H:00")] += 1

    # Error clusters.
    clusters = defaultdict(list)
    for entry in error_entries:
        clusters[normalize_message(entry.get("message", ""))].append(entry)
    error_clusters = []
    for message, group in clusters.items():
        if len(group) >= CLUSTER_THRESHOLD:
            stamped = []
            for group_entry in group:
                ts = to_utc(group_entry.get("timestamp"))
                if ts is not None:
                    stamped.append(ts)
            error_clusters.append({
                "message": message,
                "count": len(group),
                "first_seen": isoformat_z(min(stamped)) if stamped else None,
                "last_seen": isoformat_z(max(stamped)) if stamped else None,
                "example": group[0].get("message", "").splitlines()[0],
            })
    error_clusters.sort(key=lambda item: (-item["count"], item["message"]))

    # Rate limits.
    rate_groups = defaultdict(list)
    for entry in entries:
        if RATE_LIMIT_RE.search(entry.get("message", "")):
            rate_groups[extract_provider(entry)].append(entry)
    rate_limits = [
        {"provider": provider, "count": len(group), "timeframe": timeframe_for(group)}
        for provider, group in sorted(rate_groups.items())
    ]
    rate_limits.sort(key=lambda item: (-item["count"], item["provider"]))

    # Timeouts.
    timeout_groups = defaultdict(list)
    for entry in entries:
        if TIMEOUT_RE.search(entry.get("message", "")):
            timeout_groups[extract_tool(entry)].append(entry)
    timeouts = []
    for tool, group in timeout_groups.items():
        urls = []
        for entry in group:
            for url in extract_urls(entry.get("message", "")):
                if url not in urls:
                    urls.append(url)
        timeouts.append({"tool": tool, "count": len(group), "urls": urls[:10]})
    timeouts.sort(key=lambda item: (-item["count"], item["tool"]))

    # Tool failures.
    tool_groups = defaultdict(list)
    for entry in error_entries:
        tool = extract_tool(entry)
        if tool != "unknown":
            tool_groups[tool].append(entry)
    tool_failures = []
    for tool, group in tool_groups.items():
        counter = Counter(normalize_message(e.get("message", "")) for e in group)
        tool_failures.append({
            "tool": tool,
            "count": len(group),
            "top_errors": [msg for msg, _count in counter.most_common(5)],
            "top_error_counts": [{"message": msg, "count": count} for msg, count in counter.most_common(5)],
        })
    tool_failures.sort(key=lambda item: (-item["count"], item["tool"]))

    # Crashes.
    crashes = []
    seen_crash_lines = set()
    for entry in entries:
        if not is_crash(entry):
            continue
        key = (entry.get("start_line"), crash_message(entry))
        if key in seen_crash_lines:
            continue
        seen_crash_lines.add(key)
        start = max(0, int(entry.get("start_line", 0)) - 2)
        end = min(len(physical_lines), int(entry.get("end_line", entry.get("start_line", 0))) + 3)
        context = physical_lines[start:end] if physical_lines else entry.get("raw_lines", [])
        crashes.append({
            "type": crash_type(entry),
            "message": crash_message(entry),
            "timestamp": isoformat_z(entry.get("timestamp")),
            "context": context,
        })

    anomalies = {
        "error_clusters": error_clusters,
        "rate_limits": rate_limits,
        "timeouts": timeouts,
        "tool_failures": tool_failures,
        "crashes": crashes,
    }

    return {
        "log_file": log_file or "",
        "lines_analyzed": sum(e.get("line_count", 1) for e in entries),
        "time_window": since or "all",
        "anomalies": anomalies,
        "component_breakdown": dict(sorted(component_counts.items())),
        "error_timeline": dict(sorted(timeline.items())),
        "total_errors": len(error_entries),
        "total_warnings": len(warning_entries),
        "has_anomalies": any(bool(value) for value in anomalies.values()),
    }


def scan_log_file(log_file, since=None):
    entries, physical_lines = read_entries(log_file)
    filtered = filter_by_since(entries, since)
    return analyze_entries(filtered, physical_lines=physical_lines, log_file=log_file, since=since)


def anomaly_type_count(scan):
    return sum(1 for value in scan.get("anomalies", {}).values() if value)


def format_counted_errors(items):
    if not items:
        return "none"
    parts = []
    for item in items[:3]:
        if isinstance(item, dict):
            parts.append(f'"{item.get("message", "")}" ({item.get("count", 0)}x)')
        else:
            parts.append(f'"{item}"')
    return ", ".join(parts)


def render_markdown_report(scan):
    anomalies = scan.get("anomalies", {})
    lines = [
        "# Log Analysis Report",
        "",
        "## Overview",
        f"- Log file: {scan.get('log_file', '')}",
        f"- Lines analyzed: {scan.get('lines_analyzed', 0)}",
        f"- Time window: {scan.get('time_window', 'all')}",
        f"- Total errors: {scan.get('total_errors', 0)} | warnings: {scan.get('total_warnings', 0)}",
        f"- Anomalies detected: {anomaly_type_count(scan)} types",
        "",
    ]

    clusters = anomalies.get("error_clusters", [])
    lines.append(f"## Error Clusters ({len(clusters)})")
    if clusters:
        for item in clusters:
            lines.extend([
                f"### \"{item.get('message', '')}\" — {item.get('count', 0)} occurrences",
                f"- First: {item.get('first_seen') or 'unknown'}",
                f"- Last: {item.get('last_seen') or 'unknown'}",
                "",
            ])
    else:
        lines.extend(["No repeated error clusters detected.", ""])

    rate_limits = anomalies.get("rate_limits", [])
    lines.append(f"## Rate Limit Hits ({len(rate_limits)})")
    if rate_limits:
        for item in rate_limits:
            lines.extend([f"### {item.get('provider', 'unknown')} — {item.get('count', 0)} hits ({item.get('timeframe', 'unknown')})", ""])
    else:
        lines.extend(["No rate limit hits detected.", ""])

    timeouts = anomalies.get("timeouts", [])
    lines.append(f"## Timeouts ({len(timeouts)})")
    if timeouts:
        for item in timeouts:
            lines.append(f"### {item.get('tool', 'unknown')} — {item.get('count', 0)} timeouts")
            urls = item.get("urls") or []
            if urls:
                lines.append("- URLs: " + ", ".join(urls[:5]))
            lines.append("")
    else:
        lines.extend(["No timeout patterns detected.", ""])

    failures = anomalies.get("tool_failures", [])
    lines.append(f"## Tool Failures ({len(failures)})")
    if failures:
        for item in failures:
            top = item.get("top_error_counts") or [{"message": msg, "count": 0} for msg in item.get("top_errors", [])]
            lines.extend([
                f"### {item.get('tool', 'unknown')} — {item.get('count', 0)} errors",
                f"- Top: {format_counted_errors(top)}",
                "",
            ])
    else:
        lines.extend(["No tool failures detected.", ""])

    crashes = anomalies.get("crashes", [])
    lines.append(f"## Crashes ({len(crashes)})")
    if crashes:
        for item in crashes:
            title = item.get("type", "crash").replace("_", " ").title()
            ts = item.get("timestamp") or "unknown time"
            lines.extend([f"### {title} — {item.get('message', '')} at {ts}", ""])
    else:
        lines.extend(["No crashes detected.", ""])

    lines.extend([
        "## Component Breakdown",
        "| Component | Errors | Warnings |",
        "|-----------|--------|----------|",
    ])
    breakdown = scan.get("component_breakdown", {})
    if breakdown:
        for component, counts in sorted(breakdown.items()):
            lines.append(f"| {component} | {counts.get('errors', 0)} | {counts.get('warnings', 0)} |")
    else:
        lines.append("| none | 0 | 0 |")
    lines.append("")

    lines.append("## Error Timeline")
    timeline = scan.get("error_timeline", {})
    if timeline:
        for hour, count in sorted(timeline.items()):
            bar = "█" * min(int(count), 50)
            lines.append(f"{hour} {bar} {count}")
    else:
        lines.append("No timestamped errors detected.")
    lines.append("")
    return "\n".join(lines)


def cmd_scan(args):
    if not os.path.exists(args.log_file):
        print(f"log file not found: {args.log_file}", file=sys.stderr)
        return 2
    try:
        scan = scan_log_file(args.log_file, since=args.since)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output = json.dumps(scan, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output + "\n")
        if args.quiet and not scan["has_anomalies"]:
            # Empty file is easier for shell tests like [ -s file ].
            open(args.output, "w", encoding="utf-8").close()
        return 0

    if args.quiet and not scan["has_anomalies"]:
        return 0
    print(output)
    return 0


def cmd_report(args):
    if not os.path.exists(args.scan):
        print(f"scan file not found: {args.scan}", file=sys.stderr)
        return 2
    try:
        with open(args.scan, "r", encoding="utf-8") as fh:
            scan = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"could not read scan file {args.scan}: {exc}", file=sys.stderr)
        return 2
    report = render_markdown_report(scan)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(report)
    else:
        print(report)
    return 0


def cmd_tail(args):
    if not os.path.exists(args.log_file):
        print(f"log file not found: {args.log_file}", file=sys.stderr)
        return 2
    try:
        entries, _physical_lines = read_entries(args.log_file)
        entries = filter_by_since(entries, args.since)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    selected = entries[-args.lines:]
    recent_errors = Counter(normalize_message(e.get("message", "")) for e in selected if is_error(e))
    for entry in selected:
        marker = "  "
        if is_error(entry):
            marker = "❌"
            if recent_errors[normalize_message(entry.get("message", ""))] >= CLUSTER_THRESHOLD:
                marker = "🔥"
        elif is_warning(entry):
            marker = "⚠️"
        print(f"{marker} {entry.get('raw_lines', [entry.get('raw', '')])[0]}")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Analyze log files for recurring errors and anomalies.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Analyze log file for patterns")
    scan.add_argument("--log-file", required=True, help="Path to log file")
    scan.add_argument("--since", help="Only analyze lines within this window (e.g. 1h, 24h, 7d)")
    scan.add_argument("--output", help="Write JSON report to file instead of stdout")
    scan.add_argument("--quiet", action="store_true", help="Suppress output if no anomalies are found")
    scan.set_defaults(func=cmd_scan)

    report = subparsers.add_parser("report", help="Generate Markdown report from scan JSON")
    report.add_argument("--scan", required=True, help="Path to scan JSON")
    report.add_argument("--output", help="Write Markdown report to file instead of stdout")
    report.set_defaults(func=cmd_report)

    tail = subparsers.add_parser("tail", help="Show recent lines with anomaly markers")
    tail.add_argument("--log-file", required=True, help="Path to log file")
    tail.add_argument("--lines", type=int, default=50, help="Number of recent parsed entries to show")
    tail.add_argument("--since", help="Only show lines within this window (e.g. 1h, 24h, 7d)")
    tail.set_defaults(func=cmd_tail)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
