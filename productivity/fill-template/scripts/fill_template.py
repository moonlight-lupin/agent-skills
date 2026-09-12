"""Template-fill (mail-merge) helper.

Turn ONE master template (a .docx letter/form or a .xlsx form) plus a data table
(one row per output) into MANY filled copies — preserving the master's layout and
branding exactly, swapping only tokens.

The reverse path (this round: .docx only) takes a filled/example document and
derives a tokenised template + data-table skeleton so fill can round-trip the
values.

Token syntax: ``{{TokenName}}`` (whitespace inside the braces is ignored).

The flow the SKILL drives, and the functions that serve each step:

    0. EXTRACT   extract_template(src, out_dir) -> tokenised copy + skeleton CSV
                                                  + a mapping report (confirm
                                                  before reuse).
    1. ANALYSE   read_content(path)            -> the master's text, so you can
                                                  spot the parts that vary.
    2. TOKENISE  tokenise(src, dst, mapping)   -> write a tokenised copy: each
                                                  variable phrase becomes {{Token}}.
                 tokens_in(path)               -> list the tokens now in the template.
    3. DATA      load_rows(path)               -> (headers, [row-dict, ...]) from
                                                  .xlsx / .csv.
    4. GENERATE  generate(tmpl, rows, ...)     -> one filled file per row + a report.
                 rows may be a list of dicts *or* the (headers, rows) tuple
                 returned by load_rows().

Design rules (from SKILL.md ## Principles):
  * Deterministic — same inputs, same outputs. No network, no model calls here.
  * Never invent — a token with no data for a row is written as a VISIBLE flag
    («MISSING: Token»), never a silent blank, and is listed in the report.
    Extract keeps ambiguous spans literal and lists them under ``uncertain``.
  * Preserve the master — replacement edits only the runs/cells a token occupies;
    formatting elsewhere is untouched. Extract never writes back to *src*.

Usage as a library:

    from fill_template import (
        read_content, tokenise, tokens_in, load_rows, generate, extract_template,
    )

    # 0. extract a reusable template from a filled example
    ext = extract_template("filled_letters.docx", "extracted")
    # ext["mapping"] is the confirm-before-reuse digest

    # 1. analyse
    print(read_content("ConfirmationLetter_master.docx"))

    # 2. tokenise a copy (mapping confirmed with the user)
    tokenise("ConfirmationLetter_master.docx", "ConfirmationLetter_tokenised.docx",
             [{"find": "Ms Jordan Lee", "token": "RecipientName"},
              {"find": "$1,000,000",  "token": "Amount"}])

    # 3. load the data table
    headers, rows = load_rows("recipients.xlsx")

    # 4. generate one file per row
    report = generate(
        "ConfirmationLetter_tokenised.docx", rows,
        token_to_column={"RecipientName": "Name"},
        outdir="out",
        name_pattern="ConfirmationLetter_{Name}",
    )
"""

from __future__ import annotations

import csv
import datetime
import os
import re
from collections import Counter, defaultdict
from pathlib import Path

import openpyxl
from docx import Document
from docx.oxml.ns import qn

_W_TR = qn("w:tr")
_W_TC = qn("w:tc")

# ----------------------------------------------------------------------------
# Token plumbing
# ----------------------------------------------------------------------------

TOKEN_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


def _token(name: str) -> str:
    return "{{" + name + "}}"


def _missing(name: str) -> str:
    # Visible, greppable, never a silent blank.
    return f"«MISSING: {name}»"


def _try_parse_date(s: str) -> datetime.date | None:
    """Try to parse a string as an ISO date (YYYY-MM-DD or YYYY/MM/DD).

    CSV data comes in as strings, not datetime objects — this lets _fmt_value
    still render them as DD MMM YYYY. Returns None if the string isn't a date
    (so non-date strings pass through untouched).
    """
    s = s.strip()
    if not s:
        return None
    # Accept YYYY-MM-DD or YYYY/MM/DD (the common ISO / spreadsheet export forms).
    for sep in ("-", "/"):
        parts = s.split(sep)
        if len(parts) == 3:
            try:
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                # Sanity-check month/day so "2026-13-01" doesn't silently parse.
                if 1 <= m <= 12 and 1 <= d <= 31:
                    return datetime.date(y, m, d)
            except (ValueError, TypeError):
                pass
    return None


