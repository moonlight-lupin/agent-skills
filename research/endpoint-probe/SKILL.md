---
name: endpoint-probe
description: "Use when you need to discover an API's surface — poke a base URL to find its type (REST, GraphQL, SOAP, JSON-RPC), auth scheme, available endpoints, rate limits, and CORS policy. Also probes MCP servers (HTTP and stdio) to discover tools, resources, and prompts with full input schemas. Runs a Python probe script that checks well-known discovery paths (OpenAPI/Swagger, GraphQL introspection, health, .well-known), fingerprints the server, sends OPTIONS for CORS, detects auth from 401/403 responses, and guesses common REST resources. For MCP, performs JSON-RPC initialize handshake then tools/list, resources/list, prompts/list. Feed it a base URL or MCP server URL, optionally with auth credentials."
license: MIT
metadata:
  version: 1.2.3
  author: moonlight-lupin
  platforms: [linux]
  hermes:
    tags: [api, discovery, recon, rest, graphql, openapi, swagger, probing, mcp, json-rpc]
    related_skills: [website-scraping]
---

# Endpoint Probe

Probe a base URL to discover its API surface: type, auth, endpoints, rate limits, CORS, and server fingerprint.

## When to Use

- User gives you a base URL and asks "what API is available?" or "what endpoints does this have?"
- You need to understand an undocumented or partially-documented API before building an integration
- User asks "how does this API authenticate?" or "what auth does this endpoint need?"
- You're evaluating a third-party service and need to map its API surface
- User says "discover", "probe", "explore", or "recon" an API endpoint
- User wants to know what tools an MCP server provides before configuring it
- User asks "what does this MCP server offer?" or "what tools does MCP server X have?"

**Don't use for:**
- Scraping HTML page content (use `website-scraping`)
- QA testing of known functionality (use a QA/testing skill)
- Configuring MCP servers (use an MCP configuration skill) — this skill *discovers* MCP server surfaces, it doesn't configure them
- Monitoring an API over time (this is a one-shot discovery tool)

## Workflow

### 1. Run the probe script

```bash
python scripts/probe_api.py <base_url> [options]
```

**Options:**

| Flag | Description | Default |
|---|---|---|
| `--auth TOKEN` | Auth token/credential | none |
| `--auth-type` | `bearer`, `basic`, or `apikey` | `bearer` |
| `--header "Key: Value"` | Custom header (repeatable) | none |
| `--timeout N` | Request timeout in seconds | 10 |
| `--json` | Output raw JSON instead of formatted report | off |
| `--no-guess` | Skip REST resource guessing | off |
| `--api-version v1` | API version prefix for resource probing | none |
| `--mcp` | Probe as MCP server over HTTP (StreamableHTTP) | off |
| `--mcp-stdio` | Probe as MCP server over stdio (launch subprocess) | off |
| `--mcp-env "KEY=value"` | Env var for stdio MCP server (repeatable) | none |
| `--allow-private` | Allow probing private/internal IP addresses | off |

**Examples:**

```bash
# Basic probe — no auth
python scripts/probe_api.py https://api.example.com

# With Bearer token
python scripts/probe_api.py https://api.example.com --auth "tok_abc123"

# With API key (sends X-API-Key header)
python scripts/probe_api.py https://api.example.com --auth "key_xyz" --auth-type apikey

# Skip resource guessing (faster, less noisy)
python scripts/probe_api.py https://api.example.com --no-guess

# JSON output for programmatic use
python scripts/probe_api.py https://api.example.com --json
```

### 2. Interpret the report

The probe runs 7 phases in sequence:

1. **Server fingerprint** — identifies framework (Express, FastAPI, Django, Rails, Spring, etc.) from `Server` and `X-Powered-By` headers
2. **Well-known paths** — checks ~40 discovery paths: `/openapi.json`, `/swagger.json`, `/docs`, `/graphql`, `/.well-known/`, `/health`, `/version`, etc.
3. **GraphQL introspection** — POSTs an introspection query to `/graphql`, `/api/graphql`, `/query` and extracts types if successful
4. **OPTIONS / CORS** — sends OPTIONS to `/`, `/api`, `/api/v1` to discover allowed methods and CORS policy
5. **Auth detection** — hits likely-protected endpoints without credentials, examines 401/403 responses and `WWW-Authenticate` headers
6. **Rate limits** — checks for `X-RateLimit-*`, `RateLimit-*`, `Retry-After` headers
7. **REST resource guessing** — probes ~50 common resource paths (`/api/users`, `/api/orders`, etc.) and reports non-404 responses

### 3. Use the findings

