# Auditing a Hermes Profile's Logs and Skill Usage

When you need a windowed performance/error/skill-usage report for a specific
Hermes profile (e.g. the Jing profile cron monitor), the agent.log completion
lines do NOT carry the skill-name argument — they only log
`tool skill_view completed (0.05s, 13890 chars)`. To get skill names and a
full tool-call breakdown, query the profile's own `state.db`.

## Where profile logs live

```
/root/.hermes/logs/                     # default (MH) profile
/root/.hermes/profiles/<name>/logs/    # named profile
  ├── agent.log          # INFO+ — tool completions, turn ends, API calls
  ├── errors.log         # WARNING+ — deduped error stream
  └── gateway.log       # gateway lifecycle, telegram reconnects, MCP
```

Old/stale copies may exist at `/root/.hermes/profiles/<name>/.hermes-<name>/logs/`
— ignore those; the active logs are under `profiles/<name>/logs/`.

## The timestamp gotcha (why `--since` silently no-ops)

Hermes Python-logging lines look like:

```
2026-07-06 12:30:45,123 INFO hermes_cli.plugins: Plugin 'browser' ...
```

`analyze_logs.py` recognizes `YYYY-MM-DD HH:MM:SS LEVEL …` and ISO-8601, but
NOT the comma-millisecond + space-level form above. When the regex misses,
lines fall to the unstructured fallback (`timestamp=null`). `--since` cannot
filter null-timestamp lines, so the **entire unrotated file is scanned** and
every cluster reports `First: unknown / Last: unknown`.

Symptoms: error/traceback counts wildly exceed the true windowed count; the
error timeline says "No timestamped errors detected"; crashes are inflated
because each stack-trace continuation line counts as a separate crash.

**Fix:** run a small custom parser that handles the comma-ms format, applies
the window, and de-duplicates multiline tracebacks (count `Traceback (most
recent call last)` first-lines, not continuation frames). See
`scripts/hermes_log_window.py` for a ready-to-run windowed counter.

## Getting skill-usage and tool-call counts

The profile's `state.db` (SQLite) stores full tool-call arguments in the
`messages` table:

```python
import sqlite3, json
from collections import Counter
from datetime import datetime, timedelta

DB = f"/root/.hermes/profiles/{profile}/state.db"
END = datetime(2026, 7, 18, 15, 48, 27)
START = END - timedelta(days=4)
start_e, end_e = START.timestamp(), END.timestamp()

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
con.row_factory = sqlite3.Row
rows = con.execute("""
  SELECT tool_name, tool_calls, timestamp
  FROM messages
  WHERE timestamp >= ? AND timestamp <= ?
""", (start_e, end_e)).fetchall()

tool_counts = Counter()
skill_view_targets = Counter()
for r in rows:
    tc = r["tool_calls"]
    if tc:
        calls = json.loads(tc) if isinstance(tc, str) else tc
        if isinstance(calls, dict): calls = [calls]
        for c in calls:
            name = c.get("name") or c.get("function", {}).get("name")
            args = c.get("arguments") or c.get("function", {}).get("arguments") or {}
            if isinstance(args, str):
                try: args = json.loads(args)
                except: pass
            if name:
                tool_counts[name] += 1
                if name == "skill_view" and isinstance(args, dict):
                    sn = args.get("name")
                    if sn: skill_view_targets[sn] += 1
    elif r["tool_name"]:
        tool_counts[r["tool_name"]] += 1
```

`messages.timestamp` is a Unix epoch (REAL), not ISO — filter with
`timestamp >= start_epoch AND timestamp <= end_epoch`.

## Distinguishing profile-interactive sessions from cron sessions

Cron jobs that operate on a profile (e.g. a memory-curator cron targeting the
Jing profile) write their session IDs into `agent.log` but those sessions
live in the **default profile's** state.db, not the target profile's. If a
session ID from `agent.log` is missing from the profile's `state.db`, it was
a cross-profile cron, not the user's interactive use — exclude it from the
skill-usage count.