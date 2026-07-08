---
name: library-rag
description: "Semantic search over a personal library using bge-m3 embeddings + sqlite-vec. Index books, documents, any text corpus; query by meaning. Includes EPUB→Markdown conversion and MCP server for auto-available search tools."
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
tags: [rag, embeddings, semantic-search, library, mcp]
---

# Library RAG

Semantic search over `~/.hermes/library/` using bge-m3 embeddings (via OpenRouter) stored in sqlite-vec. Enables meaning-based retrieval across any text corpus — books, documents, reference works — in any language.

## Architecture

```
OpenRouter API (bge-m3, 1024-dim)
        │
        ▼
~/.hermes/library/rag_index.db (sqlite-vec)
  ├── chunks table      — text + metadata (source, book, chapter, section)
  ├── vec_chunks table  — L2-normalized vector embeddings
  └── indexed_files     — SHA-256 hash tracking for incremental updates

MCP Server (mcp_server.py)
  ├── search(query, top_k, source_type)  — semantic search, auto-available
  ├── stats()                             — index statistics
  └── add_book(file_path, ...)            — EPUB/PDF → md → index in one call
```

## Onboarding workflow (run this the first time a user sets up the skill)

When a user wants to start using Library RAG, walk them through this sequence.
Use `AskUserQuestion` for the decisions marked **ASK** — don't assume paths or
silently create directories outside the home folder.

### Step 1 — Check prerequisites

```bash
python3 --version                                   # need 3.9+
python3 -c "import sqlite_vec; print('sqlite-vec ok')" 2>&1
test -n "$OPENROUTER_API_KEY" && echo "key in env" || grep -qs OPENROUTER ~/.hermes/.env && echo "key in .env" || echo "NO API KEY"
```

- If `sqlite-vec` import fails → run `pip install -r requirements.txt` (add
  `--break-system-packages` on externally-managed Python). See README "Installation".
- If `NO API KEY` → help the user create one at <https://openrouter.ai/keys>, then
  store it: `echo 'OPENROUTER_API_KEY=sk-or-v1-...' >> ~/.hermes/.env`.

### Step 2 — Define directories (**ASK**)

Three locations drive everything. Confirm them with the user and export the env vars
(persist in their shell profile). Defaults in parentheses:

| Purpose | Env var | Default | Notes |
|---|---|---|---|
| **Indexed content + vector DB** | `LIBRARY_ROOT` | `~/.hermes/library` | Holds the structured `.md`/`.txt` that get embedded, plus `rag_index.db`. |
| **Vector DB file** | (derived) | `$LIBRARY_ROOT/rag_index.db` | Override per-run with `rag_index.py --db <path>` if you want it elsewhere. |
| **Raw books + conversion staging** | `BOOKS_DIR` | `~/.hermes/book` | Where original EPUBs/PDFs land and where text is extracted. |

Recommended layout (keep raw/text **out of** `LIBRARY_ROOT` — see pitfall below):

```
$BOOKS_DIR/                        staging — NOT indexed
  raw/        original EPUBs/PDFs
  text/       extracted plain text
$LIBRARY_ROOT/                     indexed — scanned recursively
  rag_index.db
  <source_type>/                   top-level dir name becomes the "source type"
    markdown/<slug>/chapters/*.md  the structured files that get embedded
```

> **Pitfall — avoid double-indexing:** `discover_files()` indexes *every* `.md` **and**
> `.txt` under `LIBRARY_ROOT`. If both the extracted `.txt` and the converted `.md` of the
> same book live under `LIBRARY_ROOT`, the content is embedded twice. Keep only **one**
> representation (prefer the structured `.md`) under `LIBRARY_ROOT`; keep raw + text staging
> in `BOOKS_DIR` outside it.

Create the chosen dirs:
```bash
mkdir -p "$LIBRARY_ROOT" "$BOOKS_DIR/raw" "$BOOKS_DIR/text"
```

### Step 3 — Add the first content & build the index

- **EPUB/PDF via MCP (if the server is configured):** call `add_book(...)` — it converts and
  indexes in one step.
- **Manual:** drop source files in `$BOOKS_DIR/raw`, convert to structured markdown under
  `$LIBRARY_ROOT/<source_type>/` (see `convert_epub_library.py` and
  `references/epub-conversion.md`), then:

```bash
python3 scripts/rag_index.py --dry-run     # preview chunk counts, no API cost
python3 scripts/rag_index.py               # incremental build
python3 scripts/rag_query.py --stats       # confirm chunks landed
python3 scripts/rag_query.py "a test query"
```

### Step 4 — Automated scanning/conversion/indexing (**ASK**)

Ask the user whether they want new files indexed **automatically** or **manually**:

