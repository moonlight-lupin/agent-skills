#!/usr/bin/env python3
"""parse_reference.py — Resolve structured references to exact passages.

Supports two reference formats:
  1. Book verses: "John 3:16", "Genesis 5", "1 John 3:1-3", "1-John 3:16"
  2. Generic chapter/section: "Ch 12", "Chapter 12", "§3.2", "Section 3.2"

Optional alias tables: place a JSON file next to this script (or pass
--aliases) to map short names to canonical headings in your source file.
For example, bible-book-names.json maps "psalm" → "Psalms", "rom" → "Romans",
etc. Without an alias file, book names are title-cased only.

Usage:
  python3 parse_reference.py "John 3:16" --source /path/to/bible.md
  python3 parse_reference.py "Genesis 5" --source /path/to/bible.md
  python3 parse_reference.py "Ch 12" --source /path/to/book.md
  python3 parse_reference.py "John 3:16" --source /path/to/bible.md --aliases bible-book-names.json

Can also be imported:
  from parse_reference import parse_bible_ref, extract_verses, lookup_passage
"""

from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

# ─── Alias table loading (optional) ─────────────────────────────────────────

_ALIASES: dict[str, str] = {}


def load_aliases(path: str | Path | None = None):
    """Load a JSON alias file mapping short names → canonical names.

    The file should be a JSON object: {"psalm": "Psalms", "rom": "Romans", ...}
    Keys are matched case-insensitively. Call this before parsing references.

    If no path is given, looks for 'bible-book-names.json' next to this script.
    Does nothing if the file doesn't exist (graceful no-op).
    """
    global _ALIASES
    if path is None:
        path = Path(__file__).parent / "bible-book-names.json"
    path = Path(path)
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _ALIASES = {k.lower(): v for k, v in data.items()}
    except (json.JSONDecodeError, OSError):
        pass


# Auto-load on import if the default file exists
load_aliases()


# ─── Book name normalization ─────────────────────────────────────────────────

def normalize_book_name(name: str) -> str:
    """Normalize a book name: fix case, hyphens, spaces, and resolve aliases."""
    name = name.strip()
    name = re.sub(r'(\d)-(\D)', r'\1 \2', name)
    lower = name.lower()
    if lower in _ALIASES:
        return _ALIASES[lower]
    return ' '.join(w.capitalize() if not w[0].isdigit() else w for w in name.split())


# ─── Bible reference parsing ─────────────────────────────────────────────────

_BIBLE_REF_RE = re.compile(
    r'^\s*'
    r'(?P<book>(?:[1-3]\s*[-]?\s*)?[A-Za-z]+(?:\s+[A-Za-z]+)?)'
    r'\s+'
    r'(?P<chapter>\d+)'
    r'(?:\s*:\s*(?P<vstart>\d+)'
    r'(?:\s*[-\u2013]\s*(?P<vend>\d+))?)?'
    r'\s*$'
)


def parse_bible_ref(ref: str) -> dict | None:
    """Parse a Bible reference string into structured components.

    Examples:
      "John 3:16"     → {"book": "John", "chapter": 3, "verse_start": 16, "verse_end": 16}
      "John 3:16-18"  → {"book": "John", "chapter": 3, "verse_start": 16, "verse_end": 18}
      "Genesis 5"     → {"book": "Genesis", "chapter": 5, "verse_start": None, "verse_end": None}
      "1 John 3:1-3"  → {"book": "1 John", "chapter": 3, "verse_start": 1, "verse_end": 3}

    Returns None if the string is not a valid Bible reference.
    """
    if not ref or not ref.strip():
        return None
    m = _BIBLE_REF_RE.match(ref)
    if not m:
        return None
    book = normalize_book_name(m.group("book"))
    chapter = int(m.group("chapter"))
    vstart = int(m.group("vstart")) if m.group("vstart") else None
    vend = int(m.group("vend")) if m.group("vend") else vstart
    return {
        "book": book,
        "chapter": chapter,
        "verse_start": vstart,
        "verse_end": vend,
    }


# ─── Verse extraction from markdown ──────────────────────────────────────────

_VERSE_RE = re.compile(r'^\*\*(\d+)\*\*\s*(.*)')


def extract_verses(md_path: Path, book: str, chapter: int,
                   verse_start: int | None, verse_end: int | None) -> str | None:
    """Extract verses from a markdown Bible file.

    The file must use the format:
      ## BookName
      ### BookName N
      **1** verse text
      **2** verse text

    Returns the verse text (with verse numbers) for the requested range,
    or None if the book/chapter is not found.
    """
    text = Path(md_path).read_text(encoding="utf-8")
    lines = text.split("\n")

    chapter_heading = f"### {book} {chapter}"
    chapter_idx = None
    for i, line in enumerate(lines):
        if line.strip() == chapter_heading:
            chapter_idx = i
            break

    if chapter_idx is None:
        for i, line in enumerate(lines):
            if line.strip().lower() == chapter_heading.lower():
                chapter_idx = i
                break

    if chapter_idx is None:
        return None

    verses = {}
    for line in lines[chapter_idx + 1:]:
        stripped = line.strip()
        if stripped.startswith("### ") or stripped.startswith("## "):
            break
        m = _VERSE_RE.match(stripped)
        if m:
            vnum = int(m.group(1))
            verses[vnum] = m.group(2)

    if not verses:
        return None

    if verse_start is not None:
        selected = {k: v for k, v in verses.items()
                    if verse_start <= k <= (verse_end or verse_start)}
    else:
        selected = verses

    if not selected:
        return None

    lines_out = []
    for vnum in sorted(selected):
        lines_out.append(f"**{vnum}** {selected[vnum]}")
    return "\n".join(lines_out)


