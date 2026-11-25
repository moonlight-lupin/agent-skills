# Full Mapping Tables

## Contents

- Hook Event Mapping (Complete)
- Hook Type Mapping
- Agent Frontmatter Mapping
- Manifest Field Mapping
- MCP Config Format Mapping

## Hook Event Mapping (Complete)

| Claude Event | Hermes Hook | Convertibility | Notes |
|---|---|---|---|
| `SessionStart` | `on_session_start` | ✅ | Direct match. New session created. |
| `SessionEnd` | `on_session_end` | ✅ | Direct match. Session ends. |
| `Setup` | ❌ | ⏭️ | No Hermes equivalent (CI/one-time prep). |
| `UserPromptSubmit` | `pre_llm_call` | ✅ | Both fire before LLM processes. Hermes can inject context via `{"context": str}`. |
| `UserPromptExpansion` | ❌ | ⏭️ | No command expansion equivalent. |
| `PreToolUse` | `pre_tool_call` | ✅ | Both can block. Claude uses `matcher` field; Hermes checks `tool_name` param. Return `{"action": "block", "message": str}` to veto. |
| `PermissionRequest` | `pre_approval_request` | ✅ | Similar concept — approval prompt about to fire. |
| `PermissionDenied` | `post_approval_response` | ✅ | Similar — user responded to approval. |
| `PostToolUse` | `post_tool_call` | ✅ | Direct match. After tool returns. |
| `PostToolUseFailure` | `post_tool_call` | ⚠️ | Same hook, check `result` for error content. No separate failure hook in Hermes. |
| `PostToolBatch` | ❌ | ⏭️ | No batch-level hook in Hermes. |
| `Notification` | `on_session_prompt` / `on_session_prompt_settled` / `on_human_input_request` | ⚠️ | Covers approval/sudo/secret prompt events (observer). No generic desktop-notification hook. |
| `MessageDisplay` | `transform_llm_output` | ⚠️ | Closest match — can transform output before delivery. Different semantics. |
| `SubagentStart` | `subagent_start` | ✅ | Direct match. delegate_task child about to run. |
| `SubagentStop` | `subagent_stop` | ✅ | Direct match. delegate_task child finished. |
| `TaskCreated` | ❌ | ⏭️ | No task-creation hook. Nearest concept: kanban task observers (`kanban_task_*`, `on_kanban_task_updated`) — different lifecycle. |
| `TaskCompleted` | ❌ | ⏭️ | No task-completion hook. Nearest concept: `kanban_task_completed` — different lifecycle. |
| `Stop` | `post_llm_call` | ⚠️ | Closest match. Fires after tool-calling loop, before final response delivered. |
| `StopFailure` | `api_request_error` / `transform_api_error_classification` | ⚠️ | API/provider failures; the transform hook can steer retry/failover classification. |
| `TeammateIdle` | ❌ | ⏭️ | No agent-teams equivalent in Hermes. |
| `InstructionsLoaded` | ❌ | ⏭️ | No context-file-loaded hook. |
| `ConfigChange` | ❌ | ⏭️ | No config-change hook. |
| `CwdChanged` | ❌ | ⏭️ | No cwd-change hook. |
| `FileChanged` | ❌ | ⏭️ | No file-watcher hook. |
| `WorktreeCreate` | ❌ | ⏭️ | No worktree hook. |
| `WorktreeRemove` | ❌ | ⏭️ | No worktree hook. |
| `PreCompact` | ❌ | ⏭️ | No pre-compaction hook. |
| `PostCompact` | `post_compaction` | ⚠️ | Observer, once per committed compaction. (No pre-compaction hook, so `PreCompact` stays unmapped.) |
| `Elicitation` | `pre_approval_request` | ⚠️ | `pre_approval_request` carries a `surface` field including `mcp-elicitation/<server>`. Observer only. |
| `ElicitationResult` | `post_approval_response` | ⚠️ | Fires with `choice`/`decided_by` when the approval response lands. |

**Summary: 10 direct matches, 9 partial, 11 no equivalent.**

