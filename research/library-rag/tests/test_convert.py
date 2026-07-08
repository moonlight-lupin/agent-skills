import pytest

import convert_epub_library as cv


def test_slugify_basic():
    assert cv.slugify("Hello, World!") == "hello-world"


def test_slugify_truncates():
    assert cv.slugify("a" * 100, max_len=10) == "a" * 10


def test_split_into_chapters_below_threshold_returns_empty():
    text = "CHAPTER 1\nFirst\nbody one\nCHAPTER 2\nSecond\nbody two"
    assert cv.split_into_chapters(text) == []


def test_split_into_chapters():
    text = "\n".join(f"CHAPTER {n}\nTitle {n}\nSome body for chapter {n}." for n in range(1, 6))
    chapters = cv.split_into_chapters(text)
    assert len(chapters) == 5
    assert chapters[0]["num"] == 1
    assert chapters[0]["title"] == "Title 1"
    assert chapters[0]["slug"].startswith("ch01-")


def test_split_into_chapters_word_numbers():
    text = "\n".join(
        f"CHAPTER {w}\nTitle {w}\nSome body for chapter {w}."
        for w in ("One", "Two", "Three", "Four", "Five")
    )
    chapters = cv.split_into_chapters(text)
    assert len(chapters) == 5
    assert chapters[0]["num"] == "One"          # word label preserved
    assert chapters[0]["slug"].startswith("ch01-")   # filename uses sequential ordinal
    assert chapters[4]["slug"].startswith("ch05-")


def test_split_into_chapters_numbered_dot_style():
    text = "\n".join(f"{n}. Section {n}\nSome body content for section {n}." for n in range(1, 6))
    chapters = cv.split_into_chapters(text)
    assert len(chapters) == 5
    assert chapters[0]["num"] == 1
    assert chapters[0]["title"] == "Section 1"


def test_split_into_chapters_excludes_date_false_positives():
    # Bare-number style, but two entries are really dates — must not become chapters.
    text = (
        "1\nIn some countries the rule applies.\n\n"
        "2\nThe second provision is as follows.\n\n"
        "1\nJanuary 2026 was the effective date.\n\n"
        "31\nDecember 2017 marked the transition.\n\n"
        "3\nThe third provision continues here.\n\n"
        "4\nThe fourth provision concludes."
    )
    labels = cv.audit_chapter_markers(text)
    titles = [t for _, t in labels]
    assert not any("January" in t or "December" in t for t in titles)
    # the four genuine provisions survive (>3, so a real chapter split happens)
    assert len(cv.split_into_chapters(text)) == 4


def test_looks_like_false_anchor():
    assert cv._looks_like_false_anchor("January 2026")
    assert cv._looks_like_false_anchor("   ")
    assert cv._looks_like_false_anchor("174")
    assert not cv._looks_like_false_anchor("In some countries the rule applies.")


def test_fix_yaml_title_leaks(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("---\ntitle: Main Title\n  leaked subtitle\nauthor: X\n---\n\nbody\n")
    fixed = cv.fix_yaml_title_leaks(tmp_path)
    assert fixed == 1
    assert "leaked subtitle" not in f.read_text()


def test_write_chapter_md_drops_empty_fields(tmp_path):
    name = cv.write_chapter_md(
        "slug",
        {"num": 1, "title": "Chap", "slug": "ch01-chap", "content": "body text"},
        {"author": "A", "year": "", "title": "Book", "source_file": "x.epub"},
        md_dir=tmp_path,
    )
    text = (tmp_path / name).read_text()
    assert "author: A" in text
    assert "book: Book" in text
    assert "year:" not in text          # empty field dropped
    assert "edition:" not in text       # absent field dropped
    assert "license:" not in text       # no hardcoded license line


def test_convert_epub_end_to_end(tmp_path):
    pytest.importorskip("ebooklib")
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("id"); book.set_title("T"); book.set_language("en")
    book.add_author("A")
    body = "".join(
        f"<h2>CHAPTER {n}</h2><p>Title {n}</p><p>{'word ' * 50}</p>" for n in range(1, 6)
    )
    item = epub.EpubHtml(title="b", file_name="b.xhtml", lang="en")
    item.content = f"<html><body>{body}</body></html>"
    book.add_item(item)
    book.add_item(epub.EpubNcx()); book.add_item(epub.EpubNav())
    book.spine = ["nav", item]
    epath = tmp_path / "book.epub"
    epub.write_epub(str(epath), book)

    md_root = tmp_path / "lib" / "markdown"
    staging = tmp_path / "staging"
    res = cv.convert_epub(str(epath), "my-book", title="T", author="A", year="2024",
                          md_root=md_root, staging_dir=staging)

    assert res["chapters"] == 5
    mds = sorted((md_root / "my-book" / "chapters").glob("*.md"))
    assert len(mds) == 5

    # raw + extracted text staged OUTSIDE the indexed markdown root
    assert (staging / "raw" / "book.epub").exists()
    assert list((staging / "text").glob("*.txt"))
    assert staging not in md_root.parents

    first = mds[0].read_text()
    assert first.startswith("---")
    assert "book: T" in first
