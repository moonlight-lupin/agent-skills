# Code Review History — api-discovery v1.2.3

6 rounds of iterative review→fix→re-review (2026-07-16).

## Reviewers

| Round | Reviewer | Model | Fixer |
|---|---|---|---|
| R1 | cursor-grok-4.5-high | Grok 4.5 | Orchestrator (GLM-5.2) |
| R2 | cursor-grok-4.5-high | Grok 4.5 | Orchestrator (GLM-5.2) |
| R3 | cursor-grok-4.5-high | Grok 4.5 | Orchestrator (GLM-5.2) |
| R4 | cursor-grok-4.5-high | Grok 4.5 | Codex 5.6 (gpt-5.5) |
| R5 | cursor-grok-4.5-high | Grok 4.5 | Orchestrator (GLM-5.2) |
| R6 | claude-opus-4.8 | Opus 4.8 | Orchestrator (GLM-5.2) |

## Findings by round

### R1 (4 BLOCKING, 9 MAJOR, 10 MINOR, 7 NIT)
- B1: stdio readline() no timeout — hang forever
- B2: _send re-sends on server notifications
- B3: No SSRF protection
- B4: --mcp-stdio launches arbitrary commands
- M1-M9: No Mcp-Session-Id, notification with id, no try/finally, shared header mutation, unbounded body, stdio/HTTP parse divergence, hardcoded root env, wrong TLS docs, credential exposure

### R2 (3 BLOCKING, 7 MAJOR, 10 MINOR, 7 NIT)
- B1: stderr.read() unbounded hang
- B2: IPv4-mapped IPv6 SSRF bypass
- B3: Absolute path allowlist bypass
- M1-M7: No try/finally, no id correlation, env scrub misses common secrets, DNS TOCTOU, 172.16 false positives, SKILL.md --version, stale interpretation-guide

### R3 (2 BLOCKING, 5 MAJOR, 10 MINOR, 7 NIT)
- B1: 0.0.0.0/:: unspecified not blocked
- B2: interpretation-guide still stale (claimed fixed but wasn't)
- M1-M5: -c/-e flags still RCE-capable, stdio soft-fail not applied, DNS TOCTOU undocumented, docstring --version, BrokenPipe crash

### R4 (1 BLOCKING, 3 MAJOR, 6 MINOR, 5 NIT) — fixed by Codex 5.6
- B1: except block KeyError on summary (report defaults not initialized)
- M1: stdio soft-fail for method-not-found
- M2: dangerous flag exact-token only (-cprint(1) bypasses)
- M3: version strings 1.2.2 vs 1.2.3

### R5 (1 BLOCKING, 2 MAJOR, 2 MINOR, 4 NIT)
- B1: npx --call bypasses denylist
- M1: --mcp-env NODE_OPTIONS RCE
- M2: soft-fail "not found" too broad

### R6 (1 BLOCKING, 0 MAJOR, 2 MINOR, 2 NIT) — claude-opus-4.8
- B1: Python short-flag clustering (python3 -Ic "code") bypasses all prefix checks
  - Root cause: CPython _PyOS_GetOpt allows clustering no-argument flags before -c
  - Fix: regex `^-[A-Za-z]*[cep]([=].*)?$` catches clustered flags
  - Also added glued-code regex `^-c\S+$|^-e\S+$|^-p\S+$`

## Key patterns

1. **Denylist regression** — each denylist fix opened a new bypass (R3→R4→R5→R6). Final fix used regex instead of prefix matching.
2. **Cross-model diversity** — Opus 4.8 caught the clustering bypass that Grok missed for 5 rounds. Different model = different parser mental model.
3. **Claimed-but-not-applied fixes** — R3 B2 (interpretation-guide) and R4 M1 (stdio soft-fail) were claimed fixed but weren't. Always verify by reading the actual file.
4. **Codex sandbox** — skills-directory paths need `--sandbox danger-full-access` (bwrap mount fails with --full-auto).