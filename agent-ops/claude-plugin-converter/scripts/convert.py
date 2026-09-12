#!/usr/bin/env python3
"""Phase 2: Convert a Claude Code plugin into a Hermes or Agent Plugins package.

Takes the analysis JSON (from analyze.py) + plugin directory.
Default `--format hermes` is unchanged. `--format agent-plugins` emits the
vendor-neutral layout from https://agent-plugins.org/ (v1.0.0).

Usage:
    python3 convert.py <plugin_dir> --analysis <analysis.json> --output <output_dir>
    python3 convert.py <plugin_dir> --analysis <analysis.json> --output <output_dir> \\
        --format agent-plugins
"""

import argparse
import ipaddress
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path, PurePosixPath
from textwrap import dedent
from urllib.parse import urlparse


# ── Path safety ─────────────────────────────────────────────────────────

_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def safe_name(name: str, fallback: str = "unnamed") -> str:
    """Sanitize a plugin/skill/agent name for use as a directory name.

    Strips path separators, null bytes, and other dangerous characters.
    Prevents path traversal (e.g. '../../etc' → 'etc').
    Returns the fallback if the result is empty or all-dots.
    """
    if not name:
        return fallback
    cleaned = _SAFE_NAME_RE.sub("-", name.strip())
    cleaned = cleaned.lstrip(".")
    cleaned = re.sub(r"(?<!\w)\.+(?!\w)", "", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    cleaned = cleaned.strip("-")
    if not cleaned or cleaned in (".", ".."):
        return fallback
    return cleaned[:64]


# ── Helpers ─────────────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse simple YAML frontmatter. Returns (frontmatter, body)."""
    if not content.startswith("---"):
        return {}, content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content
    fm_text = parts[1].strip()
    body = parts[2]
    fm = {}
    for line in fm_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm, body


_YAML_PLAIN_FORBIDDEN = frozenset(":#{}[],&!*|>'\"%@`\n\r\t\\")
_YAML_RESERVED_PLAIN = frozenset({
    "y", "n", "yes", "no", "true", "false", "on", "off", "null", "nil", "~",
})


def _yaml_plain_ok(s: str) -> bool:
    if not s or s.strip() != s:
        return False
    if s.lower() in _YAML_RESERVED_PLAIN:
        return False
    if s[0] in "?:[]{}#&*!|>'\"%@`+0123456789":
        return False
    if s.startswith("-") and not s.startswith("--"):
        return False
    if any(c in _YAML_PLAIN_FORBIDDEN for c in s):
        return False
    return not any(ord(c) in (0x85, 0x2028, 0x2029) for c in s)


def yaml_quote(s: str) -> str:
    """Quote a string for YAML 1.2. Bare when it is a safe plain scalar."""
    if not isinstance(s, str):
        raise ValueError(f"yaml_quote expects str, got {type(s).__name__}")
    if _yaml_plain_ok(s):
        return s
    dumped = json.dumps(s, ensure_ascii=False)
    return (
        dumped.replace("\u0085", "\\u0085")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


# ── Skill conversion ────────────────────────────────────────────────────

def convert_skill(skill_info: dict, source_plugin_dir: Path, dest_skills_dir: Path,
                  flavour: str = "hermes") -> dict:
    """Convert a Claude skill. Returns {name, path, issues}.

    flavour='hermes' keeps directory names via safe_name and rewrites
    ${CLAUDE_PLUGIN_ROOT} to '..'. flavour='agent-plugins' slugifies the
    skill dir + frontmatter name and rewrites the placeholder to ${PLUGIN_ROOT}.
    """
    source_skill_dir = Path(skill_info["path"])
    raw_name = skill_info.get("name", source_skill_dir.name)
    if flavour == "agent-plugins":
        skill_name = ap_skill_slug(skill_info)
    else:
        skill_name = safe_name(raw_name, source_skill_dir.name)

    dest_skill_dir = dest_skills_dir / skill_name
    dest_skill_dir.mkdir(parents=True, exist_ok=True)

    source_skill_md = source_skill_dir / "SKILL.md"
    if not source_skill_md.exists():
        return {"name": skill_name, "path": str(dest_skill_dir), "issues": ["Source SKILL.md not found"]}

    content = source_skill_md.read_text(encoding="utf-8", errors="replace")
    orig_fm, body = parse_frontmatter(content)
    desc = orig_fm.get("description", "")

    new_fm_lines = [
        f"name: {skill_name}",
        f"description: {yaml_quote(desc)}",
    ]

    new_body = body
    if "$ARGUMENTS" in new_body:
        new_body = new_body.replace(
            "$ARGUMENTS",
            "<the user's request — read their message for the argument>",
        )

    if flavour == "agent-plugins":
        new_body = new_body.replace("${CLAUDE_PLUGIN_ROOT}", "${PLUGIN_ROOT}")
    else:
        new_body = new_body.replace("${CLAUDE_PLUGIN_ROOT}", "..")
        new_body = re.sub(
            r"`\.\./([^`]+)`\]\((\.\./[^)]+)\)",
            r"`\1`](\2)",
            new_body,
        )

    new_content = "---\n" + "\n".join(new_fm_lines) + "\n---\n" + new_body
    (dest_skill_dir / "SKILL.md").write_text(new_content, encoding="utf-8")

    for subdir in ("scripts", "references", "assets", "templates"):
        src = source_skill_dir / subdir
        if src.exists() and src.is_dir():
            shutil.copytree(src, dest_skill_dir / subdir, dirs_exist_ok=True)

    issues = []
    if skill_info.get("uses_arguments"):
        issues.append("$ARGUMENTS rewritten to placeholder text — review")
    if skill_info.get("has_disable_invocation"):
        issues.append("disable-model-invocation dropped — Hermes skills are always model-invoked")
    if flavour == "agent-plugins" and not str(desc).strip():
        issues.append("empty description — Agent Plugins discovery requires a non-empty description")

    return {"name": skill_name, "path": str(dest_skill_dir), "issues": issues}


# ── Agent → Delegation skill conversion ─────────────────────────────────

def convert_agent(agent_info: dict, dest_skills_dir: Path) -> dict:
    """Convert a Claude agent definition to a Hermes delegation skill."""
    agent_name = safe_name(agent_info.get("name", "unnamed-agent"), "unnamed-agent")
    source_path = Path(agent_info["path"])
    
    content = source_path.read_text(encoding="utf-8", errors="replace")
    orig_fm, body = parse_frontmatter(content)

    description = orig_fm.get("description", f"Delegation skill for {agent_name}")
    
    # Build the delegation skill
    skill_content = f"""---
name: {agent_name}
description: {yaml_quote(description)}
---

# {agent_name} (Converted from Claude Agent)

When the user's task matches this agent's specialty, delegate it:

1. Call `delegate_task` with:
   - `goal`: "{description}"
   - `context`: The full system prompt below — pass it as context so the subagent follows these instructions.

2. Do not attempt the task yourself — delegate it.

## Original Agent System Prompt

{body.strip()}

## Original Agent Config (for reference)
- Model: {orig_fm.get('model', 'unspecified')}
- Effort: {orig_fm.get('effort', 'unspecified')}
- MaxTurns: {orig_fm.get('maxTurns', 'unspecified')}
- Tools: {orig_fm.get('tools', 'all')}
- DisallowedTools: {orig_fm.get('disallowedTools', 'none')}
"""
    
    dest_skill_dir = dest_skills_dir / agent_name
    dest_skill_dir.mkdir(parents=True, exist_ok=True)
    (dest_skill_dir / "SKILL.md").write_text(skill_content, encoding="utf-8")
    
    return {"name": agent_name, "path": str(dest_skill_dir), "issues": ["Agent converted to delegation skill — behavior may differ"]}


# ── Hook conversion ─────────────────────────────────────────────────────

def convert_hooks(hooks_list: list, plugin_name: str, plugin_dir: Path) -> tuple[str, list[dict]]:
    """Convert Claude hooks to Hermes plugin hook callbacks. Returns (hooks_py_code, hook_infos)."""
    hook_infos = []
    callbacks = []
    
    for i, hook in enumerate(hooks_list):
        if hook["convertibility"] == "no":
            hook_infos.append({
                "claude_event": hook["claude_event"],
                "status": "skipped",
                "reason": hook["reason"],
            })
            continue
        
        hermes_event = hook.get("hermes_event")
        if not hermes_event:
            hook_infos.append({
                "claude_event": hook["claude_event"],
                "status": "skipped",
                "reason": "No Hermes event mapping",
            })
            continue
        
        claude_type = hook.get("hook_type", "command")
        command = hook.get("command", "")
        matcher = hook.get("matcher", "")
        
        cb_name = f"_on_{hermes_event}_{i}"
        
        # Generate callback based on hook type
        if claude_type == "command":
            # Shell command hook
            escaped_cmd = command.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_dir))
            
            # Build matcher filter if present
            matcher_check = ""
            if matcher and hermes_event in ("pre_tool_call", "post_tool_call"):
                # matcher is a regex-like pattern e.g. "Write|Edit"
                patterns = matcher.split("|")
                patterns_py = ", ".join(f'"{p.strip()}"' for p in patterns)
                matcher_check = f"""
    # Only fire for matching tools: {matcher}
    if tool_name not in ({patterns_py}):
        return"""
            
            callback_code = f"""
_CMD_{i} = {escaped_cmd!r}

def {cb_name}(tool_name=None, args=None, result=None, task_id="", **kwargs):
    \"\"\"Converted from Claude hook: {hook['claude_event']} ({claude_type})\"\"\"
    tool_name = tool_name or ""
{matcher_check}
    import subprocess
    try:
        proc = subprocess.run(
            _CMD_{i},
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Hook {cb_name} failed: %s", e)
"""
            if hermes_event == "pre_tool_call" and matcher:
                callback_code += """
    # Pre-tool hooks can block — check if command failed
    if proc.returncode != 0:
        return {"action": "block", "message": f"Hook blocked: {proc.stderr[:200]}"}
"""
            callbacks.append(callback_code)
            
        elif claude_type == "http":
            url = command  # For http type, "command" is the URL
            callback_code = f"""
def {cb_name}(**kwargs):
    \"\"\"Converted from Claude hook: {hook['claude_event']} (http)\"\"\"
    import httpx
    try:
        httpx.post("{url}", json=kwargs, timeout=10)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Hook {cb_name} failed: %s", e)
"""
            callbacks.append(callback_code)
            
        elif claude_type == "mcp_tool":
            callback_code = f"""
def {cb_name}(**kwargs):
    \"\"\"Converted from Claude hook: {hook['claude_event']} (mcp_tool)\"\"\"
    # TODO: Manual implementation needed
    # Original command: {command}
    # Hermes equivalent: use ctx.dispatch_tool() from within register()
    # but hooks don't have ctx access — need a different pattern
    import logging
    logging.getLogger(__name__).info("Hook {cb_name} fired (mcp_tool — manual implementation needed)")
"""
            callbacks.append(callback_code)
        
        hook_infos.append({
            "claude_event": hook["claude_event"],
            "hermes_event": hermes_event,
            "status": "converted" if claude_type in ("command", "http") else "partial",
            "callback_name": cb_name,
            "reason": hook.get("reason", ""),
        })
    
    # Assemble hooks.py
    hooks_py = '"""Hook callbacks converted from Claude plugin hooks."""\n\nimport logging\n\nlogger = logging.getLogger(__name__)\n'
    for cb in callbacks:
        hooks_py += "\n" + cb
    
    return hooks_py, hook_infos


