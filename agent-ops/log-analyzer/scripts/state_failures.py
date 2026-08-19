#!/usr/bin/env python3
"""Hermes state.db failure-rate monitor.

Computes per-tool success/failure rates from a Hermes profile's `state.db`
(sessions/messages tables) using STRUCTURED failure signals, not naive
regex-over-content.

Why structured? Naive regex classification (as in Yonkoo11/hermes-dojo's
monitor.py) flags any tool result that merely MENTIONS error words. On the
real MH profile state.db this produced absurd rates (read_file 70% failure)
when the true rate is 0%. JSON-mode tools (terminal, process, execute_code,
patch, read_file, ...) carry an `exit_code` field — the only reliable signal.
Text-mode tools (web_search, web_extract, browser_*) get a narrow fatal-marker
list; a benign page mentioning "exceptions" is NOT a failure.

Cron-compatible: --quiet exits 0 with no stdout when no failures are found.

Usage:
    python3 state_failures.py [--db ~/.hermes/state.db] [--days 7] [--json] [--quiet]
"""

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_DB = str(Path.home() / ".hermes" / "state.db")

# Narrow fatal markers for TEXT-mode tool results. Deliberately short:
# content that merely discusses error handling must NOT match.
TEXT_FATAL_MARKERS = [
    "command not found",
    "no such file or directory",
    "permission denied",
    "traceback (most recent call last)",
    "failed to connect",
    "connection refused",
    "econnrefused",
    "no such host",
    "not found",
]


def classify_result(content):
    """Classify one tool result as success/failure.

    Returns (mode, is_failure, snippet):
      mode: "json" | "text" | "empty"
      is_failure: True only on a structured exit_code != 0 (json) or a
                  narrow fatal marker (text).
      snippet: short error text for reporting ("" for successes).
    """
    content = (content or "").strip()
    if not content:
        return "empty", False, ""

    if content.startswith("{") or content.startswith("["):
        try:
            d = json.loads(content)
            if isinstance(d, dict):
                ec = d.get("exit_code")
                if ec is None and isinstance(d.get("output"), dict):
                    ec = d["output"].get("exit_code")
                if ec is not None:
                    if ec != 0:
                        out = d.get("output") or d.get("error") or ""
                        if isinstance(out, dict):
                            out = out.get("output") or out.get("error") or ""
                        return "json", True, str(out)[:300]
                    return "json", False, ""
            return "json", False, ""  # no exit_code → no failure signal
        except (json.JSONDecodeError, TypeError):
            pass  # malformed JSON → treat as text below

    low = content.lower()
    for marker in TEXT_FATAL_MARKERS:
        if marker in low:
            return "text", True, content[:300]
    return "text", False, ""


def categorize_failure(output):
    """Bucket a failure's output into an actionable category."""
    low = (output or "").lower()
    if "timed out" in low or "timeout" in low or "deadline exceeded" in low:
        return "timeout"
    if any(k in low for k in
           ["connection refused", "econnrefused", "no such host",
            "unreachable", "failed to connect", "network is unreachable"]):
        return "network"
    if "command not found" in low:
        return "command_not_found"
    if "permission denied" in low or "eacces" in low:
        return "permission"
    if "no such file" in low or "no such directory" in low or "enoent" in low:
        return "not_found"
    if "traceback" in low or "error:" in low or "exit status" in low:
        return "explicit_error"
    return "other"


