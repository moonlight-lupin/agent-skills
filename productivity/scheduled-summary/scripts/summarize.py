#!/usr/bin/env python3
"""Generate compact cross-session activity digests.

The CLI is intentionally stdlib-only and data-source agnostic. It can read a
best-effort SQLite session store, cron output files, JSON memory records, text or
JSONL logs, and optional Markdown decision records.
"""

import argparse
import collections
import datetime as dt
import glob
import json
import os
import re
import sqlite3

DEFAULT_SECTIONS = ["sessions", "cron", "memory", "tools", "outstanding"]
SOURCE_ENV = {
    "sessions_db": "SESSIONS_DB",
    "cron_dir": "CRON_OUTPUT_DIR",
    "memory_dir": "MEMORY_DIR",
    "log_file": "LOG_FILE",
    "decisions_dir": "DECISIONS_DIR",
}
SOURCE_LABELS = {
    "sessions_db": "Session SQLite database",
    "cron_dir": "Cron output directory",
    "memory_dir": "Memory JSON directory",
    "log_file": "Log file",
    "decisions_dir": "Decision records directory",
}
TODO_RE = re.compile(r"\b(?:TODO|FIXME|ACTION(?: ITEM)?|FOLLOW[- ]?UP)\b\s*[:\-]?\s*(.{0,180})", re.I)
FAIL_RE = re.compile(r"\b(fail(?:ed|ure)?|error|exception|timeout|timed out|non[- ]?zero|exit code [1-9]|rate limit)\b", re.I)
SUCCESS_RE = re.compile(r"(✅|\b(success|succeeded|successful|completed|ok|exit code 0)\b)", re.I)
OVERDUE_RE = re.compile(r"\b(overdue|stale|missed schedule|last ran \d+\s+(?:day|days|week|weeks) ago)\b", re.I)
TOOL_RE_PATTERNS = [
    re.compile(r"\btool\s*[=:]\s*['\"]?([A-Za-z0-9_.-]+)"),
    re.compile(r"\bTOOL\s+([A-Za-z0-9_.-]+)"),
    re.compile(r"\bcalled\s+([A-Za-z0-9_.-]+)\b", re.I),
]


def utc_now():
    """Return an aware UTC datetime."""
    return dt.datetime.now(dt.timezone.utc)


def parse_since(value):
    """Parse a relative duration such as 24h, 7d, 2w, or 30m."""
    if not value:
        value = "24h"
    text = str(value).strip().lower()
    match = re.fullmatch(r"(\d+)\s*([smhdw])", text)
    if not match:
        raise argparse.ArgumentTypeError("--since must look like 30m, 24h, 7d, or 2w")
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return dt.timedelta(seconds=amount)
    if unit == "m":
        return dt.timedelta(minutes=amount)
    if unit == "h":
        return dt.timedelta(hours=amount)
    if unit == "d":
        return dt.timedelta(days=amount)
    if unit == "w":
        return dt.timedelta(weeks=amount)
    raise argparse.ArgumentTypeError("unsupported --since unit")


def window_label(value):
    """Return a human-friendly label for a --since value."""
    text = str(value or "24h").strip()
    return "Last " + text


def parse_datetime(value):
    """Best-effort conversion of timestamps to aware UTC datetimes."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        result = value
    elif isinstance(value, (int, float)):
        stamp = float(value)
        if stamp > 10_000_000_000:
            stamp = stamp / 1000.0
        result = dt.datetime.fromtimestamp(stamp, dt.timezone.utc)
    else:
        text = str(value).strip()
        if not text:
            return None
        if re.fullmatch(r"\d+(?:\.\d+)?", text):
            return parse_datetime(float(text))
        text = text.replace("Z", "+00:00")
        for candidate in (text, text[:19], text[:10]):
            try:
                result = dt.datetime.fromisoformat(candidate)
                break
            except ValueError:
                result = None
        if result is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
                try:
                    result = dt.datetime.strptime(text[:19], fmt)
                    break
                except ValueError:
                    result = None
        if result is None:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=dt.timezone.utc)
    return result.astimezone(dt.timezone.utc)


def parse_date(value):
    """Parse YYYY-MM-DD from text."""
    if not value:
        return None
    match = re.search(r"(\d{4}-\d{2}-\d{2})", str(value))
    if not match:
        return None
    try:
        return dt.date.fromisoformat(match.group(1))
    except ValueError:
        return None


def safe_read(path, max_chars=200_000):
    """Read text, tolerating encoding errors and very large files."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(max_chars)
    except OSError:
        return ""