def _fmt_value(v) -> str:
    """House-style scalar formatting for a data value.

    Dates -> DD MMM YYYY (datetime objects from .xlsx, and ISO date strings from
    .csv like '2026-07-01'); whole-number floats lose the trailing .0; everything
    else is str(). Currency/precision formatting is the caller's job (format the
    column in the data file) — this only handles the obvious cases.
    """
    if v is None:
        return ""
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.strftime("%d %b %Y")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    # CSV dates arrive as strings — try to parse common ISO date formats so they
    # render as DD MMM YYYY, matching .xlsx datetime behaviour. Non-date strings
    # (names, references, amounts) fall through to str() untouched.
    if isinstance(v, str):
        parsed = _try_parse_date(v)
        if parsed is not None:
            return parsed.strftime("%d %b %Y")
    return str(v)


# ----------------------------------------------------------------------------
# Run-aware literal replacement (the .docx hard part)
# ----------------------------------------------------------------------------

def _find_matches(text: str, finds: list[str]) -> list[tuple[int, int, str]]:
    """Left-to-right, non-overlapping matches of any literal in *finds*.

    Returns (start, end, matched_find). At each position the LONGEST matching
    literal wins, so "{{A}}" is preferred over a stray "{{".
    """
    matches: list[tuple[int, int, str]] = []
    i, n = 0, len(text)
    while i < n:
        hit = None
        for f in finds:
            if f and text.startswith(f, i) and (hit is None or len(f) > len(hit)):
                hit = f
        if hit:
            matches.append((i, i + len(hit), hit))
            i += len(hit)
        else:
            i += 1
    return matches


def _apply_spans(paragraph, spans: list[tuple[int, int, str]]) -> int:
    """Replace [start:end] slices in *paragraph* with the given strings.

    Spans are applied right-to-left so earlier offsets stay valid. The
    replacement lands in the run where the span begins (inheriting that run's
    formatting); any other runs the span covers are trimmed. Runs outside every
    span are left untouched.
    """
    runs = paragraph.runs
    if not runs or not spans:
        return 0
    for start, end, repl in sorted(spans, key=lambda s: s[0], reverse=True):
        pos = 0
        first = True
        for r in runs:
            r_start, r_end = pos, pos + len(r.text)
            pos = r_end
            if r_end <= start or r_start >= end:
                continue
            local_start = max(r_start, start) - r_start
            local_end = min(r_end, end) - r_start
            before, after = r.text[:local_start], r.text[local_end:]
            if first:
                r.text = before + repl + after
                first = False
            else:
                r.text = before + after
    return len(spans)


def _replace_in_paragraph(paragraph, repl_for: dict) -> int:
    """Replace literals in one paragraph, preserving run formatting.

    *repl_for* maps a literal -> its replacement string. Matches are located in
    the paragraph's concatenated run text, then applied via ``_apply_spans``.
    """
    runs = paragraph.runs
    if not runs:
        return 0
    text = "".join(r.text for r in runs)
    matches = _find_matches(text, list(repl_for.keys()))
    if not matches:
        return 0
    spans = [(start, end, repl_for[found]) for start, end, found in matches]
    return _apply_spans(paragraph, spans)


def _iter_paragraphs(doc_or_container):
    """Yield every paragraph in a document/cell: body, tables (recursively),
    and — for a Document — each section's header and footer."""
    for p in doc_or_container.paragraphs:
        yield p
    for table in doc_or_container.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from _iter_paragraphs(cell)
    # Headers/footers only exist on a Document, not on a _Cell.
    sections = getattr(doc_or_container, "sections", None)
    if sections is not None:
        for section in sections:
            for hf in (section.header, section.first_page_header,
                       section.even_page_header, section.footer,
                       section.first_page_footer, section.even_page_footer):
                for p in hf.paragraphs:
                    yield p
                for table in hf.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            yield from _iter_paragraphs(cell)


# ----------------------------------------------------------------------------
# 1. ANALYSE
# ----------------------------------------------------------------------------

def read_content(path: str) -> str:
    """Return the master's readable text so the variable parts can be spotted.

    .docx -> paragraph and table text (and header/footer text), one block per line.
    Repeated paragraph text is shown once with a ``(×N)`` count so the user sees
    every location the ``tokenise`` hits will touch (e.g. a name in both the body
    and the header). .xlsx -> each non-empty cell as ``Sheet!A1: value`` (cells are
    where tokens go).
    """
    ext = Path(path).suffix.lower()
    if ext == ".docx":
        doc = Document(path)
        counts: Counter = Counter()
        for p in _iter_paragraphs(doc):
            t = p.text.strip()
            if t:
                counts[t] += 1
        lines = []
        for text, n in counts.items():
            lines.append(text if n == 1 else f"{text}  (×{n})")
        return "\n".join(lines)
    if ext == ".xlsx":
        wb = openpyxl.load_workbook(path, data_only=True)
        lines = []
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value not in (None, ""):
                        lines.append(f"{ws.title}!{cell.coordinate}: {cell.value}")
        return "\n".join(lines)
    raise ValueError(f"Unsupported template type: {ext} (use .docx or .xlsx)")


