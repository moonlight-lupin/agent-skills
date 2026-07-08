# RAG Pipeline Review Checklist

A systematic audit checklist for any bge-m3 + sqlite-vec RAG pipeline.
Use when reviewing a new pipeline or debugging poor retrieval quality.
Distilled from a real audit of the cyberpunk-red-gm portable RAG.

## How to use

Run through each section in order. The issues are ranked by impact:
citation survival > embedding noise > chunk quality > similarity math > endpoint.

## 1. Citation Survival (🔴 Highest Impact)

The most common high-impact bug: metadata captured during extraction
is silently lost before query time.

- [ ] **Do extracted .md files have heading structure?**
  PDF extractors that only do `clean_text()` + appended tables produce
  NO `##`/`###` headings. A heading-based chunker will fall back to
  plain chunking, losing all section-level metadata.

- [ ] **Are `<!-- Page N -->` markers parsed into the `page` column?**
  Extractors insert page markers, but if the chunker doesn't parse them
  (via `split_by_pages()` or equivalent), every chunk gets `page: NULL`.
  Check: `SELECT COUNT(*) FROM chunks WHERE page IS NOT NULL` — should
  be ~100% for PDF-extracted content.

- [ ] **Are page markers stripped from stored `chunk_text`?**
  Markers are metadata, not content. If they survive into chunk_text,
  they pollute the embedding and display. Check:
  `SELECT COUNT(*) FROM chunks WHERE chunk_text LIKE '%<!-- Page%'`
  — should be 0.

- [ ] **Does `format_result` print citations that are actually populated?**
  If the query script prints `p.{page}` and `{section_title}` but those
  columns are always NULL, the citation display is misleading. Verify
  with real queries that return non-NULL page/section values.

- [ ] **Do marker-less chunks carry forward the nearest anchor?**
  A page/section-aware chunker stamps an anchor only on the chunk that
  *starts* at a marker. Chunks that continue a page, sit between markers,
  or are split fragments get NULL — and in practice that "mid-body" bucket
  is often the largest. Thread the last-seen anchor through the chunker and
  let a marker-less chunk inherit the nearest *preceding* page/section
  (front matter before the first marker stays unanchored, which is correct):

  ```python
  last_page, last_section = None, None
  for chunk in chunks_in_document_order:
      if chunk.page is not None:
          last_page = chunk.page
      elif last_page is not None:
          chunk.page = last_page          # continues the last page seen
      # (same for section_title; for nested headings, carry the parent ##
      #  forward so a ### chunk reads "Section — Subsection")
  ```

  Consider a `page_exact: bool` (anchor started here vs. carried) so a
  reviewer knows a carried page is the nearest preceding, not a fresh marker.
  In one BM25 audit this single change took paragraph-citation coverage
  from 61% → 85%.

- [ ] **Is the marker pattern validated per source family — with a
  false-positive audit?**
  One regex tuned on one book/publisher silently under-detects others
  (`7.` / `A17.` vs multi-level `5.5.14` vs a bare `1 In some countries…`).
  Worse, loosening the rule to catch a new style can mint *bogus* anchors —
  e.g. `"1 January 2026"` matching a paragraph-number shape. A wrong anchor
  is worse than a missing one. Before trusting a new rule, list everything
  it *newly* matches and eyeball it:

  ```python
  for line in corpus_lines:
      new = marker_new(line)
      if new and not marker_old(line):
          print(repr(new), "<-", line[:72])   # real anchors, or dates/prose?
  ```

  Add exclusions (e.g. month names) until every new match is a genuine
  anchor. In that same audit this took coverage 85% → 96% with zero false
  anchors. (In this repo, `convert_epub_library.audit_chapter_markers()`
  is the equivalent eyeball check for chapter detection.)

## 2. Table Handling (🟠 High Impact)

- [ ] **Is table text duplicated?**
  pdfplumber's `extract_text()` includes text inside table regions.
  If `extract_page()` also appends `extract_tables()` output, the same
  data appears twice — inflating chunk size and embedding noise.
  Check: sample chunks with markdown table syntax (`|---|`) and look
  for cell content also appearing in prose lines.

- [ ] **Are tables kept as atomic chunks?**
  Damage tables, DV tables, and other reference tables should not be
  split across chunks. The chunker should detect `|` patterns and keep
  small tables intact within their section heading.

## 3. Embedding Quality (🟡 Medium Impact)

- [ ] **Does `clean_for_embedding` strip all artifacts?**
  Must strip: `**bold**`, `*italic*`, `# headings`, `[links](url)`,
  `<br>` (table cell breaks), `**[Table N]**` (table markers),
  `<!-- Page N -->` (page markers). Check the regex list covers all
  artifact types present in your extracted text.

