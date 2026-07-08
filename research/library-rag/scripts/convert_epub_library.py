#!/usr/bin/env python3
"""Convert EPUB files into a structured Markdown library.

Extracts text from an EPUB, splits it into per-chapter Markdown files with YAML
frontmatter, and stages the raw EPUB + extracted text alongside. This is the
single conversion implementation used by both the CLI and the MCP server's
`add_book` tool.

Usage (CLI):
    python3 convert_epub_library.py \
        --epub /path/to/book.epub --slug my-book \
        --title "Book Title" --author "Author Name" --year 2024

    # Make the output indexable by writing markdown under the library root:
    python3 convert_epub_library.py --epub book.epub --slug my-book \
        --title "..." --author "..." \
        --md-root ~/.hermes/library/books/markdown

Usage (Python):
    from convert_epub_library import convert_epub
    convert_epub("book.epub", "my-book", title="...", author="...", year="2024")

Prerequisites:
    pip install ebooklib beautifulsoup4 pyyaml   # (--break-system-packages if needed)

See references/epub-conversion.md for pitfalls and design notes.
"""

import os
import re
import json
import shutil
import argparse
from pathlib import Path

import yaml

# ──────────────────────────────────────────
# Configuration — directories (overridable via env / CLI)
# ──────────────────────────────────────────

BOOKS_DIR = Path(os.environ.get("BOOKS_DIR", Path.home() / ".hermes" / "book"))
TEXT_DIR = BOOKS_DIR / "text"
MD_DIR = BOOKS_DIR / "markdown"
RAW_DIR = BOOKS_DIR / "raw"


def slugify(text: str, max_len: int = 60) -> str:
    """Create filesystem-safe slug from text, truncated to max_len."""
    text = text.lower().strip()
    text = re.sub(r"[—––]+", "-", text)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    text = re.sub(r"-+", "-", text)
    text = text[:max_len].rstrip("-")
    return text


def extract_epub_to_text(epub_path: str, output_path: str) -> int:
    """Extract full text from EPUB, save as .txt, return char count."""
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup

    book = epub.read_epub(epub_path, options={"ignore_ncx": True})
    chunks = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text(separator="\n", strip=True)
        if text.strip():
            chunks.append(text)
    full_text = "\n\n".join(chunks)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    return len(full_text)


_MONTHS = {"january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"}

# Chapter heading styles, tried in priority order. Books from different families
# use different conventions, so we pick the FIRST style that confidently matches
# this document rather than forcing one regex on every book. Each captures
# (label, title).
_CHAPTER_PATTERNS = [
    # "CHAPTER 12" / "Chapter 12" with the title on the next line
    re.compile(r'^(?:CHAPTER|Chapter)\s+(\d{1,3})\b[^\n]*\n([^\n]+)', re.MULTILINE),
    # "CHAPTER One" / "Chapter Twelve" (word numbers)
    re.compile(r'^(?:CHAPTER|Chapter)\s+([A-Z][a-z]+)\b[^\n]*\n([^\n]+)', re.MULTILINE),
    # "PART I" / "Part IV" (roman numerals)
    re.compile(r'^(?:PART|Part)\s+([IVXLC]+)\b[^\n]*\n([^\n]+)', re.MULTILINE),
    # "12. Title" — number, period, title on the same line
    re.compile(r'^(\d{1,3})\.\s+([^\n]+)', re.MULTILINE),
    # bare "12\nTitle" — most false-positive-prone; kept only behind the guard
    re.compile(r'^(\d{1,3})\s*\n([^\n]+)', re.MULTILINE),
]


def _looks_like_false_anchor(title: str) -> bool:
    """Reject candidate chapter titles that are really dates or page-number noise.

    A wrong anchor is worse than a missing one: a bare "1\\nJanuary 2026" or a
    standalone page number followed by a running header must not mint a chapter.
    """
    t = title.strip().lower()
    if not t:
        return True
    first = re.split(r"[\s,]+", t)[0]
    if first in _MONTHS:                 # "January 2026", date continuations
        return True
    if t.replace(" ", "").isdigit():     # title is just a number (page noise)
        return True
    return False