def truncate(text, limit=120):
    """Return a single-line truncated string."""
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def split_sections(value):
    """Normalize a comma-separated section list."""
    if not value:
        return list(DEFAULT_SECTIONS)
    requested = []
    for part in str(value).split(","):
        name = part.strip().lower()
        if not name:
            continue
        if name not in DEFAULT_SECTIONS:
            raise argparse.ArgumentTypeError(
                "unknown section %r; choose from %s" % (name, ",".join(DEFAULT_SECTIONS))
            )
        requested.append(name)
    return requested or list(DEFAULT_SECTIONS)


def load_config_file(path):
    """Load optional JSON config."""
    if not path:
        path = ".summary-config.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def resolve_sources(args=None, config=None):
    """Resolve data source paths from args, env vars, and config file."""
    args = args or argparse.Namespace()
    config = config or {}
    sources = {}
    for key, env_name in SOURCE_ENV.items():
        arg_value = getattr(args, key, None)
        sources[key] = arg_value or os.environ.get(env_name) or config.get(key) or ""
    return sources


def source_exists(key, path):
    """Return True when a configured source path exists with the right type."""
    if not path:
        return False
    if key.endswith("_dir"):
        return os.path.isdir(path)
    return os.path.isfile(path)


def summarize_config(args=None):
    """Return configuration rows for display."""
    config = load_config_file(getattr(args, "config", None))
    sources = resolve_sources(args, config)
    rows = []
    for key in SOURCE_ENV:
        path = sources.get(key, "")
        rows.append(
            {
                "source": key,
                "label": SOURCE_LABELS[key],
                "env": SOURCE_ENV[key],
                "path": path,
                "configured": bool(path),
                "exists": source_exists(key, path),
            }
        )
    return rows


def find_todos(text, source_title=""):
    """Extract TODO-like items from free text."""
    found = []
    for line in str(text or "").splitlines():
        match = TODO_RE.search(line)
        if not match:
            continue
        item = truncate(match.group(1) or line, 160)
        if not item:
            item = truncate(line, 160)
        found.append({"source": source_title or "unknown", "item": item})
    return found


def sqlite_tables(conn):
    """Return user table names for a SQLite connection."""
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return [row[0] for row in rows if not str(row[0]).startswith("sqlite_")]


def table_columns(conn, table):
    """Return column names for a SQLite table."""
    return [row[1] for row in conn.execute("PRAGMA table_info(%s)" % quote_ident(table)).fetchall()]


def quote_ident(name):
    """Quote a SQLite identifier."""
    return '"' + str(name).replace('"', '""') + '"'


def pick_first(row, names):
    """Pick the first present, non-empty row value."""
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def row_time(row):
    """Pick the best timestamp from a generic row."""
    fields = [
        "updated_at",
        "completed_at",
        "ended_at",
        "finished_at",
        "created_at",
        "started_at",
        "timestamp",
        "time",
        "date",
    ]
    parsed = [parse_datetime(row.get(name)) for name in fields if name in row]
    parsed = [value for value in parsed if value]
    if not parsed:
        return None
    return max(parsed)


