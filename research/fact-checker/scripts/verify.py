#!/usr/bin/env python3
"""Rule-based claim structuring, source assessment, and verification reporting."""

from __future__ import annotations

import argparse
import datetime as _datetime
import json
import os
import re
import sys

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "had",
    "has", "have", "he", "her", "his", "in", "into", "is", "it", "its",
    "of", "on", "or", "said", "says", "she", "that", "the", "their", "they",
    "this", "to", "was", "were", "will", "with", "grew", "growth", "rose",
    "fell", "increased", "decreased", "announced", "launched", "acquired",
}

EVENT_VERBS = re.compile(
    r"\b(acquired|merged|launched|announced|released|resigned|appointed|won|filed|"
    r"approved|closed|opened|founded|introduced|signed|completed|cancelled)\b",
    re.IGNORECASE,
)
RELATIONSHIP_PATTERNS = [
    re.compile(r"\bis\s+(?:the\s+)?(?:ceo|cfo|cto|president|chair|founder|owner|subsidiary)\s+of\b", re.IGNORECASE),
    re.compile(r"\b(?:belongs\s+to|owned\s+by|part\s+of|subsidiary\s+of|partnered\s+with|reports\s+to)\b", re.IGNORECASE),
]
DATE_PATTERN = re.compile(
    r"\b(?:\d{4}|(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},?\s+\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
    re.IGNORECASE,
)
PERCENT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%")
NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")
CAPITALIZED_PATTERN = re.compile(r"\b(?:[A-Z][A-Za-z0-9&.'-]*|[A-Z]{2,})\b")
COMMON_TWO_LEVEL_SUFFIXES = {
    "co.uk", "org.uk", "gov.uk", "ac.uk", "com.au", "net.au", "org.au",
    "com.sg", "gov.sg", "edu.sg", "com.my", "com.hk", "co.jp", "com.br",
    "com.cn", "com.tw", "co.nz", "co.in",
}
WIRE_SERVICES = {
    "ap": re.compile(r"(?:associated[-_\s]?press|\bapnews\b|\bap\b)", re.IGNORECASE),
    "reuters": re.compile(r"\breuters\b", re.IGNORECASE),
    "afp": re.compile(r"(?:\bafp\b|agence[-_\s]?france[-_\s]?presse)", re.IGNORECASE),
    "bloomberg": re.compile(r"\bbloomberg\b", re.IGNORECASE),
}


