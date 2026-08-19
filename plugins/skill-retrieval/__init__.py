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
"""

import logging
import os
import sys
from pathlib import Path

# Ensure scripts/ is importable
_scripts_dir = Path(__file__).parent / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from bm25_retriever import get_index, get_skill_info

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


TOP_K = _parse_top_k(os.environ.get("SKILL_RETRIEVAL_TOP_K"))


# ─── Phase 1: System prompt compaction ───────────────────────────────────────

def _compact_skills_prompt():
    """Monkey-patch build_skills_system_prompt to return names-only.

    The original function builds a full skill index with descriptions.
    We wrap it: call the original, then strip all descriptions, keeping
    only skill names organized by category.

    Partial-patch scenario: if ``run_agent`` cannot be imported (e.g. the
    plugin is loaded outside a full Hermes runtime), only ``prompt_builder``
    is patched.  Callers that resolve ``build_skills_system_prompt`` via
    ``run_agent`` will still see the original (uncompacted) prompt.  The
    retrieval hook (Phase 2) remains functional regardless.
    """
    try:
        from agent import prompt_builder
    except ImportError:
        try:
            import hermes_agent.agent.prompt_builder as prompt_builder
        except ImportError:
            logger.warning("Cannot locate prompt_builder — compaction skipped")
            return False

    # The function is called via run_agent.build_skills_system_prompt(...)
    # (see agent/system_prompt.py _ra() lazy reference). We must patch it
    # on BOTH prompt_builder (source module) AND run_agent (caller module)
    # so the patched version is resolved at call time.
    try:
        import run_agent
    except ImportError:
        try:
            import hermes_agent.run_agent as run_agent
        except ImportError:
            logger.warning(
                "Cannot locate run_agent — patching prompt_builder only"
            )
            run_agent = None

    original = prompt_builder.build_skills_system_prompt
    if getattr(original, "_skill_retrieval_patched", False):
        return True  # Already patched

    def compact_build(*args, **kwargs):
        # Call original to get the full prompt
        full_prompt = original(*args, **kwargs)
        if not full_prompt:
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
            f"plugin (BM25 top-{TOP_K}). If no skills appear in the injected context "
            f"above your message, use skill_view(name) to load any skill by name."
        )
        return result

    compact_build._skill_retrieval_patched = True
    prompt_builder.build_skills_system_prompt = compact_build
    if run_agent is not None:
        run_agent.build_skills_system_prompt = compact_build
    logger.info("System prompt compaction enabled (names-only skill index)")
    return True


# ─── Phase 2: Per-turn retrieval hook ───────────────────────────────────────

def _on_pre_llm_call(session_id: str, user_message: str, **kwargs) -> dict | None:
    """pre_llm_call hook — inject top-K relevant skills per turn.

    Called once per turn before the tool-calling loop. Returns a dict with
    a "context" key whose value is appended to the user message.
    """
    try:
        index = get_index()
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
            info = get_skill_info(skill_id)
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
    """Register the pre_llm_call hook and compact the skills system prompt."""
    # Phase 1: Compact system prompt (names-only). Failures are logged inside
    # _compact_skills_prompt — never abort registration of the retrieval hook.
    try:
        _compact_skills_prompt()
    except Exception as e:
        logger.warning("System prompt compaction failed: %s", e, exc_info=True)

    # Phase 2: Per-turn retrieval
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    logger.info("Skill retrieval plugin registered (top_k=%d, compact=true)", TOP_K)
