"""Jev semantic rerank stage for the skill-retrieval plugin (trial).

Advisory-layer pattern (system-one-decision-models skill): BM25 stays the
deterministic recall stage and the source of truth. When
``SKILL_RETRIEVAL_RERANK=jev`` is set, the BM25 top-N shortlist is reranked
by one batched TypeSafe Jev call (one Noul judgement per candidate) and the
injected order follows Jev's probabilities. Any Jev failure falls back to
the exact BM25 order — the plugin never blocks or loses injection quality
because of the advisory layer.

Per-turn A/B logging records both orders side by side to a JSONL file so
the trial review can compute rank flips, displacement, fallback rate,
latency and cost on real traffic. The log never blocks the turn.

Request shape follows the proven contract in ~/.hermes/scripts/yahoo_triage.py
(POST https://api.typesafe.ai/v1/systemone, model jev-latest, noul questions
with true/false criteria dict, one question keyed per candidate id).

Injection defense: imperative sentence patterns in the user query are
neutralised before the query becomes Jev state. Measured in the
2026-09-29 hard-case trial: Jev followed injected text at conf 0.43.

The API key is read from ~/.hermes/.env (TYPESAFE_API_KEY=...; legacy
TYPESAFE_KEY= still accepted) and is never
logged, never returned, never included in any record.
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

TS_URL = "https://api.typesafe.ai/v1/systemone"
MODEL_DEFAULT = "jev-latest"
ENV_PREFIX_RE = re.compile(
    r"^(ignore( all)?( previous| prior)? (instructions|prompts?|messages?)"
    r"|disregard( all)? (instructions|prompts?)"
    r"|system( prompt)?:"
    r"|you are now"
    r"|new (instructions|task):"
    r"|delete (everything|all)"
    r"|erase (everything|all)"
    r"|forget (everything|all|your)"
    r"|override (your )?(instructions|rules)"
    r")\b[^.\n]*[.\n]?\s*",
    re.IGNORECASE,
)


def _parse_rerank_env(raw: str | None) -> str:
    """Parse SKILL_RETRIEVAL_RERANK; only 'jev' enables. Anything else → off."""
    value = (raw or "").strip().lower()
    if value == "jev":
        return "jev"
    if value in ("", "off", "0", "false", "no"):
        return "off"
    logger.warning("Invalid SKILL_RETRIEVAL_RERANK=%r — rerank disabled", raw)
    return "off"


def _env_or_envfile(name: str) -> str:
    """os.environ first, then ~/.hermes/.env (same file the key lives in)."""
    raw = os.environ.get(name)
    if raw is not None:
        return raw
    try:
        for line in open(os.path.expanduser("~/.hermes/.env")):
            m = re.match(rf"^{name}=(.*)$", line.strip())
            if m:
                return m.group(1)
    except OSError:
        pass
    return ""


RERANK_MODE = _parse_rerank_env(_env_or_envfile("SKILL_RETRIEVAL_RERANK"))

#: BM25 shortlist size fed to the reranker (TOP_K is carved out of this).
RERANK_CANDIDATES = 12
# Decisive bands outside which Jev's order is trusted; inside the band the
# candidate keeps its BM25-relative position (calibration describes groups,
# not single answers — measured in the 2026-09-29 trial).
BAND_LOW = 0.35
BAND_HIGH = 0.65
# Decision-low: below this the candidate sinks (but is never dropped while
# it is on the BM25 shortlist — recall stays BM25's job).
_TOK_PRICE_PER_INPUT = 0.042 / 1_000_000  # $/token, TypeSafe list price


def neutralize_query(query) -> str:
    """Flatten any input to a string and strip imperative sentence patterns.

    Keeps legitimate query content; removes text shaped like injected
    commands so it cannot steer the rerank judgement from inside the state.
    """
    if query is None:
        return ""
    text = query if isinstance(query, str) else str(query)
    neutral = ENV_PREFIX_RE.sub("", text)
    # Collapse whitespace left by removals; cap length for the request budget.
    neutral = re.sub(r"\s+", " ", neutral).strip()
    return neutral[:2000]


def _env_log_path() -> Path:
    raw = os.environ.get("SKILL_RETRIEVAL_RERANK_LOG", "")
    return Path(raw) if raw else Path.home() / ".hermes/data/jev-trial/rerank_ab_log.jsonl"


def _load_key() -> str | None:
    """Read TYPESAFE_API_KEY (or legacy TYPESAFE_KEY) from ~/.hermes/.env.

    Returns None when absent."""
    try:
        for line in open(os.path.expanduser("~/.hermes/.env")):
            m = re.match(r"^(?:TYPESAFE_API_KEY|TYPESAFE_KEY)=(\S+)", line.strip())
            if m:
                return m.group(1)
    except OSError:
        pass
    return None


def build_request(query: str, shortlist: "list[tuple[str, str]]") -> "tuple[dict, dict]":
    """Build the Jev request payload pieces for one rerank turn.

    ``shortlist`` is [(skill_id, description), ...] in BM25 order.
    Returns (questions, state) following the proven /v1/systemone contract:
    one noul per candidate, keyed ``rel_<skill_id>``, true/false criteria.
    """
    neutral_query = neutralize_query(query)
    questions: dict = {}
    items: dict = {}
    for skill_id, description in shortlist:
        desc = (description or "")[:400]
        questions[f"rel_{skill_id}"] = {
            "type": "noul",
            "instructions": (
                "Is this skill relevant to serve the user's query intent? "
                "Judge semantic intent match, not exact word overlap."
            ),
            "criteria": {
                "true": "skill should be surfaced for this query",
                "false": "skill is unrelated to this query",
            },
        }
        items[skill_id] = desc
    state = {"user_query": neutral_query, "skills": items}
    return questions, state


def _jev_rerank_call(shortlist, query, key) -> "tuple[dict | None, dict | None, str | None]":
    """One batched Jev call: N Noul judgements in a single request.

    Returns (probs, usage, error): probs maps skill_id → probability,
    usage carries input_tokens and latency_ms for the A/B log.
    On any failure returns (None, None, reason). Never raises outward.
    """
    try:
        questions, state = build_request(query, shortlist)
        body = json.dumps(
            {"state": state, "model": os.environ.get("SKILL_RETRIEVAL_RERANK_MODEL", MODEL_DEFAULT),
             "questions": questions},
        ).encode()
        req = urllib.request.Request(
            TS_URL,
            data=body,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.load(resp)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        answers = data.get("answers") or {}
        probs: dict[str, float] = {}
        for skill_id, _desc in shortlist:
            ans = answers.get(f"rel_{skill_id}")
            if not isinstance(ans, dict):
                return None, None, f"missing answer for {skill_id}"
            value = ans.get("probability", ans.get("noul"))
            try:
                p = float(value)
            except (TypeError, ValueError):
                return None, None, f"non-numeric probability for {skill_id}"
            if not 0.0 <= p <= 1.0:
                return None, None, f"out-of-range probability for {skill_id}"
            probs[skill_id] = p
        usage_in = data.get("usage", {}).get("input_tokens", 0)
        return probs, {"input_tokens": usage_in, "latency_ms": latency_ms}, None
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode()[:120]
        except Exception:
            pass
        return None, None, f"HTTP {exc.code} {detail}".strip()
    except Exception as exc:  # network, timeout, JSON, anything
        return None, None, f"{type(exc).__name__}: {exc}"[:200]


def _score_rerank_key(item: "tuple[str, float, float, int]") -> "tuple":
    """Sort key for the blended order.

    Decisive candidates (prob outside the band) sort by Jev probability;
    band candidates keep BM25-relative position, which is implemented as:
    decisive-high first (by prob desc), then band candidates (by BM25 rank),
    then decisive-low (by prob asc so the least-relevant sink deepest).
    """
    skill_id, bm25_score, prob, bm25_rank = item
    if prob >= BAND_HIGH:
        return (0, -prob, bm25_rank)
    if prob > BAND_LOW:  # band — anchor to BM25 position
        return (1, bm25_rank, prob)
    return (2, prob, bm25_rank)


def _write_log(record: dict) -> None:
    """Append one JSONL line; any failure is swallowed (fail-soft)."""
    try:
        path = _env_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a") as fh:
            fh.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception as exc:
        logger.debug("rerank A/B log write failed: %s", exc)


def rerank(query, shortlist=None, rerank_candidates: int = RERANK_CANDIDATES) -> dict:
    """Optionally rerank the BM25 shortlist with Jev. Never raises.

    ``shortlist``: [(skill_id, bm25_score)] in BM25 order (or with desc as
    a third position element [(skill_id, score, description)]).

    Returns dict:
      order: final skill ids in injected order
      skipped: True when Jev did not run (disabled, no key, error, empty)
      fallback_reason: why the BM25 order was kept (None when Jev ran)
      plus key_loaded/input_tokens/latency_ms for the caller's logging.
    """
    shortlist = list(shortlist or [])
    if RERANK_MODE != "jev" or not shortlist:
        return {"order": [s[0] for s in shortlist], "skipped": True,
                "fallback_reason": "disabled" if RERANK_MODE != "jev" else "empty_shortlist"}

    key = _load_key()
    probs, usage, error = (None, None, "missing_key")
    if key:
        # Description text for Jev state comes from the shortlist tuples when
        # present; the caller may pass (skill_id, score, description) triples.
        enriched = []
        for entry in shortlist:
            if len(entry) >= 3:
                enriched.append((entry[0], entry[2]))
            else:
                info_probe = entry
                enriched.append((info_probe[0], str(info_probe[1])))
        probs, usage, error = _jev_rerank_call(enriched, query, key)

    bm25_order = [s[0] for s in shortlist]
    bm25_rank = {sid: i for i, sid in enumerate(bm25_order)}

    record: dict = {
        "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "session_id": os.environ.get("HERMES_SESSION_ID", ""),
        "query": (str(query)[:200] if query else ""),
        "bm25_order": bm25_order,
        "jev_order": None,
        "injected_order": bm25_order,
        "jev_probs": None,
        "input_tokens": None,
        "latency_ms": None,
        "fallback_reason": None,
    }

    if probs is None:
        record["fallback_reason"] = error
        _write_log(record)
        logger.info("Jev rerank skipped: %s — BM25 order unchanged", error)
        return {"order": bm25_order, "skipped": True, "fallback_reason": error,
                "key_loaded": key is not None}

    # Sorted by Jev probability desc with band anchoring.
    decorated = []
    for entry in shortlist:
        sid = entry[0]
        # Score may be (skill_id, score) or (skill_id, score, description).
        bm25_score = entry[1] if isinstance(entry[1], (int, float)) else 0.0
        p = probs.get(sid, BAND_LOW)  # missing prob → treated as band
        decorated.append((sid, bm25_score, p, bm25_rank[sid]))
    final = [sid for sid, *_ in sorted(decorated, key=_score_rerank_key)]

    record.update({
        "jev_order": final,
        "injected_order": final,
        "jev_probs": probs,
        "input_tokens": (usage or {}).get("input_tokens"),
        "latency_ms": (usage or {}).get("latency_ms"),
        "rank1_flip": bool(
            final and bm25_order and final[0] != bm25_order[0]
        ),
    })
    _write_log(record)
    logger.debug(
        "Jev rerank: %d candidates, rank1_flip=%s, %s tok, %.0f ms",
        len(final), record["rank1_flip"], (usage or {}).get("input_tokens"),
        (usage or {}).get("latency_ms", 0),
    )
    return {"order": final, "skipped": False, "fallback_reason": None,
            "key_loaded": True,
            "input_tokens": (usage or {}).get("input_tokens"),
            "latency_ms": (usage or {}).get("latency_ms")}