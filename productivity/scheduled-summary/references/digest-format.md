# Digest Format Guide

The scheduled summary digest is intentionally compact. It should tell a reader
what happened across sessions and scheduled activity, what needs attention, and
where to inspect next — without becoming a transcript or scheduler dashboard.

## Top-level structure

```markdown
## 📋 Activity Digest — Last 24h

### Sessions
- 3 sessions completed
- Topics: "agent skills repo expansion", "NAS cleanup"

### Cron Jobs
- ✅ 4 jobs ran successfully
- ❌ 1 job failed: news-monitoring (timeout)
- ⏰ 1 job overdue: weekly-review (last ran 9 days ago)

### Memory
- 2 new memories saved
- 1 fact updated: "VM RAM 6GB"

### Tool Usage
- Most used: terminal (47), web_search (23), read_file (18)
- Errors: 3 (1 timeout, 2 rate limit)

### Outstanding
- 2 decisions due for review (from decision-log)
- TODO from "NAS cleanup": "recheck tunnel config"

---
Generated at 2026-07-06T22:30:00Z
```

## Section contract

### Sessions

Purpose: make cross-session work visible on messaging platforms.

Include:

- Count of sessions started or completed in the time window.
- Recent session titles or short topics.
- TODO-like lines discovered in session transcript fields, but only as short
  action items in the Outstanding section.

Do not include full transcript excerpts.

### Cron Jobs

Purpose: show scheduled automation health.

Include:

- Number of jobs that ran successfully.
- Failed jobs with one short reason.
- Jobs whose output marks them overdue or stale.

A cron job is considered failed when the output contains failure markers such as
`failed`, `error`, `timeout`, `exception`, or a non-zero exit code. It is
considered overdue when the output contains markers such as `overdue`, `stale`,
`missed schedule`, or `last ran N days ago`.

### Memory

Purpose: show durable knowledge changes that are easy to miss in chat.

Include:

- New memory count.
- Updated fact count.
- Up to a few brief facts if they are safe to send.

Avoid sensitive personal facts, credentials, private addresses, and full raw
memory objects.

### Tool Usage

Purpose: provide a compact operational signal.

Include:

- Most-used tools and counts.
- Total tool/API calls.
- Error count and common error types.

Use code blocks only for dense stats; keep the main bullets readable.

### Outstanding

Purpose: turn the digest into a useful next-action list.

Include:

- Decision reviews due from a decision-log directory.
- TODO/FIXME/action-item/follow-up lines found in sessions or logs.
- Unresolved scheduler failures that require attention.

Do not invent action items. If a source is missing, say it was not configured or
use template placeholders.

## Output variants

### Markdown

Default. Best for chat platforms that support headings, bullets, and basic code
blocks.

```bash
python scripts/summarize.py generate --format markdown --since 24h
```

### JSON

Best for downstream bots, dashboards, or webhook formatters.

```bash
python scripts/summarize.py generate --format json --since 24h
```

The JSON output contains the rendered sections, source-path existence flags, raw
counts, and item arrays.

### Plain text

Best for SMS, email subject/body pipelines, or platforms with weak Markdown.

```bash
python scripts/summarize.py generate --format text --since 24h
```

## Customization options

### Section filtering

Use `--sections` to keep the digest short:

```bash
python scripts/summarize.py generate --sections sessions,cron,outstanding
```

Common profiles:

| Profile | Sections |
| --- | --- |
| Daily operations | `sessions,cron,outstanding` |
| Weekly review | `sessions,cron,memory,tools,outstanding` |
| Low-noise health check | `cron,tools` |
| Memory review | `memory,outstanding` |

### Time windows

Use `--since` for relative windows:

```bash
python scripts/summarize.py generate --since 24h
python scripts/summarize.py generate --since 7d
python scripts/summarize.py generate --since 2w
```

Overdue cron jobs are included when explicitly marked overdue even if their file
mtime is outside the window. That is intentional: overdue status is about current
attention, not only recent execution.

## Daily example

```markdown
## 📋 Activity Digest — Last 24h

### Sessions
- 3 sessions completed
- 4 sessions started
- Topics: "agent skills repo expansion", "NAS docker cleanup", "wedding planning"

### Cron Jobs
- ✅ 4 jobs ran successfully
- ❌ news-monitoring failed: timeout
- ⏰ weekly-review overdue: last ran 9 days ago

### Outstanding
- 1 decision due for review (from decision-log)
  - "Use SQLite for source tracker" due 2026-07-06
- TODO from NAS docker cleanup: "recheck tunnel config"

---
Generated at 2026-07-06T22:30:00Z
```

## Weekly example

```markdown
## 📋 Activity Digest — Last 7d

### Sessions
- 12 sessions completed
- 15 sessions started
- Topics: "Q3 planning", "source tracker export", "cron cleanup", "image workflow"

### Cron Jobs
- ✅ 27 jobs ran successfully
- ❌ 0 jobs failed
- ⏰ 1 job overdue: monthly-archive (last ran 35 days ago)

### Memory
- 5 new memories saved
- 3 facts updated
- Updated: "preferred report format is concise Markdown"

### Tool Usage
- Most used: terminal (91), web_search (44), read_file (37), web_extract (18)
- Errors: 4 (2 timeout, 2 rate limit)

```text
Total API/tool calls: 211
```

### Outstanding
- 2 decisions due for review (from decision-log)
- TODO from Q3 planning: "confirm budget owner"
- TODO from cron cleanup: "dedupe weekly digest delivery"

---
Generated at 2026-07-06T22:30:00Z
```
