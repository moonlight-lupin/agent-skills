# Library RAG

A complete pipeline for building a personal semantic search library: **acquire → convert → index → search**. Uses bge-m3 embeddings via OpenRouter, stored in sqlite-vec for meaning-based retrieval.

## Pipeline

```
1. Acquire    — Bring your own texts (EPUB & PDF built-in; XML/JSON need a custom chunker)
2. Convert    — EPUB → Markdown (chapters) · PDF → Markdown (pages + tables)
3. Index      — bge-m3 embeddings → sqlite-vec (incremental, SHA-256 tracked)
4. Search     — Meaning-based retrieval with per-chunk citations
```

## Architecture

```
OpenRouter API (baai/bge-m3, 1024-dim)
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

## Features

- **Meaning-based retrieval** — search by concept, not keywords
- **Bilingual** — works across English, Chinese, and other languages
- **EPUB & PDF built-in** — chapter-split EPUBs and page-split PDFs (tables preserved for display, dropped from embeddings)
- **Per-chunk citations** — every result includes book, chapter/page, section title
- **Incremental indexing** — SHA-256 file hash tracking; only new/changed files get re-embedded
- **Atomic per-file indexing (blue/green)** — a re-index stores the new version before retiring the old, so the previous version stays searchable until the new one fully succeeds; partial failures roll back just the new chunks and retry next run (no duplicates, no search gap)
- **L2-normalized vectors** — cosine similarity is exact, not an implicit assumption
- **Chunk overlap (15%)** — better recall for content that straddles chunk boundaries
- **MCP integration** — auto-available search tools when registered in Hermes config.yaml

## Conversion Tools

Before indexing, raw source files must be converted to structured Markdown with YAML frontmatter.
The pipeline includes built-in EPUB and PDF conversion:

### EPUB → Markdown (`scripts/convert_epub_library.py`)

Extracts text from EPUB files using `ebooklib` + `BeautifulSoup`, splits by chapter headings
into per-chapter `.md` files with frontmatter (`author`, `book`, `chapter`, `year`, `slug`,
`source`), and runs a YAML-leak post-processing pass. The raw EPUB and extracted text are
staged outside the index; only the structured markdown is written to `--md-root`.

```bash
python3 scripts/convert_epub_library.py \
    --epub /path/to/book.epub --slug my-book \
    --title "Book Title" --author "Author Name" --year 2024 \
    --md-root ~/.hermes/library/books/markdown   # point under LIBRARY_ROOT to make it indexable

# Then index the new chapters:
python3 scripts/rag_index.py
```

Importable too — `from convert_epub_library import convert_epub`. The same function backs the
MCP `add_book` tool, so CLI and MCP share one conversion implementation. Chapter detection
tries several heading styles (`CHAPTER 12` / `CHAPTER One` / `PART IV` / `12. Title` / bare
`12\nTitle`) and skips date/page-number false positives; eyeball
`audit_chapter_markers(text)` before trusting a conversion.

Key pitfalls (see `references/epub-conversion.md` for full details):
- Multiple TOC ghosts in large EPUBs — skip all when finding chapter headings
- `CHAPTER N` body pattern differs from TOC pattern — grep for the body pattern
- Title/subtitle leak into YAML — use only the main title
- Slug truncation to 60 chars to avoid filesystem errors
- Page-number blocks — detect and exclude

### PDF → Markdown (`scripts/convert_pdf_library.py`)

Extracts text **and tables** with `pdfplumber`. Each page becomes a `## Page N` section
(so search results cite the page), and tables are rendered as `**[Table N]**` blocks. The
table block is display-only — `clean_for_embedding` drops it from the embedding input since
the page's narrative text already carries the table content linearly, keeping it searchable
without double-embedding.

```bash
python3 scripts/convert_pdf_library.py \
    --pdf /path/to/doc.pdf --slug my-doc \
    --title "Doc Title" --author "Author Name" --year 2024 \
    --md-root ~/.hermes/library/books/markdown

python3 scripts/rag_index.py
```

Importable as `from convert_pdf_library import convert_pdf`; it also backs `add_book` for `.pdf`
inputs. (XML/JSON and other formats still need a custom chunker — see
`references/chunking-strategies.md`.)

### EPUB/PDF via MCP (one-call)

If the MCP server is configured, `add_book()` handles EPUB/PDF → Markdown → index in one call
(it dispatches on the file extension):

```
mcp_library_rag_add_book(
    file_path="/path/to/book.epub",   # or /path/to/doc.pdf
    book_slug="my-new-book",
    author="Author Name",
    title="Book Title",
    year="2024"
)
```

### Built-in chunkers

`rag_index.py` includes two general-purpose chunkers that handle converted Markdown and plain text:

| Chunker | Input | Strategy |
|---|---|---|
| `chunk_markdown()` | `.md` files with headings | Split by `##`/`###` (a `###` chunk inherits its parent `##` as a `Section — Subsection` breadcrumb), paragraph merge fallback, single-newline normalization |
| `chunk_plain_text()` | `.txt` files | Paragraph merge with overlap |

PDFs are converted to page-structured Markdown (see above) and handled by `chunk_markdown()`.
For other domain-specific formats (XML, JSON, etc.), write a custom chunker and register it in
`discover_files()`. See `references/chunking-strategies.md` for patterns.

