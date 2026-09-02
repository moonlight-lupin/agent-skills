#!/usr/bin/env python3
"""Aggregate input-token audit for a Hermes instance.

Read-only: state.db (session_model_usage, sessions, messages) + cron usage ledger.
Pure stdlib. Prints a report.

Usage:
  audit.py [--days 30] [--db ~/.hermes/state.db]
           [--cron-audit ~/.hermes/cron/usage_audit.jsonl] [--jobs ~/.hermes/cron/jobs.json]
"""
import argparse
import collections
import json
import os
import sqlite3
import sys
import time
import urllib.parse

HERMES = os.path.expanduser("~/.hermes")


def audit_sessions(db_path, cutoff):
    if not os.path.exists(db_path):
        print(f"[sessions] DB not found: {db_path}")
        return
    uri = pathlib_uri(db_path) + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=15)

    print(f"\n=== task/model/provider breakdown, window attributed by last_seen ({db_path}) ===")
    print("  NOTE: task rows are cumulative per session; 'input' semantics vary by provider wire")
    print("  format (see SKILL.md pitfalls). If cache_read > input for a row, that provider")
    print("  reports cache IN ADDITION to input: true prompt volume ~ input + cache_read + cache_write.")
    try:
        rows = conn.execute("""SELECT task, model, billing_provider, SUM(api_call_count), SUM(input_tokens),
                                 SUM(output_tokens), SUM(cache_read_tokens), SUM(cache_write_tokens),
                                 SUM(estimated_cost_usd), SUM(actual_cost_usd), COUNT(*)
                          FROM session_model_usage WHERE last_seen >= ?
                          GROUP BY task, model, billing_provider ORDER BY SUM(input_tokens) DESC""",
                            (cutoff,)).fetchall()
    except sqlite3.OperationalError as e:
        print(f"  table missing or error: {e}")
        conn.close()
        return
    tot_in = tot_cr = tot_cw = tot_calls = tot_cost = 0
    for task, model, prov, calls, it, ot, cr, cw, est, act, n in rows:
        calls = calls or 0; it = it or 0; cr = cr or 0; cw = cw or 0
        tot_in += it; tot_cr += cr; tot_cw += cw; tot_calls += calls
        tot_cost += (act if (act := act or est) is not None else (est or 0)) if False else (act if (act := (act or est)) is not None else 0)
        avg = it / calls if calls else 0
        flag = " [cache-added-to-input]" if cr > it and cr > 0 else ""
        print(f"  {str(task or '(main)'):20} {str(model):26} {str(prov or '-'):14} calls={calls:>6} "
              f"input={it:>13,} cache_read={cr:>11,} cache_write={cw:>9,} avg/call={avg:>9,.0f}"
              f" est_usd={(est or 0):>8.2f}{flag}")
    print(f"  TOTAL input={tot_in:,} cache_read={tot_cr:,} cache_write={tot_cw:,} calls={tot_calls:,}")
    print("  cache_read is NOT a subset of input on all providers — see note above.")

    print("\n--- top sessions by input (started or active within window) ---")
    try:
        rows = conn.execute("""SELECT s.id, s.source, s.chat_type, s.title, s.api_call_count,
                                 s.input_tokens, s.cache_read_tokens
                          FROM sessions s
                          WHERE s.started_at >= ? OR s.last_activity_at >= ?
                          ORDER BY s.input_tokens DESC LIMIT 10""", (cutoff, cutoff)).fetchall()
        for sid, src, ct, title, calls, it, cr in rows:
            flag = " FLAG>40M" if (it or 0) > 40_000_000 else ""
            flag += " FLAG>200calls" if (calls or 0) > 200 else ""
            print(f"  {sid} {str(src):8} calls={calls or 0:>5} input={it or 0:>13,} "
                  f"cr={cr or 0:>10,} {str(title)[:40]!r}{flag}")
    except sqlite3.OperationalError as e:
        print(f"  sessions table error: {e}")

    try:
        # Weighted per-call average: SUM(input)/SUM(calls), not mean of ratios.
        row = conn.execute("""SELECT SUM(input_tokens)*1.0/SUM(api_call_count), SUM(api_call_count), COUNT(*)
                         FROM sessions WHERE (started_at>=? OR last_activity_at>=?) AND api_call_count>=200""",
                          (cutoff, cutoff)).fetchone()
        if row and row[1]:
            print(f"\n  weighted avg tokens/call (sessions >=200 calls): {row[0]:,.0f} over {row[1]} calls in {row[2]} sessions")
        row = conn.execute("""SELECT SUM(input_tokens)*1.0/SUM(api_call_count), SUM(api_call_count), COUNT(*)
                         FROM sessions WHERE (started_at>=? OR last_activity_at>=?) AND api_call_count < 50""",
                          (cutoff, cutoff)).fetchone()
        if row and row[1]:
            print(f"  weighted avg tokens/call (sessions <50 calls — the fixed-floor case): {row[0]:,.0f} over {row[1]} calls in {row[2]} sessions")
    except sqlite3.OperationalError:
        pass

    print("\n--- tool-result volume (ACTIVE messages only; compacted/inactive excluded) ---")
    tool_chars = non_tool_chars = 0
    try:
        rows = conn.execute("""SELECT m.tool_name, COUNT(*), SUM(LENGTH(m.content))
                          FROM messages m JOIN sessions s ON m.session_id=s.id
                          WHERE (s.started_at>=? OR s.last_activity_at>=?)
                            AND m.active=1 AND m.tool_name IS NOT NULL AND m.tool_name!=''
                          GROUP BY m.tool_name ORDER BY SUM(LENGTH(m.content)) DESC LIMIT 10""",
                            (cutoff, cutoff)).fetchall()
        tool_chars = sum((r[2] or 0) for r in rows)
        for tn, n, sz in rows:
            print(f"  {str(tn):24} n={n:>6} chars={sz or 0:>12,}")
        row = conn.execute("""SELECT COALESCE(SUM(LENGTH(m.content)),0)
                          FROM messages m JOIN sessions s ON m.session_id=s.id
                          WHERE (s.started_at>=? OR s.last_activity_at>=?)
                            AND m.active=1 AND (m.tool_name IS NULL OR m.tool_name='')""",
                           (cutoff, cutoff)).fetchone()
        non_tool_chars = row[0]
        if (tool_chars + non_tool_chars) > 0:
            share = 100 * tool_chars / (tool_chars + non_tool_chars)
            print(f"  tool chars share of stored active content: {share:.0f}% "
                  f"(tool {tool_chars:,} / non-tool {non_tool_chars:,}; stored ~= upper bound on sent)")
    except sqlite3.OperationalError as e:
        print(f"  messages table error: {e}")

    try:
        row = conn.execute("""SELECT COUNT(*), SUM(LENGTH(m.content))
                         FROM messages m JOIN sessions s ON m.session_id=s.id
                         WHERE (s.started_at>=? OR s.last_activity_at>=?) AND m.active=1
                           AND m.tool_name IS NOT NULL AND m.tool_name!=''
                           AND LENGTH(m.content) > 50000""", (cutoff, cutoff)).fetchone()
        n, sz = row[0], row[1] or 0
        print(f"  active results over 50k chars (tool_output.max_bytes default): {n} ({sz:,} chars)")
    except sqlite3.OperationalError:
        pass

    try:
        row = conn.execute("""SELECT COUNT(*), COALESCE(AVG(LENGTH(m.content)),0)
                         FROM messages m JOIN sessions s ON m.session_id=s.id
                         WHERE (s.started_at>=? OR s.last_activity_at>=?) AND m.active=1
                           AND m.tool_name='skill_view'""", (cutoff, cutoff)).fetchone()
        print(f"  skill_view loads (active): {row[0]}, avg chars {row[1]:,.0f}")
    except sqlite3.OperationalError:
        pass

    conn.close()