- **Manual (default, recommended to start):** they run `python3 scripts/rag_index.py`
  after adding files. Incremental + SHA-256 tracking means re-runs are cheap and only touch
  new/changed files. No setup needed.
- **Automated (cron):** schedule a periodic incremental index. Only offer this once Step 3
  works end-to-end. Example — index nightly at 02:00 and log output:

  ```bash
  # crontab -e   (adjust the repo path and env vars)
  0 2 * * * OPENROUTER_API_KEY=sk-or-v1-... LIBRARY_ROOT=$HOME/.hermes/library \
    /usr/bin/python3 $HOME/library-rag/scripts/rag_index.py >> $HOME/.hermes/rag_index.log 2>&1
  ```

  If they also want EPUBs auto-converted before indexing, chain a conversion step ahead of
  `rag_index.py` in the same cron line (or a small wrapper script). On macOS, `launchd` /
  a `launchd` plist is the more reliable equivalent of cron.

  **Cron cautions to mention:**
  - Cron has a minimal environment — set `OPENROUTER_API_KEY`, `LIBRARY_ROOT`, and use an
    **absolute** `python3` path (or activate the venv inside a wrapper script).
  - Never overlap two `--rebuild` runs on the same DB (see Pitfalls). A nightly incremental
    run is safe; a full `--rebuild` should stay manual.
  - Each run costs roughly `$0.01/M tokens` — effectively free, but the log shows actual cost.

After onboarding, summarize for the user: the three paths chosen, where the DB lives, and
whether indexing is manual or scheduled.

## MCP Tools (auto-available in every conversation)

Once configured in `config.yaml`, these tools are available as
`mcp_library_rag_search`, `mcp_library_rag_stats`, `mcp_library_rag_add_book`.

### Config

```yaml
# ~/.hermes/config.yaml
mcp_servers:
  library_rag:
    command: "python3"
    args: ["~/.hermes/skills/research/library-rag/scripts/mcp_server.py"]
    timeout: 60
```

Restart the gateway after adding.

### search

```
mcp_library_rag_search(query="your search query", top_k=10)
mcp_library_rag_search(query="search terms", source_type="my-source-type")
```

Returns JSON array of results with `similarity`, `source_type`, `book`, `chapter`,
`section_title`, `text`.

### stats

```
mcp_library_rag_stats()
→ {"total_chunks": 78000, "files_indexed": 1383, "by_source": {...}}
```

### add_book

```
mcp_library_rag_add_book(
    file_path="/path/to/book.epub",   # or /path/to/doc.pdf
    book_slug="my-new-book",
    author="Author Name",
    title="Book Title",
    year="2024"
)
```

Converts EPUB → chapters or PDF → pages, then indexes them. One-call workflow for adding
new books to the library.

## Scripts (for batch operations)

### rag_index.py — Indexer

```bash
# Index all new/changed files (incremental — SHA-256 hash tracking)
python3 scripts/rag_index.py

# Full rebuild (drop everything, re-index from scratch)
python3 scripts/rag_index.py --rebuild

# Dry run (show what would be indexed, no API calls)
python3 scripts/rag_index.py --dry-run

# Index only one source type
python3 scripts/rag_index.py --source my-source-type
```

**When to use:**
- After adding new files to the library → run incremental (default)
- After changing chunking strategy → run `--rebuild`
- To estimate cost/time → run `--dry-run` first

### rag_query.py — CLI Query

```bash
python3 scripts/rag_query.py "your search query"
python3 scripts/rag_query.py "search terms" --top-k 5
python3 scripts/rag_query.py "query" --source my-source-type --verbose
python3 scripts/rag_query.py --stats
```

Can also be imported:
```python
from rag_query import search
results = search("query text", top_k=10)
```

## Conversion Tools

### EPUB → Markdown (`scripts/convert_epub_library.py`)

Extracts text from EPUB files and splits into per-chapter Markdown with YAML frontmatter.
Runnable as a CLI or importable as `convert_epub()` — the same implementation backs the MCP
`add_book` tool, so there is one conversion code path.

```bash
python3 scripts/convert_epub_library.py \
    --epub book.epub --slug my-book --title "Book Title" --author "Author" --year 2024 \
    --md-root ~/.hermes/library/books/markdown   # under LIBRARY_ROOT so it gets indexed
```

Raw EPUB + extracted text stage under `$BOOKS_DIR` (outside `LIBRARY_ROOT`); only the
structured markdown is written to `--md-root`, so the raw text is never double-indexed.

