"""Lane pin-source guard (PR: lane source of truth and safe git).

The lanes TOML is the single source for model pins, CLI binaries, and
invocation flags. Skills and references name LANES, never models. These
tests pin that contract:

1. the default config still declares all four CLI families with four
   DISTINCT model families (lane names alone are not enough — four lanes
   could share one family and pass a name check);
2. lanes.md has no dated model-pin table and no table row carrying a model
   value that exists in the bundle config or its examples;
3. plugin Markdown and tools (except ``skills/orchestrator/config/**`` and
   CHANGELOG history) carry no model pins: no ``--model``/``-m``/
   ``--fallback-model`` literal ids (env-var and template forms are fine)
   and no versioned pin ids, matched by a generic version-shape pattern, not
   a list of today's ids. Product/role names in prose (Opus, Codex, Cursor,
   Muse, Claude Code) are allowed.
4. no fenced command block under the plugin RUNS blanket staging
   (``git add -A``, ``--all``, or ``.``): stage explicit paths; run
   ``git status --short`` and a secrets scan before committing. Prose that
   warns about the antipattern, and fenced examples that mark it as one,
   stay allowed.
"""
import re
import tomllib
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]  # plugins/dev-pipeline
CONFIG = BASE / "skills/orchestrator/config/lanes.default.toml"
CONFIG_ROOT = BASE / "skills/orchestrator/config"
LANES_MD = BASE / "skills/orchestrator/references/lanes.md"

# value forms that are NOT pins: shell vars, resolver templates, placeholders
NOT_A_PIN = re.compile(r"^[$<{]\w*|\{\w+\}")

# known historical ids, kept explicit so id renames cannot sneak past the
# shape rule
KNOWN_IDS = re.compile(
    r"(?i)gpt-6-sol|gpt-5-\d+[a-z]?|cursor-grok[-\w.]*|muse-spark-\d+(?:\.\d+)*|"
    r"glm-\d+(?:\.\d+)*[\w-]*|claude-opus-[\w-]+|claude-sonnet-[\w-]+|"
    r"claude-haiku-[\w-]+|deepseek-[\w-]+|composer-\d[\w.-]*"
)
# generic versioned-id shape ((word)-(digit)(.digit)+(-suffix)*) — the pattern
# versioned model pins almost always take, including future renames
PIN_SHAPE_RE = re.compile(r"\b[a-z][a-z0-9]{1,14}-\d+(?:\.\d+)+(?:-[a-z0-9]+)*\b")
SHAPE_ALLOW = {"dev-pipeline-lanes.v1"}
# family/model words that make a bare -m value a model selector
MODEL_WORD_RE = re.compile(r"(?i)^(?:opus|sonnet|haiku|grok|glm|gpt|muse|claude|deepseek|composer|cursor|codex)(?:$|[.\-])")

# a literal model id used as a model-selecting CLI value in a command
# (--model/--fallback-model: ANY literal is a pin; bare -m is ambiguous with
#  `python3 -m pytest`, so it needs a model-shaped value)
MODEL_VALUE_RE = re.compile(
    r"(?i)(?:--model(?:=|\s+)|--fallback-model(?:=|\s+))"
    r"(\"?)((?![$<{])[^\s\"`;&|]+\1)"
)
BARE_M_RE = re.compile(r"(?i)-m\s+\"?([\w.\-]+)\"?")

# blanket staging inside fenced command blocks; 'git add' is matched only at
# command position (start or after &&, ;, |, ( ) so warnings in prose pass
GIT_ADD_A_RE = re.compile(
    r"(?:^|[;&|(]\s*|&&\s*)git(?:\s+-C\s+\S+)?\s+add\s+(?:-{1,2}[\w-]+\s+)*(-A|--all|\.(?:\s|$))"
)
ANTIPATTERN_ALLOW = re.compile(r"avoid|instead of|rather than|never\s+`?git add", re.I)
DATED_TABLE_RE = re.compile(
    r"[Aa]s of \d{4}-\d{2}-\d{2}|(?:[Pp]inned|[Dd]ated|[Uu]pdated) (?:by .{0,40} )?(?:19|20)\d\d-\d{2}-\d{2}"
)


