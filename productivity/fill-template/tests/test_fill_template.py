#!/usr/bin/env python3
"""Unit tests for fill_template.py — the mail-merge engine.

Run:  python -m pytest productivity/fill-template/tests/test_fill_template.py -v
  or:  python productivity/fill-template/tests/test_fill_template.py

These tests build small synthetic .docx/.xlsx fixtures in a temp dir, so they
don't need any external template files. No network, no credentials.
"""

import sys
import os
import csv
import datetime
import tempfile
import unittest
from pathlib import Path

# Import the module under test (scripts/ is one level up from tests/)
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import fill_template as ft  # noqa: E402
from docx import Document  # noqa: E402
import openpyxl  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers: build small synthetic fixtures
# ---------------------------------------------------------------------------

def _make_docx(path, paragraphs, *, header=None, footer=None):
    """Create a .docx with the given paragraph strings. Optional header/footer text."""
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    if header or footer:
        section = doc.sections[0]
        if header:
            section.header.add_paragraph(header)
        if footer:
            section.footer.add_paragraph(footer)
    doc.save(str(path))


def _make_docx_with_bold(path, before, bold_text, after):
    """Create a .docx where bold_text is in a bold run: [before][bold_text][after]."""
    doc = Document()
    p = doc.add_paragraph()
    p.add_run(before)
    r = p.add_run(bold_text)
    r.bold = True
    p.add_run(after)
    doc.save(str(path))


def _make_xlsx(path, cells, *, formula_cell=None):
    """Create an .xlsx where cells is {coord: value}. Optional formula in a coord."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for coord, val in cells.items():
        ws[coord] = val
    if formula_cell:
        coord, formula = formula_cell
        ws[coord] = formula
    wb.save(str(path))


def _make_data_csv(path, headers, rows):
    """Write a CSV data file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in rows:
            w.writerow(row)


def _make_data_xlsx(path, headers, rows):
    """Write an XLSX data file. Row values can include datetime.date for real date cells."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    wb.save(str(path))


# ---------------------------------------------------------------------------
# _fmt_value — scalar formatting
# ---------------------------------------------------------------------------

class TestFmtValue(unittest.TestCase):
    """_fmt_value: dates, floats, zero, None, strings."""

    def test_none(self):
        self.assertEqual(ft._fmt_value(None), "")

    def test_int(self):
        self.assertEqual(ft._fmt_value(42), "42")

    def test_float_whole(self):
        """Whole-number floats lose the trailing .0."""
        self.assertEqual(ft._fmt_value(1000000.0), "1000000")

    def test_float_fractional(self):
        self.assertEqual(ft._fmt_value(3.14), "3.14")

    def test_zero(self):
        """Zero renders as '0', not '' (it's a real value, not missing)."""
        self.assertEqual(ft._fmt_value(0), "0")
        self.assertEqual(ft._fmt_value(0.0), "0")

    def test_datetime_object(self):
        d = datetime.datetime(2026, 7, 1, 0, 0)
        self.assertEqual(ft._fmt_value(d), "01 Jul 2026")

    def test_date_object(self):
        d = datetime.date(2026, 7, 1)
        self.assertEqual(ft._fmt_value(d), "01 Jul 2026")

    def test_csv_date_string_iso_dash(self):
        """CSV dates arrive as strings — should parse to DD MMM YYYY."""
        self.assertEqual(ft._fmt_value("2026-07-01"), "01 Jul 2026")

    def test_csv_date_string_iso_slash(self):
        self.assertEqual(ft._fmt_value("2026/07/01"), "01 Jul 2026")

    def test_non_date_string_passthrough(self):
        """Strings that aren't dates pass through untouched."""
        self.assertEqual(ft._fmt_value("REF-0001"), "REF-0001")
        self.assertEqual(ft._fmt_value("Ms Jordan Lee"), "Ms Jordan Lee")
        self.assertEqual(ft._fmt_value("1000000"), "1000000")

    def test_already_formatted_date_passthrough(self):
        """'01 Jul 2026' is not an ISO date string — passes through as-is."""
        self.assertEqual(ft._fmt_value("01 Jul 2026"), "01 Jul 2026")

    def test_invalid_month_passthrough(self):
        """Invalid month (13) doesn't parse — passes through as-is."""
        self.assertEqual(ft._fmt_value("2026-13-01"), "2026-13-01")

    def test_invalid_day_passthrough(self):
        """Invalid day (32) doesn't parse — passes through as-is."""
        self.assertEqual(ft._fmt_value("2026-07-32"), "2026-07-32")

    def test_empty_string(self):
        self.assertEqual(ft._fmt_value(""), "")

    def test_reference_with_dashes_not_date(self):
        """REF-0001 has dashes but isn't a date — must not be parsed."""
        self.assertEqual(ft._fmt_value("REF-0001"), "REF-0001")


# ---------------------------------------------------------------------------
# _try_parse_date — the ISO date string parser
# ---------------------------------------------------------------------------

class TestTryParseDate(unittest.TestCase):
    """_try_parse_date: ISO date string detection."""

    def test_valid_iso_dash(self):
        self.assertEqual(ft._try_parse_date("2026-07-01"), datetime.date(2026, 7, 1))

    def test_valid_iso_slash(self):
        self.assertEqual(ft._try_parse_date("2026/07/01"), datetime.date(2026, 7, 1))

    def test_invalid_month(self):
        self.assertIsNone(ft._try_parse_date("2026-13-01"))

    def test_invalid_day(self):
        self.assertIsNone(ft._try_parse_date("2026-07-32"))

    def test_not_a_date(self):
        self.assertIsNone(ft._try_parse_date("REF-0001"))
        self.assertIsNone(ft._try_parse_date("hello"))
        self.assertIsNone(ft._try_parse_date("1000000"))

    def test_empty(self):
        self.assertIsNone(ft._try_parse_date(""))

    def test_two_parts(self):
        """Only two parts (YYYY-MM) is not a full date."""
        self.assertIsNone(ft._try_parse_date("2026-07"))

    def test_four_parts(self):
        """Four parts is not a date."""
        self.assertIsNone(ft._try_parse_date("2026-07-01-extra"))


# ---------------------------------------------------------------------------
# _find_matches — longest-match-wins
# ---------------------------------------------------------------------------

class TestFindMatches(unittest.TestCase):
    """_find_matches: left-to-right, non-overlapping, longest wins."""

    def test_simple_match(self):
        matches = ft._find_matches("hello world", ["world"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0], (6, 11, "world"))

    def test_no_match(self):
        matches = ft._find_matches("hello", ["xyz"])
        self.assertEqual(matches, [])

    def test_longest_wins(self):
        """{{A}} should win over stray {{ — longest match at each position."""
        matches = ft._find_matches("hello {{A}} world", ["{{A}}", "{{"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][2], "{{A}}")

    def test_multiple_matches(self):
        matches = ft._find_matches("aaa bbb aaa", ["aaa"])
        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0][0], 0)
        self.assertEqual(matches[1][0], 8)

    def test_empty_find_ignored(self):
        """Empty find strings are skipped (falsy)."""
        matches = ft._find_matches("hello", ["", "hello"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0][2], "hello")


# ---------------------------------------------------------------------------
# tokenise — .docx path
# ---------------------------------------------------------------------------

