#!/usr/bin/env python3
"""Rule-based media technique scanner and report generator.

The scanner detects signals of rhetorical technique usage. It does not infer
political direction, factual truth, motive, or intent.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlparse


LOADED_LANGUAGE = [
    {"word": "slammed", "category": "aggressive_verb", "neutral_alternative": "responded"},
    {"word": "blasted", "category": "aggressive_verb", "neutral_alternative": "criticized"},
    {"word": "ripped", "category": "aggressive_verb", "neutral_alternative": "criticized"},
    {"word": "crushed", "category": "aggressive_verb", "neutral_alternative": "defeated"},
    {"word": "destroyed", "category": "aggressive_verb", "neutral_alternative": "strongly criticized"},
    {"word": "attacked", "category": "aggressive_verb", "neutral_alternative": "criticized"},
    {"word": "fumed", "category": "aggressive_verb", "neutral_alternative": "said"},
    {"word": "erupted", "category": "aggressive_verb", "neutral_alternative": "responded"},
    {"word": "lashed", "category": "aggressive_verb", "neutral_alternative": "criticized"},
    {"word": "savaged", "category": "aggressive_verb", "neutral_alternative": "criticized"},
    {"word": "devastating", "category": "emotional_adjective", "neutral_alternative": "significant"},
    {"word": "shocking", "category": "emotional_adjective", "neutral_alternative": "unexpected"},
    {"word": "alarming", "category": "emotional_adjective", "neutral_alternative": "concerning"},
    {"word": "horrific", "category": "emotional_adjective", "neutral_alternative": "severe"},
    {"word": "disastrous", "category": "emotional_adjective", "neutral_alternative": "problematic"},
    {"word": "outrageous", "category": "emotional_adjective", "neutral_alternative": "controversial"},
    {"word": "stunning", "category": "emotional_adjective", "neutral_alternative": "notable"},
    {"word": "explosive", "category": "emotional_adjective", "neutral_alternative": "important"},
    {"word": "damning", "category": "emotional_adjective", "neutral_alternative": "critical"},
    {"word": "bombshell", "category": "emotional_adjective", "neutral_alternative": "major"},
    # NOTE: extremely common qualifiers ("just", "only", "simply") and standard
    # journalistic hedges ("allegedly") are deliberately NOT listed — flagging
    # every ordinary use of them buries real signal in noise.
    {"word": "merely", "category": "dismissive_term", "neutral_alternative": "only"},
    {"word": "so-called", "category": "dismissive_term", "neutral_alternative": "named"},
    {"word": "supposedly", "category": "dismissive_term", "neutral_alternative": "reportedly"},
    {"word": "claimed", "category": "dismissive_term", "neutral_alternative": "said"},
    {"word": "insisted", "category": "dismissive_term", "neutral_alternative": "said"},
    {"word": "admitted", "category": "loaded_verb", "neutral_alternative": "said"},
    {"word": "radical", "category": "framing_word", "neutral_alternative": "substantial"},
    {"word": "extremist", "category": "framing_word", "neutral_alternative": "outside the mainstream"},
    {"word": "mainstream", "category": "framing_word", "neutral_alternative": "widely used"},
    {"word": "establishment", "category": "framing_word", "neutral_alternative": "institutional"},
    {"word": "elite", "category": "framing_word", "neutral_alternative": "senior"},
    {"word": "special interests", "category": "framing_word", "neutral_alternative": "advocacy groups"},
    {"word": "hidden agenda", "category": "framing_word", "neutral_alternative": "unstated plan"},
    {"word": "scheme", "category": "framing_word", "neutral_alternative": "proposal"},
    {"word": "boondoggle", "category": "framing_word", "neutral_alternative": "project"},
    {"word": "giveaway", "category": "framing_word", "neutral_alternative": "subsidy"},
    {"word": "crisis", "category": "emotional_adjective", "neutral_alternative": "problem"},
    {"word": "catastrophe", "category": "emotional_adjective", "neutral_alternative": "major problem"},
    {"word": "catastrophic", "category": "emotional_adjective", "neutral_alternative": "severe"},
    {"word": "nightmare", "category": "emotional_adjective", "neutral_alternative": "difficult situation"},
    {"word": "reckless", "category": "emotional_adjective", "neutral_alternative": "high-risk"},
    {"word": "failed", "category": "loaded_verb", "neutral_alternative": "did not"},
    {"word": "secretive", "category": "framing_word", "neutral_alternative": "private"},
    {"word": "shadowy", "category": "framing_word", "neutral_alternative": "less visible"},
]

EMOTIONAL_PATTERNS = {
    "fear": ["threat", "danger", "dangerous", "crisis", "catastrophic", "catastrophe", "panic", "risk", "fear", "collapse"],
    "outrage": ["outrage", "outrageous", "scandal", "betrayal", "furious", "anger", "rage"],
    "pity": ["children", "vulnerable", "suffering", "victims", "families", "elderly", "helpless"],
    "appeal_to_authority": ["expert", "experts say", "study shows", "research proves", "scientists agree", "analysts say"],
    "urgency": ["now or never", "before it is too late", "immediate action", "act now", "urgent", "countdown"],
}

SOURCE_KEYWORDS = {
    "official": ["minister", "department", "agency", "government", "mayor", "council", "police", "court", "regulator", "office", "authority", "commission"],
    "expert": ["professor", "researcher", "analyst", "scientist", "economist", "doctor", "study", "university", "institute", "data", "scholar"],
    "citizen": ["resident", "local", "witness", "parent", "worker", "student", "homeowner", "commuter", "customer", "farmer"],
    "organization": ["group", "association", "union", "company", "organization", "coalition", "nonprofit", "foundation", "campaign", "committee"],
}

SOURCE_TYPES = ["official", "expert", "citizen", "organization", "unknown"]


# Public API -----------------------------------------------------------------

def read_text_file(path: str) -> str:
    """Read a UTF-8 text file and return its contents."""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write_text_file(path: str, text: str) -> None:
    """Write text to a UTF-8 file, creating parent directories when needed."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def get_wordlist() -> list[dict[str, str]]:
    """Return the built-in loaded-language dictionary."""
    return list(LOADED_LANGUAGE)


