# skill-retrieval

BM25-based skill retrieval plugin for [Hermes Agent](https://hermes-agent.nousresearch.com). Replaces the full skill list in the system prompt with a names-only compact view (~2K tokens) and injects top-K relevant skill descriptions per turn (~300 tokens), saving ~9K tokens/turn while keeping skills discoverable by name. Those figures were measured on a Hermes install with ~300 skills; the saving scales with your own skill count.

This is a **Hermes Agent** plugin. It is not a Claude Code plugin and will not load in Claude Code — that runtime has no `pre_llm_call` event, no Python `register()` entry point, and reads `.claude-plugin/plugin.json` rather than `plugin.yaml`. Requires Hermes Agent >=0.21.1.

See [SKILL.md](SKILL.md) for full architecture, token measurements, how it works, performance, limitations, and how to verify a healthy install.

## Contents

- Installation
- Configuration
- Read-only core references
- Uninstall
- Data handling (Jev rerank)
- License

## Installation

```bash
# From the agent_skills repo root
ln -s "$(pwd)/plugins/skill-retrieval" ~/.hermes/plugins/skill-retrieval

# Named profile: the plugin reads its own directory relative to the plugin
# folder, and keys/paths resolve under $HERMES_HOME (set per profile) — no
# cross-profile fallback. Copy the plugin into the profile's plugins/ dir
# and set any needed keys in that profile's environment (Hermes loads the
# profile's .env into os.environ at startup).

# Dependencies (Hermes Python env)
# pyyaml is the only dependency — usually already present in a Hermes env
pip install pyyaml
```

User plugins are opt-in — Hermes discovers the directory but does not load it until you enable it:

```bash
hermes plugins enable skill-retrieval
```

Then restart the Hermes session so the plugin's `register()` runs.

## Configuration

| Setting | Default | Override |
|---------|---------|----------|
| Top-K results | `6` | `SKILL_RETRIEVAL_TOP_K` env var |
| System prompt compaction | enabled | `SKILL_RETRIEVAL_COMPACT=0` disables compaction but keeps retrieval injection |
| BM25 k1 | `1.5` | edit `scripts/bm25_retriever.py` |
| BM25 b | `0.75` | edit `scripts/bm25_retriever.py` |
| Jev rerank | off | `SKILL_RETRIEVAL_RERANK=jev` enables; key `TYPESAFE_API_KEY` (legacy `TYPESAFE_KEY` accepted) from `os.environ` |
| Rerank A/B log | `$HERMES_HOME/data/jev-trial/rerank_ab_log.jsonl` (rotates to `.1` past 5 MB) | `SKILL_RETRIEVAL_RERANK_LOG` env var |

```bash
export SKILL_RETRIEVAL_TOP_K=8
export SKILL_RETRIEVAL_COMPACT=0  # retrieval-only mode; the skills prompt is left unchanged (the builder is still wrapped to record tool capabilities)
export SKILL_RETRIEVAL_RERANK=jev  # optional: rerank the top-K with the Jev system-one model
```

### Jev rerank

Optional, off by default. When enabled, the BM25 top-N shortlist is reranked by the Jev system-one judgment model (`api.typesafe.ai/v1/systemone`, model `jev-latest`). It is fail-soft: a 3.0 s timeout with no retries, and any error falls back to the BM25 order. The key is read from `os.environ` only (Hermes loads the active profile's `.env` into environ at startup — no cross-profile file reads). Every query is logged to the A/B log path; `scripts/rerank_ab_report.py` summarizes the log locally. See **Data handling** below for exactly what leaves the machine.

## Read-only core references

The plugin imports ten Hermes core helpers **read-only** (never assigned, never wrapped). From `agent.prompt_builder`:

- `_current_session_platform_hint` — session platform for cache keying and visibility gating
- `_parse_skill_file`, `_build_snapshot_entry` — SKILL.md frontmatter/description parsing for the corpus
- `_skill_should_show` — per-skill visibility gating (tools, toolsets, platform)
- `extract_skill_conditions` — condition extraction feeding `_skill_should_show`

From `agent.skill_utils`:

- `get_all_skills_dirs`, `get_project_skills_dirs` — skill root resolution (profile, external dirs)
- `get_disabled_skill_names` — disabled-set gating
- `iter_project_skill_files`, `iter_skill_index_files` — SKILL.md file enumeration
- (`skill_matches_platform` is consulted via `getattr` when present)

These are read-only imports disclosed per the catalog's rule-9 note. If a Hermes upgrade changes their signatures, the corpus loader is guarded: any mid-scan exception falls back to the standalone loader, so the index is never silently empty while compaction strips descriptions. If a future change needs an assignment or wrap there, that counts against rule 9's strict reading and warrants a core seam request instead.

In `codex_app_server` mode the prompt goes to Codex as `developerInstructions` and bypasses `llm_request`, so that mode gets no compaction and no snapshot, while turn-1 fail-open still retrieves.

## Uninstall

1. Disable the plugin (`hermes plugins disable skill-retrieval`), then delete the plugin folder from `~/.hermes/plugins/` with your file manager or shell.
2. Restart the Hermes session
3. The system prompt reverts on restart

The middleware and hook are session-scoped, so removal is otherwise instant.

## Data handling (Jev rerank)

The rerank is **off by default**. With no `SKILL_RETRIEVAL_RERANK=jev` set,
the plugin makes **no network calls** and writes nothing.

When you opt in (`SKILL_RETRIEVAL_RERANK=jev` + a key present):

- **Sent to `api.typesafe.ai`** (one POST per retrieval turn, model
  `jev-latest`): the user message flattened and stripped of imperative
  patterns, capped at 2000 characters, plus the top-12 shortlisted skills'
  descriptions, each capped at 400 characters. The BM25 scores and skill ids
  never leave the machine beyond those descriptions. The response carries one
  relevance probability per candidate.
- **Key**: `TYPESAFE_API_KEY` (legacy `TYPESAFE_KEY` accepted), read from
  `os.environ` only — Hermes loads the active profile's `.env` into
  environ at startup, so no other profile's file is ever read. The key is
  never logged, never written, never included in any record.
- **Local log**: each reranked turn appends one JSONL line to
  `$HERMES_HOME/data/jev-trial/rerank_ab_log.jsonl` (override:
  `SKILL_RETRIEVAL_RERANK_LOG`) containing the timestamp, session id, a
  200-character query excerpt, the BM25 order, the Jev order, probabilities,
  token count, and latency. The log rotates to `<name>.1` past 5 MB, so it
  never grows without bound. `scripts/rerank_ab_report.py` summarizes it
  locally; no log data is uploaded anywhere.

## License

MIT. See [LICENSE](LICENSE) for the upstream SR-Agents notice and this project's notice.