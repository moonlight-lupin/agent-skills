# Onboarding Setup Details

Reference material for the hermes-onboarding skill. Loaded at Step 0.

## Detection

```bash
echo "=== OS ===" && uname -a
echo "=== systemd ===" && systemctl --version 2>&1 | head -2
echo "=== Docker ===" && docker --version 2>&1
echo "=== cgroup ===" && head -5 /proc/1/cgroup 2>/dev/null
echo "=== user ===" && whoami
echo "=== hermes path ===" && which hermes
echo "=== hermes version ===" && hermes --version
echo "=== hermes home ===" && echo $HERMES_HOME
echo "=== venv python ===" && ls -la $(dirname $(which hermes))/../python3 2>/dev/null || ls -la $(dirname $(which hermes))/python3 2>/dev/null
```

Vision detection: check the configured model name against known vision-capable models. Common vision models: Claude 3.5+ (anthropic), GPT-4o+ (openai), Gemini (google), Qwen-VL (alibaba). If the model name does not contain a vision indicator, test by sending an image and checking if the model can describe it.

## Soul.md template

```markdown
# Identity

You are {agent_name}, an AI assistant for {customer_name}.

## Language

Primary language: {language}

## Personality

{personality}

## Domain

{domain_instructions}
```

Write to `~/.hermes/SOUL.md`. Keep it under 2000 chars. The customer can expand it later.

## Gateway systemd unit

### Root mode

```ini
[Unit]
Description=Hermes Agent Gateway
After=network.target

[Service]
Type=simple
User=root
ExecStart={hermes_path} gateway run
Restart=always
RestartSec=10
TimeoutStopSec=240
Environment=HERMES_HOME={hermes_home}

[Install]
WantedBy=multi-user.target
```

Save to `/etc/systemd/system/hermes-gateway.service`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-gateway
sudo systemctl start hermes-gateway
```

### User mode

Save to `~/.config/systemd/user/hermes-gateway.service`. Same content but remove `User=root`.

```bash
loginctl enable-linger $USER
systemctl --user daemon-reload
systemctl --user enable hermes-gateway
systemctl --user start hermes-gateway
```

### Verification

```bash
systemctl status hermes-gateway
# Send test message through configured platform
```

## Dashboard systemd unit

### Default: loopback only (most secure)

```ini
[Unit]
Description=Hermes Agent Dashboard
After=network.target

[Service]
Type=simple
User={user}
ExecStart={hermes_path} dashboard
Restart=always
RestartSec=10
Environment=HERMES_DASHBOARD_TUI=1
Environment=HERMES_PYTHON={venv_python_path}
Environment=HERMES_HOME={hermes_home}

[Install]
WantedBy=multi-user.target
```

Access via SSH tunnel: `ssh -L 9119:127.0.0.1:9119 user@host`, then open `http://127.0.0.1:9119` locally.

### Optional: LAN access (for trusted internal WiFi/LAN)

Choose this if the customer wants direct access from other devices on the same network without SSH tunneling. Suitable for home or office networks where all devices are trusted.

```ini
[Unit]
Description=Hermes Agent Dashboard
After=network.target

[Service]
Type=simple
User={user}
ExecStart={hermes_path} dashboard --host 0.0.0.0 --insecure
Restart=always
RestartSec=10
Environment=HERMES_DASHBOARD_TUI=1
Environment=HERMES_PYTHON={venv_python_path}
Environment=HERMES_HOME={hermes_home}

[Install]
WantedBy=multi-user.target
```

Open firewall: `sudo ufw allow 9119/tcp`. Access from any LAN device at `http://<host-ip>:9119`.

**Note:** The dashboard fronts an agent with terminal access. On a trusted LAN this is convenient. On an untrusted network, add an authenticated reverse proxy (Caddy/nginx with basic auth) in front. Example Caddy config:

