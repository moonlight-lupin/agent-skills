---
name: notebooklm-mode
description: >
  Source-grounded research pipeline inspired by NotebookLM. Collect verbatim
  source extracts into a temporary workspace, then answer questions and create
  deliverables grounded in those sources. Two grounding modes: strict
  (vault-only) and augmented (vault + labeled [background] knowledge).
  Trigger when the user asks to research a topic from sources, wants
  NotebookLM-style grounded answers, asks to build a resource vault, or
  says "notebooklm mode".
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
---

# NotebookLM-Grounded Research Pipeline

Research a topic from sources — collect verbatim extracts, index them for
semantic search, then answer questions and create deliverables grounded in
those sources. Inspired by NotebookLM.

## Trigger

- User asks to research a topic "from sources" or "grounded in sources"
- User mentions "notebooklm mode", "source-grounded", or "vault mode"
- User wants responses that cite collected sources, not general knowledge
- User asks to create deliverables from collected sources

---

## Modes

### Direct mode (default)

The orchestrator runs all roles inline — no subagents. Use for most topics.

### Subagent mode (optional)

Spawn agents via `delegate_task` only when genuinely needed: parallel research
across distinct sub-topics, or user explicitly requests it. Not triggered by
source count alone — escalate when the work is genuinely parallel or the user
asks for isolation.

```
delegate_task(
  goal="<user's request>",
  context="You are the [Research|Response|Output] Agent in a NotebookLM
           pipeline. Vault path: <vault_path>. Load skill 'notebooklm-mode'.
           Your role: [Research|Response|Output]. Topic: <topic>.
           Grounding mode: [strict|augmented].",
  toolsets=[<appropriate toolsets per role>]
)
```

Sequential: Research → (user reviews) → Response → (user requests) → Output.
Never dispatch a dependent agent before the previous one returns and files are verified.

### Grounding modes

| Mode | Behavior |
|------|----------|
| **Strict** (default) | Vault only. If it's not in the vault, you don't know it. Gaps are identified, never bridged with inference. |
| **Augmented** | Vault first. General knowledge allowed but must be explicitly tagged `[background]` and clearly separated from vault-sourced claims. User requests this explicitly. |

Augmented mode example:

> According to Source #3: "The LTCI system covers 95% of seniors" [vault]
>
> [background] LTCI was introduced in 2000 as part of Japan's long-term care insurance reform.

---

## Shared Rules (all roles, both modes)

- **Verbatim only** in source files — copy exact wording. Mark `[paraphrased]` only if paywalled and only abstract is available. Mark `[reconstructed from search snippets]` if full-page fetch failed.
- **Cite everything** — every factual claim from the vault references a specific source file and, where possible, a verbatim quote with attribution.
- **Present contradictions honestly** — when sources disagree, present both with attribution. Do not arbitrate.
- **Gap identification ≠ conclusion** — "the vault lacks info on X" is fine; "therefore X is probably Y" is forbidden (strict) or must be tagged `[background]` (augmented).
- **Strip secrets** — scan source content for API keys, tokens, or credentials before saving to vault or outputs.
- **No pre-existing knowledge in source files** — record sources as-is, even if you believe they're wrong. Assessment happens in Response role.

---

## Workspace Vault

The vault is a temporary workspace directory created specifically for the
user's research — **not** part of the permanent library. It holds source
extracts, a per-corpus RAG index, and outputs for one research topic. Clean
up when research is complete, or archive if the user wants to keep it.

**Always confirm the vault location on first interaction:**

> "Where should I create the workspace? Default: `<project_folder>/research-<topic>/`"

The workspace serves as the working directory for the research session. The
user may provide source materials through any connected channel (Telegram,
WhatsApp, etc.) — the agent saves them into `sources/` and indexes them on
the next interaction. The user does not need direct VM filesystem access.

Delivery of outputs works the same way — the agent sends finished deliverables
back through the channel the user requested them on (e.g., Telegram MEDIA:
for files, inline markdown for notes).

### Structure

```
<vault_path>/
├── vault_index.md          # Catalog of sources + outputs
├── sources/                # Verbatim source extracts (one file per source)
│   └── 001_title.md
├── rag_index.db            # Per-corpus sqlite-vec DB (semantic search)
└── outputs/                # Agent-generated deliverables
    └── notes_YYYY-MM-DD.md
```

### Source file format

```markdown
# Source Title

| Field    | Value                     |
|----------|---------------------------|
| URL      | https://example.com/page  |
| Author   | Author Name (if known)    |
| Date     | Publication date (if known) |
| Retrieved| YYYY-MM-DD                |
| Type     | web / pdf / user-provided / youtube |

## Extracts

> "Verbatim quote from the source."
> — Section: Introduction

## Key Data Points

- Statistic: 42% of respondents... (Section: Results)
```

- For websites, extract the **actual content**, not just the URL
- If too long, extract relevant passages and note what was skipped
- Number files sequentially: `001_`, `002_`, etc.
- User-provided files: set Type to `user-provided`, leave URL blank
- Markers for non-verbatim extracts: `[paraphrased]` (paywalled, abstract only), `[reconstructed from search snippets]` (full-page fetch failed)