## Installation

### Prerequisites

- **Python 3.9+**
- **An OpenRouter API key** with credit — embeddings use the `baai/bge-m3` model
  (1024-dim) via OpenRouter's [embeddings endpoint](https://openrouter.ai/baai/bge-m3).
  Get a key at <https://openrouter.ai/keys>.
- **A Python build that allows SQLite extension loading.** `sqlite-vec` is loaded as a
  runtime extension via `conn.enable_load_extension(True)`. Most builds support this, but
  some (notably the system Python on macOS) ship SQLite with extension loading disabled.
  If you hit `sqlite3.OperationalError: ... enable_load_extension`, install Python from
  python.org or via `pyenv`/Homebrew (`brew install python`), or use `conda`.

### Steps

```bash
# 1. Clone the agent_skills repository (this skill lives in research/library-rag)
git clone https://github.com/moonlight-lupin/agent_skills.git
cd agent_skills/research/library-rag

# 2. (Recommended) create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
# On externally-managed environments (Debian/Ubuntu, recent macOS) you may need:
#   pip install -r requirements.txt --break-system-packages
```

> The `mcp` package is only required if you run the MCP server (`scripts/mcp_server.py`).
> Everything else (indexing, querying, EPUB conversion) works without it.

### Verify the install

```bash
python3 -c "import sqlite_vec, sqlite3; \
c = sqlite3.connect(':memory:'); c.enable_load_extension(True); \
sqlite_vec.load(c); print('sqlite-vec OK:', c.execute('select vec_version()').fetchone()[0])"
```

### Set up the API key

```bash
# Option A: environment variable (per shell session)
export OPENROUTER_API_KEY=sk-or-v1-...

# Option B: Hermes .env file (persistent)
echo 'OPENROUTER_API_KEY=sk-or-v1-...' >> ~/.hermes/.env
```

Both `rag_index.py` and `rag_query.py` read `OPENROUTER_API_KEY` from the environment
first, then fall back to the `.env` file pointed to by `HERMES_ENV` (default `~/.hermes/.env`).

## Quick Start

### 1. Prepare your library

Organize content under `~/.hermes/library/` and write a chunker for your source type
(see `references/chunking-strategies.md` for patterns).

### 2. Build the index

```bash
# Index all new/changed files (incremental)
python3 scripts/rag_index.py

# Full rebuild from scratch
python3 scripts/rag_index.py --rebuild

# Preview without API calls
python3 scripts/rag_index.py --dry-run
```

### 3. Query

```bash
# CLI
python3 scripts/rag_query.py "your search query"
python3 scripts/rag_query.py "search terms" --top-k 5
python3 scripts/rag_query.py "query" --source my-source-type --verbose

# Import in Python
from rag_query import search
results = search("your query", top_k=10)
```

### 4. Optional: MCP server

Register in Hermes `config.yaml`:

```yaml
mcp_servers:
  library_rag:
    command: "python3"
    args: ["~/.hermes/skills/research/library-rag/scripts/mcp_server.py"]
    timeout: 60
```

## Configuration

All paths are overridable via environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `LIBRARY_ROOT` | `~/.hermes/library` | Root directory for library content + DB |
| `HERMES_ENV` | `~/.hermes/.env` | Path to env file containing API key |
| `OPENROUTER_API_KEY` | (from .env) | OpenRouter API key for bge-m3 embeddings |

## Cost

Provider pricing changes — always check current
[OpenRouter pricing](https://openrouter.ai/baai/bge-m3). At the time of writing
(bge-m3 ≈ **$0.01 per million tokens**) the orders of magnitude are:

- A typical book (300 pages, ~100K tokens): **~$0.001**
- Per query: **~$0.0000001** (7-17 tokens per query string)

Effectively free for personal use.

## Portable Standalone RAG

The same bge-m3 → sqlite-vec pattern can be deployed as a **standalone,
self-contained RAG** inside any skill directory — no MCP registration, no
dependency on `~/.hermes/library/`. See
[`references/portable-rag-per-skill.md`](references/portable-rag-per-skill.md)
for the full pattern, including page-marker parsing, L2 normalization, chunk
overlap, and citation fidelity.

## References

- [`references/chunking-strategies.md`](references/chunking-strategies.md) — Chunking patterns, design principles, and pitfalls
- [`references/portable-rag-per-skill.md`](references/portable-rag-per-skill.md) — Standalone RAG pattern for other skills
- [`references/openrouter-embeddings.md`](references/openrouter-embeddings.md) — API endpoint details and cost breakdown
- [`references/rag-pipeline-review.md`](references/rag-pipeline-review.md) — Audit checklist for RAG pipeline quality
- [`references/epub-conversion.md`](references/epub-conversion.md) — EPUB extraction patterns and pitfalls

## Testing

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

The suite (`tests/`) runs offline — no API calls. It covers vector normalization,
the chunkers, frontmatter parsing, EPUB conversion, and a real sqlite-vec store +
search round trip (embeddings are injected directly). The repo-root CI
(`.github/workflows/test.yml`) runs this suite along with every other skill's
tests on each push and pull request.

## License

MIT — see [LICENSE](LICENSE). The software contains no copyrighted content;
users are responsible for ensuring they have rights to index any content
they process.
