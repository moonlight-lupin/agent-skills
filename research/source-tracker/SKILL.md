---
name: source-tracker
description: "Persistent citation database for multi-session research. Add URLs as they're cited, dedup variants, tag by topic, check link health, and export bibliographies in Markdown/BibTeX/CSV/JSON."
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [citation, bibliography, research, sources, dedup, url-tracking, link-health]
  related_skills: [deep-research, notebooklm-mode, entity-research]
---

# Source Tracker

## Overview

Source Tracker is a small persistent citation manager for research workflows.
Research sources often scatter across browser tabs, notes, temporary files, and
separate sessions. URLs get cited once and then disappear, duplicates accumulate
as `http`/`https` or `www` variants, and bibliography export becomes a manual
cleanup job at the end.

This skill fixes that by keeping a portable SQLite database of every cited URL:
add sources as soon as they are cited, tag them by topic, deduplicate URL
variants, re-check stale links, and export bibliographies in Markdown, BibTeX,
CSV, or JSON.

The database path is configurable with `--db-path` or the
`SOURCE_TRACKER_DB` environment variable. If neither is set, commands use
`./sources.db` relative to the current working directory.

## Quick Start

From the skill directory:

```bash
python scripts/source_db.py add --url URL --topic TOPIC
```

A practical example:

```bash
python scripts/source_db.py add \
  --url "https://example.org/report" \
  --topic "battery supply chain" \
  --title "Example Battery Report" \
  --notes "Baseline market-size estimate" \
  --type report
```

Use a persistent project database when research spans folders or sessions:

```bash
export SOURCE_TRACKER_DB="$HOME/research/sources.db"
python scripts/source_db.py add --url "https://example.org" --topic "market scan"
```

Or pass the path explicitly:

```bash
python scripts/source_db.py --db-path "$HOME/research/sources.db" add --url "https://example.org" --topic "market scan"
```

## Workflows

### 1. Add Sources

Add every URL at the moment it becomes a cited source. Always include a topic.
Use a source type when the material is not a normal web page.

```bash
python scripts/source_db.py add \
  --url "https://example.com/article#section" \
  --topic "ai regulation" \
  --title "Example Article" \
  --notes "Defines the enforcement timeline" \
  --type news \
  --session-id "research-2026-07-06"
```

If `--title` is omitted, the script tries a best-effort GET request and parses
`<title>`. If that fetch fails, the source is still added with a blank title.

Completion criterion: the command prints a JSON object with `inserted: true` for
a new row or `inserted: false` for an exact canonical URL already in the DB.

### 2. Search Sources

Search by topic and optional filters. Results are JSON so they can be piped into
other tools.

```bash
python scripts/source_db.py search --topic "ai regulation"
```

Filter by date range:

```bash
python scripts/source_db.py search \
  --topic "ai regulation" \
  --from 2026-01-01 \
  --to 2026-12-31
```

Filter by source type and verification status:

```bash
python scripts/source_db.py search \
  --topic "ai regulation" \
  --type report \
  --verified true
```

Completion criterion: the JSON array contains only records matching the topic
and filters.

### 3. Deduplicate URL Variants

Run dedup after a research burst or before export. It merges common URL variants
such as `http` vs `https`, `www.` vs bare host, fragment-only differences, and
trailing slash differences.

```bash
python scripts/source_db.py dedup
```

Completion criterion: the command prints a JSON summary with `merged_groups`,
`removed_rows`, and `removed_ids`. The survivor keeps the earliest `accessed_at`
and combines non-empty notes from all merged rows.

### 4. Export Bibliographies

Export a topic bibliography. If `--output` is omitted, content prints to stdout.
If `--output` is set, provide the file path to the user.

Markdown:

```bash
python scripts/source_db.py export \
  --topic "ai regulation" \
  --format markdown \
  --output ai-regulation-sources.md
```

BibTeX:

```bash
python scripts/source_db.py export \
  --topic "ai regulation" \
  --format bibtex \
  --output ai-regulation-sources.bib
```

CSV:

```bash
python scripts/source_db.py export \
  --topic "ai regulation" \
  --format csv \
  --output ai-regulation-sources.csv
```

JSON:

```bash
python scripts/source_db.py export \
  --topic "ai regulation" \
  --format json \
  --output ai-regulation-sources.json
```

Completion criterion: the output contains every source for the topic, sorted by
topic/title/date, in the requested format.

### 5. Health Check

Run link health checks manually before a final report or from a cron scheduler.
The checker uses HEAD requests, marks HTTP 200-399 as alive, updates
`last_checked`, and flags dead links by setting `verified = 0`.

```bash
python scripts/url_health.py --stale-days 30 --timeout 10 --batch-size 50
```

With an explicit database path:

```bash
python scripts/url_health.py \
  --db-path "$HOME/research/sources.db" \
  --stale-days 7 \
  --timeout 5 \
  --batch-size 100
```

Completion criterion: the command prints `Checked N URLs: M alive, K dead` and
exits with code 0. Dead links are recorded in the database; they are not treated
as runtime errors.

### 6. Stats and Topic Inventory

Show source counts by topic, type, and verification status:

```bash
python scripts/source_db.py stats
```

List all topic tags:

```bash
python scripts/source_db.py list-topics
```

Completion criterion: stats print as JSON and topic inventory prints a JSON
array of distinct topic strings.

## URL Normalization Rules

