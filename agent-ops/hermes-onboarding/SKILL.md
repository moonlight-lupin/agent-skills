---
name: hermes-onboarding
description: "Use when onboarding a new customer — configure gateway, dashboard, memory, services for production."
license: MIT
metadata:
  version: 1.3.0
  author: moonlight-lupin
  platforms: [linux]
  tags: [onboarding, setup, configuration, deployment, customer]
---


# Hermes Onboarding

Configure a fresh Hermes Agent from a working base chat to a production-ready deployment.

**Precondition:** Hermes is installed and the main model + provider are configured. Verify with `hermes doctor`. If the agent cannot complete a normal chat, stop here and fix the provider first.

**Leading word:** *onboard* — configure every layer before declaring the setup complete.

## When to Use

- A customer has a fresh Hermes install with a working base chat and needs full configuration
- An operator is setting up Hermes on a new VPS or machine for production use
- A customer wants to go from "it works" to "it is secured, memory-enabled, always-on, and maintained"

Do not use if the main model is not yet configured. Fix the provider first.

## Step 0 — Load references

Load `references/setup-details.md`. It holds config snippets, systemd templates, DonSeTch MCP config, skill guardrail principles, and verbosity examples.

**Done:** references file loaded into context.

## Step 1 — Detect environment

Run the detection block from `references/setup-details.md` § Detection. Collect:

| Item | How |
|------|-----|
| OS | `uname -a` |
| systemd | `systemctl --version` |
| Docker | `docker --version` |
| root vs user | `whoami` |
| container vs bare metal | `head -5 /proc/1/cgroup` |
| Hermes path | `which hermes` |
| Hermes version | `hermes --version` |
| Main model vision | Check model capabilities via provider docs or test with `vision_analyze` |

**Done:** all 8 items detected and recorded. No user input required.

## Step 2 — Ask up-front questions

Ask the customer 3 questions in one batch:

1. **Customer name** — used for profile name and soul.md identity
2. **Timezone** — IANA timezone (e.g. Asia/Singapore, America/New_York)
3. **Gateway platform(s)** — Telegram, Discord, WhatsApp, Slack, Signal. Collect bot tokens or pairing info. Tokens are stored in `~/.hermes/.env` (chmod 600). Do not paste tokens into chat transcripts.

If Step 1 detected the main model lacks vision, add a 4th question:

4. **Vision-capable aux model** — which model + provider for vision tasks? Default: same provider as main.

**Done:** all up-front questions answered. Conditional vision question asked only if needed.

## Step 3 — Alternative providers and aux models

| Task | Command | Default |
|------|---------|---------|
| Aux vision model | `hermes config set agent.aux_models.vision <model>` | Same provider as main |
| Embedding model | Set `NVIDIA_API_KEY` in `~/.hermes/.env` | NVIDIA NIM (nemotron-3-embed-1b) |
| Delegation | Leave as default (follows main model) | No action |
| Fallback provider | `hermes config set fallback_providers '[...]'` | Skip unless customer asks |

If no `NVIDIA_API_KEY`: help customer get a free key at https://build.nvidia.com/nvidia/nemotron-3-embed-1b. Fallback: OpenRouter bge-m3 using existing `OPENROUTER_API_KEY`.

**Done:** aux vision model configured (if needed). `NVIDIA_API_KEY` set. Delegation confirmed as following main model.

## Step 4 — Profile and soul.md

1. Create single profile: `hermes profile create <customer-name>`
2. Ask customer for soul.md input:
   - Agent name (default: "Hermes")
   - Preferred language (default: English)
   - Personality (default: business)
   - Domain-specific instructions (optional)
3. Write `~/.hermes/SOUL.md` from customer input. See `references/setup-details.md` § Soul.md template.

Multi-profile: only if customer specifically mentions needing separate profiles.

**Done:** profile created. soul.md written with customer's input.

## Step 5 — Gateway and services

