from pathlib import Path

import rag_index as ri


def test_parse_frontmatter():
    meta, body = ri.parse_frontmatter("---\nauthor: Jane\nbook: B\n---\n\nBody here.")
    assert meta["author"] == "Jane"
    assert meta["book"] == "B"
    assert body == "Body here."


def test_parse_frontmatter_none():
    meta, body = ri.parse_frontmatter("no frontmatter at all")
    assert meta == {}
    assert body == "no frontmatter at all"


def test_parse_frontmatter_yaml_handles_quoted_colon_and_types():
    text = ('---\n'
            'title: "A Book: A Subtitle"\n'
            "year: '2024'\n"
            'chapter: 1\n'
            '---\n\nBody text')
    meta, body = ri.parse_frontmatter(text)
    assert meta["title"] == "A Book: A Subtitle"   # colon inside quoted value preserved
    assert meta["year"] == "2024"
    assert meta["chapter"] == "1"                   # int coerced to str for citations
    assert body == "Body text"


def test_parse_frontmatter_malformed_yaml_falls_back():
    # Unparseable YAML should not raise — return empty meta + body.
    text = "---\ntitle: : : oops\n  - broken\n---\n\nBody"
    meta, body = ri.parse_frontmatter(text)
    assert isinstance(meta, dict)
    assert body == "Body"


def test_clean_for_embedding_strips_markers():
    raw = ("**bold** and *italic* and [link](http://x) <br> "
           "**[Table 3]** <!-- Page 12 -->\n# Heading")
    out = ri.clean_for_embedding(raw)
    assert "**" not in out
    assert "Table 3" not in out
    assert "Page 12" not in out
    for kept in ("bold", "italic", "link", "Heading"):
        assert kept in out


def test_split_long_text_short_passthrough():
    assert ri.split_long_text("short text", max_chars=1000) == ["short text"]


def test_split_long_text_splits_and_bounds_size():
    text = "This is a sentence. " * 200
    chunks = ri.split_long_text(text, max_chars=200)
    assert len(chunks) > 1
    # nothing wildly larger than the target (overlap + a sentence of slack)
    assert all(len(c) <= 400 for c in chunks)
    # reassembled content preserves the words
    assert "sentence" in chunks[0]


def test_merge_tiny_chunks_folds_into_previous():
    chunks = [
        {"chunk_text": "x" * 300, "chunk_index": 0},
        {"chunk_text": "y" * 10, "chunk_index": 1},
    ]
    merged = ri.merge_tiny_chunks(chunks, min_chars=200)
    assert len(merged) == 1
    assert "y" * 10 in merged[0]["chunk_text"]
    assert merged[0]["chunk_index"] == 0


def test_chunk_markdown_splits_by_heading(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(
        "---\nbook: MyBook\nchapter: 1\n---\n\n"
        "## Section One\n\n" + ("Alpha beta gamma. " * 40) + "\n\n"
        "## Section Two\n\n" + ("Delta epsilon zeta. " * 40)
    )
    chunks = ri.chunk_markdown(str(p), source_type="books")
    assert chunks
    titles = {c["section_title"] for c in chunks}
    assert "Section One" in titles
    assert "Section Two" in titles
    assert all(c["book"] == "MyBook" for c in chunks)
    assert all(c["source_type"] == "books" for c in chunks)


def test_chunk_markdown_subsection_inherits_parent_heading(tmp_path):
    p = tmp_path / "doc.md"
    p.write_text(
        "---\nbook: MyBook\n---\n\n"
        "## Parent Section\n\n" + ("Parent body text here. " * 30) + "\n\n"
        "### Child Subsection\n\n" + ("Child body text here. " * 30) + "\n\n"
        "## Another Section\n\n" + ("More body text here. " * 30)
    )
    chunks = ri.chunk_markdown(str(p), source_type="books")
    titles = {c["section_title"] for c in chunks}
    # level-2 headings stand alone; the ### subsection carries its parent as a breadcrumb
    assert "Parent Section" in titles
    assert "Parent Section — Child Subsection" in titles
    assert "Another Section" in titles
    # the bare subsection name should NOT appear on its own
    assert "Child Subsection" not in titles


def test_chunk_plain_text(tmp_path):
    p = tmp_path / "doc.txt"
    p.write_text(("Para one sentence. " * 30) + "\n\n" + ("Para two sentence. " * 30))
    chunks = ri.chunk_plain_text(str(p), source_type="notes")
    assert chunks
    assert all(c["source_type"] == "notes" for c in chunks)
    assert all(c["source_book"] == "doc" for c in chunks)


def test_discover_files_uses_top_level_dir_as_source_type(tmp_path, monkeypatch):
    monkeypatch.setattr(ri, "LIBRARY_ROOT", tmp_path)
    (tmp_path / "books" / "markdown" / "b" / "chapters").mkdir(parents=True)
    (tmp_path / "books" / "markdown" / "b" / "chapters" / "c1.md").write_text(
        "---\nbook: B\n---\n\n## H\n\nsome body text that is long enough")
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "n.txt").write_text("hello world content")

    found = ri.discover_files()
    types = {st for _, st, _ in found}
    assert types == {"books", "notes"}
    names = {Path(f).name for f, _, _ in found}
    assert {"c1.md", "n.txt"} <= names
    # markdown -> chunk_markdown, txt -> chunk_plain_text
    by_name = {Path(f).name: chunker.__name__ for f, _, chunker in found}
    assert by_name["c1.md"] == "chunk_markdown"
    assert by_name["n.txt"] == "chunk_plain_text"
