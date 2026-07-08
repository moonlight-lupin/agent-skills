#!/usr/bin/env python3
"""
RAG Query — semantic search over a personal library.

Usage:
  python3 rag_query.py "your search query"
  python3 rag_query.py "search terms" --top-k 5
  python3 rag_query.py "query" --source my-source-type --verbose
  python3 rag_query.py --stats

Can also be imported:
  from rag_query import search
  results = search("query text", top_k=10)
"""

import os, sys, json, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_common import load_api_key, get_embedding, float_to_blob, connect_db

# ─── Config ───────────────────────────────────────────────────────────────────
LIBRARY_ROOT = Path(os.environ.get('LIBRARY_ROOT', os.path.expanduser('~/.hermes/library')))
DB_PATH = LIBRARY_ROOT / 'rag_index.db'


# ─── Search ───────────────────────────────────────────────────────────────────

def search(query, top_k=10, source_type=None, api_key=None):
    """
    Semantic search over the library.

    Args:
        query: Natural language search query
        top_k: Number of results to return
        source_type: Optional filter by source type (top-level directory name)
        api_key: OpenRouter API key (loaded from env if not provided)

    Returns:
        List of dicts with: rank, similarity, source_type, source_book,
        book, chapter, section_title, chunk_text, source_file
    """
    if api_key is None:
        api_key = load_api_key()
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Index DB not found at {DB_PATH}. Run rag_index.py first.")

    query_emb = get_embedding(query, api_key)
    query_blob = float_to_blob(query_emb)

    conn = connect_db(DB_PATH)

    total_vecs = conn.execute('SELECT COUNT(*) FROM vec_chunks').fetchone()[0]
    if total_vecs == 0:
        conn.close()
        return []

    # sqlite-vec MATCH/k can't combine with WHERE clauses, so we over-fetch and
    # post-filter by source_type. When a source type is sparse, the first over-fetch
    # may not yield top_k matches — iteratively grow k (capped at the corpus size)
    # until we have enough or have scanned everything.
    fetch_k = min(top_k * 5 if source_type else top_k, total_vecs)
    results = []
    while True:
        raw_results = conn.execute('''
            SELECT rowid, distance FROM vec_chunks
            WHERE embedding MATCH ? AND k = ?
            ORDER BY distance
        ''', (query_blob, fetch_k)).fetchall()

        results = []
        for rowid, distance in raw_results:
            row = conn.execute('''
                SELECT source_type, source_book, source_file, book, chapter,
                       section_title, chunk_text
                FROM chunks WHERE id = ?
            ''', (rowid,)).fetchone()

            if not row:
                continue
            if source_type and row[0] != source_type:
                continue

            sim = max(0, 1 - distance ** 2 / 2)
            results.append({
                'rowid': rowid,
                'distance': distance,
                'similarity': sim,
                'source_type': row[0],
                'source_book': row[1],
                'source_file': row[2],
                'book': row[3],
                'chapter': row[4],
                'section_title': row[5],
                'chunk_text': row[6],
            })

            if len(results) >= top_k:
                break

        if len(results) >= top_k or fetch_k >= total_vecs or not source_type:
            break
        fetch_k = min(fetch_k * 2, total_vecs)

    conn.close()

    results.sort(key=lambda x: x['similarity'], reverse=True)
    for i, r in enumerate(results):
        r['rank'] = i + 1

    return results


def stats():
    """Print index statistics."""
    conn = connect_db(DB_PATH)

    total = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
    by_type = conn.execute('''
        SELECT source_type, COUNT(*) as cnt FROM chunks
        GROUP BY source_type ORDER BY cnt DESC
    ''').fetchall()
    files = conn.execute('SELECT COUNT(*) FROM indexed_files').fetchone()[0]

    print(f"📚 RAG Index Statistics")
    print(f"   DB: {DB_PATH}")
    print(f"   Total chunks: {total:,}")
    print(f"   Files indexed: {files}")
    print(f"\n   By source type:")
    for stype, cnt in by_type:
        print(f"     {stype:25s} {cnt:>7,}")

    db_size = DB_PATH.stat().st_size
    print(f"\n   DB size: {db_size / 1024 / 1024:.1f} MB")
    conn.close()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def format_result(r, verbose=False):
    """Format a single result for display."""
    citation_parts = []
    if r['book']:
        citation_parts.append(r['book'])
    if r['chapter']:
        citation_parts.append(r['chapter'])
    if r['section_title']:
        citation_parts.append(r['section_title'])

    citation = ' — '.join(citation_parts) if citation_parts else 'Unknown section'
    source_label = f"[{r['source_type']}]"
    book_label = f"({r['source_book']})" if r['source_book'] else ""
    sim_pct = f"{r['similarity']:.1%}"

    text = r['chunk_text']
    if not verbose and len(text) > 400:
        text = text[:400] + '...'

    return f"{r['rank']}. {source_label} {book_label} {citation} ({sim_pct})\n   {text}"


def main():
    parser = argparse.ArgumentParser(description='RAG Query')
    parser.add_argument('query', nargs='?', help='Search query')
    parser.add_argument('--top-k', type=int, default=10, help='Number of results')
    parser.add_argument('--source', type=str, help='Filter by source type')
    parser.add_argument('--stats', action='store_true', help='Show index statistics')
    parser.add_argument('--verbose', action='store_true', help='Show full chunk text')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    args = parser.parse_args()

    if args.stats:
        stats()
        return

    if not args.query:
        parser.print_help()
        return

    results = search(
        args.query,
        top_k=args.top_k,
        source_type=args.source,
    )

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        if not results:
            print("No results found.")
            return
        print(f"🔍 Query: \"{args.query}\"")
        if args.source:
            print(f"   Filter: source={args.source}")
        print(f"   Results: {len(results)}\n")
        for r in results:
            print(format_result(r, verbose=args.verbose))
            print()


if __name__ == '__main__':
    main()