# ----------------------------------------------------------------------------
# 2. TOKENISE
# ----------------------------------------------------------------------------

def tokenise(src: str, dst: str, mapping: list[dict]) -> dict:
    """Write a tokenised copy of *src* to *dst*.

    *mapping* is a list of ``{"find": <exact phrase in the master>, "token":
    <TokenName>}``. Longer phrases are applied first so a phrase that contains a
    shorter one is not pre-empted. Returns a report: per-token hit counts and any
    phrase that was not found (so it can be corrected before generating).
    """
    repl_for = {}
    # Longest find first => correct precedence inside a single paragraph/cell.
    for m in sorted(mapping, key=lambda d: len(d["find"]), reverse=True):
        repl_for[m["find"]] = _token(m["token"])
    counts = {m["token"]: 0 for m in mapping}
    find_to_token = {m["find"]: m["token"] for m in mapping}

    ext = Path(src).suffix.lower()
    if ext == ".docx":
        doc = Document(src)
        for p in _iter_paragraphs(doc):
            text = "".join(r.text for r in p.runs)
            for start, end, found in _find_matches(text, list(repl_for.keys())):
                counts[find_to_token[found]] += 1
            _replace_in_paragraph(p, repl_for)
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        doc.save(dst)
    elif ext == ".xlsx":
        wb = openpyxl.load_workbook(src)
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str):
                        new = cell.value
                        for find in repl_for:
                            if find in new:
                                counts[find_to_token[find]] += new.count(find)
                                new = new.replace(find, repl_for[find])
                        if new != cell.value:
                            cell.value = new
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        wb.save(dst)
    else:
        raise ValueError(f"Unsupported template type: {ext} (use .docx or .xlsx)")

    not_found = [m["token"] for m in mapping if counts[m["token"]] == 0]
    return {"dst": dst, "hits": counts, "not_found": not_found}


def tokens_in(path: str) -> list[str]:
    """List the distinct tokens present in a (tokenised) template, in first-seen
    order — used to validate the token->column map before generating."""
    text = read_content(path)
    seen, out = set(), []
    for name in TOKEN_RE.findall(text):
        name = name.strip()
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


# ----------------------------------------------------------------------------
# 3. DATA
# ----------------------------------------------------------------------------

