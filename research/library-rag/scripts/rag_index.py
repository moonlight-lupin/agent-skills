#!/usr/bin/env python3
"""
RAG Indexer — general-purpose semantic search indexer.

Embeds text documents using bge-m3 via OpenRouter.
Stores vectors in sqlite-vec for cosine similarity search.

Supports any markdown or plain text files organized under a library root.
Write your own chunker or use the built-in heading-based + paragraph-merge chunkers.

Usage:
  python3 rag_index.py                    # index all new/changed files
  python3 rag_index.py --rebuild          # drop everything, re-index from scratch
  python3 rag_index.py --dry-run          # show what would be indexed, no API calls
  python3 rag_index.py --source my-type   # index only specific source type

To add custom chunkers, see references/chunking-strategies.md.
"""

import os, sys, re, hashlib, time, sqlite3, argparse
from pathlib import Path
from datetime import datetime, timezone

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_common import (
    EMBEDDING_MODEL, EMBEDDING_DIMS,
    load_api_key, get_embeddings, float_to_blob, connect_db,
)

# ─── Config ───────────────────────────────────────────────────────────────────
LIBRARY_ROOT = Path(os.environ.get('LIBRARY_ROOT', os.path.expanduser('~/.hermes/library')))
DB_PATH = LIBRARY_ROOT / 'rag_index.db'
BATCH_SIZE = 32          # chunks per API call
MAX_CHUNK_CHARS = 1000   # target max chunk size
MIN_CHUNK_CHARS = 200    # merge smaller chunks with next
OVERLAP_RATIO = 0.15    # 15% overlap between adjacent chunks for better recall


# ─── DB ───────────────────────────────────────────────────────────────────────

def init_db(conn, rebuild=False):
    """Initialize the sqlite-vec database."""
    import sqlite_vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    if rebuild:
        conn.execute("DROP TABLE IF EXISTS chunks")
        conn.execute("DROP TABLE IF EXISTS indexed_files")
        conn.execute("DROP TABLE IF EXISTS vec_chunks")

    conn.executescript('''
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_book TEXT,
            source_file TEXT NOT NULL,
            book TEXT,
            chapter TEXT,
            section_title TEXT,
            chunk_index INTEGER,
            chunk_text TEXT NOT NULL,
            file_hash TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS indexed_files (
            file_path TEXT PRIMARY KEY,
            file_hash TEXT NOT NULL,
            chunk_count INTEGER NOT NULL,
            indexed_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source_type);
        CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(source_file);
    ''')

    conn.execute(f'CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{EMBEDDING_DIMS}])')
    conn.commit()


