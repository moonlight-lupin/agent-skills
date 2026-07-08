---
name: log-analyzer
description: "Parse agent log files to identify error patterns, rate limit hits, timeout clusters, tool failures, and component-level error counts. Produces a structured anomaly report. Cron-compatible — silent if no issues, alert digest if anomalies found."
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [logs, analysis, errors, patterns, anomalies, monitoring, debugging, cron]
  related_skills: [scheduled-summary, skill-maintainer]
---

# Log Analyzer

## Overview

Log viewers filter lines. This skill finds patterns.

Use it when an agent runtime, tool process, gateway, scheduler, or other service
has produced enough log output that individual `grep` hits no longer explain the
system behavior. The analyzer parses standard log lines, normalizes repeated
messages, groups errors by component and tool, and produces a structured anomaly
report that is suitable for debugging sessions or cron digests.

The script is intentionally lightweight and portable: it uses only Python's
standard library and works on any text log with timestamp, level, optional
component, and message fields. It also has a best-effort fallback for
unstructured logs.

## Quick Start

```bash
cd agent-ops/log-analyzer
python scripts/analyze_logs.py scan --log-file agent.log --since 24h
```

To write JSON for later Markdown rendering:

```bash
python scripts/analyze_logs.py scan --log-file agent.log --since 24h --output scan.json
python scripts/analyze_logs.py report --scan scan.json --output report.md
```

For cron-compatible anomaly detection:

```bash
python scripts/analyze_logs.py scan --log-file agent.log --since 24h --quiet
```

`--quiet` exits 0 and prints nothing when no anomalies are found. If anomalies
exist, it prints the JSON report so the scheduler can deliver the digest.

## What It Detects

1. **Error clusters** — the same normalized error message repeated 3+ times
   within the selected time window. URLs, IP addresses, and numbers are replaced
   with placeholders before grouping so repeated failures with changing IDs still
   cluster.
2. **Rate limit hits** — HTTP `429`, `rate limit`, `rate_limit`, `too many
   requests`, and `quota exceeded` patterns. The analyzer groups them by
   provider when it can detect a provider name.
3. **Timeout patterns** — `timeout`, `timed out`, `deadline exceeded`, and
   `connection timeout`. Results are grouped by detected tool name and include
   example URLs where present.
4. **Tool failures** — error lines grouped by tool name extracted from patterns
   such as `tool: terminal`, `tool_call: web_search`, `tool terminal failed`, or
   lines emitted by a `tools` component.
5. **Session crashes** — fatal errors, unhandled exceptions, stack traces,
   `Traceback`, `Exception`, and `segfault` markers. Multiline stack traces are
   grouped as one crash entry with nearby context.
6. **Component breakdown** — error and warning counts by component such as
   `gateway`, `agent`, `tools`, `cron`, or `unknown`.
7. **Error timeline** — error counts bucketed by hour to reveal spikes and
   regressions after deploys or scheduled jobs.

See `references/anomaly-types.md` for detection criteria and interpretation.

## Log Format Support

The parser handles standard log lines shaped like:

```text
2026-07-06 12:30:45 ERROR [gateway] Connection refused
2026-07-06T12:30:45Z ERROR gateway: Connection refused
12:30:45 ERROR Connection refused
```

It recognizes `ERROR`, `WARN`, `WARNING`, `INFO`, `DEBUG`, `FATAL`, and
`CRITICAL` levels. Components may appear in square brackets after the level or as
`component:` after the level. Time-only lines are anchored to the current day (or
to the supplied default date when called as a library). Unstructured lines fall
back to best-effort line-by-line scanning, so obvious `ERROR`/`WARN` strings are
still counted even when the timestamp cannot be parsed.

See `references/log-formats.md` for examples and guidance on adding custom
patterns.

## CLI Commands

### `scan` — analyze a log file for patterns

```bash
python scripts/analyze_logs.py scan --log-file LOGFILE [--since TIME] [--output report.json] [--quiet]
```

Options:

- `--log-file LOGFILE` — required path to the log file.
- `--since TIME` — optional time window: minutes/hours/days/weeks, e.g. `30m`,
  `1h`, `24h`, `7d`, `2w`; default is all lines.
- `--output report.json` — write JSON to a file instead of stdout.
- `--quiet` — cron mode: suppress output when no anomalies are found.

### `report` — render Markdown from scan JSON

```bash
python scripts/analyze_logs.py report --scan scan.json [--output report.md]
```