def scan_article(text: str, source: str = "") -> dict[str, object]:
    """Scan article text for rule-based media technique signals."""
    paragraphs = split_paragraphs(text)
    loaded = detect_loaded_language(text, paragraphs)
    sources = extract_source_mentions(text, paragraphs)
    emotional = detect_emotional_appeals(text, paragraphs)
    structure = analyze_structure(text, paragraphs)
    technique_count = count_technique_signals(loaded, sources, emotional, structure)
    return {
        "source": source,
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "word_count": count_words(text),
        "loaded_language": loaded,
        "source_mentions": sources,
        "emotional_appeals": emotional,
        "structure": structure,
        "bias_spectrum_score": bias_spectrum_score(technique_count),
        "technique_count": technique_count,
    }


def split_paragraphs(text: str) -> list[str]:
    """Split text into non-empty paragraphs separated by blank lines."""
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def count_words(text: str) -> int:
    """Count words using a simple word-boundary tokenizer."""
    return len(re.findall(r"\b[\w'-]+\b", text))


def detect_loaded_language(text: str, paragraphs: list[str]) -> dict[str, object]:
    """Detect loaded words from the built-in dictionary."""
    instances = []
    for entry in LOADED_LANGUAGE:
        pattern = r"(?<![\w-])" + re.escape(entry["word"]) + r"(?![\w-])"
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            paragraph_number, paragraph_text = paragraph_for_offset(text, paragraphs, match.start())
            instances.append({
                "word": match.group(0),
                "category": entry["category"],
                "neutral_alternative": entry["neutral_alternative"],
                "paragraph": paragraph_number,
                "context": summarize_context(paragraph_text),
            })
    instances.sort(key=lambda item: (int(item["paragraph"]), str(item["word"]).lower()))
    return {"count": len(instances), "instances": instances}


