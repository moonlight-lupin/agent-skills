#!/usr/bin/env python3
"""Document format converter.

Core conversions use only the Python standard library. Optional integrations:
- pandoc executable for Markdown -> PDF
- openpyxl package for XLSX -> CSV

YAML note: PyYAML is used if available. Otherwise this module falls back to a
minimal block-style YAML parser/writer for simple mappings, lists, nested dicts,
strings, numbers, booleans, and null. It does not support anchors, aliases,
tags, flow style, merge keys, or multi-document streams.
"""

from __future__ import annotations

import argparse
import csv
import html
from html.parser import HTMLParser
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

try:  # Python 3.11+
    import tomllib
except ImportError:  # pragma: no cover - repo targets 3.11+
    tomllib = None  # type: ignore[assignment]

FORMATS = {"markdown", "html", "csv", "json", "yaml", "toml", "text", "pdf", "xlsx"}
TEXT_FORMATS = {"markdown", "html", "csv", "json", "yaml", "toml", "text"}
EXTENSION_FORMATS = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".csv": "csv",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".txt": "text",
    ".xlsx": "xlsx",
}


class ConversionError(RuntimeError):
    """Raised for user-facing conversion failures."""


# ─── Markdown / HTML ───────────────────────────────────────────────────────


def _extract_code_spans(text: str) -> tuple[str, dict[str, str]]:
    placeholders: dict[str, str] = {}

    def repl(match: re.Match[str]) -> str:
        token = f"\u0000CODE{len(placeholders)}\u0000"
        placeholders[token] = f"<code>{html.escape(match.group(1))}</code>"
        return token

    return re.sub(r"`([^`]+)`", repl, text), placeholders


def markdown_inline_to_html(text: str) -> str:
    text, code_placeholders = _extract_code_spans(text)
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    for token, rendered in code_placeholders.items():
        text = text.replace(html.escape(token), rendered).replace(token, rendered)
    return text


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    out: list[str] = []
    paragraph: list[str] = []
    in_code = False
    code_lines: list[str] = []
    in_list = False

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append(f"<p>{markdown_inline_to_html(' '.join(paragraph).strip())}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.rstrip("\n")
        if line.strip().startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                flush_paragraph()
                close_list()
                in_code = True
                code_lines = []
            continue
        if in_code:
            code_lines.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            close_list()
            continue

        header = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if header:
            flush_paragraph()
            close_list()
            level = len(header.group(1))
            out.append(f"<h{level}>{markdown_inline_to_html(header.group(2).strip())}</h{level}>")
            continue

        list_item = re.match(r"^[-*+]\s+(.+)$", stripped)
        if list_item:
            flush_paragraph()
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{markdown_inline_to_html(list_item.group(1).strip())}</li>")
            continue

        paragraph.append(stripped)

    if in_code:
        out.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
    flush_paragraph()
    close_list()
    return "\n".join(out) + ("\n" if out else "")


class HTMLToMarkdownParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.href_stack: list[str] = []
        self.list_stack: list[str] = []

    def _append(self, text: str) -> None:
        self.parts.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._append("\n" + "#" * int(tag[1]) + " ")
        elif tag == "p":
            self._append("\n")
        elif tag in {"strong", "b"}:
            self._append("**")
        elif tag in {"em", "i"}:
            self._append("*")
        elif tag == "code":
            self._append("`")
        elif tag == "a":
            self.href_stack.append(attrs_dict.get("href") or "")
            self._append("[")
        elif tag in {"ul", "ol"}:
            self.list_stack.append(tag)
            self._append("\n")
        elif tag == "li":
            marker = "- " if not self.list_stack or self.list_stack[-1] == "ul" else "1. "
            self._append("\n" + marker)
        elif tag == "br":
            self._append("\n")
        elif tag == "pre":
            self._append("\n````\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p"}:
            self._append("\n\n")
        elif tag in {"strong", "b"}:
            self._append("**")
        elif tag in {"em", "i"}:
            self._append("*")
        elif tag == "code":
            self._append("`")
        elif tag == "a":
            href = self.href_stack.pop() if self.href_stack else ""
            self._append(f"]({href})" if href else "]")
        elif tag in {"ul", "ol"}:
            if self.list_stack:
                self.list_stack.pop()
            self._append("\n")
        elif tag == "pre":
            self._append("\n````\n")

    def handle_data(self, data: str) -> None:
        self._append(data)

    def get_markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        lines = [line.rstrip() for line in text.strip().splitlines()]
        return "\n".join(lines).strip() + "\n"


def html_to_markdown(source: str) -> str:
    parser = HTMLToMarkdownParser()
    parser.feed(source)
    parser.close()
    return parser.get_markdown()


class HTMLToTextParser(HTMLParser):
    BREAK_TAGS = {"p", "div", "br", "li", "ul", "ol", "section", "article", "tr"}
    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in self.HEADING_TAGS:
            self.parts.append("\n")
        elif tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.BREAK_TAGS or tag in self.HEADING_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def get_text(self) -> str:
        text = html.unescape("".join(self.parts)).replace("\xa0", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def html_to_text(source: str) -> str:
    parser = HTMLToTextParser()
    parser.feed(source)
    parser.close()
    return parser.get_text()


# ─── CSV / JSON / Markdown table ───────────────────────────────────────────


def csv_to_json(source: str) -> str:
    reader = csv.DictReader(io.StringIO(source))
    return json.dumps(list(reader), indent=2, ensure_ascii=False) + "\n"


def flatten_json(value: Any, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        if not value and prefix:
            # An empty object still owns its column — don't drop the key.
            return {prefix: ""}
        result: dict[str, Any] = {}
        for key, child in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            result.update(flatten_json(child, name))
        return result
    if isinstance(value, list):
        return {prefix: json.dumps(value, ensure_ascii=False, separators=(",", ":"))}
    return {prefix: value}


def json_to_csv(source: str) -> str:
    data = json.loads(source)
    rows = data if isinstance(data, list) else [data]
    if not all(isinstance(row, dict) for row in rows):
        raise ConversionError("JSON to CSV expects an object or an array of objects.")
    flat_rows = [flatten_json(row) for row in rows]
    headers: list[str] = []
    for row in flat_rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    for row in flat_rows:
        writer.writerow({k: _csv_value(row.get(k, "")) for k in headers})
    return output.getvalue()


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def csv_to_markdown_table(source: str) -> str:
    rows = list(csv.reader(io.StringIO(source)))
    if not rows:
        return ""
    headers = rows[0]
    body = rows[1:]

    def esc(cell: Any) -> str:
        return str(cell).replace("|", r"\|").replace("\n", "<br>")

    lines = ["| " + " | ".join(esc(h) for h in headers) + " |"]
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in body:
        padded = row + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(esc(c) for c in padded[: len(headers)]) + " |")
    return "\n".join(lines) + "\n"


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip().replace("<br>", "\n"))
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip().replace("<br>", "\n"))
    return cells


