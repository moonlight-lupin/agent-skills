"""Contract tests for issue #12: Agent Plugins (agent-plugins.org v1.0.0) output mode.

Written by the orchestrator (Hermes) — builders must NOT modify this file.

What the converter must produce when asked for `--format agent-plugins`:
  <out>/<plugin-name>/
  ├── plugin.json          — schema-valid against tests/plugin.schema.json
  ├── skills/<name>/SKILL.md — Agent Skills-conformant frontmatter
  └── mcp.json             — schema-valid against tests/mcp.schema.json (only when
                             the source plugin has MCP servers)

Each test states the hazard it defends. Fixture plugin lives in
tests/fixtures/claude_plugin_sample/.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONVERTER = REPO_ROOT / "agent-ops" / "claude-plugin-converter" / "scripts" / "convert.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "claude_plugin_sample"
PLUGIN_SCHEMA = json.loads((Path(__file__).parent / "plugin.schema.json").read_text())
MCP_SCHEMA = json.loads((Path(__file__).parent / "mcp.schema.json").read_text())

# §5.5 name constraints, duplicated here so failures read standalone.
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]{0,62}[a-z0-9])?$")
NAME_FORBIDDEN = ("--", "..")


ANALYZE = REPO_ROOT / "agent-ops" / "claude-plugin-converter" / "scripts" / "analyze.py"


def run_convert(out_dir: Path) -> Path:
    """Run the two-phase pipeline (analyze → convert) in agent-plugins mode."""
    out_dir.mkdir(parents=True, exist_ok=True)
    analysis = out_dir / "analysis.json"
    proc = subprocess.run(
        [sys.executable, str(ANALYZE), str(FIXTURE), "-o", str(analysis)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"analyze.py failed:\n{proc.stderr}"
    proc = subprocess.run(
        [sys.executable, str(CONVERTER), str(FIXTURE),
         "--analysis", str(analysis),
         "--output", str(out_dir / "converted"),
         "--format", "agent-plugins"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"convert.py failed:\n{proc.stderr}"
    return out_dir / "converted"


def fixture_plugin_name() -> str:
    """The fixture's Claude plugin display name, for deriving the AP package name."""
    manifest = json.loads((FIXTURE / ".claude-plugin" / "plugin.json").read_text())
    return manifest["name"]


# ─── fixture sanity ──────────────────────────────────────────────────────────

def test_fixture_plugin_exists():
    """The fixture must be a real Claude plugin layout, or every later test lies."""
    assert (FIXTURE / ".claude-plugin" / "plugin.json").is_file()
    assert (FIXTURE / "skills" / "greet" / "SKILL.md").is_file()


# ─── manifest contract ───────────────────────────────────────────────────────

def test_plugin_json_exists_and_is_schema_valid():
    """plugin.json MUST validate against the canonical 1.0.0 schema (§5.2)."""
    out = run_convert(Path(__file__).parent / "_tmp_ap_out1")
    plugin_json = out / "plugin.json"
    assert plugin_json.is_file(), "agent-plugins output must have plugin.json at root"
    manifest = json.loads(plugin_json.read_text())
    jsonschema.validate(manifest, PLUGIN_SCHEMA)


def test_manifest_required_fields():
    """$schema + name are required (§5.3); name must satisfy §5.5 constraints."""
    out = run_convert(Path(__file__).parent / "_tmp_ap_out2")
    manifest = json.loads((out / "plugin.json").read_text())
    assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    name = manifest["name"]
    assert 1 <= len(name) <= 64
    assert NAME_RE.match(name), f"invalid AP name: {name!r}"
    assert not any(f in name for f in NAME_FORBIDDEN)


def test_manifest_no_unknown_top_level_fields():
    """The manifest schema is closed (§5.2) — only the 10 permitted fields."""
    out = run_convert(Path(__file__).parent / "_tmp_ap_out3")
    manifest = json.loads((out / "plugin.json").read_text())
    allowed = {"$schema", "name", "version", "description", "author",
               "homepage", "repository", "license", "keywords", "extensions"}
    unknown = set(manifest) - allowed
    assert not unknown, f"unknown manifest fields (closed schema §5.2): {unknown}"