def extract_source_mentions(text: str, paragraphs: list[str]) -> dict[str, object]:
    """Extract and categorize quoted or attributed sources."""
    candidates = []
    patterns = [
        r"\baccording to\s+([^\.\n,;:]{2,120})",
        r"\b(?:said|stated|reported|told|explained|noted|added|argued|warned)\s+([^\.\n,;:]{2,120})",
        r"[\"“][^\"”]{3,240}[\"”]\s*,?\s*(?:said|stated|reported|told|explained|noted|added|argued|warned)\s+([^\.\n,;:]{2,120})",
        r"\b([A-Z][A-Za-z0-9 .'-]*(?:Department|Agency|Ministry|Government|Minister|Professor|Researcher|Analyst|Study|Association|Union|Group|Coalition|Resident|Witness|Organization|Company|Institute|University)[^\.\n,;:]{0,80})\s+(?:said|stated|reported|told|explained|noted|added|argued|warned)\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            name = clean_source_name(match.group(1))
            if not name:
                continue
            paragraph_number, paragraph_text = paragraph_for_offset(text, paragraphs, match.start())
            key = (name.lower(), paragraph_number)
            if key in {(item["name"].lower(), item["paragraph"]) for item in candidates}:
                continue
            source_type = categorize_source(name, paragraph_text)
            candidates.append({
                "name": name,
                "type": source_type,
                "paragraph": paragraph_number,
                "context": summarize_context(paragraph_text),
            })
    by_type = {source_type: 0 for source_type in SOURCE_TYPES}
    for item in candidates:
        by_type[str(item["type"])] += 1
    return {"total": len(candidates), "by_type": by_type, "instances": candidates}


def clean_source_name(name: str) -> str:
    """Normalize a source-name candidate captured by attribution regexes."""
    cleaned = re.sub(r"\s+", " ", name.strip(" \t\n\r'\"“”"))
    cleaned = re.sub(r"^(the|a|an)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(who|that|which)\b.*$", "", cleaned, flags=re.IGNORECASE)
    trailing = ["in an interview", "in a statement", "on Monday", "on Tuesday", "on Wednesday", "on Thursday", "on Friday"]
    for phrase in trailing:
        cleaned = re.sub(r"\s+" + re.escape(phrase) + r"$", "", cleaned, flags=re.IGNORECASE)
    if len(cleaned.split()) > 12:
        cleaned = " ".join(cleaned.split()[:12])
    cleaned = cleaned.strip(" ,;:-")
    if re.match(r"^(that|which|who)\b", cleaned, flags=re.IGNORECASE):
        return ""
    if cleaned and cleaned[0].islower() and not any(keyword in cleaned.lower() for keywords in SOURCE_KEYWORDS.values() for keyword in keywords):
        return ""
    return cleaned


def categorize_source(name: str, context: str = "") -> str:
    """Categorize a source mention by institutional type using keywords."""
    value = f"{name} {context}".lower()
    for source_type in ["official", "expert", "organization", "citizen"]:
        if any(keyword in value for keyword in SOURCE_KEYWORDS[source_type]):
            return source_type
    return "unknown"


def detect_emotional_appeals(text: str, paragraphs: list[str]) -> dict[str, object]:
    """Detect surface markers of emotional appeal patterns."""
    instances = []
    patterns_found = set()
    for pattern_name, terms in EMOTIONAL_PATTERNS.items():
        for term in terms:
            regex = r"(?<![\w-])" + re.escape(term) + r"(?![\w-])"
            for match in re.finditer(regex, text, flags=re.IGNORECASE):
                paragraph_number, paragraph_text = paragraph_for_offset(text, paragraphs, match.start())
                patterns_found.add(pattern_name)
                instances.append({
                    "pattern": pattern_name,
                    "term": match.group(0),
                    "paragraph": paragraph_number,
                    "context": summarize_context(paragraph_text),
                })
    instances.sort(key=lambda item: (int(item["paragraph"]), str(item["pattern"]), str(item["term"]).lower()))
    return {"count": len(instances), "patterns": sorted(patterns_found), "instances": instances}


def analyze_structure(text: str, paragraphs: list[str]) -> dict[str, object]:
    """Measure simple article structure signals."""
    sentence_matches = re.findall(r"[^.!?]+[.!?]", text)
    if not sentence_matches and text.strip():
        sentence_matches = [text.strip()]
    sentence_word_counts = [count_words(sentence) for sentence in sentence_matches if count_words(sentence) > 0]
    avg_sentence_length = 0.0
    if sentence_word_counts:
        avg_sentence_length = round(sum(sentence_word_counts) / len(sentence_word_counts), 1)
    return {
        "paragraphs": len(paragraphs),
        "sentences": len(sentence_word_counts),
        "avg_sentence_length": avg_sentence_length,
        "questions_asked": text.count("?"),
        "exclamation_marks": text.count("!"),
    }


def paragraph_for_offset(text: str, paragraphs: list[str], offset: int) -> tuple[int, str]:
    """Return the 1-based paragraph number and text containing a character offset."""
    search_start = 0
    for index, paragraph in enumerate(paragraphs, start=1):
        found = text.find(paragraph, search_start)
        if found == -1:
            continue
        if found <= offset <= found + len(paragraph):
            return index, paragraph
        search_start = found + len(paragraph)
    if paragraphs:
        return len(paragraphs), paragraphs[-1]
    return 0, ""


def summarize_context(paragraph: str, max_length: int = 220) -> str:
    """Return a compact one-line paragraph context."""
    compact = re.sub(r"\s+", " ", paragraph).strip()
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 3].rstrip() + "..."