def _detect_chapter_markers(full_text: str) -> list:
    """Return the regex matches for the first heading style that confidently
    applies to this document (> 3 guard-passing matches), or [] if none do."""
    for pattern in _CHAPTER_PATTERNS:
        matches = [m for m in pattern.finditer(full_text)
                   if not _looks_like_false_anchor(m.group(2))]
        if len(matches) > 3:
            return matches
    return []


def audit_chapter_markers(full_text: str) -> list:
    """List the detected chapter markers as (label, title) for eyeballing.

    Before trusting a conversion, print this and confirm every entry is a real
    chapter — not a date, page number, or prose line the pattern grabbed.
    """
    return [(m.group(1), m.group(2).strip()) for m in _detect_chapter_markers(full_text)]


def split_into_chapters(full_text: str) -> list:
    """Split extracted book text into chapter dicts.

    Detects the heading style (CHAPTER N / CHAPTER One / PART I / "N. Title" /
    bare "N\\nTitle") and guards against date/page-number false positives.
    Returns a list of {num, title, slug, content}, or [] when no clear chapter
    structure is found (≤3 matches → treat the book as a single document).
    """
    matches = _detect_chapter_markers(full_text)
    if len(matches) <= 3:
        return []

    chapters = []
    n = len(matches)
    for i, m in enumerate(matches):
        label = m.group(1)
        num = int(label) if label.isdigit() else label
        title = m.group(2).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < n else len(full_text)
        content = full_text[start:end].strip()
        # Sequential ordinal drives the filename prefix so word/roman labels
        # ("One", "IV") still produce clean ch01-, ch02- slugs.
        chapters.append({
            "num": num,
            "title": title,
            "slug": f"ch{i + 1:02d}-{slugify(title)}",
            "content": content,
        })
    return chapters


def write_chapter_md(book_slug: str, chapter: dict, config: dict,
                     part_name: str = None, md_dir: Path = None) -> str:
    """Write a single chapter as a Markdown file with YAML frontmatter."""
    if md_dir is None:
        md_dir = MD_DIR / book_slug / "chapters"
    md_dir = Path(md_dir)
    md_dir.mkdir(parents=True, exist_ok=True)

    frontmatter = {
        "title": chapter["title"],
        "author": config.get("author"),
        "year": config.get("year"),
        "edition": config.get("edition"),
        "book": config.get("title"),
        "chapter": chapter.get("num"),
        "part": part_name,
        "slug": chapter["slug"],
        "source": config.get("source_file"),
    }
    # Drop empty/None fields so frontmatter stays clean
    frontmatter = {k: v for k, v in frontmatter.items() if v not in (None, "")}

    max_slug = 80
    if len(chapter["slug"]) > max_slug:
        prefix = chapter["slug"][:max_slug - 4]
        chapter["slug"] = prefix.rstrip("-") + "-etc"

    filepath = md_dir / f"{chapter['slug']}.md"
    body = chapter["content"]

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("---\n")
        f.write(yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False))
        f.write("---\n\n")
        f.write(f"# {chapter['title']}\n\n")
        f.write(body)
        f.write("\n")

    return filepath.name


# ──────────────────────────────────────────
# Post-processing: fix YAML title leaks
# ──────────────────────────────────────────