def _bundled_model_values() -> set[str]:
    values = set()
    for p in sorted(CONFIG_ROOT.rglob("*.toml")):
        data = tomllib.loads(p.read_text())
        for spec in data.get("lanes", {}).values():
            m = spec.get("model")
            if isinstance(m, str) and m.strip():
                values.add(m.strip())
    return values


def _scan_targets():
    """Markdown anywhere under the plugin + the tools scripts. The config
    tree is the declared pin home; CHANGELOG is history."""
    for f in sorted(BASE.rglob("*")):
        if not f.is_file() or f.name in ("CHANGELOG.md", Path(__file__).name):
            continue
        if CONFIG_ROOT in f.parents or f == CONFIG:
            continue
        if f.suffix == ".md" or (f.suffix == ".py" and "tools" in f.parts):
            yield f


def test_default_config_declares_four_cli_families_with_distinct_model_families():
    data = tomllib.loads(CONFIG.read_text())
    lanes = data["lanes"]
    for lane in ("claude", "codex", "cursor", "muse"):
        assert lane in lanes, f"default config lost the {lane} lane"
        assert "family" in lanes[lane], f"lane {lane} lost its family"
        assert "via" in lanes[lane], f"lane {lane} lost its dispatch type"
    families = {lanes[l]["family"] for l in ("claude", "codex", "cursor", "muse")}
    assert len(families) == 4, \
        f"the four CLI lanes must map to four DISTINCT model families, got {families}"
    reviewers = data["roles"]["reviewers"]
    for lane in ("claude", "codex", "cursor", "muse"):
        assert lane in reviewers, f"reviewers role lost the {lane} lane"


def test_lanes_md_has_no_dated_pin_table():
    text = LANES_MD.read_text()
    assert not DATED_TABLE_RE.search(text), "lanes.md carries a dated pin table"
    for line in text.splitlines():
        if line.startswith("|") and "---" not in line:
            for mv in _bundled_model_values():
                assert mv not in line, \
                    f"lanes.md table row carries model value {mv!r}: {line.strip()[:120]}"


def test_markdown_and_tools_carry_no_model_pins():
    offenders = []
    for f in _scan_targets():
        for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            for m in MODEL_VALUE_RE.finditer(line):
                if NOT_A_PIN.search(m.group(2)):
                    continue
                tail = line[m.end():][:24]
                if tail.lstrip(" ").startswith(("is ", "was ", "required", "must")):
                    continue  # prose about the flag, not a command
                offenders.append(f"{f.relative_to(BASE)}:{i}: literal model value {m.group(2)!r}")
            for m in BARE_M_RE.finditer(line):
                v = m.group(1)
                if NOT_A_PIN.search(v):
                    continue
                if KNOWN_IDS.search(v) or PIN_SHAPE_RE.fullmatch(v) or MODEL_WORD_RE.search(v):
                    offenders.append(f"{f.relative_to(BASE)}:{i}: -m model value {v!r}")
            for m in KNOWN_IDS.finditer(line):
                offenders.append(f"{f.relative_to(BASE)}:{i}: known pin id {m.group(0)!r}")
            for m in PIN_SHAPE_RE.finditer(line):
                if m.group(0).lower() in SHAPE_ALLOW:
                    continue
                if re.search(r"backend|library|requirement|pip install", line, re.I):
                    continue  # library/package versions, not model pins
                offenders.append(f"{f.relative_to(BASE)}:{i}: versioned pin id {m.group(0)!r}")
    assert not offenders, "Model pins leaked into Markdown/tools:\n" + "\n".join(offenders)


def test_no_blanket_staging_in_command_blocks():
    offenders = []
    for f in sorted((BASE / "skills").rglob("*.md")):
        if "config" in f.parts:
            continue
        in_fence = False
        for ln, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence:
                continue
            m = GIT_ADD_A_RE.search(line)
            if m and not ANTIPATTERN_ALLOW.search(line):
                offenders.append(f"{f.relative_to(BASE)}:{ln}: {line.strip()[:100]}")
    assert not offenders, "Blanket staging inside command blocks:\n" + "\n".join(offenders)