def load_rows(path: str) -> tuple[list[str], list[dict]]:
    """Load the data table. First row = headers; each later row = one output.

    .xlsx -> first worksheet, values only (formulas evaluated by the last app to
    save the file). .csv -> DictReader. Returns (headers, [row-dict, ...]).
    """
    ext = Path(path).suffix.lower()
    if ext == ".xlsx":
        wb = openpyxl.load_workbook(path, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return [], []
        headers = [str(h).strip() if h is not None else "" for h in header_row]
        out = []
        for raw in rows_iter:
            if all(c is None or str(c).strip() == "" for c in raw):
                continue  # skip wholly blank rows
            out.append({headers[i]: raw[i] if i < len(raw) else None
                        for i in range(len(headers))})
        return headers, out
    if ext == ".csv":
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = [h.strip() for h in (reader.fieldnames or [])]
            out = [dict(r) for r in reader
                   if any((v or "").strip() for v in r.values())]
        return headers, out
    raise ValueError(f"Unsupported data type: {ext} (use .xlsx or .csv)")


# ----------------------------------------------------------------------------
# 4. GENERATE
# ----------------------------------------------------------------------------

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_name(stem: str) -> str:
    stem = _ILLEGAL.sub("_", stem).strip().strip(".")
    stem = re.sub(r"\s+", " ", stem)
    return stem or "output"


def _resolve_map(template_tokens: list[str], token_to_column: dict | None,
                 headers: list[str]) -> dict:
    """Default mapping: token name == column header (case-insensitive). An
    explicit *token_to_column* overrides per token."""
    token_to_column = dict(token_to_column or {})
    lower = {h.lower(): h for h in headers}
    for tok in template_tokens:
        if tok not in token_to_column and tok.lower() in lower:
            token_to_column[tok] = lower[tok.lower()]
    return token_to_column


def _fill_one(template_path: str, values: dict, out_path: str) -> list[str]:
    """Write one filled copy. *values* maps token -> already-stringified value
    (missing tokens absent => flagged). Returns the list of tokens left missing."""
    ext = Path(template_path).suffix.lower()
    tmpl_tokens = tokens_in(template_path)
    repl_for, missing = {}, []
    for tok in tmpl_tokens:
        if tok in values and values[tok] != "":
            repl_for[_token(tok)] = values[tok]
        else:
            repl_for[_token(tok)] = _missing(tok)
            missing.append(tok)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    if ext == ".docx":
        doc = Document(template_path)
        for p in _iter_paragraphs(doc):
            _replace_in_paragraph(p, repl_for)
        doc.save(out_path)
    elif ext == ".xlsx":
        wb = openpyxl.load_workbook(template_path)
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and "{{" in cell.value:
                        new = cell.value
                        for t, r in repl_for.items():
                            new = new.replace(t, r)
                        cell.value = new
        wb.save(out_path)
    else:
        raise ValueError(f"Unsupported template type: {ext} (use .docx or .xlsx)")
    return missing


def _row_dicts(rows):
    """Accept list[dict] or the ``(headers, rows)`` tuple from load_rows()."""
    if isinstance(rows, tuple) and len(rows) == 2:
        _headers, data = rows
        if isinstance(data, list) and (not data or isinstance(data[0], dict)):
            return data
        raise TypeError(
            "generate() rows must be list[dict] or the (headers, list[dict]) "
            f"tuple from load_rows(); got tuple with {type(data).__name__} rows"
        )
    if isinstance(rows, list) and (not rows or isinstance(rows[0], dict)):
        return rows
    raise TypeError(
        "generate() rows must be list[dict] or the (headers, list[dict]) "
        f"tuple from load_rows(); got {type(rows).__name__}"
    )


def generate(template_path: str, rows: list[dict] | tuple, token_to_column: dict | None = None,
             outdir: str = "out", name_pattern: str | None = None) -> dict:
    """Generate one filled file per row.

    template_path  the TOKENISED master (.docx or .xlsx).
    rows           list of row-dicts from load_rows(), or the (headers, rows)
                   tuple load_rows() itself returns.
    token_to_column  optional {token: column}. Tokens not given here default to
                   the column whose header matches the token name (case-insensitive).
    outdir         output folder (created if absent).
    name_pattern   output stem, with {Column} placeholders filled from the row,
                   e.g. "ConfirmationLetter_{Name}". Defaults to
                   "<template-stem>_<n>". The template's extension is kept.

    Returns a report:
      {"written":[{"file","row","missing":[...]}], "skipped":[...],
       "unmapped_tokens":[...], "rows":N, "outdir":...}
    Never invents data: an unmapped token, or a mapped column that is blank for a
    row, is written as «MISSING: Token» and recorded.
    """
    rows = _row_dicts(rows)
    ext = Path(template_path).suffix.lower()
    tmpl_tokens = tokens_in(template_path)
    headers = list(rows[0].keys()) if rows else []
    mapping = _resolve_map(tmpl_tokens, token_to_column, headers)
    unmapped = [t for t in tmpl_tokens if t not in mapping]

    outdir_p = Path(outdir)
    outdir_p.mkdir(parents=True, exist_ok=True)
    stem_default = Path(template_path).stem.replace("_tokenised", "")

    written, skipped, used_names = [], [], set()
    for n, row in enumerate(rows, start=1):
        values = {tok: _fmt_value(row.get(mapping[tok]))
                  for tok in tmpl_tokens if tok in mapping}
        # filename
        if name_pattern:
            try:
                stem = name_pattern.format(**{k: _fmt_value(v) for k, v in row.items()})
            except KeyError as e:
                skipped.append({"row": n, "reason": f"name_pattern column {e} not in data"})
                continue
        else:
            stem = f"{stem_default}_{n}"
        stem = _safe_name(stem)
        candidate, k = stem, 2
        while candidate in used_names:  # avoid clobbering same-named rows
            candidate = f"{stem} ({k})"
            k += 1
        used_names.add(candidate)

        out_path = outdir_p / f"{candidate}{ext}"
        missing = _fill_one(template_path, values, str(out_path))
        written.append({"file": str(out_path), "row": n, "missing": missing})

    return {
        "written": written,
        "skipped": skipped,
        "unmapped_tokens": unmapped,
        "rows": len(rows),
        "outdir": str(outdir_p),
    }


# ----------------------------------------------------------------------------
# 0. EXTRACT (filled document → tokenised template + skeleton)
# ----------------------------------------------------------------------------
#
# Domain shape: a PatternSlot is one field aligned across instances
#   {token, values[i], wheres[i], starts[i], ends[i], paragraphs[i]}
# starts/ends are character offsets in that instance's paragraph. Tokenisation
# replaces those located spans, never a global find of the literal.
# Instances are ordered occurrences of a repeating paragraph-fingerprint group.
# Token names come from the matcher that found the span (Recipient, Amount, …).

_MONTHS = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"

# First matcher to claim a span wins. InvoiceRef before AccountRef so INV-1024
# is not classified as an account code.
_VALUE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("InvoiceRef", re.compile(r"INV-\d+")),
    ("Amount", re.compile(r"\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?")),
    ("Date", re.compile(rf"\b\d{{1,2}} {_MONTHS} \d{{4}}\b")),
    ("AccountRef", re.compile(r"\b[A-Z]{2,}-\d+(?![-\d])")),
    ("Recipient", re.compile(r"(?<=Dear )[^,.\n]+", re.IGNORECASE)),
]

