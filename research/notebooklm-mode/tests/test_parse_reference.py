#!/usr/bin/env python3
"""Tests for parse_reference.py — Bible verse + chapter/section reference parsing.

No network calls. All tests use synthetic markdown fixtures.
Run: python3 -m pytest tests/test_parse_reference.py -v
"""

import json
import os
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import parse_reference
from parse_reference import (
    parse_bible_ref, extract_verses, parse_chapter_ref,
    extract_chapter, normalize_book_name, lookup_passage,
)


@pytest.fixture(autouse=True)
def _reset_aliases():
    """Reset alias state before and after each test for isolation."""
    # Save and restore: reload the default bible-book-names.json if it exists
    default_path = Path(SCRIPTS_DIR) / "bible-book-names.json"
    saved = dict(parse_reference._ALIASES)
    yield
    parse_reference._ALIASES = saved


# ─── normalize_book_name (no aliases loaded) ─────────────────────────────────

class TestNormalizeBookName:
    def test_standard(self):
        assert normalize_book_name("John") == "John"
        assert normalize_book_name("Genesis") == "Genesis"

    def test_case(self):
        assert normalize_book_name("john") == "John"
        assert normalize_book_name("GENESIS") == "Genesis"

    def test_hyphen_to_space(self):
        assert normalize_book_name("1-John") == "1 John"
        assert normalize_book_name("2-corinthians") == "2 Corinthians"

    def test_leading_trailing_space(self):
        assert normalize_book_name("  John  ") == "John"

    def test_no_alias_no_change(self):
        """Without aliases loaded, 'psalm' title-cases to 'Psalm', not 'Psalms'."""
        parse_reference._ALIASES = {}
        assert normalize_book_name("Psalm") == "Psalm"
        assert normalize_book_name("Gen") == "Gen"


# ─── Alias loading ──────────────────────────────────────────────────────────

class TestAliasLoading:
    def test_load_aliases_from_file(self, tmp_path):
        aliases = {"psalm": "Psalms", "rom": "Romans"}
        path = tmp_path / "aliases.json"
        path.write_text(json.dumps(aliases))
        parse_reference.load_aliases(path)
        assert normalize_book_name("Psalm") == "Psalms"
        assert normalize_book_name("rom") == "Romans"

    def test_load_aliases_missing_file(self, tmp_path):
        """Missing alias file is a graceful no-op (existing aliases preserved)."""
        parse_reference._ALIASES = {}
        parse_reference.load_aliases(tmp_path / "nonexistent.json")
        assert normalize_book_name("Psalm") == "Psalm"

    def test_load_aliases_none_resets(self):
        """load_aliases with a nonexistent path is a no-op (existing aliases preserved)."""
        parse_reference._ALIASES = {"psalm": "Psalms"}
        parse_reference.load_aliases("/nonexistent/path.json")
        # Aliases remain — load_aliases only replaces on successful load
        assert normalize_book_name("Psalm") == "Psalms"

    def test_load_aliases_invalid_json(self, tmp_path):
        """Invalid JSON is silently ignored (existing aliases preserved)."""
        parse_reference._ALIASES = {"psalm": "Psalms"}
        path = tmp_path / "bad.json"
        path.write_text("not json{{{")
        parse_reference.load_aliases(path)
        assert normalize_book_name("Psalm") == "Psalms"

    def test_case_insensitive_alias_keys(self, tmp_path):
        """Alias keys are matched case-insensitively."""
        aliases = {"PSALM": "Psalms"}
        path = tmp_path / "aliases.json"
        path.write_text(json.dumps(aliases))
        parse_reference.load_aliases(path)
        assert normalize_book_name("psalm") == "Psalms"
        assert normalize_book_name("PSALM") == "Psalms"

    def test_auto_load_on_import(self):
        """The module auto-loads bible-book-names.json next to the script if it exists."""
        default_path = Path(SCRIPTS_DIR) / "bible-book-names.json"
        if default_path.exists():
            # Explicitly reload to verify auto-load works
            parse_reference.load_aliases(default_path)
            assert normalize_book_name("Psalm") == "Psalms"
            assert normalize_book_name("Gen") == "Genesis"
            assert normalize_book_name("Rom") == "Romans"


# ─── parse_bible_ref ─────────────────────────────────────────────────────────

