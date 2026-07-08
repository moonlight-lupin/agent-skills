#!/usr/bin/env python3
"""
MCP Server for Library RAG — exposes semantic search over a personal library.

Tools exposed:
  - search(query, top_k, source_type) — semantic search across library
  - stats() — index statistics
  - add_book(file_path, book_slug, author, title, year) — convert EPUB/PDF → md → index

Config in ~/.hermes/config.yaml:
  mcp_servers:
    library_rag:
      command: "python3"
      args: ["~/.hermes/skills/research/library-rag/scripts/mcp_server.py"]
      timeout: 60
"""

import sys, os, json, sqlite3
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_common import load_api_key, get_embedding, float_to_blob, connect_db

# ─── Config ───────────────────────────────────────────────────────────────────
LIBRARY_ROOT = Path(os.environ.get('LIBRARY_ROOT', os.path.expanduser('~/.hermes/library')))
DB_PATH = LIBRARY_ROOT / 'rag_index.db'


# ─── MCP Server ───────────────────────────────────────────────────────────────

def main():
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types

    app = Server("library_rag")

    @app.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="search",
                description="Semantic search across the library. "
                            "Supports any language. Returns matching passages with citations.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query"
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results to return (default 10, max 100)",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 100
                        },
                        "source_type": {
                            "type": "string",
                            "description": "Filter by source type (top-level directory name under library root). "
                                          "Omit to search all sources.",
                        }
                    },
                    "required": ["query"]
                }
            ),
            types.Tool(
                name="stats",
                description="Show RAG index statistics: total chunks, breakdown by source type, DB size.",
                inputSchema={"type": "object", "properties": {}}
            ),
            types.Tool(
                name="add_book",
                description="Convert an EPUB or PDF file to Markdown and index it for semantic search. "
                            "EPUBs split by chapter; PDFs split by page with tables preserved. "
                            "Returns the number of chunks indexed.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path to the .epub or .pdf file"
                        },
                        "book_slug": {
                            "type": "string",
                            "description": "Slug for the book directory (e.g. 'my-book')"
                        },
                        "author": {"type": "string", "description": "Author name"},
                        "title": {"type": "string", "description": "Book title"},
                        "year": {"type": "string", "description": "Publication year"}
                    },
                    "required": ["file_path", "book_slug", "author", "title"]
                }
            ),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        if name == "search":
            query = arguments["query"]
            # Clamp to a sane range — guard against huge/zero/invalid values.
            try:
                top_k = int(arguments.get("top_k", 10))
            except (TypeError, ValueError):
                top_k = 10
            top_k = max(1, min(top_k, 100))
            source_type = arguments.get("source_type")

            if not DB_PATH.exists():
                return [types.TextContent(type="text", text="Error: Index DB not found. Run rag_index.py first.")]

            query_emb = get_embedding(query, load_api_key())
            query_blob = float_to_blob(query_emb)
            conn = connect_db(DB_PATH)

            total_vecs = conn.execute('SELECT COUNT(*) FROM vec_chunks').fetchone()[0]
            if total_vecs == 0:
                conn.close()
                return [types.TextContent(type="text", text="[]")]

            # Over-fetch + post-filter; grow k for sparse source types (capped at corpus size).
            fetch_k = min(top_k * 5 if source_type else top_k, total_vecs)
            results = []
            while True:
                raw = conn.execute(
                    'SELECT rowid, distance FROM vec_chunks WHERE embedding MATCH ? AND k = ? ORDER BY distance',
                    (query_blob, fetch_k)
                ).fetchall()

                results = []
                for rowid, distance in raw:
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
                        'similarity': round(sim, 4),
                        'source_type': row[0],
                        'source_book': row[1],
                        'book': row[3],
                        'chapter': row[4],
                        'section_title': row[5],
                        'text': row[6][:500] + '...' if len(row[6]) > 500 else row[6],
                    })
                    if len(results) >= top_k:
                        break

                if len(results) >= top_k or fetch_k >= total_vecs or not source_type:
                    break
                fetch_k = min(fetch_k * 2, total_vecs)
            conn.close()

            results.sort(key=lambda x: x['similarity'], reverse=True)
            return [types.TextContent(type="text", text=json.dumps(results, ensure_ascii=False, indent=2))]

        elif name == "stats":
            if not DB_PATH.exists():
                return [types.TextContent(type="text", text="Index DB not found.")]
            conn = connect_db(DB_PATH)
            total = conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
            by_type = conn.execute(
                'SELECT source_type, COUNT(*) FROM chunks GROUP BY source_type ORDER BY COUNT(*) DESC'
            ).fetchall()
            files = conn.execute('SELECT COUNT(*) FROM indexed_files').fetchone()[0]
            db_size = DB_PATH.stat().st_size
            conn.close()

            stats = {
                'total_chunks': total,
                'files_indexed': files,
                'db_size_mb': round(db_size / 1024 / 1024, 1),
                'by_source': {s[0]: s[1] for s in by_type}
            }
            return [types.TextContent(type="text", text=json.dumps(stats, ensure_ascii=False, indent=2))]

        elif name == "add_book":
            file_path = arguments["file_path"]
            book_slug = arguments["book_slug"]
            author = arguments.get("author", "")
            title = arguments.get("title", "")
            year = arguments.get("year", "")

            # Step 1: Convert to structured markdown (EPUB → chapters, PDF → pages).
            # Markdown lands under LIBRARY_ROOT so the indexer discovers it; the raw
            # file + extracted text stage outside it (avoids double-indexing).
            md_root = LIBRARY_ROOT / 'books' / 'markdown'
            if str(file_path).lower().endswith('.pdf'):
                from convert_pdf_library import convert_pdf
                conv = convert_pdf(file_path, book_slug, title=title, author=author,
                                   year=year, md_root=md_root)
            else:
                from convert_epub_library import convert_epub
                conv = convert_epub(file_path, book_slug, title=title, author=author,
                                    year=year, md_root=md_root)

            # Step 2: Index the new files via the same atomic indexer the CLI uses
            # (handles stale-chunk removal + partial-failure rollback).
            from rag_index import discover_files, file_hash, init_db, index_file

            api_key = load_api_key()
            conn = sqlite3.connect(str(DB_PATH))
            init_db(conn, rebuild=False)

            # Restrict to files under this book's exact markdown directory — a
            # substring match on the slug could catch unrelated books.
            md_dir = Path(conv['markdown_dir']).resolve()
            new_files = [t for t in discover_files()
                         if md_dir in Path(t[0]).resolve().parents]

            total_chunks = 0
            for file_path, source_type, chunker in new_files:
                fhash = file_hash(file_path)
                existing = conn.execute(
                    'SELECT file_hash FROM indexed_files WHERE file_path = ?', (file_path,)
                ).fetchone()
                if existing and existing[0] == fhash:
                    continue
                stored, _ = index_file(conn, file_path, source_type, chunker, api_key)
                total_chunks += stored

            conn.close()
            return [types.TextContent(type="text",
                text=json.dumps({
                    'status': 'success',
                    'book': title,
                    # chapters for EPUB, pages for PDF
                    'segments_created': conv.get('chapters', conv.get('pages')),
                    'chunks_indexed': total_chunks,
                    'markdown_dir': conv['markdown_dir'],
                    'raw_text_saved': conv['text_path'],
                    'raw_file_saved': conv['raw_path'],
                }, indent=2))]

    import asyncio

    async def run():
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())

    asyncio.run(run())

if __name__ == '__main__':
    main()