# ── MCP config conversion ──────────────────────────────────────────────

def convert_mcp(mcp_list: list, plugin_dir: Path) -> tuple[str, list[dict]]:
    """Convert MCP server configs. Returns (yaml_snippet, infos)."""
    if not mcp_list:
        return "", []
    
    lines = ["# Merge these into ~/.hermes/config.yaml under mcp_servers:", ""]
    infos = []
    
    for srv in mcp_list:
        name = srv["name"]
        command = srv["command"].replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_dir))
        args = [
            a.replace("${CLAUDE_PLUGIN_ROOT}", str(plugin_dir)) if isinstance(a, str) else a
            for a in srv.get("args", [])
        ]
        env_vars = srv.get("env_vars", [])
        
        lines.append(f"{name}:")
        lines.append(f"  command: {yaml_quote(command)}")
        if args:
            quoted = []
            for a in args:
                if not isinstance(a, str):
                    raise ValueError(
                        f"args entries must be strings, got {type(a).__name__}"
                    )
                quoted.append(yaml_quote(a))
            args_str = ", ".join(quoted)
            lines.append(f"  args: [{args_str}]")
        if env_vars:
            lines.append("  env:")
            for ev in env_vars:
                lines.append(f"    {ev}: \"{ev}_VALUE\"  # Set actual value")
        lines.append("")
        
        infos.append({"name": name, "command": command, "status": "converted"})
    
    return "\n".join(lines), infos


# ── Command conversion ──────────────────────────────────────────────────

def convert_commands(cmd_list: list) -> tuple[list[dict], str]:
    """Convert Claude commands to Hermes slash command registrations.
    Returns (command_infos, register_code)."""
    if not cmd_list:
        return [], ""
    
    infos = []
    register_lines = []
    
    for cmd in cmd_list:
        name = cmd["name"]
        content = Path(cmd["path"]).read_text(encoding="utf-8", errors="replace")
        
        # Strip frontmatter if present
        if content.startswith("---"):
            parts = content.split("---", 2)
            content = parts[2] if len(parts) >= 3 else content
        
        # Escape for Python string
        escaped = content.replace('"""', '\\"\\"\\"').replace("\\", "\\\\")
        
        register_lines.append(f'''
    # /{name} — converted from Claude command
    ctx.register_command(
        "{name}",
        lambda raw, _content={escaped!r}: _content,
        description="Converted from Claude command: {name}",
    )''')
        
        infos.append({"name": name, "status": "converted", "note": "Returns markdown content as response"})
    
    register_code = "\n".join(register_lines)
    return infos, register_code


# ── Plugin manifest conversion ─────────────────────────────────────────

def generate_plugin_yaml(manifest: dict, analysis: dict) -> str:
    """Generate Hermes plugin.yaml from Claude plugin.json manifest."""
    name = manifest.get("name", "unnamed-plugin")
    version = manifest.get("version", "1.0.0")
    description = manifest.get("description", "")
    author = manifest.get("author", {})
    if isinstance(author, dict):
        author = author.get("name", "")
    
    provides_tools = []
    provides_hooks = []
    
    # Collect tool names from MCP servers
    for srv in analysis["components"].get("mcp_servers", []):
        provides_tools.append(f"mcp__{srv['name']}")
    
    # Collect hook names
    for hook in analysis["components"].get("hooks", []):
        if hook.get("hermes_event") and hook["convertibility"] != "no":
            provides_hooks.append(hook["hermes_event"])
    
    # Collect env requirements
    requires_env = []
    for srv in analysis["components"].get("mcp_servers", []):
        for ev in srv.get("env_vars", []):
            if ev not in requires_env:
                requires_env.append(ev)
    
    lines = [
        f"name: {name}",
        f"version: {version}",
        f"description: {yaml_quote(description)}",
    ]
    if author:
        lines.append(f"author: {yaml_quote(author)}")
    
    if provides_tools:
        lines.append("provides_tools:")
        for t in provides_tools:
            lines.append(f"  - {t}")
    
    if provides_hooks:
        # Deduplicate
        unique_hooks = list(dict.fromkeys(provides_hooks))
        lines.append("provides_hooks:")
        for h in unique_hooks:
            lines.append(f"  - {h}")
    
    if requires_env:
        lines.append("requires_env:")
        for ev in requires_env:
            lines.append(f"  - {ev}")
    
    return "\n".join(lines) + "\n"


# ── __init__.py generation ──────────────────────────────────────────────

