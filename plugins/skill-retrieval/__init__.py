"""Skill Retrieval Plugin — pre_llm_call hook + system prompt compaction.

Two-phase progressive disclosure for Hermes Agent skills:

1. **System prompt compaction** (at session start): Monkey-patches
   `build_skills_system_prompt` to return names-only — all skill names
   visible but descriptions stripped (~2K tokens instead of ~11.5K).

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

import logging
import os
import sys
import time
from collections import OrderedDict
from pathlib import Path

# Ensure scripts/ is importable
_scripts_dir = Path(__file__).parent / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from bm25_retriever import clear_index_cache, get_index, get_skill_info

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 6


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

# Capability snapshots captured from the patched build_skills_system_prompt
# (its kwargs) so the retrieval hook can rebuild the BM25 corpus with the same
# available_tools / available_toolsets.
#
# Named sessions are keyed by the session-env identity (see
# _remember_capability_snapshot). A session's capabilities are fixed, and
# Hermes builds its system prompt once then restores it from the DB on later
# turns, so named snapshots never expire — they are only evicted by the LRU
# bound. The anonymous key ("") is shared by every identity-less build, so it
# keeps a STALENESS WINDOW: a snapshot older than the window belongs to another
# turn and must NOT be applied (hook falls back to the fail-open get_index()).
_SNAPSHOT_MAX_AGE_S = 30.0
_MAX_SNAPSHOT_SESSIONS = 256
_session_capability_snaps: "OrderedDict[str, tuple[float, frozenset | None, frozenset | None]]" = OrderedDict()


def _freeze_capability_set(value) -> frozenset | None:
    try:
        return None if value is None else frozenset(value)
    except TypeError:
        return None  # unhashable/odd input — treat as unknown, never raise


def _remember_capability_snapshot(*args, **kwargs) -> None:
    """Store available_tools / available_toolsets from a compact_build call.

    Fail-soft: must never break Hermes' system-prompt construction.
    """
    try:
        has_kw_tools = "available_tools" in kwargs
        has_kw_toolsets = "available_toolsets" in kwargs
        if not has_kw_tools and not has_kw_toolsets and not args:
            return
        tools = kwargs["available_tools"] if has_kw_tools else (args[0] if len(args) > 0 else None)
        toolsets = kwargs["available_toolsets"] if has_kw_toolsets else (args[1] if len(args) > 1 else None)
        # Identity: explicit session_id kwarg wins (future-proofing). Otherwise
        # bind to the task-local Hermes session identity via
        # gateway.session_context.get_session_env("HERMES_SESSION_ID") —
        # build_skills_system_prompt() has no session_id parameter, so the
        # session env is the only identity source available at build time
        # (issue #8 close-out contract). Anonymous (no identity) falls to "".
        session_id = kwargs.get("session_id") or ""
        if not isinstance(session_id, str):
            session_id = str(session_id) if session_id else ""
        if not session_id:
            try:
                get_session_env = getattr(
                    sys.modules.get("gateway.session_context"), "get_session_env", None,
                )
                if callable(get_session_env):
                    session_id = get_session_env("HERMES_SESSION_ID") or ""
            except Exception:
                session_id = ""
            if not isinstance(session_id, str):
                session_id = str(session_id) if session_id else ""
        _session_capability_snaps[session_id] = (
            time.monotonic(),
            _freeze_capability_set(tools),
            _freeze_capability_set(toolsets),
        )
        # Bounded LRU: the current session is most recent, evict the least recent.
        _session_capability_snaps.move_to_end(session_id)
        while len(_session_capability_snaps) > _MAX_SNAPSHOT_SESSIONS:
            _session_capability_snaps.popitem(last=False)
    except Exception:
        logger.debug("capability snapshot capture failed", exc_info=True)


def _capability_kwargs_for_session(session_id: str | None) -> dict | None:
    """Return get_index/get_skill_info kwargs for a session, or None if unknown."""
    sid = session_id or ""
    snap = _session_capability_snaps.get(sid)
    if snap is None:
        return None
    captured_at, tools, toolsets = snap
    if not sid and time.monotonic() - captured_at > _SNAPSHOT_MAX_AGE_S:
        # Stale anonymous snapshot — belongs to another turn. Fail open.
        _session_capability_snaps.pop(sid, None)
        return None
    _session_capability_snaps.move_to_end(sid)
    return {
        "available_tools": set(tools) if tools is not None else None,
        "available_toolsets": set(toolsets) if toolsets is not None else None,
    }


# ─── Phase 1: System prompt compaction ───────────────────────────────────────

def _compact_skills_prompt(compact: bool = True):
    """Monkey-patch build_skills_system_prompt to return names-only.

    The original function builds a full skill index with descriptions.
    We wrap it: call the original, then strip all descriptions, keeping
    only skill names organized by category. The wrapper always records the
    capability snapshot; with ``compact=False`` it returns the original
    prompt unchanged (SKILL_RETRIEVAL_COMPACT=0).

    Since the Sep 2026 decomposition, only ``agent.prompt_builder`` is
    patched — every caller (including the ``run_agent`` PLUGIN-COMPAT
    facade) resolves the function through it. The retrieval hook
    (Phase 2) is unaffected.
    """
    try:
        from agent import prompt_builder
    except ImportError:
        try:
            import hermes_agent.agent.prompt_builder as prompt_builder
        except ImportError:
            logger.warning("Cannot locate prompt_builder — compaction skipped")
            return False

    # Sep 2026 decomposition (PR #102117; this call site ships from v0.21.1,
    # hence requires_hermes ">=0.21.1" — v0.21.0 still called run_agent's
    # import-time binding): callers resolve build_skills_system_prompt via
    # agent.prompt_builder directly
    # (agent/system_prompt.py uses _pb.build_skills_system_prompt), and the
    # run_agent PLUGIN-COMPAT shim resolves the attribute through
    # agent.prompt_builder at call time too. Patching prompt_builder alone
    # therefore covers every resolution path. The old run_agent attribute
    # patch is gone: it triggered `hermes doctor`'s plugin-compat AST scan
    # (removed-on-2026-09-14 warning) and would get the plugin disabled
    # after that date. Do NOT re-add run_agent patching.

    original = prompt_builder.build_skills_system_prompt
    if getattr(original, "_skill_retrieval_patched", False):
        return True  # Already patched

    def compact_build(*args, **kwargs):
        _remember_capability_snapshot(*args, **kwargs)
        # Call original to get the full prompt
        full_prompt = original(*args, **kwargs)
        if not compact or not full_prompt:
            return full_prompt

        # Parse the <available_skills> block and strip descriptions
        import re
        # Extract everything between <available_skills> and </available_skills>
        match = re.search(r"<available_skills>(.*?)</available_skills>", full_prompt, re.DOTALL)
        if not match:
            return full_prompt  # Can't parse — return original

        skills_block = match.group(1)
        # Build names-only version: keep category headers and skill names, drop descriptions
        lines = skills_block.strip().split("\n")
        compact_lines = []
        in_skill_entry = False
        entry_indent = 0  # indentation level of the current skill entry
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            indent = len(line) - len(line.lstrip())
            # Skill entries (e.g. "    - name: description")
            if stripped.startswith("-"):
                name = stripped[1:].strip()
                if ":" in name:
                    name = name.split(":")[0].strip()
                compact_lines.append(f"    - {name}")
                in_skill_entry = True
                entry_indent = indent
            # Wrapped continuation of a skill description — drop it.
            # A continuation line is MORE indented than the skill entry.
            # Category headers are LESS indented and must clear the flag.
            elif in_skill_entry and indent > entry_indent:
                continue
            # Demoted categories (e.g. "  devops [names only]: a, b") are
            # already names-only — keep the line, its names are the skills.
            elif "[names only]:" in stripped:
                compact_lines.append(f"  {stripped}")
                in_skill_entry = False
            # Category headers (e.g. "  creative:" or "  creative: Some description")
            elif stripped.endswith(":") or ":" in stripped:
                # Keep category name, drop its description
                cat_name = stripped.split(":")[0].strip()
                compact_lines.append(f"  {cat_name}:")
                in_skill_entry = False
            else:
                compact_lines.append(line)

        compact_block = "\n".join(compact_lines)

        # Replace the available_skills block in the full prompt
        result = full_prompt[:match.start()] + "<available_skills>\n" + compact_block + "\n</available_skills>" + full_prompt[match.end():]

        # Add a note about the retrieval hook
        result += (
            f"\n\nSkill descriptions are injected per-turn by the skill-retrieval "
            f"plugin (BM25 top-{TOP_K}), appended after the user's message. If none "
            f"appear there, use skill_view(name) to load any skill by name."
        )
        return result

    compact_build._skill_retrieval_patched = True
    prompt_builder.build_skills_system_prompt = compact_build

    if compact:
        logger.info("System prompt compaction enabled (names-only skill index)")
    return True


def _hook_skills_cache_clear():
    """Wrap clear_skills_system_prompt_cache so it also drops the BM25 index.

    Hermes calls it after skill_manage create/patch/delete, hub installs and
    skill toggles. Every caller (tools/skill_manager_tool.py,
    agent/learning_mutations.py, hermes_cli/skills_hub.py, ...) does a
    function-local ``from agent.prompt_builder import
    clear_skills_system_prompt_cache`` at call time, so replacing the module
    attribute reaches them all. The original always runs first; a failure
    clearing the plugin cache never propagates into Hermes.
    """
    try:
        from agent import prompt_builder
    except ImportError:
        logger.debug("Cannot locate prompt_builder — cache-clear hook skipped")
        return False
    original = getattr(prompt_builder, "clear_skills_system_prompt_cache", None)
    if original is None:
        return False
    if getattr(original, "_skill_retrieval_patched", False):
        return True  # Already patched

    def clear_with_index(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            try:
                clear_index_cache()
            except Exception:
                logger.debug("BM25 index cache clear failed", exc_info=True)

    clear_with_index._skill_retrieval_patched = True
    prompt_builder.clear_skills_system_prompt_cache = clear_with_index
    return True


# ─── Phase 2: Per-turn retrieval hook ───────────────────────────────────────

def _on_pre_llm_call(session_id: str, user_message: str, **kwargs) -> dict | None:
    """pre_llm_call hook — inject top-K relevant skills per turn.

    Called once per turn before the tool-calling loop. Returns a dict with
    a "context" key whose value is appended to the user message.
    """
    try:
        cap_kwargs = _capability_kwargs_for_session(session_id)
        if cap_kwargs is None and session_id:
            # Named session without a snapshot (never built, or evicted): the
            # fail-open corpus could suggest skills Hermes hides. Skip the turn.
            logger.debug("No capability snapshot for session %s — skipping", session_id)
            return None
        index = get_index(**cap_kwargs) if cap_kwargs is not None else get_index()
        if index is None:
            return None

        results = index.retrieve(user_message, top_k=TOP_K)
        if not results:
            return None

        # Build the injection block
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
                # Truncate long descriptions
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
    """Register the pre_llm_call hook and optionally compact the skills system prompt."""
    # Phase 1: Compact system prompt (names-only). The wrapper is installed
    # even with compaction disabled, because it also records the capability
    # snapshot the hook needs. Failures are logged inside
    # _compact_skills_prompt — never abort registration of the retrieval hook.
    if not COMPACT_SYSTEM_PROMPT:
        logger.info("System prompt compaction disabled by SKILL_RETRIEVAL_COMPACT")
    try:
        _compact_skills_prompt(compact=COMPACT_SYSTEM_PROMPT)
    except Exception as e:
        logger.warning("System prompt compaction failed: %s", e, exc_info=True)

    # Invalidate the BM25 index whenever Hermes drops its skills prompt cache.
    try:
        _hook_skills_cache_clear()
    except Exception as e:
        logger.warning("Skill cache-clear hook failed: %s", e, exc_info=True)

    # Phase 2: Per-turn retrieval
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    logger.info(
        "Skill retrieval plugin registered (top_k=%d, compact=%s)",
        TOP_K,
        str(COMPACT_SYSTEM_PROMPT).lower(),
    )
