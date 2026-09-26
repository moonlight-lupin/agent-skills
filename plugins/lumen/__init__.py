"""Lumen — standalone LLM wiki plugin (methodology + memory-fed curator)."""

from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent

_SKILLS = ("wiki", "curator")


def _read_frontmatter(skill_path: Path) -> dict:
    """Return the SKILL.md YAML frontmatter as a dict ({} when absent or unparseable)."""

    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        import yaml

        data = yaml.safe_load(text[3:end]) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def register(ctx):
    """Register Lumen skills with Hermes."""

    for name in _SKILLS:
        skill_path = PLUGIN_ROOT / "skills" / name / "SKILL.md"
        frontmatter = _read_frontmatter(skill_path)
        description = str(frontmatter.get("description") or "")
        try:
            ctx.register_skill(name, skill_path, description=description, frontmatter=frontmatter)
        except TypeError:
            # Older Hermes contexts only accept (name, path).
            ctx.register_skill(name, skill_path)