def pathlib_uri(db_path):
    """Build a file: URI with the path properly encoded."""
    p = os.path.abspath(db_path)
    return "file:" + urllib.parse.quote(p)


def audit_cron(ledger, jobs_path, cutoff):
    if not os.path.exists(ledger):
        print(f"\n[cron] ledger not found: {ledger}")
        return
    names = {}
    if os.path.exists(jobs_path):
        try:
            d = json.load(open(jobs_path))
            jobs = d["jobs"] if isinstance(d, dict) and "jobs" in d else (d if isinstance(d, list) else [])
            for j in jobs:
                if isinstance(j, dict):
                    names[j.get("id") or j.get("job_id")] = j.get("name")
            if not names:
                print("  note: jobs.json parsed but contained no job names")
        except Exception as e:
            print(f"  jobs.json parse error: {e}")

    cutoff_str = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(cutoff))
    byjob = collections.defaultdict(lambda: [0, 0, 0])  # tokens, fires, max
    for line in open(ledger):
        try:
            r = json.loads(line)
        except Exception:
            continue
        ts = (r.get("ts") or "").replace("T", " ")[:19]  # normalize ISO-T to space for string compare
        if ts < cutoff_str:
            continue
        pt = r.get("prompt_tokens") or 0
        e = byjob[r.get("job_id") or "(unknown job)"]
        e[0] += pt; e[1] += 1; e[2] = max(e[2], pt)
    print(f"\n=== cron ledger (fires since {cutoff_str} UTC; prompt_tokens semantics per fire: see SKILL.md) ===")
    tot = 0
    for jid, (tokens, fires, mx) in sorted(byjob.items(), key=lambda kv: -kv[1][0]):
        tot += tokens
        flag = " FLAG>2M-avg" if fires and tokens / fires > 2_000_000 else ""
        print(f"  {str(jid)[:12]:12} {str(names.get(jid, jid if jid == '(unknown job)' else '?'))[:34]:34} fires={fires:>3} "
              f"tokens={tokens:>13,} avg={tokens // max(fires, 1):>11,} max={mx:>11,}{flag}")
    print(f"  TOTAL cron prompt tokens: {tot:,}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--db", default=os.path.join(HERMES, "state.db"))
    ap.add_argument("--cron-audit", default=os.path.join(HERMES, "cron", "usage_audit.jsonl"))
    ap.add_argument("--jobs", default=os.path.join(HERMES, "cron", "jobs.json"))
    args = ap.parse_args()
    cutoff = time.time() - args.days * 86400
    print(f"# Input token audit — last {args.days} days — generated {time.strftime('%Y-%m-%d %H:%M %Z', time.localtime())}")
    audit_sessions(args.db, cutoff)
    audit_cron(args.cron_audit, args.jobs, cutoff)
    print("\n# Interpretation levers: see SKILL.md (input-token-analysis)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