def load_session_activity(path, since_dt):
    """Load best-effort session statistics and TODOs from SQLite."""
    result = {"completed": 0, "started": 0, "topics": [], "todos": []}
    if not path or not os.path.isfile(path):
        return result
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error:
        return result

    session_titles = {}
    try:
        for table in sqlite_tables(conn):
            cols = table_columns(conn, table)
            if not cols:
                continue
            quoted = ", ".join(quote_ident(col) for col in cols)
            try:
                rows = conn.execute("SELECT %s FROM %s" % (quoted, quote_ident(table))).fetchall()
            except sqlite3.Error:
                continue
            is_session_table = "session" in table.lower() or "conversation" in table.lower() or "thread" in table.lower()
            for raw in rows:
                row = dict(raw)
                when = row_time(row)
                in_window = when is None or when >= since_dt
                title = pick_first(row, ["title", "name", "summary", "subject", "topic"])
                row_id = pick_first(row, ["id", "session_id", "conversation_id", "thread_id"])
                if is_session_table and title:
                    if row_id is not None:
                        session_titles[str(row_id)] = str(title)
                    if in_window:
                        result["started"] += 1
                        status = str(pick_first(row, ["status", "state"]) or "").lower()
                        if status in ("completed", "done", "closed", "finished") or pick_first(row, ["ended_at", "completed_at", "finished_at"]):
                            result["completed"] += 1
                        topic = truncate(title, 90)
                        if topic and topic not in result["topics"]:
                            result["topics"].append(topic)
                if not in_window:
                    continue
                source_title = title or session_titles.get(str(row.get("session_id", ""))) or table
                for col, value in row.items():
                    if isinstance(value, str) and ("todo" in value.lower() or "fixme" in value.lower() or "follow" in value.lower() or "action" in value.lower()):
                        result["todos"].extend(find_todos(value, truncate(source_title, 90)))
    finally:
        conn.close()
    result["topics"] = result["topics"][:10]
    result["todos"] = dedupe_dicts(result["todos"], ("source", "item"))[:20]
    return result


def dedupe_dicts(items, keys):
    """Deduplicate dictionaries by a tuple of keys while preserving order."""
    seen = set()
    out = []
    for item in items:
        marker = tuple(item.get(key) for key in keys)
        if marker in seen:
            continue
        seen.add(marker)
        out.append(item)
    return out


def file_datetime(path):
    """Return file modification time as UTC datetime."""
    try:
        return dt.datetime.fromtimestamp(os.path.getmtime(path), dt.timezone.utc)
    except OSError:
        return None


def extract_timestamp_from_text(text):
    """Find the first ISO-like timestamp in text."""
    match = re.search(r"\d{4}-\d{2}-\d{2}(?:[T ][0-9:.+-]+Z?)?", text or "")
    if match:
        return parse_datetime(match.group(0))
    return None


def job_name_from_file(path, text):
    """Infer a cron job name from content or filename."""
    for pat in (r"\bjob\s*[:=]\s*([A-Za-z0-9_.-]+)", r"\bname\s*[:=]\s*([A-Za-z0-9_.-]+)"):
        match = re.search(pat, text or "", re.I)
        if match:
            return match.group(1)
    name = os.path.splitext(os.path.basename(path))[0]
    name = re.sub(r"^\d{4}-\d{2}-\d{2}[-_]?", "", name)
    return name or "unknown"


def load_cron_status(directory, since_dt):
    """Parse cron output files for success, failure, and overdue markers."""
    result = {"success": 0, "failed": [], "overdue": [], "ran": 0}
    if not directory or not os.path.isdir(directory):
        return result
    paths = []
    for pattern in ("*.md", "*.txt", "*.log"):
        paths.extend(glob.glob(os.path.join(directory, pattern)))
    for path in sorted(set(paths)):
        text = safe_read(path)
        name = job_name_from_file(path, text)
        when = extract_timestamp_from_text(text) or file_datetime(path)
        in_window = when is None or when >= since_dt
        if OVERDUE_RE.search(text) or OVERDUE_RE.search(os.path.basename(path)):
            detail_match = re.search(r"(last ran \d+\s+(?:day|days|week|weeks) ago)", text, re.I)
            if not detail_match:
                detail_match = re.search(r"(overdue[^\n.]*)", text, re.I)
            detail = truncate(detail_match.group(1), 90) if detail_match else "marked overdue"
            result["overdue"].append({"job": name, "detail": detail})
        if not in_window:
            continue
        failed = FAIL_RE.search(text)
        succeeded = SUCCESS_RE.search(text)
        if failed:
            reason = truncate(failed.group(1), 60)
            result["failed"].append({"job": name, "reason": reason})
            result["ran"] += 1
        elif succeeded:
            result["success"] += 1
            result["ran"] += 1
    result["failed"] = dedupe_dicts(result["failed"], ("job", "reason"))
    result["overdue"] = dedupe_dicts(result["overdue"], ("job", "detail"))
    return result