- **OpenAPI found** → parse the spec for full endpoint list, request/response schemas, auth schemes. The probe already extracts endpoints from the spec.
- **GraphQL introspection works** → you have the full type system. Build queries from the discovered types.
- **Only REST resources found** → the API is undocumented. Use the discovered resource paths as a starting point and probe individual endpoints with GET/POST/PUT/DELETE.
- **Auth detected** → use the identified scheme for all subsequent requests.
- **Nothing found** → the API may be behind a login, use non-standard paths, or not exist at that URL. Try with auth credentials, or check if the base URL is correct.

## MCP Server Probing

The probe also supports discovering MCP (Model Context Protocol) server surfaces — tools, resources, and prompts with full input schemas. This lets you evaluate an MCP server *before* configuring it in Hermes.

### MCP over HTTP (StreamableHTTP transport)

```bash
# Probe a remote MCP server
python scripts/probe_api.py "https://mcp.example.com/mcp" --mcp

# With auth headers
python scripts/probe_api.py "https://mcp.example.com/mcp" --mcp --auth "tok_abc123"

# With custom headers
python scripts/probe_api.py "https://mcp.example.com/mcp" --mcp --header "X-API-Key: mykey"
```

### MCP over stdio (local subprocess)

```bash
# Probe a local MCP server (npx-based)
python scripts/probe_api.py "npx -y @modelcontextprotocol/server-time" --mcp-stdio

# Probe a Python-based MCP server
python scripts/probe_api.py "python3 /path/to/mcp_server.py" --mcp-stdio

# With environment variables
python scripts/probe_api.py "npx -y @modelcontextprotocol/server-github" --mcp-stdio \
  --mcp-env "GITHUB_PERSONAL_ACCESS_TOKEN=ghp_xxx"
```

### What the MCP probe discovers

The probe performs the full MCP handshake sequence:

1. **Initialize** — JSON-RPC `initialize` with protocol version, client info, and capabilities. Reports server name, version, protocol version, and server capabilities.
2. **Tools** — `tools/list` → all tool names, descriptions, and full input schemas (parameter names, types, required/optional, defaults, enums)
3. **Resources** — `resources/list` → all resource URIs, names, descriptions, and MIME types
4. **Prompts** — `prompts/list` → all prompt template names, descriptions, and arguments

### MCP vs an MCP configuration skill

| Aspect | `endpoint-probe --mcp` | MCP configuration skill |
|---|---|---|
| Purpose | Discover what a server offers | Configure & use a server |
| When | Before deciding to use a server | After deciding to use it |
| Output | Tool schemas, resources, prompts | Registered tools in the agent's toolset |
| Requires restart | No | Yes (agent restart to register) |
| Transport | HTTP and stdio | HTTP and stdio |

**Workflow:** Use `endpoint-probe --mcp` to evaluate a server → decide if useful → use an MCP configuration skill to register it → restart the agent.

## Common Pitfalls

1. **Base URL wrong or too specific.** `https://api.example.com` is correct; `https://api.example.com/v1/users/123` is too specific — the probe needs the root to discover paths. Strip trailing paths.

   **OpenAI-compatible APIs:** If the base URL is an inference endpoint like `https://provider.ai/v1` or `https://provider.ai/zen/go/v1`, the probe will find nothing because discovery paths (`/openapi.json`, `/docs`, etc.) are served from the **domain root**, not the inference prefix. Always probe the domain root (`https://provider.ai`) to find the OpenAPI spec and full API surface. The inference endpoints (`/v1/chat/completions`, `/v1/models`) are usually a small slice of a larger platform API.

2. **GraphQL introspection disabled.** Many production GraphQL APIs disable introspection for security. The probe will show status 200/400/403 with "introspection disabled" — this confirms GraphQL exists but the schema is hidden. Try sending a simple query like `{"query": "{ __typename }"}` to confirm.

3. **Auth-gated APIs return 404 instead of 401.** Some APIs return 404 for unauthenticated requests to hide endpoint existence. If everything is 404, try providing `--auth` credentials.

4. **Rate limiting during probe.** The script makes ~80-100 requests concurrently (8 threads). Most APIs tolerate this, but if you hit 429s, increase `--timeout` or use `--no-guess` to reduce request count. The script auto-detects rate-limit exhaustion (via `X-RateLimit-Remaining: 0`) and skips resource guessing to avoid false positives — check the report for `rate_limited_skipped_guessing: true`.

5. **Uniform 403 ≠ auth-gated.** If *every* discovery path returns 403 with the same error body, you're rate-limited, not auth-blocked. Check rate-limit headers (`X-RateLimit-Remaining`) before interpreting 403s as auth requirements. A true auth-gated API returns 401 (with `WWW-Authenticate`) or mixed 200/401/403 across paths, not uniform 403.

6. **403 on `/graphql` means the endpoint exists.** A 403 on `/graphql` confirms the endpoint is there but introspection is blocked — not that GraphQL is absent. A 404 means the endpoint doesn't exist. Don't conflate the two.

