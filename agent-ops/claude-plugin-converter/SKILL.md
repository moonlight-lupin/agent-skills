---
name: claude-plugin-converter
description: Convert Claude Code plugins into self-contained Hermes plugins — discovery analysis then full conversion
version: 1.0.0
author: moonlight-lupin
license: MIT
---

# Claude Plugin Converter

Convert a Claude Code plugin (`.claude-plugin/plugin.json` manifest + components) into a self-contained, installable Hermes plugin (`plugin.yaml` + `__init__.py` + bundled skills/hooks).

## When to Use

- User wants to use a Claude Code plugin with Hermes Agent
- User says "convert this Claude plugin" or "make this work with Hermes"
- User provides a Claude plugin directory, git URL, or marketplace reference

## Overview

Two-phase workflow:

1. **Discovery** — analyze the Claude plugin, report what can/can't be converted
2. **Conversion** — generate a complete Hermes plugin directory the user can install with `hermes plugins enable <name>`

The output is a **single self-contained Hermes plugin** — skills, hooks, and MCP config all bundled inside one `~/.hermes/plugins/<name>/` directory. Not scattered artifacts.

## ⚠️ Security & Trust Boundary

**Only convert plugins from sources you trust.** The converter reads shell commands, Python hooks, and MCP server configurations from the source plugin and reproduces them in the Hermes output. Converted hooks may execute shell commands from the source plugin via `subprocess.run(..., shell=True, ...)`.

Before enabling a converted plugin:
- **Review `hooks.py`** — inspect every `subprocess.run` call and `_CMD_*` variable for dangerous commands
- **Review `__init__.py`** — check what's registered (tools, hooks, slash commands)
- **Review `mcp_config.yaml`** — verify MCP server commands and env vars are safe
- **Review `MANUAL_STEPS.md`** — understand what the converter couldn't automate

**Do not** blindly convert and enable plugins from untrusted GitHub repos or marketplaces without reviewing the generated output first.

## Phase 1: Discovery

Run the analysis script:

```bash
python3 {SKILL_DIR}/scripts/analyze.py <claude_plugin_dir> --output <output_dir>/analysis.json
```

The script reads `.claude-plugin/plugin.json` and all component directories, producing structured JSON with convertibility assessments for each component.

Present the findings to the user as a table showing:
- What converts cleanly (✅)
- What converts partially (⚠️)
- What has no Hermes equivalent (⏭️)

See `references/mapping-tables.md` for the full component → component mapping.

## Phase 2: Conversion

After user approval, run the conversion script:

```bash
python3 {SKILL_DIR}/scripts/convert.py <claude_plugin_dir> --analysis <output_dir>/analysis.json --output <output_dir>/<plugin_name>
```

This generates a complete Hermes plugin directory:

```
<plugin_name>/
├── plugin.yaml              # Translated manifest
├── __init__.py              # register(ctx) — wires tools, hooks, skills, commands
├── schemas.py               # Tool schemas (if MCP servers had custom tools)
├── tools.py                 # Tool handlers (if any)
├── hooks.py                 # Hook callback functions (only if hooks exist)
├── skills/                  # Bundled skills (registered via ctx.register_skill)
│   └── <skill-name>/
│       └── SKILL.md
├── engines/                 # Non-skill data dirs copied from source (engines, foundations, etc.)
├── foundations/
├── connectors/
├── mcp_config.yaml          # MCP server config snippet (for user to merge)
├── CONVERSION_REPORT.md     # Full report: converted, partial, skipped, manual steps
└── MANUAL_STEPS.md           # What the user must do by hand
```

## Installation

After conversion, install the plugin:

```bash
cp -r <output_dir>/<plugin_name> ~/.hermes/plugins/
hermes plugins enable <plugin_name>
# Then restart: /reset in CLI or /restart in gateway
```

If the plugin has MCP servers, merge `mcp_config.yaml` into `~/.hermes/config.yaml`:
```bash
cat <plugin_name>/mcp_config.yaml >> ~/.hermes/config.yaml
# Or use: hermes mcp add <name> --command <cmd> --args <args>
```

## Component Mapping Summary

| Claude Component | Hermes Target | Location | Convertibility |
|---|---|---|---|
| Manifest (`plugin.json`) | `plugin.yaml` | Plugin root | ✅ Direct field mapping |
| Skills (`skills/*/SKILL.md`) | Bundled skills | `skills/*/SKILL.md` + `ctx.register_skill()` | ✅ Frontmatter remap |
| Commands (`commands/*.md`) | Slash commands | `ctx.register_command()` in `__init__.py` | ⚠️ Simpler format, needs wrapping |
| Hooks (`hooks/hooks.json`) | Plugin hooks | `hooks.py` + `ctx.register_hook()` | ⚠️ ~10/30 events have equivalents |
| Agents (`agents/*.md`) | Delegation skills | `skills/<agent-name>/SKILL.md` | ⚠️ Paradigm shift |
| MCP servers (`.mcp.json`) | MCP config | `mcp_config.yaml` snippet | ✅ Config format translation |
| LSP servers (`.lsp.json`) | ❌ No equivalent | — | ⏭️ Skipped, noted in report |
| Monitors (`monitors/*.json`) | Cron jobs | Noted in MANUAL_STEPS.md | ⚠️ Different concept, manual setup |
| `bin/` (PATH executables) | Plugin data files | Copied into plugin dir | ✅ Low priority |