class TestTokeniseDocx(unittest.TestCase):
    """tokenise: hit counts, not_found, formatting preservation."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.master = Path(self.tmp) / "master.docx"

    def test_basic_tokenise(self):
        _make_docx(self.master, [
            "Dear Ms Jordan Lee,",
            "We confirm your subscription of $1,000,000, effective 01 Jul 2026. Your reference is REF-0001.",
        ])
        dst = Path(self.tmp) / "tokenised.docx"
        rep = ft.tokenise(str(self.master), str(dst), [
            {"find": "Ms Jordan Lee", "token": "Name"},
            {"find": "$1,000,000", "token": "Amount"},
            {"find": "01 Jul 2026", "token": "EffectiveDate"},
            {"find": "REF-0001", "token": "Reference"},
        ])
        self.assertEqual(rep["not_found"], [])
        self.assertEqual(rep["hits"]["Name"], 1)
        self.assertEqual(rep["hits"]["Amount"], 1)
        self.assertEqual(rep["hits"]["EffectiveDate"], 1)
        self.assertEqual(rep["hits"]["Reference"], 1)

    def test_not_found_reported(self):
        """A phrase that doesn't exist is flagged in not_found."""
        _make_docx(self.master, ["Dear Ms Jordan Lee,"])
        dst = Path(self.tmp) / "tokenised.docx"
        rep = ft.tokenise(str(self.master), str(dst), [
            {"find": "Ms Jordan Lee", "token": "Name"},
            {"find": "NONEXISTENT", "token": "Ghost"},
        ])
        self.assertIn("Ghost", rep["not_found"])
        self.assertEqual(rep["hits"]["Name"], 1)
        self.assertEqual(rep["hits"]["Ghost"], 0)

    def test_repeated_phrase_multiple_hits(self):
        """A phrase that appears multiple times gets counted per occurrence."""
        _make_docx(self.master, [
            "Dear Ms Jordan Lee,",
            "Ms Jordan Lee, your subscription is confirmed.",
        ])
        dst = Path(self.tmp) / "tokenised.docx"
        rep = ft.tokenise(str(self.master), str(dst), [
            {"find": "Ms Jordan Lee", "token": "Name"},
        ])
        self.assertEqual(rep["hits"]["Name"], 2)
        self.assertEqual(rep["not_found"], [])

    def test_header_footer_tokenised(self):
        """Tokens in header/footer are found and replaced."""
        _make_docx(self.master, ["Body text."], header="Header: REF-0001", footer="Footer: REF-0001")
        dst = Path(self.tmp) / "tokenised.docx"
        rep = ft.tokenise(str(self.master), str(dst), [
            {"find": "REF-0001", "token": "Reference"},
        ])
        self.assertEqual(rep["hits"]["Reference"], 2)  # header + footer

    def test_bold_preserved(self):
        """The tokenised position keeps bold formatting."""
        _make_docx_with_bold(self.master, "Dear ", "Ms Jordan Lee", ",")
        dst = Path(self.tmp) / "tokenised.docx"
        rep = ft.tokenise(str(self.master), str(dst), [
            {"find": "Ms Jordan Lee", "token": "Name"},
        ])
        self.assertEqual(rep["hits"]["Name"], 1)
        # Read back and check the tokenised run is bold
        doc = Document(str(dst))
        p = doc.paragraphs[0]
        bold_runs = [r for r in p.runs if r.text == "{{Name}}"]
        self.assertEqual(len(bold_runs), 1)
        self.assertTrue(bold_runs[0].bold)

    def test_longest_find_first(self):
        """Overlapping finds: longer phrase wins, shorter reports not_found."""
        _make_docx(self.master, ["Dear Ms Jordan Lee,"])
        dst = Path(self.tmp) / "tokenised.docx"
        rep = ft.tokenise(str(self.master), str(dst), [
            {"find": "Ms Jordan", "token": "ShortName"},
            {"find": "Ms Jordan Lee", "token": "FullName"},
        ])
        self.assertEqual(rep["hits"]["FullName"], 1)
        self.assertEqual(rep["hits"]["ShortName"], 0)
        self.assertIn("ShortName", rep["not_found"])
        # Verify the text
        tokens = ft.tokens_in(str(dst))
        self.assertIn("FullName", tokens)


# ---------------------------------------------------------------------------
# tokenise — .xlsx path
# ---------------------------------------------------------------------------

class TestTokeniseXlsx(unittest.TestCase):
    """tokenise: .xlsx tokenisation + formula preservation."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.master = Path(self.tmp) / "form.xlsx"

    def test_basic_xlsx_tokenise(self):
        _make_xlsx(self.master, {"B5": "{{Name}}", "B6": "{{Amount}}"})
        dst = Path(self.tmp) / "tokenised.xlsx"
        rep = ft.tokenise(str(self.master), str(dst), [
            {"find": "{{Name}}", "token": "Name"},
            {"find": "{{Amount}}", "token": "Amount"},
        ])
        self.assertEqual(rep["not_found"], [])
        self.assertEqual(rep["hits"]["Name"], 1)
        self.assertEqual(rep["hits"]["Amount"], 1)


# ---------------------------------------------------------------------------
# tokens_in
# ---------------------------------------------------------------------------

class TestTokensIn(unittest.TestCase):
    """tokens_in: lists distinct tokens in first-seen order."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_distinct_tokens(self):
        master = Path(self.tmp) / "master.docx"
        _make_docx(master, ["Dear {{Name}}, amount {{Amount}}, ref {{Reference}}"])
        tokens = ft.tokens_in(str(master))
        self.assertEqual(tokens, ["Name", "Amount", "Reference"])

    def test_repeated_token_once(self):
        master = Path(self.tmp) / "master.docx"
        _make_docx(master, ["{{Name}} says {{Name}} is here"])
        tokens = ft.tokens_in(str(master))
        self.assertEqual(tokens, ["Name"])

    def test_whitespace_in_braces(self):
        master = Path(self.tmp) / "master.docx"
        _make_docx(master, ["Dear {{ Name }}, amount {{Amount}}"])
        tokens = ft.tokens_in(str(master))
        self.assertEqual(set(tokens), {"Name", "Amount"})


# ---------------------------------------------------------------------------
# load_rows — data loading
# ---------------------------------------------------------------------------