- [ ] **Is there chunk overlap?**
  `split_long_text()` should carry ~15% of each chunk's tail into the
  next chunk's prefix. Without overlap, rules that straddle a boundary
  lose recall. Check: `OVERLAP_RATIO` defined and used in the split
  function.

- [ ] **Is `MIN_CHUNK_CHARS` actually wired in?**
  A common pattern: define `MIN_CHUNK_CHARS` but never use it. Check
  that `merge_tiny_chunks()` (or equivalent) is called after chunking.
  Verify: `SELECT MIN(LENGTH(chunk_text)) FROM chunks` — should be
  >= MIN_CHUNK_CHARS.

## 4. Similarity Math (🟡 Medium Impact)

- [ ] **Are vectors L2-normalized at store time?**
  `float_to_blob()` should call `normalize_vec()` before packing.
  Verify: unpack a stored vector and check `math.sqrt(sum(x*x)) ≈ 1.0`.

- [ ] **Are query vectors L2-normalized?**
  `get_embedding()` should call `normalize_vec()` on the API response.
  Without this, the similarity formula is only correct if the API
  returns unit-norm vectors (bge-m3 does, but don't rely on it).

- [ ] **Is the similarity formula correct for the metric?**
  `sim = 1 - dist²/2` is exact cosine similarity ONLY for unit-normalized
  vectors with L2 distance. If using a different metric or non-normalized
  vectors, use explicit cosine: `dot(a,b) / (|a| * |b|)`.

## 5. Endpoint Verification (⏳ Confirm)

- [ ] **Is the embedding API endpoint actually available?**
  OpenRouter's `/v1/embeddings` endpoint serves `baai/bge-m3` but
  coverage is narrower than chat/completions. Test with a single
  embedding request before committing to a full index build.

- [ ] **Does the endpoint return normalized vectors?**
  Check `math.sqrt(sum(x*x for x in embedding))` — should be ~1.0.
  If not, L2-normalize at store+query time (you should do this anyway
  for robustness).

- [ ] **Is there a fallback if the endpoint is down?**
  Consider documenting a local `sentence-transformers` path:
  ```python
  from sentence_transformers import SentenceTransformer
  model = SentenceTransformer('BAAI/bge-m3')
  embeddings = model.encode(texts, normalize_embeddings=True)
  ```
  Heavier install (torch), but no API dependency.

## 6. Post-Reindex Verification

After any re-index, verify with known-answer queries:

```bash
# Pick queries with known page citations
python3 rag_query.py "autofire range penalty" --top-k 3  # expect p.174
python3 rag_query.py "death save" --top-k 3              # expect p.223
```

DB-level checks:
```sql
-- Page citation coverage
SELECT COUNT(*) FROM chunks WHERE page IS NOT NULL;
-- Markers leaking into text
SELECT COUNT(*) FROM chunks WHERE chunk_text LIKE '%<!-- Page%';
-- Tiny chunks
SELECT COUNT(*) FROM chunks WHERE LENGTH(chunk_text) < 100;
```

Vector normalization check:
```python
import struct, math
blob = conn.execute('SELECT embedding FROM vec_chunks LIMIT 1').fetchone()[0]
vec = struct.unpack(f'{len(blob)//4}f', blob)
assert abs(math.sqrt(sum(x*x for x in vec)) - 1.0) < 0.001
```

### Re-index operational pitfalls

- **Don't run two `--rebuild` jobs on the same DB**: A foreground test
  (`--rebuild`) and a background `--rebuild` overlapping on the same SQLite
  DB produces spurious "Failed after 3 retries" errors — the background job
  fails to write batches because the foreground job already dropped/recreated
  the tables. Use `--dry-run` for quick tests (it never touches the DB).
  If you see mass "Failed after 3 retries" in the log, check whether all
  chunks are actually present in the DB — the errors may be spurious.
- **Verify chunk count matches vector count after re-index**:
  `SELECT COUNT(*) FROM chunks` should equal `SELECT COUNT(*) FROM vec_chunks`.
  A mismatch means some chunks were stored without vectors (or vice versa).
- **Expect ~50-90 min for a full library rebuild**: Small files finish fast, large text collections dominate the time. Cost: ~$0.01-$0.12 depending on corpus size. No rate limiting observed on OpenRouter `/v1/embeddings` with 0.3s delay between batches of 32.

## Audit severity key

| Symbol | Meaning | Action |
|---|---|---|
| 🔴 | High impact | Fix before relying on citations |
| 🟠 | High impact | Fix when possible; affects embedding quality |
| 🟡 | Medium impact | Fix for quality; not blocking |
| ⏳ | Confirm | Verify the assumption holds; document fallback |
