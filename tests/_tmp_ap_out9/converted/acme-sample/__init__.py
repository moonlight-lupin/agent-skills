"""acme-sample — converted from Claude Code plugin."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire schemas to handlers and register hooks/skills."""
    # ── Bundled skills ──
    skills_dir = Path(__file__).parent / "skills"
    for child in sorted(skills_dir.iterdir()):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            ctx.register_skill(child.name, skill_md)

    logger.info("%s plugin loaded", "acme-sample")