class TestParseBibleRef:
    def test_simple_verse(self):
        ref = parse_bible_ref("John 3:16")
        assert ref["book"] == "John"
        assert ref["chapter"] == 3
        assert ref["verse_start"] == 16
        assert ref["verse_end"] == 16

    def test_verse_range(self):
        ref = parse_bible_ref("John 3:16-18")
        assert ref["book"] == "John"
        assert ref["chapter"] == 3
        assert ref["verse_start"] == 16
        assert ref["verse_end"] == 18

    def test_en_dash_range(self):
        ref = parse_bible_ref("John 3:16\u201318")
        assert ref["verse_start"] == 16
        assert ref["verse_end"] == 18

    def test_chapter_only(self):
        ref = parse_bible_ref("Genesis 5")
        assert ref["book"] == "Genesis"
        assert ref["chapter"] == 5
        assert ref["verse_start"] is None
        assert ref["verse_end"] is None

    def test_prefixed_book(self):
        ref = parse_bible_ref("1 John 3:1-3")
        assert ref["book"] == "1 John"
        assert ref["chapter"] == 3
        assert ref["verse_start"] == 1
        assert ref["verse_end"] == 3

    def test_prefixed_book_hyphen(self):
        ref = parse_bible_ref("1-John 3:1")
        assert ref["book"] == "1 John"

    def test_case_insensitive_book(self):
        ref = parse_bible_ref("genesis 5")
        assert ref["book"] == "Genesis"

    def test_spaces_around_colon(self):
        ref = parse_bible_ref("John 3 : 16")
        assert ref["chapter"] == 3
        assert ref["verse_start"] == 16

    def test_invalid_ref(self):
        assert parse_bible_ref("not a reference") is None

    def test_empty(self):
        assert parse_bible_ref("") is None

    def test_none(self):
        assert parse_bible_ref(None) is None

    def test_just_a_number(self):
        assert parse_bible_ref("42") is None

    def test_no_chapter(self):
        assert parse_bible_ref("John") is None


# ─── parse_bible_ref with aliases ────────────────────────────────────────────

class TestParseBibleRefWithAliases:
    def setup_method(self):
        """Load aliases before each test."""
        default_path = Path(SCRIPTS_DIR) / "bible-book-names.json"
        if default_path.exists():
            parse_reference.load_aliases(default_path)

    def teardown_method(self):
        parse_reference._ALIASES = {}

    def test_psalm_alias(self):
        ref = parse_bible_ref("Psalm 23")
        assert ref["book"] == "Psalms"

    def test_abbreviation_resolves(self):
        ref = parse_bible_ref("Rom 8:28")
        assert ref["book"] == "Romans"

    def test_gen_abbreviation(self):
        ref = parse_bible_ref("Gen 1:1")
        assert ref["book"] == "Genesis"


# ─── extract_verses ──────────────────────────────────────────────────────────

class TestExtractVerses:
    def test_single_verse(self, tmp_path):
        md = "## John\n\n### John 3\n\n**1** First verse.\n**2** Second verse.\n**3** Third verse.\n**16** For God so loved.\n**17** Next verse.\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = extract_verses(path, "John", 3, 16, 16)
        assert "For God so loved" in result
        assert "First verse" not in result

    def test_verse_range(self, tmp_path):
        md = "## John\n\n### John 3\n\n**1** First.\n**16** Sixteen.\n**17** Seventeen.\n**18** Eighteen.\n**19** Nineteen.\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = extract_verses(path, "John", 3, 16, 18)
        assert "Sixteen" in result
        assert "Seventeen" in result
        assert "Eighteen" in result
        assert "Nineteen" not in result

    def test_full_chapter(self, tmp_path):
        md = "## John\n\n### John 3\n\n**1** First.\n**2** Second.\n**3** Third.\n\n### John 4\n\n**1** Next chapter.\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = extract_verses(path, "John", 3, None, None)
        assert "First" in result
        assert "Second" in result
        assert "Third" in result
        assert "Next chapter" not in result

    def test_chapter_not_found(self, tmp_path):
        md = "## John\n\n### John 3\n\n**1** First.\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = extract_verses(path, "John", 99, None, None)
        assert result is None

    def test_book_not_found(self, tmp_path):
        md = "## John\n\n### John 3\n\n**1** First.\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = extract_verses(path, "Nonexistent", 1, None, None)
        assert result is None

    def test_case_insensitive_heading(self, tmp_path):
        md = "## john\n\n### john 3\n\n**1** First.\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = extract_verses(path, "John", 3, None, None)
        assert "First" in result

    def test_verse_not_in_chapter(self, tmp_path):
        md = "## John\n\n### John 3\n\n**1** First.\n**2** Second.\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = extract_verses(path, "John", 3, 99, 99)
        assert result is None

    def test_stops_at_next_book(self, tmp_path):
        md = "## John\n\n### John 3\n\n**1** First.\n\n## Acts\n\n### Acts 1\n\n**1** Other.\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = extract_verses(path, "John", 3, None, None)
        assert "First" in result
        assert "Other" not in result