_TOKEN_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _paragraph_xml_id(paragraph) -> int:
    xml = getattr(paragraph, "_p", None)
    if xml is None:
        xml = paragraph._element
    return id(xml)


def _collect_table_texts(table, prefix: str) -> list[tuple[str, str, object]]:
    records: list[tuple[str, str, object]] = []
    for ri, row in enumerate(table.rows, start=1):
        seen_tc: set[int] = set()
        ci = 0
        for cell in row.cells:
            tc_id = id(cell._tc)
            if tc_id in seen_tc:
                continue
            seen_tc.add(tc_id)
            ci += 1
            cell_prefix = f"{prefix} r{ri} c{ci}"
            for i, p in enumerate(cell.paragraphs, start=1):
                if p.text.strip():
                    records.append((p.text, f"{cell_prefix} paragraph {i}", p))
            for ti, nested in enumerate(cell.tables, start=1):
                records.extend(_collect_table_texts(nested, f"{cell_prefix} table {ti}"))
    return records


def _collect_located_texts(doc) -> list[tuple[str, str, object]]:
    """Body, nested tables, headers/footers — same coverage as _iter_paragraphs."""
    records: list[tuple[str, str, object]] = []
    for i, p in enumerate(doc.paragraphs, start=1):
        if p.text.strip():
            records.append((p.text, f"paragraph {i}", p))
    for ti, table in enumerate(doc.tables, start=1):
        records.extend(_collect_table_texts(table, f"table {ti}"))
    for si, section in enumerate(getattr(doc, "sections", []), start=1):
        for label, hf in (
            ("header", section.header),
            ("first-page header", section.first_page_header),
            ("even-page header", section.even_page_header),
            ("footer", section.footer),
            ("first-page footer", section.first_page_footer),
            ("even-page footer", section.even_page_footer),
        ):
            # Accessing paragraphs on a linked first/even header creates a
            # spurious part (header2.xml). Skip linked definitions.
            if hf.is_linked_to_previous:
                continue
            for i, p in enumerate(hf.paragraphs, start=1):
                if p.text.strip():
                    records.append((p.text, f"section {si} {label} paragraph {i}", p))
            for ti, table in enumerate(hf.tables, start=1):
                records.extend(
                    _collect_table_texts(table, f"section {si} {label} table {ti}")
                )
    seen: set[int] = set()
    unique: list[tuple[str, str, object]] = []
    for rec in records:
        xml_id = _paragraph_xml_id(rec[2])
        if xml_id in seen:
            continue
        seen.add(xml_id)
        unique.append(rec)
    return unique


def _fingerprint(text: str) -> str:
    t = text
    for _kind, rx in _VALUE_PATTERNS:
        t = rx.sub("{}", t)
    return re.sub(r"\s+", " ", t).strip()


