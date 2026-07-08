"""Tests for atomic per-file indexing (index_file): partial-failure rollback
and stale-chunk replacement. No API calls — embeddings are injected."""
import sqlite3

import pytest

import rag_index as ri


def fake_embeddings_ok(dim):
    return lambda texts, key, retries=3: ([[0.1] * dim for _ in texts],
                                          {"prompt_tokens": 1, "cost": 0.0})


def make_doc(path, paras=8):
    body = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(paras))
    path.write_text(f"---\nbook: B\n---\n\n## Heading\n\n{body}")


def test_index_file_rolls_back_on_failure(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite"
    conn = sqlite3.connect(str(db))
    ri.init_db(conn, rebuild=True)

    p = tmp_path / "doc.md"
    make_doc(p)
    monkeypatch.setattr(ri, "BATCH_SIZE", 1)  # force multiple batches
    dim = ri.EMBEDDING_DIMS

    calls = {"n": 0}

    def flaky(texts, key, retries=3):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("simulated API failure")
        return [[0.1] * dim for _ in texts], {"prompt_tokens": 1, "cost": 0.0}

    monkeypatch.setattr(ri, "get_embeddings", flaky)

    with pytest.raises(RuntimeError):
        ri.index_file(conn, str(p), "books", ri.chunk_markdown, "key")

    # Partial chunks rolled back; file NOT recorded as indexed -> retried next run.
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM indexed_files WHERE file_path = ?", (str(p),)
    ).fetchone()[0] == 0


def test_index_file_replaces_stale_chunks(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite"
    conn = sqlite3.connect(str(db))
    ri.init_db(conn, rebuild=True)

    p = tmp_path / "doc.md"
    make_doc(p)
    dim = ri.EMBEDDING_DIMS
    monkeypatch.setattr(ri, "get_embeddings", fake_embeddings_ok(dim))

    stored1, _ = ri.index_file(conn, str(p), "books", ri.chunk_markdown, "key")
    assert stored1 > 0
    count1 = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    # Re-index the same file: chunks must be replaced, not accumulated.
    ri.index_file(conn, str(p), "books", ri.chunk_markdown, "key")
    count2 = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    assert count2 == count1
    # vec rows stay in lockstep with chunk rows
    assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == count2
    assert conn.execute(
        "SELECT chunk_count FROM indexed_files WHERE file_path = ?", (str(p),)
    ).fetchone()[0] == stored1


def test_index_file_preserves_previous_version_on_failure(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite"
    conn = sqlite3.connect(str(db))
    ri.init_db(conn, rebuild=True)
    dim = ri.EMBEDDING_DIMS

    p = tmp_path / "doc.md"
    make_doc(p, paras=8)
    monkeypatch.setattr(ri, "get_embeddings", fake_embeddings_ok(dim))

    # First successful index — the "old good" version.
    stored1, _ = ri.index_file(conn, str(p), "books", ri.chunk_markdown, "key")
    assert stored1 > 0
    count_old = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    first_hash = conn.execute(
        "SELECT file_hash FROM indexed_files WHERE file_path = ?", (str(p),)).fetchone()[0]

    # Change the file (new content + hash), then make the re-index fail mid-way.
    make_doc(p, paras=14)
    monkeypatch.setattr(ri, "BATCH_SIZE", 1)
    calls = {"n": 0}

    def flaky(texts, key, retries=3):
        calls["n"] += 1
        if calls["n"] >= 2:
            raise RuntimeError("simulated API failure")
        return [[0.1] * dim for _ in texts], {"prompt_tokens": 1, "cost": 0.0}

    monkeypatch.setattr(ri, "get_embeddings", flaky)

    with pytest.raises(RuntimeError):
        ri.index_file(conn, str(p), "books", ri.chunk_markdown, "key")

    # Previous version stays fully searchable; no partial new rows linger.
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == count_old
    assert conn.execute("SELECT COUNT(*) FROM vec_chunks").fetchone()[0] == count_old
    # indexed_files still points at the OLD hash, so the next run detects the change and retries.
    assert conn.execute(
        "SELECT file_hash FROM indexed_files WHERE file_path = ?", (str(p),)
    ).fetchone()[0] == first_hash


def test_index_file_empty_returns_zero(tmp_path, monkeypatch):
    db = tmp_path / "db.sqlite"
    conn = sqlite3.connect(str(db))
    ri.init_db(conn, rebuild=True)
    p = tmp_path / "empty.txt"
    p.write_text("")  # no chunks
    monkeypatch.setattr(ri, "get_embeddings", fake_embeddings_ok(ri.EMBEDDING_DIMS))

    stored, usage = ri.index_file(conn, str(p), "notes", ri.chunk_plain_text, "key")
    assert stored == 0
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
