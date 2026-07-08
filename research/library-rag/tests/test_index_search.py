"""End-to-end store + vector-search round trip against real sqlite-vec.

No API calls: embeddings are deterministic one-hot vectors injected directly,
so this exercises init_db / store_batch / float_to_blob normalization, the
sqlite-vec MATCH query, the `1 - d**2/2` similarity, and search's post-filter.
"""
import sqlite3

import pytest

import rag_index as ri
import rag_query as rq


def one_hot(dim, hot):
    v = [0.0] * dim
    v[hot] = 1.0
    return v


def build_index(db_path):
    conn = sqlite3.connect(str(db_path))
    ri.init_db(conn, rebuild=True)
    dim = ri.EMBEDDING_DIMS
    chunks = [
        {"source_type": "books", "source_book": "B", "source_file": "f1",
         "book": "B", "chapter": "1", "section_title": "S", "chunk_index": 0,
         "chunk_text": "alpha content", "file_hash": "h"},
        {"source_type": "notes", "source_book": "N", "source_file": "f2",
         "book": "N", "chapter": "", "section_title": None, "chunk_index": 0,
         "chunk_text": "beta content", "file_hash": "h"},
    ]
    ri.store_batch(conn, chunks, [one_hot(dim, 0), one_hot(dim, 1)])
    conn.commit()
    conn.close()
    return dim


def test_search_ranks_nearest_first(tmp_path, monkeypatch):
    db = tmp_path / "idx.db"
    dim = build_index(db)

    monkeypatch.setattr(rq, "DB_PATH", db)
    monkeypatch.setattr(rq, "load_api_key", lambda: "k")
    monkeypatch.setattr(rq, "get_embedding", lambda q, key: one_hot(dim, 0))

    res = rq.search("anything", top_k=2)
    assert res[0]["chunk_text"] == "alpha content"
    assert res[0]["rank"] == 1
    assert res[0]["similarity"] > 0.99
    # the orthogonal vector should score near zero
    assert res[1]["similarity"] < 0.01


def test_search_source_filter(tmp_path, monkeypatch):
    db = tmp_path / "idx.db"
    dim = build_index(db)

    monkeypatch.setattr(rq, "DB_PATH", db)
    monkeypatch.setattr(rq, "load_api_key", lambda: "k")
    # query nearest to the 'notes' vector, but filter to 'books'
    monkeypatch.setattr(rq, "get_embedding", lambda q, key: one_hot(dim, 1))

    res = rq.search("anything", top_k=5, source_type="books")
    assert res
    assert all(r["source_type"] == "books" for r in res)
    assert all(r["chunk_text"] == "alpha content" for r in res)


def test_search_missing_db_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(rq, "DB_PATH", tmp_path / "nope.db")
    monkeypatch.setattr(rq, "load_api_key", lambda: "k")
    monkeypatch.setattr(rq, "get_embedding", lambda q, key: [0.0])
    with pytest.raises(FileNotFoundError):
        rq.search("q")


def sparse_vec(dim, pairs):
    v = [0.0] * dim
    for idx, val in pairs:
        v[idx] = val
    return v


def build_sparse_index(db_path):
    """Two 'notes' chunks (one a perfect match, one far away) plus many closer
    'books' chunks — so the far 'notes' chunk only surfaces if over-fetch grows."""
    conn = sqlite3.connect(str(db_path))
    ri.init_db(conn, rebuild=True)
    dim = ri.EMBEDDING_DIMS

    chunks, embs = [], []

    def add(stype, text, vec):
        chunks.append({"source_type": stype, "source_book": stype, "source_file": f"{stype}-{len(chunks)}",
                       "book": stype, "chapter": "", "section_title": None,
                       "chunk_index": 0, "chunk_text": text, "file_hash": "h"})
        embs.append(vec)

    add("notes", "notes near", sparse_vec(dim, [(0, 1.0)]))          # exact match to query
    add("notes", "notes far", sparse_vec(dim, [(1, 1.0)]))           # orthogonal -> farthest
    for j in range(30):
        add("books", f"book {j}", sparse_vec(dim, [(0, 10.0), (2, (j + 1) * 0.1)]))  # all near e0

    ri.store_batch(conn, chunks, embs)
    conn.commit()
    conn.close()
    return dim


def test_search_overfetch_grows_for_sparse_source(tmp_path, monkeypatch):
    db = tmp_path / "idx.db"
    dim = build_sparse_index(db)

    monkeypatch.setattr(rq, "DB_PATH", db)
    monkeypatch.setattr(rq, "load_api_key", lambda: "k")
    monkeypatch.setattr(rq, "get_embedding", lambda q, key: sparse_vec(dim, [(0, 1.0)]))

    # The far 'notes' chunk ranks last overall (after 30 books); a single
    # top_k*5 fetch would miss it. Iterative growth must surface both notes.
    res = rq.search("q", top_k=2, source_type="notes")
    assert len(res) == 2
    assert all(r["source_type"] == "notes" for r in res)


def test_search_source_filter_returns_fewer_when_truly_sparse(tmp_path, monkeypatch):
    db = tmp_path / "idx.db"
    dim = build_index(db)  # only one 'notes' chunk exists

    monkeypatch.setattr(rq, "DB_PATH", db)
    monkeypatch.setattr(rq, "load_api_key", lambda: "k")
    monkeypatch.setattr(rq, "get_embedding", lambda q, key: one_hot(dim, 1))

    # Asking for more than exist must terminate and return what's available.
    res = rq.search("q", top_k=5, source_type="notes")
    assert len(res) == 1
    assert res[0]["source_type"] == "notes"