Hermes column checked 2026-11-25 against installed-core `VALID_HOOKS` (`hermes_cli/plugins.py`) — 50 events at that date. Recheck against source when converting; the set grows.

## Hook Type Mapping

| Claude Type | Implementation | Notes |
|---|---|---|
| `command` | `subprocess.run(command, shell=True, ...)` in Python callback | Translate `${CLAUDE_PLUGIN_ROOT}` to plugin dir. Alternative: a shell hook in `config.yaml` (`hooks:` block) — Hermes shell hooks use the Claude Code wire format with exit code 2 = block; supported events = `VALID_HOOKS` minus `transform_api_error_classification`. |
| `http` | `httpx.post(url, json=event_data, timeout=...)` in Python callback | Event data = the context dict. |
| `mcp_tool` | `ctx.dispatch_tool(tool_name, args)` in Python callback | Strip plugin namespace from tool names. |
| `prompt` | ⏭️ No equivalent | Note in MANUAL_STEPS. Could spawn one-shot AIAgent. |
| `agent` | ⏭️ No equivalent | Note in MANUAL_STEPS. Could use delegate_task. |

## Agent Frontmatter Mapping

| Claude Field | Hermes Handling | Notes |
|---|---|---|
| `name` | Skill name | Used in `ctx.register_skill()` |
| `description` | Skill description | Copied to SKILL.md frontmatter |
| `model` | Noted in delegation skill | Hermes uses `delegate_task` which inherits parent model. Note as config hint. |
| `effort` | Noted in delegation skill | No direct equivalent. |
| `maxTurns` | Noted in delegation skill | Map to `delegation.max_iterations` concept. |
| `tools` | Noted in delegation skill | If restricted, note which tools to pass. |
| `disallowedTools` | Noted in delegation skill | If specified, note which tools to block. |
| `skills` | Bundled alongside | If agent references skills, copy them too. |
| `memory` | ❌ | No per-agent memory in Hermes. Note in report. |
| `background` | ❌ | No background-agent flag. Note in report. |
| `isolation` | Noted | `worktree` isolation maps to Hermes `-w` flag. |

## Manifest Field Mapping

| Claude `plugin.json` | Hermes `plugin.yaml` | Notes |
|---|---|---|
| `name` | `name` | Direct copy. Used as plugin identifier. |
| `description` | `description` | Direct copy. |
| `version` | `version` | Direct copy. |
| `author.name` | `author` | Flatten to string. |
| `author` | `author` | If string, direct copy. |
| `homepage` | `homepage` | Direct copy (optional). |
| `repository` | `repository` | Direct copy (optional). |
| `license` | `license` | Direct copy (optional). |
| (missing) | `provides_tools` | Generated from MCP servers if present. |
| (missing) | `provides_hooks` | Generated from hooks.json if present. |
| (missing) | `requires_env` | Inferred from MCP server env vars. |

## MCP Config Format Mapping

Claude `.mcp.json`:
```json
{
  "mcpServers": {
    "server-name": {
      "command": "${CLAUDE_PLUGIN_ROOT}/servers/db-server",
      "args": ["--config", "config.json"],
      "env": { "DB_PATH": "/data" }
    }
  }
}
```

Hermes `mcp_config.yaml`:
```yaml
mcp_servers:
  server-name:
    command: /path/to/servers/db-server
    args: ["--config", "config.json"]
    env:
      DB_PATH: /data
```

Key differences:
- `${CLAUDE_PLUGIN_ROOT}` → absolute path to plugin directory
- `mcpServers` (camelCase) → `mcp_servers` (snake_case)
- JSON → YAML

## Portable Packages — When Conversion Is Unnecessary

Hermes installs Claude-style Agent Plugins v1 (`plugin.json`) packages natively. The portable subset: `plugin.json` + `skills/*/SKILL.md` directories + a root `mcp.json` (stdio MCP servers). No conversion needed.

Hooks are NOT in the portable subset. Check the source plugin first: if it contains only skills and MCP servers, use a native install. Hooks, commands, agents, and monitors still need this converter.