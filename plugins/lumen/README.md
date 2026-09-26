# lumen

Requires: Python 3.11+, PyYAML. Tests: python3 -m pytest lumen/tests/.

Standalone LLM wiki plugin for [Hermes Agent](https://hermes-agent.nousresearch.com). Two skills:

- **`lumen:wiki`** — methodology (OKF frontmatter, three-layer layout, ingest/query/lint)
- **`lumen:curator`** — `wiki_curator.py` plus a read-only memory-source adapter layer

This is a **Hermes Agent** plugin. It is not a Claude Code plugin. See [docs/README.md](docs/README.md) for config, adapters, and the CLI cheatsheet.

## Installation

```bash
# From a local checkout
hermes plugins install /path/to/lumen

# Or copy/symlink into the Hermes plugins folder
ln -s /path/to/lumen ~/.hermes/plugins/lumen
```

Catalog install (after this tree is published to `moonlight-lupin/agent-skills`):

```bash
hermes plugins install lumen
```

Hermes user plugins are opt-in: discovery skips any plugin not listed in `plugins.enabled`. Enable Lumen (answer yes to the install prompt, pass `--enable` to `hermes plugins install`, or run this after a symlink/copy install):

```bash
hermes plugins enable lumen
```

Then restart the Hermes session so `register()` runs. Load skills with `skill_view('lumen:wiki')` and `skill_view('lumen:curator')`.

## Configuration

Edit `shared/config/lumen.yaml` or pass `--config`:

| Key | Default | Meaning |
|-----|---------|---------|
| `paths.wiki_path` | `$WIKI_PATH` or `~/wiki` | Wiki root |
| `curator.timezone` | `Asia/Singapore` | Timestamps on generated pages |
| `curator.max_write_pages` | `20` | Cap on source items ingested per `run` |
| `curator.memory_source` | `auto` | `auto` \| `json-file` \| `mnemosyne` \| `none` (`auto` tries Mnemosyne and falls back to json-file if the export fails) |

## License

MIT. See [LICENSE](LICENSE).
