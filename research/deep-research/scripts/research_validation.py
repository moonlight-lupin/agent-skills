#!/usr/bin/env python3
"""Deterministic validation gates for deep-research reports.

Four gates, all stdlib-only, no network calls (except nothing — fully offline):

  evidence store   init-run / register-source / add-claim / add-evidence
                   Append-only JSONL. Survives context compaction. Source IDs are
                   sha256 of a canonical URL, stable across renumbering.
  claim support    verify-claims — does the stored evidence snippet actually
                   support the claim? Token overlap + number + year + entity
                   matching. --strict exits 1 on unsupported factual claims.
  citation check   verify-citations — every inline [N] resolves to a Sources
                   table row, every row is cited, URLs well-formed, suspicious
                   titles flagged.
  structure check  validate-report — required sections present (including the
                   mandatory Contradictions and Gaps sections), no placeholder
                   text, research stats block present.

The agent writes markdown reports and evidence.json; these scripts check the
output deterministically. LLM judgment stays in the skill; the gate stays dumb.

Usage:
  python3 research_validation.py init-run --dir DIR --query "..." [--mode standard] [--provider auto]
  python3 research_validation.py register-source --dir DIR --json '{"url": "...", "title": "...", "quality": "primary"}'
  python3 research_validation.py add-claim --dir DIR --json '{"claim_id": "c1", "claim": "...", "kind": "factual", "snippet": "...", "source_id": "..."}'
  python3 research_validation.py add-evidence --dir DIR --json '{"claim_id": "c1", "snippet": "...", "source_id": "..."}'
  python3 research_validation.py verify-claims --dir DIR [--strict]
  python3 research_validation.py verify-citations --report REPORT.md
  python3 research_validation.py validate-report --report REPORT.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

STOPWORDS = frozenset(
    """a an and are as at be by for from has have in into is it its of on or
    that the to was were will with this these those their there than then not
    but which who whom whose what when where how why can could may might must
    also more most other some such only own same so too very just about over
    under between across per via new new""".split()
)

TOKEN_RE = re.compile(r"[a-z0-9]+")
NUMBER_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)([a-zA-Z]+)?")
YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
ENTITY_RE = re.compile(r"\b[A-Z][a-zA-Z0-9]+(?:\s+[A-Z][a-zA-Z0-9]+)*\b|[\u4e00-\u9fff]{2,}")

SUPPORTED_THRESHOLD = 0.60
PARTIAL_THRESHOLD = 0.35
VALID_KINDS = frozenset({"factual", "interpretive", "projective", "synthesis", "speculation"})
VALID_QUALITIES = frozenset({"primary", "secondary", "tertiary"})
VALID_POLARITIES = frozenset({"support", "refute", "neutral"})
# The four evidence-basis labels from SKILL.md, stored lowercase.
VALID_BASES = frozenset({"verified", "sourced", "reasoned", "estimated"})
# Counter-evidence is mandatory once a report reaches the gated size (SKILL.md §5.5).
REFUTE_MIN_SOURCES = 5

REQUIRED_SECTIONS = [
    ("Executive Summary", "Executive summary"),
    ("Contradictions", "Contradictions section (mandatory)"),
    ("Gaps", "Gaps section (mandatory)"),
    ("Conclusion", "Conclusion"),
    ("Sources", "Sources table"),
]

PLACEHOLDER_PATTERNS = [
    (r"\bTBD\b", "TBD placeholder"),
    (r"\bTODO\b", "TODO placeholder"),
    (r"\[placeholder\]", "[placeholder] text"),
    (r"\[Sections? [X\d].*[–-]", "truncation placeholder"),
    (r"\.\.\.\s*continue", "'... continue' placeholder"),
    (r"Additional citations", "'additional citations' placeholder"),
    (r"(?i)content continues", "'content continues' placeholder"),
    (r"(?i)due to length", "'due to length' placeholder"),
]

SUSPICIOUS_TITLE_PATTERNS = [
    (r"^(A |An |The )?(Study|Analysis|Review|Survey|Investigation) (of|on|into) (the |a |an )?\w",
     "generic academic title pattern"),
    (r"^(Recent|Current|Modern|Contemporary) (Advances|Developments|Trends) in ",
     "generic 'advances' title pattern"),
    (r"^[A-Z][a-z]+ [A-Z][a-z]+: A (Comprehensive|Complete|Systematic) (Review|Analysis|Guide)$",
     "templated title structure"),
]

STATS_RE = re.compile(r"Research stats:")



def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_url(raw: str) -> str:
    """Normalize a URL: lowercase host, strip tracking params/fragments/trailing slash.

    Only well-known pure-tracking params are dropped. Content-bearing params
    (branch refs like ?ref=main, path ids) are preserved so distinct resources
    never collapse to one identity.
    """
    raw = (raw or "").strip()
    parts = urlsplit(raw)
    scheme = parts.scheme.lower() or "https"
    if scheme == "http":
        scheme = "https"
    host = parts.netloc.lower()
    # Drop only unambiguous tracking params; keep the rest (incl. branch refs).
    tracking = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "utm_id", "ref_src", "ref_url", "fbclid", "gclid", "mc_cid", "mc_eid",
        "igshid", "_hsenc", "_hsmi", "oly_anon_id", "wickedid", "msclkid",
        "twclid", "yclid", "sb_referer_tag",
    }
    query = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if k.lower() not in tracking)
    path = parts.path.rstrip("/") if parts.path != "/" else ""
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def stable_source_id(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def _append_jsonl(path: Path, obj: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit(json.dumps({"ok": False, "error": f"malformed JSON in {path} line {i}: {e}"}))
        if not isinstance(rec, dict):
            raise SystemExit(json.dumps({"ok": False, "error": f"{path} line {i}: expected a JSON object"}))
        out.append(rec)
    return out


def _load_json_arg(raw: str, what: str) -> dict:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(json.dumps({"ok": False, "error": f"malformed --json for {what}: {e}"}))
    if not isinstance(obj, dict):
        raise SystemExit(json.dumps({"ok": False, "error": f"--json for {what} must be a JSON object"}))
    return obj


def _load_manifest(run_dir: Path) -> dict:
    path = run_dir / "run_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- evidence store

def cmd_init_run(args) -> int:
    d = Path(args.dir)
    d.mkdir(parents=True, exist_ok=True)
    manifest_path = d / "run_manifest.json"
    created = utc_now()
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(json.dumps({"ok": False,
                "error": f"malformed JSON in {manifest_path}: {e}"}))
        if not isinstance(old, dict):
            raise SystemExit(json.dumps({"ok": False,
                "error": f"{manifest_path}: expected a JSON object, got {type(old).__name__}"}))
        old["reinitialized_at"] = created
        if args.query:
            old["query"] = args.query
        if args.mode:
            old["mode"] = args.mode
        if args.provider:
            old["provider_preference"] = args.provider
        manifest_path.write_text(json.dumps(old, indent=2), encoding="utf-8")
    else:
        manifest_path.write_text(json.dumps({
            "query": args.query or "",
            "mode": args.mode or "moderate",
            "provider_preference": args.provider or "auto",
            "provider_used": None,
            "created_at": created,
        }, indent=2), encoding="utf-8")
    for name in ("sources.jsonl", "claims.jsonl"):
        if not (d / name).exists():
            (d / name).touch()
    print(json.dumps({"ok": True, "dir": str(d), "manifest": str(manifest_path)}))
    return 0


def cmd_register_source(args) -> int:
    d = Path(args.dir)
    obj = _load_json_arg(args.json, "register-source")
    url = obj.get("url", "")
    if not isinstance(url, str) or not url.strip():
        print(json.dumps({"ok": False, "error": "source url required"}))
        return 2
    url = url.strip()
    try:
        sid = stable_source_id(url)
        canonical = canonical_url(url)
    except ValueError:
        # urlsplit raises ValueError on malformed input like 'http://['.
        print(json.dumps({"ok": False, "error": f"malformed url: {url!r}"}))
        return 2
    quality = str(obj.get("quality") or "secondary").strip().lower()
    if quality not in VALID_QUALITIES:
        print(json.dumps({"ok": False,
                          "error": f"invalid quality {obj.get('quality')!r} — valid: {sorted(VALID_QUALITIES)}"}))
        return 2
    existing = _read_jsonl(d / "sources.jsonl")
    if any(s.get("source_id") == sid for s in existing):
        print(json.dumps({"ok": True, "source_id": sid, "deduplicated": True,
                          "canonical_url": canonical_url(url)}))
        return 0
    rec = {
        "source_id": sid,
        "url": url,
        "canonical_url": canonical,
        "title": obj.get("title", ""),
        "quality": quality,
        "registered_at": utc_now(),
    }
    _append_jsonl(d / "sources.jsonl", rec)
    print(json.dumps({"ok": True, "source_id": sid, "deduplicated": False}))
    return 0


def _claim_exists(claims: list, claim_id: str) -> bool:
    return any(c.get("claim_id") == claim_id for c in claims)


def cmd_add_claim(args) -> int:
    d = Path(args.dir)
    obj = _load_json_arg(args.json, "add-claim")
    claim_id = obj.get("claim_id", "")
    claim = obj.get("claim", "")
    kind = obj.get("kind", "factual")
    if not isinstance(claim_id, str) or not isinstance(claim, str) or not claim_id.strip() or not claim.strip():
        print(json.dumps({"ok": False, "error": "claim_id and claim required"}))
        return 2
    if not isinstance(kind, str) or kind not in VALID_KINDS:
        print(json.dumps({"ok": False,
                          "error": f"invalid kind {kind!r} — valid: {sorted(VALID_KINDS)}"}))
        return 2
    polarity = str(obj.get("polarity") or "neutral").strip().lower()
    if polarity not in VALID_POLARITIES:
        print(json.dumps({"ok": False,
                          "error": f"invalid polarity {obj.get('polarity')!r} — valid: {sorted(VALID_POLARITIES)}"}))
        return 2
    basis = obj.get("basis")
    if basis is not None:
        basis = str(basis).strip().strip("[]").lower()
        if basis not in VALID_BASES:
            print(json.dumps({"ok": False,
                              "error": f"invalid basis {obj.get('basis')!r} — valid: {sorted(VALID_BASES)}"}))
            return 2
    claim_id = claim_id.strip()
    if _claim_exists(_read_jsonl(d / "claims.jsonl"), claim_id):
        print(json.dumps({"ok": False, "error": f"duplicate claim_id {claim_id}"}))
        return 2
    rec = {
        "claim_id": claim_id,
        "claim": claim.strip() if isinstance(claim, str) else claim,
        "kind": kind,
        "polarity": polarity,
        "basis": basis,
        "topic_tag": obj.get("topic_tag", ""),
        "snippet": obj.get("snippet", ""),
        "source_id": obj.get("source_id", ""),
        "recorded_at": utc_now(),
    }
    _append_jsonl(d / "claims.jsonl", rec)
    print(json.dumps({"ok": True, "claim_id": claim_id}))
    return 0


def cmd_add_evidence(args) -> int:
    d = Path(args.dir)
    obj = _load_json_arg(args.json, "add-evidence")
    claim_id = obj.get("claim_id", "")
    snippet = obj.get("snippet", "")
    if not isinstance(claim_id, str) or not isinstance(snippet, str) or not claim_id.strip() or not snippet.strip():
        print(json.dumps({"ok": False, "error": "claim_id and snippet required"}))
        return 2
    if not _claim_exists(_read_jsonl(d / "claims.jsonl"), claim_id):
        print(json.dumps({"ok": False, "error": f"unknown claim_id {claim_id} — add-claim first"}))
        return 2
    _append_jsonl(d / "claims.jsonl", {
        "claim_id": claim_id,
        "evidence_snippet": snippet,
        "source_id": obj.get("source_id", ""),
        "recorded_at": utc_now(),
    })
    print(json.dumps({"ok": True, "claim_id": claim_id}))
    return 0


# ---------------------------------------------------------------- claim support

def _tokens(text: str) -> set:
    return {t for t in TOKEN_RE.findall(text.lower()) if t not in STOPWORDS and len(t) > 1}


def _numbers(text: str) -> set:
    """Plain numeric values (suffix-stripped, comma-normalized) for the
    coarse numbers axis; the suffix-aware view lives in _figures."""
    return {(m.group(1) or "").replace(",", "") for m in NUMBER_RE.finditer(text)}


MAGNITUDE_WORD_RE = re.compile(
    r"(?i)\b(thousand|million|billion|trillion|milliard)s?\b")
_MAG_WORD_SUFFIX = {"thousand": "k", "million": "m", "milliard": "b",
                    "billion": "b", "trillion": "t"}
# Common abbreviations of the same magnitudes: '2.4bn' == '2.4b' == '2.4 billion'.
# 'mm' is deliberately NOT aliased: it means both 'million' (finance) and
# 'millimetre' (physical), and aliasing it would erase '2mm' vs '2m' unit
# contradictions (Codex review round 2, MAJOR — 2026-09-25).
_SUFFIX_ALIASES = {"bn": "b", "mn": "m", "mln": "m", "tn": "t", "trn": "t"}


def _figures(text: str) -> set:
    """Non-year numbers with their magnitude/unit suffix preserved (1.1k ≠ 1.1m).

    - Spelled-out magnitude words count as suffixes: '40 million' → 40m, so
      '40 million' vs '40 billion' is a contradiction (40m ≠ 40b).
    - Comma-grouped integers are normalized: '1,200' == '1200'.
    - Unit-bound numbers keep their unit: '40ms' ≠ '90ms' — the full letter
      run is part of the figure, so format variants ('2.4b' vs '2.4bn')
      count as different figures. Write figures in one format per report.
    - A match counts as a year only if it carries NO suffix: '2025' is a
      year, '2025k' is a suffixed figure, not a year.
    """
    out = set()
    for m in NUMBER_RE.finditer(text):
        val = (m.group(1) or "").replace(",", "")
        run = (m.group(2) or "")
        suffix = run.lower()
        if not suffix:
            # Spelled-out magnitude word after the number? '40 million' → '40m'.
            # Two prose guards: a yearlike value never takes a magnitude word
            # ('in 2025 millions of users' is prose), and a plural magnitude
            # word followed by ' of ' is prose ('millions of users').
            tail = text[m.end():]
            wm = MAGNITUDE_WORD_RE.match(tail.lstrip())
            if wm and not re.fullmatch(r"(19|20)\d{2}", val):
                rest = tail.lstrip()[wm.end():]
                plural_of = tail.lstrip()[wm.end() - 1] == "s" and re.match(r"(?i)\s+of\b", rest)
                if not plural_of:
                    suffix = _MAG_WORD_SUFFIX[wm.group(1).lower()]
        if not suffix and YEAR_RE.fullmatch(val):
            # Boundary-consistent with _years: exclude as a year only when this
            # exact occurrence stands alone (word char on neither side).
            # Occurrence-level, not whole-text — a bare ' in 2000' must not
            # excuse the embedded '2000' inside 'v2000' elsewhere in the text.
            before = text[m.start() - 1] if m.start() > 0 else " "
            after = text[m.end()] if m.end() < len(text) else " "
            if not (re.match(r"\w", before) or re.match(r"\w", after)):
                continue
        suffix = suffix.lower()
        out.add(val + _SUFFIX_ALIASES.get(suffix, suffix))
    return out


def _years(text: str) -> set:
    """Years, with comma-grouped counts normalized so '2,000' == '2000'."""
    return set(YEAR_RE.findall(text.replace(",", "")))


def _entities(text: str) -> set:
    ents = set()
    for m in ENTITY_RE.finditer(text):
        # Skip pure years and common sentence-start artifacts of one char.
        ent = m.group(0).strip()
        if len(ent) >= 3 and not YEAR_RE.fullmatch(ent) and ent.lower() not in STOPWORDS:
            ents.add(ent.lower())
    return ents


def support_score(claim: str, snippets: list) -> float:
    """Deterministic v3 support score (0-1), no LLM calls.

    - Signal axes (figure/year/entity) score only when the CLAIM carries them;
      absent-in-snippet scores 0 (evidence against support), weights renormalize.
    - Contradiction cap: if the claim's non-year figures and the snippet's figures
      are both present but disjoint (1.1k vs 1.1m, 40 vs 90), the snippet
      contradicts the claim — capped below "supported" regardless of prose
      similarity. Same rule for years and entities.
    """
    if not snippets:
        return 0.0
    c_tok, c_num, c_year, c_ent = _tokens(claim), _numbers(claim), _years(claim), _entities(claim)
    c_fig = _figures(claim)
    best = 0.0
    for snip in snippets:
        s_tok, s_num, s_year, s_ent = (
            _tokens(snip), _numbers(snip), _years(snip), _entities(snip))
        s_fig = _figures(snip)
        axes = []
        # Token Jaccard: always in play.
        axes.append((0.40, len(c_tok & s_tok) / len(c_tok | s_tok) if (c_tok | s_tok) else 0.0))
        # Signal axes: scored only when the CLAIM carries the signal; if the claim
        # carries it and the snippet does not, that is evidence AGAINST support.
        if c_num:
            axes.append((0.25, len(c_num & s_num) / len(c_num)))
        if c_year:
            axes.append((0.15, len(c_year & s_year) / len(c_year)))
        if c_ent:
            axes.append((0.20, len(c_ent & s_ent) / len(c_ent)))
        if not axes:
            continue
        wsum = sum(w for w, _ in axes)
        score = sum(w * v for w, v in axes) / wsum
        # Contradiction cap: any claim figure that the snippet does not fully
        # corroborate — contradicted ({40} vs {90}), partially shared
        # ({1.1k,20} vs {20,1.1m}), or entirely absent from the snippet —
        # caps the score below "supported". Suffix-aware: 1.1k ≠ 1.1m;
        # bare '2025' is a year, '2025k' is a figure. Same rule for years
        # (superset cap: a claim's years must all be corroborated —
        # {2024,2025} vs {2024,2026} caps) and entities.
        if ((c_fig and (not s_fig or not c_fig.issubset(s_fig)))
                or (c_year and (not s_year or not (c_year <= s_year)))
                or (c_ent and s_ent and not (c_ent & s_ent))):
            score = min(score, PARTIAL_THRESHOLD - 0.01)
        best = max(best, score)
    return round(best, 3)


def cmd_verify_claims(args) -> int:
    d = Path(args.dir)
    claims = _read_jsonl(d / "claims.jsonl")
    # Record the provider actually used, so the manifest reflects reality.
    if getattr(args, "provider_used", None):
        manifest_path = d / "run_manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if not isinstance(manifest, dict):
                    raise ValueError("not a JSON object")
            except (json.JSONDecodeError, ValueError) as e:
                print(json.dumps({"ok": False,
                    "error": f"malformed manifest {manifest_path} ({e}) — provider not recorded"}))
                manifest = None
            if manifest is not None:
                manifest["provider_used"] = args.provider_used
                manifest["provider_used_at"] = utc_now()
                manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    refute_none = getattr(args, "refute_none", None)
    if refute_none is not None and not str(refute_none).strip():
        # A blank waiver is not a waiver — the reason must say what was
        # searched (Codex review round 2, MINOR — 2026-09-25).
        refute_none = None
    if refute_none:
        _record_manifest(d, refute_none_reason=refute_none)
    main = {}
    extra = {}
    sources = {}
    evidence_recs = {}  # claim_id -> list of full evidence records (with source_id)
    for s in _read_jsonl(d / "sources.jsonl"):
        sid = s.get("source_id")
        if sid:
            sources[sid] = s
    source_ids = set(sources)
    for rec in claims:
        cid = rec.get("claim_id")
        if "claim" in rec:
            main[cid] = rec
            extra.setdefault(cid, [])
            evidence_recs.setdefault(cid, [])
        else:
            extra.setdefault(cid, []).append(rec.get("evidence_snippet", ""))
            evidence_recs.setdefault(cid, []).append(rec)
    results = []
    failures = 0
    warnings = 0
    basis_warnings = 0
    for cid, rec in main.items():
        snippets = ([rec.get("snippet", "")] if rec.get("snippet") else []) + extra.get(cid, [])
        snippets = [s for s in snippets if s]
        kind = rec.get("kind", "factual")
        score = support_score(rec["claim"], snippets)
        if not snippets:
            status = "unsupported"
        elif score >= SUPPORTED_THRESHOLD:
            status = "supported"
        elif score >= PARTIAL_THRESHOLD:
            status = "partial"
        else:
            status = "needs_review"
        # source_id resolution: the primary source_id and EVERY additional
        # evidence record's source_id must point at a registered source. An
        # evidence record with an EMPTY source_id is also a defect: evidence
        # without provenance cannot back a factual claim.
        claim_sids = []
        if rec.get("source_id", ""):
            claim_sids.append(rec["source_id"])
        ev_recs = [r for r in claims
                   if r.get("claim_id") == cid and "claim" not in r]
        ev_sids = [r.get("source_id", "") for r in ev_recs]
        claim_sids.extend(s for s in ev_sids if s)
        bad_sids = [sid for sid in claim_sids if sid not in source_ids]
        ev_missing = any(not r.get("source_id") for r in ev_recs)
        bad_source = bool(bad_sids) or ev_missing
        missing_source = not rec.get("source_id", "")
        hard = kind == "factual" and (status in ("unsupported", "needs_review")
                                      or bad_source or missing_source)
        is_partial_factual = kind == "factual" and status == "partial" and args.strict
        if hard and args.strict:
            failures += 1
        entry = {"claim_id": cid, "kind": kind, "status": status,
                 "score": score, "strict_fail": bool(hard and args.strict)}
        if is_partial_factual:
            # Partial factual claims do not pass silently: they hard-fail in
            # --strict because a partial match is not evidence of support.
            failures += 1
            entry["strict_fail"] = True
            entry["strict_warning"] = "partial factual claim"
        if bad_source:
            entry["warning"] = f"unregistered source_id(s): {bad_sids}" + (" (empty source_id in evidence)" if ev_missing else "")
            warnings += 1
        if missing_source:
            entry["warning"] = "claim has no source_id"
            warnings += 1
        # [VERIFIED] means >=2 independent sources that CORROBORATE the claim:
        # each (source_id, snippet) pair is scored separately, and only a
        # source whose OWN snippet supports the claim counts as corroboration
        # (Codex review round 2, MAJOR — 2026-09-25).
        if rec.get("basis") == "verified":
            pairs = []
            if rec.get("snippet") and rec.get("source_id"):
                pairs.append((rec["source_id"], rec["snippet"]))
            for ev in ev_recs:
                if ev.get("evidence_snippet") and ev.get("source_id"):
                    pairs.append((ev["source_id"], ev["evidence_snippet"]))
            supporting_hosts = {
                _host(sources[sid])
                for sid, sn in pairs
                if sid in sources and support_score(rec["claim"], [sn]) >= SUPPORTED_THRESHOLD
            }
            if len(supporting_hosts) < 2:
                entry["basis_warning"] = (
                    f"tagged [VERIFIED] but corroborated by only {len(supporting_hosts)} supporting source host(s); "
                    "[VERIFIED] needs >=2 corroborating evidence from another site or tag it [SOURCED]")
                basis_warnings += 1
                if args.strict and not entry["strict_fail"]:
                    failures += 1
                    entry["strict_fail"] = True
        results.append(entry)
    if not main:
        # No claims recorded — in strict mode this is a failure (no gate ran);
        # otherwise warn so the agent knows the gate was skipped.
        out = {"ok": not args.strict, "claims": 0,
               "warning": "no claims recorded — run add-claim during research",
               "strict_ok": not args.strict}
        print(json.dumps(out))
        return 0 if not args.strict else 1
    # Counter-evidence: required once the report reaches the gated size.
    # A refute claim counts ONLY if it is evidence-backed — a qualifying
    # snippet (score >= PARTIAL_THRESHOLD) that belongs to a REGISTERED
    # source. Source presence and snippet support must be PAIRED: a
    # supporting snippet from an unregistered source counts for nothing,
    # and neither does a registered source with an unrelated snippet
    # (Codex round 2 MAJOR, confirm round PARTIAL — 2026-09-25).
    refute_records = []
    for cid, rec in main.items():
        if rec.get("polarity") != "refute":
            continue
        pairs = []
        if rec.get("snippet") and rec.get("source_id"):
            pairs.append((rec["source_id"], rec["snippet"]))
        for e in evidence_recs.get(cid, []):
            if e.get("evidence_snippet") and e.get("source_id"):
                pairs.append((e["source_id"], e["evidence_snippet"]))
        if any(sid in sources and support_score(rec["claim"], [sn]) >= PARTIAL_THRESHOLD
               for sid, sn in pairs):
            refute_records.append(cid)
    refute_claims = len(refute_records)
    refute_warning = ""
    if refute_claims == 0 and len(sources) >= REFUTE_MIN_SOURCES and not refute_none:
        refute_warning = (
            f"no counter-evidence (polarity 'refute') claims across {len(sources)} sources — "
            "search for criticism or opposing data, or pass --refute-none '<what you searched>'")
        if args.strict:
            failures += 1
    quality = _quality_mix(sources.values())
    quality_warning = ""
    if quality["rating"] == "weak":
        quality_warning = (
            f"weak source mix ({quality['primary']} primary, {quality['tertiary']} tertiary of "
            f"{quality['total']}) — fetch primary sources or qualify claims and flag it under Gaps")
    print(json.dumps({"ok": failures == 0, "claims": len(results),
                      "unsupported_strict": failures, "source_warnings": warnings,
                      "basis_warnings": basis_warnings,
                      "refute_claims": refute_claims, "refute_warning": refute_warning,
                      "source_quality": quality, "quality_warning": quality_warning,
                      "results": results}))
    return 1 if failures else 0


def _host(source: dict) -> str:
    host = urlsplit(source.get("canonical_url") or source.get("url") or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _quality_mix(sources) -> dict:
    """Counts per tier and the SKILL.md §3e rating: healthy (>=30% primary and
    <=30% tertiary), weak (no primary, or >50% tertiary), else acceptable.
    Legacy records with a non-tier quality (stored before validation existed)
    count as their historical default, 'secondary' — dropping them from the
    denominator would let one primary rate a whole store healthy
    (Codex review round 2, MINOR — 2026-09-25)."""
    counts = {"primary": 0, "secondary": 0, "tertiary": 0}
    for s in sources:
        q = str(s.get("quality", "secondary")).lower()
        if q not in counts:
            q = "secondary"
        counts[q] += 1
    total = sum(counts.values())
    if total == 0:
        rating = "none"
    elif counts["primary"] / total >= 0.30 and counts["tertiary"] / total <= 0.30:
        rating = "healthy"
    elif counts["primary"] == 0 or counts["tertiary"] / total > 0.50:
        rating = "weak"
    else:
        rating = "acceptable"
    return {**counts, "total": total, "rating": rating}


def _record_manifest(run_dir: Path, **fields) -> None:
    path = run_dir / "run_manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except json.JSONDecodeError:
        return
    if isinstance(manifest, dict):
        manifest.update(fields)
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ---------------------------------------------------------------- citation check

CITATION_RE = re.compile(r"\[(\d+)\]")
BIB_ENTRY_RE = re.compile(r"^\[(\d+)\]\s+(.+)$")


def _strip_code_blocks(text: str) -> str:
    """Remove fenced and inline code so numeric brackets in code are not citations."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"~~~.*?~~~", " ", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", " ", text)
    return text


