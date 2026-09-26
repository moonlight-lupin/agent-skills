# Lumen plugin

Standalone LLM wiki: methodology skill plus a memory-fed curator.

## Install

```bash
# Local path
hermes plugins install /path/to/lumen
ln -s /path/to/lumen ~/.hermes/plugins/lumen   # equivalent

# Catalog (after publish to moonlight-lupin/agent-skills)
hermes plugins install lumen
```

User plugins are opt-in (discovery skips plugins not in `plugins.enabled`). Enable Lumen — accept the install prompt, pass `hermes plugins install --enable`, or after a symlink/copy install run:

```bash
hermes plugins enable lumen
```

Restart Hermes. Skills: `lumen:wiki`, `lumen:curator`.

Python: 3.11 stdlib + PyYAML. Tests: `python3 -m pytest plugins/lumen/tests/` from the agent-skills repo root (or `python3 -m pytest lumen/tests/` in this dev tree).

## Config reference

File: `shared/config/lumen.yaml`. Override with `--config PATH` or `LUMEN_CONFIG`.

```yaml
paths:
  wiki_path: ~/wiki          # else $WIKI_PATH, else ~/wiki

curator:
  timezone: Asia/Singapore
  max_write_pages: 20
  memory_source: auto        # auto | json-file | mnemosyne | none
```

Wiki path order: `--wiki` → `paths.wiki_path` → `$WIKI_PATH` → `~/wiki`.

`auto` tries Mnemosyne when `hermes` is on `PATH`; if the export fails (for example the Mnemosyne plugin is not installed) it falls back to json-file with a warning. Without `hermes` it uses json-file directly (`<wiki>/.knowledge/memory.json`, missing file → empty ingest). Explicit `memory_source: mnemosyne` never falls back.

`index.md` and `overview.md`: the curator only rewrites the block between `<!-- lumen:auto:start -->` and `<!-- lumen:auto:end -->`. Content outside the markers is yours; a file without markers gets a marked block appended.

## Adapter extension point (generic-json)

Shipped adapters: `json-file`, `mnemosyne`, `none`. They are read-only.

Other memory providers can feed the curator by emitting the json-file shape:

```json
{
  "records": {
    "id-1": {
      "id": "id-1",
      "timestamp": "2026-09-20T09:15:00+00:00",
      "text": "...",
      "people": ["Dana"],
      "entities": ["Acme Logistics"],
      "projects": ["pricing-review"]
    }
  }
}
```

A top-level list of records is also accepted. People/entity/project keys are tolerant (`people`/`persons`/`participants`, `project`/`projects`/`deal`, `entity`/`entities`/`organization`/`org`/`company`/`client`/`vendor`).

Write that file to `<wiki>/.knowledge/memory.json` and set `curator.memory_source: json-file`. A future `generic-json` adapter would take an explicit export path; do not import provider internals into Lumen.

## CLI cheatsheet

```bash
python3 <plugin>/skills/curator/scripts/wiki_curator.py run --since 24h
python3 <plugin>/skills/curator/scripts/wiki_curator.py run --since 24h --dry-run
python3 <plugin>/skills/curator/scripts/wiki_curator.py report --since 7d --config /tmp/lumen.yaml
python3 <plugin>/skills/curator/scripts/wiki_curator.py validate --wiki ~/wiki
python3 <plugin>/skills/curator/scripts/wiki_curator.py lint --summary --wiki ~/wiki
python3 <plugin>/skills/curator/scripts/wiki_curator.py search "Acme" --format json --limit 5 --wiki ~/wiki
```

`--since` values: `90m`, `24h`, `7d`, `2w`. `lint`/`validate` exit 1 when any ERROR finding exists.