7. **CORS headers only on OPTIONS.** Some APIs only send CORS headers on OPTIONS preflight, not on GET. The probe checks OPTIONS separately for this reason.

8. **False positives on /health, /status.** These paths may return 200 from a load balancer or CDN even if the API itself is down. Treat them as "something is listening" not "API is healthy".

9. **Server fingerprint unreliable.** `X-Powered-By` is often stripped by proxies. The framework hints are best-effort — don't treat them as definitive.

10. **Self-signed certs.** The script uses urllib which verifies certs by default. `PYTHONHTTPSVERIFY=0` does NOT affect urllib (it only affects `requests`/`httpx`). Self-signed targets are currently unsupported — use `--allow-private` for internal hosts but self-signed TLS requires a future `--insecure` flag with a custom `ssl.SSLContext`.

11. **Concurrency is load-bearing.** The probe script uses `concurrent.futures.ThreadPoolExecutor(max_workers=8)` for both well-known paths and resource guessing. Sequential probing of ~90 paths times out against slow APIs (>120s). If you modify the script, preserve the thread pool — do not revert to sequential requests.

12. **SPA catch-all false positives.** Next.js, Nuxt, and other SPA frameworks serve the same HTML page (200 + `text/html`) for *every* path — including `/api/users`, `/health`, `/openapi.json`, etc. This floods the report with bogus "endpoints" that are just the SPA shell. The script auto-detects this in REST resource guessing (uniform 200 + text/html + similar body lengths → discarded) and guards SOAP detection (WSDL path returning text/html is not SOAP). However, the discovery-paths phase may still show many `html-docs` entries — these are SPA routes, not real API docs. If the server fingerprint shows Next.js/Nuxt and most discovery paths return 200 text/html, treat all but the OpenAPI spec (if found) as SPA noise.

13. **MCP stdio server hangs.** Some MCP servers don't exit cleanly on stdin close. The probe sends `terminate()` then waits 5s before `kill()`. If a server ignores SIGTERM, the probe may take 5s longer. This is expected — the probe always cleans up.

14. **Reports redact credential values, not auth protocol.** Auth detection still surfaces scheme (`Bearer`, `Basic`, `WWW-Authenticate`, “API key required”, cookie **names**). Echoed `Authorization` / `X-API-Key` values, `Set-Cookie` values, and token-shaped strings in error bodies are replaced with `***` so reports/logs stay shareable. If a header looks “empty” of secrets, check for `***` — that means a secret was present and scrubbed.

15. **MCP protocol version mismatch.** The probe sends protocol version `2025-06-18`. Older MCP servers may use `2024-11-05` — the server negotiates and returns its supported version in the response. The probe reports the negotiated version in the summary. If initialize fails with a protocol error, the server may require an older version.

16. **MCP HTTP endpoint URL.** MCP over HTTP uses a single endpoint URL (e.g. `https://mcp.example.com/mcp`), not path-based routing. All JSON-RPC requests go to the same URL via POST. Don't append `/tools/list` or similar — the `--mcp` flag handles this correctly.

17. **MCP resources/prompts may be unsupported.** Not all MCP servers implement resources or prompts. The probe gracefully handles `method not found` errors and reports "None" for unsupported primitives. This is not an error — it means the server only implements tools.

18. **MCP StreamableHTTP requires Accept header.** Modern MCP servers (protocol 2025-06-18) use the StreamableHTTP transport, which requires `Accept: application/json, text/event-stream` in request headers. Without it, the server returns 406 Not Acceptable. The probe sends this header automatically.

19. **MCP SSE response format.** StreamableHTTP servers may respond with `text/event-stream` (SSE) format — `data: {"jsonrpc":"2.0","result":{...}}` — instead of plain JSON. The probe auto-detects and extracts JSON from SSE `data:` lines. If you see "Non-JSON response" errors against an MCP server, the SSE parser may need updating.

20. **Credentials exposed via process argv.** Tokens passed via `--auth`, `--mcp-env`, and `--header` appear in `ps`, shell history, and agent logs. For basic auth, `--auth` must be `user:password` (not just the password). Prefer reading credentials from environment variables or `.env` files when possible. The SKILL.md examples use redacted tokens — never use real tokens in examples.

21. **SSRF protection.** The probe blocks private/internal IP ranges (RFC1918, loopback, link-local, CGNAT `100.64/10`, ULA `fc00::/7`, IPv4-mapped IPv6 like `::ffff:127.0.0.1`) and cloud metadata endpoints (`169.254.169.254`). Uses `ipaddress` module for accurate detection — no brittle string prefixes. Redirects are disabled to prevent redirect-based SSRF. Use `--allow-private` to override (e.g. probing `localhost` for local dev APIs). When probing returns all connection errors and the target is internal, check for the `ssrf_warning` field in the JSON report.

