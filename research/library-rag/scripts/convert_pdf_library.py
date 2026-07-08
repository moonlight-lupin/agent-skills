#!/usr/bin/env python3
"""Convert PDF files into structured Markdown for the RAG library.

PDFs are the format where tables matter, so this path preserves them: each page
becomes a `## Page N` section (giving per-page citations through the normal
markdown chunker), and tables are rendered as `**[Table N]**` blocks with rows
ending in `<br>`. The table *content* is dropped from the embedding input by
`clean_for_embedding` (the page's narrative text already carries it linearly, so
it stays searchable) while the structured block is kept for display.

All the rendering/cleaning logic lives in pure functions (`render_table`,
`render_page_markdown`) so it is testable without pdfplumber; only
`extract_pdf_pages` touches pdfplumber.

Usage (CLI):
    python3 convert_pdf_library.py \
        --pdf /path/to/doc.pdf --slug my-doc \
        --title "Doc Title" --author "Author" --year 2024 \
        --md-root ~/.hermes/library/books/markdown

Usage (Python):
    from convert_pdf_library import convert_pdf
    convert_pdf("doc.pdf", "my-doc", title="...", author="...")

Prerequisites:
    pip install pdfplumber pyyaml
"""

import json
import shutil
import argparse
from pathlib import Path

import yaml

from convert_epub_library import fix_yaml_title_leaks, BOOKS_DIR, MD_DIR

__all__ = ["render_table", "render_page_markdown", "extract_pdf_pages", "convert_pdf"]


def render_table(table, index) -> str:
    """Render an extracted table (list of rows of cell strings) as a display block.

    Marked with ``**[Table N]**`` and rows ending in ``<br>`` so that
    ``clean_for_embedding`` can drop the block from embedding input while the
    structured form is preserved in the stored chunk text.
    """
    lines = [f"**[Table {index}]**"]
    for row in table:
        cells = [("" if c is None else str(c)).replace("\n", " ").strip() for c in row]
        lines.append(" | ".join(cells) + "<br>")
    return "\n".join(lines)


def render_page_markdown(page_number, text, tables) -> str:
    """Render one PDF page as a ``## Page N`` markdown section with any tables."""
    parts = [f"## Page {page_number}", ""]
    if text and text.strip():
        parts.append(text.strip())
    for i, table in enumerate(tables or [], start=1):
        if not table:
            continue
        parts.append("")
        parts.append(render_table(table, i))
    return "\n".join(parts).rstrip()


def extract_pdf_pages(pdf_path):
    """Return a list of ``(text, tables)`` per page. I/O edge — needs pdfplumber."""
    import pdfplumber

    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            pages.append((page.extract_text() or "", page.extract_tables() or []))
    return pages


def convert_pdf(pdf_path, book_slug, title, author, year="",
                md_root=None, staging_dir=None) -> dict:
    """Convert a PDF into a single structured Markdown file (pages as sections).

    Stages the raw PDF + extracted text under ``staging_dir`` (outside
    ``LIBRARY_ROOT``) and writes the markdown to ``md_root/<book_slug>/`` so only
    the structured markdown is indexed. Returns a summary dict.
    """
    pdf_path = Path(pdf_path)
    staging_dir = Path(staging_dir) if staging_dir else BOOKS_DIR
    md_root = Path(md_root) if md_root else MD_DIR

    pages = extract_pdf_pages(str(pdf_path))
    body = "\n\n".join(
        render_page_markdown(i, text, tables) for i, (text, tables) in enumerate(pages, start=1)
    )

    # Stage extracted text + raw PDF (outside the indexed markdown root)
    text_dir = staging_dir / "text"
    text_dir.mkdir(parents=True, exist_ok=True)
    suffix = f" ({year})" if year else ""
    txt_path = text_dir / f"{title} - {author}{suffix}.txt"
    txt_path.write_text(body, encoding="utf-8")

    raw_dir = staging_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / pdf_path.name
    shutil.copy2(pdf_path, raw_path)

    # Write the structured markdown
    md_dir = md_root / book_slug
    md_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = {
        "title": title,
        "author": author,
        "year": year,
        "book": title,
        "source": pdf_path.name,
    }
    frontmatter = {k: v for k, v in frontmatter.items() if v not in (None, "")}

    md_path = md_dir / f"{book_slug}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False))
        f.write("---\n\n")
        f.write(f"# {title}\n\n")
        f.write(body)
        f.write("\n")

    yaml_fixes = fix_yaml_title_leaks(md_dir)

    return {
        "markdown_dir": str(md_dir),
        "markdown_file": str(md_path),
        "pages": len(pages),
        "text_path": str(txt_path),
        "raw_path": str(raw_path),
        "yaml_fixes": yaml_fixes,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Convert a PDF into structured Markdown (pages + tables).")
    parser.add_argument("--pdf", required=True, help="Path to the .pdf file")
    parser.add_argument("--slug", required=True, help="Document directory slug")
    parser.add_argument("--title", required=True, help="Document title")
    parser.add_argument("--author", required=True, help="Author name")
    parser.add_argument("--year", default="", help="Publication year")
    parser.add_argument("--md-root", default=None,
                        help="Markdown output root (default: $BOOKS_DIR/markdown). "
                             "Point this under LIBRARY_ROOT to make it indexable.")
    parser.add_argument("--staging-dir", default=None,
                        help="Where the raw PDF + extracted text are stored "
                             "(default: $BOOKS_DIR). Keep this outside LIBRARY_ROOT.")
    args = parser.parse_args()

    result = convert_pdf(
        args.pdf, args.slug, title=args.title, author=args.author,
        year=args.year, md_root=args.md_root, staging_dir=args.staging_dir,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
