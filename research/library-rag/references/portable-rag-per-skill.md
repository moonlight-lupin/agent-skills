---
name: portable-rag-per-skill
description: "Pattern for standalone RAG indexes that live inside a skill directory — portable, no external DB or MCP dependency."
version: 1.0.0
---

# Portable RAG: Per-Skill Standalone Index

The default library-rag setup uses a shared DB at `~/.hermes/library/rag_index.db`
with an MCP server registered in config.yaml. This is good for a permanent library
but creates two problems for skills that should be self-contained:

1. **Not portable** — moving the skill to another machine breaks the DB path
2. **MCP dependency** — requires config.yaml registration, not self-contained

## The Portable Pattern

Instead of the shared DB + MCP approach, create a standalone RAG index inside
the skill's own `references/` directory:

### Key Differences from Library RAG

| Aspect | Library RAG | Portable RAG |
|---|---|---|
| DB location | `~/.hermes/library/rag_index.db` | `<skill>/references/rag_index.db` |
| Path resolution | Hardcoded `LIBRARY_ROOT` | `Path(__file__).resolve().parent.parent` |
| DB override | None | `--db` flag or env var |
| API key | `.env` only | `OPENROUTER_API_KEY` env var OR `.env` |
| MCP server | Yes (config.yaml dependency) | No — import `rag_query.search()` directly |
| Chunker | Source-specific | Domain-specific (headings, sections, etc.) |
| Portable | No | Yes — zip the folder, drop on another machine, done |

### Implementation: Path Resolution

```python
# All paths resolve from the script's own location — no hardcoded paths
SKILL_DIR = Path(__file__).resolve().parent.parent
REFERENCES_DIR = Path(os.environ.get('SKILL_REFERENCES_DIR', SKILL_DIR / 'references'))
DB_PATH = Path(os.environ.get('SKILL_RAG_DB', REFERENCES_DIR / 'rag_index.db'))
ENV_PATH = os.environ.get('HERMES_ENV', os.path.expanduser('~/.hermes/.env'))
```

### Implementation: API Key Loading

```python
def load_api_key():
    # Try env var first (most portable), then fall back to .env
    key = os.environ.get('OPENROUTER_API_KEY')
    if key:
        return key
    env_path = Path(ENV_PATH)
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if 'OPENROUTER' in line.upper() and 'API_KEY' in line.upper() and not line.startswith('#'):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
    raise ValueError(f"No OPENROUTER_API_KEY found in env or {ENV_PATH}")
```

### Implementation: Query Without MCP

Instead of registering an MCP server, scripts import directly:

```python
# In the skill's GM/game script:
import sys; sys.path.insert(0, "scripts")
from rag_query import search

results = search("autofire range penalty", top_k=3)
for r in results:
    print(f"[{r['similarity']:.0%}] {r['chapter']} — {r['section_title']}")
```

### Chunker Design for Rulebooks/Structured Docs

Unlike verse-based chunking, rulebook/general document chunking needs:
- **Split by headings** (`##`, `###`) — each section is self-contained
- **Keep tables attached to their heading** — a damage table without "Heavy Weapons" context is useless
- **Fallback to paragraph merging** when no headings found (fiction, prose sections)
- **Parse `<!-- Page N -->` markers for page citations** — the extractor inserts these
  at each page boundary; the chunker must split on them and stamp each chunk with its
  page number. This is the single most important metadata fix — without it, citations
  degrade to chapter-level only.
- **Extract section titles heuristically** — PDF extraction doesn't produce markdown
  headings, so the chunker uses a best-effort heuristic: first short non-punctuation
  line that isn't a chapter running header, author byline, or extraction artifact
  (doubled characters like "AARRBBIITTEERR").
- **Chunk overlap (~15%)** — `split_long_text()` carries the last ~15% of each chunk
  as a prefix into the next, improving recall for rules that straddle a boundary.