The report contains overview counts, one section per anomaly type, a component
breakdown table, and an hourly error timeline.

### `tail` — smart tail for recent lines

```bash
python scripts/analyze_logs.py tail --log-file LOGFILE [--lines N] [--since TIME]
```

The smart tail prints plain text with markers suitable for chat delivery:

- normal lines: no marker
- warnings: `⚠️`
- errors: `❌`
- repeated recent errors: `🔥` when the same normalized error is seen 3+ times

## Output Format

`scan` emits JSON with these top-level fields:

- `log_file`, `lines_analyzed`, `time_window`
- `anomalies.error_clusters`, `anomalies.rate_limits`, `anomalies.timeouts`,
  `anomalies.tool_failures`, `anomalies.crashes`
- `component_breakdown`
- `error_timeline`
- `total_errors`, `total_warnings`, `has_anomalies`

`report` converts that JSON into Markdown:

```markdown
# Log Analysis Report

## Overview
- Log file: agent.log
- Lines analyzed: 1542
- Time window: 24h
- Total errors: 12 | warnings: 20
- Anomalies detected: 5 types
```

## Scheduled Summary Integration

For a scheduled digest, run `scan` in quiet mode and include the output only when
it is non-empty:

```bash
python scripts/analyze_logs.py scan --log-file /var/log/agent.log --since 24h --quiet --output /tmp/log-scan.json
if [ -s /tmp/log-scan.json ]; then
  python scripts/analyze_logs.py report --scan /tmp/log-scan.json
fi
```

A `scheduled-summary` job can append the Markdown output under a "Log anomalies"
heading. Keep the analysis window aligned with the summary window (for example,
24 hours for a daily digest) so counts do not overlap or disappear.

## Common Pitfalls

1. **Log rotation breaks time windows.** If yesterday's file was rotated out, a
   `--since 24h` scan over only the current file may miss early-window failures.
   Point the scheduler at the active file plus rotated file, or concatenate the
   relevant files before scanning.
2. **Multiline stack traces need the first line.** The parser groups indented
   stack-trace continuation lines under the preceding parsed log line. If a log
   collector strips the first `Traceback` or `ERROR` line, the remaining stack
   frames become unstructured context.
3. **Expected errors can be false positives.** Retries, probing, and health
   checks may intentionally emit warnings or connection failures. Treat clusters
   as "investigate" signals, not automatic incidents.
4. **First run on a large historical log can overwhelm output.** Start with
   `--since 24h`, inspect the report, then widen the window if needed.
5. **Changing message formats can split clusters.** If an application changes an
   error string during a deploy, pre- and post-deploy failures may appear as two
   clusters even when the root cause is the same.
6. **Time-only logs depend on the scan date.** `12:30:45 ERROR ...` lines do not
   contain a date. For historical files, prefer full timestamps.
7. **The error timeline buckets by hour-of-day, not date.** On a multi-day
   window (`--since 7d`), errors from 08:00 on different days merge into one
   `08:00` bar. Use the clusters (which carry full timestamps) for multi-day
   forensics; treat the timeline as a time-of-day profile.
8. **Crash detection is substring-based.** The crash regex matches words like
   `fatal` or `Exception` anywhere in a line, so mentions inside INFO lines
   (e.g. "retry succeeded after TimeoutException", "non-fatal warning") count
   as crash signals and can set `has_anomalies`. Treat crash counts as leads
   to eyeball, and tune the regex if your logs legitimately chat about
   exceptions at INFO level.

## What This Skill Is NOT

- Not a log viewer: use `tail`, `less`, or a log UI when you need raw line
  inspection.
- Not a log shipper: it does not forward logs to storage or observability
  systems.
- Not a SIEM: it does not correlate identities, networks, or security events.
- Not real-time monitoring: `tail` is a recent-line analyzer, not a daemon or
  alerting service.
- Not a root-cause oracle: it highlights patterns so an agent or operator can
  investigate faster.

## Verification Checklist

- [ ] Run `python scripts/analyze_logs.py --help` and confirm subcommands load.
- [ ] Scan a synthetic log with repeated errors and confirm `has_anomalies` is
      true.
- [ ] Render Markdown from the scan JSON and confirm all anomaly sections appear.
- [ ] Run `python -m pytest tests/test_analyze_logs.py -v` from this skill
      directory.
- [ ] For cron use, test a no-anomaly log with `--quiet` and confirm stdout is
      empty with exit code 0.