def generate_init_py(plugin_name: str, analysis: dict, hooks_code_exists: bool, 
                      commands_register_code: str, skill_names: list,
                      hook_callback_names: dict = None) -> str:
    """Generate __init__.py for the Hermes plugin.
    
    hook_callback_names: {event_name: [callback_name, ...]} from convert_hooks()
    """
    
    has_hooks = bool(analysis["components"].get("hooks"))
    
    lines = [
        f'"""{plugin_name} — converted from Claude Code plugin."""',
        "",
        "import logging",
        "from pathlib import Path",
        "",
    ]
    
    if has_hooks:
        lines += [
            "from . import hooks as _hooks  # noqa: F401",
            "",
        ]
    
    lines += [
        "logger = logging.getLogger(__name__)",
        "",
        "",
        "def register(ctx):",
        '    """Wire schemas to handlers and register hooks/skills."""',
    ]
    
    # Register skills (bundled)
    if skill_names:
        lines.append("    # ── Bundled skills ──")
        lines.append("    skills_dir = Path(__file__).parent / \"skills\"")
        lines.append("    for child in sorted(skills_dir.iterdir()):")
        lines.append("        skill_md = child / \"SKILL.md\"")
        lines.append("        if child.is_dir() and skill_md.exists():")
        lines.append("            ctx.register_skill(child.name, skill_md)")
        lines.append("")
    
    # Register hooks
    hook_callback_names = hook_callback_names or {}
    if hook_callback_names:
        lines.append("    # ── Hooks (converted from Claude plugin) ──")
        for event, cb_names in sorted(hook_callback_names.items()):
            for cb in cb_names:
                lines.append(f"    ctx.register_hook(\"{event}\", _hooks.{cb})")
        lines.append("")
    
    # Register commands
    if commands_register_code:
        lines.append("    # ── Slash commands (converted from Claude commands) ──")
        lines.append(commands_register_code)
        lines.append("")
    
    lines.append("    logger.info(\"%s plugin loaded\", \"" + plugin_name + "\")")
    
    return "\n".join(lines) + "\n"


# ── Manual steps ────────────────────────────────────────────────────────

def generate_manual_steps(analysis: dict, plugin_name: str) -> str:
    """Generate MANUAL_STEPS.md listing what needs manual attention."""
    lines = [
        f"# Manual Steps for {plugin_name}",
        "",
        "These items could not be fully automated. Please review and handle manually.",
        "",
    ]
    
    components = analysis["components"]
    
    # Skills with issues
    for skill in components.get("skills", []):
        if skill.get("issues"):
            lines.append(f"## Skill: {skill['name']}")
            for issue in skill["issues"]:
                lines.append(f"- {issue}")
            lines.append("")
    
    # Agents (always need manual review)
    for agent in components.get("agents", []):
        lines.append(f"## Agent: {agent['name']}")
        lines.append(f"- Converted to delegation skill, but behavior may differ")
        lines.append(f"- Original model: {agent.get('model', 'unspecified')}")
        lines.append(f"- Original maxTurns: {agent.get('maxTurns', 'unspecified')}")
        if agent.get("tools"):
            lines.append(f"- Restricted tools: {agent['tools']}")
        if agent.get("disallowedTools"):
            lines.append(f"- Disallowed tools: {agent['disallowedTools']}")
        lines.append("")
    
    # Hooks that were skipped
    for hook in components.get("hooks", []):
        if hook.get("convertibility") == "no" or hook.get("status") == "skipped":
            lines.append(f"## Hook: {hook.get('claude_event', 'unknown')}")
            lines.append(f"- {hook.get('reason', 'No Hermes equivalent')}")
            if hook.get("command"):
                lines.append(f"- Original command: `{hook['command'][:100]}`")
            lines.append("")
    
    # Prompt/agent type hooks
    for hook in components.get("hooks", []):
        if hook.get("hook_type") in ("prompt", "agent"):
            lines.append(f"## Hook type '{hook['hook_type']}': {hook.get('claude_event', '')}")
            lines.append(f"- No Hermes equivalent for '{hook['hook_type']}' hook type")
            lines.append(f"- Consider implementing manually via plugin hook + one-shot agent")
            lines.append("")
    
    # LSP servers
    for lsp in components.get("lsp_servers", []):
        lines.append(f"## LSP Server: {lsp['name']}")
        lines.append("- Hermes has no LSP integration — skipped")
        lines.append("")
    
    # Monitors
    for mon in components.get("monitors", []):
        lines.append(f"## Monitor: {mon['name']}")
        lines.append("- Convert to Hermes cron job manually")
        lines.append("- Use: `hermes cron create <schedule>` or the `cronjob` tool")
        lines.append("")
    
    # MCP env vars
    for srv in components.get("mcp_servers", []):
        if srv.get("env_vars"):
            lines.append(f"## MCP Server: {srv['name']} — Environment Variables")
            for ev in srv["env_vars"]:
                lines.append(f"- Set `{ev}` in `~/.hermes/.env`")
            lines.append("")
    
    if len(lines) <= 3:
        lines.append("✅ No manual steps required — everything converted cleanly!")
    
    return "\n".join(lines)


# ── Conversion report ──────────────────────────────────────────────────

def generate_report(analysis: dict, conversion_results: dict, plugin_name: str) -> str:
    """Generate the full CONVERSION_REPORT.md."""
    s = analysis["summary"]
    lines = [
        f"# Conversion Report: {plugin_name}",
        "",
        f"**Source:** Claude Code plugin",
        f"**Target:** Hermes plugin",
        "",
        "## Summary",
        "",
        f"| Status | Count |",
        f"|--------|-------|",
        f"| ✅ Converted | {s['convertible']} |",
        f"| ⚠️ Partial | {s['partial']} |",
        f"| ⏭️ Skipped | {s['skipped']} |",
        f"| **Total** | {s['total']} |",
        "",
        "## Conversion Results",
        "",
    ]
    
    # Skills
    if "skills" in conversion_results:
        lines.append("### Skills")
        lines.append("")
        lines.append("| Skill | Status | Issues |")
        lines.append("|-------|--------|--------|")
        for sk in conversion_results["skills"]:
            status = "✅" if not sk.get("issues") else "⚠️"
            issues = "; ".join(sk.get("issues", [])) or "None"
            lines.append(f"| {sk['name']} | {status} | {issues} |")
        lines.append("")
    
    # Agents
    if "agents" in conversion_results:
        lines.append("### Agents → Delegation Skills")
        lines.append("")
        lines.append("| Agent | Status |")
        lines.append("|-------|--------|")
        for ag in conversion_results["agents"]:
            lines.append(f"| {ag['name']} | ⚠️ Converted (behavior may differ) |")
        lines.append("")
    
    # Hooks
    if "hooks" in conversion_results:
        lines.append("### Hooks")
        lines.append("")
        lines.append("| Claude Event | Hermes Event | Status |")
        lines.append("|-------------|-------------|--------|")
        for hk in conversion_results["hooks"]:
            status_map = {"converted": "✅", "skipped": "⏭️", "partial": "⚠️"}
            status = status_map.get(hk.get("status", ""), "?")
            hermes_ev = hk.get("hermes_event", "—")
            lines.append(f"| {hk['claude_event']} | {hermes_ev} | {status} |")
        lines.append("")
    
    # MCP
    if "mcp_servers" in conversion_results:
        lines.append("### MCP Servers")
        lines.append("")
        lines.append("| Server | Status |")
        lines.append("|--------|--------|")
        for srv in conversion_results["mcp_servers"]:
            lines.append(f"| {srv['name']} | ✅ Config generated |")
        lines.append("")
    
    # Commands
    if "commands" in conversion_results:
        lines.append("### Commands")
        lines.append("")
        lines.append("| Command | Status |")
        lines.append("|---------|--------|")
        for cmd in conversion_results["commands"]:
            lines.append(f"| {cmd['name']} | ✅ Slash command registered |")
        lines.append("")
    
    # LSP
    if analysis["components"].get("lsp_servers"):
        lines.append("### LSP Servers (Skipped)")
        lines.append("")
        for lsp in analysis["components"]["lsp_servers"]:
            lines.append(f"- {lsp['name']}: ⏭️ No Hermes LSP equivalent")
        lines.append("")
    
    lines.append("## Next Steps")
    lines.append("")
    lines.append("1. Review `MANUAL_STEPS.md` for items needing manual attention")
    lines.append("2. Copy this plugin to `~/.hermes/plugins/`")
    lines.append("3. Enable: `hermes plugins enable " + plugin_name + "`")
    lines.append("4. If MCP servers exist, merge `mcp_config.yaml` into `~/.hermes/config.yaml`")
    lines.append("5. Restart your session (`/reset` in CLI or `/restart` in gateway)")
    
    return "\n".join(lines)


