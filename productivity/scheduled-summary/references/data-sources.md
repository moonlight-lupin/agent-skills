# Data Sources

`scheduled-summary` is agent-agnostic. It does not assume a particular runtime,
cloud service, or messaging platform. Connect any source that can expose local
files in one of the formats below.

Paths can be provided by command-line flags, environment variables, or a JSON
config file created with `python scripts/summarize.py init`.

| Source | Flag | Environment variable | Required? |
| --- | --- | --- | --- |
| Session SQLite database | `--sessions-db` | `SESSIONS_DB` | No |
| Cron output directory | `--cron-dir` | `CRON_OUTPUT_DIR` | No |
| Memory JSON directory | `--memory-dir` | `MEMORY_DIR` | No |
| Log file | `--log-file` | `LOG_FILE` | No |
| Decision records directory | `--decisions-dir` | `DECISIONS_DIR` | No |

If no configured source path exists, the CLI runs in template mode and prints a
placeholder digest for an agent or operator to fill manually.

## Session store

Expected format: SQLite database.

The parser uses best-effort introspection because session schemas vary by agent
platform. It looks for tables whose names contain `session`, `conversation`, or
`thread`, then reads common columns:

- Title/topic columns: `title`, `name`, `summary`, `subject`, `topic`
- Timestamp columns: `created_at`, `started_at`, `updated_at`, `ended_at`,
  `completed_at`, `finished_at`, `timestamp`, `time`, `date`
- Status columns: `status`, `state`
- Text columns that may contain TODO-like items

Minimal compatible schema:

```sql
CREATE TABLE sessions (
  id TEXT PRIMARY KEY,
  title TEXT,
  created_at TEXT,
  ended_at TEXT,
  status TEXT
);

CREATE TABLE messages (
  id INTEGER PRIMARY KEY,
  session_id TEXT,
  created_at TEXT,
  content TEXT
);
```

Configuration:

```bash
python scripts/summarize.py generate --sessions-db /data/sessions.sqlite
SESSIONS_DB=/data/sessions.sqlite python scripts/summarize.py generate
```

Notes:

- ISO 8601 timestamps are preferred. Unix seconds and milliseconds are accepted.
- Naive timestamps are treated as UTC.
- Session counts are best-effort. For exact counts, adapt your platform's export
  to the minimal schema above.

## Cron output directory

Expected format: directory of `.md`, `.txt`, or `.log` files written by scheduled
jobs.

Each file should include a job name and status marker when possible:

```text
job: news-monitoring
started_at: 2026-07-06T08:00:00Z
status: success
```

Failure example:

```text
job: news-monitoring
finished_at: 2026-07-06T08:02:30Z
status: failed
error: timeout while fetching feeds
```

Overdue example:

```text
job: weekly-review
status: overdue
last ran 9 days ago
```

The parser infers:

- **Success** from markers such as `success`, `succeeded`, `completed`, `ok`,
  `exit code 0`, or `✅`.
- **Failure** from markers such as `failed`, `error`, `exception`, `timeout`,
  `rate limit`, `non-zero`, or `exit code 1`.
- **Overdue** from markers such as `overdue`, `stale`, `missed schedule`, or
  `last ran N days ago`.

Configuration:

```bash
python scripts/summarize.py generate --cron-dir /data/cron-output
CRON_OUTPUT_DIR=/data/cron-output python scripts/summarize.py generate
```

## Memory store

Expected format: directory of JSON files. Each file can contain one object or a
list of objects.

Example new memory:

```json
{
  "timestamp": "2026-07-06T09:10:00Z",
  "action": "new",
  "memory": "User prefers concise operational summaries."
}
```

Example updated fact:

```json
{
  "updated_at": "2026-07-06T11:00:00Z",
  "action": "updated",
  "fact": "VM RAM 6GB"
}
```

Recognized fields:

- Time: `timestamp`, `created_at`, `updated_at`, `time`, `date`
- Action: `action`, `event`, `type`, `kind`, `status`
- Brief text: `fact`, `memory`, `content`, `text`, `summary`, `title`

Configuration:

```bash
python scripts/summarize.py generate --memory-dir /data/memory
MEMORY_DIR=/data/memory python scripts/summarize.py generate
```

## Log file

Expected format: text log or JSONL log.

Text example:

```text
2026-07-06T10:00:00Z tool=terminal status=success
2026-07-06T10:01:00Z tool=web_search error=rate limit
2026-07-06T10:02:00Z TODO: retry source export
```

JSONL example:

```jsonl
{"timestamp":"2026-07-06T10:00:00Z","tool":"terminal","status":"success"}
{"timestamp":"2026-07-06T10:01:00Z","tool":"web_search","error":"rate limit"}
```

The parser extracts:

- Tool names from JSON `tool`, `tool_name`, `name`, or text `tool=<name>`.
- Errors from `error`, `failed`, `timeout`, `rate limit`, and related markers.
- TODO-like lines for the Outstanding section.

Configuration:

```bash
python scripts/summarize.py generate --log-file /data/agent.log
LOG_FILE=/data/agent.log python scripts/summarize.py generate
```

## Decision records

Expected format: Markdown decision records compatible with the `decision-log`
pattern. The parser looks for:

```markdown
# Use SQLite for source tracking

## Status
accepted

## Review
Next review: 2026-07-06
```

Records with `superseded` or `deprecated` status are ignored. Accepted or
proposed decisions with `Next review` on or before the digest date are reported
as due.

Configuration:

```bash
python scripts/summarize.py generate --decisions-dir /data/decisions
DECISIONS_DIR=/data/decisions python scripts/summarize.py generate
```

## Config file

Create a template:

```bash
python scripts/summarize.py init --output .summary-config.json
```

Then fill any paths you have:

```json
{
  "default_since": "24h",
  "sections": "sessions,cron,memory,tools,outstanding",
  "format": "markdown",
  "sessions_db": "/data/sessions.sqlite",
  "cron_dir": "/data/cron-output",
  "memory_dir": "/data/memory",
  "log_file": "/data/agent.log",
  "decisions_dir": "/data/decisions"
}
```

Run with:

```bash
python scripts/summarize.py generate --config .summary-config.json
python scripts/summarize.py config --config .summary-config.json
```

Command-line flags override environment variables and config-file values.