def iter_memory_records(directory):
    """Yield memory JSON records with source path and mtime."""
    if not directory or not os.path.isdir(directory):
        return
    paths = glob.glob(os.path.join(directory, "*.json")) + glob.glob(os.path.join(directory, "**", "*.json"), recursive=True)
    for path in sorted(set(paths)):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        records = data if isinstance(data, list) else [data]
        for record in records:
            if isinstance(record, dict):
                yield path, record, file_datetime(path)


def load_memory_changes(directory, since_dt):
    """Summarize JSON memory records."""
    result = {"new": 0, "updated": 0, "briefs": []}
    for path, record, mtime in iter_memory_records(directory) or []:
        when = parse_datetime(pick_first(record, ["timestamp", "created_at", "updated_at", "time", "date"])) or mtime
        if when and when < since_dt:
            continue
        action = str(pick_first(record, ["action", "event", "type", "kind", "status"]) or "new").lower()
        brief = pick_first(record, ["fact", "memory", "content", "text", "summary", "title"])
        if ("update" in action or "fact" in action) and "new" not in action:
            result["updated"] += 1
            if brief:
                result["briefs"].append({"kind": "updated", "text": truncate(brief, 100)})
        else:
            result["new"] += 1
            if brief:
                result["briefs"].append({"kind": "new", "text": truncate(brief, 100)})
    result["briefs"] = dedupe_dicts(result["briefs"], ("kind", "text"))[:10]
    return result


def parse_log_line(line):
    """Extract timestamp, tool, and error type from one log line."""
    timestamp = extract_timestamp_from_text(line)
    tool = None
    try:
        obj = json.loads(line)
        if isinstance(obj, dict):
            timestamp = parse_datetime(pick_first(obj, ["timestamp", "time", "created_at"])) or timestamp
            tool = pick_first(obj, ["tool", "tool_name", "name"])
            message = " ".join(str(v) for v in obj.values())
        else:
            message = line
    except json.JSONDecodeError:
        message = line
    if not tool:
        for pattern in TOOL_RE_PATTERNS:
            match = pattern.search(line)
            if match:
                tool = match.group(1)
                break
    error_type = None
    lower = message.lower()
    if "rate limit" in lower:
        error_type = "rate limit"
    elif "timeout" in lower or "timed out" in lower:
        error_type = "timeout"
    elif FAIL_RE.search(message):
        error_type = "error"
    return timestamp, str(tool) if tool else None, error_type


def load_tool_usage(path, since_dt):
    """Summarize tool usage from a text or JSONL log."""
    result = {"total_calls": 0, "tools": [], "errors": 0, "error_types": {}}
    if not path or not os.path.isfile(path):
        return result
    counts = collections.Counter()
    errors = collections.Counter()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        lines = []
    for line in lines:
        timestamp, tool, error_type = parse_log_line(line)
        if timestamp and timestamp < since_dt:
            continue
        if tool:
            counts[tool] += 1
            result["total_calls"] += 1
        if error_type:
            errors[error_type] += 1
    result["tools"] = counts.most_common(10)
    result["errors"] = sum(errors.values())
    result["error_types"] = dict(errors)
    return result


def load_due_decisions(directory, now_date):
    """Find due decision reviews from Markdown files."""
    result = []
    if not directory or not os.path.isdir(directory):
        return result
    for path in sorted(glob.glob(os.path.join(directory, "*.md"))):
        text = safe_read(path)
        title_match = re.search(r"^#\s+(.+)$", text, re.M)
        status_match = re.search(r"(?:^##\s+Status\s*$\s*)([^\n]+)", text, re.I | re.M)
        review_match = re.search(r"Next review\s*:\s*(\d{4}-\d{2}-\d{2})", text, re.I)
        status = status_match.group(1).strip().lower() if status_match else ""
        if "superseded" in status or "deprecated" in status:
            continue
        due = parse_date(review_match.group(1) if review_match else "")
        if due and due <= now_date:
            result.append({"title": truncate(title_match.group(1) if title_match else os.path.basename(path), 100), "date": due.isoformat()})
    return result[:20]


