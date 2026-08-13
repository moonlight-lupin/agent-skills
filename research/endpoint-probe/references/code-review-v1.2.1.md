# Code Review Findings — cursor-grok-4.5-high

Two review rounds on v1.2.0 → v1.2.2 (2026-07-16).

## Round 1: 4 BLOCKING, 9 MAJOR, 10 MINOR, 7 NIT

All findings applied in v1.2.1.

### BLOCKING (round 1)
- B1: stdio `readline()` no timeout → `select()` with deadline
- B2: `_send` re-sends on server notifications → discard notifications, keep reading
- B3: No SSRF protection → `ipaddress` blocklist, redirect disabled, `--allow-private`
- B4: Arbitrary command via `--mcp-stdio` → allowlist runners only

### MAJOR (round 1)
- M1: No `Mcp-Session-Id` → capture from init response, replay on all requests
- M2: `notifications/initialized` sent with `id` → omit `id`, accept 202/204
- M3: No `try/finally` cleanup → wrap post-Popen body, `_cleanup_subprocess` helper
- M4: Shared `auth_headers` mutated by threads → copy in `_make_request`
- M5: Unbounded body reads → cap at 5 MiB with truncation marker
- M6: stdio/HTTP resource parsing diverges → unified normalize functions
- M7: Hardcoded `HOME=/root` → scrubbed `os.environ` inherit
- M8: `PYTHONHTTPSVERIFY=0` myth → corrected to "does not affect urllib"
- M9: Credentials in argv → warning in SKILL.md

### MINOR (round 1, selected)
- m1: OpenAPI YAML not parsed (JSON only) — documented as limitation
- m2: gRPC-Web path-only detection — documented as limitation
- m3: `--mcp` / `--mcp-stdio` mutual exclusion added
- m4: SSE parser first-data-line only — documented as limitation
- m7: Useless `try/except ImportError` removed
- m10: Auth-header construction deduplicated via `_build_auth_headers`

### NIT (round 1, selected)
- n1: Redundant condition in well-known typing fixed
- n2: GraphQL type counts no longer added to endpoint count
- n4: USER_AGENT version aligned with skill version
- n5: `--version` renamed to `--api-version`

## Round 2: 3 BLOCKING, 7 MAJOR, 10 MINOR, 7 NIT

Fixes applied in v1.2.2. These were NEW issues introduced by round 1 fixes.

### BLOCKING (round 2)
- B1r2: `stderr.read()` hang after stdout EOF → bounded with `select()` + 2s timeout
- B2r2: IPv4-mapped IPv6 (`::ffff:127.0.0.1`) bypasses string-prefix SSRF → `ipaddress` module
- B3r2: Absolute paths bypass command allowlist → runners only, no absolute path bypass

### MAJOR (round 2)
- M1r2: `try/finally` still missing despite helper existing → real `try/finally` wrapping
- M2r2: No JSON-RPC response `id` correlation → skip responses with wrong `id`
- M3r2: Env scrub prefix-at-start misses `GITHUB_TOKEN` → substring deny-list
- M4r2: DNS rebinding TOCTOU → documented as residual risk (pinning out of scope)
- M5r2: `172.160.0.1` false-positive from string prefixes → `ipaddress` fixes
- M6r2: SKILL.md still says `--version` → `--api-version` everywhere
- M7r2: interpretation-guide.md stale → rewritten

### MINOR (round 2, selected)
- m1: SKILL.md `shutil.which()` claim removed (not used)
- m3: HTTPError body truncation marker added
- m4: Stdio soft-fail for unsupported resources/prompts aligned with HTTP
- m5: Server-to-client JSON-RPC requests now skipped (not aborted)

### NIT (round 2, selected)
- n1: Unused imports (`ssl`, `shutil`) removed
- n2: Version strings aligned to 1.2.1

## Key Lesson

**Security fixes themselves introduce new security bypasses.** String-prefix IP matching missed IPv4-mapped IPv6. Command allowlist with absolute-path bypass allowed `/bin/bash`. Cleanup helper without `try/finally` still orphaned on exceptions. Env scrub with prefix-at-start missed `GITHUB_TOKEN`. Always run a second review after security fixes — the fixes create new attack surfaces.

## Verified Working (post-v1.2.2)

| Test | Result |
|---|---|
| REST probe (Petstore) | 20 endpoints from OpenAPI ✅ |
| MCP stdio (library-rag) | 3 tools with full schemas ✅ |
| MCP HTTP (Composio) | 7 tools, session-id working ✅ |
| SSRF: `127.0.0.1` | Blocked ✅ |
| SSRF: `::ffff:127.0.0.1` | Blocked ✅ |
| SSRF: `100.64.0.1` (CGNAT) | Blocked ✅ |
| SSRF: `172.160.0.1` (public) | Allowed ✅ |
| SSRF: `8.8.8.8` (public) | Allowed ✅ |
| Allowlist: `rm` | Blocked ✅ |
| Allowlist: `python3` | Allowed ✅ |
| Mutual exclusion `--mcp --mcp-stdio` | Rejected ✅ |
| Syntax: py_compile | Clean ✅ |