def _group_instances(
    records: list[tuple],
) -> tuple[list[list[tuple]], list[str]]:
    """Split records into repeating pattern instances.

    Paragraphs that share a fingerprint and appear ≥2 times become roles of
    one pattern; each instance is one occurrence of every role, in document
    order. No repeats → the whole document is a single instance. Extra tuple
    fields (paragraph objects) travel with the record.
    """
    uncertain: list[str] = []
    if not records:
        return [[]], uncertain

    fps = [_fingerprint(t) for t, *_ in records]
    groups: dict[str, list[int]] = {}
    order: list[str] = []
    for i, fp in enumerate(fps):
        if fp not in groups:
            groups[fp] = []
            order.append(fp)
        groups[fp].append(i)

    repeating = [fp for fp in order if len(groups[fp]) >= 2]
    if not repeating:
        return [records], uncertain

    varying = [
        fp for fp in repeating
        if len({_typed_signature(records[i][0]) for i in groups[fp]}) > 1
    ]
    if not varying:
        return [records], uncertain

    n = min(len(groups[fp]) for fp in repeating)
    for fp in repeating:
        extra = len(groups[fp]) - n
        if extra:
            uncertain.append(
                f"{extra} extra occurrence(s) of pattern {fp!r} not aligned"
            )
    instances = [
        [records[groups[fp][k]] for fp in repeating]
        for k in range(n)
    ]
    return instances, uncertain


def _typed_signature(text: str) -> tuple:
    hits, _notes = _typed_hits(text)
    return tuple((kind, value) for kind, value, _start, _end in hits)


def _typed_hits(text: str) -> tuple[list[tuple[str, str, int, int]], list[str]]:
    """Non-overlapping (kind, value, start, end), left-to-right, first matcher wins.

    A later match that overlaps an earlier claim is trimmed to its unclaimed
    prefix when that prefix is non-empty; otherwise it is skipped. Either way
    a note is returned so the caller can surface the overlap instead of
    dropping a field silently.
    """
    taken = [False] * len(text)
    hits: list[tuple[int, int, str, str]] = []
    notes: list[str] = []
    for kind, rx in _VALUE_PATTERNS:
        for m in rx.finditer(text):
            start, end = m.start(), m.end()
            if start >= end:
                continue
            claimed = taken[start:end]
            if all(claimed):
                if kind == "AccountRef" and any(
                    hk == "InvoiceRef" and hs <= start and end <= he
                    for hs, he, hk, _hv in hits
                ):
                    continue
                notes.append(f"overlapping {kind} skipped at {start}:{end}")
                continue
            if any(claimed):
                new_end = start
                while new_end < end and not taken[new_end]:
                    new_end += 1
                notes.append(
                    f"overlapping {kind} trimmed from {start}:{end} to {start}:{new_end}"
                )
                if new_end <= start:
                    continue
                end = new_end
            for i in range(start, end):
                taken[i] = True
            raw = text[start:end]
            value = raw.strip()
            if value != raw:
                lead = len(raw) - len(raw.lstrip())
                trail = len(raw) - len(raw.rstrip())
                start += lead
                end -= trail
            if start < end and value:
                hits.append((start, end, kind, value))
    hits.sort()
    return [(kind, value, start, end) for start, end, kind, value in hits], notes


def _unique_token(kind: str, used: set[str]) -> str:
    base = kind if _TOKEN_NAME_RE.match(kind) else "Value"
    if base not in used:
        used.add(base)
        return base
    n = 2
    while f"{base}{n}" in used:
        n += 1
    name = f"{base}{n}"
    used.add(name)
    return name


def _slots_for_role(
    texts: list[str],
    wheres: list[str],
    used: set[str],
    uncertain: list[str],
    *,
    paragraphs: list | None = None,
    promote_constants: bool = False,
) -> list[dict]:
    """Align typed values across instances of one paragraph-role into slots."""
    parsed: list[list[tuple[str, str, int, int]]] = []
    for i, t in enumerate(texts):
        hits, notes = _typed_hits(t)
        parsed.append(hits)
        where = wheres[i] if i < len(wheres) else f"instance {i}"
        for n in notes:
            uncertain.append(f"{n} at {where}")
    kinds = [[k for k, *_ in p] for p in parsed]
    if not kinds or not kinds[0]:
        if any(texts[0] != t for t in texts[1:]):
            uncertain.append(
                f"untyped variation at {wheres[0]}; left literal"
            )
        return []
    if any(k != kinds[0] for k in kinds[1:]):
        uncertain.append(
            f"typed-value pattern mismatch across instances at {wheres[0]}"
        )
        return []

    paras = paragraphs or [None] * len(texts)
    slots: list[dict] = []
    for idx, kind in enumerate(kinds[0]):
        values = [p[idx][1] for p in parsed]
        if len(set(values)) <= 1 and not promote_constants:
            continue
        token = _unique_token(kind, used)
        slots.append({
            "token": token,
            "values": values,
            "wheres": wheres,
            "starts": [p[idx][2] for p in parsed],
            "ends": [p[idx][3] for p in parsed],
            "paragraphs": paras,
        })
    return slots


