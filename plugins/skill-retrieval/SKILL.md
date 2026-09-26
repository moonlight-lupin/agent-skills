---
name: skill-retrieval
description: >-
  BM25-based skill retrieval plugin for Hermes Agent. Replaces the full skill
  list in the system prompt with a names-only compact view (~2K tokens) and
  injects top-K relevant skill descriptions per turn via BM25 retrieval (~300
  tokens). Saves ~9K tokens/turn. Use when system prompt token overhead from
  skills is a concern, or when skill discovery quality matters.
license: MIT
metadata:
  version: 0.3.0
  author: moonlight-lupin
  platforms: [linux, macos, windows]
  tags: [bm25, skill-retrieval, system-prompt, token-optimization, plugin]
  hermes:
    plugin_type: hook
    hooks: [pre_llm_call]
---

# Skill Retrieval

This is a **Hermes Agent** plugin. It is not a Claude Code plugin and will
not load in Claude Code — that runtime has no `pre_llm_call` event, no Python
`register()` entry point, and reads `.claude-plugin/plugin.json` rather than
`plugin.yaml`. Requires Hermes Agent >=0.21.1 (`requires_hermes` in
`plugin.yaml`).

BM25-based progressive disclosure for Hermes Agent skills. Instead of dumping
every skill description into the system prompt (~11.5K tokens), this plugin
keeps a compact names-only index and injects only the top-K relevant
descriptions per turn.

## What it does

Two-phase progressive disclosure:

1. **Phase 1 — System prompt compaction** (session start): Monkey-patches
   `build_skills_system_prompt` so the `<available_skills>` block lists skill
   names only (descriptions stripped). All skills remain discoverable by name
   (~2K tokens instead of ~11.5K).

2. **Phase 2 — Per-turn BM25 retrieval** (`pre_llm_call` hook): Tokenizes the
   user message, ranks active skill descriptions with BM25 Okapi, and injects
   the top-K matches (~300 tokens) as context appended after the user
   message.

## Architecture

```
Session start
    │
    ▼
Phase 1: patch build_skills_system_prompt
    └── <available_skills> → names only (~2K tokens)

Each turn (pre_llm_call)
    │
    ▼
Phase 2: BM25Index.retrieve(user_message, top_k)
    └── inject "## Retrieved Skills ..." into user message (~300 tokens)
```

The BM25 index is built once at plugin load from standalone skills
(`~/.hermes/skills`) and plugin-bundled skills (`~/.hermes/plugins/*/skills`).
Retrieval uses a pure-stdlib inverted index (term → posting list of
precomputed BM25 weights) and is sub-millisecond for ~200 skills.

## Token savings

| Stage | Tokens (approx.) |
|-------|------------------|
| Before (full skill list in system prompt) | ~11.5K |
| After — names-only system prompt | ~2.0K |
| After — per-turn top-K descriptions | ~0.3K |
| **Net per turn** | **~2.3K** (~9K saved) |

Measured on a Hermes install with ~300 skills; savings scale with skill count.

## Installation

Copy or symlink this directory into the Hermes plugins folder:

```bash
# From this repo
ln -s "$(pwd)/plugins/skill-retrieval" ~/.hermes/plugins/skill-retrieval

# Or copy
cp -r plugins/skill-retrieval ~/.hermes/plugins/skill-retrieval
```

User plugins are opt-in: Hermes discovers the directory but does not load it
until it is enabled (this adds `skill-retrieval` to `plugins.enabled` in
`~/.hermes/config.yaml`):

```bash
hermes plugins enable skill-retrieval
```

Restart the agent session so `register()` runs — it patches the system prompt
and registers the `pre_llm_call` hook.

Dependencies (install into the Hermes Python env if missing):

```bash
pip install pyyaml
```

## Configuration

| Setting | Default | How to set |
|---------|---------|------------|
| `TOP_K` | `6` | Env var `SKILL_RETRIEVAL_TOP_K` |
| System prompt compaction | enabled | Set `SKILL_RETRIEVAL_COMPACT=0` to disable compaction while keeping BM25 retrieval injection |
| BM25 `k1` | `1.5` | Constant in `scripts/bm25_retriever.py` |
| BM25 `b` | `0.75` | Constant in `scripts/bm25_retriever.py` |

```bash
export SKILL_RETRIEVAL_TOP_K=8
export SKILL_RETRIEVAL_COMPACT=0
```

## Verify it's working

Phase 1 silently no-ops outside a full Hermes runtime, and the BM25 index can
silently empty. After restart, check the Hermes logs.

**Healthy start — look for these log lines:**

- `BM25 index built: N docs …`
- `Skill retrieval plugin registered (top_k=…, compact=true)`

**Degraded — these warnings mean it's not working:**

- `Cannot locate prompt_builder — compaction skipped` (Phase 1 failed; Phase 2
  still runs for anonymous sessions, but named sessions skip injection because
  no capability snapshot is recorded)
- `No active skills found for BM25 index` (index is empty — zero retrieval injection)

## How it works

- **Tokenizer** — lowercases text, strips punctuation, splits on whitespace.
- **Corpus** — each skill becomes `"name: description"` from SKILL.md YAML
  frontmatter. Disabled skills from `~/.hermes/config.yaml` are skipped.
- **Index** — BM25 Okapi TF saturation + Lucene IDF
  `log(1 + (N-df+0.5)/(df+0.5))` (always positive, so small corpora and common
  terms still score), stored as an inverted index:
  ``dict[str, list[tuple[int, float]]]`` mapping each term to a posting list of
  (doc_index, precomputed BM25 weight).
- **Retrieve** — for each unique query token present in the index, walk its
  posting list and accumulate scores; sort by descending score (score > 0 only).

## Performance

- Index built once at plugin load (~8 ms for 200 skills on a CPU-only VM).
- Retrieval is sub-millisecond (~0.03 ms mean for 200 skills). The inverted
  index touches only documents that share a query term — no full-corpus scan.
- No compiled dependencies. The plugin uses only the Python standard library
  (plus pyyaml for config/frontmatter parsing). This removes a 154 MB
  numpy/scipy install and a ~573 ms import cost, which matters for subprocess
  spawning paths (e.g. a Claude Code `UserPromptSubmit` variant).
- Failures in the hook return `None` (no injection) so the agent keeps working.

## Dependencies

- `pyyaml`

## Limitations

- BM25 is **lexical**, not semantic. Paraphrased queries that share few tokens
  with a skill's description may rank poorly even when the intent matches.
- Descriptions longer than 200 characters are truncated in the injected block;
  use `skill_view(name)` for the full skill body.
- Compaction requires Hermes's `agent.prompt_builder` module; if it cannot be
  imported, Phase 1 is skipped.
- A named session is only injected once its system prompt has been built in
  this process (that build records the session's tool capabilities). A session
  restored after a restart without a rebuild gets no injection rather than
  risking skills Hermes hides from it.
- The index is built once at load and never refreshes — skills added, edited,
  or enabled mid-session are invisible until the agent restarts.
- Phase 1 depends on Hermes internals (`agent.prompt_builder`) and can break
  on a Hermes upgrade.
- BM25 top-1 precision is soft: the best-matching skill is often not rank 1,
  though it usually lands within the first few results. Ranking depends entirely
  on your own corpus and how its descriptions are worded, so `TOP_K` below ~5 is
  not recommended.
- The stdlib index computes in float64 (the previous scipy version used
  float32). Equal-scoring skills may order differently than before. This is
  harmless — the scores are genuine ties (~1e-6 difference) — but it is a real
  behaviour delta from the scipy version.