Source Tracker uses two levels of URL handling:

1. **Canonical storage URL**
   - Lowercase scheme and host.
   - Strip URL fragments such as `#section`.
   - Strip trailing slash on non-root paths.
   - Preserve query strings.
   - Preserve `www.` because it may be the URL the user expects to see.

2. **Dedup comparison key**
   - Applies all canonical storage rules.
   - Treats `http` and `https` variants as the same source.
   - Strips a leading `www.` prefix from the host for comparison only.

Examples:

| Input | Canonical URL | Dedup comparison |
|---|---|---|
| `HTTPS://WWW.Example.com/Page/#intro` | `https://www.example.com/Page` | `//example.com/Page` |
| `http://example.com/` | `http://example.com/` | `//example.com/` |
| `https://www.example.com` | `https://www.example.com/` | `//example.com/` |

## Source Types

Use one of these values with `--type`:

| Type | Use for |
|---|---|
| `web` | Standard web pages, documentation pages, blog posts, landing pages. |
| `pdf` | Direct PDF URLs or pages where the source of record is a PDF. |
| `api` | API endpoints, JSON/XML data endpoints, machine-readable service output. |
| `dataset` | Data downloads, CSV/Parquet repositories, public data catalogs. |
| `book` | Online books, book chapters, scans, or bibliographic pages for books. |
| `news` | News articles, wire reports, interviews, live blogs. |
| `report` | White papers, government reports, analyst reports, institutional reports. |

## Research Workflow Integration

### Deep Research

During iterative search/extract/synthesize work, add a source immediately after
it passes the quality filter and before using it in the synthesis:

```bash
python scripts/source_db.py add \
  --url "SOURCE_URL" \
  --topic "PROJECT_TOPIC" \
  --title "SOURCE_TITLE" \
  --notes "Supports sub-question: ..." \
  --session-id "SESSION_ID"
```

Before the final report:

```bash
python scripts/source_db.py dedup
python scripts/source_db.py export --topic "PROJECT_TOPIC" --format markdown --output bibliography.md
```

### Notebook-style Source Vaults

When building a source vault, add each source as it enters the vault. Store the
vault or corpus identifier in `--session-id`, and use notes for coverage labels
such as `primary evidence`, `background`, or `contradiction`.

```bash
python scripts/source_db.py add \
  --url "SOURCE_URL" \
  --topic "VAULT_TOPIC" \
  --notes "Vault source 007; primary evidence" \
  --session-id "vault-007"
```

### Entity Research

For entity dossiers, tag sources with the entity name plus the research lens.
Use source types to distinguish official registries, adverse media, reports, and
datasets.

```bash
python scripts/source_db.py add \
  --url "SOURCE_URL" \
  --topic "Acme Ltd adverse media" \
  --type news \
  --notes "Allegation source; not independently verified"
```

## Cron Usage

Run weekly health checks with the cron scheduler. Example crontab entry:

```cron
0 9 * * 1 cd /path/to/source-tracker && SOURCE_TRACKER_DB=/path/to/sources.db python scripts/url_health.py --stale-days 30 --batch-size 100 >> /path/to/source-health.log 2>&1
```

Use small batches for very large databases to avoid long scheduler jobs:

```cron
0 9 * * 1 cd /path/to/source-tracker && python scripts/url_health.py --db-path /path/to/sources.db --stale-days 30 --batch-size 50
```

## Output Formats

- **Markdown bibliography** — grouped by topic, with each source rendered as
  `- [Title](URL) — notes (accessed_at)`.
- **BibTeX** — `@misc{key, title={...}, url={...}, note={...}, urldate={...}}`.
- **CSV** — `id,url,title,topic,source_type,accessed_at,notes,verified,last_checked`.
- **JSON** — array of full source objects, including `session_id` and normalized
  URL fields.

See `references/export-formats.md` for concrete examples.

## Common Pitfalls

1. **Invented URLs** — never add a URL unless it came from a web search tool,
   web extraction tool, user-provided source, or another verifiable source
   channel. If a URL was guessed, verify it before adding it.
2. **Missing topic tags** — `--topic` is required for a reason. Use consistent
   topic names so search, stats, and export do not fragment across near-duplicates.
3. **Stale health checks** — `verified = 1` means the source was alive at its
   last check, not that it is alive forever. Run `url_health.py` before final
   delivery for long-running projects.
4. **Duplicate variants** — `https://www.example.com/`, `http://example.com`,
   and `https://example.com#intro` can refer to the same source. Run `dedup`
   before export.
5. **Blank titles** — title extraction is best-effort. For important citations,
   pass `--title` explicitly instead of relying on a remote page fetch.
6. **Relative database confusion** — the default `./sources.db` depends on the
   current working directory. Use `SOURCE_TRACKER_DB` or `--db-path` for
   long-running projects.

## Verification Checklist

- [ ] Every cited URL was observed through a real source channel before adding.
- [ ] Each added row has a meaningful `--topic` and appropriate `--type`.
- [ ] `python scripts/source_db.py dedup` was run before bibliography export.
- [ ] `python scripts/url_health.py` was run recently for final deliverables.
- [ ] Exported bibliography uses the requested format and output path.
- [ ] Dead or unverified links are reviewed before final citation use.
- [ ] The database path is explicit for multi-session work (`--db-path` or
      `SOURCE_TRACKER_DB`).
