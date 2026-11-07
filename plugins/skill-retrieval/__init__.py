"""Skill Retrieval Plugin — pre_llm_call hook + llm_request compaction.

Two-phase progressive disclosure for Hermes Agent skills:

1. **System prompt compaction** (llm_request middleware): Rewrites the
   ``<available_skills>`` block in the outgoing provider request to
   names-only (~2K tokens instead of ~11.5K). No core monkey-patches.

2. **Per-turn retrieval** (pre_llm_call hook): BM25 retrieves top-K
   relevant skills based on the user message and injects their full
   descriptions into the user message (~300 tokens).

Net token savings: ~11.5K → ~2.3K tokens per turn for skills, with
better discovery than dumping every description into the system prompt.

Configuration:
  TOP_K (BM25 candidate pool) defaults to 6. Override with env var
  ``SKILL_RETRIEVAL_TOP_K``.
  INJECT_K (how many of the retrieved candidates are actually injected)
  defaults to TOP_K. Override with env var ``SKILL_RETRIEVAL_INJECT_K``.
  Values above TOP_K are clamped. A candidate pool wider than the
  injected set gives the reranker something to filter: Jev injects its top
  INJECT_K picks; on any Jev failure BM25's first INJECT_K stand.
  System prompt compaction is enabled by default. Set
  ``SKILL_RETRIEVAL_COMPACT=0`` to keep retrieval injection while leaving the
  original Hermes skills prompt untouched.
  Jev session caching is disabled by default. Set
  ``SKILL_RETRIEVAL_RERANK_SESSION_CACHE=1`` to reuse a named session's
  confirmed candidate workset and avoid redundant external rerank calls.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import sys
import time
from collections import OrderedDict
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from .scripts.bm25_retriever import clear_index_cache, get_index, get_skill_info
except ImportError:  # direct-script / spec_from_file_location (no package context)
    _retriever_path = Path(__file__).resolve().parent / "scripts" / "bm25_retriever.py"
    _br = sys.modules.get("bm25_retriever")

    def _same_retriever(mod) -> bool:
        raw = getattr(mod, "__file__", "") or ""
        if not raw:
            return False
        try:
            return Path(raw).resolve() == _retriever_path.resolve()
        except OSError:
            return False

    if _br is None or not getattr(_br, "get_index", None) or not _same_retriever(_br):
        _spec = importlib.util.spec_from_file_location("bm25_retriever", _retriever_path)
        _br = importlib.util.module_from_spec(_spec)
        sys.modules["bm25_retriever"] = _br
        _spec.loader.exec_module(_br)
    clear_index_cache = _br.clear_index_cache
    get_index = _br.get_index
    get_skill_info = _br.get_skill_info

try:
    from .scripts.jev_rerank import RERANK_MODE, rerank as _jev_rerank
except ImportError:  # direct-script import (no package context) or module missing
    try:
        _jev_path = Path(__file__).resolve().parent / "scripts" / "jev_rerank.py"
        _jmod = sys.modules.get("jev_rerank")
        if _jmod is None or not getattr(_jmod, "rerank", None):
            _jspec = importlib.util.spec_from_file_location("jev_rerank", _jev_path)
            _jmod = importlib.util.module_from_spec(_jspec)
            sys.modules["jev_rerank"] = _jmod
            _jspec.loader.exec_module(_jmod)
        RERANK_MODE = _jmod.RERANK_MODE
        _jev_rerank = _jmod.rerank
    except Exception:
        RERANK_MODE = "off"

        def _jev_rerank(query, shortlist=None, rerank_candidates=12):
            return {"order": [s[0] for s in (shortlist or [])], "skipped": True,
                    "fallback_reason": "module_unavailable"}

_DEFAULT_TOP_K = 6
_COMPACT_SENTINEL = "<!-- skill-retrieval:compact -->"
_SKILLS_BLOCK_RE = re.compile(r"<available_skills>(.*?)</available_skills>", re.DOTALL)


def _parse_top_k(
    raw: str | None, default: int = _DEFAULT_TOP_K, name: str = "SKILL_RETRIEVAL_TOP_K"
) -> int:
    """Parse a size env var (TOP_K, INJECT_K); invalid/empty → ``default``."""
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning(
            "Invalid %s=%r — using default %d", name, raw, default
        )
        return default
    if value < 1:
        logger.warning(
            "%s=%r must be >= 1 — using default %d", name, raw, default
        )
        return default
    return value


def _parse_inject_k(raw: str | None, top_k: int) -> int:
    """Parse INJECT_K; unset → top_k; out of range clamped, never rejected."""
    if raw is None or not str(raw).strip():
        return top_k
    value = _parse_top_k(raw, default=top_k, name="SKILL_RETRIEVAL_INJECT_K")
    if value > top_k:
        logger.warning(
            "SKILL_RETRIEVAL_INJECT_K=%d exceeds candidate top_k=%d — clamping",
            value, top_k,
        )
        return top_k
    return value


def _parse_bool_env(
    raw: str | None,
    *,
    default: bool = True,
    name: str = "SKILL_RETRIEVAL_COMPACT",
) -> bool:
    """Parse a permissive boolean env var without failing plugin startup."""
    if raw is None or not str(raw).strip():
        return default
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    logger.warning("Invalid %s=%r — using default %s", name, raw, default)
    return default


TOP_K = _parse_top_k(os.environ.get("SKILL_RETRIEVAL_TOP_K"))
INJECT_K = _parse_inject_k(os.environ.get("SKILL_RETRIEVAL_INJECT_K"), TOP_K)
COMPACT_SYSTEM_PROMPT = _parse_bool_env(os.environ.get("SKILL_RETRIEVAL_COMPACT"))
RERANK_SESSION_CACHE = _parse_bool_env(
    os.environ.get("SKILL_RETRIEVAL_RERANK_SESSION_CACHE"),
    default=False,
    name="SKILL_RETRIEVAL_RERANK_SESSION_CACHE",
)

# Capability snapshots captured from the llm_request middleware: the skill
# names currently visible in Hermes' <available_skills> block, keyed by
# session_id from the middleware kwargs.
#
# Named sessions never expire — they are only evicted by the LRU bound.
# The anonymous key ("") is shared by every identity-less request, so it
# keeps a STALENESS WINDOW: a snapshot older than the window belongs to another
# turn and must NOT be applied (hook falls back to the fail-open get_index()).
_SNAPSHOT_MAX_AGE_S = 30.0
_MAX_SNAPSHOT_SESSIONS = 256
_MAX_RERANK_SESSION_STATES = 256
_session_capability_snaps: "OrderedDict[str, tuple[float, frozenset]]" = OrderedDict()
_session_platforms: "OrderedDict[str, str]" = OrderedDict()
_session_rerank_states: "OrderedDict[str, tuple[frozenset, frozenset]]" = OrderedDict()
_llm_request_warned = False


def _resolve_session_id(session_id) -> str:
    """Normalize a session id; empty falls back to the task-local Hermes identity."""
    sid = session_id or ""
    if not isinstance(sid, str):
        sid = str(sid) if sid else ""
    if sid:
        return sid
    try:
        get_session_env = getattr(
            sys.modules.get("gateway.session_context"), "get_session_env", None,
        )
        if callable(get_session_env):
            sid = get_session_env("HERMES_SESSION_ID") or ""
    except Exception:
        sid = ""
    if not isinstance(sid, str):
        sid = str(sid) if sid else ""
    return sid


def _can_reuse_session_rerank(session_id: str | None, candidate_ids) -> bool:
    """Return whether BM25's injected candidates fit a confirmed workset.

    The cache is deliberately limited to named sessions. Anonymous requests
    cannot be isolated safely and always take the normal rerank path.
    """
    if not RERANK_SESSION_CACHE:
        return False
    sid = _resolve_session_id(session_id)
    if not sid:
        return False
    state = _session_rerank_states.get(sid)
    if state is None:
        return False
    workset, confirmed_fallbacks = state
    would_inject = frozenset(list(candidate_ids)[:INJECT_K])
    if not would_inject.issubset(workset | confirmed_fallbacks):
        return False
    _session_rerank_states.move_to_end(sid)
    return True


def _remember_session_rerank(
    session_id: str | None,
    candidate_ids,
    injected_ids,
) -> None:
    """Freeze an initial workset or remember newly confirmed fallbacks."""
    if not RERANK_SESSION_CACHE:
        return
    sid = _resolve_session_id(session_id)
    if not sid:
        return
    candidate_set = frozenset(candidate_ids)
    injected_set = frozenset(injected_ids)
    previous = _session_rerank_states.get(sid)
    if previous is None:
        state = (candidate_set, frozenset())
    else:
        workset, confirmed_fallbacks = previous
        state = (workset, confirmed_fallbacks | (injected_set - workset))
    _session_rerank_states[sid] = state
    _session_rerank_states.move_to_end(sid)
    while len(_session_rerank_states) > _MAX_RERANK_SESSION_STATES:
        _session_rerank_states.popitem(last=False)


def _clear_session_rerank_cache() -> None:
    _session_rerank_states.clear()


def _remember_capability_snapshot(
    session_id: str | None = None,
    visible_names: frozenset | None = None,
    platform: str | None = None,
    **_kwargs,
) -> None:
    """Store visible skill names from an llm_request rewrite.

    Fail-soft: must never break Hermes' request path.
    """
    try:
        if visible_names is None:
            return
        names = visible_names if isinstance(visible_names, frozenset) else frozenset(visible_names)
        sid = _resolve_session_id(session_id)
        _session_capability_snaps[sid] = (time.monotonic(), names)
        _session_capability_snaps.move_to_end(sid)
        if platform:
            _session_platforms[sid] = str(platform)
            _session_platforms.move_to_end(sid)
        while len(_session_capability_snaps) > _MAX_SNAPSHOT_SESSIONS:
            evicted, _ = _session_capability_snaps.popitem(last=False)
            _session_platforms.pop(evicted, None)
            _session_rerank_states.pop(evicted, None)
        while len(_session_platforms) > _MAX_SNAPSHOT_SESSIONS:
            _session_platforms.popitem(last=False)
    except Exception:
        logger.debug("capability snapshot capture failed", exc_info=True)


def _capability_kwargs_for_session(session_id: str | None) -> dict | None:
    """Return get_index/get_skill_info kwargs for a session, or None if unknown."""
    sid = session_id or ""
    snap = _session_capability_snaps.get(sid)
    if snap is None:
        return None
    captured_at, names = snap
    if not sid and time.monotonic() - captured_at > _SNAPSHOT_MAX_AGE_S:
        # Stale anonymous snapshot — belongs to another turn. Fail open.
        _session_capability_snaps.pop(sid, None)
        _session_platforms.pop(sid, None)
        return None
    _session_capability_snaps.move_to_end(sid)
    kwargs: dict = {
        "visible_names": set(names) if names is not None else None,
    }
    plat = _session_platforms.get(sid)
    if plat:
        kwargs["platform_hint"] = plat
    return kwargs


# ─── Phase 1: names-only compaction (pure + llm_request middleware) ──────────

def _rendered_label(body: str) -> str:
    """Identity before the description separator in a rendered skills line.

    Core renders ``{name}: {desc}`` and ``{category}: {cat_desc}``
    (``prompt_builder._render_skills_index``). Qualified names such as
    ``vendor:demo`` and category labels such as ``org:acme`` contain colons.
    The separator is the first colon followed by a space. A trailing colon
    with no description (``org:acme:``) is not that separator.
    """
    sep = body.find(": ")
    if sep != -1:
        return body[:sep].strip()
    if body.endswith(":"):
        return body[:-1].strip()
    return body.strip()


def _is_legacy_names_only(skills_block: str) -> bool:
    """True for a pre-sentinel names-only block.

    Resumed sessions froze that byte string. Inserting the sentinel would
    miss the prompt cache. Any line containing ``": "`` (a skill description
    or a category description) is the current renderer and still compacts.
    A demoted ``[names only]:`` category line is the pre-sentinel compactor's
    own output and is skipped before that test.
    """
    saw_skill = False
    for line in skills_block.split("\n"):
        stripped = line.strip()
        if not stripped or stripped == _COMPACT_SENTINEL:
            continue
        if "[names only]:" in stripped:
            continue
        if ": " in stripped:
            return False
        if stripped.startswith("-"):
            saw_skill = True
    return saw_skill


def compact_available_skills_block(skills_block: str, compact: bool) -> str:
    """Deterministic names-only rewrite of an ``<available_skills>`` inner block.

    Pure: no I/O, no global mutation. Rewriting an already-rewritten block
    (sentinel present) is a no-op. ``compact=False`` returns ``skills_block``
    unchanged.
    """
    if not compact:
        return skills_block
    if _COMPACT_SENTINEL in skills_block or _is_legacy_names_only(skills_block):
        return skills_block

    lines = skills_block.strip().split("\n")
    compact_lines = []
    in_skill_entry = False
    entry_indent = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == _COMPACT_SENTINEL:
            continue
        indent = len(line) - len(line.lstrip())
        # Skill entries (e.g. "    - name: description")
        if stripped.startswith("-"):
            name = _rendered_label(stripped[1:].strip())
            compact_lines.append(f"    - {name}")
            in_skill_entry = True
            entry_indent = indent
        # Wrapped continuation of a skill description — drop it.
        elif in_skill_entry and indent > entry_indent:
            continue
        # Demoted categories (e.g. "  devops [names only]: a, b")
        elif "[names only]:" in stripped:
            compact_lines.append(f"  {stripped}")
            in_skill_entry = False
        # Category headers
        elif stripped.endswith(":") or ":" in stripped:
            cat_name = _rendered_label(stripped)
            compact_lines.append(f"  {cat_name}:")
            in_skill_entry = False
        else:
            compact_lines.append(line)

    compact_block = "\n".join(compact_lines)
    return f"{_COMPACT_SENTINEL}\n{compact_block}"


def _extract_visible_skill_names(skills_block: str) -> frozenset[str]:
    """Skill names currently listed in an ``<available_skills>`` inner block."""
    names: list[str] = []
    for line in skills_block.split("\n"):
        stripped = line.strip()
        if not stripped or stripped == _COMPACT_SENTINEL:
            continue
        if stripped.startswith("-"):
            name = _rendered_label(stripped[1:].strip())
            if name:
                names.append(name)
        elif "[names only]:" in stripped:
            after = stripped.split("[names only]:", 1)[1]
            for part in after.split(","):
                n = part.strip()
                if n:
                    names.append(n)
    return frozenset(names)


def _compaction_note() -> str:
    return (
        f"\n\nSkill descriptions are injected per-turn by the skill-retrieval "
        f"plugin (BM25 top-{TOP_K}), appended after the user's message. If none "
        f"appear there, use skill_view(name) to load any skill by name."
    )


def _rewrite_system_text(text: str, *, compact: bool) -> tuple[str | None, frozenset[str] | None]:
    """Rewrite one system-prompt string. Returns (new_text_or_None, names_or_None).

    ``new_text`` is None when the text should be left unchanged (no skills
    block, already compacted, or compaction disabled). Names are still
    returned whenever a skills block is found so the capability snapshot
    can be captured without rewriting.
    """
    if not isinstance(text, str) or not text:
        return None, None
    match = _SKILLS_BLOCK_RE.search(text)
    if not match:
        return None, None
    skills_block = match.group(1)
    names = _extract_visible_skill_names(skills_block)
    if not compact or _COMPACT_SENTINEL in skills_block or _is_legacy_names_only(skills_block):
        return None, names
    compact_inner = compact_available_skills_block(skills_block, compact=True)
    new_text = (
        text[: match.start()]
        + "<available_skills>\n"
        + compact_inner
        + "\n</available_skills>"
        + text[match.end() :]
    )
    note = _compaction_note()
    if "Skill descriptions are injected per-turn" not in new_text:
        new_text += note
    return new_text, names


def _copy_message(msg):
    if not isinstance(msg, dict):
        return msg
    out = dict(msg)
    content = out.get("content")
    if isinstance(content, list):
        out["content"] = [dict(p) if isinstance(p, dict) else p for p in content]
    return out


def _copy_system_blocks(system):
    if isinstance(system, list):
        return [dict(b) if isinstance(b, dict) else b for b in system]
    return system


def _apply_text_rewrite(text, compact: bool, names_out: list) -> str | None:
    new_text, names = _rewrite_system_text(text, compact=compact)
    if names is not None:
        names_out.append(names)
    return new_text


def _rewrite_request(request: dict, *, compact: bool) -> tuple[dict | None, frozenset[str] | None]:
    """Return (rewritten_request_or_None, visible_names_or_None).

    Never mutates ``request``. Never touches ``request["tools"]``.
    """
    names_found: list[frozenset[str]] = []
    changed = False
    out = dict(request)

    instructions = out.get("instructions")
    if isinstance(instructions, str):
        new = _apply_text_rewrite(instructions, compact, names_found)
        if new is not None:
            out["instructions"] = new
            changed = True

    messages = out.get("messages")
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, dict) and first.get("role") in {"system", "developer"}:
            copied = [_copy_message(m) for m in messages]
            msg0 = copied[0]
            content = msg0.get("content")
            if isinstance(content, str):
                new = _apply_text_rewrite(content, compact, names_found)
                if new is not None:
                    msg0["content"] = new
                    changed = True
            elif isinstance(content, list):
                new_parts = []
                part_changed = False
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        new_part = dict(part)
                        new_text = _apply_text_rewrite(new_part["text"], compact, names_found)
                        if new_text is not None:
                            new_part["text"] = new_text
                            part_changed = True
                        new_parts.append(new_part)
                    else:
                        new_parts.append(part)
                if part_changed:
                    msg0["content"] = new_parts
                    changed = True
            out["messages"] = copied

    system = out.get("system")
    if isinstance(system, str):
        new = _apply_text_rewrite(system, compact, names_found)
        if new is not None:
            out["system"] = new
            changed = True
    elif isinstance(system, list):
        copied_sys = _copy_system_blocks(system)
        sys_changed = False
        for i, block in enumerate(copied_sys):
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                new_text = _apply_text_rewrite(block["text"], compact, names_found)
                if new_text is not None:
                    copied_sys[i] = dict(block)
                    copied_sys[i]["text"] = new_text
                    sys_changed = True
        if sys_changed:
            out["system"] = copied_sys
            changed = True

    names = names_found[0] if names_found else None
    if not changed:
        return None, names
    return out, names


def _on_llm_request(
    request=None,
    original_request=None,
    session_id: str = "",
    platform: str = "",
    **kwargs,
) -> dict | None:
    """llm_request middleware — names-only skills rewrite + capability capture."""
    global _llm_request_warned
    try:
        if not isinstance(request, dict):
            return None
        rewritten, names = _rewrite_request(request, compact=COMPACT_SYSTEM_PROMPT)
        if names is not None:
            _remember_capability_snapshot(session_id, names, platform or None)
        if rewritten is None:
            return None
        return {"request": rewritten}
    except Exception:
        if not _llm_request_warned:
            _llm_request_warned = True
            logger.warning("llm_request skills rewrite failed", exc_info=True)
        return None


def _on_skill_lifecycle(action: str = "", **kwargs) -> None:
    """Drop retrieval caches on any skill mutation (not mere loads)."""
    try:
        if action != "loaded":
            clear_index_cache()
            _clear_session_rerank_cache()
    except Exception:
        logger.debug("on_skill_lifecycle cache clear failed", exc_info=True)


# ─── Phase 2: Per-turn retrieval hook ───────────────────────────────────────

def _on_pre_llm_call(session_id: str, user_message: str, **kwargs) -> dict | None:
    """pre_llm_call hook — inject top-K relevant skills per turn.

    Called once per turn before the tool-calling loop. Returns a dict with
    a "context" key whose value is appended to the user message.
    """
    try:
        cap_kwargs = _capability_kwargs_for_session(session_id)
        # pre_llm_call runs before llm_request, so turn 1 has no snapshot yet.
        # Single-turn sessions would otherwise compact the prompt and never
        # retrieve. Fail open (visible_names=None; disabled-set filtering
        # still applies) when this is the first turn and nothing was captured.
        # A later named turn whose snapshot was evicted or never captured skips.
        first_turn_without_snapshot = bool(kwargs.get("is_first_turn")) and cap_kwargs is None
        if cap_kwargs is None and session_id and not first_turn_without_snapshot:
            logger.debug("No capability snapshot for session %s — skipping", session_id)
            return None
        index = get_index(**cap_kwargs) if cap_kwargs is not None else get_index()
        if index is None:
            return None

        results = index.retrieve(user_message, top_k=TOP_K)
        if not results:
            return None

        # Optional Jev semantic rerank stage (SKILL_RETRIEVAL_RERANK=jev).
        # Advisory: BM25 order is kept on any Jev failure; the shortlist is
        # only re-ordered. The injection below then filters to INJECT_K.
        rerank_note = ""
        if RERANK_MODE == "jev" and len(results) >= 2:
            bm25_candidate_ids = [skill_id for skill_id, _score in results]
            reuse_session_workset = _can_reuse_session_rerank(
                session_id, bm25_candidate_ids
            )
            if reuse_session_workset:
                logger.debug(
                    "Reused session rerank workset for session %s", session_id
                )
            else:
                shortlist = []
                for skill_id, score in results:
                    info = (
                        get_skill_info(skill_id, **cap_kwargs)
                        if cap_kwargs is not None
                        else get_skill_info(skill_id)
                    )
                    desc = info["description"] if info else ""
                    shortlist.append((skill_id, score, desc))
                rr = _jev_rerank(user_message, shortlist)
                if not rr.get("skipped"):
                    # Rebuild (skill_id, score) pairs in the reranked order; keep
                    # the BM25 score for any candidate missing from the result.
                    score_by_id = dict(results)
                    reranked_results = [
                        (sid, score_by_id[sid])
                        for sid in rr["order"]
                        if sid in score_by_id
                    ]
                    if len(reranked_results) == len(results):
                        results = reranked_results
                        _remember_session_rerank(
                            session_id,
                            bm25_candidate_ids,
                            [sid for sid, _score in results[:INJECT_K]],
                        )
                        rerank_note = (
                            f"\n<!-- jev rerank: applied, "
                            f"{rr.get('input_tokens', '?')} tok, "
                            f"{rr.get('latency_ms', 0):.0f} ms -->"
                        )
                    else:
                        logger.warning(
                            "Jev rerank returned incomplete order — keeping BM25"
                        )
                else:
                    logger.info(
                        "Jev rerank skipped: %s", rr.get("fallback_reason", "unknown")
                    )

        # Injection split: the candidate pool is TOP_K wide but only the
        # first INJECT_K entries are injected. With jev rerank applied this
        # keeps Jev's top picks; on any fallback it keeps BM25's.
        dropped = len(results) - INJECT_K
        if dropped > 0:
            if rerank_note:
                rerank_note = rerank_note.replace(
                    " -->", f", kept top {INJECT_K}/{len(results)} -->"
                )
            results = results[:INJECT_K]

        lines = [
            "## Retrieved Skills (top-K relevant to your query)",
            "Load any of these with skill_view(name) if relevant:",
            "",
        ]
        for skill_id, score in results:
            info = (
                get_skill_info(skill_id, **cap_kwargs)
                if cap_kwargs is not None
                else get_skill_info(skill_id)
            )
            if info:
                name = info["name"]
                desc = info["description"]
                if len(desc) > 200:
                    desc = desc[:197] + "..."
                lines.append(f"- **{name}** ({skill_id}): {desc}")

        if rerank_note:
            lines.append(rerank_note.lstrip("\n"))
        context = "\n".join(lines)
        logger.debug("Injected %d skills for session %s", len(results), session_id)
        return {"context": context}

    except Exception as e:
        logger.error("Skill retrieval failed: %s", e, exc_info=True)
        return None  # fail gracefully — no injection


def register(ctx):
    """Register public surfaces: pre_llm_call, llm_request, on_skill_lifecycle."""
    if not COMPACT_SYSTEM_PROMPT:
        logger.info("System prompt compaction disabled by SKILL_RETRIEVAL_COMPACT")

    try:
        ctx.register_middleware("llm_request", _on_llm_request)
    except Exception as e:
        logger.warning("llm_request middleware registration failed: %s", e, exc_info=True)

    try:
        ctx.register_hook("on_skill_lifecycle", _on_skill_lifecycle)
    except Exception as e:
        logger.warning("on_skill_lifecycle hook registration failed: %s", e, exc_info=True)

    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    logger.info(
        "Skill retrieval plugin registered "
        "(top_k=%d, inject_k=%d, compact=%s, rerank_session_cache=%s)",
        TOP_K,
        INJECT_K,
        str(COMPACT_SYSTEM_PROMPT).lower(),
        str(RERANK_SESSION_CACHE).lower(),
    )
