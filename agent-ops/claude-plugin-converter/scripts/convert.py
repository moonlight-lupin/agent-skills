#!/usr/bin/env python3
"""Phase 2: Convert a Claude Code plugin into a self-contained Hermes plugin.

Takes the analysis JSON (from analyze.py) + plugin directory.
Generates a complete Hermes plugin directory.

Usage:
    python3 convert.py <plugin_dir> --analysis <analysis.json> --output <output_dir>
"""

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from textwrap import dedent


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


def yaml_quote(s: str) -> str:
    """Quote a string for YAML."""
    if not s:
        return '""'
    if any(c in s for c in [":", "#", "{", "}", "[", "]", ",", "&", "*", "!", "|", ">", "'", '"', "%", "@", "`"]):
        return f'"{s}"'
    return s


# ── Skill conversion ────────────────────────────────────────────────────

def convert_skill(skill_info: dict, source_plugin_dir: Path, dest_skills_dir: Path) -> dict:
    """Convert a Claude skill to Hermes format. Returns {name, path, issues}."""
    source_skill_dir = Path(skill_info["path"])
    skill_name = safe_name(skill_info.get("name", source_skill_dir.name), source_skill_dir.name)

    # Create destination
    dest_skill_dir = dest_skills_dir / skill_name
    dest_skill_dir.mkdir(parents=True, exist_ok=True)

    # Read original SKILL.md
    source_skill_md = source_skill_dir / "SKILL.md"
    if not source_skill_md.exists():
        return {"name": skill_name, "path": str(dest_skill_dir), "issues": ["Source SKILL.md not found"]}
    
    content = source_skill_md.read_text(encoding="utf-8", errors="replace")
    orig_fm, body = parse_frontmatter(content)

    # Build new frontmatter
    new_fm_lines = [
        f"name: {skill_name}",
        f"description: {yaml_quote(orig_fm.get('description', ''))}",
    ]

    # Remove disable-model-invocation (no Hermes equivalent)
    if orig_fm.get("disable-model-invocation", "").lower() == "true":
        pass  # Intentionally dropped
    
    # Rewrite $ARGUMENTS
    new_body = body
    if "$ARGUMENTS" in new_body:
        new_body = new_body.replace(
            "$ARGUMENTS",
            "<the user's request — read their message for the argument>",
        )

    # Rewrite ${CLAUDE_PLUGIN_ROOT} → relative path from skills/ dir
    # In Hermes plugins, skills are at <plugin>/skills/<name>/SKILL.md
    # The plugin root is 2 levels up from the skill dir
    new_body = new_body.replace("${CLAUDE_PLUGIN_ROOT}", "..")
    # Also rewrite relative links that used CLAUDE_PLUGIN_ROOT as base
    # e.g. [`${CLAUDE_PLUGIN_ROOT}/foundations/doctrine.md`](../../foundations/doctrine.md)
    # becomes [foundations/doctrine.md](../../foundations/doctrine.md)
    new_body = re.sub(
        r"`\.\./([^`]+)`\]\((\.\./[^)]+)\)",
        r"`\1`](\2)",
        new_body,
    )

    # Write converted SKILL.md
    new_content = "---\n" + "\n".join(new_fm_lines) + "\n---\n" + new_body
    (dest_skill_dir / "SKILL.md").write_text(new_content, encoding="utf-8")

    # Copy supporting files (scripts/, references/, assets/, templates/)
    for subdir in ("scripts", "references", "assets", "templates"):
        src = source_skill_dir / subdir
        if src.exists() and src.is_dir():
            shutil.copytree(src, dest_skill_dir / subdir, dirs_exist_ok=True)

    issues = []
    if skill_info.get("uses_arguments"):
        issues.append("$ARGUMENTS rewritten to placeholder text — review")
    if skill_info.get("has_disable_invocation"):
        issues.append("disable-model-invocation dropped — Hermes skills are always model-invoked")

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
        args = srv.get("args", [])
        env_vars = srv.get("env_vars", [])
        
        lines.append(f"{name}:")
        lines.append(f"  command: {yaml_quote(command)}")
        if args:
            args_str = ", ".join(yaml_quote(a) for a in args)
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
    parser = argparse.ArgumentParser(description="Convert a Claude Code plugin to a Hermes plugin")
    parser.add_argument("plugin_dir", help="Path to the Claude plugin directory")
    parser.add_argument("--analysis", "-a", required=True, help="Path to analysis.json from analyze.py")
    parser.add_argument("--output", "-o", required=True, help="Output directory for the Hermes plugin")
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

    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    if "error" in analysis:
        print(f"Error: {analysis['error']}", file=sys.stderr)
        sys.exit(1)

    results = convert_plugin(plugin_dir, analysis, output_dir)

    # Print summary
    print(f"\n✅ Converted: {results['plugin_name']}", file=sys.stderr)
    print(f"   Output: {results['output_dir']}", file=sys.stderr)
    
    for component_type in ("skills", "agents", "hooks", "mcp_servers", "commands"):
        count = len(results.get(component_type, []))
        if count:
            print(f"   {component_type}: {count}", file=sys.stderr)
    
    # Write results JSON
    results_path = output_dir / results["plugin_name"] / "conversion_results.json"
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults: {results_path}", file=sys.stderr)


if __name__ == "__main__":
    main()