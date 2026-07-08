---
name: document-converter
description: "Convert between document formats: Markdown↔HTML, CSV↔JSON, YAML↔TOML, JSON↔YAML, CSV↔Markdown table, HTML→plain text, JSON→CSV (flattening nested objects), Excel→CSV, Markdown→PDF. Requires pandoc for PDF and openpyxl for Excel."
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [document, converter, format, markdown, html, csv, json, yaml, toml, transform]
  related_skills: [fill-template]
---

# Document Converter

## Overview

Use this skill when you need to convert common document and data formats while preserving as much structure as the source format allows. The bundled CLI covers lightweight, local conversions between Markdown, HTML, CSV, JSON, YAML, TOML, plain text, Excel, and PDF output.

The core conversions use the Python standard library: JSON, CSV, HTML parsing, Markdown heuristics, TOML reading via `tomllib`, and custom TOML/YAML writers. PDF output uses `pandoc` and Excel reading uses `openpyxl` — both are required dependencies for those conversion paths. If a dependency is missing, the tool exits with a clear installation hint instead of failing with a traceback.

## Conversion matrix

| From | To | Command shape | Dependency | Notes |
|------|----|---------------|------------|-------|
| Markdown | HTML | `--from markdown --to html` | stdlib | Headers, paragraphs, lists, fenced code, bold/italic/code, links. |
| HTML | Markdown | `--from html --to markdown` | stdlib | Common block/inline tags; complex CSS/layout is discarded. |
| HTML | text | `--from html --to text` | stdlib | Strips tags, decodes entities, preserves paragraph/list breaks. |
| CSV | JSON | `--from csv --to json` | stdlib | Header row becomes object keys; values remain strings. |
| JSON | CSV | `--from json --to csv` | stdlib | Flattens nested objects with dot notation; arrays are JSON strings. |
| CSV | Markdown | `--from csv --to markdown` | stdlib | Produces a GitHub-style pipe table. |
| Markdown | CSV | `--from markdown --to csv` | stdlib | Reads the first pipe table. |
| YAML | JSON | `--from yaml --to json` | stdlib fallback; PyYAML optional | Basic YAML only without PyYAML. |
| JSON | YAML | `--from json --to yaml` | stdlib | 2-space YAML, no anchors. |
| YAML | TOML | `--from yaml --to toml` | stdlib fallback; PyYAML optional | Single YAML document; TOML-compatible values only. |
| TOML | YAML | `--from toml --to yaml` | stdlib | TOML tables become nested YAML mappings. |
| TOML | JSON | `--from toml --to json` | Python 3.11+ `tomllib` | TOML dates/times become strings for JSON. |
| JSON | TOML | `--from json --to toml` | stdlib | Strings, numbers, bools, arrays, and nested tables. |
| XLSX | CSV | `--from xlsx --to csv` | openpyxl | Reads the first worksheet only. |
| Markdown | PDF | `--from markdown --to pdf` | pandoc | Write-only PDF target; requires `--output`. |

See `references/conversion-matrix.md` for limitations and data-loss risks per conversion.

## Quick start

Run from the skill directory or call the script by path:

```bash
python scripts/convert.py --input notes.md --from markdown --to html --output notes.html
```

Format auto-detection uses the input file extension when `--from` is omitted:

```bash
python scripts/convert.py --input notes.md --to html --output notes.html
```

Examples for each supported conversion:

```bash
# Markdown ↔ HTML
python scripts/convert.py --input page.md --to html --output page.html
python scripts/convert.py --input page.html --to markdown --output page.md

# HTML → plain text
python scripts/convert.py --input page.html --to text --output page.txt

# CSV ↔ JSON
python scripts/convert.py --input people.csv --to json --output people.json
python scripts/convert.py --input records.json --to csv --output records.csv

# CSV ↔ Markdown table
python scripts/convert.py --input people.csv --to markdown --output people-table.md
python scripts/convert.py --input people-table.md --to csv --output people.csv

# JSON ↔ YAML
python scripts/convert.py --input config.json --to yaml --output config.yaml
python scripts/convert.py --input config.yaml --to json --output config.json

# YAML ↔ TOML
python scripts/convert.py --input config.yaml --to toml --output config.toml
python scripts/convert.py --input config.toml --to yaml --output config.yaml

# JSON ↔ TOML
python scripts/convert.py --input config.json --to toml --output config.toml
python scripts/convert.py --input config.toml --to json --output config.json

# Excel → CSV, first sheet only; requires openpyxl
python scripts/convert.py --input workbook.xlsx --to csv --output sheet.csv

# Markdown → PDF; requires pandoc
python scripts/convert.py --input report.md --to pdf --output report.pdf
```

