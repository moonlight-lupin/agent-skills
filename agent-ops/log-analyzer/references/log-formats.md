# Supported Log Formats

`analyze_logs.py` is built for common line-oriented logs with a timestamp, a log
level, an optional component, and a message. It also performs best-effort scans
of unstructured lines that contain obvious level words such as `ERROR` or
`WARN`.

## Recognized Levels

The parser recognizes these levels, case-insensitively when falling back to
unstructured parsing:

- `ERROR`
- `WARN`
- `WARNING`
- `INFO`
- `DEBUG`
- `FATAL`
- `CRITICAL`

`ERROR`, `FATAL`, and `CRITICAL` count as errors. `WARN` and `WARNING` count as
warnings.

## Full Timestamp with Bracketed Component

```text
2026-07-06 12:30:45 ERROR [gateway] Connection refused
2026-07-06 12:31:01 WARN [cron] job ran longer than expected
```

Shape:

```text
YYYY-MM-DD HH:MM:SS LEVEL [component] message
```

The component is the value inside brackets. If no component is present, the
component is recorded as `unknown`.

## ISO 8601 Timestamp with Colon Component

```text
2026-07-06T12:30:45Z ERROR gateway: Connection refused
2026-07-06T12:30:45+00:00 ERROR agent: unhandled exception
```

Shape:

```text
YYYY-MM-DDTHH:MM:SSZ LEVEL component: message
YYYY-MM-DDTHH:MM:SS+00:00 LEVEL component: message
```

The parser accepts `Z`, `+00:00`, and compact offsets such as `+0000`.
Parsed timestamps are normalized to UTC in JSON output.

## Time-Only Lines

```text
12:30:45 ERROR Connection refused
12:31:00 WARN [tools] retrying tool call
```

Shape:

```text
HH:MM:SS LEVEL [optional-component] message
```

Time-only lines do not contain a date. The command-line parser anchors them to
the current UTC date. If you import `parse_log_line()` from Python, pass a
`default_date` argument when parsing historical fixtures.

## Unstructured Fallback

```text
worker stderr: ERROR command failed with exit code 127
WARN retry budget almost exhausted
```

If a line does not match a timestamped format but contains a recognized level,
the parser records:

- `timestamp: null`
- `component: unknown`
- `level`: the matched level
- `message`: the text after the level

Unknown-timestamp lines are retained when `--since` is used, because the tool
cannot prove they are outside the window.

## Multiline Stack Traces

```text
2026-07-06 15:30:00 ERROR [agent] Traceback (most recent call last):
  File "runner.py", line 12, in <module>
    run()
KeyError: 'session_id'
```

Continuation lines are grouped under the preceding parsed line when they are
indented or look like common Python traceback frames/errors. The grouped entry
counts as one parsed log event, but `lines_analyzed` still includes the physical
line count.

## Adding Custom Patterns

To add another log format, edit `scripts/analyze_logs.py`:

1. Add a compiled regular expression near `ISO_LINE_RE`, `SPACE_LINE_RE`, and
   `TIME_LINE_RE`. Use named groups: `ts`, `level`, optional `bracket` or
   `colon`, and `message`.
2. Add the regex to the loop in `parse_log_line()`.
3. Extend `parse_timestamp()` if the new timestamp shape is not already
   supported.
4. Add a pytest fixture in `tests/test_analyze_logs.py` that proves the parser
   extracts timestamp, level, component, and message correctly.

Keep custom patterns conservative. Overly broad regexes can misclassify ordinary
application messages as log headers and break multiline stack trace grouping.
