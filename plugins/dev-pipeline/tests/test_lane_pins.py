"""Lane pin-source guard (PR: lane source of truth and safe git).

The bundled default TOML is the single source for model names, CLI binaries,
and invocation flags. Skills and references name LANES, never models. These
tests pin that contract:

1. the default config still declares all four CLI families;
2. lanes.md has no dated model-pin table and no model identifier that exists
   as a ``model =`` value in the example config;
3. plugin Markdown (except ``config/**`` and CHANGELOG history) carries no
   model pin strings — no ``--model <literal id>`` commands and no
   versioned pin ids. Product and role names in prose (Opus, Codex, Cursor,
   Muse, Claude Code) are allowed.
4. no command block under the plugin RUNS ``git add -A``: stage explicit
   paths. Prose that names the antipattern as a warning stays allowed.
"""
import re
import tomllib
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]  # plugins/dev-pipeline
CONFIG = BASE / "skills/orchestrator/config/lanes.default.toml"
EXAMPLES = BASE / "skills/orchestrator/config/examples"
LANES_MD = BASE / "skills/orchestrator/references/lanes.md"

# pin-shaped model ids anywhere in prose or commands (versioned ids are what
# the single-source rule exists to prevent)
PIN_ID_RE = re.compile(
    r"(?i)cursor-grok[-\w.]*|muse-spark-\d+(?:\.\d+)*|gpt-6-sol|"
    r"glm-\d+\.\d+|claude-opus-[\w-]+|claude-sonnet-[\w-]+"
)
# a literal model id used as a --model value in a command line (--model "$X" is fine)
MODEL_FLAG_RE = re.compile(r'--model\s+"?(opus|sonnet|haiku|grok|gpt|muse|glm|claude|codex|cursor)', re.I)
DATED_TABLE_RE = re.compile(r"as of \d{4}-\d{2}-\d{2}|(?:pinned|dated|updated) (?:by .{0,40} )?(?:19|20)\d\d-\d{2}-\d{2}")
# a command block that stages everything
GIT_ADD_A_RE = re.compile(r"^\s*git add -A\b", re.M)


def _bundled_model_values() -> set[str]:
    values = set()
    for p in [CONFIG, *EXAMPLES.glob("*.toml")]:
        data = tomllib.loads(p.read_text())
        for spec in data.get("lanes", {}).values():
            m = spec.get("model")
            if isinstance(m, str) and m.strip():
                values.add(m.strip())
    return values


def test_default_config_declares_all_four_cli_families():
    lanes = tomllib.loads(CONFIG.read_text())["lanes"]
    for lane in ("claude", "codex", "cursor", "muse"):
        assert lane in lanes, f"default config lost the {lane} lane"
    for lane in ("claude", "codex", "cursor", "muse"):
        assert lane in tomllib.loads(CONFIG.read_text())["roles"]["reviewers"], \
            f"reviewers role lost the {lane} lane"


def test_lanes_md_has_no_dated_pin_table():
    text = LANES_MD.read_text()
    assert not DATED_TABLE_RE.search(text), "lanes.md carries a dated pin table"
    model_values = _bundled_model_values()
    for line in text.splitlines():
        if line.startswith("|") and "---" not in line:
            for mv in model_values:
                assert mv not in line, \
                    f"lanes.md table row carries model value {mv!r}: {line.strip()[:120]}"


def test_markdown_carries_no_model_pins():
    offenders = []
    for f in sorted((BASE / "skills").rglob("*.md")):
        if "config" in f.parent.parts:  # config/** is the declared pin home
            continue
        for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if MODEL_FLAG_RE.search(line):
                offenders.append(f"{f.relative_to(BASE)}:{i}: literal --model id")
            for m in PIN_ID_RE.finditer(line):
                offenders.append(f"{f.relative_to(BASE)}:{i}: pin id {m.group(0)!r}")
    assert not offenders, "Model pins leaked into Markdown:\n" + "\n".join(offenders)


def test_no_git_add_dash_A_command_blocks():
    offenders = []
    for f in sorted((BASE / "skills").rglob("*.md")):
        if "config" in f.parent.parts:
            continue
        for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if GIT_ADD_A_RE.search(line):
                offenders.append(f"{f.relative_to(BASE)}:{i}: {line.strip()[:100]}")
    assert not offenders, "Instructional 'git add -A' commands:\n" + "\n".join(offenders)
