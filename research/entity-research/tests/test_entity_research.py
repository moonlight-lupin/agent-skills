#!/usr/bin/env python3
"""Unit tests for entity_research.py — sanctions matcher, parsers, and dossier assembler.

Run:  python -m pytest research/entity-research/tests/test_entity_research.py -v
  or:  python research/entity-research/tests/test_entity_research.py

No network required — all tests use injected fixtures and sample bytes.
"""

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import entity_research as er  # noqa: E402


# ---------------------------------------------------------------------------
# _norm — name normalisation
# ---------------------------------------------------------------------------

class TestNorm(unittest.TestCase):
    """_norm: lowercase, depunctuate, strip corporate suffixes."""

    def test_lowercase(self):
        self.assertEqual(er._norm("ACME TRADING"), ["acme", "trading"])

    def test_strips_punctuation(self):
        self.assertEqual(er._norm("Acme Trading, Co."), ["acme", "trading"])

    def test_strips_corp_suffixes(self):
        for suffix in ("Ltd", "Limited", "Inc", "LLC", "Pte", "Corp", "Company", "Holdings", "Group"):
            tokens = er._norm(f"Acme {suffix}")
            self.assertEqual(tokens, ["acme"], msg=f"Suffix '{suffix}' not stripped")

    def test_strips_multiple_suffixes(self):
        self.assertEqual(er._norm("Acme Pte Ltd"), ["acme"])
        self.assertEqual(er._norm("Acme Corp LLC"), ["acme"])

    def test_empty(self):
        self.assertEqual(er._norm(""), [])
        self.assertEqual(er._norm(None), [])

    def test_preserves_distinctive_tokens(self):
        """Generic words like 'trading', 'capital' are NOT stripped by _norm (they're in
        _GENERIC for matching, not _CORP_SUFFIXES for normalisation)."""
        tokens = er._norm("Northwind Capital Management Ltd")
        self.assertIn("northwind", tokens)
        self.assertIn("capital", tokens)
        self.assertIn("management", tokens)
        self.assertNotIn("ltd", tokens)


# ---------------------------------------------------------------------------
# _match — token-based name matching
# ---------------------------------------------------------------------------

class TestMatch(unittest.TestCase):
    """_match: subset, overlap, generic-word guard, aliases, edge cases."""

    def setUp(self):
        self.fixture = [
            {"name": "ACME TRADING CO", "type": "Entity", "program": "SDGT",
             "aliases": ["ACME TRADING LLC", "ACME HOLDINGS"]},
            {"name": "JOHN A SMITH", "type": "Individual", "program": "UKRAINE-EO13662",
             "aliases": []},
            {"name": "NORTHWIND LOGISTICS", "type": "Entity", "program": "SDGT", "aliases": []},
        ]

    def test_exact_subset(self):
        """Query is a token-subset of candidate → score 1.0."""
        matches = er._match("Acme Trading", self.fixture)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["matched_name"], "ACME TRADING CO")
        self.assertEqual(matches[0]["score"], 1.0)

    def test_reverse_subset(self):
        """Candidate is a token-subset of query → score 1.0."""
        matches = er._match("Acme Trading Co Ltd", self.fixture)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["matched_name"], "ACME TRADING CO")

    def test_no_match(self):
        matches = er._match("Jane Doe", self.fixture)
        self.assertEqual(matches, [])

    def test_empty_query(self):
        matches = er._match("", self.fixture)
        self.assertEqual(matches, [])

    def test_alias_match(self):
        """Match against an alias, not just the primary name."""
        matches = er._match("Acme Holdings", self.fixture)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["matched_name"], "ACME TRADING CO")

    def test_generic_word_guard_blocks(self):
        """Two entities sharing only generic words must NOT match."""
        fixture = [{"name": "Y CAPITAL MANAGEMENT", "type": "Entity", "program": "SDGT", "aliases": []}]
        matches = er._match("X Capital Management", fixture)
        self.assertEqual(matches, [], "Generic-only overlap should not match")

    def test_generic_word_guard_allows_distinctive(self):
        """A distinctive shared token + generic words → match if overlap ≥2 or subset."""
        fixture = [{"name": "NORTHWIND CAPITAL MANAGEMENT", "type": "Entity", "program": "SDGT", "aliases": []}]
        # "Northwind Capital" shares 'northwind' (distinctive) + 'capital' (generic)
        # overlap=2 → passes the ≥2 threshold
        matches = er._match("Northwind Capital", fixture)
        self.assertEqual(len(matches), 1)

    def test_single_distinctive_token_no_partial(self):
        """A single distinctive shared token (overlap=1, not subset) → no partial match.
        This is by design — prevents false positives on thin overlap."""
        fixture = [{"name": "NORTHWIND TRADING", "type": "Entity", "program": "SDGT", "aliases": []}]
        # query "Northwind Capital Management" shares only 'northwind' with candidate
        # overlap=1, not a subset → no match
        matches = er._match("Northwind Capital Management", fixture)
        self.assertEqual(matches, [])

    def test_single_token_subset(self):
        """Single-token names match via subset if they're identical (after norm)."""
        fixture = [{"name": "NORTHWIND", "type": "Entity", "program": "SDGT", "aliases": []}]
        matches = er._match("Northwind", fixture)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["score"], 1.0)

    def test_transliteration_miss(self):
        """Token-based matcher does NOT catch spelling variants (documented limitation)."""
        fixture = [{"name": "MUHAMMAD ALI", "type": "Individual", "program": "SDGT", "aliases": []}]
        matches = er._match("Mohammed Ali", fixture)
        self.assertEqual(matches, [], "Transliteration variants should not match (token-based)")

    def test_results_sorted_by_score(self):
        """Matches are sorted highest score first."""
        fixture = [
            {"name": "ACME TRADING CO", "type": "Entity", "program": "SDGT", "aliases": []},
            {"name": "ACME BANK TRUST", "type": "Entity", "program": "SDGT", "aliases": []},
        ]
        matches = er._match("Acme Trading", fixture)
        # First match should be the subset (score 1.0)
        self.assertEqual(matches[0]["score"], 1.0)

    def test_threshold_override(self):
        """Lower threshold → more partial matches."""
        fixture = [{"name": "ACME BANK TRUST HOLDINGS", "type": "Entity", "program": "SDGT", "aliases": []}]
        # "Acme Bank" shares 'acme' + 'bank' with candidate → overlap=2, score=2/2=1.0 (subset)
        # This is a subset so threshold doesn't matter, but test with high threshold
        matches_high = er._match("Acme Bank Trust", fixture, threshold=0.99)
        self.assertEqual(len(matches_high), 1)  # subset match still works