1. Configure gateway: `hermes gateway setup` — select customer's chosen platform(s), enter tokens
2. Deploy gateway as systemd service. Use template from `references/setup-details.md` § Gateway systemd unit:
   - Root mode: `/etc/systemd/system/hermes-gateway.service`
   - User mode: `~/.config/systemd/user/hermes-gateway.service` + `loginctl enable-linger $USER`
   - Set `TimeoutStopSec=240`
3. Deploy dashboard as systemd service. Use template from `references/setup-details.md` § Dashboard systemd unit:
   - Set `HERMES_DASHBOARD_TUI=1`
   - Set `HERMES_PYTHON` to venv python path
   - **Binding choice — ask the customer:**
     - **Loopback (default):** bind to 127.0.0.1. Access via SSH tunnel: `ssh -L 9119:127.0.0.1:9119 user@host`. Most secure. No firewall change needed.
     - **LAN (0.0.0.0):** bind to all interfaces with `--host 0.0.0.0`. Direct access from any device on the same network at `http://<host-ip>:9119`. Suitable for internal WiFi/LAN where all devices are trusted. Set up basic auth (Step 5b) so the dashboard is not unprotected.
4. Enable and start both services
5. Set timezone: `hermes config set timezone '<customer-timezone>'` + `timedatectl set-timezone '<tz>'`

**Done:** gateway and dashboard running as systemd services. Test message sent through gateway. Dashboard accessible via SSH tunnel or LAN with basic auth.

## Step 5b — Dashboard basic auth (required for LAN mode, recommended for all)

Hermes has a built-in basic auth provider. Set a username and password so the dashboard is not unprotected.

1. Hash the password:
   ```bash
   python3 -c "from plugins.dashboard_auth.basic import hash_password; print(hash_password('customer-password'))"
   ```
2. Set in config.yaml (edit directly — `hermes config set` stringifies nested values):
   ```yaml
   dashboard:
     basic_auth:
       username: admin
       password_hash: <hash-from-step-1>
   ```
3. Restart dashboard: `systemctl restart hermes-dashboard`
4. Verify: open dashboard URL in browser — should show login page

For loopback-only deployments this is optional (SSH tunnel already gates access). For LAN deployments this is required.

**Done:** basic auth configured. Dashboard shows login page when accessed.

## Step 5c — Plugin baseline

Hermes is plugin-based since v0.23. Bundled plugins ship disabled — none load until you enable them. Discovery order: bundled (`<repo>/plugins/`) → user (`~/.hermes/plugins/`) → project (requires `HERMES_ENABLE_PROJECT_PLUGINS=1`) → pip entry points. On name collision the later source REPLACES the bundled one.

1. Review the bundled set: `hermes plugins list`
2. Enable the recommended baseline (headless VPS disks fill silently):

   ```bash
   hermes plugins enable disk-cleanup    # auto-tracks ephemeral files, cleans on session end; /disk-cleanup slash command
   ```

   Ask the customer about `security-guidance` (write-time dangerous-pattern warnings) — enable if wanted.