- **Merge tiny chunks** — `merge_tiny_chunks()` merges any chunk < `MIN_CHUNK_CHARS`
  with the previous chunk, preventing near-empty chunks from diluting search results.
- **Larger chunks** (1000-1200 chars vs 800 for verse-based) — document paragraphs are denser

### Page Marker Parsing Pattern

The extractor (`extract_rulebook.py`) inserts `<!-- Page N -->` HTML comments at each
page boundary. The chunker parses these to provide per-chunk page citations:

```python
PAGE_MARKER_RE = re.compile(r'<!--\s*Page\s+(\d+)\s*-->\s*\n*')

def split_by_pages(text):
    """Split text by page markers → [(page_num, segment_text), ...]."""
    markers = list(PAGE_MARKER_RE.finditer(text))
    if not markers:
        return [(None, text)]
    segments = []
    if markers[0].start() > 0:
        pre = text[:markers[0].start()].strip()
        if pre:
            segments.append((None, pre))
    for i, m in enumerate(markers):
        page = int(m.group(1))
        start = m.end()
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        seg = text[start:end].strip()
        if seg:
            segments.append((page, seg))
    return segments
```

In the heading-based chunker (`chunk_rulebook_md`), page markers are parsed within
each section's text — the last marker becomes the chunk's page number, and markers
are stripped from the stored text.

### Section Title Heuristic

PDF extractors don't produce markdown headings, so section titles must be inferred
from the text. The `extract_section_title()` function picks the first short
non-punctuation line, filtering out common PDF extraction noise:

```python
def extract_section_title(text, chapter=None):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:5]:
        if line.startswith('<!--') or line.startswith('**[Table'):
            continue
        # Skip doubled-char artifacts (e.g. "AARRBBIITTEERR" → "ARBITER")
        pairs = [(line[i], line[i + 1]) for i in range(0, len(line) - 1, 2)]
        if pairs and sum(1 for a, b in pairs if a == b) > len(pairs) * 0.5:
            continue
        if line.upper().startswith('BY '):       # author byline
            continue
        if chapter:                               # chapter running header
            ch_title = chapter.split(': ', 1)[-1] if ': ' in chapter else chapter
            if line.upper() == ch_title.upper():
                continue
        if 3 < len(line) < 60 and not line.endswith(('.', ',', ';', ':', '!')):
            return line
    return None
```

Key PDF artifact: stylized rulebook layouts produce **doubled characters** in
`extract_text()` (e.g., "AARRBBIITTEERR" instead of "ARBITER"). The doubled-char
detection (checking if >50% of character pairs match) filters these out. In the
Cyberpunk Red rulebook, this heuristic achieves 86% section title coverage.

### Merging Tiny Chunks

After chunking, chunks below `MIN_CHUNK_CHARS` should merge with the previous
chunk to avoid near-empty chunks diluting search results:

```python
def merge_tiny_chunks(chunks, min_chars=MIN_CHUNK_CHARS):
    if min_chars <= 0 or len(chunks) <= 1:
        return chunks
    merged = []
    for chunk in chunks:
        if merged and len(chunk['chunk_text']) < min_chars:
            prev = merged[-1]
            prev['chunk_text'] += '\n\n' + chunk['chunk_text']
        else:
            merged.append(chunk)
    for i, c in enumerate(merged):
        c['chunk_index'] = i
    return merged
```

### Post-Reindex Verification

After re-indexing with page citations, verify with queries that have known page
answers. This catches silent metadata loss:

```bash
# Should return p.174 for the autofire DV table
python3 rag_query.py "autofire range penalty" --top-k 3

# Should return p.223 or p.189 for death save rules
python3 rag_query.py "death save" --top-k 3
```

Also verify at the DB level:
```python
# Page citation coverage (should be ~100% for PDF-extracted content)
conn.execute('SELECT COUNT(*) FROM chunks WHERE page IS NOT NULL').fetchone()
# Markers leaking into text (should be 0)
conn.execute("SELECT COUNT(*) FROM chunks WHERE chunk_text LIKE '%<!-- Page%'").fetchone()
# Vector normalization (should be ~1.0)
struct.unpack(f'{dim}f', blob) → math.sqrt(sum(x*x)) ≈ 1.0
```

