---
name: scheduled-summary
description: "Cron-driven cross-session digest. Aggregates session activity, cron job outputs, memory changes, and tool usage stats into a compact summary for delivery via messaging platforms. Surfaces outstanding tasks and cross-session context that's invisible on chat platforms."
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [summary, digest, cron, sessions, activity, cross-session, notification, scheduled]
  related_skills: [decision-log, news-monitoring]
---

# Scheduled Summary

## Overview

Messaging platforms are excellent for one active conversation, but they hide the
activity that happened elsewhere: other sessions, scheduled jobs, saved memory,
and unresolved items from earlier work. This skill creates a periodic digest that
surfaces that cross-session activity in a compact format suitable for chat
messaging platforms or any notification channel that accepts Markdown or plain
text.

The digest is designed for a cron scheduler. It reads optional local data sources
(session store, cron output directory, memory JSON files, and log file), filters
activity to a configurable time window, and emits Markdown, JSON, or plain text.
When no data sources are configured, it emits a template digest that an agent can
fill by querying its own platform-specific session history, scheduler status,
and memory tools.

## Quick start

From this skill directory:

```bash
python scripts/summarize.py generate --since 24h
```

With explicit data sources:

```bash
python scripts/summarize.py generate \
  --since 24h \
  --sessions-db /path/to/sessions.sqlite \
  --cron-dir /path/to/cron-output \
  --memory-dir /path/to/memory-json \
  --log-file /path/to/agent.log
```

Show current configuration and skipped sources:

```bash
python scripts/summarize.py config
```

Create a config template to fill in:

```bash
python scripts/summarize.py init --output .summary-config.json
```

## What the digest includes

1. **Session activity** — sessions started or completed inside the time window,
   plus topic titles where available.
2. **Cron job status** — jobs that ran successfully, jobs that failed, and jobs
   marked overdue by their output files.
3. **Memory changes** — new saved memories and updated facts from JSON records.
4. **Tool usage** — most-used tools, total calls, and error counts from a text or
   JSONL log file.
5. **Outstanding items** — due decision reviews, incomplete tasks, and TODO-like
   items found in session transcripts.
6. **Time window** — every section is scoped to `--since` (`24h`, `7d`, `2w`,
   etc.) unless the source explicitly marks an item overdue.

## Workflow

1. **Pick the delivery cadence.** Daily is a good default. Weekly works for
   quieter systems. Avoid high-frequency summaries unless the downstream channel
   has strong threading or batching.
2. **Choose data sources.** Configure only the stores you trust the digest to
   read. Start with cron output and logs, then add session and memory stores once
   you understand their schema.
3. **Generate once manually.** Run `generate --since 24h` and inspect the result
   for length, sensitive fields, and duplicate items.
4. **Tune sections.** Use `--sections sessions,cron,outstanding` to keep the
   first scheduled digest short. Add `memory` and `tools` if they are useful.
5. **Schedule the command.** Run it from a cron scheduler and redirect output to
   the channel integration or a file consumed by your notifier.
6. **Review after a week.** Check whether the digest is surfacing actionable
   items. Remove noisy sections and add missing source paths.

Completion criterion: the scheduled command produces a digest with a generated
timestamp, the requested sections, and no unexpected secrets or full transcripts.

## Cron scheduler setup

Generic daily cron scheduler entry:

```cron
0 8 * * * cd /path/to/scheduled-summary && python scripts/summarize.py generate --since 24h --output /tmp/activity-digest.md
```

Example with environment variables instead of flags:

```cron
0 8 * * * SESSIONS_DB=/data/sessions.sqlite CRON_OUTPUT_DIR=/data/cron MEMORY_DIR=/data/memory LOG_FILE=/data/agent.log python /path/to/scheduled-summary/scripts/summarize.py generate --since 24h
```

To deliver to a messaging platform, pipe or post the generated file using your
own notifier:

```bash
python scripts/summarize.py generate --since 24h --output /tmp/digest.md
python /path/to/send_notification.py /tmp/digest.md
```

Keep the notifier separate from the digest generator so the script remains
portable across platforms.

## Output format

Markdown output is optimized for chat platforms:

- Compact `##` / `###` headings.
- Bullets rather than paragraphs.
- Emoji status markers for quick scanning.
- Short quoted topics instead of transcript excerpts.
- Code blocks only for dense stats when useful.
- A final generated timestamp in UTC.

