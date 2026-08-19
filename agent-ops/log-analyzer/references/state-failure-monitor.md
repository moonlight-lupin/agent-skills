# state_failures.py — Hermes state.db failure-rate monitor

`scripts/state_failures.py` computes per-tool success/failure rates from a
Hermes profile's `state.db` (`sessions` + `messages` tables).

## Provenance

Concept adapted from [Yonkoo11/hermes-dojo](https://github.com/Yonkoo11/hermes-dojo)
(MIT, Mar 2026) — a Hermes hackathon project whose `monitor.py`/`analyzer.py`
read `state.db` to find weak tools and skill gaps. We ported ONLY the
measurement concept (per-tool failure rates + root-cause categories) and
**deliberately NOT** the auto-fixer / GEPA self-evolution half (see
SkillsBench evidence in `skill-maintainer`: self-generated skills land below
the no-skills baseline; skills must stay human-directed). All code is ours —
none of Dojo's scripts were copied verbatim.

## Why structured exit_code instead of regex-over-content (the spike)

Running Dojo's `monitor.py` unmodified against the real MH profile `state.db`
produced garbage:

| Tool | Dojo regex claims | Structured truth |
|---|---|---|
| read_file | 70% failure | 0.1% (1/1139) |
| skill_view | 48.7% failure | 0% |
| overall success | 82.6% | 95.4% |

Root cause: Dojo flags any tool result whose text merely *mentions* an error
word. Real examples of false positives: a code-review page containing
"Error paths? Tests cover the change?", an academic text mentioning
"Scaled Error (Hyndman & Koehler 2006)". Our JSON-mode tool results
(`terminal`, `process`, `execute_code`, `read_file`, `patch`, ...) carry an
`exit_code` field — that is the only reliable failure signal. Text-mode tools
(`web_search`, `web_extract`, `browser_*`) get a narrow fatal-marker list
(`command not found`, `connection refused`, `traceback`, ...), so a benign
page that discusses "exceptions" is not counted as a failure.

## Usage

```bash
# Dashboard — last 7 days (default), any Hermes profile:
python3 scripts/state_failures.py
python3 scripts/state_failures.py --db ~/.hermes/profiles/jing/state.db --days 30

# JSON for pipelines / scheduled summary:
python3 scripts/state_failures.py --json

# Cron mode — exit 0, no stdout when zero failures:
python3 scripts/state_failures.py --quiet
```

## Output fields

- `sessions_analyzed` — count of sessions started in the window (best-effort;
  schema may lack `started_at` → 0).
- `tool_calls` / `failures` / `overall_success_rate` — window totals.
- `tools` — per-tool `total`, `failures`, `success_rate` (sorted by volume).
- `top_tools` — failure-ranked, only tools with ≥ `min_calls` (default 5)
  in the window — one-off failures don't drive recommendations.
- `categories` — failure buckets: `timeout`, `network`,
  `command_not_found`, `permission`, `not_found`, `explicit_error`, `other`,
  each with per-tool counts.
- `failure_samples` — first 10 failures with snippet + category.

## Interpretation notes (real data, 7-day window, Aug 2026)

- Overall success ~95.4% (422 failures / 9,207 calls).
- **timeout (58) is the single most actionable category** — ~55 of them are
  `terminal` foreground timeouts (tool caps at 600s; long builds/deploys hit
  it). Consider raising the cap for known-long commands or running them
  backgrounded.
- network (20) = connection refused/unreachable — check daemons on NAS/hosts.
- `other` (248) dominates and is mostly terminal failures with empty or
  unusual output — a refinement candidate (log the raw snippets, review
  quarterly for new markers).

## Pitfalls

1. **Never count "mentions error words" as failure.** This is the whole
   point of the structured approach. If you extend `TEXT_FATAL_MARKERS`,
   keep the list narrow and add a regression test (see
   `test_mention_of_error_word_is_NOT_failure`).
2. **`messages.timestamp` is Unix epoch (REAL), not ISO.** Filter with
   `time.time() - days*86400`.
3. **Rows are JSON sometimes, text other times.** The same tool column can
   hold both (web_search mixed in the spike). `classify_result` falls back
   from JSON parse to text markers — malformed JSON must not crash.
4. **`exit_code` can be nested** (`{"output": {"output": ..., "exit_code": N}}`
   from `process`). `classify_result` checks the nested shape.
5. **Read-only access.** The monitor opens `file:...?mode=ro` — safe to run
   against a live state.db while Hermes is running.
6. **Dojo's other signals** (user-correction regexes, skill-gap detection)
   were NOT ported: the correction patterns false-positive on our
   `[IMPORTANT: skill invoked]` wrapper messages, and the gap detection only
   had 11 hardcoded patterns. If we want correction mining later, it needs
   its own spike against real data first.