### L2 Normalization (Store + Query)

bge-m3 vectors from OpenRouter are already unit-normalized (verified: L2 norm = 1.0).
But to make the similarity formula exact and robust against model/API changes,
normalize explicitly at both store and query time:

```python
def normalize_vec(vec):
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else vec

# In indexer: normalize before storing
def float_to_blob(emb):
    emb = normalize_vec(emb)
    return struct.pack(f'{len(emb)}f', *emb)

# In query: normalize the query embedding
def get_embedding(text, api_key):
    ...
    return normalize_vec(resp.json()['data'][0]['embedding'])
```

With both sides guaranteed unit-norm, `similarity = 1 - distance²/2` is the exact
cosine similarity (not an implicit assumption).

### clean_for_embedding Artifacts

The cleaning function strips markdown markers before sending text to the embedding
API. In addition to bold/italic/headings/links, it must also strip:
- `<br>` → space (from table cell line breaks in PDF extraction)
- `**[Table N]**` → remove (table annotation markers)
- `<!-- Page N -->` → remove (page markers — should never reach the embedding)

Chunk text in the DB retains these for display readability; only the embedding input
is cleaned.

### sqlite-vec Filtering Limitation

sqlite-vec's `MATCH` / `k` vector search **cannot be combined with arbitrary `WHERE` clauses**. This means `source_type` and `source_book` filters must be applied as post-filters after the vector search, not in the SQL query itself.

**Wrong** (filter is silently ignored — returns unfiltered results):
```python
# This does NOT filter by source_type — sqlite-vec ignores it
results = conn.execute('''
    SELECT rowid, distance FROM vec_chunks
    WHERE embedding MATCH ? AND k = ? AND source_type = ?
''', (query_blob, top_k, source_type)).fetchall()
```

**Correct** (over-fetch, then post-filter on chunk metadata):
```python
search_k = top_k * 5 if (source_type or source_book) else top_k
raw_results = conn.execute('''
    SELECT rowid, distance FROM vec_chunks
    WHERE embedding MATCH ? AND k = ?
    ORDER BY distance
''', (query_blob, search_k)).fetchall()

results = []
for rowid, distance in raw_results:
    row = conn.execute('SELECT source_type, source_book, ... FROM chunks WHERE id = ?', (rowid,)).fetchone()
    if source_type and row[0] != source_type:
        continue
    if source_book and row[1] != source_book:
        continue
    results.append(...)
    if len(results) >= top_k:
        break
```

This was a real bug in the cyberpunk-red-gm RAG — `--source core-rules` was silently a no-op, returning results from all source types. Discovered during PR review.

### .gitignore for Copyrighted Content

When publishing the skill to GitHub, the RAG DB and extracted markdown are
derived from copyrighted source material. Exclude them:

```gitignore
references/raw/           # Original PDFs
references/rag_index.db   # Generated DB
references/ch*.md         # Extracted chapters
references/errata/*.md    # Extracted errata
references/supplements/*.md  # Extracted supplements
```

Users clone the repo, purchase their own PDFs, and run the extraction + indexing
scripts locally.

## Real-World Example

The `cyberpunk-red-gm` skill uses this pattern:
- 458-page RPG rulebook extracted to 18 chapter markdown files
- 2,306 chunks embedded with bge-m3 → standalone sqlite-vec DB (15.6 MB)
- 100% of chunks have page citations (via `<!-- Page N -->` marker parsing)
- 86% have best-effort section titles (heuristic extraction from PDF text)
- Cost: $0.006 for full index, ~$0.0000003 per query
- Vectors L2-normalized at store time; cosine similarity formula exact
- Fully portable — no dependency on the main library RAG or config.yaml
