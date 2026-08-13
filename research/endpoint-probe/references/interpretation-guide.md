# Interpretation Guide

Patterns observed from testing against real APIs: GitHub, Petstore Swagger, OpenRouter, OpenCode, Composio MCP, AlphaVantage MCP, library-rag MCP.

## Status Code Patterns

| Pattern | Meaning | Example |
|---|---|---|
| All 404 | API not at this URL, or auth-gated with 404-hiding | GitHub `/api/v1` base |
| All 403 + same body | Rate-limited, not auth-blocked | GitHub unauthenticated (60/60 used) |
| Mixed 200/401/403 | True auth-gated API — some paths open, some protected | Typical REST API |
| 406 Not Acceptable | MCP server needs `Accept: application/json, text/event-stream` | Composio MCP before fix |
| 401 + `WWW-Authenticate: Bearer` | OAuth2/JWT auth required | Standard OAuth2 API |
| 200 + `text/html` for every path | SPA catch-all (Next.js, Nuxt) — not real API responses | OpenRouter domain root |

## OpenAI-Compatible Inference Prefixes

If probing `https://provider.ai/v1` returns nothing, the OpenAPI spec is at the domain root (`https://provider.ai`). The `/v1` prefix is just the inference slice (`/v1/chat/completions`, `/v1/models`). Always probe the domain root.

**Tested:** OpenCode (`opencode.ai/zen/go/v1` → empty; `opencode.ai` → 188 endpoints)

## SPA Catch-All Detection

Next.js/Nuxt/SPA frameworks serve the same HTML shell for every path. Signs:
- Server fingerprint shows Next.js/Nuxt
- Most discovery paths return 200 + `text/html` with similar body lengths (±200 bytes)
- REST resource guessing returns 200 for every path

The script auto-detects this in REST resource guessing (uniform 200 + text/html + similar body lengths → discarded) and SOAP detection (WSDL returning text/html → not SOAP). Discovery paths may still show many `html-docs` entries — these are SPA routes, not real docs.

**Tested:** OpenRouter (Next.js + Cloudflare, 45 discovery paths all 200 text/html)

## MCP Transport Quirks

### StreamableHTTP (protocol 2025-06-18)
- Requires `Accept: application/json, text/event-stream` header
- May respond with SSE format (`data: {...}\n\n`) instead of plain JSON
- Composio returns SSE; AlphaVantage returns plain JSON — both work with the probe's SSE parser

### Stdio
- Server reads JSON-RPC from stdin, writes to stdout (newline-delimited)
- Read timeout via `select()` with `--timeout` deadline — no hang on silent servers
- Server→client notifications (no `id`) are discarded; response `id` is correlated
- Subprocess cleanup via `try/finally` with `_cleanup_subprocess` — always terminates even on exception
- Environment: scrubbed `os.environ` inherit — safe vars only (`PATH`, `HOME`, `USER`, `LANG`, `LC_*`, `TERM`, `SHELL`, `XDG_*`); secrets stripped by substring match (`TOKEN`, `API_KEY`, `PASSWORD`, etc.)
- Command allowlist: only `npx`, `uvx`, `python3`, `python`, `node`, `bunx` — no arbitrary paths, no `-c`/`-e`/`-p`/`--call`/`--eval`/`--exec`/`--print` inline code flags
- Body capped at 5 MiB to prevent memory DoS
- `pid` and `returncode` recorded in report for verification

### Protocol version negotiation
- Probe sends `2025-06-18` (latest). Server returns its supported version.
- AlphaVantage returned `2024-11-05` (older) — worked fine, probe reports the negotiated version.

## Performance Benchmarks

| Target | Mode | Time | Notes |
|---|---|---|---|
| Petstore Swagger | `--no-guess` | ~2s | OpenAPI found immediately |
| Petstore Swagger | Full probe | ~34s | Resource guessing adds time |
| GitHub API | Full probe | ~1.7s | Rate-limited, skipped guessing |
| OpenRouter | Full probe | ~3s | SPA detected, filtered |
| Composio MCP | `--mcp` | ~2s | SSE response parsed, 7 meta-tools (search/execute pattern) |
| AlphaVantage MCP | `--mcp` | ~5s | 129 tools, plain JSON, protocol 2024-11-05 |
| library-rag MCP | `--mcp-stdio` | ~3s | Subprocess launch + handshake, 3 tools with full schemas |

## Composio MCP Meta-Tool Pattern

Composio is a **meta-tool server** — instead of exposing 500+ individual app integrations, it exposes 7 orchestration tools that let you search for and execute any app integration dynamically. This is a different architecture from AlphaVantage (direct tools) or library-rag (direct tools).

Key tools: `COMPOSIO_SEARCH_TOOLS` (search by natural language → returns tool slugs + execution plans + pitfalls), `COMPOSIO_MULTI_EXECUTE_TOOL` (parallel execution), `COMPOSIO_GET_TOOL_SCHEMAS` (retrieve schemas by slug).

When probing a meta-tool server, the tool count will be low (7) but each tool is a gateway to hundreds of underlying integrations. The real surface is discovered at runtime via `COMPOSIO_SEARCH_TOOLS`, not at handshake time.
