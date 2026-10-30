"""Parse UPSTREAM_MANIFEST.md tables into a fail-open ManifestDoc.

Italic, strike-through, and HTML markup inside cells are not stripped and may yield junk keys.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

_SEP_CELL = re.compile(r"^:?-{1,}:?$")
_TRAILING_PUNCT = ".,;:!?"
LINK_LOOKAHEAD = 2048  # [text](dest) completers beyond this are plain text; keys never exceed 2KB.


@dataclass
class ManifestDoc:
    skills: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)
    path: str = ""
    rows: dict[str, dict[str, str]] = field(default_factory=dict)
    # R17: True when parsing saw at least one Skill table header row
    # (header + separator with a normalized "Skill" cell, even with zero
    # data rows). Distinguishes a legitimate empty manifest from a file
    # whose tables were overwritten with prose.
    has_table: bool = False
    # R18: length in bytes of the content actually parsed by load_manifest;
    # None when unknown (text input, never read from disk). The trust gate
    # treats an unknown size as untrusted (fail-closed) unless has_table
    # is set.
    size: int | None = None


@dataclass
class GfmTable:
    header: list[str]
    data: list[list[str]]
    header_line: int
    data_lines: list[int]


@dataclass
class TableScan:
    tables: list[GfmTable] = field(default_factory=list)
    unpaired: list[tuple[int, list[str]]] = field(default_factory=list)


def load_manifest(path) -> ManifestDoc:
    # R18: size is the length of the bytes actually read (len(raw)), never
    # a later stat(): a file mutated after the read must not change what
    # the parsed document claims about itself.
    spath = str(path)
    try:
        raw = Path(path).read_bytes()
    except Exception as exc:
        return ManifestDoc(
            skills=set(),
            errors=[f"cannot read manifest: {spath}: {exc}"],
            path=spath,
            size=0,
        )
    try:
        text = raw.decode("utf-8-sig", errors="replace")
    except Exception as exc:
        return ManifestDoc(
            skills=set(), errors=[str(exc)], path=spath, size=len(raw)
        )
    try:
        doc = _parse(text, path=spath)
        doc.size = len(raw)
        return doc
    except Exception as exc:
        return ManifestDoc(
            skills=set(), errors=[str(exc)], path=spath, size=len(raw)
        )


def load_manifest_text(text: str) -> ManifestDoc:
    try:
        return _parse(text, path="")
    except Exception as exc:
        return ManifestDoc(skills=set(), errors=[str(exc)], path="")


def is_manifested(doc: ManifestDoc, name: str) -> bool:
    if not isinstance(name, str):
        return False
    key = _normalize_key(name)
    if not key:
        return False
    return key in doc.skills


def scan_tables(text: str) -> TableScan:
    """Split visible (non-fence, non-comment) pipe-lines into GFM tables.

    A table starts only at a header row directly followed by a separator row.
    Remaining pipe-rows in that contiguous block are DATA, including an
    all-separator row in the middle of a table.
    """
    result = TableScan()
    if not isinstance(text, str):
        return result
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    visible = list(_iter_visible_lines(lines))
    i = 0
    n = len(visible)
    while i < n:
        if not _is_table_line(visible[i][1]):
            i += 1
            continue
        block: list[tuple[int, list[str]]] = []
        while i < n and _is_table_line(visible[i][1]):
            ln, raw = visible[i]
            block.append((ln, _split_row(raw)))
            i += 1
        _consume_block(block, result)
    return result


def _parse(text: str, path: str) -> ManifestDoc:
    if not isinstance(text, str):
        return ManifestDoc(skills=set(), errors=["manifest text is not a string"], path=path)
    if text.startswith("\ufeff"):
        text = text[1:]
    skills: set[str] = set()
    errors: list[str] = []
    rows: dict[str, dict[str, str]] = {}
    has_table = False
    scan = scan_tables(text)
    for ln, cells in scan.unpaired:
        header_norm = [_normalize_header_cell(c) for c in cells]
        if "Skill" in header_norm:
            errors.append(f"line {ln}: header row with no separator")
    for table in scan.tables:
        header_norm = [_normalize_header_cell(c) for c in table.header]
        if "Skill" not in header_norm:
            continue
        has_table = True
        for row, rln in zip(table.data, table.data_lines):
            if not row:
                continue
            key = row[0]
            if not key or not str(key).strip():
                errors.append(f"line {rln}: empty first cell")
                continue
            if _is_separator_cell(key):
                continue
            name = _normalize_key(key)
            if name:
                skills.add(name)
                if name not in rows:
                    rows[name] = {
                        _normalize_header_cell(header): (
                            cell.strip() if isinstance(cell, str) else cell
                        )
                        for header, cell in zip(table.header, row)
                    }
            else:
                errors.append(f"line {rln}: rejected key {key!r}")
    return ManifestDoc(
        skills=skills, errors=errors, path=path, rows=rows, has_table=has_table
    )


def _consume_block(block: list[tuple[int, list[str]]], result: TableScan) -> None:
    j = 0
    while j < len(block):
        ln, cells = block[j]
        if j + 1 < len(block) and _is_separator_row(block[j + 1][1]):
            data: list[list[str]] = []
            data_lines: list[int] = []
            j += 2
            while j < len(block):
                # F2: an all-separator row in DATA is data, never a header boundary.
                if _is_separator_row(block[j][1]):
                    data.append(block[j][1])
                    data_lines.append(block[j][0])
                    j += 1
                    continue
                if (
                    j + 1 < len(block)
                    and _is_separator_row(block[j + 1][1])
                    and _looks_like_header(block[j][1])
                ):
                    break
                data.append(block[j][1])
                data_lines.append(block[j][0])
                j += 1
            result.tables.append(
                GfmTable(
                    header=cells,
                    data=data,
                    header_line=ln,
                    data_lines=data_lines,
                )
            )
            continue
        result.unpaired.append((ln, cells))
        j += 1


def _looks_like_header(cells: list[str]) -> bool:
    """A new table in a pipe-block starts at a real header, not a data row."""
    known = {"Skill", "File", "Date"}
    return any(_normalize_header_cell(c) in known for c in cells)


def _fence_run(stripped: str) -> tuple[str, int]:
    """Return (fence char, run length) if stripped starts with 3+ ` or ~."""
    if not stripped or stripped[0] not in "`~":
        return "", 0
    char = stripped[0]
    n = 0
    for c in stripped:
        if c != char:
            break
        n += 1
    if n < 3:
        return "", 0
    return char, n