# ---------------------------------------------------------------------------
# _parse_ofac_sdn — OFAC SDN / Consolidated CSV parser
# ---------------------------------------------------------------------------

class TestParseOfacSdn(unittest.TestCase):
    """_parse_ofac_sdn: CSV parsing, -0- placeholder handling."""

    def test_basic_parse(self):
        raw = b'1,ACME TRADING CO,Entity,SDGT,-0- ,,,,,,\n2,JOHN SMITH,Individual,SDGT,"123 Main St",,,,,,\n'
        entries = er._parse_ofac_sdn(raw)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["name"], "ACME TRADING CO")
        self.assertEqual(entries[0]["type"], "Entity")
        self.assertEqual(entries[0]["program"], "SDGT")

    def test_skips_placeholder_with_space(self):
        """'-0- ' (with trailing space) is skipped."""
        raw = b'1,-0- ,-0- ,-0- ,,,,,,\n2,ACME,Entity,SDGT,,,,,,\n'
        entries = er._parse_ofac_sdn(raw)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "ACME")

    def test_skips_placeholder_without_space(self):
        """'-0-' (without trailing space) is also skipped (the #3 fix)."""
        raw = b'1,-0-,-0-,-0-,,,,,,\n2,ACME,Entity,SDGT,,,,,,\n'
        entries = er._parse_ofac_sdn(raw)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "ACME")

    def test_skips_empty_name(self):
        """Empty name field is skipped."""
        raw = b'1,,Entity,SDGT,,,,,,\n2,ACME,Entity,SDGT,,,,,,\n'
        entries = er._parse_ofac_sdn(raw)
        self.assertEqual(len(entries), 1)

    def test_short_rows_skipped(self):
        """Rows with <4 columns are skipped."""
        raw = b'1,ACME\n2,ACME,Entity,SDGT,,,,,,\n'
        entries = er._parse_ofac_sdn(raw)
        self.assertEqual(len(entries), 1)


# ---------------------------------------------------------------------------
# _parse_uk_ofsi — UK OFSI CSV parser
# ---------------------------------------------------------------------------

class TestParseUkOfsi(unittest.TestCase):
    """_parse_uk_ofsi: multi-column name join, header skip."""

    def test_basic_parse(self):
        raw = b'Last Updated,2024-01-01\nName 6,Name 1,Name 2,Name 3,Name 4,Name 5,Group Type\n,,GLOBAL,FINANCIAL,,HOLDINGS,Entity\n,,NORTHWIND,,LOGISTICS,,,Entity\n'
        entries = er._parse_uk_ofsi(raw)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["name"], "GLOBAL FINANCIAL HOLDINGS")
        self.assertEqual(entries[0]["program"], "UK-OFSI")
        self.assertEqual(entries[1]["name"], "NORTHWIND LOGISTICS")

    def test_skips_header_rows(self):
        """First two rows (Last Updated + header) are skipped."""
        raw = b'Last Updated,2024-01-01\nName 6,Name 1,Name 2,Name 3,Name 4,Name 5\n,,GLOBAL,FINANCIAL,,\n'
        entries = er._parse_uk_ofsi(raw)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "GLOBAL FINANCIAL")

    def test_empty_name_skipped(self):
        """Rows where all 6 name columns are empty are skipped."""
        raw = b'Last Updated,2024-01-01\nName 6,Name 1,Name 2,Name 3,Name 4,Name 5\n,,,,,,\n,,ACME,,,,\n'
        entries = er._parse_uk_ofsi(raw)
        self.assertEqual(len(entries), 1)