# ── Agent Plugins (agent-plugins.org v1.0.0) ───────────────────────────

PLUGIN_SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
MCP_SCHEMA_URL = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
_AP_NAME_RE = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")
_AP_PLUGIN_FIELDS = {
    "$schema", "name", "version", "description", "author",
    "homepage", "repository", "license", "keywords", "extensions",
}
_CLAUDE_PLUGIN_ROOT = "${CLAUDE_PLUGIN_ROOT}"
_AP_PLUGIN_ROOT = "${PLUGIN_ROOT}"
_AP_OWNED_OUTPUT_FILES = frozenset({
    "plugin.json",
    "mcp.json",
    "conversion_results.json",
    "CONVERSION_REPORT.md",
})
_AP_OWNED_OUTPUT_DIRS = frozenset({"skills", "agents"})


def _assert_output_disjoint_from_source(plugin_dir: Path, output_dir: Path) -> None:
    src = plugin_dir.resolve()
    dest = output_dir.resolve()
    if src == dest or src in dest.parents or dest in src.parents:
        raise ValueError("output directory overlaps source directory")


def _ap_dest_looks_converter_owned(dest: Path) -> bool:
    """True when dest is empty or already an Agent Plugins package we wrote."""
    if not dest.exists():
        return True
    if not dest.is_dir():
        return False
    try:
        entries = list(dest.iterdir())
    except OSError:
        return False
    if not entries:
        return True
    plugin_json = dest / "plugin.json"
    if not plugin_json.is_file():
        return False
    try:
        data = json.loads(plugin_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return isinstance(data, dict) and bool(data.get("$schema"))


def _assert_ap_dest_is_writable(dest: Path) -> None:
    if dest.exists() and not _ap_dest_looks_converter_owned(dest):
        raise ValueError("pick a fresh output directory")


def _is_dest_or_contains_dest(child: Path, dest: Path) -> bool:
    """True if child is dest, or dest lives inside child (copy would nest dest)."""
    try:
        c = child.resolve()
        d = dest.resolve()
    except OSError:
        return False
    if c == d:
        return True
    try:
        d.relative_to(c)
        return True
    except ValueError:
        return False


def _clear_ap_owned_outputs(dest: Path) -> None:
    """Remove converter-owned files/dirs so a rerun cannot ship stale output."""
    for name in _AP_OWNED_OUTPUT_FILES:
        p = dest / name
        if p.is_file() or p.is_symlink():
            p.unlink()
    for name in _AP_OWNED_OUTPUT_DIRS:
        p = dest / name
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        elif p.is_file() or p.is_symlink():
            p.unlink()


def ap_slug(name: str, fallback: str = "plugin") -> str:
    """Derive an Agent Plugins §5.5 name from a Claude manifest name."""
    s = (name or "").lower()
    s = re.sub(r"[_\s]+", "-", s)
    s = re.sub(r"[^a-z0-9.-]", "", s)
    while "--" in s:
        s = s.replace("--", "-")
    while ".." in s:
        s = s.replace("..", ".")
    s = re.sub(r"^[^a-z0-9]+", "", s)
    s = re.sub(r"[^a-z0-9]+$", "", s)
    if not s:
        return fallback
    s = s[:64]
    s = re.sub(r"[^a-z0-9]+$", "", s)
    if not s or not _AP_NAME_RE.match(s):
        return fallback
    return s


def ap_skill_slug(skill_info: dict) -> str:
    """Agent Plugins skill directory / frontmatter name from analysis info."""
    source_skill_dir = Path(skill_info.get("path") or ".")
    raw_name = skill_info.get("name", source_skill_dir.name)
    return ap_slug(str(raw_name), ap_slug(source_skill_dir.name, "skill"))


def _raise_on_ap_skill_slug_collision(skills: list[dict]) -> None:
    """Reject two source skills that slug to the same Agent Plugins name."""
    by_slug: dict[str, list[str]] = {}
    for sk in skills:
        slug = ap_skill_slug(sk)
        source = str(sk.get("name") or Path(sk.get("path") or "unnamed").name)
        by_slug.setdefault(slug, []).append(source)
    for slug, sources in by_slug.items():
        if len(sources) > 1:
            raise ValueError(
                "duplicate skill name after slugification: "
                f"{slug} (sources: {', '.join(sources)})"
            )


def map_ap_author(author):
    """Map a Claude author (string or object) to the AP {name,email,url} object."""
    if isinstance(author, str) and author.strip():
        return {"name": author.strip()}
    if isinstance(author, dict):
        out = {}
        for key in ("name", "email", "url"):
            val = author.get(key)
            if isinstance(val, str) and val:
                out[key] = val
        return out or None
    return None


def load_source_manifest(plugin_dir: Path, analysis: dict) -> dict:
    """Read the Claude plugin.json. Analysis drops license and extra fields."""
    path = plugin_dir / ".claude-plugin" / "plugin.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise ValueError(
                f"malformed plugin manifest {path}: invalid JSON"
            ) from None
        if not isinstance(data, dict):
            raise ValueError(
                f"malformed plugin manifest {path}: must be an object"
            )
        return data
    return dict(analysis.get("manifest") or {})


def load_claude_mcp_servers(plugin_dir: Path, manifest: dict) -> dict:
    """Read MCP servers from .mcp.json or inline manifest mcpServers.

    Absent .mcp.json is fine (fall back to inline). A present file that is not
    valid JSON, or whose mcpServers is not an object, is an error.
    """
    mcp_file = plugin_dir / ".mcp.json"
    if mcp_file.is_file():
        try:
            data = json.loads(mcp_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            raise ValueError(f"malformed MCP config {mcp_file}: invalid JSON") from None
        if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict):
            raise ValueError(
                f"malformed MCP config {mcp_file}: mcpServers must be an object"
            )
        return data["mcpServers"]
    inline = manifest.get("mcpServers")
    return inline if isinstance(inline, dict) else {}


def _rewrite_command_token(token: str) -> str:
    """Rewrite one argv token for use as a stdio command."""
    if token == _CLAUDE_PLUGIN_ROOT or token.rstrip("/") == _CLAUDE_PLUGIN_ROOT:
        return "."
    prefix = _CLAUDE_PLUGIN_ROOT + "/"
    if token.startswith(prefix):
        rest = token[len(prefix):]
        return f"./{rest}" if rest else "."
    return token


def split_stdio_command(command: str) -> tuple[str, list[str]]:
    """shlex-split a raw command; rewrite plugin-root in the executable token."""
    raw = (command or "").strip()
    if not raw:
        return "", []
    try:
        parts = shlex.split(raw)
    except ValueError as e:
        raise ValueError(f"malformed command string: {e}") from None
    if not parts:
        return "", []
    cmd = _rewrite_command_token(parts[0])
    extra = [rewrite_ap_placeholders(p) for p in parts[1:]]
    return cmd, extra


def rewrite_stdio_command(command: str) -> str:
    """Rewrite a stdio command to one token or a ./ plugin-relative path."""
    cmd, _extra = split_stdio_command(command)
    return cmd


def rewrite_ap_placeholders(value: str) -> str:
    return value.replace(_CLAUDE_PLUGIN_ROOT, _AP_PLUGIN_ROOT)