def analyze_state_db(db_path, days=7, min_calls=5):
    """Analyze tool results in a Hermes state.db over the window.

    Returns a dict with per-tool stats, failure categories, and top tools
    (ranked by failure rate, requiring >= min_calls in the window).
    """
    if not Path(db_path).exists():
        return {"error": f"state.db not found at {db_path}"}

    cutoff = time.time() - days * 86400

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT content, tool_name FROM messages "
            "WHERE role='tool' AND tool_name IS NOT NULL AND timestamp > ?",
            (cutoff,),
        ).fetchall()

        sessions = 0
        try:
            sessions = conn.execute(
                "SELECT COUNT(*) AS n FROM sessions WHERE started_at > ?",
                (cutoff,),
            ).fetchone()["n"]
        except sqlite3.Error:
            sessions = 0  # schema may lack started_at; best effort
        conn.close()
    except sqlite3.Error as e:
        return {"error": f"failed to read state.db: {e}"}

    tool_stats = defaultdict(lambda: {"total": 0, "failures": 0})
    categories = defaultdict(lambda: {"count": 0, "tools": Counter()})
    failures = []

    for r in rows:
        tool = r["tool_name"]
        mode, is_fail, snippet = classify_result(r["content"] or "")
        tool_stats[tool]["total"] += 1
        if is_fail:
            tool_stats[tool]["failures"] += 1
            cat = categorize_failure(snippet)
            categories[cat]["count"] += 1
            categories[cat]["tools"][tool] += 1
            failures.append({"tool": tool, "category": cat, "snippet": snippet[:200]})

    tools = []
    for name, s in tool_stats.items():
        rate = 100.0 if s["total"] == 0 else round(100 * (1 - s["failures"] / s["total"]), 1)
        tools.append({
            "tool": name,
            "total": s["total"],
            "failures": s["failures"],
            "success_rate": rate,
        })

    # Rank by failure rate; only tools with enough samples in the window.
    ranked = [t for t in tools if t["total"] >= min_calls and t["failures"] > 0]
    ranked.sort(key=lambda t: (-t["failures"] / t["total"], -t["failures"]))

    cat_list = []
    for name, c in sorted(categories.items(), key=lambda kv: -kv[1]["count"]):
        cat_list.append({
            "category": name,
            "count": c["count"],
            "tools": dict(c["tools"].most_common(5)),
        })

    return {
        "db": db_path,
        "days": days,
        "sessions_analyzed": sessions,
        "tool_calls": sum(s["total"] for s in tool_stats.values()),
        "failures": sum(s["failures"] for s in tool_stats.values()),
        "overall_success_rate": (
            round(100 * (1 - sum(s["failures"] for s in tool_stats.values())
                         / max(sum(s["total"] for s in tool_stats.values()), 1)), 1)
        ),
        "tools": sorted(tools, key=lambda t: -t["total"]),
        "top_tools": ranked[:10],
        "categories": cat_list,
        "failure_samples": failures[:10],
    }


def print_dashboard(data):
    if "error" in data:
        print(f"Error: {data['error']}")
        return
    print("=" * 60)
    print("  STATE.DB FAILURE-RATE ANALYSIS")
    print("=" * 60)
    print(f"  DB:            {data['db']}")
    print(f"  Window:        last {data['days']} days")
    print(f"  Sessions:      {data['sessions_analyzed']}")
    print(f"  Tool calls:    {data['tool_calls']}")
    print(f"  Failures:      {data['failures']}")
    print(f"  Success rate:  {data['overall_success_rate']}%")
    print()
    if data["top_tools"]:
        print("  TOP FAILING TOOLS (>=5 calls in window):")
        print("  " + "-" * 56)
        for t in data["top_tools"]:
            print(f"  {t['tool']}: {t['success_rate']}% ({t['failures']}/{t['total']} failures)")
    else:
        print("  No tools with >=5 calls and failures in the window.")
    if data["categories"]:
        print("\n  FAILURE CATEGORIES:")
        for c in data["categories"]:
            tools = ", ".join(f"{k}×{v}" for k, v in c["tools"].items())
            print(f"  • {c['category']}: {c['count']}  ({tools})")
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Hermes state.db failure-rate monitor")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to state.db")
    parser.add_argument("--days", type=int, default=7, help="Analysis window in days")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--quiet", action="store_true",
                        help="Cron mode: no output when no failures (exit 0)")
    args = parser.parse_args()

    data = analyze_state_db(args.db, days=args.days)

    if "error" in data:
        print(f"Error: {data['error']}")
        sys.exit(1)

    if args.quiet:
        if data["failures"] == 0:
            return  # silent
        print(json.dumps(data, indent=2, default=str))
    elif args.json:
        print(json.dumps(data, indent=2, default=str))
    else:
        print_dashboard(data)


if __name__ == "__main__":
    main()