Supported formats:

```bash
python scripts/summarize.py generate --format markdown
python scripts/summarize.py generate --format json
python scripts/summarize.py generate --format text
```

Write to a file:

```bash
python scripts/summarize.py generate --since 7d --output weekly-digest.md
```

## Customization

Include only specific sections:

```bash
python scripts/summarize.py generate --sections sessions,cron,outstanding
```

Common section sets:

- **Daily operational digest:** `sessions,cron,outstanding`
- **Weekly review:** `sessions,cron,memory,tools,outstanding`
- **Low-noise health check:** `cron,tools`
- **Agent-filled template:** run with no source paths configured, then fill the
  placeholders from platform-specific tools.

Configure paths with flags, environment variables, or a generated config file:

| Source | Flag | Environment variable |
| --- | --- | --- |
| Session SQLite database | `--sessions-db` | `SESSIONS_DB` |
| Cron output directory | `--cron-dir` | `CRON_OUTPUT_DIR` |
| Memory JSON directory | `--memory-dir` | `MEMORY_DIR` |
| Tool/log file | `--log-file` | `LOG_FILE` |
| Decision records | `--decisions-dir` | `DECISIONS_DIR` |

See `references/data-sources.md` for expected formats and schema notes.

## Integrations

### decision-log

If a decision record directory is available, pass it with `--decisions-dir` or
`DECISIONS_DIR`. The digest scans Markdown decision records for accepted or
proposed decisions whose `Next review: YYYY-MM-DD` is due, then reports the count
and titles in the Outstanding section.

### news-monitoring

News monitoring jobs usually write a scheduled output file. Point `--cron-dir` at
the directory containing those outputs. The digest will report whether monitoring
ran, succeeded, failed, or marked itself overdue. Keep the full news summary in
its own file; the scheduled summary should only mention that monitoring ran and
whether action is required.

## Common pitfalls

1. **Too verbose for chat.** Do not paste full transcripts or full cron logs into
   the digest. Surface counts, titles, and one-line action items.
2. **Sensitive data leakage.** Session titles, memory facts, and log lines may
   contain secrets or personal data. Review the first outputs manually and redact
   upstream sources where needed.
3. **Running too frequently.** Hourly summaries often create notification
   fatigue and duplicate the active chat. Daily or weekly is usually better.
4. **No deduplication across summaries.** If the same overdue item appears every
   day, either resolve it, suppress it upstream, or add a stable decision/task
   owner outside this digest.
5. **Treating template mode as complete data.** Placeholder output means no data
   sources were readable. The agent or operator must fill it from platform tools.
6. **Assuming one universal session schema.** Session stores vary by platform.
   The script uses best-effort SQLite introspection, but exact counts depend on
   the available columns.
7. **Mixing generation and delivery.** Keep the digest generator independent from
   platform-specific webhook or bot code; this makes testing and migration easier.

## What this skill is not

- Not a session search tool. Use your platform's session search or transcript
  browser when you need a specific conversation.
- Not a full transcript exporter. It intentionally summarizes titles, counts,
  and TODO-like lines only.
- Not a replacement for session browsing. It helps decide what to inspect next.
- Not a complete scheduler dashboard. It reads output files and status markers;
  it does not own or run the scheduler.
- Not a secrets scanner. It reduces verbosity, but it cannot guarantee that the
  source data is safe to send to a messaging platform.

## Reference files

- `references/digest-format.md` — section contract, output variants, daily and
  weekly examples.
- `references/data-sources.md` — source configuration, expected formats, and
  schema examples.
- `templates/digest-template.md` — blank Markdown template for agent-filled or
  manually curated digests.
- `scripts/summarize.py` — stdlib CLI for generating, configuring, and
  bootstrapping summary files.

## Verification checklist

- [ ] `python scripts/summarize.py --help` shows `generate`, `config`, and `init`.
- [ ] `python scripts/summarize.py generate --since 24h` works without sources
      and emits template mode output.
- [ ] A mock run with sources includes only events inside the time window, except
      explicitly overdue cron jobs.
- [ ] `--sections` excludes omitted sections from Markdown, JSON, and text.
- [ ] `--format json` returns parseable JSON.
- [ ] The first scheduled output has been reviewed for secrets and excessive
      length before connecting it to a messaging platform.