_CREDENTIAL_HEADER_NAMES = frozenset({"authorization", "cookie", "proxy-authorization"})
_TOKEN_VALUE_PREFIXES = ("bearer ", "basic ", "token ")
_CWD_PATTERN = re.compile(
    r"^(?:\./|\$\{PLUGIN_ROOT\}(?:/|$)|\$\{PLUGIN_DATA\}(?:/|$))"
)


def _path_has_dotdot(value: str) -> bool:
    return ".." in PurePosixPath(value.replace("\\", "/")).parts


_CREDENTIAL_KEY_BITS = frozenset({"api", "token", "secret", "key", "password", "auth"})
_CREDENTIAL_KEY_OVERRIDES = frozenset({"file", "path", "url", "mode", "id"})
_PLACEHOLDER_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
_PLUGIN_PATH_PLACEHOLDER_RE = re.compile(r"\$\{(?:PLUGIN_ROOT|PLUGIN_DATA)\}")


def _env_placeholder_name(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", key).upper()


def _is_credential_shaped_key(key: str) -> bool:
    kl = key.lower().replace("_", "-")
    if kl in _CREDENTIAL_HEADER_NAMES:
        return True
    segments = [s for s in re.split(r"[-_]", key.lower()) if s]
    if segments and segments[-1] in _CREDENTIAL_KEY_OVERRIDES:
        return False
    compact = "".join(segments)
    return any(bit in compact for bit in _CREDENTIAL_KEY_BITS)


def _redact_credential_value(key: str, val: str, warnings: list[str] | None, where: str) -> str:
    stripped = val.strip()
    if _PLACEHOLDER_RE.match(stripped):
        return val
    already = re.fullmatch(r"\$\{([^}]+)\}", stripped)
    if already:
        return "${" + _env_placeholder_name(already.group(1)) + "}"
    placeholder = "${" + _env_placeholder_name(key) + "}"
    msg = (
        f"{where}[{key}] looks credential-shaped; value replaced with {placeholder} "
        "— rotate the source credential"
    )
    if warnings is not None:
        warnings.append(msg)
    return placeholder


def _is_loopback_host(host: str) -> bool:
    if not host:
        return False
    h = host.strip("[]").lower()
    if h in {"localhost", "localhost."}:
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def _reject_credential_headers(headers: dict) -> dict:
    """Copy headers, rejecting credential-bearing keys/values. Never echo secrets."""
    cleaned = {}
    for key, val in headers.items():
        key_s = str(key)
        val_s = str(val)
        if key_s.lower() in _CREDENTIAL_HEADER_NAMES:
            raise ValueError(f"headers[{key_s}] embeds credentials")
        lowered = val_s.lstrip().lower()
        if any(lowered.startswith(p) for p in _TOKEN_VALUE_PREFIXES):
            raise ValueError(f"headers[{key_s}] embeds credentials")
        cleaned[key_s] = val_s
    return cleaned


def _validate_mcp_url(url: str, warnings: list[str] | None = None) -> None:
    """HTTP MCP URL semantics (spec §7.2.1). Errors name the key, not secrets."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError("url scheme must be http or https")
    if parsed.username is not None or parsed.password is not None or "@" in (parsed.netloc or ""):
        raise ValueError("url must not contain userinfo")
    if parsed.fragment:
        raise ValueError("url must not contain a fragment")
    if parsed.query:
        raise ValueError("url must not contain a query string")
    if parsed.scheme.lower() == "http" and not _is_loopback_host(parsed.hostname or ""):
        host = parsed.hostname or ""
        msg = f"plain HTTP url host {host!r} is not loopback; allowed with warning"
        if warnings is not None:
            warnings.append(msg)


def _command_is_dots_only(cmd: str) -> bool:
    return bool(cmd) and set(cmd) <= {"."}


def _validate_stdio_command(cmd: str) -> None:
    normalized = cmd.rstrip("/") or cmd
    if cmd in {".", "./", "./.", ".."} or normalized in {".", "./", "./.", ".."}:
        raise ValueError(
            "command is a directory, not an executable "
            "(bare ${CLAUDE_PLUGIN_ROOT} is not a command)"
        )
    cmd = normalized
    if any(c.isspace() for c in cmd):
        raise ValueError(f"command contains whitespace: {cmd!r}")
    if _path_has_dotdot(cmd) or _command_is_dots_only(cmd):
        raise ValueError(f"command escapes plugin root: {cmd!r}")
    if "/" not in cmd:
        return
    if cmd.startswith("/"):
        return
    if not cmd.startswith("./"):
        raise ValueError(
            f"command must be a bare token, absolute path, or ./relative: {cmd!r}"
        )


def _validate_stdio_cwd(cwd: str) -> None:
    if not _CWD_PATTERN.match(cwd):
        raise ValueError(f"cwd must match ./ or ${{PLUGIN_ROOT}}/${{PLUGIN_DATA}}: {cwd!r}")
    if _path_has_dotdot(cwd):
        raise ValueError(f"cwd escapes plugin root: {cwd!r}")


def _mask_stdio_args(args: list[str], warnings: list[str] | None = None) -> list[str]:
    """Replace credential-like --flag values with *** so secrets never land in mcp.json."""
    out: list[str] = []
    masked = False
    i = 0
    n = len(args)
    while i < n:
        a = args[i]
        if a.startswith("--") and "=" in a:
            flag, _, val = a.partition("=")
            if val and _is_credential_shaped_key(flag.lstrip("-")):
                out.append(f"{flag}=***")
                masked = True
            else:
                out.append(a)
            i += 1
            continue
        key = a.lstrip("-") if a.startswith("-") and len(a) > 1 else ""
        nxt = args[i + 1] if i + 1 < n else ""
        if key and _is_credential_shaped_key(key) and nxt and not nxt.startswith("-"):
            out.append(a)
            out.append("***")
            masked = True
            i += 2
            continue
        out.append(a)
        i += 1
    if masked and warnings is not None:
        warnings.append("credential-like value in args masked")
    return out


def _validate_stdio_arg(arg: str) -> None:
    # Args are opaque strings: containment applies only to ./ and ${PLUGIN_*} paths.
    if arg.startswith("./") and _path_has_dotdot(arg):
        raise ValueError(f"args path escapes plugin root: {arg!r}")
    for m in _PLUGIN_PATH_PLACEHOLDER_RE.finditer(arg):
        tail = arg[m.end():]
        if _path_has_dotdot(tail) or _path_has_dotdot(arg[m.start():]):
            raise ValueError(f"args path escapes plugin root: {arg!r}")


def convert_ap_mcp_server(config: dict, warnings: list[str] | None = None) -> dict:
    """Map one Claude MCP server entry to an AP mcp.json server object."""
    if not isinstance(config, dict):
        raise ValueError("MCP server entry must be an object")

    url = config.get("url")
    command = config.get("command")
    raw_type = config.get("type")

    if url and command:
        msg = "url is discarded because command is present"
        if warnings is not None:
            warnings.append(msg)

    if (raw_type in ("streamable-http", "sse") or url) and not command:
        if not url:
            raise ValueError("HTTP MCP server is missing url")
        url_s = str(url)
        _validate_mcp_url(url_s, warnings)
        entry = {
            "type": raw_type if raw_type in ("streamable-http", "sse") else "streamable-http",
            "url": url_s,
        }
        headers = config.get("headers")
        if isinstance(headers, dict) and headers:
            cleaned_headers = _reject_credential_headers(headers)
            redacted = {}
            for hk, hv in cleaned_headers.items():
                if _is_credential_shaped_key(hk):
                    redacted[hk] = _redact_credential_value(hk, hv, warnings, "headers")
                else:
                    redacted[hk] = hv
            entry["headers"] = redacted
        return entry

    raw_cmd = "" if command is None else str(command)
    cmd, extra_args = split_stdio_command(raw_cmd)
    if not cmd:
        raise ValueError("stdio MCP server is missing command")
    _validate_stdio_command(cmd)
    if cmd.startswith("/") and warnings is not None:
        warnings.append(
            f"command {cmd!r} is an absolute path; it will not resolve on other machines"
        )

    entry = {"type": "stdio", "command": cmd}
    raw_args = extra_args + list(config.get("args") or [])
    if raw_args:
        rewritten = []
        for a in raw_args:
            if not isinstance(a, str):
                raise ValueError(
                    f"args entries must be strings, got {type(a).__name__}"
                )
            ra = rewrite_ap_placeholders(a)
            _validate_stdio_arg(ra)
            rewritten.append(ra)
        rewritten = _mask_stdio_args(rewritten, warnings)
        entry["args"] = rewritten
    env = config.get("env")
    if isinstance(env, dict) and env:
        cleaned = {}
        for key, val in env.items():
            key_s = str(key)
            if key_s in ("PLUGIN_ROOT", "PLUGIN_DATA"):
                raise ValueError(f"MCP env key {key_s} is reserved")
            if not isinstance(val, str):
                raise ValueError(f"env[{key_s}] must be a string")
            rewritten_val = rewrite_ap_placeholders(val)
            if _is_credential_shaped_key(key_s):
                rewritten_val = _redact_credential_value(
                    key_s, rewritten_val, warnings, "env"
                )
            cleaned[key_s] = rewritten_val
        entry["env"] = cleaned
    cwd = config.get("cwd")
    if cwd:
        cwd_s = rewrite_ap_placeholders(str(cwd))
        _validate_stdio_cwd(cwd_s)
        entry["cwd"] = cwd_s
    return entry


def build_ap_plugin_json(manifest: dict, name: str | None = None) -> dict:
    """Build a closed-schema Agent Plugins plugin.json from a Claude manifest."""
    doc = {
        "$schema": PLUGIN_SCHEMA_URL,
        "name": name if name is not None else ap_slug(str(manifest.get("name") or "")),
    }
    for key in ("version", "description", "license", "homepage"):
        val = manifest.get(key)
        if isinstance(val, str) and val:
            doc[key] = val
    repo = manifest.get("repository")
    if isinstance(repo, str) and repo:
        doc["repository"] = repo
    elif isinstance(repo, dict):
        url = repo.get("url")
        if isinstance(url, str) and url:
            doc["repository"] = url
    author = map_ap_author(manifest.get("author"))
    if author:
        doc["author"] = author
    keywords = manifest.get("keywords")
    if isinstance(keywords, list) and keywords and all(isinstance(k, str) for k in keywords):
        doc["keywords"] = keywords
    extensions = manifest.get("extensions")
    if isinstance(extensions, dict):
        cleaned = {k: v for k, v in extensions.items() if isinstance(v, dict)}
        if cleaned:
            doc["extensions"] = cleaned
    unknown = set(doc) - _AP_PLUGIN_FIELDS
    if unknown:
        raise ValueError(f"internal error, unknown plugin.json fields: {unknown}")
    return doc


_STDLIB_SKIP_NOTE = (
    "stdlib fallback skips JSON Schema additionalProperties, the cwd pattern, "
    "reserved env names, and per-variant field sets that jsonschema would enforce"
)


def _schema_file(filename: str) -> Path | None:
    shipped = Path(__file__).resolve().parent / "schemas" / filename
    if shipped.is_file():
        return shipped
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "tests" / filename
        if candidate.is_file():
            return candidate
    return None


def _stdlib_validate_plugin_json(doc: dict) -> None:
    if not isinstance(doc, dict):
        raise ValueError("plugin.json must be an object")
    extra = set(doc) - _AP_PLUGIN_FIELDS
    if extra:
        raise ValueError(f"unknown plugin.json fields: {sorted(extra)}")
    if doc.get("$schema") != PLUGIN_SCHEMA_URL:
        raise ValueError("plugin.json $schema is invalid")
    name = doc.get("name")
    if not isinstance(name, str) or not (1 <= len(name) <= 64) or not _AP_NAME_RE.match(name):
        raise ValueError(f"invalid plugin.json name: {name!r}")
    if "author" in doc:
        author = doc["author"]
        if not isinstance(author, dict) or set(author) - {"name", "email", "url"}:
            raise ValueError("plugin.json author must be {name?, email?, url?}")
    if "keywords" in doc and (
        not isinstance(doc["keywords"], list)
        or not all(isinstance(k, str) for k in doc["keywords"])
    ):
        raise ValueError("plugin.json keywords must be an array of strings")
    if "extensions" in doc:
        ext = doc["extensions"]
        if not isinstance(ext, dict) or not all(isinstance(v, dict) for v in ext.values()):
            raise ValueError("plugin.json extensions must be an object of objects")


def _stdlib_validate_mcp_json(doc: dict) -> None:
    if not isinstance(doc, dict):
        raise ValueError("mcp.json must be an object")
    extra = set(doc) - {"$schema", "mcpServers"}
    if extra:
        raise ValueError(f"unknown mcp.json fields: {sorted(extra)}")
    if doc.get("$schema") != MCP_SCHEMA_URL:
        raise ValueError("mcp.json $schema is invalid")
    servers = doc.get("mcpServers")
    if not isinstance(servers, dict):
        raise ValueError("mcp.json mcpServers must be an object")
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            raise ValueError(f"MCP server {name!r} must be an object")
        stype = entry.get("type")
        if stype == "stdio":
            allowed = {"type", "command", "args", "env", "cwd"}
            extra_s = set(entry) - allowed
            if extra_s:
                raise ValueError(f"unknown stdio fields on {name!r}: {sorted(extra_s)}")
            cmd = entry.get("command")
            if not isinstance(cmd, str) or not cmd:
                raise ValueError(f"stdio server {name!r} is missing command")
        elif stype in ("streamable-http", "sse"):
            if not isinstance(entry.get("url"), str) or not entry.get("url"):
                raise ValueError(f"{stype} server {name!r} is missing url")
        else:
            raise ValueError(f"MCP server {name!r} has invalid type: {stype!r}")


def _validate_mcp_semantics(doc: dict) -> None:
    """Spec §7.2.1 checks the JSON schema does not encode (containment, credentials)."""
    servers = doc.get("mcpServers") or {}
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            continue
        stype = entry.get("type")
        try:
            if stype == "stdio":
                cmd = entry.get("command")
                if isinstance(cmd, str):
                    _validate_stdio_command(cmd)
                cwd = entry.get("cwd")
                if cwd:
                    _validate_stdio_cwd(str(cwd))
                for a in entry.get("args") or []:
                    _validate_stdio_arg(str(a))
            elif stype in ("streamable-http", "sse"):
                url = entry.get("url")
                if isinstance(url, str) and url:
                    _validate_mcp_url(url)
                headers = entry.get("headers")
                if isinstance(headers, dict) and headers:
                    _reject_credential_headers(headers)
        except ValueError as e:
            raise ValueError(f"MCP server {name!r}: {e}") from None


def _validate_with_schema(doc: dict, filename: str, stdlib_fn) -> None:
    schema_path = _schema_file(filename)
    try:
        import jsonschema
    except ImportError:
        jsonschema = None
    if jsonschema is not None and schema_path is not None:
        jsonschema.validate(doc, json.loads(schema_path.read_text(encoding="utf-8")))
        return
    if jsonschema is None:
        print(
            "Warning: jsonschema is not installed; using built-in Agent Plugins checks. "
            + _STDLIB_SKIP_NOTE,
            file=sys.stderr,
        )
    if schema_path is None:
        print(
            "Warning: Agent Plugins schema file "
            f"{filename} not found beside the converter; using built-in checks. "
            + _STDLIB_SKIP_NOTE,
            file=sys.stderr,
        )
    stdlib_fn(doc)


def validate_ap_plugin_json(doc: dict) -> None:
    _validate_with_schema(doc, "plugin.schema.json", _stdlib_validate_plugin_json)


def validate_ap_mcp_json(doc: dict) -> None:
    _validate_with_schema(doc, "mcp.schema.json", _stdlib_validate_mcp_json)
    _validate_mcp_semantics(doc)


def _validate_or_die(doc: dict, kind: str) -> None:
    try:
        if kind == "plugin":
            validate_ap_plugin_json(doc)
        else:
            validate_ap_mcp_json(doc)
    except Exception as e:
        raise ValueError(f"Agent Plugins {kind} validation failed: {e}") from e


def _ap_skipped_component_bits(analysis: dict) -> list[tuple[str, list, str]]:
    components = analysis.get("components") or {}
    reason = "No Agent Plugins equivalent — skipped"
    bits: list[tuple[str, list, str]] = []
    for key, title, name_key, fallback in (
        ("agents", "Agents", "name", "unnamed"),
        ("hooks", "Hooks", "claude_event", "unknown"),
        ("commands", "Commands", "name", "unnamed"),
        ("lsp_servers", "LSP Servers", "name", "unnamed"),
        ("monitors", "Monitors", "name", "unnamed"),
    ):
        items = components.get(key) or []
        if items:
            names = [a.get(name_key, fallback) for a in items]
            bits.append((title, names, reason))
    return bits


def _ap_summary_counts(analysis: dict, conversion_results: dict) -> dict:
    converted = 0
    partial = 0
    for sk in conversion_results.get("skills") or []:
        if sk.get("issues"):
            partial += 1
        else:
            converted += 1
    converted += len(conversion_results.get("mcp_servers") or [])
    skipped = sum(len(names) for _, names, _ in _ap_skipped_component_bits(analysis))
    skipped += len(conversion_results.get("skipped_mcp_servers") or [])
    return {
        "convertible": converted,
        "partial": partial,
        "skipped": skipped,
        "total": converted + partial + skipped,
    }


def generate_ap_report(analysis: dict, conversion_results: dict, plugin_name: str) -> str:
    """CONVERSION_REPORT.md for Agent Plugins output. Same table style as Hermes."""
    s = _ap_summary_counts(analysis, conversion_results)
    lines = [
        f"# Conversion Report: {plugin_name}",
        "",
        f"**Source:** Claude Code plugin",
        f"**Target:** Agent Plugins package (agent-plugins.org v1.0.0)",
        "",
        "## Summary",
        "",
        f"| Status | Count |",
        f"|--------|-------|",
        f"| ✅ Converted | {s['convertible']} |",
        f"| ⚠️ Partial | {s['partial']} |",
        f"| ⏭️ Skipped | {s['skipped']} |",
        f"| **Total** | {s['total']} |",
        "",
        "## Conversion Results",
        "",
    ]

    if conversion_results.get("skills"):
        lines.append("### Skills")
        lines.append("")
        lines.append("| Skill | Status | Issues |")
        lines.append("|-------|--------|--------|")
        for sk in conversion_results["skills"]:
            status = "✅" if not sk.get("issues") else "⚠️"
            issues = "; ".join(sk.get("issues", [])) or "None"
            lines.append(f"| {sk['name']} | {status} | {issues} |")
        lines.append("")

    if conversion_results.get("mcp_servers"):
        lines.append("### MCP Servers")
        lines.append("")
        lines.append("| Server | Status |")
        lines.append("|--------|--------|")
        for srv in conversion_results["mcp_servers"]:
            lines.append(f"| {srv['name']} | ✅ mcp.json entry |")
        lines.append("")
        warn_bits = []
        for srv in conversion_results["mcp_servers"]:
            for w in srv.get("warnings") or []:
                warn_bits.append(f"- {srv['name']}: {w}")
        if warn_bits:
            lines.append("### Warnings")
            lines.append("")
            lines.extend(warn_bits)
            lines.append("")

    skipped_bits = _ap_skipped_component_bits(analysis)
    skipped_mcp = conversion_results.get("skipped_mcp_servers") or []
    if skipped_bits or skipped_mcp:
        lines.append("### Skipped")
        lines.append("")
        for title, names, reason in skipped_bits:
            lines.append(f"**{title}**")
            for n in names:
                lines.append(f"- {n}: ⏭️ {reason}")
            lines.append("")
        if skipped_mcp:
            lines.append("**MCP Servers**")
            for item in skipped_mcp:
                reason = item.get("reason") or "non-conforming"
                lines.append(f"- {item.get('name', 'unnamed')}: ⏭️ {reason}")
            lines.append("")

    ignored = conversion_results.get("ignored_source_files") or []
    if ignored:
        lines.append("### Ignored source files")
        lines.append("")
        for name in ignored:
            lines.append(
                f"- `{name}` at the source root is converter-owned output and was not copied"
            )
        lines.append("")

    lines.append("## Next Steps")
    lines.append("")
    lines.append("1. Review `plugin.json` against https://agent-plugins.org/ (closed manifest)")
    lines.append("2. Review each `skills/<name>/SKILL.md` frontmatter (name + description)")
    if conversion_results.get("mcp_servers"):
        lines.append("3. Review `mcp.json` (stdio command is one token; plugin paths use `./` or `${PLUGIN_ROOT}`)")
        lines.append("4. Copy this directory to your Agent Plugins search path")
    else:
        lines.append("3. Copy this directory to your Agent Plugins search path")
    return "\n".join(lines) + "\n"


def convert_plugin_agent_plugins(plugin_dir: Path, analysis: dict, output_dir: Path) -> dict:
    """Convert a Claude plugin to an Agent Plugins package.

    `--output` is the package root (plugin.json lives at <output>/plugin.json),
    matching the contract tests. Hermes mode still nests under <output>/<name>/.
    """
    plugin_dir = Path(plugin_dir).resolve()
    output_dir = Path(output_dir).resolve()
    _assert_output_disjoint_from_source(plugin_dir, output_dir)
    dest = output_dir
    _assert_ap_dest_is_writable(dest)
    dest.mkdir(parents=True, exist_ok=True)
    _clear_ap_owned_outputs(dest)

    manifest = load_source_manifest(plugin_dir, analysis)
    plugin_name = ap_slug(str(manifest.get("name") or plugin_dir.name), "plugin")

    components = analysis.get("components") or {}
    _raise_on_ap_skill_slug_collision(components.get("skills") or [])

    plugin_doc = build_ap_plugin_json(manifest, name=plugin_name)
    _validate_or_die(plugin_doc, "plugin")

    source_servers = None
    try:
        source_servers = load_claude_mcp_servers(plugin_dir, manifest)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    mcp_doc = None
    mcp_infos = []
    skipped_mcp: list[dict] = []
    if source_servers:
        mcp_servers = {}
        for sname, sconfig in source_servers.items():
            try:
                warns: list[str] = []
                mcp_servers[sname] = convert_ap_mcp_server(sconfig, warnings=warns)
            except Exception as e:
                skipped_mcp.append({"name": sname, "reason": str(e)})
                continue
            info = {"name": sname, "status": "converted"}
            if warns:
                info["warnings"] = warns
            mcp_infos.append(info)
        if mcp_servers:
            mcp_doc = {"$schema": MCP_SCHEMA_URL, "mcpServers": mcp_servers}
            _validate_or_die(mcp_doc, "mcp")

    results = {
        "skills": [],
        "mcp_servers": mcp_infos,
        "agents": [],
        "hooks": [],
        "commands": [],
        "skipped_mcp_servers": skipped_mcp,
    }

    if components.get("skills"):
        skills_dir = dest / "skills"
        skills_dir.mkdir(exist_ok=True)
        for skill_info in components["skills"]:
            result = convert_skill(
                skill_info, plugin_dir, skills_dir, flavour="agent-plugins"
            )
            results["skills"].append(result)

    (dest / "plugin.json").write_text(
        json.dumps(plugin_doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    if mcp_doc is not None:
        (dest / "mcp.json").write_text(
            json.dumps(mcp_doc, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    bin_dir = plugin_dir / "bin"
    if bin_dir.exists():
        shutil.copytree(bin_dir, dest / "bin", dirs_exist_ok=True)

    skip_dirs = {
        ".claude-plugin", "skills", "commands", "agents", "hooks", ".git",
        "__pycache__", ".pytest_cache", "tests", "tools", "bin",
    }
    ignored_source_files: list[str] = []
    for child in plugin_dir.iterdir():
        if child.name.startswith("."):
            continue
        if child.is_dir() and child.name not in skip_dirs:
            if _is_dest_or_contains_dest(child, dest):
                continue
            shutil.copytree(child, dest / child.name, dirs_exist_ok=True)
        elif child.is_file():
            if child.name in _AP_OWNED_OUTPUT_FILES:
                ignored_source_files.append(child.name)
                continue
            shutil.copy2(child, dest / child.name)

    results["ignored_source_files"] = ignored_source_files
    report = generate_ap_report(analysis, results, plugin_name)
    (dest / "CONVERSION_REPORT.md").write_text(report, encoding="utf-8")

    results["plugin_name"] = plugin_name
    results["output_dir"] = str(dest)
    results["results_dir"] = str(dest)
    return results


# ── Main conversion ────────────────────────────────────────────────────

def convert_plugin(plugin_dir: Path, analysis: dict, output_dir: Path) -> dict:
    """Convert a Claude plugin to a Hermes plugin. Returns conversion results."""
    manifest = analysis["manifest"]
    plugin_name = safe_name(manifest.get("name", plugin_dir.name), plugin_dir.name)
    
    # Create output directory
    dest = output_dir / plugin_name
    dest.mkdir(parents=True, exist_ok=True)
    
    components = analysis["components"]
    results = {}
    
    # 1. Generate plugin.yaml
    plugin_yaml = generate_plugin_yaml(manifest, analysis)
    (dest / "plugin.yaml").write_text(plugin_yaml, encoding="utf-8")
    
    # 2. Convert skills
    results["skills"] = []
    if components.get("skills"):
        skills_dir = dest / "skills"
        skills_dir.mkdir(exist_ok=True)
        for skill_info in components["skills"]:
            result = convert_skill(skill_info, plugin_dir, skills_dir)
            results["skills"].append(result)
    
    # 3. Convert agents → delegation skills
    results["agents"] = []
    if components.get("agents"):
        skills_dir = dest / "skills"
        skills_dir.mkdir(exist_ok=True)
        for agent_info in components["agents"]:
            result = convert_agent(agent_info, skills_dir)
            results["agents"].append(result)
    
    # 4. Convert hooks
    results["hooks"] = []
    hooks_code = ""
    hook_cb_names = {}  # {event_name: [callback_name, ...]}
    if components.get("hooks"):
        hooks_py, hook_infos = convert_hooks(components["hooks"], plugin_name, dest)
        (dest / "hooks.py").write_text(hooks_py, encoding="utf-8")
        results["hooks"] = hook_infos
        hooks_code = hooks_py
        # Build callback name mapping for __init__.py
        for info in hook_infos:
            if info.get("callback_name") and info.get("hermes_event"):
                hook_cb_names.setdefault(info["hermes_event"], []).append(info["callback_name"])
    
    # 5. Convert MCP servers
    results["mcp_servers"] = []
    if components.get("mcp_servers"):
        mcp_yaml, mcp_infos = convert_mcp(components["mcp_servers"], plugin_dir)
        (dest / "mcp_config.yaml").write_text(mcp_yaml, encoding="utf-8")
        results["mcp_servers"] = mcp_infos
    
    # 6. Convert commands
    results["commands"] = []
    commands_register_code = ""
    if components.get("commands"):
        cmd_infos, commands_register_code = convert_commands(components["commands"])
        results["commands"] = cmd_infos
    
    # 7. Generate __init__.py
    skill_names = [s["name"] for s in results.get("skills", [])] + [a["name"] for a in results.get("agents", [])]
    init_py = generate_init_py(plugin_name, analysis, bool(components.get("hooks")), 
                                commands_register_code, skill_names, hook_cb_names)
    (dest / "__init__.py").write_text(init_py, encoding="utf-8")
    
    # 8. Copy bin/ if present
    bin_dir = plugin_dir / "bin"
    if bin_dir.exists():
        shutil.copytree(bin_dir, dest / "bin", dirs_exist_ok=True)
    
    # 8b. Copy non-skill directories that skills reference (engines, foundations, connectors, etc.)
    #     These are part of the plugin's data and need to travel with it.
    skip_dirs = {".claude-plugin", "skills", "commands", "agents", "hooks", ".git", 
                 "__pycache__", ".pytest_cache", "tests", "tools"}
    for child in plugin_dir.iterdir():
        if child.is_dir() and child.name not in skip_dirs and not child.name.startswith("."):
            if _is_dest_or_contains_dest(child, dest):
                continue
            shutil.copytree(child, dest / child.name, dirs_exist_ok=True)
    
    # 9. Generate reports
    report = generate_report(analysis, results, plugin_name)
    (dest / "CONVERSION_REPORT.md").write_text(report, encoding="utf-8")
    
    manual_steps = generate_manual_steps(analysis, plugin_name)
    (dest / "MANUAL_STEPS.md").write_text(manual_steps, encoding="utf-8")

    results["plugin_name"] = plugin_name
    results["output_dir"] = str(dest)
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Convert a Claude Code plugin to a Hermes plugin or Agent Plugins package",
    )
    parser.add_argument("plugin_dir", help="Path to the Claude plugin directory")
    parser.add_argument("--analysis", "-a", required=True, help="Path to analysis.json from analyze.py")
    parser.add_argument("--output", "-o", required=True, help="Output directory for the converted plugin")
    parser.add_argument(
        "--format",
        choices=("hermes", "agent-plugins"),
        default="hermes",
        help="Output package format (default: hermes)",
    )
    args = parser.parse_args()

    plugin_dir = Path(args.plugin_dir).resolve()
    analysis_path = Path(args.analysis).resolve()
    output_dir = Path(args.output).resolve()

    if not plugin_dir.is_dir():
        print(f"Error: {plugin_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    if not analysis_path.exists():
        print(f"Error: Analysis file not found: {analysis_path}", file=sys.stderr)
        sys.exit(1)

    try:
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(
            f"Error: malformed analysis file {analysis_path}: invalid JSON",
            file=sys.stderr,
        )
        sys.exit(1)
    if not isinstance(analysis, dict):
        print(
            f"Error: malformed analysis file {analysis_path}: must be an object",
            file=sys.stderr,
        )
        sys.exit(1)

    if "error" in analysis:
        print(f"Error: {analysis['error']}", file=sys.stderr)
        sys.exit(1)

    try:
        if args.format == "agent-plugins":
            results = convert_plugin_agent_plugins(plugin_dir, analysis, output_dir)
        else:
            results = convert_plugin(plugin_dir, analysis, output_dir)
    except (ValueError, shutil.Error) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    skipped_mcp = results.get("skipped_mcp_servers") or []
    skills = results.get("skills") or []
    converted_skills = [
        s for s in skills
        if not any("not found" in str(i).lower() for i in (s.get("issues") or []))
    ]
    failed = not converted_skills and not results.get("mcp_servers")
    skipped_any = bool(skipped_mcp) or (len(converted_skills) < len(skills))
    if failed:
        banner = "❌ Conversion failed"
    elif skipped_any:
        banner = "⚠ completed with skipped skills"
    else:
        banner = "✅ Converted"
    print(f"\n{banner}: {results['plugin_name']}", file=sys.stderr)
    print(f"   Output: {results['output_dir']}", file=sys.stderr)
    
    for component_type in ("skills", "agents", "hooks", "mcp_servers", "commands"):
        count = len(results.get(component_type, []))
        if count:
            print(f"   {component_type}: {count}", file=sys.stderr)

    for item in skipped_mcp:
        name = item.get("name", "unnamed")
        reason = item.get("reason") or "non-conforming"
        print(f"   skipped MCP server {name}: {reason}", file=sys.stderr)
    
    # Write results JSON inside the package root (--output).
    results_dir = Path(results.get("results_dir") or results["output_dir"])
    results_path = results_dir / "conversion_results.json"
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults: {results_path}", file=sys.stderr)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()