```
# /etc/caddy/Caddyfile
:9120 {
    basicauth {
        admin <bcrypt-hash>
    }
    reverse_proxy 127.0.0.1:9119
}
```

For root mode, save to `/etc/systemd/system/hermes-dashboard.service`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable hermes-dashboard
sudo systemctl start hermes-dashboard
```

Open firewall only for LAN mode: `sudo ufw allow 9119/tcp`. Not needed for loopback-only deployments.

### Verification

```bash
systemctl status hermes-dashboard
curl -s http://127.0.0.1:9119 | head -5
# From remote machine: http://<host-ip>:9119
```

### LAN TUI patches (only if LAN access explicitly requested)

**Warning:** These patches disable security checks in `hermes_cli/web_server.py`. Only apply if the customer explicitly asked for LAN dashboard access and an authenticated reverse proxy is in place. Do not apply for loopback-only deployments.

If the dashboard TUI chat tab must work from a LAN IP (not localhost), three security checks in `hermes_cli/web_server.py` must be patched:

1. `_LOOPBACK_HOST_VALUES` (~line 158) — add the host's LAN IPs
2. `_LOOPBACK_HOSTS` (~line 3373) — add LAN IPs to WS client IP whitelist
3. CORS `allow_origin_regex` (~line 161) — include private network IPs

These patches are overwritten by `hermes update`. Re-apply after every update.

For full patch details, load the `hermes-service-deployment` skill.

## SearXNG deployment

```bash
# Create data directory
mkdir -p ~/.hermes/searxng

# Run SearXNG container
docker run -d \
  --name searxng \
  --restart always \
  -p 8080:8080 \
  -v ~/.hermes/searxng:/etc/searxng \
  searxng/searxng:latest

# Wait for startup
sleep 5

# Verify
curl -s "http://127.0.0.1:8080/search?q=test&format=json" | python3 -m json.tool | head -20
```

Set Hermes to use SearXNG:

```bash
hermes config set web.search_backend searxng
hermes config set web.searxng_url http://127.0.0.1:8080
```

## SearXNG engine settings

After deploying SearXNG, configure the engines in `~/.hermes/searxng/settings.yml`.

### Key engines to enable

```yaml
# In settings.yml under engines:
engines:
  # Core search engines (enable these)
  - name: duckduckgo
    engine: duckduckgo
    disabled: false

  - name: brave
    engine: brave
    disabled: false

  - name: google
    engine: google
    disabled: false

  - name: bing
    engine: bing
    disabled: false

  - name: wikipedia
    engine: wikipedia
    disabled: false

  - name: startpage
    engine: startpage
    disabled: false

  # News engines
  - name: duckduckgo news
    engine: duckduckgo
    categories: news
    disabled: false

  - name: google news
    engine: google_news
    disabled: false

  # IT/Dev engines
  - name: github
    engine: github
    disabled: false

  - name: stackoverflow
    engine: stackoverflow
    disabled: false

  # General reference
  - name: arxiv
    engine: arxiv
    disabled: false

  - name: reddit
    engine: reddit
    disabled: false
```

### Important settings

```yaml
# settings.yml top-level
search:
  formats:
    - html
    - json
  safe_search: 0
  autocomplete: ""
  default_lang: "en"

server:
  bind_address: "127.0.0.1"
  port: 8080
  limiter: false  # disable rate limiting for local use

outgoing:
  request_timeout: 10.0
  max_request_timeout: 15.0
  # If datacenter IP is blocked by Google/Brave, add a proxy:
  # proxies:
  #   all://: socks5h://user:pass@proxy-host:port
```

### Apply changes

```bash
docker restart searxng
sleep 3

