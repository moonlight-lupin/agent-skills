# EPUB Conversion Notes

## EPUB to text extraction

### Extraction script

```python
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import os

def extract_epub_to_text(epub_path, output_path):
    """Extract full text from an EPUB and save as .txt."""
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
```

Dependencies: `pip install ebooklib beautifulsoup4` (use `--break-system-packages` on PEP 668 systems or use a venv).

### Key options

- `ignore_ncx=True` — skip the NCX navigation spine (toc.ncx) which duplicates content from the HTML items.
- `ebooklib.ITEM_DOCUMENT` — extracts only HTML content items (chapters, sections). Filters out images, stylesheets, and metadata.
- `BeautifulSoup.get_text(separator="\n", strip=True)` — clean line-separated text suitable for Markdown generation or direct RAG indexing.

## Structured Markdown conversion (chapter splitting)

After text extraction, the raw `.txt` must be parsed into per-chapter Markdown files.
The conversion script is at `scripts/convert_epub_library.py`.

### Per-chapter Markdown structure

Each chapter becomes `chapters/chNN-slug.md` with YAML frontmatter:

```yaml
---
title: "Chapter Title"
author: Author Name
year: 2024
book: Book Title
chapter: 5
slug: ch05-chapter-title
source: book.txt
license: Private copy — copyrighted work, converted for personal study use only
---
```

### Pitfalls encountered and fixed

1. **Multiple TOC ghosts**: Large EPUBs produce multiple table-of-contents blocks in the extracted text (short TOC, extended TOC, page-number lists). You MUST skip all of them when finding chapter headings in body text. Identify TOC line ranges and exclude them from chapter-heading searches.

2. **CHAPTER N vs N. Title**: EPUBs use different heading patterns in TOC vs body. Always grep for the BODY pattern (e.g. `^Chapter \d+$` or `^CHAPTER \d+$`), not the TOC pattern. Use the TOC only to map chapter numbers to titles.

3. **Title + subtitle leak into YAML**: EPUB headings often include a title line followed by subtitle text. When building YAML frontmatter, use ONLY the main title. Post-process by removing indented continuation lines between `title:` and the next YAML field.

4. **Slug length**: Truncate slugs to 60 chars (preserving `chNN-` prefix) to avoid `OSError: File name too long`.

5. **Page-number blocks**: Some EPUBs extract huge blocks of standalone page numbers. Detect by long runs of purely-numeric lines and skip.

6. **Additional notes and appendices**: Reference works often have special sections between or after chapters. Handle them as separate sections with their own slug prefixes (`additional-note-`, `appendix-NN-`).

7. **Post-processing pass is essential**: After initial generation, ALWAYS verify:
   - Every `.md` file starts with `---` (valid YAML frontmatter)
   - Every file has `title:`, `year:`, `slug:` fields
   - No multi-line values leaked into the YAML block
   - Slug lengths are under the filesystem limit
   - Content is non-empty for each chapter file

## Telegram limitation

Telegram gateway rejects `.epub` as an unsupported document type. Workarounds:
1. **ZIP the EPUB** — send as `.zip`, agent can unzip and process.
2. **Local file reference** — if the file is already on the machine, reference it by path directly.
3. **Pre-convert** — extract text on the sending device and send `.txt` or `.md` instead.
