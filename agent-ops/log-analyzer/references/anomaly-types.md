# Anomaly Types

This reference explains each anomaly emitted by `scripts/analyze_logs.py scan`,
how it is detected, and how to interpret it.

## Error Clusters

**Detection criteria:**

- Only `ERROR`, `FATAL`, and `CRITICAL` entries are considered.
- The first line of the message is normalized by replacing URLs with `[URL]`, IP
  addresses with `[IP]`, and numbers with `[NUM]`.
- A cluster is reported when the same normalized message appears at least 3
  times in the selected time window.

**Interpretation:**

A cluster usually means a stable failure mode: a down dependency, repeated bad
input, a broken deploy, or a retry loop. The normalized message is useful for
pattern recognition; the `example` field preserves one original message for
context.

## Rate Limit Hits

**Detection criteria:**

A line is counted when its message contains any of:

- `429`
- `rate limit`, `rate-limit`, or `rate_limit`
- `too many requests`
- `quota exceeded`

The analyzer groups hits by provider. It first looks for `provider=<name>` or
`provider: <name>`, then checks known provider names in the line, then falls back
to the component name or `unknown`.

**Interpretation:**

Rate limits indicate capacity pressure, too much concurrency, insufficient
backoff, or a low service quota. A small count may be normal if retries succeed;
a repeated count in a narrow timeframe usually needs backoff or scheduling
changes.

## Timeouts

**Detection criteria:**

A line is counted when its message contains:

- `timeout`
- `timed out`
- `deadline exceeded`
- `connection timeout`

Timeouts are grouped by detected tool name. URLs are extracted as examples when
present.

**Interpretation:**

Timeouts point to slow dependencies, network issues, undersized timeouts, or
large inputs. Grouping by tool helps distinguish one failing integration from a
global system slowdown.

## Tool Failures

**Detection criteria:**

Only error-level entries are considered. Tool names are extracted from patterns
such as:

- `tool: terminal`
- `tool=terminal`
- `tool_call: web_search`
- `tool web_extract failed`
- messages emitted by a `tools` or `tool` component, where the first token looks
  like a tool name

The report includes total failures per tool and the most common normalized error
messages.

**Interpretation:**

Use this to decide whether failures are concentrated in one integration or
spread across the runtime. If one tool dominates, inspect credentials, network
access, package availability, or input size for that tool first.

## Crashes

**Detection criteria:**

A crash is reported for any entry with:

- `FATAL` or `CRITICAL` level
- `fatal`
- `unhandled`
- `Traceback`
- `Exception`
- `segfault`

Multiline tracebacks are grouped with continuation lines. Crash entries include
nearby context lines when available.

**Interpretation:**

Crashes are higher-priority than ordinary error clusters because they may stop a
session or worker. Use the final exception line and context to identify the
failing module and missing state.

## Component Breakdown

**Detection criteria:**

For every parsed entry, the analyzer increments `errors` or `warnings` under the
detected component. Components come from `[component]`, `component:` after the
level, or `unknown` when absent.

**Interpretation:**

Component counts show where to begin. A warning-heavy component may be noisy but
not failing. An error-heavy component likely owns the root cause or the
integration boundary where the root cause surfaces.

## Error Timeline

**Detection criteria:**

Timestamped error-level entries are bucketed by UTC hour using `HH:00` keys.
Entries without timestamps are counted in totals but cannot be placed on the
timeline.

**Interpretation:**

Spikes often align with deploys, scheduled jobs, traffic bursts, log rotation,
or external outages. Compare the hour buckets to known operational events before
assuming the application changed.

## `has_anomalies`

`has_anomalies` is true when any anomaly list is non-empty:

- error clusters
- rate limits
- timeouts
- tool failures
- crashes

Plain warning/error totals alone do not set `has_anomalies` unless they match an
anomaly pattern. This keeps cron mode quiet for isolated expected warnings.
