"""Tests for --prune-missing and --vacuum: dead-row cleanup keeps the DB bounded.

No API calls — embeddings are injected (the index path is already covered by
test_indexing_atomicity.py; these focus on the pruning/vacuum logic).
"""
import os
import sqlite3
import sys

import pytest

import rag_index as ri


def fake_embeddings_ok(dim):
    return lambda texts, key, retries=3: ([[0.1] * dim for _ in texts],
                                          {"prompt_tokens": 1, "cost": 0.0})


def make_doc(path, paras=4):
    body = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(paras))
    path.write_text(f"---\nbook: B\n---\n\n## Heading\n\n{body}")


def _index_file_into(conn, path, source_type="books"):
    dim = ri.EMBEDDING_DIMS
    stored, _ = ri.index_file(conn, str(path), source_type, ri.chunk_markdown, "key")
    return stored


@pytest.fixture
def db_and_docs(tmp_path, monkeypatch):
    conn = sqlite3.connect(str(tmp_path / "db.sqlite"))
    ri.init_db(conn, rebuild=True)
    monkeypatch.setattr(ri, "get_embeddings", fake_embeddings_ok(ri.EMBEDDING_DIMS))
    return conn, tmp_path


def test_prune_missing_removes_dead_rows(db_and_docs):
    conn, tmp = db_and_docs

    keep = tmp / "keep.md"
    gone = tmp / "gone.md"
    make_doc(keep)
    make_doc(gone)
    ri.index_file(conn, str(keep), "books", ri.chunk_markdown, "key")
    ri.index_file(conn, str(gone), "books", ri.chunk_markdown, "key")
    chunks_before = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    # "gone.md" no longer exists on disk — prune against only keep.md
    files_pruned, chunks_pruned = ri.prune_missing(conn, [str(keep)])

    assert files_pruned == 1
    assert chunks_pruned > 0
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == chunks_before - chunks_pruned
    # vec rows stay in lockstep
    assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == \
        conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    # record gone from indexed_files
    assert conn.execute(
        "SELECT COUNT(*) FROM indexed_files WHERE file_path = ?", (str(gone),)
    ).fetchone()[0] == 0
    # keep.md untouched
    assert conn.execute(
        "SELECT COUNT(*) FROM indexed_files WHERE file_path = ?", (str(keep),)
    ).fetchone()[0] == 1


def test_prune_missing_keeps_all_present(db_and_docs):
    conn, tmp = db_and_docs

    a = tmp / "a.md"
    b = tmp / "b.md"
    make_doc(a)
    make_doc(b)
    ri.index_file(conn, str(a), "books", ri.chunk_markdown, "key")
    ri.index_file(conn, str(b), "books", ri.chunk_markdown, "key")
    chunks_before = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    files_pruned, chunks_pruned = ri.prune_missing(conn, [str(a), str(b)])

    assert files_pruned == 0
    assert chunks_pruned == 0
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == chunks_before


def test_prune_missing_relative_path_matches_absolute(db_and_docs):
    """A recorded path is normalized to absolute before comparison."""
    conn, tmp = db_and_docs

    p = tmp / "rel.md"
    make_doc(p)
    ri.index_file(conn, str(p), "books", ri.chunk_markdown, "key")

    # Record the path as its relative form (resolves to the same file).
    rel = os.path.relpath(str(p))
    conn.execute("UPDATE indexed_files SET file_path = ? WHERE file_path = ?",
                 (rel, str(p)))
    conn.commit()

    files_pruned, chunks_pruned = ri.prune_missing(conn, [str(p)])
    assert files_pruned == 0
    assert chunks_pruned == 0


def test_vacuum_runs_via_main(tmp_path, monkeypatch, capsys):
    """--vacuum runs end-to-end through main() (empty library, no API calls)."""
    monkeypatch.setattr(ri, "LIBRARY_ROOT", tmp_path)
    db_path = tmp_path / "db.sqlite"
    monkeypatch.setattr(ri, "DB_PATH", db_path)
    monkeypatch.setattr(sys, "argv", ["rag_index.py", "--vacuum", "--dry-run"])

    ri.main()

    out = capsys.readouterr().out
    assert "VACUUM" in out
    assert db_path.exists()


def test_prune_missing_flag_runs_via_main(tmp_path, monkeypatch, capsys):
    """--prune-missing + --vacuum run together through main().

    Library contains keep.md only; DB has an orphaned record for gone.md
    (simulated by writing the record directly). Prune must remove it.
    """
    conn = sqlite3.connect(str(tmp_path / "db.sqlite"))
    ri.init_db(conn, rebuild=True)

    # discover_files() only scans files inside top-level source-type dirs.
    books = tmp_path / "books"
    books.mkdir()
    keep = books / "keep.md"
    make_doc(keep)
    dim = ri.EMBEDDING_DIMS
    monkeypatch.setattr(ri, "get_embeddings", fake_embeddings_ok(dim))
    ri.index_file(conn, str(keep), "books", ri.chunk_markdown, "key")

    # Orphan record: gone.md is in indexed_files but no longer on disk.
    conn.execute(
        "INSERT INTO indexed_files (file_path, file_hash, chunk_count, indexed_at) "
        "VALUES (?, 'deadbeef', 5, '2026-01-01')", (str(tmp_path / "gone.md"),))
    conn.commit()
    conn.close()

    monkeypatch.setattr(ri, "LIBRARY_ROOT", tmp_path)
    monkeypatch.setattr(ri, "DB_PATH", tmp_path / "db.sqlite")
    monkeypatch.setattr(sys, "argv",
                        ["rag_index.py", "--prune-missing", "--vacuum", "--dry-run"])

    ri.main()

    out = capsys.readouterr().out
    assert "Files pruned:  1" in out
    assert "VACUUM" in out

    conn = sqlite3.connect(str(tmp_path / "db.sqlite"))
    assert conn.execute(
        "SELECT COUNT(*) FROM indexed_files WHERE file_path LIKE '%gone.md'"
    ).fetchone()[0] == 0
    conn.close()