def store_batch(conn, chunks, embeddings):
    """Store a batch of chunks + embeddings in the DB. Returns the new chunk ids."""
    ids = []
    for chunk, emb in zip(chunks, embeddings):
        cur = conn.execute('''
            INSERT INTO chunks (source_type, source_book, source_file, book, chapter,
                               section_title, chunk_index, chunk_text, file_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            chunk['source_type'], chunk.get('source_book'), chunk['source_file'],
            chunk.get('book'), chunk.get('chapter'), chunk.get('section_title'),
            chunk.get('chunk_index'), chunk['chunk_text'], chunk['file_hash']
        ))
        rowid = cur.lastrowid
        ids.append(rowid)
        conn.execute('INSERT INTO vec_chunks (rowid, embedding) VALUES (?, ?)',
                     (rowid, float_to_blob(emb)))
    conn.commit()
    return ids


def _delete_chunk_ids(conn, ids):
    """Delete specific chunk rows (and their vectors) by id."""
    for rowid in ids:
        conn.execute('DELETE FROM vec_chunks WHERE rowid = ?', (rowid,))
        conn.execute('DELETE FROM chunks WHERE id = ?', (rowid,))


def remove_file_chunks(conn, source_file):
    """Remove all chunks + vectors for a file (for re-indexing)."""
    rows = conn.execute('SELECT id FROM chunks WHERE source_file = ?', (source_file,)).fetchall()
    for (rowid,) in rows:
        conn.execute('DELETE FROM vec_chunks WHERE rowid = ?', (rowid,))
    conn.execute('DELETE FROM chunks WHERE source_file = ?', (source_file,))
    conn.execute('DELETE FROM indexed_files WHERE file_path = ?', (source_file,))
    conn.commit()
    return len(rows)


def index_file(conn, file_path, source_type, chunker, api_key):
    """Index a single file atomically, preserving the previous version on failure.

    Blue/green: the new version is embedded and stored *alongside* the file's
    existing chunks; the old chunks are retired only after every batch succeeds.
    So a re-index never accumulates stale duplicates, and if embedding fails the
    previous version stays searchable (only the partial new rows are rolled back)
    and the file is left unrecorded so the next run retries it.

    (There is a brief window during a successful re-index where both versions are
    present; don't run two indexers against the same DB at once — see SKILL.md.)

    Returns ``(chunks_stored, usage)`` where usage is ``{'prompt_tokens', 'cost'}``.
    """
    fhash = file_hash(file_path)

    chunks = chunker(file_path, source_type=source_type)
    for c in chunks:
        c['file_hash'] = fhash

    # Snapshot the existing (old) chunk ids before inserting the new version.
    old_ids = [r[0] for r in conn.execute(
        'SELECT id FROM chunks WHERE source_file = ?', (file_path,)).fetchall()]

    if not chunks:
        # File has no indexable content now — retire the old version, record nothing.
        _delete_chunk_ids(conn, old_ids)
        conn.execute('DELETE FROM indexed_files WHERE file_path = ?', (file_path,))
        conn.commit()
        return 0, {'prompt_tokens': 0, 'cost': 0.0}

    new_ids = []
    stored = 0
    tokens = 0
    cost = 0.0
    try:
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            embed_texts = [clean_for_embedding(c['chunk_text']) for c in batch]
            embeddings, usage = get_embeddings(embed_texts, api_key)
            new_ids += store_batch(conn, batch, embeddings)
            stored += len(batch)
            tokens += usage.get('prompt_tokens', 0)
            cost += usage.get('cost', 0)
            time.sleep(0.3)
    except Exception:
        # Roll back ONLY the partial new chunks; the previous version stays intact.
        _delete_chunk_ids(conn, new_ids)
        conn.commit()
        raise

    # New version fully stored — now retire the old version and record the file.
    _delete_chunk_ids(conn, old_ids)
    conn.execute('''
        INSERT OR REPLACE INTO indexed_files (file_path, file_hash, chunk_count, indexed_at)
        VALUES (?, ?, ?, ?)
    ''', (file_path, fhash, stored, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    return stored, {'prompt_tokens': tokens, 'cost': cost}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(8192), b''):
            h.update(block)
    return h.hexdigest()


def clean_for_embedding(text):
    """Light cleanup: strip markdown markers but keep text content.

    Structured table blocks (a `**[Table N]**` line followed by rows ending in
    `<br>`, as produced by the PDF converter) are display-only and removed here —
    the page's narrative text already carries the table content linearly, so it
    stays searchable without being embedded twice.
    """
    text = re.sub(r'\*\*\[Table\s+\d+\]\*\*', '', text)   # table markers (before bold strip)
    text = re.sub(r'(?m)^.*<br>[ \t]*$', '', text)        # structured table rows (display-only)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)       # italic
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)  # headings
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)    # links
    text = re.sub(r'<br\s*/?>', ' ', text)           # any leftover inline <br>
    text = re.sub(r'<!--\s*Page\s+\d+\s*-->', '', text)   # page markers
    return text.strip()


def parse_frontmatter(text):
    """Parse YAML frontmatter from markdown. Returns (metadata_dict, body_text).

    Uses a real YAML parser so quoted values, colons in values, etc. are handled
    correctly. Scalar values are coerced to str so downstream citation joins (which
    assume strings) keep working; lists/dicts are passed through untouched.
    """
    if text.startswith('---'):
        end = text.find('\n---', 3)
        if end != -1:
            fm = text[3:end]
            body = text[end + 4:].strip()
            try:
                meta = yaml.safe_load(fm)
            except yaml.YAMLError:
                meta = None
            if not isinstance(meta, dict):
                return {}, body
            meta = {
                k: ('' if v is None else v if isinstance(v, (list, dict)) else str(v))
                for k, v in meta.items()
            }
            return meta, body
    return {}, text


def split_long_text(text, max_chars=MAX_CHUNK_CHARS):
    """Split text that exceeds max_chars by sentences, with ~15% overlap."""
    if len(text) <= max_chars:
        return [text]

    overlap_chars = int(max_chars * OVERLAP_RATIO)
    sents = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    buf, buflen = [], 0
    for s in sents:
        if buflen + len(s) > max_chars and buf:
            chunk_text = ' '.join(buf)
            chunks.append(chunk_text)
            if overlap_chars > 0 and len(chunk_text) > overlap_chars:
                tail = chunk_text[-overlap_chars:]
                space_idx = tail.find(' ')
                if space_idx >= 0:
                    tail = tail[space_idx + 1:]
                buf, buflen = [tail, s], len(tail) + len(s) + 1
            else:
                buf, buflen = [s], len(s)
        else:
            buf.append(s)
            buflen += len(s) + 1
    if buf:
        chunks.append(' '.join(buf))

    final = []
    for c in chunks:
        if len(c) > max_chars * 2:
            for i in range(0, len(c), max_chars):
                final.append(c[i:i + max_chars])
        else:
            final.append(c)
    return final


def merge_tiny_chunks(chunks, min_chars=MIN_CHUNK_CHARS):
    """Merge chunks smaller than min_chars with the previous chunk."""
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


# ─── Chunkers ─────────────────────────────────────────────────────────────────

def merge_paragraphs(paras, max_chars=MAX_CHUNK_CHARS, min_chars=MIN_CHUNK_CHARS):
    """Merge consecutive paragraphs into chunks of ~max_chars."""
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


def chunk_markdown(file_path, source_type='default'):
    """General-purpose markdown chunker.

    Splits by ## and ### headings, keeps tables with their section,
    falls back to paragraph merge when no headings found.
    Handles single-newline line wrapping (normalizes to spaces).
    """
    text = Path(file_path).read_text(encoding='utf-8')
    meta, body = parse_frontmatter(text)
    source_book = meta.get('source_book', meta.get('book', Path(file_path).stem))
    chapter = meta.get('chapter', '')

    # Normalize single newlines to spaces (some sources use \n for line wrapping)
    normalized = re.sub(r'(?<!\n)\n(?!\n)', ' ', body)

    # Split by ## and ### headings. Prepend a newline so a heading at the very
    # start of the body (the common case right after frontmatter) is detected.
    heading_pattern = re.compile(r'\n(#{2,3}\s+.+)\n')
    sections = heading_pattern.split('\n' + normalized)

    chunks = []
    idx = 0

    def add_chunk(text_content, section_title):
        nonlocal idx
        text_content = text_content.strip()
        if len(text_content) < 20:
            return
        paras = [p.strip() for p in re.split(r'\n\s*\n', text_content) if len(p.strip()) > 10]
        for merged in merge_paragraphs(paras):
            for split_text in split_long_text(merged, MAX_CHUNK_CHARS):
                chunks.append({
                    'source_type': source_type,
                    'source_book': source_book,
                    'source_file': str(file_path),
                    'book': meta.get('book', source_book),
                    'chapter': chapter,
                    'section_title': section_title,
                    'chunk_index': idx,
                    'chunk_text': split_text,
                })
                idx += 1

    if len(sections) <= 1:
        # No headings — paragraph merge fallback
        paras = [p.strip() for p in re.split(r'\n\s*\n', normalized) if len(p.strip()) > 20]
        for merged in merge_paragraphs(paras):
            for split_text in split_long_text(merged, MAX_CHUNK_CHARS):
                chunks.append({
                    'source_type': source_type,
                    'source_book': source_book,
                    'source_file': str(file_path),
                    'book': meta.get('book', source_book),
                    'chapter': chapter,
                    'section_title': meta.get('title'),
                    'chunk_index': idx,
                    'chunk_text': split_text,
                })
                idx += 1
    else:
        # Process preamble
        if sections and sections[0].strip():
            add_chunk(sections[0], meta.get('title', 'Introduction'))
        # Process sections with headings. Carry the nearest ## (level-2) heading
        # forward so a ### subsection chunk keeps its parent's context as a
        # breadcrumb ("Section — Subsection") instead of losing it.
        last_h2 = None
        i = 1
        while i < len(sections):
            raw_heading = sections[i].strip()
            level = len(raw_heading) - len(raw_heading.lstrip('#'))
            heading = raw_heading.lstrip('#').strip()
            section_text = sections[i + 1].strip() if i + 1 < len(sections) else ''
            if level <= 2:
                last_h2 = heading
                section_title = heading
            else:  # deeper heading inherits the nearest preceding ## as a breadcrumb
                section_title = f"{last_h2} — {heading}" if last_h2 else heading
            if len(section_text) > 10:
                add_chunk(section_text, section_title)
            i += 2

    return merge_tiny_chunks(chunks)


def chunk_plain_text(file_path, source_type='default'):
    """Chunk plain text files by paragraph merge."""
    text = Path(file_path).read_text(encoding='utf-8')
    paras = [p.strip() for p in re.split(r'\n\s*\n', text) if len(p.strip()) > 20]
    chunks = []
    source_book = Path(file_path).stem
    for idx, merged in enumerate(merge_paragraphs(paras)):
        for split_text in split_long_text(merged, MAX_CHUNK_CHARS):
            chunks.append({
                'source_type': source_type,
                'source_book': source_book,
                'source_file': str(file_path),
                'book': source_book,
                'chapter': '',
                'section_title': None,
                'chunk_index': len(chunks),
                'chunk_text': split_text,
            })
    return merge_tiny_chunks(chunks)


# ─── File Discovery ───────────────────────────────────────────────────────────

def discover_files():
    """
    Discover all indexable files in the library root.

    Default behavior: scan LIBRARY_ROOT recursively for .md and .txt files.
    Source type is derived from the top-level directory name under LIBRARY_ROOT.

    Override this function or register custom chunkers for domain-specific needs.
    See references/chunking-strategies.md for patterns.
    """
    files = []  # (path, source_type, chunker)

    if not LIBRARY_ROOT.exists():
        return files

    # Scan top-level directories as source types
    for top_dir in sorted(LIBRARY_ROOT.iterdir()):
        if not top_dir.is_dir() or top_dir.name.startswith('.'):
            continue
        source_type = top_dir.name

        # Find all .md and .txt files recursively
        for ext in ['*.md', '*.txt']:
            for f in sorted(top_dir.rglob(ext)):
                if f.name.startswith('.') or '__pycache__' in str(f):
                    continue
                chunker = chunk_markdown if ext == '*.md' else chunk_plain_text
                files.append((str(f), source_type, chunker))

    return files


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='RAG Indexer')
    parser.add_argument('--rebuild', action='store_true', help='Drop everything and re-index')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be indexed, no API calls')
    parser.add_argument('--source', type=str, help='Only index specific source type')
    parser.add_argument('--db', type=str, help='Custom DB path')
    args = parser.parse_args()

    global DB_PATH
    if args.db:
        DB_PATH = Path(args.db)

    api_key = load_api_key() if not args.dry_run else None

    LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    init_db(conn, rebuild=args.rebuild)

    all_files = discover_files()
    if args.source:
        all_files = [f for f in all_files if f[1] == args.source]

    print(f"📚 RAG Indexer")
    print(f"   Library: {LIBRARY_ROOT}")
    print(f"   DB: {DB_PATH}")
    print(f"   Model: {EMBEDDING_MODEL} ({EMBEDDING_DIMS}-dim)")
    print(f"   Mode: {'dry-run' if args.dry_run else 'rebuild' if args.rebuild else 'incremental'}")
    print(f"   Files discovered: {len(all_files)}")
    print()

    total_chunks = 0
    total_tokens = 0
    total_cost = 0.0
    files_indexed = 0
    files_skipped = 0
    errors = []

    for file_path, source_type, chunker in all_files:
        fhash = file_hash(file_path)

        if not args.rebuild:
            existing = conn.execute(
                'SELECT file_hash FROM indexed_files WHERE file_path = ?', (file_path,)
            ).fetchone()
            if existing and existing[0] == fhash:
                files_skipped += 1
                continue

        if args.dry_run:
            try:
                chunks = chunker(file_path, source_type=source_type)
            except Exception as e:
                print(f"  ❌ Chunk error: {Path(file_path).name}: {e}")
                errors.append((file_path, str(e)))
                continue
            print(f"  📄 {source_type:12s} {Path(file_path).name:45s} → {len(chunks)} chunks")
            total_chunks += len(chunks)
            files_indexed += 1
            continue

        print(f"  🔖 {source_type:12s} {Path(file_path).name:45s}", end='', flush=True)

        try:
            stored, usage = index_file(conn, file_path, source_type, chunker, api_key)
        except Exception as e:
            print(f"\n  ❌ {Path(file_path).name}: {e}")
            errors.append((file_path, str(e)))
            continue

        if stored == 0:
            files_skipped += 1
            print(" → no chunks, skipped")
            continue

        total_chunks += stored
        total_tokens += usage.get('prompt_tokens', 0)
        total_cost += usage.get('cost', 0)
        files_indexed += 1
        print(f" → {stored} chunks ✓")

    conn.close()

    print()
    print("=" * 60)
    print(f"✅ Indexing complete")
    print(f"   Files indexed: {files_indexed}")
    print(f"   Files skipped: {files_skipped}")
    print(f"   Total chunks:  {total_chunks}")
    if not args.dry_run:
        print(f"   Total tokens:  {total_tokens:,}")
        print(f"   Estimated cost: ${total_cost:.4f}")
    if errors:
        print(f"   Errors: {len(errors)}")
        for fp, err in errors:
            print(f"     {Path(fp).name}: {err}")
    print("=" * 60)


if __name__ == '__main__':
    main()