def markdown_table_to_csv(source: str) -> str:
    # Extract the FIRST pipe table only (as documented): a contiguous run of
    # |-containing lines. Prose lines that merely contain a pipe, and any
    # later tables, are not swept into the CSV.
    parsed: list[list[str]] = []
    in_table = False
    for line in source.splitlines():
        if "|" in line.strip() and line.strip():
            in_table = True
            cells = _split_markdown_row(line)
            if cells and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells):
                continue
            parsed.append(cells)
        elif in_table:
            break
    if not parsed:
        raise ConversionError("No Markdown pipe table found.")
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(parsed)
    return output.getvalue()


# ─── YAML ──────────────────────────────────────────────────────────────────


def _has_multiple_yaml_documents(text: str) -> bool:
    markers = [line.strip() for line in text.splitlines() if line.strip() == "---"]
    return len(markers) > 1 or any(line.strip() == "..." for line in text.splitlines())


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    low = value.lower()
    if low in {"null", "~"}:
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        if value.startswith('"'):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value[1:-1]
        return value[1:-1].replace("''", "'")
    try:
        if re.fullmatch(r"[-+]?\d+", value):
            return int(value)
        if re.fullmatch(r"[-+]?(\d+\.\d*|\d*\.\d+)([eE][-+]?\d+)?", value) or re.fullmatch(r"[-+]?\d+[eE][-+]?\d+", value):
            return float(value)
    except ValueError:
        pass
    return value


def _yaml_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _preprocess_yaml(text: str) -> list[str]:
    processed: list[str] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.strip() == "---":
            continue
        if "\t" in raw[: _yaml_indent(raw)]:
            raise ConversionError("YAML fallback parser does not support tab indentation.")
        processed.append(raw.rstrip())
    return processed