# ---------------------------------------------------------------------------
# _parse_un — UN XML parser
# ---------------------------------------------------------------------------

class TestParseUn(unittest.TestCase):
    """_parse_un: XML parsing, individual/entity, aliases."""

    def test_individual_with_alias(self):
        raw = b'<?xml version="1.0"?><CONSOLIDATED_LIST><INDIVIDUAL><FIRST_NAME>MUHAMMAD</FIRST_NAME><SECOND_NAME>ALI</SECOND_NAME><INDIVIDUAL_ALIAS><ALIAS_NAME>Mohammed Ali</ALIAS_NAME></INDIVIDUAL_ALIAS></INDIVIDUAL></CONSOLIDATED_LIST>'
        entries = er._parse_un(raw)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "MUHAMMAD ALI")
        self.assertEqual(entries[0]["type"], "Individual")
        self.assertIn("Mohammed Ali", entries[0]["aliases"])

    def test_entity(self):
        raw = b'<?xml version="1.0"?><CONSOLIDATED_LIST><ENTITY><NAME_ORIGINAL_SCRIPT>ACME TRADING</NAME_ORIGINAL_SCRIPT></ENTITY></CONSOLIDATED_LIST>'
        entries = er._parse_un(raw)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["name"], "ACME TRADING")
        self.assertEqual(entries[0]["type"], "Entity")

    def test_empty_list(self):
        raw = b'<?xml version="1.0"?><CONSOLIDATED_LIST></CONSOLIDATED_LIST>'
        entries = er._parse_un(raw)
        self.assertEqual(entries, [])


# ---------------------------------------------------------------------------
# screen_lists — integration with injected entries
# ---------------------------------------------------------------------------

class TestScreenLists(unittest.TestCase):
    """screen_lists: match aggregation, unavailable lists, note string, threshold."""

    def setUp(self):
        self.fixture = {
            "OFAC-SDN": [
                {"name": "ACME TRADING CO", "type": "Entity", "program": "SDGT",
                 "aliases": ["ACME TRADING LLC"]},
                {"name": "JOHN A SMITH", "type": "Individual", "program": "UKRAINE-EO13662",
                 "aliases": []},
            ],
            "UN": [
                {"name": "GLOBAL HOLDINGS", "type": "Entity", "program": "UN", "aliases": []},
            ],
        }

    def test_match_found(self):
        sig = er.screen_lists("AcME TRADING Co", lists=("OFAC-SDN",), _entries=self.fixture)
        self.assertEqual(len(sig["matches"]), 1)
        self.assertEqual(sig["matches"][0]["list"], "OFAC-SDN")
        self.assertEqual(sig["matches"][0]["matched_name"], "ACME TRADING CO")
        self.assertIn("OFAC-SDN", sig["checked"])
        self.assertEqual(sig["unavailable"], [])

    def test_no_match(self):
        sig = er.screen_lists("Jane Doe", lists=("OFAC-SDN",), _entries=self.fixture)
        self.assertEqual(sig["matches"], [])
        self.assertIn("SIGNAL ONLY", sig["note"])

    def test_unavailable_list(self):
        """A list not in _entries is reported as unavailable."""
        sig = er.screen_lists("Acme", lists=("OFAC-SDN", "UK-OFSI"), _entries=self.fixture)
        self.assertIn("OFAC-SDN", sig["checked"])
        self.assertIn("UK-OFSI", sig["unavailable"])
        self.assertIn("UK-OFSI", sig["note"])

    def test_note_contains_signal_only(self):
        sig = er.screen_lists("Acme", lists=("OFAC-SDN",), _entries=self.fixture)
        self.assertIn("SIGNAL ONLY", sig["note"])
        self.assertIn("NOT a clearance", sig["note"])

    def test_multiple_lists(self):
        sig = er.screen_lists("Northwind Logistics", lists=("OFAC-SDN", "UN"), _entries={
            "OFAC-SDN": self.fixture["OFAC-SDN"],
            "UN": [{"name": "NORTHWIND LOGISTICS", "type": "Entity", "program": "UN", "aliases": []}],
        })
        # Should find match in UN list (Northwind is distinctive, Logistics not generic)
        un_matches = [m for m in sig["matches"] if m["list"] == "UN"]
        self.assertTrue(len(un_matches) >= 1)

    def test_threshold_passthrough(self):
        """The threshold parameter is passed through to _match."""
        # With a very high threshold, partial matches are suppressed
        fixture = {"OFAC-SDN": [
            {"name": "ACME BANK TRUST HOLDINGS", "type": "Entity", "program": "SDGT", "aliases": []},
        ]}
        # "Acme Bank" is a subset of "ACME BANK TRUST HOLDINGS" (after suffix strip)
        # → subset match, score 1.0 → matches regardless of threshold
        sig = er.screen_lists("Acme Bank", lists=("OFAC-SDN",), _entries=fixture, threshold=0.99)
        self.assertEqual(len(sig["matches"]), 1)

    def test_default_lists_constant(self):
        """DEFAULT_LISTS includes all 4 lists."""
        self.assertEqual(set(er.DEFAULT_LISTS), {"OFAC-SDN", "OFAC-CONS", "UK-OFSI", "UN"})


