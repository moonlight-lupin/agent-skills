# Conversion Report: acme-sample

**Source:** Claude Code plugin
**Target:** Hermes plugin

## Summary

| Status | Count |
|--------|-------|
| ✅ Converted | 2 |
| ⚠️ Partial | 0 |
| ⏭️ Skipped | 0 |
| **Total** | 2 |

## Conversion Results

### Skills

| Skill | Status | Issues |
|-------|--------|--------|
| greet | ✅ | None |

### Agents → Delegation Skills

| Agent | Status |
|-------|--------|

### Hooks

| Claude Event | Hermes Event | Status |
|-------------|-------------|--------|

### MCP Servers

| Server | Status |
|--------|--------|
| acme-validator | ✅ Config generated |

### Commands

| Command | Status |
|---------|--------|

## Next Steps

1. Review `MANUAL_STEPS.md` for items needing manual attention
2. Copy this plugin to `~/.hermes/plugins/`
3. Enable: `hermes plugins enable acme-sample`
4. If MCP servers exist, merge `mcp_config.yaml` into `~/.hermes/config.yaml`
5. Restart your session (`/reset` in CLI or `/restart` in gateway)