def minimal_yaml_load(text: str) -> Any:
    """Parse a minimal subset of block-style YAML."""
    if _has_multiple_yaml_documents(text):
        raise ConversionError("YAML multi-document streams are not supported; split the documents first.")
    lines = _preprocess_yaml(text)
    if not lines:
        return None

    def parse_block(index: int, indent: int) -> tuple[Any, int]:
        container: Any | None = None
        while index < len(lines):
            line = lines[index]
            current_indent = _yaml_indent(line)
            if current_indent < indent:
                break
            if current_indent > indent:
                raise ConversionError(f"Unexpected YAML indentation near: {line.strip()}")
            stripped = line.strip()
            if stripped.startswith("- "):
                if container is None:
                    container = []
                if not isinstance(container, list):
                    raise ConversionError("Cannot mix YAML list items and mapping keys at the same indentation.")
                item = stripped[2:].strip()
                if item == "":
                    child, index = parse_block(index + 1, _next_indent(index + 1, current_indent + 2))
                    container.append(child)
                    continue
                if re.fullmatch(r"[^:#][^:]*:\s*.*", item):
                    key, value = item.split(":", 1)
                    item_dict = {key.strip(): parse_scalar(value.strip())} if value.strip() else {}
                    if value.strip():
                        index += 1
                        if index < len(lines) and _yaml_indent(lines[index]) > current_indent:
                            child, index = parse_block(index, _next_indent(index, current_indent + 2))
                            if isinstance(child, dict):
                                item_dict.update(child)
                            else:
                                raise ConversionError("YAML fallback parser cannot merge a non-mapping into a list item mapping.")
                    else:
                        child, index = parse_block(index + 1, _next_indent(index + 1, current_indent + 2))
                        item_dict[key.strip()] = child
                    container.append(item_dict)
                    continue
                container.append(parse_scalar(item))
                index += 1
                continue

            if ":" not in stripped:
                raise ConversionError(f"YAML fallback parser expected 'key: value', got: {stripped}")
            if container is None:
                container = {}
            if not isinstance(container, dict):
                raise ConversionError("Cannot mix YAML mapping keys and list items at the same indentation.")
            key, value = stripped.split(":", 1)
            key = key.strip()
            if not key:
                raise ConversionError("YAML fallback parser found an empty key.")
            if value.strip() == "":
                if index + 1 >= len(lines) or _yaml_indent(lines[index + 1]) <= current_indent:
                    container[key] = {}
                    index += 1
                else:
                    child, index = parse_block(index + 1, _next_indent(index + 1, current_indent + 2))
                    container[key] = child
            else:
                container[key] = parse_scalar(value.strip())
                index += 1
        return ({} if container is None else container), index

    def _next_indent(index: int, default: int) -> int:
        if index >= len(lines):
            return default
        return _yaml_indent(lines[index])

    result, final = parse_block(0, _yaml_indent(lines[0]))
    if final != len(lines):
        raise ConversionError("Could not parse complete YAML document with fallback parser.")
    return result


def load_yaml(text: str, prefer_pyyaml: bool = True) -> Any:
    if _has_multiple_yaml_documents(text):
        raise ConversionError("YAML multi-document streams are not supported; split the documents first.")
    if prefer_pyyaml:
        try:
            import yaml  # type: ignore
        except Exception:
            yaml = None  # type: ignore[assignment]
        if yaml is not None:
            return yaml.safe_load(text)
    return minimal_yaml_load(text)


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value)
    if text == "" or text.strip() != text or re.search(r"[:#\[\]{},&*!|>'\"%@`]|^-|^\?|^~$|^(true|false|null)$", text, re.I):
        return json.dumps(text, ensure_ascii=False)
    return text


def dump_yaml(data: Any, indent: int = 0) -> str:
    space = " " * indent
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.append(dump_yaml(value, indent + 2).rstrip("\n"))
            else:
                lines.append(f"{space}{key}: {_yaml_scalar(value)}")
        return "\n".join(lines) + "\n"
    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.append(dump_yaml(item, indent + 2).rstrip("\n"))
            else:
                lines.append(f"{space}- {_yaml_scalar(item)}")
        return "\n".join(lines) + "\n"
    return f"{space}{_yaml_scalar(data)}\n"


# ─── TOML ──────────────────────────────────────────────────────────────────


def load_toml(text: str) -> Any:
    if tomllib is None:  # pragma: no cover
        raise ConversionError("TOML reading requires Python 3.11+ with tomllib.")
    return tomllib.loads(text)


def _toml_scalar(value: Any) -> str:
    if value is None:
        raise ConversionError("TOML has no null value; remove nulls before JSON/YAML to TOML conversion.")
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        if any(isinstance(item, (dict, list)) for item in value):
            raise ConversionError("TOML writer supports only arrays of scalar values.")
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    raise ConversionError(f"Unsupported TOML value type: {type(value).__name__}")


def dump_toml(data: Any) -> str:
    if not isinstance(data, dict):
        raise ConversionError("TOML output expects a mapping/object at the top level.")
    lines: list[str] = []

    def write_table(table: dict[str, Any], prefix: list[str]) -> None:
        scalar_items = [(k, v) for k, v in table.items() if not isinstance(v, dict)]
        child_items = [(k, v) for k, v in table.items() if isinstance(v, dict)]
        if prefix:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append("[" + ".".join(prefix) + "]")
        for key, value in scalar_items:
            lines.append(f"{key} = {_toml_scalar(value)}")
        for key, value in child_items:
            write_table(value, prefix + [str(key)])

    write_table(data, [])
    return "\n".join(lines).strip() + "\n"


