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
  TOP_K defaults to 6. Override with env var ``SKILL_RETRIEVAL_TOP_K``.
  System prompt compaction is enabled by default. Set
  ``SKILL_RETRIEVAL_COMPACT=0`` to keep retrieval injection while leaving the
  original Hermes skills prompt untouched.
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

_DEFAULT_TOP_K = 6
_COMPACT_SENTINEL = "<!-- skill-retrieval:compact -->"
_SKILLS_BLOCK_RE = re.compile(r"<available_skills>(.*?)</available_skills>", re.DOTALL)


def _parse_top_k(raw: str | None, default: int = _DEFAULT_TOP_K) -> int:
    """Parse TOP_K from env; invalid/empty values fall back to ``default``."""
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning(
            "Invalid SKILL_RETRIEVAL_TOP_K=%r — using default %d", raw, default
        )
        return default
    if value < 1:
        logger.warning(
            "SKILL_RETRIEVAL_TOP_K=%r must be >= 1 — using default %d", raw, default
        )
        return default
    return value


def _parse_bool_env(raw: str | None, *, default: bool = True) -> bool:
    """Parse a permissive boolean env var without failing plugin startup."""
    if raw is None or not str(raw).strip():
        return default
    value = str(raw).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    logger.warning("Invalid SKILL_RETRIEVAL_COMPACT=%r — using default %s", raw, default)
    return default


TOP_K = _parse_top_k(os.environ.get("SKILL_RETRIEVAL_TOP_K"))
COMPACT_SYSTEM_PROMPT = _parse_bool_env(os.environ.get("SKILL_RETRIEVAL_COMPACT"))

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
_session_capability_snaps: "OrderedDict[str, tuple[float, frozenset]]" = OrderedDict()
_session_platforms: "OrderedDict[str, str]" = OrderedDict()
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
    """Observer: drop the BM25 index on any skill mutation (not mere loads)."""
    try:
        if action != "loaded":
            clear_index_cache()
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
        "Skill retrieval plugin registered (top_k=%d, compact=%s)",
        TOP_K,
        str(COMPACT_SYSTEM_PROMPT).lower(),
    )