3. Other bundled plugins are use-case driven — leave disabled unless the customer asks: `teams_pipeline` (Teams meeting summaries), `google_meet` (Meet calls + transcription), `image_gen/openai|openai-codex|xai` (image backends), `hermes-achievements` (dashboard tab), `kanban/dashboard` (multi-agent dispatcher board).
4. Note the distinction: MCP servers (Step 8's DonSeTch) are external processes registered in `mcp:` config; plugins are in-process hooks, tools, and slash commands. Do not convert one into the other.
5. Memory providers and context engines are configured separately (`hermes memory setup`, `context.engine` in config) — see Step 10.

**Done:** bundled plugin set reviewed. `disk-cleanup` enabled (or explicitly declined and recorded). Customer answered on `security-guidance`. Enabled set recorded for the Step 19 snapshot.

## Step 5d — Webapp (Desktop workspace in a browser)

The gateway can serve the Desktop workspace in a browser on its own listener. It is **off until enabled**.

1. Enable with the loopback default (SSH-tunnel access, most secure):

   ```yaml
   # config.yaml — edit directly; hermes config set stringifies nested values
   webapp:
     enabled: true
     host: 127.0.0.1        # 127.0.0.1/::1 = this machine only; 0.0.0.0/:: = other machines
     port: 9120
     public_url: ""         # set when a reverse proxy or tunnel serves it at its own https:// address
   ```

2. Decide the exposure with the customer:
   - **Loopback only** — reach it over SSH tunnel like the dashboard.
   - **`public_url` or `host: 0.0.0.0`/`::`** — requires a dashboard sign-in provider (Step 5b basic auth or OAuth) or the gateway serves native clients only; `hermes webapp --status` says so. Set `dashboard.trusted_proxies` when a proxy is in front (the Webapp honors `X-Forwarded-*` only from loopback and those addresses).
   - In a container, use `host: 0.0.0.0` — a published port cannot reach the container loopback.
3. Restart the gateway (it reads `webapp.enabled` at start): `hermes gateway restart`
4. Verify: `hermes webapp --status` reports serving; open the URL (one-use sign-in link or the sign-in-gated address for non-loopback).

**Done:** webapp enabled (or declined and recorded). Exposure decided with the customer. Gateway restarted. `hermes webapp --status` confirms serving.

## Step 6 — Approvals and terminal backend

| Setting | Value | Command |
|---------|-------|---------|
| Approvals | smart | `hermes config set approvals.mode smart` |
| Terminal backend | docker (if detected) or local | `hermes config set terminal.backend docker` |

**Done:** approvals set to smart. Terminal backend set based on Docker detection.

## Step 7 — Compression

Set compression based on model context length:

| Context length | Threshold | Target ratio |
|----------------|-----------|--------------|
| 64K–128K | 0.35 | 0.20 |
| 200K+ | 0.50 | 0.20 |

```bash
hermes config set compression.enabled true
hermes config set compression.threshold <value>
hermes config set compression.target_ratio 0.20
```

**Done:** compression enabled with threshold matched to model context length.

## Step 8 — Search and fetch backend (DonSeTch + fallback)

Primary: DonSeTch MCP server (`mcp_donsetch_web_search` / `web_fetch` / `web_crawl`). It handles research-grade queries, bot-walled pages, and JS-rendered content. Install and wire it, then set a lightweight fallback for single-fact lookups.

### 8a — Install DonSeTch

```bash
npm install -g donsetch
```

### 8b — Register as MCP server

Add to `mcp:` in `~/.hermes/config.yaml` (edit directly — `hermes config set` stringifies nested values):

```yaml
  donsetch:
    command: /usr/local/lib/node_modules/donsetch/binaries/donsetch
    args:
      - mcp
      - --supervised
    env:
      DONGHOST_CHROME: /usr/bin/google-chrome-stable
      DONGHOST_NO_SANDBOX: '1'
    enabled: true
```

Verify: `hermes plugins list` or session info shows `donsetch` with 3 tools connected. Test with a query through `mcp_donsetch_web_search`.

### 8c — Fallback backend (keyless Firecrawl)

Set `web.search_backend: firecrawl` in config. With no `FIRECRAWL_API_KEY` set, Hermes uses Firecrawl's anonymous public cloud mode (`api.firecrawl.dev`, no auth header) — verified: explicit selection + no credentials routes to keyless, zero install steps. It supports both search and extraction.

If the customer later buys a Firecrawl plan, set `FIRECRAWL_API_KEY` — the same backend upgrades to keyed mode automatically, no config change.

Alternatives only if the customer objects to anonymous cloud calls:
- Docker available: deploy SearXNG (`references/setup-details.md` § SearXNG deployment), set `web.search_backend: searxng`
- No Docker: `pip install ddgs`, set `web.search_backend: ddgs`

The fallback serves single-fact quick lookups (one URL, one version, one price) and covers the case where DonSeTch is down.

### 8d — Web-routing rules in SOUL.md

Write the web-routing section into the customer's SOUL.md at Step 4 (soul.md write), not later. Use the template in `references/setup-details.md` § Web tool routing (SOUL.md template). Core rules:

- Research or precision search, comparisons, multi-source verification → `mcp_donsetch_web_search` FIRST
- Built-in `web_search` = single-fact quick lookup ONLY
- Bot-walled, captcha-adjacent, or JS-rendered URL → `mcp_donsetch_web_fetch`; built-in `web_extract` = plain pages only
- Site-wide inventory → `mcp_donsetch_web_crawl`
- Authenticated sites, file uploads, interactive flows → `browser_exec`
- Scanned-PDF/OCR → pdftoppm + tesseract, not donsetch
- LAN/loopback URLs → built-ins (donsetch SSRF-blocks them)

### 8e — DonSeTch weekly update cron

Install the release-binary self-updater (no source builds — lighter dependency footprint):

```bash
# Script ships with the onboarding skill
cp ~/.hermes/skills/agent-ops/hermes-onboarding/scripts/donsetch_update.sh ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/donsetch_update.sh
hermes cron create --name "DonSeTch weekly update" --schedule "0 9 * * 1" --mode no_agent ~/.hermes/scripts/donsetch_update.sh
```

The script gates on GitHub `releases/latest` (published releases with assets), NOT tags — a tag without published assets makes `donsetch update` 404. Silent (empty stdout) when already latest: the no_agent cron only alerts on failure or update.

If customer has Nous Portal: Tool Gateway search is already active. Still install DonSeTch + fallback — Tool Gateway search does not fetch bot-walled pages.

**Done:** DonSeTch installed and connected as MCP server (3 tools). Fallback backend set. Web-routing rules written into SOUL.md. Update cron armed. Search verified with a test query.

## Step 9 — Extraction

Verify keyless extraction works. Step 1 recorded the Hermes version — confirm it is 0.20.5+ for the keyless MCP ring (exa, parallel, tavily, firecrawl, keenable):

```bash
hermes chat -q "Extract the content from https://example.com"
```

If the extraction succeeds, no action needed. If customer wants a pinned backend, set `web.extract_backend: firecrawl` — keyless anonymous mode works with no API key (same mechanism as Step 8c); set `FIRECRAWL_API_KEY` later to upgrade to keyed.

**Done:** keyless extraction verified working.

## Step 10 — Memory (Mnemosyne)

Memory providers are now plugins. `hermes memory setup` is a single-select provider picker — the bundled list is `retaindb` / `byterover`; catalog providers (`honcho`, `hindsight`, `supermemory`, …) install via `hermes plugins install <name>`. Mnemosyne is a user-installed provider plugin (pip `mnemosyne-hermes`) — same surface, not an external catalog entry. The built-in MEMORY.md/USER.md memory stays active alongside any provider.

1. Install and enable Mnemosyne as the provider plugin: `pip install mnemosyne-hermes`, then `hermes memory setup` → select Mnemosyne (or set `memory.provider: mnemosyne` in config.yaml directly — `hermes config set` stringifies nested values)
2. Point embeddings at NVIDIA NIM: in the provider's own config surface `~/.hermes/mnemosyne/config.yaml` set `embeddings_via_api: true`, `embedding_api_url: https://integrate.api.nvidia.com/v1`, `embedding_model: nvidia/nemotron-3-embed-1b`, and `embedding_api_key: <NVIDIA key>` (the `NVIDIA_API_KEY` from Step 3). Hermes's two memory sections: the agent-side knobs live under `memory.mnemosyne:` in `~/.hermes/config.yaml` (sleep/reflect/sync/tools); the provider internals live in `~/.hermes/mnemosyne/config.yaml`.
3. Verify the embedding dimension: `embedding_dim: 2048` — the value nemotron-3-embed-1b returns. The sqlite-vec virtual tables (`vec_episodes`, `vec_working`, `vec_facts`) fix the dimension at creation; a different `embedding_dim` breaks inserts and vector recall. If the customer switches embedding models, re-embed into fresh tables — do not edit the dim under existing vec tables.
4. Verify end to end: `mnemosyne_recall({"query": "test", "limit": 1})` returns results, and `hermes memory status` shows `Provider: mnemosyne`.

Run the memory provider's gap check if anything misbehaves: `skill_view(name='hermes-memory-provider')` covers unavailable providers and recall gaps.

**Done:** Mnemosyne provider plugin selected and active. Provider config surface written with NVIDIA embeddings. Embedding dimension verified 2048 before first vectors land. Recall verified.

## Step 11 — Skill writing guardrails

Apply the 7 Matt Pocock principles to self-generated skills. See `references/setup-details.md` § Skill guardrails. The agent should review any skill it creates against these principles.

For full skill authoring validation, load the bundled skill: `skill_view(name='hermes-agent-skill-authoring')`. This is a Hermes-bundled skill — it ships with every install under the `software-development` category.

**Done:** guardrail principles loaded. Agent knows where to find full skill authoring validation.

## Step 12 — Skill retrieval plugin (BM25)

Install the skill-retrieval plugin from the agent-skills repo. The plugin replaces the full skill list in the system prompt with a compact names-only index and injects top-K relevant descriptions per turn via a `pre_llm_call` hook. It honors named profiles, `skills.external_dirs`, disabled lists, and platform/condition gates — the corpus matches what Hermes itself resolves. Install disabled. Activate only when skill count or token overhead warrants it.

### 12a — Install (disabled)

```bash
hermes plugins install moonlight-lupin/agent-skills/plugins/skill-retrieval --no-enable
```

### 12b — Assess activation need

Run the assessment to measure skill count and overhead ratio:

Run the assessment script from `references/setup-details.md` § "Skill-count and token-overhead assessment script" (heredoc it into `python3 - <<'PY'`).

Two thresholds trigger the recommendation:

- **Skill count > 50** — the full skill list in the system prompt exceeds ~2.5K tokens; the plugin's compact index (~2.3K) saves more than it costs.
- **Skill description overhead > 5%** of context window — descriptions alone at 5% push total overhead above 15% when combined with fixed costs.
### 12c — Activate if recommended

```bash
hermes plugins enable skill-retrieval
```

Restart the session for the plugin to take effect. Per-turn injection runs from the `pre_llm_call` hook; the names-only compaction applies at prompt build.

If not recommended, the plugin stays installed but disabled. Re-run this assessment after adding skills — the customer can enable it later.

### 12d — Record in memory if not enabled

If the plugin was not enabled, store a Mnemosyne memory so the agent remembers the upgrade path exists:

```python
mnemosyne_remember(
    content="Skill-retrieval plugin (BM25) is installed but disabled. Enable with `hermes plugins enable skill-retrieval` if skill count exceeds 50 or input token overhead from skill descriptions exceeds 5% of context window. Re-run the Step 12b assessment after adding skills.",
    importance=0.6,
    scope="global",
    source="onboarding",
    veracity="stated"
)
```

**Done:** skill-retrieval plugin installed (disabled). Activation recommended only if skill count > 50 or skill overhead > 5% of context window. If disabled, Mnemosyne memory records the upgrade path.

## Step 13 — Light RAG (library-rag)

1. Install library-rag skill from the agent-skills repo
2. Follow library-rag's onboarding workflow (directories, NVIDIA API key, first index)
3. Register MCP server in config.yaml if customer wants auto-available search tools

Note: The index grows ~8KB per chunk. Start with a small corpus. A 50-book library is ~100MB. A full research library can exceed 1GB.

**Done:** library-rag installed. First document indexed. MCP server registered (if customer opted in).

## Step 14 — Browser automation (CDP)

1. Check for Chromium: `which chromium-browser || which chromium || which google-chrome`
2. If missing, install: `apt install -y chromium-browser` (or platform equivalent)
3. Set browser backend: `hermes config set browser.cdp_url http://127.0.0.1:9222`
4. Install the chrome-cdp systemd service with memory guardrails and the idle-tab drain from `references/setup-details.md` § "CDP browser systemd service". Headless Chrome leaks renderer memory over weeks — the cap + 6-hourly drain + weekly restart keep it from starving the host.
5. Verify: agent can open a browser tab and navigate
6. Verify the drain: `journalctl -t chrome-cdp-drain -n 1` shows activity (defer is fine); `systemctl list-timers 'chrome-cdp*'` shows both timers armed

Browserbase and Firecrawl are documented as upgrades for anti-detection or cloud browser needs.

**Done:** CDP browser configured with systemd service, memory cap, drain + restart timers. Chromium available. Browser test passed. Drain timers armed.

## Step 15 — Toolset audit

1. Run `hermes tools list`
2. Present toolsets grouped:

| Category | Toolsets |
|----------|---------|
| Essential (keep) | terminal, file, web, search, browser, code_execution, memory, session_search, todo, skills, cronjob, clarify |
| Optional (ask) | vision, image_gen, tts, delegation, messaging, kanban |
| Advanced (default off) | spotify, homeassistant, discord, discord_admin, feishu_doc, feishu_drive, yuanbao, rl, debugging, x_search, video |

3. Ask customer which optional toolsets to keep
4. Disable unneeded: `hermes tools disable <name>`

Note: `messaging` = cross-platform message sending (only for multi-platform setups). `rl` = reinforcement learning tools. `debugging` = extra introspection for Hermes development.

**Done:** toolsets audited. Unneeded toolsets disabled. Customer confirmed optional selections.

## Step 16 — Verbosity confirmation

Present the 4 tool_progress modes with examples from `references/setup-details.md` § Verbosity. Ask customer to confirm.

| Mode | What you see |
|------|-------------|
| off | Final response only, no tool output |
| new | One line per tool, skips consecutive repeats |
| all | One line per tool call with duration (default) |
| verbose | Same as all plus full tool arguments |

Recommend `show_cost: true` to track spending.

```bash
hermes config set display.tool_progress all
hermes config set display.show_cost true
```

**Done:** verbosity confirmed. show_cost enabled.

## Step 17 — Cron fleet default model

Set cron fleet default to prevent drift guard failures on provider switches:

```bash
hermes config set cron.model_provider <main-provider>
hermes config set cron.model <main-model>
```

**Done:** cron fleet default set. Future unpinned cron jobs will not fail on provider switches.

## Step 18 — Maintenance crons

Create 4 scheduled crons + document 1 triggered procedure:

| Cron | Schedule | Mode | What |
|------|----------|------|------|
| Memory consolidation | Every 4 days, 02:00 | no_agent | `mnemosyne_sleep.sh` — working memory → episodic. Silent when done. |
| Backup + update + health | Weekly (Sun, 03:00) | Agent | `hermes backup` (max 2 copies), then `hermes update`, then post-update health check (re-apply LAN patches if needed). Alert on failure. |
| Weekly health check | Weekly (Sun, 06:00) | no_agent | `weekly_health_check.sh` — consolidated report: host status, disk usage, log anomalies, input token overhead. Silent when healthy. Alerts with breakdown when any check finds issues. |
| Input token audit | Every 30 days, 09:30 | Agent | Run the `input-token-overheads` skill's aggregate audit (`scripts/audit.py --days 30`): rank consumers, pre-check levers, report deltas vs the prior baseline, propose changes with verified config values. Delivers a full report each run — the deep audit the weekly check only samples. Requires the `input-token-overheads` skill installed (see Step 20). |
| DonSeTch weekly update | Weekly (Mon, 09:00) | no_agent | `donsetch_update.sh` — release-binary self-updater. Gates on GitHub `releases/latest`, not tags. Silent when already latest. See Step 8e. |

The backup+update cron runs in agent mode (not no_agent) because the post-update health check may need to re-apply dashboard patches that `hermes update` overwrites. A no_agent script cannot re-apply patches or run `skill_view`.

The weekly health check script (`~/.hermes/scripts/weekly_health_check.sh`) chains four checks (host status, disk usage, log anomalies, input-token overhead) into one report with a conditionally generated Suggested Actions section. Design details and the per-alert remediation table: `references/setup-details.md` § "Weekly health check design". The cron delivers to the customer's home channel.

Install the script during onboarding:

```bash
# Script ships with the onboarding skill at scripts/weekly_health_check.sh
cp ~/.hermes/skills/agent-ops/hermes-onboarding/scripts/weekly_health_check.sh ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/weekly_health_check.sh
```

Triggered (not scheduled): post-update health check — run `hermes doctor`, verify gateway + dashboard status, re-apply patches if needed. See `references/setup-details.md` § Post-update health check. Also triggered manually after any `hermes update` outside the weekly cron.

Create the input-token audit cron (agent mode — it needs `skill_view` and reasoning):

```
Prompt skeleton (adapt to the customer):

"You are the input-token auditor. Load the `input-token-overheads` skill and run
its scripts/audit.py for the last 30 days. Compare against the previous audit's
baseline (read it from the prior cron output if available, else establish this
run as the first baseline). Pre-check every lever before proposing changes:
read current values with `hermes config get`, confirm mechanisms against
config_defaults.py or the Hermes docs, mark unverifiable claims UNVERIFIED.
Report under 600 words: (1) total vs baseline with % change, (2) breakdown by
task, (3) verdict on any previously applied changes with proving numbers,
(4) top 3 remaining consumers, (5) one recommended next tweak citing the
pre-checked current value."

Schedule: every 30 days. Delivery: customer's home channel.
```

**Done:** 4 crons created. Weekly health check script installed. Post-update procedure documented.

## Step 19 — Verification summary

1. Run `hermes doctor`
2. Walk the verification checklist — `references/setup-details.md` § "Verification checklist" — and check every item before declaring onboarding complete (includes the plugin-baseline and memory-provider rows).

3. Present config snapshot: provider, model, aux model, gateway platform, memory backend, search backend, browser backend, webapp (enabled + exposure), compression settings, cron jobs, soul.md path, profile name
4. Present pass/fail for each item

**Done:** all verification items checked. Config snapshot presented. Failures flagged with troubleshooting steps.

## Step 20 — Use case and skill recommendations

Ask: "What will you use Hermes for?"

Based on the answer, recommend 3-5 skills from the Skills Hub:

```bash
hermes skills search <use-case-keyword>
```

Install customer's chosen skills: `hermes skills install <id>`

Also install the `input-token-overheads` skill from this repo (`agent-ops/input-token-overheads`) — the 30-day audit cron from Step 18 depends on it.

**Done:** use case recorded. Relevant skills recommended and installed. `input-token-overheads` skill installed for the Step 18 audit cron.

## Files

- `references/setup-details.md` — config snippets, systemd templates, Soul.md template, DonSeTch web routing, skill-count assessment script, weekly health check design, verification checklist
- `scripts/donsetch_update.sh` — DonSeTch release-binary self-updater (Step 8e cron)
- `scripts/weekly_health_check.sh` — consolidated weekly health report installer source (Step 18 cron)

## Common Pitfalls

- **Gateway crash loop with --replace:** Never use `--replace` in systemd unit files for multiple profiles. It SIGTERMs other gateway processes.
- **Plugin name collision replaces bundled plugins:** a user plugin named like a bundled one silently replaces it. Skill names that collide with plugin names are renamed, not shared — this install's disk-cleanup-skill became `disk-triage` so the bundled `disk-cleanup` plugin stays reachable.
- **TimeoutStopSec too short:** Always set 240s. Default 90s causes SIGKILL mid-drain on WhatsApp/Telegram bridges.
- **Cron drift guard:** Unpinned cron jobs fail closed when global model changes. Set cron fleet default early (Step 17).
- **SearXNG IP reputation:** Google/Brave may block datacenter IPs. No config fix — use residential proxy or accept DDG fallback. This affects the fallback backend only; DonSeTch is the primary search path.
- **Double-indexing in library-rag:** Keep raw files outside LIBRARY_ROOT. Only structured markdown goes under LIBRARY_ROOT.
- **plugins.enabled stringification:** `hermes config set plugins.enabled '["a"]'` stores a JSON string, not a YAML list. Edit config.yaml directly for plugin lists.
- **Dashboard TUI on LAN:** Requires HERMES_PYTHON env var and CORS/loopback patches. See hermes-service-deployment skill references.

## Verification

The Step 19 verification checklist (references § Verification checklist) is the single source of truth for setup completeness. Do not duplicate it here.

All items must pass before declaring onboarding complete. Failed items get troubleshooting steps from the Common Pitfalls section.