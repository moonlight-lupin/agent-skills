"""Entity research — helpers for a cited background dossier on a company or person.

This handles the DETERMINISTIC bits; the actual research (web search / fetch, the
deep-research engine, PDL) is agent-driven per SKILL.md. Two pieces:

  * screen_lists(name) — name-match the public consolidated SANCTIONS lists (OFAC SDN +
    Consolidated, UK-OFSI, UN; extensible) and return POTENTIAL-MATCH SIGNALS. Fetched live (cached), degrades
    gracefully offline. A match is a SIGNAL to escalate to your compliance / AML
    function — NOT a determination; NO match is NOT a clearance (the lists aren't
    exhaustive; this is not a professional screening tool like World-Check).
  * dossier(subject, sections, ...) — assemble the cited markdown dossier (the six lenses
    + a 'not a determination' header + escalation flags).

    from entity_research import screen_lists, dossier
    sig = screen_lists("Acme Trading Co")
    print(dossier("Acme Trading Co", {"Identity & background": "...", ...},
                  flags=["Sanctions: potential OFAC match — escalate to compliance"]))

SAFETY: research & compilation, not a CDD/AML/sanctions determination. Cite everything;
allegations are not facts. See the SKILL's Data handling note (search the name, not the relationship).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# Public consolidated lists (official government sources — public domain). URLs drift —
# override the constants if they move. Coverage: US (OFAC SDN + non-SDN Consolidated),
# UK (OFSI), UN. National/local autonomous lists often have no clean machine-readable feed —
# do a manual portal check for the subject's home jurisdiction; absence of a feed is not screening.
LIST_URLS = {
    "OFAC-SDN": "https://www.treasury.gov/ofac/downloads/sdn.csv",                            # US
    "OFAC-CONS": "https://www.treasury.gov/ofac/downloads/consolidated/cons_prim.csv",        # US (non-SDN)
    "UK-OFSI": "https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv",  # UK
    "UN": "https://scsanctions.un.org/resources/xml/en/consolidated.xml",                     # UN
}
DEFAULT_LISTS = ("OFAC-SDN", "OFAC-CONS", "UK-OFSI", "UN")
_CACHE_DIR = ".sanctions_cache"
_CACHE_DAYS = 7
_CORP_SUFFIXES = {"ltd", "limited", "inc", "incorporated", "llc", "llp", "plc", "pte",
                  "co", "corp", "corporation", "company", "gmbh", "sa", "bv", "pty",
                  "holdings", "group", "fze", "fzco"}
# Generic business words that must NOT, on their own, create a match — a name match needs at
# least one DISTINCTIVE shared token. Prevents 'X Capital Management' matching 'Y Capital
# Management' on the generic words alone (a common false-positive source).
_GENERIC = {"capital", "management", "managment", "partners", "partner", "investment",
            "investments", "investing", "fund", "funds", "asset", "assets", "global",
            "international", "trading", "ventures", "venture", "advisors", "advisers",
            "advisory", "services", "solutions", "enterprises", "consultancy",
            "consultancies", "consulting", "properties", "property", "realty", "estate",
            "the", "and", "of"}


def _norm(s: str) -> list[str]:
    """Normalise a name to comparable tokens (lowercase, depunctuated, suffixes dropped)."""
    s = re.sub(r"[^\w\s]", " ", str(s or "").lower())
    toks = [t for t in s.split() if t and t not in _CORP_SUFFIXES]
    return toks


def _match(query: str, entries: list[dict], threshold: float = 0.6) -> list[dict]:
    """Token-based name match. Strong = query is a token-subset of a candidate (or vice
    versa); partial = overlap >= threshold. Returns matches with a score + matched name."""
    q = set(_norm(query))
    if not q:
        return []
    out = []
    for e in entries:
        best = None
        for cand in [e.get("name", "")] + list(e.get("aliases") or []):
            c = set(_norm(cand))
            if not c:
                continue
            shared = q & c
            if not (shared - _GENERIC):     # need ≥1 DISTINCTIVE shared token (not just generic)
                continue
            overlap = len(shared)
            subset = q <= c or c <= q
            score = 1.0 if subset else overlap / max(len(q), 1)
            # require subset, or (>=2 shared tokens AND coverage past threshold)
            if subset or (overlap >= 2 and score >= threshold):
                if best is None or score > best[0]:
                    best = (score, cand)
        if best:
            out.append({"matched_name": best[1], "score": round(best[0], 2),
                        "program": e.get("program"), "type": e.get("type")})
    out.sort(key=lambda m: -m["score"])
    return out


# --------------------------------------------------------------------------- #
# List fetchers (cached, graceful). Parsing is best-effort; formats can change.
# --------------------------------------------------------------------------- #
def _fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "entity-research/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 (public gov lists)
        return r.read()


def _parse_ofac_sdn(raw: bytes) -> list[dict]:
    entries = []
    text = raw.decode("utf-8", errors="ignore")
    for row in csv.reader(io.StringIO(text)):
        # OFAC uses "-0- " (or "-0-") as a placeholder for empty fields; strip and check
        # both forms so a whitespace format change doesn't create fake entries.
        if len(row) >= 4 and row[1].strip() not in ("", "-0-"):
            entries.append({"name": row[1].strip(), "type": row[2].strip(),
                            "program": row[3].strip(), "aliases": []})
    return entries


def _parse_un(raw: bytes) -> list[dict]:
    entries = []
    root = ET.fromstring(raw)
    for node in root.iter():
        tag = node.tag.upper()
        if tag in ("INDIVIDUAL", "ENTITY"):
            parts = []
            aliases = []
            for ch in node:
                t = ch.tag.upper()
                if t.startswith(("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME",
                                 "NAME_ORIGINAL_SCRIPT")) and ch.text:
                    parts.append(ch.text.strip())
                if t.startswith("INDIVIDUAL_ALIAS") or t.startswith("ENTITY_ALIAS"):
                    a = ch.find("ALIAS_NAME")
                    if a is not None and a.text:
                        aliases.append(a.text.strip())
            name = " ".join(p for p in parts if p)
            if name:
                entries.append({"name": name, "type": tag.title(),
                                "program": "UN", "aliases": aliases})
    return entries


def _parse_uk_ofsi(raw: bytes) -> list[dict]:
    """UK OFSI consolidated list CSV. Line 1 = 'Last Updated,...'; line 2 = header; names
    are split across the first six columns (Name 6, Name 1..Name 5) — token-set matching is
    order-independent, so we just join them. Alias rows add recall."""
    entries = []
    text = raw.decode("utf-8", errors="ignore")
    rows = csv.reader(io.StringIO(text))
    for i, row in enumerate(rows):
        if i < 2 or len(row) < 6:                 # skip 'Last Updated' + header
            continue
        name = " ".join(c.strip() for c in row[0:6] if c and c.strip())
        if name:
            entries.append({"name": name, "type": None, "program": "UK-OFSI", "aliases": []})
    return entries


_PARSERS = {"OFAC-SDN": _parse_ofac_sdn, "OFAC-CONS": _parse_ofac_sdn,
            "UK-OFSI": _parse_uk_ofsi, "UN": _parse_un}


def _load_list(listname: str, cache_dir: str, refresh: bool) -> list[dict] | None:
    cache = Path(cache_dir) / f"{listname}.json"
    if not refresh and cache.is_file():
        try:
            blob = json.loads(cache.read_text(encoding="utf-8"))
            fetched = dt.date.fromisoformat(blob.get("fetched", "1900-01-01"))
            if (dt.date.today() - fetched).days <= _CACHE_DAYS:
                return blob["entries"]
        except Exception:
            pass
    try:
        raw = _fetch(LIST_URLS[listname])
        entries = _PARSERS[listname](raw)
        if not entries:
            return None
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"fetched": dt.date.today().isoformat(),
                                     "entries": entries}), encoding="utf-8")
        return entries
    except Exception:                       # network/parse failure → degrade gracefully
        if cache.is_file():                 # fall back to any stale cache
            try:
                return json.loads(cache.read_text(encoding="utf-8"))["entries"]
            except Exception:
                return None
        return None


def screen_lists(name: str, lists=DEFAULT_LISTS, cache_dir: str = _CACHE_DIR,
                 refresh: bool = False, threshold: float = 0.6,
                 _entries: dict | None = None) -> dict:
    """Name-match `name` against the public consolidated sanctions lists — US (OFAC SDN +
    Consolidated), UK (OFSI) and UN. Returns
    {name, checked, unavailable, matches[], note}. SIGNAL ONLY — escalate any match to
    your compliance / AML function; NO match is NOT a clearance (lists/coverage are
    partial — national/local lists may have no clean feed: do a manual portal check; matching is
    token-based, not fuzzy/phonetic).

    `threshold` controls partial-match sensitivity (0.0=match anything distinctive,
    1.0=subset only). Lower it for broader recall (more false positives); raise it for
    fewer hits. Default 0.6 is a balanced starting point."""
    checked, unavailable, matches = [], [], []
    for ln in lists:
        entries = _entries.get(ln) if _entries is not None else _load_list(ln, cache_dir, refresh)
        if entries is None:
            unavailable.append(ln)
            continue
        checked.append(ln)
        for m in _match(name, entries, threshold=threshold):
            matches.append({"list": ln, **m})
    matches.sort(key=lambda m: -m["score"])
    return {
        "name": name, "checked": checked, "unavailable": unavailable, "matches": matches,
        "note": ("SIGNAL ONLY — potential matches must be verified by your compliance / AML "
                 "function; absence of a match is NOT a clearance. Coverage: US (OFAC "
                 "SDN+Consolidated), UK (OFSI), UN; for national/local autonomous measures do a "
                 "manual portal check (often no clean feed). "
                 "Matching is token-based, not fuzzy/phonetic. "
                 + (f"Could not fetch: {', '.join(unavailable)} — do an official-portal web "
                    f"check for those." if unavailable else "")),
    }


# --------------------------------------------------------------------------- #
# Dossier assembly
# --------------------------------------------------------------------------- #
LENSES = ["Identity & background", "Ownership & key management", "Adverse / negative media",
          "Sanctions / PEP / watchlist signals", "Litigation & regulatory", "Summary & flags"]


def dossier(subject: str, sections, *, identifiers: dict | None = None, flags=None,
            sources=None, as_of: str | None = None, is_person: bool = False) -> str:
    """Assemble the cited markdown dossier. `sections` is a dict {lens_title: markdown}
    (use LENSES order where present). `flags` = escalation lines. `sources` = list of
    'Title — URL (date)' strings for a consolidated source list."""
    as_of = as_of or dt.date.today().strftime("%d %b %Y")
    L = [f"# Entity research — {subject}",
         f"_{'Person' if is_person else 'Entity'} background dossier · as of {as_of}_",
         "",
         "> **Research & compilation — not a determination.** This dossier is cited research "
         "for a human to assess. It is **not** a CDD/AML/sanctions determination or a "
         "clearance: a sanctions/PEP signal is to **escalate to compliance / "
         "your AML function**, and negative items are **allegations with sources**, not proven "
         "facts.", ""]
    if identifiers:
        L.append("## Identifiers")
        for k, v in identifiers.items():
            L.append(f"- **{k}:** {v}")
        L.append("")
    if flags:
        L.append("## ⚠ Escalation flags")
        L += [f"- {f}" for f in flags]
        L.append("")
    if isinstance(sections, dict):
        ordered = [k for k in LENSES if k in sections] + [k for k in sections if k not in LENSES]
        items = [(k, sections[k]) for k in ordered]
    else:
        items = list(sections)
    for title, body in items:
        L.append(f"## {title}")
        L.append(str(body).strip() or "_No material findings located._")
        L.append("")
    if sources:
        L.append("## Sources")
        L += [f"{i}. {s}" for i, s in enumerate(sources, 1)]
        L.append("")
    L.append("_Internal — keep local. A draft for review by a qualified person; not "
             "advice and not a screening determination. Verify any signal before acting._")
    return "\n".join(L).strip()


if __name__ == "__main__":
    import argparse
    _ap = argparse.ArgumentParser(
        description="Entity-research helpers. The agent imports this module; the only "
                    "standalone command is an offline self-test.")
    _ap.add_argument("--self-test", action="store_true",
                     help="Run the offline matcher + dossier self-test (no network).")
    _args = _ap.parse_args()
    if not _args.self_test:
        _ap.error("nothing to run — pass --self-test for the offline self-test")
    # Offline self-test — matcher + dossier (no network).
    fixture = {"OFAC-SDN": [
        {"name": "ACME TRADING CO", "type": "Entity", "program": "SDGT", "aliases": ["ACME TRADING LLC"]},
        {"name": "JOHN A SMITH", "type": "Individual", "program": "UKRAINE-EO13662", "aliases": []},
    ]}
    print("match 'Acme Trading':", _match("Acme Trading", fixture["OFAC-SDN"]))
    print("match 'Jane Doe':", _match("Jane Doe", fixture["OFAC-SDN"]))
    sig = screen_lists("Acme Trading Co", lists=("OFAC-SDN",), _entries=fixture)
    print("screen matches:", len(sig["matches"]), "| note ok:", "SIGNAL ONLY" in sig["note"])
    d = dossier("Acme Trading Co",
                {"Identity & background": "Registered trading company (reg. no. ...) [src].",
                 "Adverse / negative media": "2024 press alleges ... (Source, 12 Mar 2024).",
                 "Sanctions / PEP / watchlist signals": "Potential OFAC-SDN match — see flags."},
                identifiers={"Jurisdiction": "Example", "Type": "Company"},
                flags=["Sanctions: potential OFAC-SDN match on 'Acme Trading' — escalate to compliance"],
                sources=["Companies registry — https://... (14 Jun 2026)"])
    print("[self-test] dossier chars:", len(d), "| has banner:",
          "not a determination" in d, "| has flags:", "Escalation flags" in d)
