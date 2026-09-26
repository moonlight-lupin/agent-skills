"""Lumen — standalone LLM wiki plugin (methodology + memory-fed curator)."""

from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent

_SKILLS = ("wiki", "curator")


def register(ctx):
    """Register Lumen skills with Hermes."""

    for name in _SKILLS:
        skill_path = PLUGIN_ROOT / "skills" / name / "SKILL.md"
        ctx.register_skill(name, skill_path)
