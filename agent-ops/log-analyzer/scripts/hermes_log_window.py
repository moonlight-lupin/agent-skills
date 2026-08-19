#!/usr/bin/env python3
"""Windowed Hermes profile-log analyzer.

Handles the comma-millisecond Python-logging timestamp format that
analyze_logs.py misses, applies a time window, de-duplicates multiline
tracebacks (counts first-lines only), and prints error/warning clusters,
MCP reconnect spam, timeouts, and rate-limit hits.

Intended for ad-hoc use alongside analyze_logs.py when --since silently
no-ops on Hermes logs. Run:

    python scripts/hermes_log_window.py /root/.hermes/profiles/<name>/logs/agent.log [hours]

Default window: 96h. Also scans errors.log and gateway.log if present in the
same directory.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}\s+(\w+)\s")
LEVEL_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}\s+(\w+)\s")


def norm(line: str) -> str:
    s = line.strip()
    s = re.sub(r"\d{8}_\d{6}_[a-f0-9]+", "[SID]", s)
    s = re.sub(r"ref:\s*[a-f0-9-]+", "ref: [ID]", s)
    s = re.sub(r"https?://\S+", "[URL]", s)
    s = re.sub(r"\b\d+\b", "[N]", s)
    return s[:160]


def in_window(line, start, end):
    m = TS_RE.match(line)
    if not m:
        return None
    try:
        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
        return ts if start <= ts <= end else None
    except ValueError:
        return None


def analyze(path: Path, start: datetime, end: datetime):
    if not path.exists():
        print(f"\n=== {path.name}: missing ===")
        return
    err_clusters = Counter()
    warn_clusters = Counter()
    timeouts = Counter()
    rate_limits = Counter()
    mcp_fails = Counter()
    tracebacks = 0
    levels = Counter()
    total = in_win = 0
    with open(path, errors="replace") as f:
        for line in f:
            total += 1
            ts = in_window(line, start, end)
            if ts is None:
                continue
            in_win += 1
            ml = LEVEL_RE.match(line)
            lvl = ml.group(1) if ml else "?"
            levels[lvl] += 1
            key = norm(line)
            if lvl == "ERROR":
                err_clusters[key] += 1
            elif lvl in ("WARNING", "WARN"):
                warn_clusters[key] += 1
            if "Traceback (most recent call last)" in line:
                tracebacks += 1
            if any(k in line.lower() for k in ("timed out", "timeout", "apitimeouterror")):
                tm = re.search(r"(browser_navigate|browser_vision|execute_code|terminal|web_search|web_extract)", line)
                timeouts[tm.group(1) if tm else "unspecified"] += 1
            if "429" in line or "too many requests" in line.lower() or "quota exceeded" in line.lower():
                rate_limits[line.strip()[:120]] += 1
            if "MCP server" in line and "initial connection failed" in line:
                mm = re.search(r"MCP server '([^']+)'", line)
                mcp_fails[mm.group(1) if mm else "?"] += 1
    print(f"\n========== {path.name} ==========")
    print(f"Lines: {total} | In window ({start:%Y-%m-%d %H:%M} → {end:%Y-%m-%d %H:%M}): {in_win}")
    print(f"Levels: {dict(levels)}")
    print(f"Distinct traceback chains: {tracebacks}")
    print("\n--- Error clusters (top 10) ---")
    for msg, n in err_clusters.most_common(10):
        print(f"  [{n:3d}] {msg}")
    print("\n--- Warning clusters (top 10) ---")
    for msg, n in warn_clusters.most_common(10):
        print(f"  [{n:3d}] {msg}")
    print("\n--- Timeouts by tool ---")
    for t, n in timeouts.most_common():
        print(f"  {t}: {n}")
    print("\n--- Rate limit hits ---")
    for msg, n in rate_limits.most_common(5):
        print(f"  [{n}] {msg}")
    print("\n--- MCP connection failures ---")
    for s, n in mcp_fails.most_common():
        print(f"  {s}: {n}")


def main():
    if len(sys.argv) < 2:
        print("usage: hermes_log_window.py <profile_logs_dir> [hours]", file=sys.stderr)
        sys.exit(2)
    logdir = Path(sys.argv[1])
    hours = int(sys.argv[2]) if len(sys.argv) > 2 else 96
    end = datetime.now()
    start = end - timedelta(hours=hours)
    for name in ("agent.log", "errors.log", "gateway.log"):
        analyze(logdir / name, start, end)


if __name__ == "__main__":
    main()