def build_digest(args):
    """Build the digest data model."""
    config = load_config_file(getattr(args, "config", None))
    since_text = getattr(args, "since", None) or config.get("default_since") or "24h"
    now = parse_datetime(getattr(args, "now", None)) or utc_now()
    since_delta = parse_since(since_text)
    since_dt = now - since_delta
    sections = split_sections(getattr(args, "sections", None) or config.get("sections"))
    sources = resolve_sources(args, config)
    existing_sources = {key: source_exists(key, path) for key, path in sources.items()}
    template_mode = not any(existing_sources.values())

    data = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "since": since_text,
        "window_label": window_label(since_text),
        "sections": sections,
        "template_mode": template_mode,
        "sources": {key: {"path": path, "exists": existing_sources[key]} for key, path in sources.items()},
        "sessions": {"completed": 0, "started": 0, "topics": [], "todos": []},
        "cron": {"success": 0, "failed": [], "overdue": [], "ran": 0},
        "memory": {"new": 0, "updated": 0, "briefs": []},
        "tools": {"total_calls": 0, "tools": [], "errors": 0, "error_types": {}},
        "outstanding": {"decisions_due": [], "todos": []},
    }
    if existing_sources.get("sessions_db"):
        data["sessions"] = load_session_activity(sources["sessions_db"], since_dt)
        data["outstanding"]["todos"].extend(data["sessions"].get("todos", []))
    if existing_sources.get("cron_dir"):
        data["cron"] = load_cron_status(sources["cron_dir"], since_dt)
    if existing_sources.get("memory_dir"):
        data["memory"] = load_memory_changes(sources["memory_dir"], since_dt)
    if existing_sources.get("log_file"):
        data["tools"] = load_tool_usage(sources["log_file"], since_dt)
        data["outstanding"]["todos"].extend(find_todos(safe_read(sources["log_file"]), "log file"))
    if existing_sources.get("decisions_dir"):
        data["outstanding"]["decisions_due"] = load_due_decisions(sources["decisions_dir"], now.date())
    data["outstanding"]["todos"] = dedupe_dicts(data["outstanding"]["todos"], ("source", "item"))[:20]
    return data


def plural(count, singular, plural_word=None):
    """Return a count + correctly pluralized noun."""
    if count == 1:
        return "1 " + singular
    return "%d %s" % (count, plural_word or singular + "s")