class TestLoadRows(unittest.TestCase):
    """load_rows: CSV and XLSX data, blank-row skipping."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_csv(self):
        path = Path(self.tmp) / "data.csv"
        _make_data_csv(path, ["Name", "Amount"], [["Alice", "100"], ["Bob", "200"]])
        headers, rows = ft.load_rows(str(path))
        self.assertEqual(headers, ["Name", "Amount"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Name"], "Alice")
        self.assertEqual(rows[1]["Amount"], "200")

    def test_csv_skips_blank_rows(self):
        path = Path(self.tmp) / "data.csv"
        _make_data_csv(path, ["Name", "Amount"], [
            ["Alice", "100"],
            ["", ""],          # blank — skip
            ["Bob", "200"],
        ])
        _, rows = ft.load_rows(str(path))
        self.assertEqual(len(rows), 2)

    def test_xlsx(self):
        path = Path(self.tmp) / "data.xlsx"
        _make_data_xlsx(path, ["Name", "Amount"], [["Alice", 100], ["Bob", 200]])
        headers, rows = ft.load_rows(str(path))
        self.assertEqual(headers, ["Name", "Amount"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["Name"], "Alice")

    def test_xlsx_datetime_preserved(self):
        """xlsx datetime cells load as datetime objects (so _fmt_value can format them)."""
        path = Path(self.tmp) / "data.xlsx"
        _make_data_xlsx(path, ["Date"], [[datetime.date(2026, 7, 1)]])
        _, rows = ft.load_rows(str(path))
        self.assertIsInstance(rows[0]["Date"], (datetime.datetime, datetime.date))


# ---------------------------------------------------------------------------
# generate — the full pipeline
# ---------------------------------------------------------------------------

class TestGenerate(unittest.TestCase):
    """generate: file production, MISSING flag, unmapped tokens, filename collision."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # Build a tokenised .docx template
        self.tmpl = Path(self.tmp) / "letter_tokenised.docx"
        _make_docx(self.tmpl, [
            "Dear {{Name}},",
            "We confirm your subscription of {{Amount}}, effective {{EffectiveDate}}. Your reference is {{Reference}}.",
        ])

    def test_basic_generate(self):
        data = Path(self.tmp) / "data.csv"
        _make_data_csv(data, ["Recipient", "Amount", "EffectiveDate", "Reference"],
                       [["Ms Jordan Lee", "1000000", "2026-07-01", "REF-0001"]])
        _, rows = ft.load_rows(str(data))
        report = ft.generate(str(self.tmpl), rows,
                             token_to_column={"Name": "Recipient"},
                             outdir=str(Path(self.tmp) / "out"),
                             name_pattern="Letter_{Recipient}")
        self.assertEqual(len(report["written"]), 1)
        self.assertEqual(report["unmapped_tokens"], [])
        self.assertEqual(report["written"][0]["missing"], [])

    def test_missing_flag(self):
        """A blank cell produces a visible MISSING flag."""
        data = Path(self.tmp) / "data.csv"
        _make_data_csv(data, ["Recipient", "Amount", "EffectiveDate", "Reference"],
                       [["Ms Jordan Lee", "", "2026-07-01", "REF-0001"]])  # Amount blank
        _, rows = ft.load_rows(str(data))
        report = ft.generate(str(self.tmpl), rows,
                             token_to_column={"Name": "Recipient"},
                             outdir=str(Path(self.tmp) / "out_missing"),
                             name_pattern="Letter_{Recipient}")
        self.assertIn("Amount", report["written"][0]["missing"])
        # Verify the file contains the MISSING flag
        doc = Document(report["written"][0]["file"])
        text = " ".join(p.text for p in doc.paragraphs)
        self.assertIn("«MISSING: Amount»", text)

    def test_unmapped_token(self):
        """A token with no matching column is flagged as unmapped and MISSING."""
        data = Path(self.tmp) / "data.csv"
        # Data has no Amount column
        _make_data_csv(data, ["Recipient", "EffectiveDate", "Reference"],
                       [["Ms Jordan Lee", "2026-07-01", "REF-0001"]])
        _, rows = ft.load_rows(str(data))
        report = ft.generate(str(self.tmpl), rows,
                             token_to_column={"Name": "Recipient"},
                             outdir=str(Path(self.tmp) / "out_unmapped"),
                             name_pattern="Letter_{Recipient}")
        self.assertIn("Amount", report["unmapped_tokens"])
        self.assertIn("Amount", report["written"][0]["missing"])

    def test_zero_value_not_missing(self):
        """Amount=0 is a real value — shows as 0, not MISSING."""
        data = Path(self.tmp) / "data.csv"
        _make_data_csv(data, ["Recipient", "Amount", "EffectiveDate", "Reference"],
                       [["Test Person", "0", "2026-07-01", "REF-0001"]])
        _, rows = ft.load_rows(str(data))
        report = ft.generate(str(self.tmpl), rows,
                             token_to_column={"Name": "Recipient"},
                             outdir=str(Path(self.tmp) / "out_zero"),
                             name_pattern="Letter_{Recipient}")
        self.assertNotIn("Amount", report["written"][0]["missing"])
        doc = Document(report["written"][0]["file"])
        text = " ".join(p.text for p in doc.paragraphs)
        self.assertIn("subscription of 0", text)

    def test_csv_date_formatted(self):
        """CSV date strings render as DD MMM YYYY (the #1 fix)."""
        data = Path(self.tmp) / "data.csv"
        _make_data_csv(data, ["Recipient", "Amount", "EffectiveDate", "Reference"],
                       [["Test Person", "1000000", "2026-07-01", "REF-0001"]])
        _, rows = ft.load_rows(str(data))
        report = ft.generate(str(self.tmpl), rows,
                             token_to_column={"Name": "Recipient"},
                             outdir=str(Path(self.tmp) / "out_date"),
                             name_pattern="Letter_{Recipient}")
        doc = Document(report["written"][0]["file"])
        text = " ".join(p.text for p in doc.paragraphs)
        self.assertIn("01 Jul 2026", text)

    def test_filename_collision(self):
        """Two rows producing the same filename get deduplicated with (2), (3)."""
        data = Path(self.tmp) / "data.csv"
        _make_data_csv(data, ["Recipient", "Amount", "EffectiveDate", "Reference"],
                       [["Same Name", "100", "2026-07-01", "REF-0001"],
                        ["Same Name", "200", "2026-07-01", "REF-0002"]])
        _, rows = ft.load_rows(str(data))
        report = ft.generate(str(self.tmpl), rows,
                             token_to_column={"Name": "Recipient"},
                             outdir=str(Path(self.tmp) / "out_collide"),
                             name_pattern="Letter_{Recipient}")
        # Both written, neither skipped
        self.assertEqual(len(report["written"]), 2)
        self.assertEqual(report["skipped"], [])
        # Check filenames are unique
        names = [Path(w["file"]).stem for w in report["written"]]
        self.assertEqual(len(set(names)), 2)

    def test_name_pattern_missing_column_skips(self):
        """If name_pattern references a column not in data, row is skipped."""
        data = Path(self.tmp) / "data.csv"
        _make_data_csv(data, ["Recipient", "Amount", "EffectiveDate", "Reference"],
                       [["Alice", "100", "2026-07-01", "REF-0001"]])
        _, rows = ft.load_rows(str(data))
        report = ft.generate(str(self.tmpl), rows,
                             token_to_column={"Name": "Recipient"},
                             outdir=str(Path(self.tmp) / "out_skip"),
                             name_pattern="Letter_{NonExistent}")
        self.assertEqual(len(report["skipped"]), 1)
        self.assertEqual(len(report["written"]), 0)

    def test_default_name_pattern(self):
        """Without name_pattern, files are named <template-stem>_<n>."""
        data = Path(self.tmp) / "data.csv"
        _make_data_csv(data, ["Recipient", "Amount", "EffectiveDate", "Reference"],
                       [["Alice", "100", "2026-07-01", "REF-0001"]])
        _, rows = ft.load_rows(str(data))
        report = ft.generate(str(self.tmpl), rows,
                             token_to_column={"Name": "Recipient"},
                             outdir=str(Path(self.tmp) / "out_default"))
        # Template stem is "letter_tokenised" → "letter" (strips _tokenised)
        fname = Path(report["written"][0]["file"]).name
        self.assertTrue(fname.startswith("letter_") or fname.startswith("Letter_"))

    def test_generate_accepts_load_rows_tuple(self):
        """generate accepts load_rows() output directly (headers, rows)."""
        data = Path(self.tmp) / "data.csv"
        _make_data_csv(data, ["Name", "Amount", "EffectiveDate", "Reference"],
                       [["Alice", "100", "01 Jul 2026", "REF-0001"]])
        loaded = ft.load_rows(str(data))
        report = ft.generate(str(self.tmpl), loaded,
                             outdir=str(Path(self.tmp) / "out_tuple"))
        self.assertEqual(len(report["written"]), 1)
        self.assertEqual(report["written"][0]["missing"], [])
        doc = Document(report["written"][0]["file"])
        text = " ".join(p.text for p in doc.paragraphs)
        self.assertIn("Alice", text)
        self.assertIn("01 Jul 2026", text)