Chapter detection tries several styles (`CHAPTER 12` / `CHAPTER One` / `PART IV` /
`12. Title` / bare `12\nTitle`), picking the first that confidently applies, and guards
against date/page-number false positives. Before trusting a conversion, eyeball
`convert_epub_library.audit_chapter_markers(text)` — every entry should be a real chapter,
not a date or page number.

Key pitfalls (see `references/epub-conversion.md` for full details):
1. **Multiple TOC ghosts**: Large EPUBs produce multiple table-of-contents blocks. Skip all when finding chapter headings in body text.
2. **CHAPTER N vs N. Title**: EPUBs use different heading patterns in TOC vs body. Match the BODY pattern.
3. **Title + subtitle leak into YAML**: Use only the main title for the `title:` field.
4. **Slug truncation**: Truncate slugs to 60 chars (preserving the `chNN-` prefix).
5. **Page-number blocks**: Some EPUBs extract huge blocks of standalone page numbers. Detect and exclude.
6. **Post-processing pass**: Always verify every `.md` file has valid YAML frontmatter.

### PDF → Markdown (`scripts/convert_pdf_library.py`)

Extracts text **and tables** with `pdfplumber`. Each page → a `## Page N` section (so the
markdown chunker yields per-page citations); tables → `**[Table N]**` blocks. CLI or
`convert_pdf()`; it also backs `add_book` for `.pdf` inputs.

```bash
python3 scripts/convert_pdf_library.py \
    --pdf doc.pdf --slug my-doc --title "Doc" --author "Author" --year 2024 \
    --md-root ~/.hermes/library/books/markdown
```

The table block is display-only: `clean_for_embedding` strips `**[Table N]**` and rows ending
in `<br>` from the embedding input (the page's narrative text already carries the table content
linearly), so tables stay searchable without being embedded twice.

### Built-in chunkers (`rag_index.py`)

| Chunker | Input | Strategy |
|---|---|---|
| `chunk_markdown()` | `.md` with headings | Split by `##`/`###` (a `###` chunk carries its parent `##` as a `Section — Subsection` breadcrumb), paragraph merge fallback, single-newline normalization |
| `chunk_plain_text()` | `.txt` files | Paragraph merge with 15% overlap |

For domain-specific formats (PDFs, XML, JSON), write a custom chunker and register it in
`discover_files()`. See `references/chunking-strategies.md` for patterns.

## Adding new books to the library

### Quick path (EPUB/PDF via MCP)

Use `mcp_library_rag_add_book` — it dispatches on extension and handles
EPUB/PDF → md → index in one call.

### Manual path

1. **Convert to structured Markdown** with the converter CLI for the format. Both stage
   the raw file + extracted text under `$BOOKS_DIR` (outside `LIBRARY_ROOT`, so they're not
   indexed) and write markdown to `--md-root`:

   ```bash
   # EPUB → per-chapter markdown
   python3 scripts/convert_epub_library.py \
       --epub book.epub --slug <slug> --title "..." --author "..." --year 2024 \
       --md-root $LIBRARY_ROOT/books/markdown

   # PDF → per-page markdown (tables preserved)
   python3 scripts/convert_pdf_library.py \
       --pdf doc.pdf --slug <slug> --title "..." --author "..." --year 2024 \
       --md-root $LIBRARY_ROOT/books/markdown
   ```

   For other sources (XML/JSON, etc.), follow the extraction pattern in
   `references/chunking-strategies.md` and write the markdown under
   `$LIBRARY_ROOT/<source_type>/` yourself.

2. **Register the chunker** (if new file type):
   - Add a chunker function in `rag_index.py`
   - Register it in `discover_files()`
   See `references/chunking-strategies.md` for patterns and pitfalls.
   See `references/portable-rag-per-skill.md` for the standalone per-skill RAG pattern.
   See `references/rag-pipeline-review.md` for a systematic audit checklist.

3. **Index:**
   ```bash
   python3 scripts/rag_index.py  # incremental — only new files
   ```

## Cost