def test_manifest_metadata_mapped_from_source():
    """Author/license/version/description should be carried from the Claude manifest."""
    out = run_convert(Path(__file__).parent / "_tmp_ap_out4")
    manifest = json.loads((out / "plugin.json").read_text())
    src = json.loads((FIXTURE / ".claude-plugin" / "plugin.json").read_text())
    if src.get("version"):
        assert manifest.get("version") == src["version"]
    if src.get("description"):
        assert manifest.get("description") == src["description"]
    if src.get("author"):
        # Claude author is a string; AP author is {name?, email?, url?} (§5.4)
        assert isinstance(manifest.get("author"), dict)
        assert src["author"] in json.dumps(manifest["author"])


# ─── skills contract ─────────────────────────────────────────────────────────

def test_skills_directory_layout():
    """Skills are immediate children of skills/, each with SKILL.md (§7.1)."""
    out = run_convert(Path(__file__).parent / "_tmp_ap_out5")
    skills_dir = out / "skills"
    assert skills_dir.is_dir(), "fixture has one skill; skills/ must exist"
    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
    names = {d.name for d in skill_dirs}
    assert "greet" in names
    for d in skill_dirs:
        assert (d / "SKILL.md").is_file(), f"skill dir {d.name} lacks SKILL.md"


def test_skill_frontmatter_conformant():
    """Agent Skills frontmatter: name + description; no Claude-only fields."""
    out = run_convert(Path(__file__).parent / "_tmp_ap_out6")
    skill_md = out / "skills" / "greet" / "SKILL.md"
    assert skill_md.is_file()
    front = skill_md.read_text().split("---")[1]
    assert "name:" in front
    assert "description:" in front
    # Claude-only fields must not leak into the portable skill
    for banned in ("disable-model-invocation", "$ARGUMENTS"):
        assert banned not in front, f"Claude-only field leaked: {banned}"


# ─── MCP contract ────────────────────────────────────────────────────────────

def test_mcp_json_schema_valid_when_mcp_present():
    """When the source has MCP servers, mcp.json must validate (§7.2)."""
    out = run_convert(Path(__file__).parent / "_tmp_ap_out7")
    mcp_json = out / "mcp.json"
    assert mcp_json.is_file(), "fixture has an MCP server; mcp.json must be emitted"
    doc = json.loads(mcp_json.read_text())
    jsonschema.validate(doc, MCP_SCHEMA)


def test_mcp_stdio_command_shape():
    """stdio command must be one token or ./relative; no shell strings (§7.2)."""
    out = run_convert(Path(__file__).parent / "_tmp_ap_out8")
    doc = json.loads((out / "mcp.json").read_text())
    servers = doc["mcpServers"]
    assert servers, "fixture declares an MCP server"
    for sname, s in servers.items():
        if s.get("type") == "stdio":
            cmd = s["command"]
            assert isinstance(cmd, str) and cmd
            assert " " not in cmd.strip() or cmd.startswith("./"), \
                f"stdio command must be one token or ./relative: {cmd!r}"
            assert not cmd.startswith(".."), f"command escapes plugin root: {cmd!r}"


# ─── no-regression ──────────────────────────────────────────────────────────

def test_default_format_still_hermes():
    """Hermes output stays the default — no --format flag means plugin.yaml."""
    out_dir = Path(__file__).parent / "_tmp_ap_out9"
    out_dir.mkdir(parents=True, exist_ok=True)
    analysis = out_dir / "analysis.json"
    proc = subprocess.run(
        [sys.executable, str(ANALYZE), str(FIXTURE), "-o", str(analysis)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    proc = subprocess.run(
        [sys.executable, str(CONVERTER), str(FIXTURE),
         "--analysis", str(analysis),
         "--output", str(out_dir / "converted")],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert (out_dir / "converted" / "plugin.yaml").is_file(), \
        "default output must remain the Hermes plugin format"
    assert not (out_dir / "converted" / "plugin.json").is_file(), \
        "default output must not emit an agent-plugins plugin.json"