If `--output` is omitted for text formats, the converted content is written to stdout.

## Edge case handling

- **Nested JSON→CSV flattening:** nested objects are flattened with dot notation, e.g. `{"user": {"name": "Ada"}}` becomes a `user.name` column. Lists and non-scalar nested values are serialized as compact JSON strings because CSV has no native nesting.
- **CSV type loss:** CSV values are strings. A CSV→JSON→CSV roundtrip does not recover original numbers, booleans, or dates unless the source encoded them explicitly and a downstream process re-types them.
- **HTML entity decoding:** HTML→Markdown and HTML→text decode entities such as `&amp;`, `&nbsp;`, and numeric entities. Whitespace is normalized; exact browser layout is not preserved.
- **YAML support:** PyYAML is used if installed. Without it, a minimal parser handles common block-style mappings, lists, nested dicts, strings, numbers, booleans, and nulls. Complex YAML features are not supported in fallback mode: anchors, aliases, tags, flow style, merge keys, and multi-document streams.
- **YAML multi-document:** the converter treats YAML input as a single document. Split multi-document YAML into separate files before conversion.
- **TOML type limitations:** TOML output supports basic scalar values, arrays of scalar values, and nested tables. Mixed arrays, arrays of tables, tagged values, and arbitrary objects are rejected with a clear message.

## Dependencies

Most conversions use only the Python standard library. Two conversion paths need external tools:

### Pandoc for Markdown→PDF

Markdown→PDF shells out to `pandoc`. If `pandoc` is missing, the CLI prints:

```text
Markdown to PDF requires pandoc. Install pandoc and ensure it is on PATH.
```

Install pandoc through your operating system package manager or from <https://pandoc.org/installing.html>. A PDF output path is required because PDF is binary and cannot be written to stdout.

### openpyxl for Excel→CSV

Excel reading requires `openpyxl`:

```bash
python -m pip install openpyxl
```

If it is absent, the CLI prints an installation hint and exits non-zero. The converter reads only the first worksheet; use a spreadsheet tool or a small custom script when you need a named sheet, formulas evaluated by Excel, formatting, or multiple CSV files.

## Common pitfalls

1. **Expecting lossless CSV roundtrips.** CSV has no schema, nesting, or reliable types. JSON→CSV flattening is practical for inspection/import, not a reversible archival format.
2. **Assuming HTML layout survives.** HTML→Markdown/text keeps content structure, not CSS, scripts, tables with spans, or exact browser whitespace.
3. **Using fallback YAML for advanced YAML.** Anchors, aliases, tags, flow-style maps/lists, merge keys, and multi-document streams need a real YAML parser and may still lose anchor identity when written back out.
4. **Writing all JSON to TOML.** TOML cannot represent every JSON shape. Arrays must be scalar and consistent enough for TOML consumers; objects become tables.
5. **Forgetting dependencies.** PDF requires `pandoc` and Excel requires `openpyxl`. Install both before relying on automation.
6. **Mixing Markdown prose and tables.** Markdown→CSV reads the first pipe table it can find and ignores surrounding prose.

## What this skill does not do

- **No OCR.** Scanned PDFs and images need an OCR pipeline before text conversion.
- **No PDF extraction.** PDF is write-only here via Markdown→PDF. Use a dedicated PDF/OCR skill for extracting text or tables from PDF.
- **No binary Office editing.** `.docx`, styled `.xlsx` generation, and mail-merge workflows are outside this converter. Use `fill-template` for filling Word/Excel templates.
- **No preservation of styling-heavy layouts.** It is intended for portable text/data transformations, not pixel-perfect publishing.

## Verification checklist

- [ ] Confirm the source and target formats are in the matrix.
- [ ] Use `--output` for file output; omit it only when stdout text is acceptable.
- [ ] Inspect a sample output before batch-converting many files.
- [ ] For JSON→CSV, check flattened column names and list serialization.
- [ ] For YAML/TOML, confirm advanced features were not required or silently lost.
- [ ] For PDF/Excel, verify pandoc and openpyxl are installed before relying on automation.