# Verify engines are active
curl -s "http://127.0.0.1:8080/config" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for e in data.get('engines', []):
    if e.get('enabled'):
        print(f\"  {e['name']}: enabled\")
"
```

### Datacenter IP note

Google, Brave, and Startpage may return CAPTCHA, 429, or silent-empty results from datacenter IPs. This is IP reputation, not a config problem. Options:
1. Accept DDG and Bing as primary engines (more datacenter-tolerant)
2. Route through a residential proxy via `outgoing.proxies`
3. Keep SearXNG for aggregation and rely on DDG fallback for blocked engines

## Skill guardrails (7 Matt Pocock principles)

Apply these to every skill the agent creates:

1. **Completion criteria** — every step ends with a checkable "Done:" condition. The agent must be able to tell done from not-done.

2. **Leading words** — use compact concepts that anchor execution. One word repeated as a token, never as a sentence. Example: *triage*, *onboard*, *relentless*.

3. **No-op test** — run on each sentence: does it change behavior versus the model's default? If not, delete the whole sentence. "Be thorough" is a no-op when the agent is already thorough-ish.

4. **Progressive disclosure** — push detail into reference files. Keep SKILL.md legible. The description is always loaded; the body loads on invocation; references load on demand.

5. **Single source of truth** — each meaning in one authoritative place. Duplication costs maintenance and inflates prominence.

6. **Pruning** — skills should get shorter or sharper over time. Remove stale layers. Sediment settles because adding feels safe and removing feels risky.

7. **Description as trigger** — trigger-first, one sentence. The description is the invocation signal. Every word costs tokens on every turn. Keep it concise — the skill-retrieval plugin truncates at 200 chars.

For full skill authoring validation (frontmatter, peer-matched structure, cross-reference parity), load the bundled skill:

```
skill_view(name='hermes-agent-skill-authoring')
```

## Verbosity

Hermes `display.tool_progress` controls how tool calls appear in the CLI. Four modes:

### off

```
What's my disk usage?
[Hermes responds with disk usage — no tool output visible]
```

### new

```
What's my disk usage?
  🔍 terminal (0.3s)
  📄 read_file (0.1s)
[Hermes responds — first call of each tool shown, repeats suppressed]
```

### all (default)

```
What's my disk usage?
  🔍 terminal (0.3s)
  📄 read_file (0.1s)
  🔍 terminal (0.2s)
[Hermes responds — every tool call shown with duration]
```

### verbose

```
What's my disk usage?
  🔍 terminal(command="df -h /", timeout=180) (0.3s)
  📄 read_file(path="/root/.hermes/config.yaml", limit=200) (0.1s)
  🔍 terminal(command="du -sh /root/.hermes/*", timeout=180) (0.2s)
[Hermes responds — every tool call shown with full arguments + duration]
```

### Related display settings

| Setting | What | Default | Command |
|---------|------|---------|---------|
| `show_reasoning` | Show model thinking before response | true | `hermes config set display.show_reasoning true` |
| `show_cost` | Show per-turn token cost | false | `hermes config set display.show_cost true` |

## Post-update health check

Run this procedure after every `hermes update` (whether triggered manually or by the weekly cron):

1. **Doctor check**
   ```bash
   hermes doctor
   ```

2. **Gateway status**
   ```bash
   systemctl status hermes-gateway
   # If failed: systemctl reset-failed hermes-gateway && systemctl start hermes-gateway
   ```

3. **Dashboard status**
   ```bash
   systemctl status hermes-dashboard
   # If failed: systemctl reset-failed hermes-dashboard && systemctl start hermes-dashboard
   ```

4. **Re-apply patches** — updates overwrite dashboard LAN patches. If the dashboard TUI is accessed from LAN, re-apply the CORS/loopback patches. See `hermes-service-deployment` skill.

5. **Test chat**
   ```bash
   hermes chat -q "What is 2+2?"
   ```

6. **Test gateway** — send a test message through each configured platform.

For the full post-update procedure including dependency reinstallation and patch re-application, load the `hermes-post-update` skill (Hermes-bundled, ships with every install under the `devops` category). For dashboard LAN patch details, load `hermes-service-deployment` (also Hermes-bundled, `devops` category).