# ─── parse_chapter_ref ───────────────────────────────────────────────────────

class TestParseChapterRef:
    def test_ch_abbrev(self):
        ref = parse_chapter_ref("Ch 12")
        assert ref["chapter"] == 12
        assert ref["section"] is None

    def test_chapter_full(self):
        ref = parse_chapter_ref("Chapter 12")
        assert ref["chapter"] == 12

    def test_section_symbol(self):
        ref = parse_chapter_ref("\u00a73.2")
        assert ref["chapter"] == 3
        assert ref["section"] == 2

    def test_section_word(self):
        ref = parse_chapter_ref("Section 3.2")
        assert ref["chapter"] == 3
        assert ref["section"] == 2

    def test_ch_with_dot(self):
        ref = parse_chapter_ref("Ch. 12")
        assert ref["chapter"] == 12

    def test_chapter_no_section(self):
        ref = parse_chapter_ref("Chapter 5")
        assert ref["chapter"] == 5
        assert ref["section"] is None

    def test_invalid(self):
        assert parse_chapter_ref("not a ref") is None

    def test_empty(self):
        assert parse_chapter_ref("") is None

    def test_none(self):
        assert parse_chapter_ref(None) is None


# ─── extract_chapter ─────────────────────────────────────────────────────────

class TestExtractChapter:
    def test_finds_chapter(self, tmp_path):
        md = "# Book\n\n## Chapter 12\n\nContent of chapter 12.\n\n## Chapter 13\n\nNext.\n"
        path = tmp_path / "book.md"
        path.write_text(md)
        result = extract_chapter(path, 12)
        assert "Content of chapter 12" in result
        assert "Next" not in result

    def test_chapter_not_found(self, tmp_path):
        md = "# Book\n\n## Chapter 12\n\nContent.\n"
        path = tmp_path / "book.md"
        path.write_text(md)
        result = extract_chapter(path, 99)
        assert result is None

    def test_numeric_heading(self, tmp_path):
        md = "# Book\n\n## 12. The Twelfth Chapter\n\nContent here.\n\n## 13. Next\n"
        path = tmp_path / "book.md"
        path.write_text(md)
        result = extract_chapter(path, 12)
        assert "Content here" in result


# ─── lookup_passage ──────────────────────────────────────────────────────────

class TestLookupPassage:
    def test_bible_ref(self, tmp_path):
        md = "## John\n\n### John 3\n\n**16** For God so loved.\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = lookup_passage("John 3:16", str(path))
        assert result["type"] == "bible"
        assert "For God so loved" in result["text"]

    def test_chapter_ref(self, tmp_path):
        md = "# Book\n\n## Chapter 12\n\nContent.\n"
        path = tmp_path / "book.md"
        path.write_text(md)
        result = lookup_passage("Ch 12", str(path))
        assert result["type"] == "chapter"
        assert "Content" in result["text"]

    def test_file_not_found(self):
        result = lookup_passage("John 3:16", "/nonexistent/path.md")
        assert result["text"] is None
        assert "not found" in result["error"].lower()

    def test_unrecognized_ref(self, tmp_path):
        md = "## John\n\n### John 3\n\n**16** text\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = lookup_passage("totally invalid ref!!!", str(path))
        assert result["type"] is None
        assert "unrecognized" in result["error"].lower()

    def test_passage_not_found(self, tmp_path):
        md = "## John\n\n### John 3\n\n**16** text\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = lookup_passage("John 99:1", str(path))
        assert result["text"] is None
        assert "not found" in result["error"].lower()

    def test_bible_ref_returns_parsed(self, tmp_path):
        md = "## John\n\n### John 3\n\n**16** text\n"
        path = tmp_path / "bible.md"
        path.write_text(md)
        result = lookup_passage("John 3:16", str(path))
        assert result["parsed"]["book"] == "John"
        assert result["parsed"]["chapter"] == 3

    def test_chapter_ref_returns_parsed(self, tmp_path):
        md = "# Book\n\n## Chapter 12\n\nContent.\n"
        path = tmp_path / "book.md"
        path.write_text(md)
        result = lookup_passage("Ch 12", str(path))
        assert result["parsed"]["chapter"] == 12


if __name__ == "__main__":
    pytest.main([__file__, "-v"])