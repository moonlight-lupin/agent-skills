#!/usr/bin/env python3
"""Phase 1: Analyze a Claude Code plugin directory.

Reads .claude-plugin/plugin.json and all component directories.
Outputs structured JSON with convertibility assessments.

Usage:
    python3 analyze.py <plugin_dir> [--output analysis.json]
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


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
    # Replace any sequence of non-safe chars with a single hyphen
    cleaned = _SAFE_NAME_RE.sub("-", name.strip())
    # Strip leading dots (prevents hidden files / traversal)
    cleaned = cleaned.lstrip(".")
    # Remove dot-only segments left by path separators (e.g. "-..-foo" → "-foo")
    cleaned = re.sub(r"(?<!\w)\.+(?!\w)", "", cleaned)
    # Collapse multiple hyphens
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    # Strip leading/trailing hyphens
    cleaned = cleaned.strip("-")
    if not cleaned or cleaned in (".", ".."):
        return fallback
    return cleaned[:64]  # Cap length for filesystem safety


# ── Hook event mapping ──────────────────────────────────────────────────

HOOK_EVENT_MAP = {
    "SessionStart": ("on_session_start", "yes", "Direct match"),
    "SessionEnd": ("on_session_end", "yes", "Direct match"),
    "Setup": (None, "no", "No Hermes equivalent — CI/one-time prep"),
    "UserPromptSubmit": ("pre_llm_call", "yes", "Both fire before LLM. Hermes can inject context."),
    "UserPromptExpansion": (None, "no", "No command expansion equivalent"),
    "PreToolUse": ("pre_tool_call", "yes", "Both can block. Claude uses matcher; Hermes checks tool_name."),
    "PermissionRequest": ("pre_approval_request", "yes", "Similar concept"),
    "PermissionDenied": ("post_approval_response", "yes", "Similar concept"),
    "PostToolUse": ("post_tool_call", "yes", "Direct match"),
    "PostToolUseFailure": ("post_tool_call", "partial", "Same hook, check result for error"),
    "PostToolBatch": (None, "no", "No batch-level hook"),
    "Notification": (None, "no", "No notification hook"),
    "MessageDisplay": ("transform_llm_output", "partial", "Closest match — transform output before delivery"),
    "SubagentStart": ("subagent_start", "yes", "Direct match"),
    "SubagentStop": ("subagent_stop", "yes", "Direct match"),
    "TaskCreated": (None, "no", "No task-creation hook"),
    "TaskCompleted": (None, "no", "No task-completion hook"),
    "Stop": ("post_llm_call", "partial", "Closest match — after tool-calling loop"),
    "StopFailure": (None, "no", "No API-error hook"),
    "TeammateIdle": (None, "no", "No agent-teams equivalent"),
    "InstructionsLoaded": (None, "no", "No context-file-loaded hook"),
    "ConfigChange": (None, "no", "No config-change hook"),
    "CwdChanged": (None, "no", "No cwd-change hook"),
    "FileChanged": (None, "no", "No file-watcher hook"),
    "WorktreeCreate": (None, "no", "No worktree hook"),
    "WorktreeRemove": (None, "no", "No worktree hook"),
    "PreCompact": (None, "no", "No pre-compaction hook"),
    "PostCompact": (None, "no", "No post-compaction hook"),
    "Elicitation": (None, "no", "No MCP elicitation hook"),
    "ElicitationResult": (None, "no", "No MCP elicitation hook"),
}

HOOK_TYPE_MAP = {
    "command": ("subprocess.run() in Python callback", "yes", "Translate ${CLAUDE_PLUGIN_ROOT}"),
    "http": ("httpx.post() in Python callback", "yes", "Event data = context dict"),
    "mcp_tool": ("ctx.dispatch_tool() in Python callback", "yes", "Strip plugin namespace from tool names"),
    "prompt": (None, "no", "No equivalent — note for manual implementation"),
    "agent": (None, "no", "No equivalent — note for manual implementation"),
}


# ── Parsing helpers ─────────────────────────────────────────────────────

def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content. Returns (frontmatter, body)."""
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
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            fm[key] = val
    return fm, body