## Frontmatter Mapping (SKILL.md)

| Claude Field | Hermes Field | Notes |
|---|---|---|
| `description` | `description` | Direct copy |
| `name` | `name` | Direct copy (used for `ctx.register_skill`) |
| `disable-model-invocation` | ❌ | No equivalent — Hermes skills are always model-invoked. Remove and note. |
| `$ARGUMENTS` (in body) | ❌ | No placeholder equivalent. Rewrite to reference "the user's request" or flag for manual review. |
| (missing) | `version` | Inherit from plugin.json version |
| (missing) | `author` | Inherit from plugin.json author |

## Hook Event Mapping

See `references/mapping-tables.md` for the complete 30+ event mapping table.

Key mappings:
- `PreToolUse` → `pre_tool_call` (both can block)
- `PostToolUse` → `post_tool_call`
- `SessionStart` → `on_session_start`
- `SessionEnd` → `on_session_end`
- `UserPromptSubmit` → `pre_llm_call` (both can inject context)
- `SubagentStart` → `subagent_start`
- `SubagentStop` → `subagent_stop`
- `Stop` → `post_llm_call` (closest match)
- `PermissionRequest` → `pre_approval_request`

Events with no Hermes equivalent: `PostToolBatch`, `PreCompact`, `PostCompact`, `Notification`, `FileChanged`, `WorktreeCreate/Remove`, `CwdChanged`, `InstructionsLoaded`, `ConfigChange`, `TeammateIdle`, `Elicitation`, `TaskCreated/Completed`.

## Hook Type Mapping

| Claude Hook Type | Hermes Implementation | Notes |
|---|---|---|
| `command` (shell) | Python callback in `hooks.py` using `subprocess` | Or shell hook in config.yaml |
| `http` (POST to URL) | Python callback using `httpx.post()` | Straightforward |
| `mcp_tool` (call MCP tool) | Python callback using `ctx.dispatch_tool()` | Map scoped tool names |
| `prompt` (LLM eval) | ⚠️ No direct equivalent | Note in MANUAL_STEPS — could spawn one-shot agent |
| `agent` (agentic verifier) | ⚠️ No direct equivalent | Note in MANUAL_STEPS — could use `delegate_task` |

## Agent → Delegation Skill Conversion

Claude agents are markdown files with a system prompt + frontmatter (model, effort, maxTurns, tools).

Hermes has no standalone agent definitions. Instead, each agent becomes a **bundled skill** that instructs the agent to use `delegate_task`:

```markdown
---
name: <agent-name>
description: <from Claude agent description>
---

# <Agent Name>

When the user's task matches this agent's specialty, delegate it:

1. Call `delegate_task` with:
   - `goal`: "<from Claude agent description>"
   - `context`: "<full system prompt from the Claude agent .md file>"
2. Do not attempt the task yourself — delegate it.

## Original Agent Config
- Model: <from frontmatter>
- MaxTurns: <from frontmatter>
- Tools: <from frontmatter, if restricted>
```

## Pitfalls

1. **`$ARGUMENTS` has no Hermes equivalent** — Claude skills use `$ARGUMENTS` for user input. Hermes skills are loaded into context and the agent reads the user's message naturally. Flag for manual review.

2. **`disable-model-invocation`** — Claude lets skills be manual-only. Hermes skills are always model-invoked. Remove the field, note it.

3. **Agent paradigm shift** — Claude has standalone agent definitions. Hermes uses `delegate_task` at runtime. The converter wraps each agent as a delegation skill, but the behavior won't be identical.

4. **Many hook events have no Hermes equivalent** — ~20 of 30 Claude events can't be converted. The report lists them clearly.

5. **`prompt` and `agent` hook types** — No direct Hermes equivalent. These are noted in MANUAL_STEPS for the user to implement manually if needed.

6. **LSP servers** — Hermes has no LSP integration. Skipped, noted in report.

7. **`${CLAUDE_PLUGIN_ROOT}` appears in skill body text, not just hooks** — Claude skills use `${CLAUDE_PLUGIN_ROOT}` in markdown links and inline code to reference files in the plugin tree (e.g. `[`${CLAUDE_PLUGIN_ROOT}/foundations/doctrine.md`](../../foundations/doctrine.md)`). A real plugin had 120 occurrences across 21 skills. The converter replaces `${CLAUDE_PLUGIN_ROOT}` with `..` (relative path from `skills/<name>/` to plugin root). For Python hooks, use `Path(__file__).parent` instead.

