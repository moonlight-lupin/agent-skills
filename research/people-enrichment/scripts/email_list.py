#!/usr/bin/env python3
"""
email_list.py - enrich a list of email addresses: triage first, one lookup per company, people last.

  triage  Sort the addresses for free (no network) into webmail, shared mailbox (info@, sales@ ...),
          personal work address, invalid and excluded. Writes:
            email_triage.csv  one row per unique address with its triage class
            companies.csv     ONE row per unique company domain (website column) -> company-enrich
            people.csv        personal work addresses only (email column)     -> person-enrich
          and prints the lookup counts so the cost can be agreed before anything is sent.
  merge   Join the enrich.py outputs back onto the triage rows -> one .xlsx (or .csv) with an
          outcome per address: person, company only, webmail, shared mailbox, not found, excluded.

Webmail addresses are never looked up (no company data, and they are private). Shared mailboxes
get the company lookup only. This script makes no network calls; the lookups are the existing
enrich.py commands:

  python email_list.py triage --input emails.csv --out-dir work [--exclude-domain example.org]
  python enrich.py company-enrich --input work/companies.csv --output work/companies.xlsx
  python enrich.py person-enrich  --input work/people.csv    --output work/people.xlsx   # optional
  python email_list.py merge --dir work --output enriched_list.xlsx
"""

import argparse
import csv
import sys
from pathlib import Path

WEBMAIL = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.co.jp", "yahoo.com.sg", "yahoo.co.uk",
    "hotmail.com", "outlook.com", "live.com", "live.jp", "msn.com", "icloud.com", "me.com",
    "aol.com", "protonmail.com", "proton.me", "gmx.com", "gmx.de", "mail.com", "qq.com", "163.com",
    "126.com", "nifty.com", "docomo.ne.jp", "ezweb.ne.jp", "softbank.ne.jp", "web.de", "yandex.ru",
}
ROLE_LOCALPARTS = {
    "info", "ir", "investor", "investors", "investorrelations", "investor.relations", "enquiries",
    "enquiry", "inquiries", "inquiry", "contact", "contactus", "admin", "hello", "office", "sales",
    "support", "help", "hr", "careers", "jobs", "recruitment", "marketing", "media", "press", "pr",
    "team", "mail", "general", "reception", "accounts", "finance", "billing", "compliance", "legal",
    "noreply", "no-reply", "webmaster", "service", "customerservice", "ops", "operations",
}
TRIAGE = "email_triage.csv"
COLS = ["email", "outcome", "company", "domain", "industry", "size", "country", "full_name",
        "title", "linkedin_url", "check"]


def classify(addr, exclude=()):
    """(class, domain) for one address. Classes: invalid, excluded, webmail, shared mailbox, personal."""
    a = str(addr or "").strip().lower()
    if a.count("@") != 1 or not a.split("@")[0] or "." not in a.split("@")[1]:
        return "invalid", ""
    local, dom = a.split("@")
    if any(dom == d or dom.endswith("." + d) for d in exclude):
        return "excluded", dom
    if dom in WEBMAIL:
        return "webmail", dom
    if local in ROLE_LOCALPARTS or local.replace("_", ".") in ROLE_LOCALPARTS:
        return "shared mailbox", dom
    return "personal", dom


def read_addresses(path):
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig", errors="replace")
    if p.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        if rows:
            key = next((k for k in rows[0] if k and k.strip().lower() in
                        ("email", "email address", "e-mail", "work email")), None)
            if not key:
                sys.exit("No email column found (expected 'email').")
            return [r[key] for r in rows if r.get(key)]
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def triage(input_path, out_dir, exclude=()):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    seen, rows = set(), []
    for raw in read_addresses(input_path):
        a = raw.strip().lower()
        if a in seen:
            continue
        seen.add(a)
        cls, dom = classify(a, [d.lower() for d in exclude])
        rows.append((a, dom, cls))
    _write_csv(out / TRIAGE, ["email", "domain", "triage"], rows)
    domains = sorted({d for _, d, c in rows if c in ("personal", "shared mailbox")})
    people = [a for a, _, c in rows if c == "personal"]
    _write_csv(out / "companies.csv", ["website"], [[d] for d in domains])
    _write_csv(out / "people.csv", ["email"], [[e] for e in people])
    counts = {}
    for _, _, c in rows:
        counts[c] = counts.get(c, 0) + 1
    return {"addresses": len(rows), "counts": counts, "company_lookups": len(domains),
            "person_lookups": len(people)}