def fix_yaml_title_leaks(md_dir: Path) -> int:
    """Remove indented continuation lines that leaked into YAML frontmatter.

    Pattern: line between 'title: ...' and the next top-level key that starts
    with '  '. These are subtitle fragments from EPUB headings that don't belong
    in YAML.
    """
    md_dir = Path(md_dir)
    fixed = 0
    for fpath in sorted(md_dir.glob("*.md")):
        with open(fpath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        title_idx = next_key_idx = None
        for i, line in enumerate(lines):
            if line.startswith("title:"):
                title_idx = i
            elif title_idx is not None and re.match(r"^\w+:", line):
                next_key_idx = i
                break
        if title_idx is None or next_key_idx is None:
            continue
        to_remove = [i for i in range(title_idx + 1, next_key_idx)
                     if lines[i].startswith("  ")]
        if to_remove:
            for i in reversed(to_remove):
                del lines[i]
            with open(fpath, "w", encoding="utf-8") as f:
                f.writelines(lines)
            fixed += 1
    return fixed


# ──────────────────────────────────────────
# Top-level conversion
# ──────────────────────────────────────────

def convert_epub(epub_path, book_slug, title, author, year="",
                 md_root=None, staging_dir=None) -> dict:
    """Convert an EPUB into structured per-chapter Markdown.

    Writes:
      - the raw EPUB copy + extracted .txt under ``staging_dir`` (NOT indexed)
      - per-chapter .md with YAML frontmatter under ``md_root/<book_slug>/chapters/``

    Keep ``staging_dir`` outside your LIBRARY_ROOT and point ``md_root`` inside it
    so only the structured markdown gets indexed (avoids double-indexing the raw
    text). Returns a summary dict.
    """
    epub_path = Path(epub_path)
    staging_dir = Path(staging_dir) if staging_dir else BOOKS_DIR
    md_root = Path(md_root) if md_root else MD_DIR

    text_dir = staging_dir / "text"
    raw_dir = staging_dir / "raw"

    # 1. Extract text → staging
    suffix = f" ({year})" if year else ""
    txt_path = text_dir / f"{title} - {author}{suffix}.txt"
    extract_epub_to_text(str(epub_path), str(txt_path))
    full_text = txt_path.read_text(encoding="utf-8")

    # 2. Stage the raw EPUB
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / epub_path.name
    shutil.copy2(epub_path, raw_path)

    # 3. Split into chapters and write structured markdown
    md_dir = md_root / book_slug / "chapters"
    md_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "author": author,
        "year": year,
        "title": title,
        "source_file": epub_path.name,
    }

    chapters = split_into_chapters(full_text)
    if chapters:
        for ch in chapters:
            write_chapter_md(book_slug, ch, config, md_dir=md_dir)
    else:
        write_chapter_md(book_slug, {
            "num": None, "title": title, "slug": "full-text", "content": full_text,
        }, config, md_dir=md_dir)

    # 4. Post-process: drop subtitle leaks from frontmatter
    yaml_fixes = fix_yaml_title_leaks(md_dir)

    return {
        "markdown_dir": str(md_dir),
        "chapters": len(list(md_dir.glob("*.md"))),
        "text_path": str(txt_path),
        "raw_path": str(raw_path),
        "yaml_fixes": yaml_fixes,
    }


# ──────────────────────────────────────────
# CLI
# ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert an EPUB into structured Markdown chapters.")
    parser.add_argument("--epub", required=True, help="Path to the .epub file")
    parser.add_argument("--slug", required=True, help="Book directory slug (e.g. my-book)")
    parser.add_argument("--title", required=True, help="Book title")
    parser.add_argument("--author", required=True, help="Author name")
    parser.add_argument("--year", default="", help="Publication year")
    parser.add_argument("--md-root", default=None,
                        help="Markdown output root (default: $BOOKS_DIR/markdown). "
                             "Point this under LIBRARY_ROOT to make it indexable.")
    parser.add_argument("--staging-dir", default=None,
                        help="Where the raw EPUB + extracted text are stored "
                             "(default: $BOOKS_DIR). Keep this outside LIBRARY_ROOT.")
    args = parser.parse_args()

    result = convert_epub(
        args.epub, args.slug, title=args.title, author=args.author,
        year=args.year, md_root=args.md_root, staging_dir=args.staging_dir,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