# ---------------------------------------------------------------------------
# generate — .xlsx template path
# ---------------------------------------------------------------------------

class TestGenerateXlsx(unittest.TestCase):
    """generate: .xlsx template — formula preservation."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tmpl = Path(self.tmp) / "form_tokenised.xlsx"
        _make_xlsx(self.tmpl, {"B5": "{{Name}}", "B6": "{{Amount}}"},
                   formula_cell=("B10", "=B6*1.1"))

    def test_xlsx_generate_preserves_formula(self):
        data = Path(self.tmp) / "data.csv"
        _make_data_csv(data, ["Name", "Amount"], [["Alice", "1000000"]])
        _, rows = ft.load_rows(str(data))
        report = ft.generate(str(self.tmpl), rows,
                             outdir=str(Path(self.tmp) / "out_xlsx"),
                             name_pattern="Form_{Name}")
        wb = openpyxl.load_workbook(report["written"][0]["file"])
        ws = wb.active
        self.assertEqual(ws["B5"].value, "Alice")
        self.assertEqual(ws["B6"].value, "1000000")
        # Formula preserved
        self.assertEqual(ws["B10"].value, "=B6*1.1")


# ---------------------------------------------------------------------------
# _safe_name — filename sanitisation
# ---------------------------------------------------------------------------

class TestSafeName(unittest.TestCase):
    """_safe_name: strips illegal filesystem characters."""

    def test_strips_illegal_chars(self):
        self.assertEqual(ft._safe_name('hello:world/test'), "hello_world_test")

    def test_collapses_whitespace(self):
        self.assertEqual(ft._safe_name("hello   world"), "hello world")

    def test_empty_returns_output(self):
        self.assertEqual(ft._safe_name(""), "output")

    def test_strips_dots(self):
        self.assertEqual(ft._safe_name("..test.."), "test")


# ---------------------------------------------------------------------------
# _resolve_map — token→column mapping
# ---------------------------------------------------------------------------

class TestResolveMap(unittest.TestCase):
    """_resolve_map: defaults to token==header (case-insensitive), overrides."""

    def test_case_insensitive_default(self):
        mapping = ft._resolve_map(["Name", "Amount"], None, ["name", "amount", "extra"])
        self.assertEqual(mapping["Name"], "name")
        self.assertEqual(mapping["Amount"], "amount")

    def test_explicit_override(self):
        mapping = ft._resolve_map(["Name"], {"Name": "Recipient"}, ["Recipient", "Name"])
        self.assertEqual(mapping["Name"], "Recipient")

    def test_no_match(self):
        """Token with no matching column is not in the mapping (→ unmapped)."""
        mapping = ft._resolve_map(["Ghost"], None, ["Name", "Amount"])
        self.assertNotIn("Ghost", mapping)


class TestExtractTemplate(unittest.TestCase):
    """Extract direction: located spans, no clobber, reserved names, single-instance."""

    def test_same_literal_in_one_paragraph_is_position_aware(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "pay.docx"
            _make_docx(src, [
                "Pay $10.00; fee $10.00.",
                "Pay $20.00; fee $30.00.",
            ])
            out = tdp / "extracted"
            report = ft.extract_template(str(src), str(out))
            self.assertEqual(report["tokens"], ["Amount", "Amount2"])
            tmpl = next(p for p in out.iterdir() if p.suffix == ".docx")
            text = ft.read_content(str(tmpl))
            self.assertIn("Pay {{Amount}}; fee {{Amount2}}.", text)
            self.assertNotIn("Pay {{Amount}}; fee {{Amount}}.", text)
            csv_path = next(p for p in out.iterdir() if p.suffix == ".csv")
            headers, rows = ft.load_rows(str(csv_path))
            self.assertEqual(headers, ["Amount", "Amount2"])
            self.assertEqual(rows[0]["Amount"], "$10.00")
            self.assertEqual(rows[0]["Amount2"], "$10.00")
            self.assertEqual(rows[1]["Amount"], "$20.00")
            self.assertEqual(rows[1]["Amount2"], "$30.00")
            filled = tdp / "refilled"
            gen = ft.generate(str(tmpl), (headers, rows), outdir=str(filled))
            self.assertEqual(len(gen["written"]), 2)
            file2 = ft.read_content(str(Path(gen["written"][1]["file"])))
            self.assertIn("$30.00", file2)
            self.assertNotIn("Pay $20.00; fee $20.00.", file2.replace("  (×2)", ""))

    def test_refuses_to_clobber_source(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "letter_tokenised.docx"
            _make_docx(src, ["Hello $10.00"])
            before = src.read_bytes()
            with self.assertRaises(ValueError) as cm:
                ft.extract_template(str(src), str(tdp), name="letter")
            self.assertIn("overwrite", str(cm.exception).lower())
            self.assertEqual(src.read_bytes(), before)

    def test_name_none_on_already_tokenised_stem_does_not_clobber(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "letter_tokenised.docx"
            _make_docx(src, ["Pay $10.00 and $20.00.", "Pay $30.00 and $40.00."])
            before = src.read_bytes()
            report = ft.extract_template(str(src), str(tdp), name=None)
            self.assertEqual(src.read_bytes(), before)
            self.assertTrue(report["template"].endswith("letter_tokenised_tokenised.docx"))

    def test_pre_existing_token_names_are_reserved(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "pre.docx"
            _make_docx(src, [
                "Dear Alice, amount {{Amount}} vs $20.00",
                "Dear Bob, amount {{Amount}} vs $30.00",
            ])
            report = ft.extract_template(str(src), str(tdp / "out"))
            self.assertIn("Amount", report["pre_existing_tokens"])
            self.assertIn("Amount2", report["tokens"])
            self.assertNotIn("Amount", report["tokens"])
            self.assertIn("pre_existing_note", report)
            tmpl = next(p for p in (tdp / "out").iterdir() if p.suffix == ".docx")
            text = ft.read_content(str(tmpl))
            self.assertIn("{{Amount}}", text)
            self.assertIn("{{Amount2}}", text)
            self.assertIn("{{Recipient}}", text)
            csv_path = next(p for p in (tdp / "out").iterdir() if p.suffix == ".csv")
            headers, rows = ft.load_rows(str(csv_path))
            self.assertIn("Amount", headers)
            for row in rows:
                self.assertEqual((row.get("Amount") or ""), "")
            self.assertIn("fill", report["pre_existing_note"].lower())

    def test_single_instance_typed_hits_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "single.docx"
            _make_docx(src, ["Invoice total: $99.00 for ACME-0001."])
            out = tdp / "extracted"
            report = ft.extract_template(str(src), str(out))
            self.assertEqual(report["instances"], 1)
            self.assertIn("Amount", report["tokens"])
            self.assertIn("AccountRef", report["tokens"])
            tmpl = next(p for p in out.iterdir() if p.suffix == ".docx")
            self.assertIn("{{Amount}}", ft.read_content(str(tmpl)))
            csv_path = next(p for p in out.iterdir() if p.suffix == ".csv")
            rows = ft.load_rows(str(csv_path))
            filled = tdp / "refilled"
            gen = ft.generate(str(tmpl), rows, outdir=str(filled))
            self.assertEqual(len(gen["written"]), 1)
            text = ft.read_content(str(Path(gen["written"][0]["file"])))
            self.assertIn("$99.00", text)
            self.assertIn("ACME-0001", text)

    def test_collapse_keeps_one_instance(self):
        """O1: extracted template is one letter; filling one row does not duplicate."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "filled.docx"
            _make_docx(src, [
                "Dear Alice Tan,",
                "Thank you for your payment of $420.00 on 12 Mar 2026 for invoice INV-1024. Your account ACME-0042 is now settled.",
                "Dear Bob Lim,",
                "Thank you for your payment of $180.50 on 03 Apr 2026 for invoice INV-1025. Your account ACME-0043 is now settled.",
            ])
            out = tdp / "extracted"
            report = ft.extract_template(str(src), str(out))
            self.assertEqual(report["instances"], 2)
            self.assertEqual(report["instances_collapsed"], 1)
            tmpl = next(p for p in out.iterdir() if p.suffix == ".docx")
            paras = [p.text for p in Document(str(tmpl)).paragraphs if p.text.strip()]
            self.assertEqual(sum(1 for p in paras if p.startswith("Dear ")), 1)
            csv_path = next(p for p in out.iterdir() if p.suffix == ".csv")
            _headers, rows = ft.load_rows(str(csv_path))
            gen = ft.generate(str(tmpl), [rows[0]], outdir=str(tdp / "refilled"))
            filled_paras = [
                p.text for p in Document(gen["written"][0]["file"]).paragraphs if p.text.strip()
            ]
            self.assertEqual(sum(1 for p in filled_paras if "Alice Tan" in p), 1)
            self.assertFalse(any("Bob Lim" in p for p in filled_paras))

    def test_boilerplate_amount_stays_literal(self):
        """O6: a fee that is not a slot stays literal even when $ amounts exist."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "pay.docx"
            _make_docx(src, [
                "Pay $10.00; fee $10.00.",
                "Pay $20.00; fee $30.00.",
                "Standard fee is $50.00. Do not change this line.",
            ])
            report = ft.extract_template(str(src), str(tdp / "out"))
            tmpl = next(p for p in (tdp / "out").iterdir() if p.suffix == ".docx")
            text = "\n".join(
                p.text for p in Document(str(tmpl)).paragraphs if p.text.strip()
            )
            self.assertIn("Pay {{Amount}}; fee {{Amount2}}.", text)
            self.assertIn("Standard fee is $50.00. Do not change this line.", text)
            self.assertNotIn("Standard fee is {{Amount}}", text)
            self.assertEqual(report["instances_collapsed"], 1)

    def test_accountref_does_not_split_hyphenated_id(self):
        """O24: AB-2026-01-02 is not tokenised as AccountRef AB-2026."""
        hits, _notes = ft._typed_hits("Your ref AB-2026-01-02 is due.")
        self.assertFalse(any(k == "AccountRef" and v == "AB-2026" for k, v, *_ in hits))

    def test_overlapping_recipient_is_trimmed_or_reported(self):
        """O25: overlapping Amount does not silently drop Recipient."""
        hits, notes = ft._typed_hits("Dear Bob owes $5")
        kinds = [k for k, *_ in hits]
        self.assertTrue(
            "Recipient" in kinds or any("Recipient" in n or "overlap" in n.lower() for n in notes),
            f"hits={hits} notes={notes}",
        )

    def test_missing_source_raises_file_not_found(self):
        """O26: missing file and directory args fail with a clear path error."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            with self.assertRaises(FileNotFoundError) as cm:
                ft.extract_template(str(tdp / "nope.docx"), str(tdp / "out"))
            self.assertIn("nope.docx", str(cm.exception))
            with self.assertRaises(IsADirectoryError) as cm:
                ft.extract_template(str(tdp), str(tdp / "out"))
            self.assertIn(str(tdp), str(cm.exception))

    def test_merged_table_cells_are_deduped(self):
        """O27: horizontally merged cells are one record, not two."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "merged.docx"
            doc = Document()
            table = doc.add_table(rows=2, cols=2)
            a = table.cell(0, 0)
            a.merge(table.cell(0, 1))
            a.text = "Dear Alice, $10.00"
            b = table.cell(1, 0)
            b.merge(table.cell(1, 1))
            b.text = "Dear Bob, $20.00"
            doc.save(str(src))
            report = ft.extract_template(str(src), str(tdp / "out"))
            self.assertEqual(report["instances"], 2)
            self.assertIn("Recipient", report["tokens"])
            self.assertIn("Amount", report["tokens"])

    def test_row_dicts_rejects_tuple_of_lists(self):
        """O28: (headers, list-of-lists) is a TypeError, not AttributeError."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            tmpl = tdp / "t.docx"
            _make_docx(tmpl, ["Hello {{Name}}"])
            with self.assertRaises(TypeError) as cm:
                ft.generate(str(tmpl), (["Name"], [["Alice"]]), outdir=str(tdp / "out"))
            self.assertIn("list[dict]", str(cm.exception))

    def test_hyperlink_mismatch_is_reported(self):
        """O29: a value only in a hyperlink is listed, not silently dropped."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "link.docx"
            doc = Document()
            p1 = doc.add_paragraph("Dear ")
            _add_hyperlink(p1, "Alice Tan")
            p1.add_run(",")
            doc.add_paragraph("Pay $10.00.")
            p2 = doc.add_paragraph("Dear ")
            _add_hyperlink(p2, "Bob Lim")
            p2.add_run(",")
            doc.add_paragraph("Pay $20.00.")
            doc.save(str(src))
            report = ft.extract_template(str(src), str(tdp / "out"))
            joined = " ".join(report.get("uncertain") or []) + " ".join(report.get("not_found") or [])
            self.assertTrue(
                "Recipient" in joined or "hyperlink" in joined.lower() or "runs" in joined.lower(),
                report,
            )

    def test_linked_section_header_is_kept(self):
        """R2: a header linked to the previous section is not deleted on collapse."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "linked.docx"
            doc = Document()
            doc.add_paragraph("Dear Alice Tan,")
            doc.add_paragraph(
                "Thank you for your payment of $420.00 on 12 Mar 2026 for invoice "
                "INV-1024. Your account ACME-0042 is now settled."
            )
            hdr = doc.sections[0].header
            if hdr.paragraphs:
                hdr.paragraphs[0].text = "ACME Letterhead — Confidential"
            else:
                hdr.add_paragraph("ACME Letterhead — Confidential")
            doc.add_section()
            doc.add_paragraph("Dear Bob Lim,")
            doc.add_paragraph(
                "Thank you for your payment of $180.50 on 03 Apr 2026 for invoice "
                "INV-1025. Your account ACME-0043 is now settled."
            )
            self.assertTrue(doc.sections[1].header.is_linked_to_previous)
            doc.save(str(src))
            report = ft.extract_template(str(src), str(tdp / "out"))
            tmpl = Path(report["template"])
            extracted = Document(str(tmpl))
            header_text = " ".join(
                p.text for sec in extracted.sections for p in sec.header.paragraphs
            )
            self.assertIn("ACME Letterhead — Confidential", header_text)
            self.assertIn("Recipient", report["tokens"])
            self.assertEqual(report["instances"], 2)

    def test_repeated_constant_does_not_create_phantom_instances(self):
        """R3: one letter with two identical 'Thank you.' still extracts role tokens."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "once.docx"
            _make_docx(src, [
                "Dear Alice Tan,",
                "Thank you for your payment of $420.00 on 12 Mar 2026 for invoice INV-1024. Your account ACME-0042 is now settled.",
                "Thank you.",
                "Thank you.",
            ])
            report = ft.extract_template(str(src), str(tdp / "out"))
            self.assertEqual(report["instances"], 1)
            self.assertIn("Recipient", report["tokens"])
            self.assertIn("Amount", report["tokens"])
            tmpl = Path(report["template"])
            text = ft.read_content(str(tmpl))
            self.assertIn("{{Recipient}}", text)
            self.assertIn("{{Amount}}", text)
            self.assertIn("Thank you.", text)
            csv_path = Path(report["skeleton"])
            _headers, rows = ft.load_rows(str(csv_path))
            self.assertEqual(rows[0]["Recipient"], "Alice Tan")
            self.assertEqual(rows[0]["Amount"], "$420.00")

    def test_hardlinked_dest_does_not_mutate_source(self):
        """R4: a hard-linked destination must not write through to the source inode."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "hard.docx"
            _make_docx(src, ["Dear Alice Tan,", "Payment $420.00 on 12 Mar 2026."])
            before = src.read_bytes()
            out = tdp / "out"
            out.mkdir()
            os.link(src, out / "hard_tokenised.docx")
            with self.assertRaises(ValueError) as cm:
                ft.extract_template(str(src), str(out))
            self.assertIn("overwrite", str(cm.exception).lower())
            self.assertEqual(src.read_bytes(), before)
            self.assertNotIn(b"{{Recipient}}", src.read_bytes())

    def test_invoice_table_drops_extra_rows_not_empty_cells(self):
        """N1: 3-row invoice table collapses to 1 row with no empty <w:tc>."""
        from docx.oxml.ns import qn

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "invoice.docx"
            doc = Document()
            table = doc.add_table(rows=3, cols=2)
            rows = [
                ("Invoice INV-1024", "Due $10.00"),
                ("Invoice INV-1025", "Due $20.00"),
                ("Invoice INV-1026", "Due $30.00"),
            ]
            for i, (left, right) in enumerate(rows):
                table.cell(i, 0).text = left
                table.cell(i, 1).text = right
            doc.save(str(src))
            report = ft.extract_template(str(src), str(tdp / "out"))
            tmpl = Path(report["template"])
            extracted = Document(str(tmpl))
            self.assertEqual(len(extracted.tables), 1)
            self.assertEqual(len(extracted.tables[0].rows), 1)
            body = extracted.element.body
            trs = body.findall(".//" + qn("w:tr"))
            tcs = body.findall(".//" + qn("w:tc"))
            empty_tc = [tc for tc in tcs if tc.find(qn("w:p")) is None]
            self.assertEqual(len(trs), 1)
            self.assertEqual(empty_tc, [])
            self.assertIn("InvoiceRef", report["tokens"])
            self.assertIn("Amount", report["tokens"])
            text = ft.read_content(str(tmpl))
            self.assertIn("{{InvoiceRef}}", text)
            self.assertIn("{{Amount}}", text)

    def test_mixed_extra_row_keeps_unclaimed_content(self):
        """C2: extra row with an unclaimed cell is kept; clean invoice still collapses."""
        from docx.oxml.ns import qn

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "mixed.docx"
            doc = Document()
            table = doc.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "Pay $10.00."
            table.cell(0, 1).text = ""
            table.cell(1, 0).text = "Pay $20.00."
            table.cell(1, 1).text = "Unique important note"
            doc.save(str(src))
            report = ft.extract_template(str(src), str(tdp / "out"))
            tmpl = Path(report["template"])
            extracted = Document(str(tmpl))
            self.assertEqual(len(extracted.tables), 1)
            self.assertEqual(len(extracted.tables[0].rows), 2)
            row2 = [c.text for c in extracted.tables[0].rows[1].cells]
            self.assertIn("Unique important note", row2)
            text = ft.read_content(str(tmpl))
            self.assertIn("Unique important note", text)
            self.assertIn("{{Amount}}", text)
            self.assertTrue(
                any("unclaimed" in u.lower() and "kept" in u.lower()
                    for u in report["uncertain"]),
                report["uncertain"],
            )
            body = extracted.element.body
            tcs = body.findall(".//" + qn("w:tc"))
            empty_tc = [tc for tc in tcs if tc.find(qn("w:p")) is None]
            self.assertEqual(empty_tc, [])

            clean = tdp / "invoice.docx"
            inv = Document()
            inv_table = inv.add_table(rows=3, cols=2)
            rows = [
                ("Invoice INV-1024", "Due $10.00"),
                ("Invoice INV-1025", "Due $20.00"),
                ("Invoice INV-1026", "Due $30.00"),
            ]
            for i, (left, right) in enumerate(rows):
                inv_table.cell(i, 0).text = left
                inv_table.cell(i, 1).text = right
            inv.save(str(clean))
            clean_report = ft.extract_template(str(clean), str(tdp / "clean"))
            clean_doc = Document(str(clean_report["template"]))
            self.assertEqual(len(clean_doc.tables[0].rows), 1)

    def test_extract_name_rejects_path_escape(self):
        """N5: name with separators or '..' must not write outside out_dir."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "letter.docx"
            _make_docx(src, ["Dear Alice Tan,", "Pay $10.00.", "Dear Bob Lim,", "Pay $20.00."])
            out = tdp / "extracted"
            out.mkdir()
            outside = tdp / "evil_tokenised.docx"
            for bad in ("../../evil", str(tdp / "evil"), "..\\evil"):
                if outside.exists():
                    outside.unlink()
                with self.assertRaises(ValueError):
                    ft.extract_template(str(src), str(out), name=bad)
                self.assertFalse(outside.exists(), f"wrote outside for name={bad!r}")
                leaked = list(tdp.glob("**/evil_tokenised.docx")) + list(tdp.glob("**/evil_data.csv"))
                self.assertEqual(leaked, [], f"leaked files for name={bad!r}: {leaked}")

    def test_not_found_hyperlink_slot_dropped_from_tokens(self):
        """N6: a hyperlink-only slot stays under uncertain, not tokens/CSV/mapping."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "link.docx"
            doc = Document()
            p1 = doc.add_paragraph("Dear ")
            _add_hyperlink(p1, "Alice Tan")
            p1.add_run(",")
            doc.add_paragraph("Pay $10.00.")
            p2 = doc.add_paragraph("Dear ")
            _add_hyperlink(p2, "Bob Lim")
            p2.add_run(",")
            pay2 = doc.add_paragraph("Pay ")
            _add_hyperlink(pay2, "$20.00")
            pay2.add_run(".")
            doc.save(str(src))
            report = ft.extract_template(str(src), str(tdp / "out"))
            self.assertNotIn("Recipient", report["tokens"])
            self.assertTrue(
                any("hyperlink" in u.lower() or "Recipient" in u for u in report["uncertain"]),
                report["uncertain"],
            )
            self.assertFalse(any(m["token"] == "Recipient" for m in report["mapping"]))
            csv_path = Path(report["skeleton"])
            headers, rows = ft.load_rows(str(csv_path))
            self.assertNotIn("Recipient", headers)
            for row in rows:
                self.assertNotIn("Recipient", row)
            joined_uncertain = " ".join(report["uncertain"])
            self.assertTrue("Recipient" in joined_uncertain or "hyperlink" in joined_uncertain.lower())

    def test_token_free_doc_is_no_tokens_empty_csv(self):
        """N12/R3-13: no typed values → status no-tokens and a zero-byte skeleton."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "plain.docx"
            _make_docx(src, ["This letter has only boilerplate."])
            report = ft.extract_template(str(src), str(tdp / "out"))
            self.assertEqual(report["status"], "no-tokens")
            self.assertEqual(report["tokens"], [])
            csv_path = Path(report["skeleton"])
            self.assertTrue(csv_path.is_file())
            self.assertEqual(csv_path.stat().st_size, 0)

    def test_no_tokens_skips_collapse(self):
        """R3-1: typed-pattern mismatch keeps every paragraph and does not collapse."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "mix.docx"
            _make_docx(src, ["Code INV-2001", "Code $10.00"])
            before = src.read_bytes()
            report = ft.extract_template(str(src), str(tdp / "out"))
            self.assertEqual(report["status"], "no-tokens")
            self.assertEqual(report["tokens"], [])
            self.assertEqual(report["instances_collapsed"], 0)
            tmpl = Path(report["template"])
            self.assertEqual(tmpl.read_bytes(), before)
            paras = [p.text for p in Document(str(tmpl)).paragraphs if p.text.strip()]
            self.assertEqual(paras, ["Code INV-2001", "Code $10.00"])

    def test_two_column_invoice_table_extracts_tokens(self):
        """R3-8: INV and $ cells in different columns are distinct roles."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "inv.docx"
            doc = Document()
            table = doc.add_table(rows=4, cols=2)
            rows = [
                ("Invoice", "Amount"),
                ("INV-2001", "$10.00"),
                ("INV-2002", "$20.00"),
                ("INV-2003", "$30.00"),
            ]
            for i, (left, right) in enumerate(rows):
                table.cell(i, 0).text = left
                table.cell(i, 1).text = right
            doc.save(str(src))
            report = ft.extract_template(str(src), str(tdp / "out"))
            self.assertIn("InvoiceRef", report["tokens"])
            self.assertIn("Amount", report["tokens"])
            self.assertNotEqual(report.get("status"), "no-tokens")
            tmpl = Path(report["template"])
            text = ft.read_content(str(tmpl))
            self.assertIn("{{InvoiceRef}}", text)
            self.assertIn("{{Amount}}", text)
            extracted = Document(str(tmpl))
            from docx.oxml.ns import qn
            trs = extracted.element.body.findall(".//" + qn("w:tr"))
            self.assertEqual(len(trs), 2)
            self.assertEqual(len(extracted.tables[0].rows), 2)
            cell_blob = " ".join(
                c.text for row in extracted.tables[0].rows for c in row.cells
            )
            self.assertIn("Invoice", cell_blob)
            self.assertNotIn("INV-2002", cell_blob)
            self.assertNotIn("INV-2003", cell_blob)

    def test_unaligned_ps_is_uncertain(self):
        """R3-7: a paragraph unique to one instance is noted as boilerplate."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "letters.docx"
            _make_docx(src, [
                "Dear Alice Tan,",
                "Thank you for your payment of $420.00 on 12 Mar 2026 for invoice INV-1024. Your account ACME-0042 is now settled.",
                "Dear Bob Lim,",
                "Thank you for your payment of $180.50 on 03 Apr 2026 for invoice INV-1025. Your account ACME-0043 is now settled.",
                "PS: Bob, your rebate of $12.00 ships separately.",
            ])
            report = ft.extract_template(str(src), str(tdp / "out"))
            self.assertTrue(
                any("boilerplate" in u.lower() and "confirm" in u.lower()
                    for u in report["uncertain"]),
                report["uncertain"],
            )
            tmpl = Path(report["template"])
            text = ft.read_content(str(tmpl))
            self.assertIn("PS: Bob, your rebate of $12.00 ships separately.", text)

    def test_identical_repeats_do_not_promote_constants(self):
        """R3-9: two byte-identical letters stay literal; constants are not tokenised."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "dup.docx"
            letter = [
                "Dear Alice Tan,",
                "Thank you for your payment of $420.00 on 12 Mar 2026 for invoice INV-1024. Your account ACME-0042 is now settled.",
            ]
            _make_docx(src, letter + letter)
            report = ft.extract_template(str(src), str(tdp / "out"))
            self.assertEqual(report["tokens"], [])
            self.assertEqual(report.get("status"), "no-tokens")
            self.assertTrue(
                any("did not vary" in u or "not aligned" in u
                    for u in report["uncertain"]),
                report["uncertain"],
            )
            paras = [
                p.text for p in Document(str(report["template"])).paragraphs
                if p.text.strip()
            ]
            self.assertEqual(paras, letter + letter)
            self.assertEqual(Path(report["skeleton"]).stat().st_size, 0)

    def test_aligned_repeating_constant_stays_literal(self):
        """E1: identical values across aligned instances stay literal."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "pay.docx"
            _make_docx(src, [
                "Pay $10.00; fee $5.00.",
                "Pay $20.00; fee $5.00.",
            ])
            report = ft.extract_template(str(src), str(tdp / "out"))
            self.assertEqual(report["tokens"], ["Amount"])
            text = ft.read_content(report["template"])
            self.assertIn("fee $5.00.", text)
            self.assertIn("Pay {{Amount}}; fee $5.00.", text)
            self.assertNotIn("{{Amount2}}", text)

    def test_singleton_header_slot_broadcasts_to_every_row(self):
        """E2: a singleton header value is copied onto every skeleton row."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "hdr.docx"
            _make_docx(
                src,
                [
                    "Pay $10.00; fee $10.00.",
                    "Pay $20.00; fee $30.00.",
                ],
                header="Account ACME-0042",
            )
            report = ft.extract_template(str(src), str(tdp / "out"))
            headers, rows = ft.load_rows(report["skeleton"])
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["AccountRef"], "ACME-0042")
            self.assertEqual(rows[1]["AccountRef"], "ACME-0042")
            self.assertEqual(report.get("not_found") or [], [])
            gen = ft.generate(
                report["template"], (headers, rows), outdir=str(tdp / "filled")
            )
            self.assertEqual(gen["written"][0]["missing"], [])
            self.assertEqual(gen["written"][1]["missing"], [])
            for written in gen["written"]:
                filled = ft.read_content(written["file"])
                self.assertIn("ACME-0042", filled)

    def test_accountref_contained_in_invoiceref_is_silent(self):
        """N14: AccountRef fully inside InvoiceRef is not an overlap note."""
        hits, notes = ft._typed_hits(
            "Thank you for invoice INV-1024. Your account ACME-0042 is settled."
        )
        kinds = [k for k, *_ in hits]
        self.assertIn("InvoiceRef", kinds)
        self.assertIn("AccountRef", kinds)
        self.assertFalse(
            any("AccountRef skipped" in n for n in notes),
            notes,
        )
        hits2, notes2 = ft._typed_hits("Dear Bob owes $5")
        self.assertTrue(
            any("overlap" in n.lower() for n in notes2) or any(k == "Recipient" for k, *_ in hits2),
            (hits2, notes2),
        )

    def test_linked_first_page_header_does_not_create_part(self):
        """N18: extracting must not materialise linked first/even header parts."""
        import zipfile

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "plain.docx"
            _make_docx(src, [
                "Dear Alice Tan,",
                "Thank you for your payment of $420.00 on 12 Mar 2026 for invoice INV-1024.",
                "Dear Bob Lim,",
                "Thank you for your payment of $180.50 on 03 Apr 2026 for invoice INV-1025.",
            ])
            report = ft.extract_template(str(src), str(tdp / "out"))
            with zipfile.ZipFile(report["template"]) as zf:
                names = zf.namelist()
            hdrs = [n for n in names if "/header" in n]
            self.assertEqual(hdrs, [], names)

    def test_partial_token_collapse_keeps_mismatched_code(self):
        """D2: Recipient token must not delete the unmatched Code $10.00 paragraph."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "partial.docx"
            _make_docx(src, [
                "Dear Alice,",
                "Code INV-2001",
                "Dear Bob,",
                "Code $10.00",
            ])
            report = ft.extract_template(str(src), str(tdp / "out"))
            text = ft.read_content(report["template"])
            csv_text = Path(report["skeleton"]).read_text()
            self.assertIn("Recipient", report["tokens"])
            self.assertIn("Code INV-2001", text)
            self.assertIn("Code $10.00", text)
            self.assertIn("$10.00", csv_text + text)
            self.assertTrue(
                any("mismatch" in u.lower() for u in report["uncertain"]),
                report["uncertain"],
            )

    def test_nested_table_in_extra_row_survives_collapse(self):
        """D3: unique nested table in extra row 2 is kept, not deleted with the row."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "nested.docx"
            doc = Document()
            table = doc.add_table(rows=2, cols=1)
            table.cell(0, 0).text = "Pay $10.00"
            table.cell(1, 0).text = "Pay $20.00"
            table.cell(1, 0).add_table(rows=1, cols=1).cell(0, 0).text = (
                "Unique nested note"
            )
            doc.save(str(src))
            report = ft.extract_template(str(src), str(tdp / "out"))
            extracted = Document(str(report["template"]))
            self.assertEqual(len(extracted.tables), 1)
            self.assertGreaterEqual(len(extracted.tables[0].rows), 2)
            row2 = extracted.tables[0].rows[1]
            nested = row2.cells[0].tables
            self.assertTrue(nested, "row 2 nested table was deleted")
            self.assertIn("Unique nested note", nested[0].cell(0, 0).text)
            text = ft.read_content(report["template"])
            self.assertIn("Unique nested note", text)
            self.assertTrue(
                any("boilerplate" in u.lower() or "unclaimed" in u.lower()
                    for u in report["uncertain"]),
                report["uncertain"],
            )

    def test_first_page_and_main_header_invoice_refs_are_kept(self):
        """N2: distinct first-page and main header refs are both tokenised."""
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "hdr.docx"
            doc = Document()
            doc.add_paragraph("Dear Alice,")
            doc.add_paragraph("Invoice INV-2024 body")
            doc.add_paragraph("Dear Bob,")
            doc.add_paragraph("Invoice INV-2025 body")
            sec = doc.sections[0]
            sec.different_first_page_header_footer = True
            fp = sec.first_page_header
            if fp.paragraphs:
                fp.paragraphs[0].text = "Invoice INV-1024"
            else:
                fp.add_paragraph("Invoice INV-1024")
            hd = sec.header
            if hd.paragraphs:
                hd.paragraphs[0].text = "Invoice INV-1025"
            else:
                hd.add_paragraph("Invoice INV-1025")
            doc.save(str(src))

            loaded = Document(str(src))
            s0 = loaded.sections[0]
            fp_el = next(
                p._element for p in s0.first_page_header.paragraphs if p.text.strip()
            )
            hd_el = next(p._element for p in s0.header.paragraphs if p.text.strip())
            self.assertEqual(
                fp_el.getroottree().getpath(fp_el),
                hd_el.getroottree().getpath(hd_el),
            )
            self.assertNotEqual(ft._xml_path(fp_el), ft._xml_path(hd_el))
            cached = ft._xml_path(fp_el)
            self.assertIs(cached, ft._xml_path(fp_el))

            report = ft.extract_template(str(src), str(tdp / "out"))
            csv_text = Path(report["skeleton"]).read_text()
            self.assertIn("INV-1024", csv_text)
            self.assertIn("INV-1025", csv_text)
            extracted = Document(str(report["template"]))
            sec = extracted.sections[0]
            fp_text = " ".join(p.text for p in sec.first_page_header.paragraphs)
            hd_text = " ".join(p.text for p in sec.header.paragraphs)
            self.assertIn("{{", fp_text)
            self.assertIn("{{", hd_text)
            self.assertNotIn("INV-1024", fp_text)
            self.assertNotIn("INV-1025", hd_text)

    def test_many_table_rows_collapse_to_one(self):
        """F1: extra rows must not be mistaken for the retained row via a stale path."""
        from docx.oxml.ns import qn

        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            src = tdp / "many.docx"
            doc = Document()
            n = 20
            table = doc.add_table(rows=n, cols=1)
            for i in range(n):
                table.cell(i, 0).text = f"Pay ${10 + i}.00"
            doc.save(str(src))
            report = ft.extract_template(str(src), str(tdp / "out"))
            extracted = Document(str(report["template"]))
            self.assertEqual(len(extracted.tables), 1)
            self.assertEqual(len(extracted.tables[0].rows), 1)
            trs = extracted.element.body.findall(".//" + qn("w:tr"))
            self.assertEqual(len(trs), 1)
            self.assertEqual(report["instances_collapsed"], n - 1)


def _add_hyperlink(paragraph, text, url="https://example.com"):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    part = paragraph.part
    r_id = part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    new_run = OxmlElement("w:r")
    text_elem = OxmlElement("w:t")
    text_elem.text = text
    new_run.append(text_elem)
    hyperlink.append(new_run)
    paragraph._p.append(hyperlink)


if __name__ == "__main__":
    unittest.main(verbosity=2)