def render_markdown(data):
    """Render digest data as Markdown."""
    sections = data["sections"]
    lines = ["## 📋 Activity Digest — %s" % data["window_label"], ""]
    if data.get("template_mode"):
        lines.extend([
            "> Template mode: no configured data sources were found. Fill the placeholders from your agent platform's session, scheduler, memory, and log tools.",
            "",
        ])
    if "sessions" in sections:
        sess = data["sessions"]
        lines.append("### Sessions")
        if data.get("template_mode"):
            lines.extend(["- [ ] Sessions completed: _fill in count_", "- Topics: _fill in recent session titles_"])
        elif sess["started"] or sess["topics"]:
            lines.append("- %s completed" % plural(sess["completed"], "session"))
            lines.append("- %s started" % plural(sess["started"], "session"))
            if sess["topics"]:
                lines.append("- Topics: " + ", ".join('"%s"' % topic for topic in sess["topics"][:6]))
        else:
            lines.append("- No session activity found in the configured source.")
        lines.append("")
    if "cron" in sections:
        cron = data["cron"]
        lines.append("### Cron Jobs")
        if data.get("template_mode"):
            lines.extend(["- ✅ _fill in successful job count_", "- ❌ _fill in failed jobs, if any_", "- ⏰ _fill in overdue jobs, if any_"])
        else:
            lines.append("- ✅ %s ran successfully" % plural(cron["success"], "job"))
            if cron["failed"]:
                for item in cron["failed"]:
                    lines.append("- ❌ %s failed: %s" % (item["job"], item["reason"]))
            else:
                lines.append("- ❌ 0 jobs failed")
            if cron["overdue"]:
                for item in cron["overdue"]:
                    lines.append("- ⏰ %s overdue: %s" % (item["job"], item["detail"]))
            else:
                lines.append("- ⏰ 0 jobs overdue")
        lines.append("")
    if "memory" in sections:
        mem = data["memory"]
        lines.append("### Memory")
        if data.get("template_mode"):
            lines.extend(["- _fill in new memory count_", "- _fill in updated facts, if any_"])
        else:
            lines.append("- %s saved" % plural(mem["new"], "new memory", "new memories"))
            lines.append("- %s updated" % plural(mem["updated"], "fact"))
            for brief in mem["briefs"][:3]:
                lines.append('- %s: "%s"' % (brief["kind"].capitalize(), brief["text"]))
        lines.append("")
    if "tools" in sections:
        tools = data["tools"]
        lines.append("### Tool Usage")
        if data.get("template_mode"):
            lines.extend(["- Most used: _fill in tool counts_", "- Errors: _fill in error count_"])
        else:
            if tools["tools"]:
                most = ", ".join("%s (%d)" % (name, count) for name, count in tools["tools"][:5])
                lines.append("- Most used: " + most)
            else:
                lines.append("- Most used: none found")
            if tools["error_types"]:
                err_detail = ", ".join("%d %s" % (count, name) for name, count in sorted(tools["error_types"].items()))
                lines.append("- Errors: %d (%s)" % (tools["errors"], err_detail))
            else:
                lines.append("- Errors: %d" % tools["errors"])
            lines.extend(["", "```text", "Total API/tool calls: %d" % tools["total_calls"], "```"])
        lines.append("")
    if "outstanding" in sections:
        out = data["outstanding"]
        lines.append("### Outstanding")
        if data.get("template_mode"):
            lines.extend(["- _fill in due decision reviews_", "- _fill in TODOs or unresolved tasks from recent sessions_"])
        else:
            if out["decisions_due"]:
                lines.append("- %s due for review (from decision-log)" % plural(len(out["decisions_due"]), "decision"))
                for item in out["decisions_due"][:5]:
                    lines.append('  - "%s" due %s' % (item["title"], item["date"]))
            else:
                lines.append("- 0 decisions due for review")
            if out["todos"]:
                for item in out["todos"][:8]:
                    lines.append('- TODO from %s: "%s"' % (item["source"], item["item"]))
            else:
                lines.append("- No TODOs found in configured sources")
        lines.append("")
    lines.extend(["---", "Generated at %s" % data["generated_at"]])
    return "\n".join(lines).rstrip() + "\n"


def render_text(data):
    """Render digest data as plain text."""
    lines = ["Activity Digest - %s" % data["window_label"], ""]
    if data.get("template_mode"):
        lines.append("Template mode: no configured data sources were found.")
        lines.append("")
    if "sessions" in data["sections"]:
        sess = data["sessions"]
        lines.append("Sessions: %d completed, %d started" % (sess["completed"], sess["started"]))
        if sess["topics"]:
            lines.append("Topics: " + ", ".join(sess["topics"][:6]))
    if "cron" in data["sections"]:
        cron = data["cron"]
        lines.append("Cron Jobs: %d succeeded, %d failed, %d overdue" % (cron["success"], len(cron["failed"]), len(cron["overdue"])))
    if "memory" in data["sections"]:
        mem = data["memory"]
        lines.append("Memory: %d new, %d updated" % (mem["new"], mem["updated"]))
    if "tools" in data["sections"]:
        tools = data["tools"]
        most = ", ".join("%s (%d)" % (name, count) for name, count in tools["tools"][:5]) or "none"
        lines.append("Tool Usage: %d calls; most used: %s; errors: %d" % (tools["total_calls"], most, tools["errors"]))
    if "outstanding" in data["sections"]:
        out = data["outstanding"]
        lines.append("Outstanding: %d decisions due, %d TODOs" % (len(out["decisions_due"]), len(out["todos"])))
        for item in out["todos"][:5]:
            lines.append("- TODO from %s: %s" % (item["source"], item["item"]))
    lines.extend(["", "Generated at %s" % data["generated_at"]])
    return "\n".join(lines).rstrip() + "\n"