def _delete_paragraph(paragraph) -> None:
    el = paragraph._element
    parent = el.getparent()
    if parent is not None:
        parent.remove(el)


def _xml_ancestor(el, tag: str):
    while el is not None:
        if el.tag == tag:
            return el
        el = el.getparent()
    return None


def _clear_paragraph_keep_p(paragraph) -> None:
    paragraph.text = ""


def _paragraph_run_text(paragraph) -> str:
    return "".join(r.text or "" for r in paragraph.runs)


def _collapse_extra_instances(instances: list[list[tuple]]) -> int:
    """Drop extra instances. Extra-only table rows are removed whole.

    Mixed rows keep one empty ``<w:p>`` per extra cell so ``<w:tc>`` stays
    valid. Body paragraphs not in a row are deleted. Returns how many extra
    instances were collapsed.
    """
    if len(instances) <= 1:
        return 0
    retained: set[int] = set()
    retained_trs: list = []
    for rec in instances[0]:
        para = rec[2] if len(rec) > 2 else None
        if para is None:
            continue
        retained.add(_paragraph_xml_id(para))
        tr = _xml_ancestor(para._element, _W_TR)
        if tr is not None:
            retained_trs.append(tr)

    extra_paras: list = []
    seen_extra: set[int] = set()
    for inst in instances[1:]:
        for rec in inst:
            para = rec[2] if len(rec) > 2 else None
            if para is None:
                continue
            pid = _paragraph_xml_id(para)
            if pid in retained or pid in seen_extra:
                continue
            seen_extra.add(pid)
            extra_paras.append(para)

    extras_by_tr: list[tuple] = []
    extras_no_tr: list = []
    seen_tr: list = []
    for para in extra_paras:
        tr = _xml_ancestor(para._element, _W_TR)
        if tr is None:
            extras_no_tr.append(para)
            continue
        bucket = None
        for i, seen in enumerate(seen_tr):
            if tr == seen:
                bucket = i
                break
        if bucket is None:
            seen_tr.append(tr)
            extras_by_tr.append((tr, [para]))
        else:
            extras_by_tr[bucket][1].append(para)

    deleted_tr: list = []
    for tr, paras in extras_by_tr:
        if any(tr == retained for retained in retained_trs):
            for para in paras:
                _clear_paragraph_keep_p(para)
            continue
        parent = tr.getparent()
        if parent is not None and not any(tr == d for d in deleted_tr):
            parent.remove(tr)
            deleted_tr.append(tr)

    for para in extras_no_tr:
        parent = para._element.getparent()
        if parent is not None and parent.tag == _W_TC:
            _clear_paragraph_keep_p(para)
        else:
            _delete_paragraph(para)
    return len(instances) - 1


def _require_extract_basename(name: str) -> str:
    if os.path.isabs(name) or Path(name).is_absolute():
        raise ValueError(
            f"extract_template name must not be an absolute path: {name!r}"
        )
    if "/" in name or "\\" in name:
        raise ValueError(
            f"extract_template name must not contain path separators: {name!r}"
        )
    if name in (".", "..") or ".." in Path(name).parts:
        raise ValueError(
            f"extract_template name must not contain '..' segments: {name!r}"
        )
    if not name or name.strip() != name:
        raise ValueError(f"extract_template name must be a basename, got {name!r}")
    return name


def _assert_under_outdir(out_p: Path, dest: Path) -> None:
    parent = Path(os.path.realpath(out_p))
    child = Path(os.path.realpath(dest))
    prefix = str(parent) if str(parent).endswith(os.sep) else str(parent) + os.sep
    if not str(child).startswith(prefix):
        raise ValueError(
            f"extract_template would write {dest} outside out_dir {out_p}"
        )


