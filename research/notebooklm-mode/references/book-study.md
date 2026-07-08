# Book Study Mode

Study a **primary text** alongside one or more **reference texts** (commentaries,
study guides, criticism, teacher's manuals) using the notebooklm-mode vault
infrastructure with structured reference parsing.

## When to use

- "Study Chapter 12 of Grudem with the study guide"
- "Study John 3:16 with Calvin's commentary" (Bible — needs alias file)
- "What does the criticism say about Chapter 5 of Moby Dick?"
- "Study the theme of predestination across the primary text and commentary"
- Daily reading plan with companion commentary + bilingual text

## Vault setup

A book-study vault is a regular notebooklm-mode vault with **tagged sources**:

```
<vault_path>/
├── vault_index.md
├── sources/
│   ├── 001_primary.md              # source_role: primary
│   ├── 002_primary-alt.md          # source_role: primary (translation/edition)
│   └── 003_reference.md             # source_role: reference
├── rag_index.db
└── outputs/
    └── study_YYYY-MM-DD.md
```

### Source file format (extends notebooklm-mode)

Add a `source_role` field to the source file metadata table:

```markdown
# Source Title

| Field | Value |
|-------|-------|
| URL | ... |
| Type | book / bible / commentary / criticism |
| Source Role | primary / reference |
| Retrieved | YYYY-MM-DD |
```

The agent uses `source_role` to distinguish "the text under study" from
"the commentary on it." This is a convention — notebooklm-mode's RAG treats
all sources the same; the role only affects how the agent presents results.

### Using library-rag if books are already indexed

If the primary and reference texts are already in `~/.hermes/library/` (indexed
by library-rag), skip re-indexing into the vault. Instead:
1. Use `parse_reference.py` to resolve the exact passage from the markdown file
2. Use `mcp_library_rag_search` to find semantically related passages in the
   reference text, filtered by `source_type`
3. Compose the study output from the exact passage + semantic search results

This is the fast path — no vault setup or re-indexing needed.

### Per-session standalone RAG (for new book pairs)

If the texts are NOT in library-rag:
1. Create a vault per the notebooklm-mode workflow
2. Convert the primary and reference texts to markdown (EPUB/PDF via library-rag
   converters, or use existing markdown)
3. Add sources with `ingest_source.py`, tagging each as primary or reference
4. Use `search_vault()` for semantic search across both

## Two modes

### Passage-first mode

User provides a specific passage reference (e.g. "Ch 12", "John 3:16",
"§3.2"):

1. **Resolve the passage** — use `parse_reference.py` to extract the exact text
   from the primary source markdown:
   ```bash
   python3 scripts/parse_reference.py "Ch 12" --source /path/to/book.md
   python3 scripts/parse_reference.py "John 3:16" --source /path/to/bible.md
   ```
2. **Find commentary** — semantic search the reference text(s) for passages
   related to the primary passage:
   - If in library-rag: `mcp_library_rag_search(query="<key phrases from passage>",
     source_type="<reference-source-type>")`
   - If in vault: `search_vault(vault_path, "<key phrases from passage>")`
3. **Compose study session** — see output format below

### Topic-first mode

User provides a topic or question (e.g. "what does the commentary say about
predestination?", "study the theme of faith in Chapter 8"):

1. **Search both corpora** — semantic search primary + reference for the topic:
   - Primary: `mcp_library_rag_search(query="<topic>",
     source_type="<primary-source-type>")` for relevant passages
   - Reference: `mcp_library_rag_search(query="<topic>",
     source_type="<reference-source-type>")` for commentary
2. **Pair results** — match primary passages with their commentary
   (by chapter/section overlap or semantic similarity)
3. **Compose study session** — see output format below

## Study session output format

```markdown
<!-- Study: {reference} | Date: YYYY-MM-DD | Primary: {primary} | Reference: {reference} -->

# Study: {Reference}

**Date:** YYYY-MM-DD
**Primary text:** {primary_source_name}
**Reference:** {reference_source_name}

## Primary Text

### {Chapter/Section/Verse reference}

{Exact passage text from parse_reference.py}

{If multiple editions/translations, present the second here}

## Commentary

**{Commentator/critic name} on {reference}:**

{Relevant commentary passages, with references if available. Quote verbatim
from the reference text. Cite the source file.}

## Insight

{Synthesize the primary text and commentary into 2-3 key observations:
- What is the main theme or argument?
- What does the commentary highlight that isn't obvious from the text alone?
- How do the primary text and commentary interact?}

## Application / Reflection

{1-2 paragraphs of personal reflection:
- How does this passage speak to current situations?
- What action or attitude change does it call for?
- Keep this grounded in the text, not generic commentary.}
```

> **Note:** The `Application / Reflection` section is optional and adapts to
> the book type — a Bible study might replace it with (or add) a short prayer,
> while a literary-criticism study may end with reflection questions. Omit or
> adapt sections that don't fit the text.

## Multi-edition study

For studying a text with two editions/translations (e.g. NIV + CUV Bible,
or an original-language text + translation):
1. Resolve the passage from both editions using `parse_reference.py`
2. Present both side by side in the Primary Text section
3. Commentary is typically in one language only
4. Reflection can be in either language per user preference

## Cron / recurring study

For a daily study habit (e.g. a reading plan through a book):
1. Create a cron job that runs the study workflow on a schedule
2. The cron prompt includes the reading plan (which passage for which day)
3. Output is saved to a studies directory
4. Use `context_from` to pass the previous day's study for continuity

Example cron prompt (generic):
```
You are a book study assistant. Today's passage is {passage_ref}.
Study this passage using {reference_name}.

## Steps
1. Use parse_reference.py to get the exact text from the primary source: {passage_ref}
2. If multi-edition, resolve from the second source as well
3. Search library-rag for {reference_name} commentary on this passage
4. Compose the study session per references/book-study.md output format
5. Save to {output_dir}/Day-{N}_{slug}_{user}.md

Primary: {primary_path}
Reference: {reference_name} (search library-rag source_type={reference_type})
```

## Pitfalls

- **parse_reference.py needs the exact markdown path** — know where your
  source files live. For single-file books (e.g. a whole Bible in one .md),
  pass that file. For per-chapter files (library-rag's usual structure),
  pass the specific chapter file.
- **Book name aliases are optional** — place an alias JSON next to
  `parse_reference.py` (or pass `--aliases path.json`) to map short names to
  canonical headings (e.g. "Psalm" → "Psalms", "Rom" → "Romans"). Without
  an alias file, only title-casing is applied. Create your own for non-Bible
  books, or omit it entirely.
- **Commentary may not cover every passage** — if semantic search returns
  nothing relevant, say so — don't fabricate commentary.
- **Reference structure varies** — commentaries use inline prose references,
  not structured verse markers. Semantic search is the only reliable way to
  find relevant commentary passages.
- **Multi-edition alignment** — translations may have different chapter/verse
  or section numbering. If passages don't align perfectly, note the discrepancy.
- **Large files** — `parse_reference.py` reads the full file each call. For
  a cron doing one passage/day this is fine. For batch processing, cache the
  file content.