### vault_index.md

```markdown
# Workspace Vault Index
**Topic:** [topic] | **Created:** YYYY-MM-DD | **Sources:** N | **Mode:** [strict|augmented]

## Sources
| # | File | Type | Title | Retrieved |
|---|------|------|-------|-----------|
| 1 | 001_title.md | web | Article Title | YYYY-MM-DD |

## Coverage Notes
- Well covered: [list] | Gaps: [list]

## Outputs
| File | Type | Created |
|------|------|---------|
| notes_YYYY-MM-DD.md | notes | YYYY-MM-DD |
```

### User-provided materials

Users can provide files through any connected channel (Telegram, WhatsApp,
etc.) at any time. The agent saves them into `sources/`, indexes them, updates
`vault_index.md`, and confirms with the user — no direct VM access needed.

---

## Per-Corpus Semantic Search (optional)

A **new** `rag_index.db` is created fresh inside each workspace — a standalone
sqlite-vec database using the same bge-m3 embeddings as `library-rag`, but
scoped to this research corpus only. Separate research topics get separate
workspace folders, each with its own isolated DB. **Never** indexes into the
main library DB at `~/.hermes/library/rag_index.db`.

**This is optional.** The skill works without it — for small vaults, direct
file reading is sufficient. Semantic search adds value as the corpus grows
(20+ sources). If library-rag is not available, `ingest_source.py` writes
files only and skips indexing.

### Atomic ingest (write + index in one call)

Use the bundled `ingest_source.py` script to write a source file AND index it
into the vault's RAG DB atomically (if RAG is available). This eliminates the
save-then-index two-step that can silently fail on weaker local models.

**Python API:**

```python
import sys; sys.path.insert(0, "<skill_dir>/scripts")
from ingest_source import ingest, search_vault, reindex_vault

# Write + index atomically
result = ingest(vault_path, "001_title.md", content)
print(f"Indexed {result['chunks_indexed']} chunks")

# Semantic search over the vault
results = search_vault(vault_path, "your query", top_k=5)
for r in results:
    print(f"[{r['similarity']:.0%}] {r['source_file']} — {r['section_title']}")
    print(f"  {r['chunk_text'][:200]}")

# Reindex all sources (e.g., after user drops files manually)
reindex_vault(vault_path)
```

**CLI:**

```bash
# Write + index
python3 <skill_dir>/scripts/ingest_source.py \
  --vault <vault_path> --file 001_title.md --content "..."

# Reindex all sources
python3 <skill_dir>/scripts/ingest_source.py --vault <vault_path> --reindex

# Search
python3 <skill_dir>/scripts/ingest_source.py \
  --vault <vault_path> --search "query" --top-k 5
```

The script resolves the library-rag scripts in order: the `LIBRARY_RAG_SCRIPTS`
env var, then the Hermes skills layout, then repo-relative fallbacks (e.g. a
sibling `library-rag/scripts` or `research/library-rag/scripts`). So a plain
clone of this repo works without any env var. No MCP dependency — imports
directly.

### When to use

- **Response** — query the vault semantically instead of loading all source
  files into context. Especially valuable for large vaults (20+ sources).
- **Output** — find all passages related to a theme before creating a deliverable.

For small vaults (<5 sources, short documents), direct file reading is fine —
semantic search adds more value as the corpus grows.

---

## Roles

### Research (Gatherer)

**Purpose:** Research online, find sources, extract verbatim passages, populate vault.

**Tools:** `web_search`, `web_extract`, `browser`, `terminal` (for `ingest_source.py`)

**Behavior:**
1. Clarify scope if topic is broad
2. **Plan the research** — break the topic into 3-6 sub-questions and define success criteria (what would comprehensive coverage look like?). This plan guides search strategy and becomes the stopping check in the gap-analysis step.
3. **Date grounding (mandatory)** — before searching, ground in the real current date: inject "Today's date is {current date as 'DD Month YYYY'}. When a search query needs a year or refers to 'latest'/'current'/'this year', use {current year} — never a year inferred from training data." This prevents stale training-cutoff year references in queries.
4. Search for authoritative, diverse, recent sources — generate queries targeting the sub-questions from step 2
5. **Quality filter** — before extracting, discard low-quality results:
   - Thin content: landing pages, aggregator stubs, <100 words of substantive text
   - Irrelevant: keyword overlap without topical relevance (word-boundary match, not substring)
   - Duplicate URLs: same page appearing in multiple results
   - Non-text: video-only pages, image boards, login walls with no preview
6. Fetch full content, select relevant passages, copy **verbatim** into source content
7. **Atomic ingest** — use `ingest_source.py` to write + index each source in one call. Update `vault_index.md` after each addition.
8. **Gap analysis** — after the first pass, review findings against the research plan:
   - Which sub-questions are unanswered? Which have thin coverage?
   - Generate targeted follow-up queries for the gaps and run another search pass
   - Repeat up to 3 passes total. Document any remaining gaps in `vault_index.md` under Coverage Notes