# ---------------------------------------------------------------------------
# dossier — assembly
# ---------------------------------------------------------------------------

class TestDossier(unittest.TestCase):
    """dossier: structure, flags, sources, is_person, empty-section fallback."""

    def test_basic_structure(self):
        d = er.dossier("Test Co", {"Identity & background": "Some info."})
        self.assertIn("# Entity research — Test Co", d)
        self.assertIn("not a determination", d)
        self.assertIn("## Identity & background", d)
        self.assertIn("Some info.", d)
        self.assertIn("Internal — keep local", d)

    def test_lens_ordering(self):
        """Sections appear in LENSES order, not dict order."""
        sections = {
            "Summary & flags": "Summary content.",
            "Identity & background": "Identity content.",
            "Adverse / negative media": "Adverse content.",
        }
        d = er.dossier("Test", sections)
        id_pos = d.index("## Identity & background")
        adv_pos = d.index("## Adverse / negative media")
        sum_pos = d.index("## Summary & flags")
        self.assertLess(id_pos, adv_pos)
        self.assertLess(adv_pos, sum_pos)

    def test_identifiers(self):
        d = er.dossier("Test", {"Identity & background": "Info."},
                       identifiers={"Jurisdiction": "UK", "Registration": "12345"})
        self.assertIn("## Identifiers", d)
        self.assertIn("**Jurisdiction:** UK", d)
        self.assertIn("**Registration:** 12345", d)

    def test_flags(self):
        d = er.dossier("Test", {"Identity & background": "Info."},
                       flags=["Sanctions: potential match — escalate"])
        self.assertIn("## ⚠ Escalation flags", d)
        self.assertIn("Sanctions: potential match — escalate", d)

    def test_sources(self):
        d = er.dossier("Test", {"Identity & background": "Info."},
                       sources=["Companies House — https://example.com (14 Jun 2026)"])
        self.assertIn("## Sources", d)
        self.assertIn("1. Companies House", d)

    def test_empty_section_fallback(self):
        """Empty section body → '_No material findings located._'"""
        d = er.dossier("Test", {"Identity & background": ""})
        self.assertIn("_No material findings located._", d)

    def test_is_person(self):
        d = er.dossier("John Smith", {"Identity & background": "A person."}, is_person=True)
        self.assertIn("Person", d.split("\n")[1])

    def test_is_entity_default(self):
        d = er.dossier("Test Co", {"Identity & background": "A company."})
        self.assertIn("Entity", d.split("\n")[1])

    def test_list_of_tuples_input(self):
        """Sections can be a list of (title, body) tuples."""
        d = er.dossier("Test", [("Custom Section", "Custom content")])
        self.assertIn("## Custom Section", d)
        self.assertIn("Custom content", d)

    def test_escalation_header_says_compliance_aml(self):
        """The 'not a determination' header says 'compliance / AML function' (the #1 fix)."""
        d = er.dossier("Test", {"Identity & background": "Info."})
        self.assertIn("compliance /", d)
        self.assertIn("AML function", d)
        # Must NOT say 'fund administrator' (the old wording)
        self.assertNotIn("fund administrator", d)


# ---------------------------------------------------------------------------
# LENSES constant
# ---------------------------------------------------------------------------

class TestLensesConstant(unittest.TestCase):
    """LENSES: the six research lenses in canonical order."""

    def test_six_lenses(self):
        self.assertEqual(len(er.LENSES), 6)

    def test_canonical_order(self):
        expected = [
            "Identity & background",
            "Ownership & key management",
            "Adverse / negative media",
            "Sanctions / PEP / watchlist signals",
            "Litigation & regulatory",
            "Summary & flags",
        ]
        self.assertEqual(er.LENSES, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)