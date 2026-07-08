# Document Converter Conversion Matrix

This table documents every conversion implemented by `scripts/convert.py`, the dependency surface, structural behavior, limitations, and likely data-loss risks.

## Supported conversions

| Source | Target | Dependency | Structure preserved | Limitations | Data-loss risk |
|--------|--------|------------|---------------------|-------------|----------------|
| Markdown | HTML | Python stdlib | Headings, paragraphs, unordered lists, fenced code blocks, inline bold/italic/code, links | Markdown parser is intentionally small; no tables, blockquotes, footnotes, HTML passthrough, task lists, images, or nested lists | Medium: unsupported Markdown constructs become plain paragraphs or are omitted from structure |
| HTML | Markdown | Python stdlib `html.parser` | h1-h6, p, strong/b, em/i, code, a href, ul/ol/li, br | CSS, scripts, styles, layout, attributes other than href, complex tables, images, spans, and semantic custom elements are discarded | High for designed pages; low for simple article-like HTML |
| HTML | text | Python stdlib `html.parser` | Text content, paragraph/list/heading breaks, decoded entities | No layout or table reconstruction; whitespace normalized | Medium: visual layout and hidden semantics are lost |
| CSV | JSON | Python stdlib `csv`, `json` | Header row mapped to object keys; one JSON object per data row | Duplicate headers follow `csv.DictReader` behavior; all values are strings; empty cells remain empty strings | Medium: types and duplicate-column intent are lost |
| JSON | CSV | Python stdlib `json`, `csv` | Nested objects flattened with dot notation; scalar values become cells | Top-level must be an object or array of objects; lists become compact JSON strings; null becomes an empty cell | High: nesting, arrays, nulls, and schema are not reversible from plain CSV |
| CSV | Markdown table | Python stdlib `csv` | Header, rows, and cell text; pipes escaped; newlines converted to `<br>` | Alignment metadata is not inferred; all columns use `---`; wide tables may be hard to read | Low for simple tables; medium if cells contain Markdown-sensitive content |
| Markdown table | CSV | Python stdlib `csv` | First/only pipe table rows and cells; separator row ignored; escaped pipes unescaped | Surrounding prose ignored; complex Markdown tables, alignment details, and multiline cells are not fully supported | Medium: table formatting and non-table Markdown are discarded |
| YAML | JSON | PyYAML if installed, otherwise fallback parser | Common mappings, lists, nested dicts, strings, numbers, booleans, null | Fallback rejects/does not support anchors, aliases, tags, flow style, merge keys, tabs, and multi-document streams | Medium: YAML-specific features are lost; with fallback, advanced YAML fails fast |
| JSON | YAML | Python stdlib writer | Mappings, lists, strings, numbers, booleans, null | Emits plain 2-space block YAML only; no anchors, aliases, tags, comments, or original ordering comments | Medium: comments and YAML-specific presentation are lost |
| YAML | TOML | YAML parser + custom TOML writer | Single YAML mapping converted to TOML keys/tables | Top-level must be TOML-compatible mapping; null unsupported; arrays must be scalar; no YAML multi-document | High: comments/anchors/tags lost and incompatible values fail |
| TOML | YAML | Python 3.11+ `tomllib` + YAML writer | TOML tables become nested YAML mappings; scalars/lists preserved | TOML comments and exact formatting are not preserved; dates/times become Python objects then string-like YAML values | Medium: comments and formatting lost |
| TOML | JSON | Python 3.11+ `tomllib`, `json` | Tables, arrays, strings, numbers, booleans | TOML date/time values are serialized as strings for JSON compatibility; comments lost | Medium: TOML comments and date type fidelity may be lost |
| JSON | TOML | Custom TOML writer | JSON objects become TOML tables; scalar arrays supported | Top-level must be object; null unsupported; arrays of objects/nested arrays unsupported; keys are emitted as supplied | High: many legal JSON shapes have no direct TOML equivalent |
| XLSX | CSV | Optional `openpyxl` | First worksheet cell values, one row per CSV row | Reads first sheet only; formulas use cached values; styles, merged-cell semantics, comments, formulas, and workbook metadata discarded | High: spreadsheet behavior and formatting are lost |
| Markdown | PDF | Optional `pandoc` executable | Delegated to pandoc | Requires `pandoc` and a working PDF engine; output must be a file path | Depends on pandoc/PDF engine; unsupported Markdown extensions may render differently |

## Auto-detected input formats

When `--from` is omitted, the converter maps extensions as follows:

| Extension | Format |
|-----------|--------|
| `.md`, `.markdown` | `markdown` |
| `.html`, `.htm` | `html` |
| `.csv` | `csv` |
| `.json` | `json` |
| `.yaml`, `.yml` | `yaml` |
| `.toml` | `toml` |
| `.txt` | `text` |
| `.xlsx` | `xlsx` |

If a file uses a non-standard extension, pass `--from` explicitly.

## Data-loss notes by family

### Markup formats

Markdown and HTML are not equivalent. Markdown is a compact writing format; HTML is a document tree with attributes and layout hooks. The converter handles common prose structures and intentionally ignores visual styling. Treat output as a portable draft, not as a pixel-perfect web publishing artifact.

### Tabular formats

CSV has no schema. It cannot represent nested objects, typed nulls, formulas, merged cells, multiple worksheets, or rich text. JSON→CSV flattening makes data spreadsheet-friendly, but the flattened CSV is not a lossless backup of the original JSON.

### Structured config formats

JSON, YAML, and TOML overlap but are not interchangeable:

- YAML can represent anchors, aliases, tags, comments, and multi-document streams that JSON/TOML cannot.
- TOML cannot represent `null` and has stricter rules for arrays and tables.
- JSON has fewer scalar types and no comments.

For configuration files used by production systems, diff and review the converted output before replacing the original.

### Optional binary/document formats

Excel and PDF support is deliberately narrow:

- XLSX is read-only and first-sheet-only via `openpyxl`.
- PDF is write-only from Markdown via `pandoc`.
- No OCR or PDF text extraction is attempted.
- `.docx` is not handled by this converter; use `fill-template` when the task is document generation from Word/Excel templates.

## Failure behavior

The CLI fails fast with a user-facing error when a conversion is unsupported, an optional dependency is missing, a source format cannot be detected, or a target format cannot represent the input shape. This is intentional: explicit failure is safer than silently dropping structure.