8. **MCP server scoped names** — Claude uses `mcp__plugin_<plugin-name>_<server-name>__<tool>`. Hermes uses `mcp__<server-name>__<tool>` (no plugin namespace). The converter must strip the plugin namespace prefix.

9. **Commands vs Skills** — Claude `commands/` are simpler than `skills/` (flat markdown, no frontmatter). Hermes slash commands need a Python handler. The converter wraps each command as a `ctx.register_command()` that returns the markdown content as a prompt.

10. **Non-skill data directories must be copied** — Claude plugins often ship support directories (`engines/`, `foundations/`, `connectors/`, `docs/`) that skills reference via relative paths. These must be copied into the Hermes plugin output directory alongside the converted skills, or all relative links break. The converter skips `.git`, `__pycache__`, `.pytest_cache`, `tests`, and hidden dirs but copies everything else.

11. **Conditional hooks import in `__init__.py`** — When a Claude plugin has no hooks, the generated `__init__.py` must NOT import a `hooks` module. The converter checks `analysis["components"]["hooks"]` and only generates the `from . import hooks` line when hooks exist.

## Verification

After conversion, verify the plugin loads:

```bash
# Copy to plugins dir (if not already there)
cp -r <output_dir>/<plugin_name> ~/.hermes/plugins/

# Check it's discovered
HERMES_PLUGINS_DEBUG=1 hermes plugins list

# Enable and test
hermes plugins enable <plugin_name>
# Then test skill loading (plugin skills are opt-in, not in available_skills):
hermes chat -q 'Load skill "plugin-name:skill-name" and tell me what it does' -t skills
```

Plugin skills are **opt-in** (not listed in `<available_skills>`). They load via `skill_view("plugin-name:skill-name")`. This is expected — not a conversion failure.

## Pitfalls: Parser Bugs (found in testing)

12. **`monitors.json` can be a bare list** — not always `{"monitors": [...]}`. The analyzer must handle `isinstance(monitors_data, list)` and use it directly, falling back to `.get("monitors", [])` for the dict case.

13. **Claude `hooks.json` has a nested layout** — each event entry contains a `hooks` array inside it: `{"Stop": [{"hooks": [{"type": "command", "command": "..."}]}]}`. The analyzer must iterate `hook_entry.get("hooks", [])` for the inner hook definitions, not read `type`/`command` from the outer entry directly. The outer entry may also have a `matcher` field that applies to all inner hooks. Fall back to flat layout (reading `type`/`command` from the entry itself) when no inner `hooks` array is present.

14. **Hook callback names must be threaded from `convert_hooks()` to `generate_init_py()`** — `convert_hooks()` generates callback function names (e.g. `_on_post_llm_call_0`) and returns them in `hook_infos`, but `generate_init_py()` needs those names to emit `ctx.register_hook()` calls. Pass them as a `{event_name: [callback_name, ...]}` dict. If you skip this, `__init__.py` has an empty hooks section and no hooks fire.

15. **Shell commands with complex quoting break manual escaping** — Claude hook commands often contain nested single quotes, double quotes, and backslashes (e.g. `python3 -c "import os; os.environ.get('CLAUDE_PLUGIN_ROOT')..."`). Never manually escape these with `.replace("'", "\\'")` — it produces invalid Python. Use Python's `repr()` (the `!r` format spec) to generate a safely-quoted module-level variable, then reference that variable in `subprocess.run()`: store as `_CMD_0 = {command!r}` then `subprocess.run(_CMD_0, shell=True, ...)`.

## Verification Checklist

1. Run `python3 -c "import py_compile; py_compile.compile('hooks.py', doraise=True)"` on every generated `.py` file
2. Install the plugin: `cp -r <name> ~/.hermes/plugins/ && hermes plugins enable <name>`
3. Check logs for load failures: `grep -i "failed to load plugin" ~/.hermes/logs/agent.log`
4. Test skill loading: `hermes chat -q 'Load skill "plugin-name:skill-name" and tell me what it does' -t skills`
5. Plugin skills are opt-in (not in `<available_skills>`) — loading via `skill_view("plugin:skill")` is the correct test, NOT checking if it appears in skills_list

## Tested Against

- A 21-skill accounting-style plugin (Python engines, foundations, connectors) — all 21 skills converted cleanly, 120 `${CLAUDE_PLUGIN_ROOT}` refs rewritten, data dirs copied, plugin loaded and skill_view confirmed working.

- A 51-skill multi-component plugin (6 agents, 2 hooks, 1 monitor, bin/) — 51 skills converted, 6 agents → delegation skills, 2 Stop hooks → post_llm_call, monitor noted for manual cron. Hit 4 bugs (monitors.json list format, nested hooks layout, callback name threading, shell quoting) — all fixed in scripts. Plugin loaded, skill_view confirmed working for both regular and delegation skills.