def analyze_skill(skill_dir: Path) -> dict:
    """Analyze a single skill directory."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return {"name": skill_dir.name, "path": str(skill_dir), "error": "No SKILL.md found"}

    content = skill_md.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(content)

    # Check for supporting files
    has_scripts = (skill_dir / "scripts").exists()
    has_references = (skill_dir / "references").exists()
    has_assets = any(
        (skill_dir / d).exists()
        for d in ("assets", "templates", "references", "scripts")
    )

    # Check for $ARGUMENTS usage
    uses_arguments = "$ARGUMENTS" in body

    # Check for disable-model-invocation
    has_disable_invocation = fm.get("disable-model-invocation", "").lower() == "true"

    issues = []
    if uses_arguments:
        issues.append("$ARGUMENTS used — no Hermes equivalent, needs manual review")
    if has_disable_invocation:
        issues.append("disable-model-invocation has no Hermes equivalent — skills are always model-invoked")

    return {
        "name": safe_name(fm.get("name", skill_dir.name), skill_dir.name),
        "path": str(skill_dir),
        "frontmatter": fm,
        "has_scripts": has_scripts,
        "has_references": has_references,
        "has_assets": has_assets,
        "uses_arguments": uses_arguments,
        "has_disable_invocation": has_disable_invocation,
        "issues": issues,
        "convertibility": "yes" if not issues else "partial",
        "body_length": len(body),
    }


def analyze_command(cmd_path: Path) -> dict:
    """Analyze a command (flat markdown file)."""
    content = cmd_path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(content)
    return {
        "name": cmd_path.stem,
        "path": str(cmd_path),
        "frontmatter": fm,
        "content_preview": body[:200],
        "convertibility": "partial",
        "issues": ["Commands need wrapping into ctx.register_command() — format differs"],
    }


def analyze_agent(agent_path: Path) -> dict:
    """Analyze an agent definition (markdown with frontmatter)."""
    content = agent_path.read_text(encoding="utf-8", errors="replace")
    fm, body = parse_frontmatter(content)

    return {
        "name": safe_name(fm.get("name", agent_path.stem), agent_path.stem),
        "path": str(agent_path),
        "model": fm.get("model", ""),
        "effort": fm.get("effort", ""),
        "maxTurns": fm.get("maxTurns", ""),
        "tools": fm.get("tools", ""),
        "disallowedTools": fm.get("disallowedTools", ""),
        "system_prompt_length": len(body),
        "system_prompt_preview": body[:200],
        "convertibility": "partial",
        "issues": ["Agent → delegation skill paradigm shift — behavior won't be identical"],
    }


def analyze_hook(hooks_data: dict) -> list:
    """Analyze hooks from hooks.json or inline hooks in plugin.json."""
    results = []
    hooks = hooks_data.get("hooks", {})
    for event_name, hook_list in hooks.items():
        hermes_event, convertibility, reason = HOOK_EVENT_MAP.get(
            event_name, (None, "no", f"Unknown event: {event_name}")
        )
        for hook_entry in hook_list:
            # Claude hooks.json has two layouts:
            # 1. Flat: {type: "command", command: "..."} directly in the entry
            # 2. Nested: {hooks: [{type: "command", command: "..."}, ...]} with optional matcher
            inner_hooks = hook_entry.get("hooks", [])
            matcher = hook_entry.get("matcher", "")
            
            if inner_hooks:
                # Nested layout — iterate inner hooks
                for inner in inner_hooks:
                    hook_type = inner.get("type", "command")
                    command = inner.get("command", "")
                    type_impl, type_conv, type_reason = HOOK_TYPE_MAP.get(
                        hook_type, (None, "no", f"Unknown type: {hook_type}")
                    )
                    results.append({
                        "claude_event": event_name,
                        "hermes_event": hermes_event,
                        "convertibility": convertibility if convertibility == "no" else type_conv,
                        "hook_type": hook_type,
                        "hermes_implementation": type_impl,
                        "matcher": matcher,
                        "command": command[:500],
                        "reason": reason if convertibility == "no" else type_reason,
                    })
            else:
                # Flat layout
                hook_type = hook_entry.get("type", "command")
                command = hook_entry.get("command", "")
                type_impl, type_conv, type_reason = HOOK_TYPE_MAP.get(
                    hook_type, (None, "no", f"Unknown type: {hook_type}")
                )
                results.append({
                    "claude_event": event_name,
                    "hermes_event": hermes_event,
                    "convertibility": convertibility if convertibility == "no" else type_conv,
                    "hook_type": hook_type,
                    "hermes_implementation": type_impl,
                    "matcher": matcher,
                    "command": command[:500],
                    "reason": reason if convertibility == "no" else type_reason,
                })
    return results


def analyze_mcp(mcp_data: dict) -> list:
    """Analyze MCP server configurations."""
    results = []
    servers = mcp_data.get("mcpServers", {})
    for name, config in servers.items():
        env_vars = list(config.get("env", {}).keys())
        results.append({
            "name": name,
            "command": config.get("command", ""),
            "args": config.get("args", []),
            "env_vars": env_vars,
            "uses_plugin_root": "${CLAUDE_PLUGIN_ROOT}" in config.get("command", ""),
            "convertibility": "yes",
            "issues": [] if not env_vars else [f"Env vars need config: {', '.join(env_vars)}"],
        })
    return results


def analyze_lsp(lsp_data: dict) -> list:
    """Analyze LSP server configurations — no Hermes equivalent."""
    results = []
    for name, config in lsp_data.items():
        results.append({
            "name": name,
            "command": config.get("command", ""),
            "language": list(config.get("extensionToLanguage", {}).keys()),
            "convertibility": "no",
            "issues": ["Hermes has no LSP integration"],
        })
    return results


def analyze_monitors(monitors_data) -> list:
    """Analyze monitor configurations — closest is cron jobs."""
    results = []
    # monitors.json can be a list of monitor dicts or {"monitors": [...]}
    if isinstance(monitors_data, list):
        monitors = monitors_data
    else:
        monitors = monitors_data.get("monitors", [])
    for m in monitors:
        results.append({
            "name": m.get("name", "unnamed"),
            "config": m,
            "convertibility": "partial",
            "issues": ["Monitors → Hermes cron jobs — different concept, needs manual setup"],
        })
    return results


# ── Main analysis ──────────────────────────────────────────────────────

def analyze_plugin(plugin_dir: Path) -> dict:
    """Analyze a complete Claude plugin directory."""
    manifest_path = plugin_dir / ".claude-plugin" / "plugin.json"
    if not manifest_path.exists():
        return {"error": f"No .claude-plugin/plugin.json found in {plugin_dir}"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Also check for inline hooks/MCP in plugin.json
    inline_mcp = manifest.get("mcpServers", {})
    inline_hooks = manifest.get("hooks", {})
    inline_lsp = manifest.get("lspServer", manifest.get("lsp", {}))

    components = {}

    # Skills
    skills_dir = plugin_dir / "skills"
    components["skills"] = []
    if skills_dir.exists():
        for child in sorted(skills_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").exists():
                components["skills"].append(analyze_skill(child))

    # Also check for single SKILL.md at root
    root_skill = plugin_dir / "SKILL.md"
    if root_skill.exists() and not skills_dir.exists():
        skill_info = analyze_skill(plugin_dir)
        skill_info["name"] = safe_name(skill_info["frontmatter"].get("name", plugin_dir.name), plugin_dir.name)
        components["skills"].append(skill_info)

    # Commands
    commands_dir = plugin_dir / "commands"
    components["commands"] = []
    if commands_dir.exists():
        for child in sorted(commands_dir.iterdir()):
            if child.is_file() and child.suffix == ".md":
                components["commands"].append(analyze_command(child))

    # Agents
    agents_dir = plugin_dir / "agents"
    components["agents"] = []
    if agents_dir.exists():
        for child in sorted(agents_dir.iterdir()):
            if child.is_file() and child.suffix == ".md":
                components["agents"].append(analyze_agent(child))

    # Hooks
    components["hooks"] = []
    hooks_file = plugin_dir / "hooks" / "hooks.json"
    if hooks_file.exists():
        hooks_data = json.loads(hooks_file.read_text(encoding="utf-8"))
        components["hooks"] = analyze_hook(hooks_data)
    elif inline_hooks:
        components["hooks"] = analyze_hook({"hooks": inline_hooks})

    # MCP servers
    components["mcp_servers"] = []
    mcp_file = plugin_dir / ".mcp.json"
    if mcp_file.exists():
        mcp_data = json.loads(mcp_file.read_text(encoding="utf-8"))
        components["mcp_servers"] = analyze_mcp(mcp_data)
    elif inline_mcp:
        components["mcp_servers"] = analyze_mcp({"mcpServers": inline_mcp})

    # LSP servers
    components["lsp_servers"] = []
    lsp_file = plugin_dir / ".lsp.json"
    if lsp_file.exists():
        lsp_data = json.loads(lsp_file.read_text(encoding="utf-8"))
        components["lsp_servers"] = analyze_lsp(lsp_data)
    elif inline_lsp:
        components["lsp_servers"] = analyze_lsp(inline_lsp)

    # Monitors
    components["monitors"] = []
    monitors_file = plugin_dir / "monitors" / "monitors.json"
    if monitors_file.exists():
        monitors_data = json.loads(monitors_file.read_text(encoding="utf-8"))
        components["monitors"] = analyze_monitors(monitors_data)

    # bin/
    components["bin"] = []
    bin_dir = plugin_dir / "bin"
    if bin_dir.exists():
        for child in sorted(bin_dir.iterdir()):
            if child.is_file():
                components["bin"].append({"name": child.name, "path": str(child)})

    # Summary
    all_components = (
        components["skills"]
        + components["commands"]
        + components["agents"]
        + components["hooks"]
        + components["mcp_servers"]
        + components["lsp_servers"]
        + components["monitors"]
    )
    convertible = sum(1 for c in all_components if c.get("convertibility") == "yes")
    partial = sum(1 for c in all_components if c.get("convertibility") == "partial")
    skipped = sum(1 for c in all_components if c.get("convertibility") == "no")

    return {
        "manifest": {
            "name": safe_name(manifest.get("name", plugin_dir.name), plugin_dir.name),
            "description": manifest.get("description", ""),
            "version": manifest.get("version", "unknown"),
            "author": manifest.get("author", {}),
        },
        "plugin_dir": str(plugin_dir),
        "components": components,
        "summary": {
            "total": len(all_components),
            "convertible": convertible,
            "partial": partial,
            "skipped": skipped,
        },
    }


def format_report(analysis: dict) -> str:
    """Format analysis as a human-readable report."""
    if "error" in analysis:
        return f"# Error\n\n{analysis['error']}\n"

    m = analysis["manifest"]
    s = analysis["summary"]
    c = analysis["components"]

    lines = [
        f"# Conversion Report: {m['name']} v{m['version']}",
        "",
        f"**Description:** {m['description']}",
        "",
        "## Summary",
        "",
        f"| Status | Count |",
        f"|--------|-------|",
        f"| ✅ Convertible | {s['convertible']} |",
        f"| ⚠️ Partial | {s['partial']} |",
        f"| ⏭️ Skipped | {s['skipped']} |",
        f"| **Total** | {s['total']} |",
        "",
    ]

    # Skills
    if c["skills"]:
        lines += ["## Skills", "", "| Skill | Issues | Convert? |", "|-------|--------|----------|"]
        for skill in c["skills"]:
            issues = "; ".join(skill.get("issues", [])) or "None"
            conv = "✅" if skill["convertibility"] == "yes" else "⚠️"
            lines.append(f"| {skill['name']} | {issues} | {conv} |")
        lines.append("")

    # Commands
    if c["commands"]:
        lines += ["## Commands", "", "| Command | Convert? |", "|---------|----------|"]
        for cmd in c["commands"]:
            lines.append(f"| {cmd['name']} | ⚠️ Needs wrapping |")
        lines.append("")

    # Agents
    if c["agents"]:
        lines += ["## Agents", "", "| Agent | Model | MaxTurns | Convert? |", "|-------|-------|-----------|----------|"]
        for agent in c["agents"]:
            conv = "⚠️ Delegation skill"
            lines.append(f"| {agent['name']} | {agent['model']} | {agent['maxTurns']} | {conv} |")
        lines.append("")

    # Hooks
    if c["hooks"]:
        lines += ["## Hooks", "", "| Claude Event | Hermes Event | Type | Convert? | Reason |", "|-------------|-------------|------|----------|--------|"]
        for hook in c["hooks"]:
            hermes_ev = hook.get("hermes_event") or "—"
            conv = {"yes": "✅", "partial": "⚠️", "no": "⏭️"}.get(hook["convertibility"], "?")
            lines.append(f"| {hook['claude_event']} | {hermes_ev} | {hook['hook_type']} | {conv} | {hook['reason']} |")
        lines.append("")

    # MCP
    if c["mcp_servers"]:
        lines += ["## MCP Servers", "", "| Server | Command | Env Vars | Convert? |", "|--------|---------|----------|----------|"]
        for srv in c["mcp_servers"]:
            env = ", ".join(srv.get("env_vars", [])) or "None"
            lines.append(f"| {srv['name']} | {srv['command'][:50]} | {env} | ✅ |")
        lines.append("")

    # LSP
    if c["lsp_servers"]:
        lines += ["## LSP Servers (No Hermes Equivalent)", "", "| Server | Language | Status |", "|--------|----------|--------|"]
        for lsp in c["lsp_servers"]:
            lang = ", ".join(lsp.get("language", []))
            lines.append(f"| {lsp['name']} | {lang} | ⏭️ Skipped |")
        lines.append("")

    # Monitors
    if c["monitors"]:
        lines += ["## Monitors", "", "| Monitor | Convert? | Notes |", "|---------|----------|-------|"]
        for mon in c["monitors"]:
            lines.append(f"| {mon['name']} | ⚠️ Manual setup | Needs cron job |")
        lines.append("")

    # Bin
    if c["bin"]:
        lines += ["## Bin (Executables)", "", "| File | Notes |", "|------|-------|"]
        for b in c["bin"]:
            lines.append(f"| {b['name']} | Copied to plugin dir |")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Analyze a Claude Code plugin for Hermes conversion")
    parser.add_argument("plugin_dir", help="Path to the Claude plugin directory")
    parser.add_argument("--output", "-o", help="Output JSON file path (default: stdout)")
    parser.add_argument("--report", "-r", help="Also write a markdown report to this path")
    args = parser.parse_args()

    plugin_dir = Path(args.plugin_dir).resolve()
    if not plugin_dir.is_dir():
        print(f"Error: {plugin_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    analysis = analyze_plugin(plugin_dir)

    if "error" in analysis:
        print(f"Error: {analysis['error']}", file=sys.stderr)
        sys.exit(1)

    json_output = json.dumps(analysis, indent=2, ensure_ascii=False)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json_output, encoding="utf-8")
        print(f"Analysis written to {args.output}", file=sys.stderr)
    else:
        print(json_output)

    if args.report:
        report = format_report(analysis)
        Path(args.report).write_text(report, encoding="utf-8")
        print(f"Report written to {args.report}", file=sys.stderr)


if __name__ == "__main__":
    main()