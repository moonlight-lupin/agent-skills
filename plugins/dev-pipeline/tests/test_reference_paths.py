"""PR-1 link-integrity guard.

Two guarantees over ``plugins/dev-pipeline/``:

1. Every file citation that CLAIMS to live in this plugin resolves to a real
   file on disk. Citations to runtime artifacts, placeholder examples, upstream
   Hermes sources, and outside skills are explicitly out of scope (see the
   skip rules below).
2. No private project identity (Pythia, Tablina, hermes-ERP, Chief of Staff,
   GVS5H, score-actuals, CoS, operator initials as policy label) appears
   anywhere in the plugin tree.
"""
import re
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]  # plugins/dev-pipeline
CITE_EXT = (".md", ".py", ".toml", ".yaml", ".yml")
SCAN_SUFFIXES = None  # scan every file; binary content decodes with errors="replace"

CITE_RE = re.compile(r"(?:`([`~\w./-]+\.(?:md|py|toml|yaml|yml))`|\]\(([\w~/.-]+\.(?:md|py|toml|yaml|yml))\))")

# Runtime/scratch artifacts a run creates — never files of the plugin.
RUNTIME_PREFIXES = (".hermes/", "BRIEF.md")

# Upstream Hermes sources that do not live in this repo: mention-only, and the
# citing sentence must name them as upstream (out of this plugin).
UPSTREAM_PREFIXES = ("tools/skill_manager_tool.py", "hermes_cli/", "agent.skill_utils")

# Outside skills (not bundled here). Citations under these names either point
# at the separately installed skill or are prose labels — not plugin files.
OUTSIDE_SKILL_DIRS = (
    "model-routing", "improve-codebase-architecture", "systematic-debugging",
    "cli-auth-fallback", "doubt-driven-development", "kanban-orchestrator",
    "context-engineering", "harness-engineering", "design-specs",
    "skill-quality-review", "council-code-review", "hermes-agent-skill-authoring",
)

# Placeholder/example paths (illustrative code, never plugin files).
# tests/test_<name>.py names in lesson references are artifacts of a TARGET
# project being reviewed (same class as src/models/user.py) — the brief
# exempts them; plugin's own tests are cited as plugins/dev-pipeline/tests/…
PLACEHOLDER_RE = re.compile(r"path/to|new_file|exact/path|<[^>]*(dir|project|path)|\bsrc/\w+/\w+\.\w+|^tests/test_\w+\.py$")

# Standard repo files that any target project owns — not this plugin's files.
STANDARD_FILES = ("pyproject.toml", "package.json")

# Plugin-context prefixes: only these CLAIM to live in the plugin. Bare code
# file names in genericised lessons (core/db.py, webhook_security.py, ...)
# illustrate a target project and are not citations.
PLUGIN_CONTEXT_RE = re.compile(
    r"^(references/|scripts/|skills/|plugins/|benchmarks/|tools/run_arm|config/|tests/test_)"
    r"|^\w[\w-]*/(references|scripts|config)/"
    r"|^goldfish/"
    r"|SKILL\.md$"
)

PRIVATE_NAMES_RE = re.compile(
    r"(?i:\bpythia\b|\btablina\b|hermes-?erp|chief[ -]of[ -]staff|\bGVS5H\b|\bscore-actuals\b"
    r"|\bpersis\b|\bargus\b|\bMH\b)|(?-i:\bCoS\b)"
)

_SKILL_SUBDIRS = None


def _skill_lookup_dirs() -> list[Path]:
    global _SKILL_SUBDIRS
    if _SKILL_SUBDIRS is None:
        dirs = []
        skills = BASE / "skills"
        for skill in sorted(skills.iterdir()):
            if skill.is_dir():
                dirs.extend([skill, skill / "references", skill / "scripts"])
        _SKILL_SUBDIRS = dirs
    return _SKILL_SUBDIRS


def _resolves(token: str, citing: Path) -> bool:
    token = token.split("#")[0].rstrip("/")
    if not any(token.endswith(e) for e in CITE_EXT):
        return True
    cands = [citing.parent / token]
    for anc in citing.parent.parents:
        if BASE not in anc.parents and anc != BASE:
            break
        cands.append(anc / token)
    cands.append(BASE / token)
    if token.startswith("plugins/"):
        # repo-rooted citation (file sits under plugins/dev-pipeline)
        cands.append(BASE.parent.parent / token)
    m_skill = re.match(r"^(\w[\w-]*)/(references|scripts|config)/", token)
    if m_skill:
        # <skill>/references/x.md names the skill explicitly
        cands.append(BASE / "skills" / m_skill.group(1) / token)
    if token.startswith("goldfish/") or token.startswith("references/goldfish/"):
        cands.append(citing.parent / "references" / token)
    cands.extend(d / token for d in _skill_lookup_dirs())
    return any(c.is_file() for c in cands)


def _citations(text: str):
    for m in CITE_RE.finditer(text):
        tok = (m.group(1) or m.group(2) or "").strip().strip("`")
        if tok:
            yield tok


def test_no_private_project_identities():
    offenders = []
    for f in sorted(BASE.rglob("*")):
        if not f.is_file() or "__pycache__" in f.parts or f.suffix in (".pyc", ".pyo"):
            continue
        if f.name == Path(__file__).name:
            continue  # the scanner itself names the pattern list
        for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if PRIVATE_NAMES_RE.search(line):
                offenders.append(f"{f.relative_to(BASE)}:{i}: {line.strip()[:120]}")
    assert not offenders, "Private project identities found:\n" + "\n".join(offenders)


def test_every_plugin_context_citation_resolves():
    offenders = []
    for f in sorted(BASE.rglob("*")):
        if not f.is_file():
            continue
        if f.name == "CHANGELOG.md":  # history text, brief allows skipping
            continue
        rel = f.relative_to(BASE).as_posix()
        for tok in _citations(f.read_text(errors="replace")):
            tok_clean = tok.strip()
            if not tok_clean:
                continue
            skip = (
                tok_clean.startswith(("/", "~"))
                or tok_clean.startswith(RUNTIME_PREFIXES)
                or tok_clean.startswith(UPSTREAM_PREFIXES)
                or tok_clean.startswith(("sdd/", ".github/", "dev-pipeline-hygiene"))
                or tok_clean.startswith(tuple(f"{d}/" for d in OUTSIDE_SKILL_DIRS))
                or tok_clean.startswith(tuple(e + "/" for e in OUTSIDE_SKILL_DIRS))
                or tok_clean in STANDARD_FILES
                or tok_clean.endswith("SKILL.md") and tok_clean == "SKILL.md"
                or bool(PLACEHOLDER_RE.search(tok_clean))
            )
            if tok_clean.startswith(OUTSIDE_SKILL_DIRS) or tok_clean.startswith(
                    tuple(e + "/" for e in OUTSIDE_SKILL_DIRS)):
                skip = True
            if tok_clean == "SKILL.md" or (tok_clean.endswith("/SKILL.md") and not tok_clean.startswith(("skills/", "plugins/"))):
                # bare SKILL.md mentions describe the concept, not a path
                skip = True
            if not PLUGIN_CONTEXT_RE.search(tok_clean):
                skip = True
            if skip:
                continue
            if not _resolves(tok_clean, f):
                offenders.append(f"{rel}: {tok_clean}")
    assert not offenders, "Dangling in-plugin citations:\n" + "\n".join(offenders)
