#!/usr/bin/env python3
"""Unit tests for email_list.py and the shared-mailbox rule — offline, fictional addresses only.

Run:  python -m pytest research/people-enrichment/tests/test_email_list.py -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import email_list  # noqa: E402
import enrich  # noqa: E402

ADDRESSES = ["Jordan.Lee@northwind.example", "info@northwind.example", "someone@gmail.com",
             "sam@globex.example", "not-an-address", "me@own.example", "jordan.lee@northwind.example"]


def _sheet(path, headers, rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(path)


class TestClassify(unittest.TestCase):
    def test_classes(self):
        c = email_list.classify
        self.assertEqual(c("sales@corp.example")[0], "shared mailbox")
        self.assertEqual(c("a@yahoo.co.jp")[0], "webmail")
        self.assertEqual(c("a@sub.own.example", ["own.example"])[0], "excluded")
        self.assertEqual(c("irene@corp.example")[0], "personal")
        self.assertEqual(c("nope")[0], "invalid")


class TestTriageAndMerge(unittest.TestCase):
    def test_one_company_lookup_per_domain_and_no_webmail(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "emails.txt"
            src.write_text("\n".join(ADDRESSES), encoding="utf-8")
            r = email_list.triage(src, d, ["own.example"])
            self.assertEqual(r["addresses"], 6)                    # duplicate dropped
            self.assertEqual(r["company_lookups"], 2)              # northwind + globex, once each
            self.assertEqual(r["person_lookups"], 2)
            sent = (Path(d) / "companies.csv").read_text() + (Path(d) / "people.csv").read_text()
            for never in ("gmail.com", "own.example", "info@"):
                self.assertNotIn(never, sent)

    def test_merge_outcomes(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "emails.txt"
            src.write_text("\n".join(ADDRESSES), encoding="utf-8")
            email_list.triage(src, d, ["own.example"])
            _sheet(Path(d) / "companies.xlsx", enrich.COMPANY_HEADERS,
                   [["northwind.example", "matched", 8, "Northwind Capital", "investment management",
                     "51-200", 120, 2009, "", "singapore", "northwind.example", "", "", "private", "", ""],
                    ["globex.example", "no_match", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]])
            _sheet(Path(d) / "people.xlsx", enrich.PEOPLE_HEADERS,
                   [["jordan.lee@northwind.example", "needs_review", "", 4, "Jordan Lee", "Director",
                     "Initech", "", "linkedin.com/in/example-jordan", "", "", "", "", "", ""]])
            recs = {r["email"]: r for r in email_list.merge(d)}
        jl = recs["jordan.lee@northwind.example"]
        self.assertEqual(jl["outcome"], "person")
        self.assertIn("below the confidence floor", jl["check"])
        self.assertIn("may have moved", jl["check"])
        self.assertTrue(recs["info@northwind.example"]["outcome"].startswith("company only"))
        self.assertEqual(recs["sam@globex.example"]["outcome"], "not found")
        self.assertTrue(recs["someone@gmail.com"]["outcome"].startswith("webmail"))
        self.assertEqual(recs["me@own.example"]["outcome"], "excluded")


class TestSharedMailboxRule(unittest.TestCase):
    def test_parse_person_drops_shared_mailboxes(self):
        rec = enrich.parse_person({"full_name": "Jordan Lee", "work_email": "info@northwind.example",
                                   "emails": [{"address": "jordan@northwind.example"},
                                              {"address": "sales@northwind.example"}]},
                                  8, 4, "Jordan Lee")
        self.assertEqual(rec["email"], "jordan@northwind.example")
        self.assertTrue(enrich.is_role_address("Investor.Relations@corp.example"))
        self.assertFalse(enrich.is_role_address("irene@corp.example"))


if __name__ == "__main__":
    unittest.main()