def _iter_visible_lines(lines: list[str]):
    """Yield 1-indexed (lineno, line) skipping fenced code and HTML comments."""
    in_fence = False
    fence_char = ""
    fence_len = 0
    in_comment = False
    for idx, line in enumerate(lines, 1):
        if in_comment:
            pos = line.find("-->")
            if pos == -1:
                continue
            line = line[pos + 3 :]
            in_comment = False
            if not line.strip():
                continue
        if in_fence:
            stripped = line.lstrip()
            char, run = _fence_run(stripped)
            rest = stripped[run:] if run else stripped
            if (
                char == fence_char
                and run >= fence_len
                and rest.strip() == ""
            ):
                in_fence = False
                fence_char = ""
                fence_len = 0
                # Closer is not a table row, but it breaks a contiguous table run.
                yield idx, line
            continue
        while "<!--" in line:
            start = line.find("<!--")
            before = line[:start]
            after = line[start + 4 :]
            end = after.find("-->")
            if end == -1:
                in_comment = True
                line = before
                break
            line = before + after[end + 3 :]
        if in_comment:
            if line.strip():
                yield idx, line
            continue
        stripped = line.lstrip()
        char, run = _fence_run(stripped)
        if char:
            in_fence = True
            fence_char = char
            fence_len = run
            # Opener is not a table row, but it breaks a contiguous table run.
            yield idx, line
            continue
        yield idx, line


