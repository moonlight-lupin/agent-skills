---
name: skill-retrieval
version: 0.1.0
description: >-
  BM25-based skill retrieval plugin for Hermes Agent. Replaces the full skill
  list in the system prompt with a names-only compact view (~2K tokens) and
  injects top-K relevant skill descriptions per turn via BM25 retrieval (~300
  tokens). Saves ~9K tokens/turn. Use when system prompt token overhead from
  skills is a concern, or when skill discovery quality matters.
author: MH
license: MIT
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
`plugin.yaml`. Developed against Hermes Agent >=0.20.0.

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
   the top-K matches (~300 tokens) as context above the user message.

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
Retrieval uses scipy sparse matrices and is sub-millisecond for ~128 skills.

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

Ensure the plugin is enabled in Hermes (plugins under `~/.hermes/plugins/`
with a valid `plugin.yaml` are typically auto-discovered). Restart the agent
session so `register()` runs — it patches the system prompt and registers the
`pre_llm_call` hook.

Dependencies (install into the Hermes Python env if missing):

```bash
pip install numpy scipy pyyaml
```

## Configuration

| Setting | Default | How to set |
|---------|---------|------------|
| `TOP_K` | `6` | Env var `SKILL_RETRIEVAL_TOP_K` |
| BM25 `k1` | `1.5` | Constant in `scripts/bm25_retriever.py` |
| BM25 `b` | `0.75` | Constant in `scripts/bm25_retriever.py` |

```bash
export SKILL_RETRIEVAL_TOP_K=8
```

## Verify it's working

Phase 1 silently no-ops outside a full Hermes runtime, and the BM25 index can
silently empty. After restart, check the Hermes logs.

**Healthy start — look for these log lines:**

- `BM25 index built: N docs …`
- `Skill retrieval plugin registered (top_k=…, compact=true)`

**Degraded — these warnings mean it's not working:**

- `Cannot locate prompt_builder — compaction skipped` (Phase 1 failed, Phase 2 still works)
- `No active skills found for BM25 index` (index is empty — zero retrieval injection)

## How it works

- **Tokenizer** — lowercases text, strips punctuation, splits on whitespace.
- **Corpus** — each skill becomes `"name: description"` from SKILL.md YAML
  frontmatter. Disabled skills from `~/.hermes/config.yaml` are skipped.
- **Index** — BM25 Okapi TF saturation + Lucene-style clipped IDF, stored as a
  scipy CSR sparse matrix.
- **Retrieve** — query tokens → sparse vector → dot product → top-K by score
  (descending, score > 0 only).

## Performance

- Index built once at plugin load.
- Retrieval is sub-millisecond for on the order of 128 skills.
- Failures in the hook return `None` (no injection) so the agent keeps working.

## Dependencies

- `numpy`
- `scipy`
- `pyyaml`

## Limitations

- BM25 is **lexical**, not semantic. Paraphrased queries that share few tokens
  with a skill's description may rank poorly even when the intent matches.
- Descriptions longer than 200 characters are truncated in the injected block;
  use `skill_view(name)` for the full skill body.
- Compaction requires Hermes's `prompt_builder` / `run_agent` modules; if they
  cannot be imported, Phase 1 is skipped (Phase 2 still works if skills load).
- The index is built once at load and never refreshes — skills added, edited,
  or enabled mid-session are invisible until the agent restarts.
- Phase 1 depends on Hermes internals (`prompt_builder`, `run_agent`) and can
  break on a Hermes upgrade.
- BM25 top-1 precision is soft — `TOP_K` below ~5 is not recommended. Observed:
  "generate an image" ranks `pexels-stock-photos` above `image-studio`;
  "plan a trip to Japan" ranks `task-brief` above `travel-itinerary`. Both land
  inside the top 6.