def as_int(value: object) -> int:
    """Convert a JSON-like value to int, returning zero on failure."""
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def count_technique_signals(loaded: dict[str, object], sources: dict[str, object], emotional: dict[str, object], structure: dict[str, object]) -> int:
    """Count distinct technique signals for the intensity spectrum.

    Signals are things that are unusual in neutral copy. Normal journalism —
    attributed sources, an occasional question — must NOT score:
    - loaded language: any hit counts (neutral copy has none)
    - sourcing: counts only when several sources are all one type
      (single-perspective sourcing), never for attribution itself
    - emotional patterns: capped at 2 so a wordlist pile-up alone can't
      reach "Partisan" without corroborating signal types
    - questions: 2+ (a single question is ordinary); exclamations: any
      (they are genuinely rare in straight news copy)
    """
    count = 0
    if as_int(loaded.get("count", 0)) > 0:
        count += 1
    total_sources = as_int(sources.get("total", 0))
    by_type = sources.get("by_type", {})
    if total_sources >= 3 and isinstance(by_type, dict) and any(
        as_int(n) == total_sources for n in by_type.values()
    ):
        count += 1
    patterns = emotional.get("patterns", [])
    if isinstance(patterns, list):
        count += min(len(patterns), 2)
    if as_int(structure.get("questions_asked", 0)) >= 2:
        count += 1
    if as_int(structure.get("exclamation_marks", 0)) > 0:
        count += 1
    return count


def bias_spectrum_score(technique_count: int) -> str:
    """Map technique signal count to an intensity label, not political direction."""
    if technique_count <= 0:
        return "Neutral"
    if technique_count <= 2:
        return "Slight lean"
    if technique_count <= 4:
        return "Clear lean"
    return "Partisan"


def build_report(scan: dict[str, object]) -> str:
    """Generate a Markdown media analysis report from scan results."""
    source = str(scan.get("source") or "[title or filename]")
    loaded_obj = scan.get("loaded_language", {})
    sources_obj = scan.get("source_mentions", {})
    emotional_obj = scan.get("emotional_appeals", {})
    loaded: dict[str, object] = loaded_obj if isinstance(loaded_obj, dict) else {}
    sources: dict[str, object] = sources_obj if isinstance(sources_obj, dict) else {}
    emotional: dict[str, object] = emotional_obj if isinstance(emotional_obj, dict) else {}
    score = str(scan.get("bias_spectrum_score", "Neutral"))
    lines = [
        "# Media Analysis Report",
        "",
        f"## Source: {source}",
        "",
        "## Overview",
        f"- Word count: {scan.get('word_count', 0)}",
        f"- Techniques detected: {scan.get('technique_count', 0)}",
        f"- Bias spectrum: {score}",
        "",
        "## Techniques Detected",
        "",
        f"### 1. Loaded Language ({loaded.get('count', 0)} instances)",
    ]
    loaded_instances = loaded.get("instances", [])
    if isinstance(loaded_instances, list) and loaded_instances:
        for item in loaded_instances:
            if isinstance(item, dict):
                lines.append(f"- \"{item.get('word')}\" (para {item.get('paragraph')}) — neutral alternative: \"{item.get('neutral_alternative')}\"")
    else:
        lines.append("- Not detected")
    lines.extend([
        "",
        f"### 2. Source Selection ({sources.get('total', 0)} sources)",
    ])
    by_type_obj = sources.get("by_type", {})
    by_type: dict[str, object] = by_type_obj if isinstance(by_type_obj, dict) else {}
    type_summary = ", ".join(f"{source_type.title()}: {by_type.get(source_type, 0)}" for source_type in SOURCE_TYPES)
    lines.append(f"- {type_summary}")
    imbalance_note = source_imbalance_note(by_type)
    lines.append(f"- {imbalance_note}")
    source_instances = sources.get("instances", [])
    if isinstance(source_instances, list):
        for item in source_instances:
            if isinstance(item, dict):
                lines.append(f"- {item.get('name')} — {item.get('type')} (para {item.get('paragraph')})")
    lines.extend([
        "",
        f"### 3. Emotional Appeals ({emotional.get('count', 0)} instances)",
    ])
    emotional_instances = emotional.get("instances", [])
    if isinstance(emotional_instances, list):
        pattern_counts = Counter(str(item.get("pattern")) for item in emotional_instances if isinstance(item, dict) and item.get("pattern"))
    else:
        pattern_counts = Counter()
    if pattern_counts:
        for pattern_name in sorted(pattern_counts):
            lines.append(f"- {format_pattern_name(pattern_name)}: {pattern_counts[pattern_name]}")
    else:
        lines.append("- Not detected")
    lines.extend([
        "",
        "## Bias Spectrum",
        "Neutral ──── Slight lean ──── Clear lean ──── Partisan ──── Propaganda",
        spectrum_pointer(score),
        "",
        "## What's Missing",
        "[To be filled by the agent after contextual research — what relevant context was omitted]",
        "",
        "## Notes",
        "- Analysis detects techniques, not political positions",
        "- Intensity rating reflects density of rhetorical tools, not direction of bias",
        "- Rule-based scanning can miss context-dependent framing, omission, cherry-picking, and false balance",
        "",
    ])
    return "\n".join(lines)