def unique_preserve_order(items: list[str]) -> list[str]:
    """Return items without duplicates while preserving first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = item.strip(" \t\n\r.,;:()[]{}\"'")
        cleaned = re.sub(r"[’']s$", "", cleaned)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            out.append(cleaned)
    return out


def detect_claim_type(claim: str) -> str:
    """Detect a claim type from rule-based surface patterns."""
    if re.search(r"[\"“”‘’].+?[\"“”‘’]", claim):
        return "quote"
    if PERCENT_PATTERN.search(claim) or (NUMBER_PATTERN.search(claim) and re.search(r"\b(rate|gdp|revenue|profit|population|inflation|grew|growth|percent|million|billion|trillion)\b", claim, re.IGNORECASE)):
        return "statistic"
    if any(pattern.search(claim) for pattern in RELATIONSHIP_PATTERNS):
        return "relationship"
    has_specific_date = bool(re.search(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?|"
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
        claim,
        re.IGNORECASE,
    ))
    if DATE_PATTERN.search(claim) and has_specific_date and re.search(r"\b(on|as of|since|until|launched|born|died|started|ended)\b", claim, re.IGNORECASE):
        return "date"
    if EVENT_VERBS.search(claim):
        return "event"
    if DATE_PATTERN.search(claim):
        return "date"
    return "event"


def extract_time_period(claim: str) -> str | None:
    """Extract the first explicit year or date-like time period from a claim."""
    date_match = DATE_PATTERN.search(claim)
    if not date_match:
        return None
    return date_match.group(0)


def extract_key_terms(claim: str) -> list[str]:
    """Extract capitalized terms, percentages, and numbers from a claim."""
    terms: list[str] = []
    terms.extend(term for term in CAPITALIZED_PATTERN.findall(claim) if term.lower() not in STOPWORDS)
    terms.extend(PERCENT_PATTERN.findall(claim))
    for number in NUMBER_PATTERN.findall(claim):
        if number not in [pct.rstrip("%") for pct in PERCENT_PATTERN.findall(claim)]:
            terms.append(number)

    for word in re.findall(r"\b[A-Za-z][A-Za-z0-9&.'-]*\b", claim):
        lower = word.lower()
        if lower not in STOPWORDS and len(word) > 2 and (word.isupper() or lower in {"gdp", "ceo", "cfo", "cto"}):
            terms.append(word.upper() if lower in {"gdp", "ceo", "cfo", "cto"} else word)

    return unique_preserve_order(terms)


def extract_entity(claim: str, key_terms: list[str]) -> str | None:
    """Infer the main entity from capitalized terms."""
    for term in key_terms:
        if not PERCENT_PATTERN.fullmatch(term) and not NUMBER_PATTERN.fullmatch(term):
            return term
    match = CAPITALIZED_PATTERN.search(claim)
    return match.group(0) if match else None


def extract_metric(claim: str) -> str | None:
    """Infer a metric label from common statistical claim patterns."""
    lowered = claim.lower()
    if "gdp" in lowered and re.search(r"\b(grew|growth|increase|increased|rose)\b", lowered):
        return "GDP growth rate"
    if "inflation" in lowered:
        return "inflation rate"
    if "revenue" in lowered:
        return "revenue"
    if "profit" in lowered:
        return "profit"
    if "population" in lowered:
        return "population"
    if "unemployment" in lowered:
        return "unemployment rate"
    return None


def extract_value(claim: str) -> str | None:
    """Extract the first percentage or numeric value from a claim."""
    pct = PERCENT_PATTERN.search(claim)
    if pct:
        return pct.group(0)
    num = NUMBER_PATTERN.search(claim)
    return num.group(0) if num else None


def generate_search_queries(claim: str, claim_type: str, key_terms: list[str], entity: str | None, metric: str | None, value: str | None, time_period: str | None) -> list[str]:
    """Generate 3-5 targeted search queries from structured claim fields."""
    terms_without_values = [term for term in key_terms if term not in {value, time_period}]
    base_terms = " ".join(terms_without_values[:4]) or claim
    queries: list[str] = []

    if claim_type == "statistic":
        metric_terms = metric or "statistic"
        entity_terms = entity or base_terms
        year = time_period or ""
        if metric and metric.lower() == "gdp growth rate":
            queries.append(" ".join(part for part in [entity_terms, "GDP growth", year] if part))
            if value:
                queries.append(" ".join(part for part in [entity_terms, "GDP", value, year, "official data"] if part))
            queries.append(" ".join(part for part in [entity_terms, "economic growth", year, "official"] if part))
        else:
            queries.append(" ".join(part for part in [entity_terms, metric_terms, year] if part))
            if value:
                queries.append(" ".join(part for part in [entity_terms, value, metric_terms, year, "official"] if part))
            queries.append(" ".join(part for part in [entity_terms, metric_terms, year, "revised final data"] if part))
    elif claim_type == "quote":
        quoted = re.search(r"[\"“”‘’](.+?)[\"“”‘’]", claim)
        phrase = quoted.group(1) if quoted else base_terms
        queries.extend([f'"{phrase}"', f'"{phrase}" transcript', f'"{phrase}" original source'])
    elif claim_type == "relationship":
        queries.extend([f"{base_terms} official", f"{base_terms} current", f"{base_terms} filing profile"])
    elif claim_type == "date":
        queries.extend([f"{base_terms} date", f"{base_terms} official timeline", f"{base_terms} history"])
    else:
        queries.extend([base_terms, f"{base_terms} official announcement", f"{base_terms} confirmed"])

    if time_period:
        queries.append(f"{base_terms} {time_period} revised updated")
    queries.append(f"{base_terms} correction dispute")
    return unique_preserve_order([query for query in queries if query])[:5]


def structure_claim(claim: str) -> dict[str, object]:
    """Parse a factual claim into a structured JSON-compatible dictionary."""
    claim_type = detect_claim_type(claim)
    key_terms = extract_key_terms(claim)
    time_period = extract_time_period(claim)
    entity = extract_entity(claim, key_terms)
    metric = extract_metric(claim)
    value = extract_value(claim)
    queries = generate_search_queries(claim, claim_type, key_terms, entity, metric, value, time_period)
    return {
        "claim_text": claim,
        "claim_type": claim_type,
        "key_terms": key_terms,
        "time_period": time_period,
        "search_queries": queries,
        "entity": entity,
        "metric": metric,
        "value": value,
    }


def extract_hostname(url: str) -> str:
    """Extract a lowercase hostname from a URL-like string without network access."""
    text = url.strip().lower()
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text)
    text = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    text = text.split("@")[-1].split(":", 1)[0]
    if text.startswith("www."):
        text = text[4:]
    return text


def root_domain(url: str) -> str:
    """Return a best-effort registrable root domain for a URL."""
    host = extract_hostname(url)
    parts = [part for part in host.split(".") if part]
    if len(parts) <= 2:
        return host
    suffix2 = ".".join(parts[-2:])
    if suffix2 in COMMON_TWO_LEVEL_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return suffix2


def detect_wire_service(url: str) -> str | None:
    """Detect likely wire-service markers from a URL string."""
    normalized = re.sub(r"[^a-z0-9]+", " ", url.lower())
    for service, pattern in WIRE_SERVICES.items():
        if pattern.search(normalized):
            return service
    return None


def assess_urls(urls: list[str]) -> dict[str, object]:
    """Assess URL root domains and simple independence warnings."""
    cleaned_urls = [url.strip() for url in urls if url.strip()]
    entries: list[dict[str, str | None]] = []
    domains: list[str] = []
    wire_counts: dict[str, int] = {}
    for url in cleaned_urls:
        domain = root_domain(url)
        wire = detect_wire_service(url)
        domains.append(domain)
        if wire:
            wire_counts[wire] = wire_counts.get(wire, 0) + 1
        entries.append({"url": url, "root_domain": domain, "possible_wire_service": wire})

    unique_domains = unique_preserve_order(domains)
    repeated_domains = {domain: domains.count(domain) for domain in unique_domains if domains.count(domain) > 1}
    wire_clusters = {service: count for service, count in wire_counts.items() if count > 1}
    is_independent = len(unique_domains) == len(cleaned_urls) and not wire_clusters and len(cleaned_urls) > 1
    if len(cleaned_urls) <= 1:
        is_independent = False

    notes: list[str] = []
    if repeated_domains:
        notes.append("Some URLs share the same root domain; do not count them as independent confirmations.")
    if wire_clusters:
        notes.append("Multiple URLs appear to reference the same wire service; check for syndication.")
    if not notes and is_independent:
        notes.append("Root domains differ and no simple wire-service URL markers were detected.")
    elif not notes:
        notes.append("Insufficient URLs for independence assessment.")

    return {
        "urls": entries,
        "root_domains": unique_domains,
        "independence_count": len(unique_domains),
        "is_independent": is_independent,
        "repeated_domains": repeated_domains,
        "wire_service_clusters": wire_clusters,
        "notes": notes,
    }


def load_json_file(path: str) -> object:
    """Load JSON from a UTF-8 file."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_text(path: str, content: str) -> None:
    """Write UTF-8 text, creating parent directories when needed."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def normalize_stance(source: dict[str, object]) -> str:
    """Normalize a source stance value to confirm, refute, nuance, or other."""
    stance = str(source.get("stance", "")).strip().lower()
    if stance in {"confirm", "confirms", "support", "supports", "supporting"}:
        return "confirm"
    if stance in {"refute", "refutes", "contradict", "contradicts", "deny", "denies"}:
        return "refute"
    if stance in {"nuance", "nuances", "partial", "qualify", "qualifies", "mixed"}:
        return "nuance"
    return "other"


def is_authoritative(source: dict[str, object]) -> bool:
    """Return whether a source type is normally authoritative for likely-true evidence."""
    return str(source.get("source_type", "")).strip().lower() in {"official", "academic", "report"}


def parse_source_date(source: dict[str, object]) -> _datetime.date | None:
    """Parse the best available source date from common source fields."""
    for field in ("published_at", "date", "accessed_at"):
        value = source.get(field)
        if not value:
            continue
        text = str(value)
        match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
        if match:
            try:
                return _datetime.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                continue
        year = re.search(r"\b(\d{4})\b", text)
        if year:
            try:
                return _datetime.date(int(year.group(1)), 1, 1)
            except ValueError:
                continue
    return None


def determine_verdict(claim: dict[str, object], sources: list[dict[str, object]]) -> dict[str, object]:
    """Determine a verification verdict from claim metadata and collected sources."""
    # A source must be independently checkable — no URL, no weight in the verdict.
    reliable_sources = [source for source in sources if source.get("url")]
    confirming = [source for source in reliable_sources if normalize_stance(source) == "confirm"]
    refuting = [source for source in reliable_sources if normalize_stance(source) == "refute"]
    nuancing = [source for source in reliable_sources if normalize_stance(source) == "nuance"]
    confirm_domains = {root_domain(str(source.get("url", ""))) for source in confirming if source.get("url")}
    # Distinct domains can still be one voice: if every confirming URL carries
    # the same wire-service marker, treat them as syndicated copies, not
    # independent corroboration.
    confirm_wires = [detect_wire_service(str(source.get("url", ""))) for source in confirming]
    all_same_wire = bool(confirm_wires) and None not in confirm_wires and len(set(confirm_wires)) == 1

    confirm_dates = [date for date in (parse_source_date(source) for source in confirming) if date is not None]
    refute_dates = [date for date in (parse_source_date(source) for source in refuting) if date is not None]
    newest_confirm = max(confirm_dates) if confirm_dates else None
    newest_refute = max(refute_dates) if refute_dates else None
    has_time_period = bool(claim.get("time_period"))

    if confirming and refuting and newest_confirm and newest_refute and newest_refute > newest_confirm and has_time_period:
        return {"verdict": "Outdated", "confidence": "High", "reason": "Older confirming evidence is superseded by newer contradictory evidence."}
    if confirming and refuting:
        return {"verdict": "Disputed", "confidence": "Medium", "reason": "Collected sources include both confirmation and contradiction."}
    if len(confirm_domains) >= 2 and not all_same_wire:
        return {"verdict": "Verified", "confidence": "High", "reason": "At least two independent root domains confirm the claim and no refutation was supplied."}
    if len(confirm_domains) >= 2 and all_same_wire:
        return {"verdict": "Likely true", "confidence": "Medium", "reason": "Multiple domains confirm the claim, but all appear to syndicate the same wire service — corroboration is not independent."}
    if len(confirming) == 1 and is_authoritative(confirming[0]):
        return {"verdict": "Likely true", "confidence": "Medium", "reason": "One authoritative source confirms the claim, but independent corroboration is limited."}
    if confirming and not refuting:
        return {"verdict": "Likely true", "confidence": "Medium", "reason": "Some confirmation was supplied, but independence or authority is limited."}
    if refuting and not confirming:
        return {"verdict": "Unverified", "confidence": "Low", "reason": "No reliable confirming sources were supplied; at least one source refutes the claim."}
    if nuancing:
        return {"verdict": "Unverified", "confidence": "Low", "reason": "Sources nuance the claim but do not directly confirm it."}
    return {"verdict": "Unverified", "confidence": "Low", "reason": "No reliable sources directly confirm the claim."}


def verdict_label(verdict: str) -> str:
    """Return a display label with icon for a verdict."""
    labels = {
        "Verified": "✅ Verified",
        "Likely true": "⚠️ Likely true",
        "Disputed": "⚖️ Disputed",
        "Unverified": "❓ Unverified",
        "Outdated": "📅 Outdated",
    }
    return labels.get(verdict, verdict)


def format_source_line(index: int, source: dict[str, object]) -> str:
    """Format a source as a Markdown numbered-list item."""
    title = str(source.get("title") or "Untitled source")
    url = str(source.get("url") or "")
    passage = str(source.get("passage") or "").strip().replace("\n", " ")
    source_type = str(source.get("source_type") or "other")
    stance = normalize_stance(source)
    return f'{index}. [{title}]({url}) — "{passage}" ({source_type}; {stance})'


def build_report(claim: dict[str, object], sources: list[dict[str, object]]) -> str:
    """Build a Markdown verification report from claim metadata and sources."""
    assessment = determine_verdict(claim, sources)
    claim_text = str(claim.get("claim_text") or "")
    today = _datetime.date.today().isoformat()
    urls = [str(source.get("url")) for source in sources if source.get("url")]
    independence = assess_urls(urls) if urls else {
        "independence_count": 0,
        "is_independent": False,
        "notes": ["No URLs supplied for independence assessment."],
    }

    source_lines = [format_source_line(index, source) for index, source in enumerate(sources, start=1)]
    if not source_lines:
        source_lines = ["No sources supplied."]

    contradictions = [source for source in sources if normalize_stance(source) == "refute"]
    if contradictions:
        contradiction_text = "\n".join(format_source_line(index, source) for index, source in enumerate(contradictions, start=1))
    else:
        contradiction_text = "None found."

    confirm_count = sum(1 for source in sources if normalize_stance(source) == "confirm")
    refute_count = sum(1 for source in sources if normalize_stance(source) == "refute")
    nuance_count = sum(1 for source in sources if normalize_stance(source) == "nuance")
    notes = [
        f"Evidence count: {confirm_count} confirming, {refute_count} refuting, {nuance_count} nuancing.",
        f"Verdict rationale: {assessment['reason']}",
        f"Source independence: {independence['independence_count']} root domain(s); "
        f"{'passes first-pass URL independence check' if independence['is_independent'] else 'does not prove full independence'}.",
    ]
    independence_notes = independence.get("notes", [])
    if isinstance(independence_notes, list):
        for note in independence_notes:
            notes.append(str(note))
    if claim.get("time_period"):
        notes.append(f"Recency check: claim references {claim['time_period']}; look for revised, final, updated, or superseding sources.")
    else:
        notes.append("Recency check: no explicit time period detected in the structured claim.")

    return "\n".join([
        "# Verification Report",
        "",
        "## Claim",
        f'"{claim_text}"',
        "",
        f"## Verdict: {verdict_label(str(assessment['verdict']))}",
        "",
        f"## Confidence: {assessment['confidence']}",
        "",
        "## Sources",
        *source_lines,
        "",
        "## Contradictions",
        contradiction_text,
        "",
        "## Notes",
        *(f"- {note}" for note in notes),
        "",
        "## Verified at",
        today,
        "",
    ])


def command_structure(args: argparse.Namespace) -> int:
    """Handle the structure subcommand."""
    print(json.dumps(structure_claim(args.claim), indent=2, ensure_ascii=False))
    return 0


def command_assess(args: argparse.Namespace) -> int:
    """Handle the assess subcommand."""
    urls = [url.strip() for url in args.urls.split(",") if url.strip()]
    print(json.dumps(assess_urls(urls), indent=2, ensure_ascii=False))
    return 0


def command_report(args: argparse.Namespace) -> int:
    """Handle the report subcommand."""
    claim = load_json_file(args.claim)
    sources = load_json_file(args.sources)
    if not isinstance(claim, dict):
        raise SystemExit("claim JSON must be an object")
    if not isinstance(sources, list) or not all(isinstance(source, dict) for source in sources):
        raise SystemExit("sources JSON must be an array of objects")
    report = build_report(claim, sources)
    if args.output:
        write_text(args.output, report)
    else:
        print(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Targeted claim verification helper: structure claims, assess source independence, and build cited reports."
    )
    parser.add_argument("--claim", help="Shortcut for 'structure --claim CLAIM'.")
    subparsers = parser.add_subparsers(dest="command")

    structure = subparsers.add_parser("structure", help="Parse a claim into structured JSON for verification.")
    structure.add_argument("--claim", required=True, help="Factual claim to structure.")
    structure.set_defaults(func=command_structure)

    report = subparsers.add_parser("report", help="Generate a Markdown verification report from claim and source JSON files.")
    report.add_argument("--claim", required=True, help="Path to claim JSON produced by the structure command.")
    report.add_argument("--sources", required=True, help="Path to sources JSON array collected by the agent.")
    report.add_argument("--output", help="Path to write Markdown report. Omit to print to stdout.")
    report.set_defaults(func=command_report)

    assess = subparsers.add_parser("assess", help="Assess URL root domains and simple independence warnings.")
    assess.add_argument("--urls", required=True, help="Comma-separated URLs to assess.")
    assess.set_defaults(func=command_assess)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.claim and not args.command:
        print(json.dumps(structure_claim(args.claim), indent=2, ensure_ascii=False))
        return 0
    if not args.command:
        parser.print_help(sys.stderr)
        return 2
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
