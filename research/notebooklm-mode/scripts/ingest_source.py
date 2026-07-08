#!/usr/bin/env python3
"""
NotebookLM-mode atomic ingest: write a source file AND optionally index it
into the vault's rag_index.db in a single call.

If library-rag (bge-m3 + sqlite-vec) is available, indexes the source for
semantic search. If not, writes the file only — the skill still works, just
without semantic search (use direct file reading for small vaults).

Usage:
  python3 ingest_source.py --vault /path/to/vault --file 001_title.md --content "..."
  python3 ingest_source.py --vault /path/to/vault --file 001_title.md --content-file /tmp/source.txt
  python3 ingest_source.py --vault /path/to/vault --reindex  # reindex all sources/
  python3 ingest_source.py --vault /path/to/vault --search "query"  # semantic search

Can also be imported:
  from ingest_source import ingest, search_vault, reindex_vault
  result = ingest(vault_path, "001_title.md", content)  # writes + indexes if RAG available
  results = search_vault(vault_path, "query")            # returns [] if no RAG index
  reindex_vault(vault_path)                               # no-op if no RAG available
"""

import os, sys, sqlite3, argparse
from pathlib import Path

# ─── Resolve library-rag (optional dependency) ────────────────────────────────

def _resolve_rag_scripts():
    """Try to locate library-rag scripts. Returns Path or None."""
    # 1. Explicit env var
    p = Path(os.environ.get('LIBRARY_RAG_SCRIPTS', ''))
    if p.exists():
        return p
    # 2. Default Hermes layout (research/ mirrors this repo; note-taking/ kept for older installs)
    for rel in ('.hermes/skills/research/library-rag/scripts',
                '.hermes/skills/note-taking/library-rag/scripts'):
        p = Path.home() / rel
        if p.exists():
            return p
    # 3. Relative to this script (sibling skill in same repo)
    p = Path(__file__).resolve().parent.parent.parent / 'library-rag' / 'scripts'
    if p.exists():
        return p
    # 4. Relative to this script (same domain folder in agent_skills repo)
    p = Path(__file__).resolve().parent.parent.parent / 'research' / 'library-rag' / 'scripts'
    if p.exists():
        return p
    return None

LIBRARY_RAG_SCRIPTS = _resolve_rag_scripts()

# ─── Load RAG modules if available ────────────────────────────────────────────

RAG_AVAILABLE = False
if LIBRARY_RAG_SCRIPTS:
    sys.path.insert(0, str(LIBRARY_RAG_SCRIPTS))
    try:
        from rag_common import load_api_key, get_embeddings, get_embedding, float_to_blob, connect_db
        import rag_index
        RAG_AVAILABLE = True
    except ImportError:
        pass

if not RAG_AVAILABLE:
    import warnings
    warnings.warn(
        "library-rag not found. Source files will be written but NOT indexed for semantic search. "
        "Set LIBRARY_RAG_SCRIPTS env var or co-locate library-rag alongside this skill. "
        "The skill still works — use direct file reading for small vaults."
    )


# ─── Ingest ───────────────────────────────────────────────────────────────────

def ingest(vault_path, filename, content):
    """Write a source file and index it if RAG is available.

    Args:
        vault_path: Path to the workspace vault
        filename: Source filename (e.g., '001_title.md')
        content: Full source file content

    Returns:
        dict with: file_path, chunks_indexed, indexed (bool), success
    """
    vault = Path(vault_path)
    sources_dir = vault / 'sources'
    sources_dir.mkdir(parents=True, exist_ok=True)

    file_path = sources_dir / filename

    # Step 1: Write the source file (always)
    file_path.write_text(content, encoding='utf-8')

    # Step 2: Index if RAG is available (optional)
    if not RAG_AVAILABLE:
        return {
            'file_path': str(file_path),
            'chunks_indexed': 0,
            'indexed': False,
            'success': True,  # file write succeeded
            'message': 'File saved. RAG indexing skipped (library-rag not available).'
        }

    db_path = vault / 'rag_index.db'
    rag_index.DB_PATH = db_path
    rag_index.LIBRARY_ROOT = vault

    api_key = load_api_key()
    conn = sqlite3.connect(str(db_path))
    rag_index.init_db(conn)

    source_type = 'sources'
    chunker = rag_index.chunk_markdown
    stored, usage = rag_index.index_file(conn, str(file_path), source_type, chunker, api_key)
    conn.close()

    return {
        'file_path': str(file_path),
        'chunks_indexed': stored,
        'indexed': True,
        'success': stored > 0,
    }