# ─── Generic chapter/section parsing ─────────────────────────────────────────

_CHAPTER_REF_RE = re.compile(
    r'^\s*(?:Ch(?:apter)?\.?\s*|\u00a7|Section\s*)(\d+)(?:\.(\d+))?\s*$',
    re.IGNORECASE
)


def parse_chapter_ref(ref: str) -> dict | None:
    """Parse a generic chapter/section reference.

    Examples:
      "Ch 12"       → {"chapter": 12, "section": None}
      "Chapter 12"  → {"chapter": 12, "section": None}
      "§3.2"        → {"chapter": 3, "section": 2}
      "Section 3.2" → {"chapter": 3, "section": 2}

    Returns None if not a valid chapter/section reference.
    """
    if not ref or not ref.strip():
        return None
    m = _CHAPTER_REF_RE.match(ref)
    if not m:
        return None
    chapter = int(m.group(1))
    section = int(m.group(2)) if m.group(2) else None
    return {"chapter": chapter, "section": section}


def extract_chapter(md_path: Path, chapter: int,
                    section: int | None = None) -> str | None:
    """Extract a chapter (and optionally a section) from a markdown file.

    Looks for ## Chapter N or ### Chapter N headings, or ## N. Title patterns.
    For sections, looks for ### N.M or **N.M** patterns within the chapter.
    """
    text = Path(md_path).read_text(encoding="utf-8")
    lines = text.split("\n")

    patterns = [
        rf'^##\s+.*\b{chapter}\b',
        rf'^###\s+.*\b{chapter}\b',
    ]
    chapter_idx = None
    for i, line in enumerate(lines):
        for pat in patterns:
            if re.match(pat, line, re.IGNORECASE):
                chapter_idx = i
                break
        if chapter_idx is not None:
            break

    if chapter_idx is None:
        return None

    collected = []
    for line in lines[chapter_idx:]:
        if line.startswith("## ") and len(collected) > 0:
            break
        collected.append(line)

    if section is not None:
        section_patterns = [
            rf'^###\s+{chapter}\.{section}\b',
            rf'^\*\*{chapter}\.{section}\*\*',
            rf'^###\s+.*\b{chapter}\.{section}\b',
        ]
        section_start = None
        for i, line in enumerate(collected):
            for pat in section_patterns:
                if re.match(pat, line):
                    section_start = i
                    break
            if section_start is not None:
                break

        if section_start is not None:
            section_lines = []
            for line in collected[section_start:]:
                if re.match(r'^###\s+', line) and len(section_lines) > 0:
                    break
                section_lines.append(line)
            return "\n".join(section_lines)

    return "\n".join(collected)


# ─── Unified lookup ──────────────────────────────────────────────────────────

def lookup_passage(ref: str, source_path: str) -> dict:
    """Look up a reference in a source file.

    Tries chapter/section parsing first, then Bible reference parsing.
    Returns a dict with: ref, type, text (or None), error (or None).
    """
    path = Path(source_path)
    if not path.is_file():
        return {"ref": ref, "type": None, "text": None, "error": f"File not found: {source_path}"}

    # Try chapter/section first — "Ch 12" would match Bible ref regex as book="Ch"
    chapter = parse_chapter_ref(ref)
    if chapter:
        text = extract_chapter(path, chapter["chapter"], chapter.get("section"))
        if text:
            return {"ref": ref, "type": "chapter", "parsed": chapter, "text": text, "error": None}
        return {"ref": ref, "type": "chapter", "parsed": chapter, "text": None,
                "error": f"Chapter not found: {chapter['chapter']}"}

    # Try Bible reference
    bible = parse_bible_ref(ref)
    if bible:
        text = extract_verses(path, bible["book"], bible["chapter"],
                              bible["verse_start"], bible["verse_end"])
        if text:
            return {"ref": ref, "type": "bible", "parsed": bible, "text": text, "error": None}
        return {"ref": ref, "type": "bible", "parsed": bible, "text": None,
                "error": f"Passage not found: {bible['book']} {bible['chapter']}"}

    return {"ref": ref, "type": None, "text": None, "error": f"Unrecognized reference format: {ref}"}


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Resolve structured references to exact passages.")
    parser.add_argument("ref", help="Reference (e.g. 'John 3:16', 'Genesis 5', 'Ch 12', '\u00a73.2')")
    parser.add_argument("--source", required=True, help="Path to the markdown source file")
    parser.add_argument("--aliases", default=None,
                        help="JSON file mapping short names to canonical headings (e.g. bible-book-names.json)")
    args = parser.parse_args()

    if args.aliases:
        load_aliases(args.aliases)

    result = lookup_passage(args.ref, args.source)
    if result.get("text"):
        print(result["text"])
    else:
        print(f"Error: {result.get('error', 'unknown')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()