def _split_report(text: str):
    """Return (body, sources_text, header_level).

    Code blocks are stripped FIRST so a fenced '## Sources' example never
    prematurely splits the report. Only a heading whose text starts with
    'Sources' ('## Sources', '## Sources & references') splits; headings that
    merely contain the word ('### Sources of revenue') do not.
    """
    text = _strip_code_blocks(text)
    m = re.search(r"^##\s*Sources\b.*$", text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return text, "", 2
    return text[: m.start()], text[m.start():], 2


def cmd_verify_citations(args) -> int:
    path = Path(args.report)
    text = path.read_text(encoding="utf-8")
    body, sources, header_level = _split_report(text)

    inline_all = {int(n) for n in CITATION_RE.findall(body)}

    bib = {}
    dup_numbers = []
    # Both formats are parsed and merged; a number defined twice is an error.
    for line in sources.splitlines():
        line_s = line.strip()
        m = BIB_ENTRY_RE.match(line_s)
        if not m:
            m = re.match(r"^\|\s*(\d+)\s*\|(.*)$", line_s)
            # Table separator rows (|---|---|) and duplicate-divider artifacts are
            # skipped only when the row is ENTIRELY separators; a '---' inside a
            # URL path or title cell is content and must parse.
            if not m or re.fullmatch(r"\|[\s\-|:]+\|", line_s):
                continue
            cells = [c.strip() for c in m.group(2).split("|")]
            entry = " | ".join(cells)
        else:
            entry = m.group(2)
        n = int(m.group(1))
        if n in bib:
            # Any repeat definition is an error, even an identical row — a
            # number must map to exactly one source.
            dup_numbers.append(n)
        else:
            bib[n] = entry

    # A bracketed year ('fiscal [2024]') is prose, not a citation — unless the
    # Sources list really has an entry with that number.
    inline = sorted(n for n in inline_all if not (1900 <= n <= 2099 and n not in bib))

    if not inline and not bib:
        print(json.dumps({"ok": False, "inline_citations": 0, "sources_entries": 0,
                          "problems": ["no citations or Sources entries found — nothing to validate; is this the right report file?"]}))
        return 1

    problems = []
    if header_level != 2:
        problems.append(f"Sources section uses '{'#' * header_level}' — the template requires '## Sources'")
    for n in sorted(set(dup_numbers)):
        problems.append(f"Sources entry [{n}] is defined more than once")
    for n in inline:
        if n not in bib:
            problems.append(f"inline citation [{n}] has no Sources entry")
    for n in bib:
        if not re.search(rf"\[{n}\]", body):
            problems.append(f"Sources entry [{n}] is never cited in the body")

    # URL well-formedness in the Sources table.
    bib_lines = sources.splitlines() if sources else []
    for line in bib_lines:
        line_s = line.strip()
        if not (BIB_ENTRY_RE.match(line_s) or re.match(r"^\|\s*\d+\s*\|", line_s)):
            continue
        urls = re.findall(r"https?://[^\s\)\|]+", line_s)
        if not urls:
            problems.append(f"Sources entry has no URL: {line_s[:80]}")
        for url in urls:
            try:
                parts = urlsplit(url)
                has_host = bool(parts.netloc) and "." in parts.netloc
            except ValueError:
                has_host = False
            if not has_host:
                problems.append(f"malformed URL: {url}")

    # Suspicious (fabrication-pattern) titles — quoted, or first table cell.
    for n, entry in bib.items():
        title_m = re.search(r'"([^"]+)"', entry)
        if title_m:
            title = title_m.group(1)
        else:
            title = entry.split("|")[0].strip()
            title = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", title)  # [text](url) -> text
            title = re.sub(r"\s*\[\d{4}\]\s*", " ", title)          # drop bracketed years
            title = title.strip().rstrip(". ")
        if title:
            for pat, why in SUSPICIOUS_TITLE_PATTERNS:
                if re.match(pat, title):
                    problems.append(f"suspicious Sources entry [{n}] — {why}: \"{title}\"")

    # Placeholder bibliography / citation ranges anywhere in the report.
    if re.search(r"\[\d+\s*[-–]\s*\d+\]", body + sources):
        problems.append("citation ranges found (e.g. [1-2] or [3-50]) — list each entry")

    ok = not problems
    print(json.dumps({"ok": ok, "inline_citations": len(inline),
                      "sources_entries": len(bib), "problems": problems}))
    return 0 if ok else 1


# ---------------------------------------------------------------- structure check

def _section_heading(text: str, name: str):
    """The '## <name>...' heading, or None.

    A required section is a level-2 heading whose text STARTS with its name:
    '## Gaps and open questions' and '## Sources & references' count;
    '## Mind the Gaps' and '### Sources of revenue' do not.
    """
    return re.search(rf"^##[ \t]+{re.escape(name)}\b[^\n]*$", text, re.MULTILINE | re.IGNORECASE)


def cmd_validate_report(args) -> int:
    path = Path(args.report)
    text = path.read_text(encoding="utf-8")
    problems = []

    for heading, label in REQUIRED_SECTIONS:
        if not _section_heading(text, heading):
            problems.append(f"missing required section: {label} ('## {heading}' heading)")

    for pat, label in PLACEHOLDER_PATTERNS:
        hits = re.findall(pat, text)
        if hits:
            problems.append(f"placeholder text ({label}): {len(hits)} occurrence(s)")

    if not STATS_RE.search(text):
        problems.append("missing research stats block ('Research stats:')")

    # Evidence key legend below the Sources table: all four labels required.
    # The raw Sources section is used (labels are inline-code in the template and
    # code stripping would delete them).
    # A missing Sources section must not skip this check: no section means no legend.
    m_src = _section_heading(text, "Sources")
    sources_raw = text[m_src.start():] if m_src else ""
    if not all(lbl in sources_raw for lbl in
               ("[VERIFIED]", "[SOURCED]", "[REASONED]", "[ESTIMATED]")):
        problems.append("evidence key legend missing under Sources table — all four labels required")

    # Empty mandatory sections (heading present but no content). The emptiness
    # check mirrors the required-section check (heading CONTAINS the word) so
    # the two checks cannot disagree about what counts as the section. The
    # section body extends across deeper sub-headings (###) and stops at the
    # next heading of the same or higher level.
    for section in ("Contradictions", "Gaps"):
        m = _section_heading(text, section)
        if not m:
            continue
        lvl = 2
        body = text[m.end():]
        stop = re.search(rf"^#{{1,{lvl}}}\s", body, re.MULTILINE)
        content = body[:stop.start()] if stop else body
        if not content.strip():
            problems.append(f"'{section}' section is empty — write content or state 'No direct contradictions identified'")

    ok = not problems
    print(json.dumps({"ok": ok, "problems": problems}))
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init-run")
    s.add_argument("--dir", required=True)
    s.add_argument("--query", default="")
    s.add_argument("--mode", default=None,
                   help="research complexity, as in SKILL.md: simple | moderate | complex "
                        "(default: moderate; keeps the existing value on re-init)")
    s.add_argument("--provider", default=None,
                   help="search provider preference: donsetch | auto (default: keep existing)")
    s.set_defaults(func=cmd_init_run)

    s = sub.add_parser("register-source")
    s.add_argument("--dir", required=True)
    s.add_argument("--json", required=True)
    s.set_defaults(func=cmd_register_source)

    s = sub.add_parser("add-claim")
    s.add_argument("--dir", required=True)
    s.add_argument("--json", required=True)
    s.set_defaults(func=cmd_add_claim)

    s = sub.add_parser("add-evidence")
    s.add_argument("--dir", required=True)
    s.add_argument("--json", required=True)
    s.set_defaults(func=cmd_add_evidence)

    s = sub.add_parser("verify-claims")
    s.add_argument("--dir", required=True)
    s.add_argument("--strict", action="store_true")
    s.add_argument("--provider-used", default=None, dest="provider_used",
                   help="record which search provider was used (e.g. donsetch, built-in)")
    s.add_argument("--refute-none", default=None, dest="refute_none",
                   help="counter-evidence was searched for and none found: say what was searched "
                        "(recorded in run_manifest.json; waives the counter-evidence check)")
    s.set_defaults(func=cmd_verify_claims)

    s = sub.add_parser("verify-citations")
    s.add_argument("--report", required=True)
    s.set_defaults(func=cmd_verify_citations)

    s = sub.add_parser("validate-report")
    s.add_argument("--report", required=True)
    s.set_defaults(func=cmd_validate_report)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())