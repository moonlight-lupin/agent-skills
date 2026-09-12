# Conversion Report: acme-sample

**Source:** Claude Code plugin
**Target:** Agent Plugins package (agent-plugins.org v1.0.0)

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

### MCP Servers

| Server | Status |
|--------|--------|
| acme-validator | ✅ mcp.json entry |

## Next Steps

1. Review `plugin.json` against https://agent-plugins.org/ (closed manifest)
2. Review each `skills/<name>/SKILL.md` frontmatter (name + description)
3. Review `mcp.json` (stdio command is one token; plugin paths use `./` or `${PLUGIN_ROOT}`)
4. Copy this directory to your Agent Plugins search path