def source_imbalance_note(by_type: object) -> str:
    """Return a neutral note about source-type concentration."""
    if not isinstance(by_type, dict) or not by_type:
        return "No source-type distribution available"
    total = sum(int(by_type.get(source_type, 0)) for source_type in SOURCE_TYPES)
    if total == 0:
        return "No attributed sources detected"
    nonzero = [source_type for source_type in SOURCE_TYPES if int(by_type.get(source_type, 0)) > 0]
    if len(nonzero) == 1:
        return f"All detected sources fall under one type: {nonzero[0]}"
    return "Multiple source types detected; assess perspective diversity during contextual review"


def format_pattern_name(pattern_name: object) -> str:
    """Format an emotional appeal pattern for report display."""
    text = str(pattern_name).replace("_", " ").title()
    return text.replace("To", "to")


def spectrum_pointer(score: str) -> str:
    """Return an arrow marker aligned approximately under a spectrum label."""
    spectrum = "Neutral ──── Slight lean ──── Clear lean ──── Partisan ──── Propaganda"
    index = spectrum.find(score)
    if index < 0:
        index = 0
    return " " * index + "↑ here"


def format_wordlist_table() -> str:
    """Return the loaded-language word list as a plain-text table."""
    rows = ["word\tcategory\tneutral_alternative"]
    for entry in LOADED_LANGUAGE:
        rows.append(f"{entry['word']}\t{entry['category']}\t{entry['neutral_alternative']}")
    return "\n".join(rows)


# CLI ------------------------------------------------------------------------

def command_scan(args: argparse.Namespace) -> int:
    """Handle the scan subcommand."""
    text = read_text_file(args.input)
    source = args.source or infer_source_label(args.input)
    result = scan_article(text, source=source)
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        write_text_file(args.output, payload + "\n")
    else:
        print(payload)
    return 0


def command_report(args: argparse.Namespace) -> int:
    """Handle the report subcommand."""
    scan = json.loads(read_text_file(args.scan))
    report = build_report(scan)
    if args.output:
        write_text_file(args.output, report)
    else:
        print(report)
    return 0


def command_wordlist(args: argparse.Namespace) -> int:
    """Handle the wordlist subcommand."""
    if args.format == "json":
        print(json.dumps(LOADED_LANGUAGE, indent=2, ensure_ascii=False))
    else:
        print(format_wordlist_table())
    return 0


def infer_source_label(path: str) -> str:
    """Infer a source label from an input path or URL."""
    parsed = urlparse(path)
    if parsed.scheme and parsed.netloc:
        return parsed.netloc + parsed.path
    return os.path.basename(path)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Detect rhetorical technique signals in media text without labeling political direction.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Analyze article text for technique signals")
    scan.add_argument("--input", required=True, help="Markdown or plain text article file")
    scan.add_argument("--output", help="Optional path for JSON scan output")
    scan.add_argument("--source", help="Optional source title or filename to store in results")
    scan.set_defaults(func=command_scan)

    report = subparsers.add_parser("report", help="Generate a Markdown analysis report from scan JSON")
    report.add_argument("--scan", required=True, help="JSON file produced by the scan command")
    report.add_argument("--output", help="Optional path for Markdown report output")
    report.set_defaults(func=command_report)

    wordlist = subparsers.add_parser("wordlist", help="Show the built-in loaded-language word list")
    wordlist.add_argument("--format", choices=["json", "table"], default="table", help="Output format")
    wordlist.set_defaults(func=command_wordlist)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
