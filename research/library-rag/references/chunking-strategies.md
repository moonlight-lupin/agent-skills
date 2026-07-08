# Chunking Strategies for Library RAG

Per-source-type chunking patterns used by `rag_index.py`. When adding a new book
format, model your chunker on the closest match here and register it in `discover_files()`.

## Design principles

1. **Target ~800–1000 chars per chunk** — enough for meaningful embeddings, not so much
   that the signal dilutes.
2. **Merge small chunks** — paragraphs shorter than ~200 chars should merge with the next
   paragraph, not stand alone.
3. **Preserve natural boundaries** — verse groups, paragraph breaks, section headings.
   Never split mid-sentence unless a paragraph is absurdly long.
4. **Chunk overlap (~15%)** — `split_long_text()` carries the last ~15% of each chunk
   into the next chunk's prefix, improving recall for content that straddles a boundary.
5. **Attach metadata** — every chunk carries `source_type`, `source_book`, `source_file`,
   `book`, `chapter`, `verse_range` or `section_title`, `chunk_index`, `chunk_text`.
   The `file_hash` is added by the indexer after chunking, not by the chunker.
6. **Clean for embedding** — `clean_for_embedding()` strips markdown markers (`**bold**`,
   `# headings`, `[links](url)`, `<br>`, `**[Table N]**`, `<!-- Page N -->`) before
   sending to the API. Chunk text itself retains markdown for readability.
7. **L2-normalize vectors** — `normalize_vec()` is called at store time (`float_to_blob`)
   and query time (`get_embedding`) so the cosine similarity formula is exact.

## Chunker patterns

### Paragraph merge (general-purpose)

For plain text or markdown without strong heading structure. Merge consecutive
paragraphs into ~max_chars chunks, respecting `MIN_CHUNK_CHARS`:

```python
def merge_paragraphs(paras, max_chars=MAX_CHUNK_CHARS, min_chars=MIN_CHUNK_CHARS):
    chunks = []
    current = []
    current_len = 0
    for para in paras:
        para = para.strip()
        if not para:
            continue
        if current_len + len(para) > max_chars and current:
            text = '\n\n'.join(current)
            if len(text) >= min_chars or len(current) == 1:
                chunks.append(text)
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para) + 2
    if current:
        text = '\n\n'.join(current)
        if len(text) >= 10:
            chunks.append(text)
    return chunks
```

### Heading-based (structured books)

For markdown with `##` and `###` section headings. Split by headings, keep tables
attached to their section, fall back to paragraph merge when no headings found.

**Critical pitfall:** Some books use **single newlines for line wrapping**, not
paragraph breaks. The chunker MUST normalize single newlines to spaces before
splitting by double-newline paragraph breaks:
```python
normalized = re.sub(r'(?<!\n)\n(?!\n)', ' ', text_content)  # single NL → space
```
Without this, the entire chapter becomes one giant chunk because there are only
2-3 real `\n\n` breaks in a 170K-char file.

### Page-aware (PDF-extracted content)

For markdown extracted from PDFs with `<!-- Page N -->` markers. Parse markers
to stamp each chunk with its page number. See `references/portable-rag-per-skill.md`
for the full pattern.

## Adding a new source type

1. Write a `chunk_<type>(file_path)` function that returns a list of chunk dicts.
2. Each chunk dict needs: `source_type`, `source_book`, `source_file`, `book`, `chapter`,
   `verse_range` or `section_title`, `chunk_index`, `chunk_text`.
   Do NOT include `file_hash` — the indexer adds it.
3. Register the file discovery in `discover_files()` — add a glob pattern and map it
   to your chunker.
4. Test with `--dry-run --source <type>` to verify chunk counts are reasonable
   (not 1 per file, not 1000 per file).
5. Run the indexer incrementally — only new files get embedded.

## Common pitfalls

- **sqlite-vec extension must be loaded BEFORE any vec0 DDL**: `init_db()` loads the
  extension first, then drops/creates tables. Reversing this order causes
  `sqlite3.OperationalError: no such module: vec0`.
- **`file_hash` missing from chunks**: The indexer adds `file_hash` to each chunk dict
  after chunking but before calling `store_batch()`. If you call `store_batch()` directly
  (e.g. from the MCP `add_book` tool), ensure `file_hash` is set.
- **Single-newline wrapping**: Some text sources use single `\n` for line wrapping, not
  paragraph breaks. Normalize to spaces before splitting on `\n\n`.
- **OpenRouter batch limits**: Batch size of 32 works reliably. Larger batches may
  timeout on slow connections.
- **Page citations lost without marker parsing**: PDF extractors insert `<!-- Page N -->`
  comments at page boundaries, but if the chunker doesn't parse them, all chunks degrade
  to chapter-level citations. Use `split_by_pages()` to split text by markers and stamp
  each chunk with its page. See `references/portable-rag-per-skill.md` for the pattern.
- **Similarity formula assumes unit-normalized vectors**: `1 - distance²/2` is only
  exact cosine similarity if both stored and query vectors are L2-normalized. bge-m3
  returns unit-norm vectors, but normalize explicitly at store and query time to guard
  against model/API changes. See `normalize_vec()` in both `rag_index.py` and
  `rag_query.py`.
- **`clean_for_embedding` must strip PDF/table artifacts**: In addition to markdown
  markers, strip `<br>` (table cell breaks), `**[Table N]**` (table markers), and
  `<!-- Page N -->` (page markers) from the text sent to the embedding API. These
  are noise that degrade vector quality. Chunk text in the DB retains them for display.
- **`MIN_CHUNK_CHARS` defined but unused**: If a min threshold is defined, wire it in
  via a `merge_tiny_chunks()` post-processing step. Without it, near-empty chunks
  dilute search results.
