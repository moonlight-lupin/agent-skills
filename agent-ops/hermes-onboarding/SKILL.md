---
name: hermes-onboarding
description: "Use when onboarding a new Hermes Agent for a customer."
license: MIT
metadata:
  version: 1.0.0
  author: moonlight-lupin
  platforms: [linux, macos, windows]
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

Load `references/setup-details.md`. It holds config snippets, systemd templates, SearXNG engine settings, skill guardrail principles, and verbosity examples.

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
| Main model vision | Check model capabilities via provider docs or test with `vision_analyze` |

**Done:** all 7 items detected and recorded. No user input required.

## Step 2 — Ask up-front questions

Ask the customer 3 questions in one batch:

1. **Customer name** — used for profile name and soul.md identity
2. **Timezone** — IANA timezone (e.g. Asia/Singapore, America/New_York)
3. **Gateway platform(s)** — Telegram, Discord, WhatsApp, Slack, Signal. Collect bot tokens or pairing info.

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
   - Add `--host 0.0.0.0 --insecure` for remote access
4. Enable and start both services
5. Set timezone: `hermes config set timezone '<customer-timezone>'` + `timedatectl set-timezone '<tz>'`

**Done:** gateway and dashboard running as systemd services. Test message sent through gateway. Dashboard URL accessible.

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

## Step 8 — Search backend

If Docker detected:

1. Deploy SearXNG container. See `references/setup-details.md` § SearXNG deployment.
2. Configure engines. See `references/setup-details.md` § SearXNG engine settings.
3. Set `web.search_backend: searxng` in config

If no Docker:

1. Install ddgs: `pip install ddgs`
2. Set `web.search_backend: ddgs` in config

If customer has Nous Portal: Tool Gateway search is already active. Still set a search backend as fallback.

**Done:** search backend configured and verified with a test query.

## Step 9 — Extraction

Verify keyless extraction works (Hermes 0.20.5+ has keyless MCP ring: exa, parallel, tavily, firecrawl, keenable):

```bash
hermes chat -q "Extract the content from https://example.com"
```

If the extraction succeeds, no action needed. If customer wants a pinned backend, set `web.extract_backend` and the corresponding API key.

**Done:** keyless extraction verified working.

## Step 10 — Memory (Mnemosyne)

1. Enable Mnemosyne: `hermes memory setup` → select Mnemosyne
2. Confirm `NVIDIA_API_KEY` is set (from Step 3) — Mnemosyne uses it for embeddings
3. Verify memory works: `mnemosyne_recall({"query": "test", "limit": 1})`

**Done:** Mnemosyne enabled. Embedding key confirmed. Memory recall verified.

## Step 11 — Skill writing guardrails

Apply the 7 Matt Pocock principles to self-generated skills. See `references/setup-details.md` § Skill guardrails. The agent should review any skill it creates against these principles.

For full skill authoring validation, load the bundled skill: `skill_view(name='hermes-agent-skill-authoring')`.

**Done:** guardrail principles loaded. Agent knows where to find full skill authoring validation.

## Step 12 — BM25 skill search (optional upgrade)

Document as optional upgrade. Hermes' built-in skill retrieval works by default. For better matching accuracy, the skill-retrieval plugin (BM25 top-k) is available from the agent-skills repo.

Do not install during base onboarding unless customer asks.

**Done:** customer informed of BM25 upgrade path.

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
4. Verify: agent can open a browser tab and navigate

Browserbase and Firecrawl are documented as upgrades for anti-detection or cloud browser needs.

**Done:** CDP browser configured. Chromium available. Browser test passed.

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
| Disk cleanup | Monthly (1st, 03:00) | Agent | Uses disk-cleanup skill |
| Memory consolidation | Every 4 days, 02:00 | Agent | Mnemosyne sleep cycle |
| Log anomaly scan | Weekly (Sun, 06:00) | no_agent | log-analyzer --quiet, silent when healthy |
| Backup + update + health | Weekly (Sun, 03:00) | no_agent | hermes backup (max 2 copies) then hermes update then hermes-post-update procedure. Alert on failure only. |

Triggered (not scheduled): post-update health check — run `hermes doctor`, verify gateway + dashboard status, re-apply patches if needed. See `references/setup-details.md` § Post-update health check.

**Done:** 4 crons created. Post-update procedure documented.

## Step 19 — Verification summary

1. Run `hermes doctor`
2. Verify each item:

| Item | Check |
|------|-------|
| Gateway | `systemctl status hermes-gateway` + test message |
| Dashboard | `systemctl status hermes-dashboard` + URL accessible |
| Memory | `mnemosyne_recall` returns results |
| Search | `web_search` test query returns results |
| Extraction | `web_extract` test URL returns content |
| Browser | CDP browser opens and navigates |
| Crons | `hermes cron list` shows 4 jobs |
| Timezone | `hermes config get timezone` matches customer input |

3. Present config snapshot: provider, model, aux model, gateway platform, memory backend, search backend, browser backend, compression settings, cron jobs, soul.md path, profile name
4. Present pass/fail for each item

**Done:** all verification items checked. Config snapshot presented. Failures flagged with troubleshooting steps.

## Step 20 — Use case and skill recommendations

Ask: "What will you use Hermes for?"

Based on the answer, recommend 3-5 skills from the Skills Hub:

```bash
hermes skills search <use-case-keyword>
```

Install customer's chosen skills: `hermes skills install <id>`

**Done:** use case recorded. Relevant skills recommended and installed.

## Common Pitfalls

- **Gateway crash loop with --replace:** Never use `--replace` in systemd unit files for multiple profiles. It SIGTERMs other gateway processes.
- **TimeoutStopSec too short:** Always set 240s. Default 90s causes SIGKILL mid-drain on WhatsApp/Telegram bridges.
- **Cron drift guard:** Unpinned cron jobs fail closed when global model changes. Set cron fleet default early (Step 17).
- **SearXNG IP reputation:** Google/Brave may block datacenter IPs. No config fix — use residential proxy or accept DDG fallback.
- **Double-indexing in library-rag:** Keep raw files outside LIBRARY_ROOT. Only structured markdown goes under LIBRARY_ROOT.
- **plugins.enabled stringification:** `hermes config set plugins.enabled '["a"]'` stores a JSON string, not a YAML list. Edit config.yaml directly for plugin lists.
- **Dashboard TUI on LAN:** Requires HERMES_PYTHON env var and CORS/loopback patches. See hermes-service-deployment skill references.

## Verification Checklist

- [ ] `hermes doctor` reports no errors
- [ ] Gateway service active and responding to test message
- [ ] Dashboard service active and URL accessible
- [ ] Memory recall returns results
- [ ] Search returns results
- [ ] Extraction returns content
- [ ] Browser opens and navigates
- [ ] 4 maintenance crons created and visible in `hermes cron list`
- [ ] Cron fleet default set
- [ ] Compression enabled with correct threshold
- [ ] Approvals set to smart
- [ ] Terminal backend set (docker or local)
- [ ] Toolsets audited and unneeded disabled
- [ ] Verbosity confirmed
- [ ] Profile created and soul.md written
- [ ] Timezone set in both Hermes config and system
- [ ] library-rag installed (if customer opted in)
- [ ] Skill guardrails loaded
- [ ] Use case recorded and skills recommended