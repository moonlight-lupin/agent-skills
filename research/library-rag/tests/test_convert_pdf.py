import pytest

import convert_pdf_library as cv
import rag_index as ri


# ─── Pure rendering logic (no pdfplumber needed) ───────────────────────────────

def test_render_table():
    out = cv.render_table([["a", "b"], ["c", None]], 1)
    assert out.splitlines()[0] == "**[Table 1]**"
    assert "a | b<br>" in out
    assert "c | <br>" in out  # None cell becomes empty


def test_render_page_markdown_has_heading_text_and_table():
    md = cv.render_page_markdown(3, "Some narrative text.", [[["x", "y"]]])
    assert md.startswith("## Page 3")
    assert "Some narrative text." in md
    assert "**[Table 1]**" in md
    assert "x | y<br>" in md


def test_render_page_markdown_no_tables():
    md = cv.render_page_markdown(1, "Only text.", [])
    assert "## Page 1" in md
    assert "Table" not in md


# ─── clean_for_embedding drops the display-only table block ─────────────────────

def test_clean_for_embedding_removes_table_block_keeps_narrative():
    chunk = (
        "## Page 2\n\n"
        "Revenue grew because of strong sales.\n\n"
        "**[Table 1]**\n"
        "Region | Sales<br>\n"
        "West | 1000<br>"
    )
    cleaned = ri.clean_for_embedding(chunk)
    # narrative survives
    assert "Revenue grew because of strong sales." in cleaned
    # structured table block is gone from embedding input
    assert "[Table 1]" not in cleaned
    assert "Region | Sales" not in cleaned
    assert "<br>" not in cleaned


# ─── PDF markdown flows through chunk_markdown with per-page citations ──────────

def test_pdf_markdown_yields_page_citations_and_keeps_table_for_display(tmp_path):
    body = "\n\n".join(
        cv.render_page_markdown(i, f"Narrative for page {i}. " * 20,
                                [[["Col", "Val"], ["a", str(i)]]] if i == 1 else [])
        for i in range(1, 3)
    )
    p = tmp_path / "doc.md"
    p.write_text(f"---\nbook: Doc\n---\n\n# Doc\n\n{body}")

    chunks = ri.chunk_markdown(str(p), source_type="pdfs")
    titles = {c["section_title"] for c in chunks}
    assert "Page 1" in titles
    assert "Page 2" in titles

    page1 = next(c for c in chunks if c["section_title"] == "Page 1")
    # stored chunk keeps the table for display ...
    assert "**[Table 1]**" in page1["chunk_text"]
    # ... but the embedding input drops it
    assert "[Table 1]" not in ri.clean_for_embedding(page1["chunk_text"])


# ─── End-to-end conversion (needs pdfplumber + reportlab; runs in CI) ──────────

def test_convert_pdf_end_to_end(tmp_path):
    # Skip if PDF libs can't be imported in this environment. Use a broad except:
    # a broken native dependency can raise more than ImportError (importorskip
    # only catches ImportError), so guard against any import-time failure.
    try:
        import pdfplumber  # noqa: F401
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
    except BaseException as e:  # noqa: BLE001  pragma: no cover - environment dependent
        # Broad on purpose: a broken native dep (e.g. cffi/cryptography) can raise
        # a pyo3 PanicException, which subclasses BaseException, not Exception.
        pytest.skip(f"PDF libraries unavailable: {e}")

    pdf_path = tmp_path / "doc.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    for n in range(1, 3):
        c.drawString(72, 720, f"This is page {n} of the document.")
        c.showPage()
    c.save()

    md_root = tmp_path / "lib" / "markdown"
    staging = tmp_path / "staging"
    res = cv.convert_pdf(str(pdf_path), "my-doc", title="Doc", author="A",
                         year="2024", md_root=md_root, staging_dir=staging)

    assert res["pages"] == 2
    md_file = md_root / "my-doc" / "my-doc.md"
    assert md_file.exists()
    text = md_file.read_text()
    assert "## Page 1" in text
    assert "## Page 2" in text
    # raw + text staged outside the markdown root
    assert (staging / "raw" / "doc.pdf").exists()
    assert list((staging / "text").glob("*.txt"))