def _write_skeleton(path: Path, token_names: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        if not token_names:
            f.write("\n")
            return
        w = csv.DictWriter(f, fieldnames=token_names, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def extract_template(src: str, out_dir: str, *, name: str | None = None) -> dict:
    """Derive a tokenised .docx template + CSV skeleton from a filled example.

    Writes into *out_dir*:
      <name>_tokenised.docx  — copy of *src* with varying values as {{Token}}
      <name>_data.csv        — header = token names, one row per instance

    *name* defaults to the source stem. Returns a report with ``mapping``
    (literal / token / where, for the confirm-before-reuse gate) and
    ``uncertain`` (spans left literal rather than guessed). Does not modify
    *src*. .docx only.
    """
    src_p = Path(src)
    if src_p.is_dir():
        raise IsADirectoryError(
            f"extract_template expected a .docx file, got a directory: {src_p}"
        )
    if not src_p.is_file():
        raise FileNotFoundError(f"extract_template source not found: {src_p}")
    if src_p.suffix.lower() != ".docx":
        raise ValueError(
            f"extract_template supports .docx only, got {src_p.suffix or 'no extension'}"
        )
    out_p = Path(out_dir)
    out_p.mkdir(parents=True, exist_ok=True)
    stem = src_p.stem if name is None else _require_extract_basename(name)
    tmpl_path = out_p / f"{stem}_tokenised.docx"
    csv_path = out_p / f"{stem}_data.csv"
    _assert_under_outdir(out_p, tmpl_path)
    _assert_under_outdir(out_p, csv_path)

    src_real = os.path.realpath(src_p)

    def _aliases_source(dest: Path) -> bool:
        try:
            return dest.exists() and os.path.samefile(src_p, dest)
        except OSError:
            return False

    if (
        os.path.realpath(tmpl_path) == src_real
        or os.path.realpath(csv_path) == src_real
        or _aliases_source(tmpl_path)
        or _aliases_source(csv_path)
    ):
        raise ValueError(
            "extract_template would overwrite the source file; "
            "pass a different name or out_dir"
        )

    doc = Document(str(src_p))
    records = _collect_located_texts(doc)
    instances, uncertain = _group_instances(records)

    pre_existing = tokens_in(str(src_p))
    used: set[str] = set(pre_existing)
    slots: list[dict] = []
    promote_constants = len(instances) == 1
    n_roles = len(instances[0]) if instances else 0
    for j in range(n_roles):
        recs = [inst[j] for inst in instances]
        texts = [r[0] for r in recs]
        wheres = [r[1] for r in recs]
        paragraphs = [r[2] for r in recs]
        slots.extend(_slots_for_role(
            texts, wheres, used, uncertain,
            paragraphs=paragraphs,
            promote_constants=promote_constants,
        ))

    spans_by_para: dict[int, list[tuple[int, int, str]]] = defaultdict(list)
    para_by_id: dict[int, object] = {}
    hits_counts: dict[str, int] = {s["token"]: 0 for s in slots}
    not_found: list[str] = []
    for slot in slots:
        if not slot["paragraphs"] or not slot["values"]:
            continue
        para = slot["paragraphs"][0]
        start, end = slot["starts"][0], slot["ends"][0]
        token = slot["token"]
        if para is None:
            continue
        full = para.text
        run_text = _paragraph_run_text(para)
        span_ok = 0 <= start < end <= len(full) and full[start:end]
        if run_text != full or not span_ok or full[start:end] not in run_text:
            msg = (
                f"{token} at {slot['wheres'][0]} not in paragraph runs "
                "(hyperlink or complex run); left literal"
            )
            uncertain.append(msg)
            not_found.append(token)
            continue
        pid = id(para)
        para_by_id[pid] = para
        spans_by_para[pid].append((start, end, _token(token)))
        hits_counts[token] += 1
    for pid, spans in spans_by_para.items():
        _apply_spans(para_by_id[pid], spans)
    instances_collapsed = _collapse_extra_instances(instances)
    tmpl_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(tmpl_path))

    dropped = set(not_found)
    kept_slots = [s for s in slots if s["token"] not in dropped]
    token_names = [s["token"] for s in kept_slots]
    data_rows = [
        {s["token"]: s["values"][i] for s in kept_slots}
        for i in range(len(instances))
    ]
    _write_skeleton(csv_path, token_names, data_rows)

    mapping = []
    for slot in kept_slots:
        for val, where in zip(slot["values"], slot["wheres"]):
            mapping.append({
                "literal": val,
                "token": slot["token"],
                "where": where,
            })

    report = {
        "mapping": mapping,
        "uncertain": uncertain,
        "template": str(tmpl_path),
        "skeleton": str(csv_path),
        "tokens": token_names,
        "instances": len(instances),
        "instances_collapsed": instances_collapsed,
        "hits": {t: hits_counts[t] for t in token_names},
        "not_found": not_found,
        "pre_existing_tokens": pre_existing,
    }
    if not token_names:
        report["status"] = "no-tokens"
    if pre_existing:
        report["pre_existing_note"] = (
            "reserved pre-existing token(s) "
            f"{pre_existing}; inferred slots will not reuse these names"
        )
    return report