def _json_default(value: Any) -> str:
    return str(value)


# ─── Optional dependencies ─────────────────────────────────────────────────


def xlsx_to_csv(path: str) -> str:
    try:
        import openpyxl  # type: ignore
    except Exception as exc:
        raise ConversionError("XLSX to CSV requires openpyxl. Install it with: python -m pip install openpyxl") from exc
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    for row in sheet.iter_rows(values_only=True):
        writer.writerow(["" if cell is None else cell for cell in row])
    workbook.close()
    return output.getvalue()


def markdown_to_pdf(input_path: str, output_path: str) -> None:
    if not shutil.which("pandoc"):
        raise ConversionError("Markdown to PDF requires pandoc. Install pandoc and ensure it is on PATH.")
    try:
        subprocess.run(["pandoc", input_path, "-o", output_path], check=True)
    except subprocess.CalledProcessError as exc:
        raise ConversionError(f"pandoc failed with exit code {exc.returncode}.") from exc


# ─── Conversion orchestration ───────────────────────────────────────────────


def detect_format(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext in EXTENSION_FORMATS:
        return EXTENSION_FORMATS[ext]
    raise ConversionError(f"Could not detect input format from extension '{ext}'. Pass --from explicitly.")


def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        return handle.read()


def write_text_file(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def convert_text(source: str, from_format: str, to_format: str) -> str:
    if from_format == to_format:
        return source

    if from_format == "markdown" and to_format == "html":
        return markdown_to_html(source)
    if from_format == "html" and to_format == "markdown":
        return html_to_markdown(source)
    if from_format == "html" and to_format == "text":
        return html_to_text(source)
    if from_format == "csv" and to_format == "json":
        return csv_to_json(source)
    if from_format == "json" and to_format == "csv":
        return json_to_csv(source)
    if from_format == "csv" and to_format == "markdown":
        return csv_to_markdown_table(source)
    if from_format == "markdown" and to_format == "csv":
        return markdown_table_to_csv(source)

    # Structured data conversions through Python objects.
    if from_format in {"json", "yaml", "toml"} and to_format in {"json", "yaml", "toml"}:
        if from_format == "json":
            data = json.loads(source)
        elif from_format == "yaml":
            data = load_yaml(source)
        else:
            data = load_toml(source)

        if to_format == "json":
            return json.dumps(data, indent=2, ensure_ascii=False, default=_json_default) + "\n"
        if to_format == "yaml":
            return dump_yaml(data)
        if to_format == "toml":
            return dump_toml(data)

    raise ConversionError(f"Unsupported conversion: {from_format} -> {to_format}")


def convert_file(input_path: str, from_format: str | None, to_format: str, output_path: str | None) -> str | None:
    from_format = from_format or detect_format(input_path)
    if from_format not in FORMATS:
        raise ConversionError(f"Unsupported input format: {from_format}")
    if to_format not in FORMATS:
        raise ConversionError(f"Unsupported output format: {to_format}")

    if to_format == "pdf":
        if from_format != "markdown":
            raise ConversionError("PDF output is supported only for Markdown input.")
        if not output_path:
            raise ConversionError("PDF output requires --output because PDF is binary.")
        markdown_to_pdf(input_path, output_path)
        return None

    if from_format == "xlsx":
        if to_format != "csv":
            raise ConversionError("XLSX input can only be converted to CSV.")
        result = xlsx_to_csv(input_path)
    else:
        if from_format not in TEXT_FORMATS:
            raise ConversionError(f"Input format {from_format} is not readable as text.")
        result = convert_text(read_text_file(input_path), from_format, to_format)

    if output_path:
        write_text_file(output_path, result)
        return None
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="convert",
        description="Convert between Markdown, HTML, CSV, JSON, YAML, TOML, text, XLSX, and PDF formats.",
    )
    parser.add_argument("--input", "-i", required=True, help="Input file path")
    parser.add_argument("--from", dest="from_format", choices=sorted(FORMATS), help="Input format; auto-detected from extension if omitted")
    parser.add_argument("--to", dest="to_format", choices=sorted(FORMATS), required=True, help="Output format")
    parser.add_argument("--output", "-o", help="Output file path; omitted writes text output to stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = convert_file(args.input, args.from_format, args.to_format, args.output)
    except (ConversionError, OSError, json.JSONDecodeError, csv.Error) as exc:
        print(f"convert: error: {exc}", file=sys.stderr)
        return 1
    if result is not None:
        sys.stdout.write(result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