def reindex_vault(vault_path):
    """Reindex all source files in a vault.

    No-op if RAG is not available (returns empty result with a message).

    Args:
        vault_path: Path to the workspace vault

    Returns:
        dict with: files_indexed, total_chunks, errors, indexed
    """
    vault = Path(vault_path)
    sources_dir = vault / 'sources'

    if not sources_dir.exists():
        return {'files_indexed': 0, 'total_chunks': 0, 'errors': ['sources/ directory not found'], 'indexed': False}

    if not RAG_AVAILABLE:
        return {'files_indexed': 0, 'total_chunks': 0, 'errors': [], 'indexed': False,
                'message': 'RAG reindex skipped (library-rag not available).'}

    db_path = vault / 'rag_index.db'
    rag_index.DB_PATH = db_path
    rag_index.LIBRARY_ROOT = vault

    api_key = load_api_key()
    conn = sqlite3.connect(str(db_path))
    rag_index.init_db(conn, rebuild=True)

    source_type = 'sources'
    chunker = rag_index.chunk_markdown

    files_indexed = 0
    total_chunks = 0
    errors = []

    for f in sorted(sources_dir.glob('*.md')):
        try:
            stored, usage = rag_index.index_file(conn, str(f), source_type, chunker, api_key)
            if stored > 0:
                files_indexed += 1
                total_chunks += stored
        except Exception as e:
            errors.append(f"{f.name}: {e}")

    conn.close()

    return {
        'files_indexed': files_indexed,
        'total_chunks': total_chunks,
        'errors': errors,
        'indexed': True,
    }


def search_vault(vault_path, query, top_k=5):
    """Semantic search over a vault's rag_index.db.

    Returns empty list if RAG is not available or the DB doesn't exist.
    In that case, use direct file reading instead.

    Args:
        vault_path: Path to the workspace vault
        query: Natural language search query
        top_k: Number of results

    Returns:
        List of dicts with: rank, similarity, source_file, section_title, chunk_text
    """
    if not RAG_AVAILABLE:
        return []

    vault = Path(vault_path)
    db_path = vault / 'rag_index.db'

    if not db_path.exists():
        return []

    api_key = load_api_key()
    query_emb = get_embedding(query, api_key)
    query_blob = float_to_blob(query_emb)

    conn = connect_db(db_path)

    total_vecs = conn.execute('SELECT COUNT(*) FROM vec_chunks').fetchone()[0]
    if total_vecs == 0:
        conn.close()
        return []

    fetch_k = min(top_k, total_vecs)
    raw_results = conn.execute('''
        SELECT rowid, distance FROM vec_chunks
        WHERE embedding MATCH ? AND k = ?
        ORDER BY distance
    ''', (query_blob, fetch_k)).fetchall()

    results = []
    for rowid, distance in raw_results:
        row = conn.execute('''
            SELECT source_type, source_file, section_title, chunk_text
            FROM chunks WHERE id = ?
        ''', (rowid,)).fetchone()
        if not row:
            continue
        sim = max(0, 1 - distance ** 2 / 2)
        results.append({
            'rank': len(results) + 1,
            'similarity': sim,
            'source_type': row[0],
            'source_file': row[1],
            'section_title': row[2],
            'chunk_text': row[3],
        })

    conn.close()
    results.sort(key=lambda x: x['similarity'], reverse=True)
    for i, r in enumerate(results):
        r['rank'] = i + 1
    return results


# ─── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='NotebookLM-mode atomic ingest')
    parser.add_argument('--vault', required=True, help='Path to the workspace vault')
    parser.add_argument('--file', help='Source filename (e.g., 001_title.md)')
    parser.add_argument('--content', help='Source content as string')
    parser.add_argument('--content-file', help='Read content from this file')
    parser.add_argument('--reindex', action='store_true', help='Reindex all sources/ in the vault')
    parser.add_argument('--search', help='Semantic search query over the vault')
    parser.add_argument('--top-k', type=int, default=5, help='Search results count')
    args = parser.parse_args()

    if not RAG_AVAILABLE:
        print("⚠️  library-rag not found — semantic search and indexing are unavailable.", file=sys.stderr)
        print("   Set LIBRARY_RAG_SCRIPTS env var or co-locate library-rag alongside this skill.", file=sys.stderr)
        print("   File writes still work; use direct file reading for small vaults.", file=sys.stderr)

    if args.search:
        results = search_vault(args.vault, args.search, top_k=args.top_k)
        if not results:
            print("No results (RAG unavailable or no index found).")
        for r in results:
            print(f"[{r['similarity']:.0%}] {r['source_file']} — {r['section_title']}")
            print(f"  {r['chunk_text'][:200]}")
        return

    if args.reindex:
        result = reindex_vault(args.vault)
        if result.get('indexed'):
            print(f"Reindexed: {result['files_indexed']} files, {result['total_chunks']} chunks")
        else:
            print(result.get('message', 'RAG reindex skipped.'))
        if result['errors']:
            print(f"Errors: {result['errors']}")
        return

    if not args.file:
        parser.error('--file is required unless --reindex or --search is used')

    if args.content_file:
        content = Path(args.content_file).read_text(encoding='utf-8')
    elif args.content:
        content = args.content
    else:
        parser.error('--content or --content-file is required')

    result = ingest(args.vault, args.file, content)
    print(f"Saved: {result['file_path']}")
    if result.get('indexed'):
        print(f"Indexed: {result['chunks_indexed']} chunks")
    else:
        print(result.get('message', 'File saved (not indexed).'))


if __name__ == '__main__':
    main()