22. **Command allowlist for `--mcp-stdio`.** Only known package runners (`npx`, `uvx`, `python3`, `python`, `node`, `bunx`) are allowed — no arbitrary commands or absolute paths. This prevents prompt-injected "MCP server" strings from executing arbitrary commands.

23. **Body size capped at 5 MiB.** Response bodies are capped at 5 MiB to prevent memory DoS. Truncated responses include `[truncated at 5 MiB]` in the body. If an OpenAPI spec or GraphQL schema exceeds this, it will be incomplete.

24. **MCP session-ID support.** The probe captures `Mcp-Session-Id` from the initialize response and replays it on all subsequent requests. This is required by sessionful StreamableHTTP servers. Stateless servers (Composio, AlphaVantage) ignore the header.

25. **MCP stdio inherits scrubbed environment.** The subprocess inherits a scrubbed copy of `os.environ`: only safe vars (`PATH`, `HOME`, `USER`, `LANG`, `LC_*`, `TERM`, `SHELL`, `XDG_*`) are kept; anything containing secret substrings (`TOKEN`, `SECRET`, `PASSWORD`, `API_KEY`, `CREDENTIAL`, `PRIVATE_KEY`, `ACCESS_KEY`, `CLIENT_SECRET`) is stripped. Pass secrets explicitly via `--mcp-env`. macOS works if `npx`/`node` are on the inherited `PATH` — set `PATH` via `--mcp-env` if needed.

26. **`--mcp` and `--mcp-stdio` are mutually exclusive.** The CLI rejects both flags together. If you need to try both transports for the same server, run two separate commands.

## Known Limitations (remaining after v1.2.3 fixes)

- **OpenAPI YAML specs not parsed.** `/openapi.yaml` is probed but only JSON is parsed. YAML specs show as generic 200 findings. Workaround: convert to JSON or use a tool that reads YAML.
- **gRPC-Web detection is path-only.** The probe checks gRPC paths via GET — no content-type or Connect protocol checks. Expect path heuristics only, not real gRPC-Web detection.
- **SSE parser is first-data-line only.** Multiline `data:` frames or multiple JSON-RPC messages in one SSE stream may not parse correctly. Most MCP servers send one message per SSE event — if not, the parser may need updating.
- **Stdio platform support.** macOS works if `npx`/`node` are on `PATH` (the env is inherited from the current process). Windows is untested for stdio MCP.
- **DNS rebinding TOCTOU.** The hostname is resolved once at validation; urllib resolves again at connect time. A public DNS answer at check time and private answer at connect time can bypass SSRF. For hostile DNS environments, IP pinning would be needed — currently out of scope.
- **Allowlisted runners can still pull remote packages.** `npx -y pkg` downloads and executes code from npm. The allowlist prevents arbitrary commands but not supply-chain attacks via package names.
- **Inline code flags blocked.** `-c`, `-e`, `-p`, `--call`, `--eval`, `--exec`, `--print` are rejected on all runners to prevent inline RCE via prompt-injected command strings.

## Verification Checklist

- [ ] Base URL is the API root (no trailing path like `/v1/users/123`)
- [ ] Auth credentials provided if the API requires authentication
- [ ] Report shows at least one non-404 discovery path
- [ ] If OpenAPI found: endpoints list is non-empty
- [ ] If GraphQL found: introspection result is clearly success or failure
- [ ] Auth scheme identified (or confirmed as "none/open")
- [ ] Rate limit headers checked (or confirmed absent)
- [ ] No 429 errors during the probe run
- [ ] If REST RESOURCES section is empty but discovery found many 200 text/html paths: check server fingerprint for Next.js/Nuxt — SPA catch-all likely filtered the false positives
- [ ] If MCP mode: initialize handshake succeeded (status = "connected")
- [ ] If MCP mode: tool count > 0 (or tools_error explains why)
- [ ] If MCP stdio: subprocess was cleaned up (no orphaned processes)

## References

- **`references/interpretation-guide.md`** — report interpretation patterns from testing against real APIs (GitHub, Petstore, OpenRouter, OpenCode, Composio MCP, AlphaVantage MCP, library-rag MCP). Status code patterns, SPA catch-all detection, OpenAI-compatible inference prefix issue, OpenAPI spec nuances, CORS caveats, MCP protocol negotiation, Composio meta-tool pattern, and performance benchmarks. Read when the probe report is ambiguous or you need to interpret unexpected status codes.
- **`references/code-review-history.md`** — full 6-round review history (R1-R6) with convergence table, key patterns (denylist regression, cross-model diversity, claimed-but-not-applied fixes), and Codex sandbox notes. Read before modifying the script or when debugging security issues.