def _is_table_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def _split_row(line: str) -> list[str]:
    s = line.strip()
    i = 1 if s.startswith("|") else 0
    cells: list[str] = []
    current: list[str] = []
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            current.append("\\")
            current.append("|")
            i += 2
            continue
        if s[i] == "|":
            cells.append("".join(current).strip())
            current.clear()
            i += 1
            continue
        current.append(s[i])
        i += 1
    if current:
        cells.append("".join(current).strip())
    return cells


def _is_separator_cell(cell: str) -> bool:
    return bool(_SEP_CELL.fullmatch(cell.strip().replace(" ", "")))


def _is_separator_row(cells: list[str]) -> bool:
    nonempty = [c for c in cells if c.strip()]
    return bool(nonempty) and all(_is_separator_cell(c) for c in nonempty)


def _normalize_header_cell(cell: str) -> str:
    return cell.replace("**", "").replace("`", "").strip()


def _cell_segment_end(raw: str) -> int:
    """Link scans stay inside one cell/row: newline or unescaped pipe ends them."""
    nl = raw.find("\n")
    end = len(raw) if nl == -1 else nl
    i = 0
    while i < end:
        pipe = raw.find("|", i, end)
        if pipe == -1:
            return end
        if pipe == 0 or raw[pipe - 1] != "\\":
            return pipe
        i = pipe + 1
    return end


def _paren_closes(s: str) -> list[int]:
    """Matching ')' index for each '(', else -1. One O(n) pass, no backtracking."""
    closes = [-1] * len(s)
    stack: list[int] = []
    for i, ch in enumerate(s):
        if ch == "(":
            stack.append(i)
        elif ch == ")" and stack:
            opens = stack.pop()
            closes[opens] = i
    return closes


def _strip_markdown_links(raw: str) -> str:
    """Replace [text](dest) with text; dest is closed by a matching parenthesis."""
    if "]" not in raw:
        return raw
    end = _cell_segment_end(raw)
    segment = raw[:end]
    suffix = raw[end:]
    if "]" not in segment:
        return raw
    n = len(segment)
    closes = _paren_closes(segment) if "(" in segment else None
    out: list[str] = []
    copied = 0
    i = 0
    next_close = -1  # forward cursor: next ']' at or after the last search
    while True:
        i = segment.find("[", i)
        if i == -1:
            break
        if next_close < i + 1:
            next_close = segment.find("]", i + 1) if i + 1 < n else -1
        if next_close == -1:
            break
        if next_close > i + LINK_LOOKAHEAD:
            i = next_close - LINK_LOOKAHEAD
            continue
        close = next_close
        if (
            closes is not None
            and close + 1 < n
            and segment[close + 1] == "("
        ):
            dest_close = closes[close + 1]
            if dest_close != -1 and dest_close <= i + LINK_LOOKAHEAD:
                out.append(segment[copied:i])
                out.append(segment[i + 1 : close])
                copied = dest_close + 1
                i = dest_close + 1
                next_close = -1
                continue
        # Failed candidate: consume through this ] — never re-visit.
        i = close + 1
        next_close = -1
    if not out:
        return raw
    out.append(segment[copied:])
    return "".join(out) + suffix


def _normalize_key(raw: str) -> str | None:
    if not isinstance(raw, str):
        return None
    s = _strip_markdown_links(raw)
    s = s.replace("**", "").replace("`", "")
    if "(" in s:
        s = s.split("(", 1)[0]
    if "references/" in s.lower() or ".md" in s.lower():
        return None
    if "/" in s:
        s = s.rsplit("/", 1)[-1]
    s = s.strip().rstrip(_TRAILING_PUNCT).strip()
    if not s:
        return None
    if "references/" in s.lower() or ".md" in s.lower():
        return None
    return s.lower()