def _read_xlsx(path):
    """{Query: row-dict} from an enrich.py output sheet (first sheet, header row 1)."""
    if not path or not Path(path).exists():
        return {}
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True)
    try:
        it = wb.worksheets[0].iter_rows(values_only=True)
        head = [str(h or "") for h in next(it)]
        out = {}
        for r in it:
            rec = dict(zip(head, r))
            q = str(rec.get("Query") or "").strip().lower()
            if q:
                out[q] = rec
    finally:
        wb.close()                                   # read-only mode keeps the file open on Windows
    return out


def merge(dir_, people_xlsx=None, companies_xlsx=None):
    d = Path(dir_)
    people = _read_xlsx(people_xlsx or d / "people.xlsx")
    companies = _read_xlsx(companies_xlsx or d / "companies.xlsx")
    rows = list(csv.DictReader((d / TRIAGE).read_text(encoding="utf-8").splitlines()))
    out = []
    for r in rows:
        rec = {k: "" for k in COLS}
        rec.update({"email": r["email"], "domain": r["domain"]})
        t = r["triage"]
        if t in ("webmail", "invalid", "excluded"):
            rec["outcome"] = {"webmail": "webmail - not looked up", "invalid": "invalid address",
                              "excluded": "excluded"}[t]
            out.append(rec)
            continue
        checks = []
        c = companies.get(r["domain"])
        if c and c.get("Status") in ("matched", "needs_review"):
            rec.update({"company": c.get("Company name") or "", "industry": c.get("Industry") or "",
                        "size": c.get("Size") or "", "country": c.get("Country") or ""})
            if c.get("Status") == "needs_review":
                checks.append("company match below the confidence floor - confirm")
        p = people.get(r["email"]) if t == "personal" else None
        if p and p.get("Status") in ("matched", "needs_review"):
            rec.update({"full_name": p.get("Full name") or "", "title": p.get("Current title") or "",
                        "linkedin_url": p.get("LinkedIn URL") or ""})
            if p.get("Status") == "needs_review":
                checks.append("person match below the confidence floor - confirm the name")
            pc = str(p.get("Current company") or "").strip().lower()
            if pc and rec["company"] and pc != rec["company"].strip().lower():
                checks.append("person's current company differs from the address's domain - may have moved")
        if rec["full_name"]:
            rec["outcome"] = "person"
        elif rec["company"]:
            rec["outcome"] = "company only" + (" (shared mailbox)" if t == "shared mailbox" else "")
        else:
            rec["outcome"] = "not found"
        rec["check"] = "; ".join(checks)
        out.append(rec)
    return out


def write(recs, output):
    outp = Path(output)
    if outp.suffix.lower() == ".xlsx":
        try:
            from openpyxl import Workbook
        except ImportError:
            outp = outp.with_suffix(".csv")
            print("openpyxl not installed - writing CSV instead.")
    if outp.suffix.lower() == ".xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "Enriched list"
        ws.append([c.replace("_", " ").capitalize() for c in COLS])
        for r in recs:
            ws.append([r[c] for c in COLS])
        ws.freeze_panes = "B2"
        wb.save(outp)
    else:
        _write_csv(outp, COLS, [[r[c] for c in COLS] for r in recs])
    return outp


def main(argv=None):
    ap = argparse.ArgumentParser(description="Enrich a list of email addresses: triage, then merge.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("triage")
    t.add_argument("--input", required=True, help=".csv with an 'email' column, or one address per line")
    t.add_argument("--out-dir", default="work")
    t.add_argument("--exclude-domain", action="append", default=[],
                   help="a domain never looked up, e.g. your own organisation's (repeatable)")
    m = sub.add_parser("merge")
    m.add_argument("--dir", default="work")
    m.add_argument("--people", help="person-enrich output (default DIR/people.xlsx)")
    m.add_argument("--companies", help="company-enrich output (default DIR/companies.xlsx)")
    m.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "triage":
        r = triage(args.input, args.out_dir, args.exclude_domain)
        print(f"{r['addresses']} unique addresses: " +
              ", ".join(f"{k} {v}" for k, v in sorted(r["counts"].items())))
        print(f"companies.csv: {r['company_lookups']} company lookups (one per domain)")
        print(f"people.csv:    {r['person_lookups']} person lookups - run only if names/titles are needed")
        print("Webmail, invalid and excluded addresses are not looked up. Agree the lookup count "
              "(1 credit per match) before running enrich.py.")
    else:
        recs = merge(args.dir, args.people, args.companies)
        outp = write(recs, args.output)
        counts = {}
        for r in recs:
            k = r["outcome"].split(" (")[0]
            counts[k] = counts.get(k, 0) + 1
        print(f"Wrote {outp}: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