def render_digest(data, fmt):
    """Render digest in the requested format."""
    if fmt == "json":
        return json.dumps(data, indent=2, sort_keys=True) + "\n"
    if fmt == "text":
        return render_text(data)
    return render_markdown(data)


def write_output(text, path):
    """Write output to a file or stdout."""
    if path:
        parent = os.path.dirname(os.path.abspath(path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        print(text, end="")


def command_generate(args):
    """Generate a digest and write it."""
    data = build_digest(args)
    text = render_digest(data, args.format)
    write_output(text, args.output)
    return 0


def command_config(args):
    """Print source configuration."""
    rows = summarize_config(args)
    print("Scheduled summary configuration")
    print("--------------------------------")
    for row in rows:
        status = "will read" if row["exists"] else "skipped"
        if not row["configured"]:
            reason = "not configured"
        elif not row["exists"]:
            reason = "path not found"
        else:
            reason = row["path"]
        print("%s: %s (%s; env %s)" % (row["label"], status, reason, row["env"]))
    return 0


def command_init(args):
    """Create a JSON config template."""
    path = args.output
    template = {
        "default_since": "24h",
        "sections": "sessions,cron,memory,tools,outstanding",
        "format": "markdown",
        "output": "",
        "sessions_db": "",
        "cron_dir": "",
        "memory_dir": "",
        "log_file": "",
        "decisions_dir": "",
        "notes": [
            "Fill in any paths your agent platform exposes.",
            "Leave unknown sources blank; they will be skipped.",
            "Review first outputs for sensitive data before sending to chat platforms.",
        ],
    }
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(template, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("Wrote config template to %s" % path)
    return 0


def build_parser():
    """Build the argparse parser."""
    parser = argparse.ArgumentParser(description="Generate scheduled cross-session activity digests.")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate a digest summary")
    gen.add_argument("--since", default="24h", help="Relative time window such as 24h, 7d, or 2w")
    gen.add_argument("--sections", default=None, help="Comma-separated sections: sessions,cron,memory,tools,outstanding")
    gen.add_argument("--format", choices=["markdown", "json", "text"], default="markdown", help="Output format")
    gen.add_argument("--output", default="", help="Optional output file")
    gen.add_argument("--sessions-db", default="", help="SQLite session database path")
    gen.add_argument("--cron-dir", default="", help="Directory of cron output .md/.txt/.log files")
    gen.add_argument("--memory-dir", default="", help="Directory of memory JSON files")
    gen.add_argument("--log-file", default="", help="Text or JSONL log file")
    gen.add_argument("--decisions-dir", default="", help="Optional directory of Markdown decision records")
    gen.add_argument("--config", default="", help="Optional JSON config file")
    gen.add_argument("--now", default="", help=argparse.SUPPRESS)
    gen.set_defaults(func=command_generate)

    cfg = sub.add_parser("config", help="Show current configuration")
    cfg.add_argument("--sessions-db", default="", help="SQLite session database path")
    cfg.add_argument("--cron-dir", default="", help="Directory of cron output files")
    cfg.add_argument("--memory-dir", default="", help="Directory of memory JSON files")
    cfg.add_argument("--log-file", default="", help="Text or JSONL log file")
    cfg.add_argument("--decisions-dir", default="", help="Optional directory of Markdown decision records")
    cfg.add_argument("--config", default="", help="Optional JSON config file")
    cfg.set_defaults(func=command_config)

    init = sub.add_parser("init", help="Create a config file template")
    init.add_argument("--output", default=".summary-config.json", help="Config path to create")
    init.set_defaults(func=command_init)
    return parser


def main(argv=None):
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if getattr(args, "sections", None):
            split_sections(args.sections)
        if getattr(args, "since", None):
            parse_since(args.since)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
