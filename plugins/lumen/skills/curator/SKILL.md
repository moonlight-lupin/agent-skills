---
name: curator
description: "Use when ingesting memory into the wiki, running wiki_curator.py (run/report/validate/lint/search), or linting wiki structure."
license: MIT
metadata:
  version: 0.1.1
  author: moonlight-lupin
  platforms: [linux, macos, windows]
  tags: [wiki, curator, knowledge-base, okf]
  hermes:
    category: research
    related_skills: [obsidian, arxiv]
---

# Wiki Curator

## Overview

The curator is the operational half of Lumen. It turns memory-source records into conservative Markdown wiki updates, and it lints the wiki for structural decay. It never calls providers, never deletes pages, and never overwrites operator-confirmed facts.

Pair it with `lumen:wiki` for methodology (OKF frontmatter, ingest/query/lint procedures). This skill is the CLI and adapter layer.

## When to Use

Use this skill when the user wants to:

- Ingest recent memory into the wiki (`run`) or preview that ingest (`report`)
- Lint or validate wiki structure
- Search wiki pages by keyword, alias, or tag
- Configure which memory source the curator reads

## Wiki Location

Resolve the wiki path in this order:

1. `--wiki` CLI override
2. `paths.wiki_path` in plugin config (`shared/config/lumen.yaml` or `--config`)
3. `$WIKI_PATH` environment variable
4. Default `~/wiki`

## Plugin config (`lumen.yaml`)

Default file: `<plugin>/shared/config/lumen.yaml`. Override with `--config` or `LUMEN_CONFIG`.

```yaml
paths:
  wiki_path: ~/wiki          # null → $WIKI_PATH → ~/wiki

curator:
  timezone: Asia/Singapore
  max_write_pages: 20        # 0 or negative disables the cap
  memory_source: auto        # auto | json-file | mnemosyne | none
```

`auto` tries Mnemosyne when `hermes` is on `PATH` and falls back to the json-file adapter if the export fails; without `hermes` it uses json-file. `none` disables ingest (file-only lint/search still work).

## Adapter layer

`${HERMES_SKILL_DIR}/scripts/adapters.py` is the read-only memory boundary. Adapters emit `SourceItem` records (`source_id`, `source_kind`, `title`, `text`, `timestamp`, `tags`, `people`, `entities`, `projects`, `raw`). Nothing writes back to a memory store.

| Adapter | Source | Notes |
|---|---|---|
| `json-file` | `<wiki>/.knowledge/memory.json` | Tolerant record shapes (`records` map or list). Missing file → `[]`. |
| `mnemosyne` | `hermes mnemosyne export --output <tmp>` | Parses `working_memory` + `episodic_memory`. Subprocess failure → `[]`. |
| `none` | empty | Explicit opt-out. |

**Extension point (`generic-json`).** Any provider that can emit the json-file `memory.json` shape (a `records` mapping or a list of record objects, with tolerant people/entities/projects keys) can be dropped in as `<wiki>/.knowledge/memory.json` and selected with `memory_source: json-file`. A dedicated `generic-json` adapter that takes an arbitrary export path is the documented next step; do not add provider-specific imports.

## CLI

Script: `${HERMES_SKILL_DIR}/scripts/wiki_curator.py` (Hermes substitutes `${HERMES_SKILL_DIR}` with this skill's directory, so the path works from any cwd). Run with system `python3` (stdlib + PyYAML).

```bash
CURATOR="${HERMES_SKILL_DIR}/scripts/wiki_curator.py"

python3 "$CURATOR" run --since 24h          # ingest (writes wiki pages)
python3 "$CURATOR" run --since 24h --dry-run
python3 "$CURATOR" report --since 7d        # planned changes, no writes
python3 "$CURATOR" validate                 # lint; exit 1 on ERROR
python3 "$CURATOR" lint                     # same checks
python3 "$CURATOR" lint --summary           # counts only
python3 "$CURATOR" search "Acme" --format json --limit 10
python3 "$CURATOR" search "Acme" --format text --wiki ~/wiki
```

Global flags: `--config <lumen.yaml>`, `--wiki <path>` (also accepted after the subcommand).

`--since` accepts `90m`, `24h`, `7d`, `2w`.

**Read-only vs mutating:** `lint`, `validate`, `report`, and `search` are read-only. `run` writes. `run --dry-run` previews. The curator never deletes pages.

## Conservative write policy

- Create or update people / project / entity / daily pages from source items only
- Preserve operator-confirmed facts; append observations with `[source: id]`
- Refresh only the `<!-- lumen:auto:start -->` … `<!-- lumen:auto:end -->` block of `index.md` and `overview.md` (hand-written content outside the markers is preserved; a file without markers gets a block appended); append `log.md`
- Record text, titles and names are flattened to one line with `[source:` / `[[` / leading `#` neutralised, so memory content cannot forge sections, source markers or links
- Never overwrite an existing page `title` or `created` value
- Cap source items per run at `curator.max_write_pages` (default 20; 0 or negative disables the cap)
- Backup the wiki tree to `<wiki>/.lumen/backup/<timestamp>/` before large batches (>5 items). `.lumen/` is excluded from index and overview regeneration.

## OKF v0.2

Every curated `.md` page needs parseable YAML frontmatter with a non-empty `type` field. See `lumen:wiki` for the full schema. The curator assigns `seq` on create and preserves `aliases` / `relations`.

## Lint checks

- Missing or malformed frontmatter (ERROR)
- Missing `type` (ERROR)
- Broken `[[wikilinks]]` (WARN)
- Duplicate titles (WARN)
- Pages absent from `index.md` (WARN)
- Orphans with no inbound links (INFO)
- Stale pages (updated >90 days) (INFO)

## File naming

Lowercase hyphenated slugs: `acme-logistics.md`. Avoid generic names like `notes.md`.

## Common pitfalls

1. Skipping orientation (`purpose.md`, `SCHEMA.md`, `index.md`, recent `log.md`)
2. Creating duplicate entity pages without searching first
3. Dumping raw notes as curated knowledge
4. No frontmatter / missing `type`
5. Unlinked pages that lint later reports as orphans

## Verification checklist

- [ ] Wiki path resolved from plugin config, then `$WIKI_PATH`, then `~/wiki`
- [ ] `memory_source` matches the host install (`auto` / `json-file` / `mnemosyne` / `none`)
- [ ] `run --dry-run` reviewed before a mutating `run`
- [ ] Lint reports file paths and severity
- [ ] Query answers cite wiki pages