Provider pricing changes — check current [OpenRouter pricing](https://openrouter.ai/baai/bge-m3).
At the time of writing (bge-m3 ≈ **$0.01 per million tokens**):

- A typical book (300 pages, ~100K tokens): **~$0.001**
- Query: 1 API call per search (~$0.0000001)

Effectively free for personal use.

## Portable Standalone RAG Instances

The same bge-m3 → sqlite-vec pattern can be deployed as a **standalone,
self-contained RAG** inside any skill directory — no MCP registration, no
dependency on `~/.hermes/library/`. This makes the skill portable: zip the
folder, drop on another machine, it works.

### How to build a standalone instance

1. **Copy** `rag_index.py` and `rag_query.py` into the skill's `scripts/` dir
2. **Parameterize the DB path** — replace the hardcoded `LIBRARY_ROOT` /
   `DB_PATH` with an env var or CLI flag, defaulting to the skill's own
   `references/` directory
3. **Write a domain-specific chunker** — chunk by the document's natural
   structure (headings, sections). For PDF-extracted content, parse
   `<!-- Page N -->` markers via `split_by_pages()` for per-chunk page citations.
4. **Do NOT register an MCP server** — scripts import `rag_query.py` directly:
   ```python
   from rag_query import search
   results = search("query text", top_k=5)
   ```
5. **L2-normalize vectors at store + query time** — add `normalize_vec()` to
   `float_to_blob()` (indexer) and `get_embedding()` (query). Makes cosine
   similarity exact, not an implicit assumption.
6. **Add ~15% chunk overlap** — `split_long_text()` should carry the tail
   of each chunk into the next for better recall.
7. **Clean embedding input** — `clean_for_embedding()` must strip `<br>`,
   `**[Table N]**`, and `<!-- Page N -->` in addition to markdown markers.
8. **Wire in `MIN_CHUNK_CHARS`** — call `merge_tiny_chunks()` after chunking
   to prevent near-empty chunks from diluting search results.
9. **Shared dependency:** the OpenRouter API key (bge-m3).
   The embedding model and sqlite-vec extension are shared, not duplicated.

See `references/portable-rag-per-skill.md` for full code patterns and
`references/rag-pipeline-review.md` for a systematic audit checklist.

### When to use standalone vs. the main library

| Use the main library when... | Use standalone when... |
|---|---|
| Content is reference/books you want globally searchable | Content is domain-specific (rulebooks, code docs, etc.) |
| You want auto-available MCP search tools | You want the skill to be portable/self-contained |
| Content should be globally searchable | Content should only surface when that skill is loaded |

## Pitfalls

- **sqlite-vec must be loaded before DROP/CREATE of vec0 tables**: The extension must be loaded first in `init_db()`.
- **`file_hash` must be added to chunks before storing**: The indexer adds it after chunking but before embedding. Don't forget this when adding new chunkers.
- **Single-newline wrapping**: Some text sources use single `\n` for line wrapping, not paragraph breaks. Normalize to spaces before splitting on `\n\n`.
- **MCP server timeout**: The default 60s timeout is fine for `search` and `stats`. `add_book` may need more time for large EPUBs — increase `timeout` in config if needed.
- **sqlite-vec source filtering**: sqlite-vec's `MATCH`/`k` vector search cannot be combined with arbitrary `WHERE` clauses. `source_type` and `source_book` filters must be applied as post-filters after over-fetching results (fetch `top_k * 5`, then filter on chunk metadata). See `references/portable-rag-per-skill.md` for the correct pattern.
- **Portable RAG instances**: To create a standalone RAG for a different skill, copy `rag_index.py` and `rag_query.py` and parameterize: (1) resolve paths from `__file__` not hardcoded `LIBRARY_ROOT`, (2) store DB inside the skill's `references/` dir, (3) skip the MCP server — import `search()` directly instead, (4) write a domain-specific chunker, (5) parse `<!-- Page N -->` markers for per-chunk page citations, (6) L2-normalize vectors at store+query time, (7) add ~15% chunk overlap for better recall. See `references/portable-rag-per-skill.md` for the full pattern.
- **Page citations require marker parsing**: PDF extractors insert `<!-- Page N -->` comments, but chunkers must actively parse them — otherwise all chunks degrade to chapter-level citations. Use `split_by_pages()` in the chunker to split by markers and stamp each chunk with its page.
- **L2 normalization required for exact similarity**: `1 - dist²/2` is only exact cosine if both stored and query vectors are unit-normalized. bge-m3 returns unit-norm vectors, but `normalize_vec()` is called at store time (`float_to_blob`) and query time (`get_embedding`) to guarantee this explicitly.
- **`clean_for_embedding` must strip table/PDF artifacts**: In addition to markdown markers, strip `<br>`, `**[Table N]**`, and `<!-- Page N -->` from embedding input. These are noise from PDF table extraction. Chunk text in the DB retains them for display readability.
- **Never run two `--rebuild` processes on the same DB simultaneously**: SQLite allows concurrent connections but `--rebuild` drops and recreates tables. If a foreground test and a background job overlap, the background process gets spurious "Failed after 3 retries" errors. Always let any foreground `--rebuild` test fully exit before starting the background job, or use `--dry-run` for quick tests (it doesn't touch the DB).
- **Full library re-index takes ~50-90 min**: Small files finish fast, large text collections dominate. Cost: ~$0.01-$0.12 depending on corpus size. No rate limiting observed on OpenRouter `/v1/embeddings` with 0.3s delay between batches of 32.