9. **Stopping criteria** — stop searching when:
   - All sub-questions have ≥1 source addressing them, OR
   - 3 search passes completed, OR
   - 20 sources collected (breadth limit)
   - If stopping with gaps: document them explicitly in Coverage Notes — never paper over with inference
10. Report themes found (not content), ask if user wants deeper research
11. Stop after 5–20 sources (depending on breadth); confirm coverage is adequate

### Response (Grounded Responder)

**Purpose:** Answer questions from the vault. The vault is the knowledge base.

**Tools:** `read_file`, `terminal` (for `search_vault`)

**Behavior:**
1. Read `vault_index.md` first. For large vaults, use `search_vault()` instead of loading all files.
2. Answer using vault content. Cite: *"According to Source #3:..."*
3. Check for unindexed user-provided files before each response (run `reindex_vault` if new files found)
4. If vault doesn't cover the question:
   - **Strict mode**: state the gap, suggest a research prompt. Never insinuate a conclusion.
   - **Augmented mode**: state the gap, suggest a research prompt, and optionally provide `[background]` context clearly separated from vault claims.
5. If sources contradict, present both — do not arbitrate
6. Save substantial responses to `outputs/notes_YYYY-MM-DD.md` with citations

### Output (Creator)

**Purpose:** Create deliverables from vault content using available tools.

**Tools:** `file`, `terminal`, + any needed for output format

**Behavior:**
1. Receive: what to create, scope, format, which sources to draw from
2. Read relevant vault sources (use `search_vault()` for large vaults)
3. Create output using appropriate tools — chain to whatever specialized
   skills your agent runtime has installed (none of these ship in this repo):
   - `.md` → write the file directly
   - `.docx`/`.pptx`/`.xlsx` → an office-document skill, if available
   - Infographics / slides / magazine layouts / data reports / posters → the
     equivalent design or authoring skill, if available; otherwise produce
     structured markdown the user can hand to their own tooling
4. Include source citations (footnotes or inline) and a "Sources" section
5. Save to `outputs/`, update `vault_index.md`
6. Verify output file exists and is valid

---

## Source Feeders

Other skills can feed source files into a vault:

| Skill | How it feeds | Source type |
|-------|-------------|-------------|
| `youtube-topic-research` | `--export-vault` flag exports reviewed videos as `NNN_youtube_*.md` source files with transcript extracts, visual/demo notes, metadata | `youtube` |
| Manual research | Agent saves web extracts directly into `sources/` | `web`, `pdf`, `user-provided` |

When a feeder skill writes sources, run `reindex_vault()` to index them into the vault's RAG DB before Response/Output roles use the vault.

## Orchestrator Routing

| User intent | Role | Mode |
|-------------|------|------|
| "Research [topic]", "Find sources on..." | Research | Direct |
| "What does the vault say about...", "Summarize..." | Response | Direct |
| "Create slides/notes/infographic from the vault" | Output | Direct |
| "Check what's in the vault" | Response | Direct |
| "Find YouTube videos and add to vault" | youtube-topic-research → feeder | Direct |
| "Study John 3:16", "Study Genesis 5 with Calvin", "What does {commentator} say about {passage}" | Research → Response | Direct + `references/book-study.md` |
| Ambiguous — research vs answer | Ask: new sources, or answer from existing vault? | — |

Default to direct mode. Only escalate to subagent mode when the work is
genuinely parallel or the user explicitly requests isolation.

---

## Pitfalls

- **Vault path must be confirmed every new session** — never assume location
- **Vault is temporary** — not part of the permanent library. Clean up when done, or archive if the user wants to keep it. Never index vault sources into the main library RAG unless the user explicitly asks.
- **Subagent file writes are unreliable** — always `ls` the sources directory after a subagent returns; re-create files yourself if missing
- **Bot detection blocks many sites** — prefer Wikipedia, government sites; use `browser_console` for extraction; mark reconstructed extracts as `[reconstructed from search snippets]`
- **Large vaults** — use `search_vault()` instead of loading all source files into context
- **Verbatim means verbatim** — keep source typos, add `[sic]` if it matters
- **Augmented mode discipline** — `[background]` tags are mandatory for any non-vault knowledge. When in doubt, use strict mode.
- **Stale year in queries** — always inject date grounding before searching. Models default to training-cutoff years, producing irrelevant results for time-sensitive topics.
- **Skipping the research plan** — without sub-questions and success criteria, the collection phase has no direction and gap analysis has no baseline. Always plan before searching.
- **Skipping gap analysis** — a single search pass misses follow-up questions. Always review coverage against the plan after the first pass and run targeted follow-up queries for gaps.
- **Papering over gaps** — if a sub-question can't be answered from sources, document it as a gap in `vault_index.md` Coverage Notes. Never bridge with inference (strict) or untagged background knowledge (augmented).
- **Book study needs parse_reference.py** — resolving "John 3:16" to exact text requires the reference parser script (`scripts/parse_reference.py`). If it's missing, fall back to semantic search (less precise — may return the wrong chapter or verse range). See `references/book-study.md` for the full workflow.