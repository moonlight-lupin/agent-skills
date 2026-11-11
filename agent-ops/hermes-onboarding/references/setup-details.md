# Onboarding Setup Details

Reference material for the hermes-onboarding skill. Loaded at Step 0.

## Contents

- Detection
- Soul.md template
- Gateway systemd unit
- Dashboard systemd unit
- SearXNG deployment
- SearXNG engine settings
- Web tool routing (SOUL.md template)
- Skill guardrails (7 Matt Pocock principles)
- Verbosity
- CDP browser systemd service
- Post-update health check
- Skill-count and token-overhead assessment script
- Weekly health check design
- Verification checklist

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

### Optional A: LAN direct (trusted internal WiFi/LAN)

Direct access from any device on the same network. Requires basic auth (see Step 5b in SKILL.md). Only safe on networks you fully control.

```ini
[Unit]
Description=Hermes Agent Dashboard
After=network.target

[Service]
Type=simple
User={user}
ExecStart={hermes_path} dashboard --host 0.0.0.0
Restart=always
RestartSec=10
Environment=HERMES_DASHBOARD_TUI=1
Environment=HERMES_PYTHON={venv_python_path}
Environment=HERMES_HOME={hermes_home}

[Install]
WantedBy=multi-user.target
```

Note: `--insecure` is not needed when basic auth is configured — the auth gate protects the dashboard. Open firewall: `sudo ufw allow 9119/tcp`. Access at `http://<host-ip>:9119`.

### Optional B: LAN via authenticated reverse proxy (untrusted networks)

For networks where not all devices are trusted, or where HTTPS is required. The dashboard stays on loopback; only the proxy port is exposed.

Dashboard unit — same as loopback default (no `--host 0.0.0.0`):

```ini
ExecStart={hermes_path} dashboard
```

Caddy config (adds HTTPS + basic auth):

```
# /etc/caddy/Caddyfile
:9120 {
    basicauth {
        admin <bcrypt-hash>
    }
    reverse_proxy 127.0.0.1:9119
}
```

Open firewall: `sudo ufw allow 9120/tcp`. Do NOT open 9119. Access at `http://<host-ip>:9120` with credentials.

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

### LAN TUI patches (only for LAN direct mode — Optional A)

If the customer chose LAN direct mode (Optional A) and the dashboard TUI chat tab must work from a LAN IP (not localhost), three security checks in `hermes_cli/web_server.py` must be patched. Basic auth (Step 5b) must be configured first.

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

## Web tool routing (SOUL.md template)

Write this section into the customer's SOUL.md at Step 4. Adjust tool names if the customer's setup differs.

```markdown
## Web tool routing (DonSeTch primary)
- Research or precision search → `mcp_donsetch_web_search` FIRST, not built-in `web_search`. "Research or precision" INCLUDES: any comparison ("X vs Y", "compare"), "look for other sources", multi-source verification, product/hardware/benchmark lookup, "find out about", and any query whose answer you would cite from 2+ web pages. Built-in `web_search` = single-fact quick lookup ONLY (one URL, one version number, one price) — never the first call for comparisons or multi-source work.
- Bot-walled, captcha-adjacent, or JS-rendered public URL → `mcp_donsetch_web_fetch` (tier-2 escalation through walls; honest structured errors). Built-in `web_extract` = plain pages and local/non-HTTP files only.
- Escalation: if built-in `web_search` results contain junk (unrelated domains, dictionary/forum noise) or fewer than 3 usable hits, re-run the SAME query with `mcp_donsetch_web_search` before answering.
- Site-wide inventory → `mcp_donsetch_web_crawl`.
- Authenticated sites, file uploads, interactive flows → `browser_exec` (donsetch cannot log in).
- Scanned-PDF/OCR → pdftoppm + tesseract pipeline, not donsetch.
- LAN/loopback URLs → built-ins (donsetch SSRF-blocks them via `guard.ssrf`).
```

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

## CDP browser systemd service

Run headless Chrome as a systemd service with CDP remote debugging. Install with:

```bash
cat > /etc/systemd/system/chrome-cdp.service <<'EOF'
[Unit]
Description=Google Chrome headless with CDP remote debugging for Browser Use
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/google-chrome-stable --headless=new --remote-debugging-port=9222 --no-sandbox --disable-gpu --disable-dev-shm-usage --user-data-dir=/tmp/chrome-debug
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now chrome-cdp.service
```

### Memory guardrails (required on VMs with ≤ 8 GB RAM)

Headless Chrome leaks renderer memory over weeks. Add a hard memory cap so Chrome gets OOM-killed and auto-restarted instead of starving the host:

```bash
mkdir -p /etc/systemd/system/chrome-cdp.service.d
cat > /etc/systemd/system/chrome-cdp.service.d/override.conf <<'EOF'
[Service]
MemoryHigh=1200M
MemoryMax=1800M
OOMPolicy=stop
EOF
systemctl daemon-reload
```

Tune `MemoryHigh`/`MemoryMax` to ~25-35% of total RAM.

### Idle-tab drain (required)

Long-lived CDP tabs accumulate renderer memory (observed: one leaked tab at 2.2 GB after 10 days). Install the drain script — it closes idle tab targets over CDP, defers when any client session is live, and never restarts Chrome itself:

Save as `/usr/local/sbin/chrome-cdp-drain.sh`, mode 755:

```bash
#!/bin/bash
# Drain idle tabs from the chrome-cdp headless browser to release renderer memory.
# Keeps the browser process alive (CDP port 9222 stays up), only closes tab targets.
# SAFE-BY-DEFAULT:
#   - defers entirely if any CDP client has an established connection to :9222
#   - skips any page target lacking webSocketDebuggerUrl (defensive: possibly attached)
#   - never restarts Chrome (systemd Restart=on-failure owns that)
#   - fails closed: any check error means "do not close anything"

CDP="http://127.0.0.1:9222"
LOG_TAG="chrome-cdp-drain"
LOCK="/run/chrome-cdp-drain.lock"

log()  { logger -t "$LOG_TAG" -p daemon.notice  "$1"; }
warn() { logger -t "$LOG_TAG" -p daemon.warning "$1"; }

# 0. Serialize concurrent invocations (timer + manual run overlap guard).
exec 9>"$LOCK"
if ! flock -n 9; then
    warn "Defer: another drain invocation is running"
    exit 0
fi

# 1. Chrome up? (No restart from this script - a restart could kill a live session.)
if ! curl -s --fail --max-time 5 "$CDP/json/version" >/dev/null; then
    warn "Chrome not responding on 9222 - deferring, no action taken"
    exit 0
fi

# 2. Defer if ANY established connection touches :9222 (client or server side).
#    Fail closed: if ss itself errors, do not close anything.
if ! SS_OUT=$(ss -Htn state established '( dport = :9222 or sport = :9222 )' 2>/dev/null); then
    warn "Defer: cannot inspect CDP connections (ss failed)"
    exit 0
fi
CONN_CLIENTS=$(printf '%s\n' "$SS_OUT" | grep -c . || true)
if [ "$CONN_CLIENTS" -gt 0 ]; then
    log "Defer: $CONN_CLIENTS CDP connection(s) active (agent session in progress)"
    exit 0
fi

# 3. Fetch + validate the target list in one pass. Structured parse, no grep counting.
PAGES_JSON=$(curl -s --fail --max-time 5 "$CDP/json/list") || {
    warn "Defer: /json/list fetch failed"
    exit 0
}
PARSE_OUT=$(printf '%s' "$PAGES_JSON" | python3 -c '
import json, sys, re
try:
    targets = json.load(sys.stdin)
    assert isinstance(targets, list)
except Exception:
    sys.exit(3)
closable, skipped, pages = [], 0, 0
for t in targets:
    if t.get("type") != "page":
        continue
    pages += 1
    tid = t.get("id", "")
    # no webSocketDebuggerUrl => possibly debugger-attached => never close
    if not t.get("webSocketDebuggerUrl") or not re.fullmatch(r"[0-9A-Fa-f]{32}", tid):
        skipped += 1
    else:
        closable.append(tid)
print(f"pages={pages}")
print(f"skipped={skipped}")
print("\n".join(closable))
') || { warn "Defer: /json/list parse failed or invalid JSON"; exit 0; }

PAGES=$(printf '%s\n' "$PARSE_OUT" | sed -n 's/^pages=//p')
SKIPPED=$(printf '%s\n' "$PARSE_OUT" | sed -n 's/^skipped=//p')
TARGET_IDS=$(printf '%s\n' "$PARSE_OUT" | grep -E '^[0-9A-Fa-f]{32}$' || true)

if [ "${PAGES:-0}" -le 1 ]; then
    log "Only ${PAGES:-0} page open, nothing to drain"
    exit 0
fi

# 4. Verify we are still talking to the same browser instance (guards against a
#    Chrome restart between snapshot and close).
BROWSER_WS=$(curl -s --fail --max-time 5 "$CDP/json/version" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("webSocketDebuggerUrl",""))') || {
    warn "Defer: /json/version re-fetch failed before close loop"
    exit 0
}
[ -n "$BROWSER_WS" ] || { warn "Defer: no browser websocket url in /json/version"; exit 0; }

# 5. Recheck connections immediately before closing (narrows the TOCTOU window).
SS_OUT2=$(ss -Htn state established '( dport = :9222 or sport = :9222 )' 2>/dev/null) || {
    warn "Defer: cannot re-inspect CDP connections before close"
    exit 0
}
if [ "$(printf '%s\n' "$SS_OUT2" | grep -c . || true)" -gt 0 ]; then
    log "Defer: CDP client connected between checks - aborting drain"
    exit 0
fi

# 6. Close validated targets; only count real HTTP-200 successes.
CLOSED=0
FAILED=0
for id in $TARGET_IDS; do
    # Abort mid-loop if a client shows up.
    if ss -Htn state established '( dport = :9222 or sport = :9222 )' 2>/dev/null | grep -q .; then
        log "Defer: CDP client connected mid-drain - stopping after $CLOSED closes"
        break
    fi
    if curl -s --fail --max-time 5 "$CDP/json/close/$id" >/dev/null; then
        CLOSED=$((CLOSED+1))
    else
        FAILED=$((FAILED+1))
    fi
done

if [ "$SKIPPED" -gt 0 ] || [ "$FAILED" -gt 0 ]; then
    log "Closed $CLOSED idle page targets, deferred $SKIPPED in-use target(s), $FAILED close failure(s)"
else
    log "Closed $CLOSED page targets"
fi
[ "$FAILED" -eq 0 ] || exit 1
exit 0
```

Timer units (tab drain every 6 h, full browser restart weekly to clear in-process leaks):

```bash
cat > /etc/systemd/system/chrome-cdp-drain.service <<'EOF'
[Unit]
Description=Drain idle chrome-cdp tabs to release renderer memory

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/chrome-cdp-drain.sh
MemoryMax=100M
TimeoutStartSec=120
EOF
cat > /etc/systemd/system/chrome-cdp-drain.timer <<'EOF'
[Unit]
Description=Drain chrome-cdp idle tabs every 6 hours

[Timer]
OnCalendar=*-*-* 03,09,15,21:00:00
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
EOF
cat > /etc/systemd/system/chrome-cdp-restart.service <<'EOF'
[Unit]
Description=Weekly full restart of chrome-cdp to clear memory leaks

[Service]
Type=oneshot
ExecStart=/bin/systemctl restart chrome-cdp.service
EOF
cat > /etc/systemd/system/chrome-cdp-restart.timer <<'EOF'
[Unit]
Description=Restart chrome-cdp weekly

[Timer]
OnCalendar=Sun *-*-* 04:30:00
RandomizedDelaySec=30m
Persistent=true

[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now chrome-cdp-drain.timer chrome-cdp-restart.timer
```

Verify the drain: open two tabs over CDP (`curl -X PUT 'http://127.0.0.1:9222/json/new?https://example.com'` twice), run `/usr/local/sbin/chrome-cdp-drain.sh`, then check `journalctl -t chrome-cdp-drain -n 1` reports closes. Run it while a CDP websocket client is attached: it must log a Defer line and close nothing.

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

## Skill-count and token-overhead assessment script

Hermes-importable when available (honors named profiles, external_dirs, plugin-bundled skills, platform gates); glob fallback for standalone contexts.

```bash
python3 -c "
import yaml, pathlib, glob, os, re, sys

# Count skills the way Hermes resolves them: discovery helpers when importable
# (honors named profiles, external_dirs, plugin-bundled skills, symlinks),
# glob fallback for standalone contexts.
count = 0; total_chars = 0
try:
    from hermes_constants import get_skills_dir
    from agent.skill_utils import get_all_skills_dirs, get_project_skills_dirs, iter_skill_index_files
    from agent.prompt_builder import _parse_skill_file, _skill_should_show, extract_skill_conditions, _current_session_platform_hint
    hint = _current_session_platform_hint() or None
    seen = set()
    for root in list(get_project_skills_dirs()) + list(get_all_skills_dirs()):
        for f in iter_skill_index_files(root, 'SKILL.md'):
            try:
                ok, fm, desc = _parse_skill_file(f)
                if not ok or not desc: continue
                name = fm.get('name', '')
                if name in seen: continue
                if not _skill_should_show(extract_skill_conditions(fm), None, None, hint): continue
                seen.add(name); count += 1
                total_chars += min(len(desc), 200)
            except Exception: pass
    # Plugin-bundled skills also occupy the system prompt (keyed prefix:name)
    from hermes_constants import get_hermes_home
    plugins_root = get_hermes_home() / 'plugins'
    if plugins_root.is_dir():
        for pdir in sorted(plugins_root.iterdir()):
            pskills = pdir / 'skills'
            if not pdir.is_dir() or pdir.name.startswith('.') or not pskills.is_dir(): continue
            for f in iter_skill_index_files(pskills, 'SKILL.md'):
                try:
                    ok, fm, desc = _parse_skill_file(f)
                    if not ok or not desc: continue
                    name = fm.get('name', '')
                    if name in seen: continue
                    if not _skill_should_show(extract_skill_conditions(fm), None, None, hint): continue
                    seen.add(name); count += 1
                    total_chars += min(len(desc), 200)
                except Exception: pass
except ImportError:
    for f in glob.glob(os.path.expanduser('~/.hermes/skills/**/SKILL.md'), recursive=True):
        try:
            text = pathlib.Path(f).read_text()
            m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
            if not m: continue
            fm = yaml.safe_load(m.group(1))
            if not fm: continue
            desc = fm.get('description', '')
            if desc:
                count += 1
                total_chars += min(len(desc), 200)
        except Exception: pass

desc_tokens = total_chars // 4

# Context window: provider-aware resolution when Hermes is importable
# (covers OpenRouter probing and cached per-model metadata), else config,
# else 128K default.
ctx = 0
try:
    from model_tools import _resolve_active_context_length
    ctx = int(_resolve_active_context_length() or 0)
except Exception:
    pass
if not ctx:
    try:
        with open(os.path.expanduser('~/.hermes/config.yaml')) as fh:
            cfg = yaml.safe_load(fh) or {}
        ctx = int(cfg.get('model', {}).get('context_length', 0))
    except Exception:
        pass
if not ctx:
    ctx = 128000

skill_ratio = desc_tokens / ctx if ctx else 0
SKILL_COUNT_THRESHOLD = 50
SKILL_RATIO_THRESHOLD = 0.05  # 5% of context from skill descriptions alone

print(f'Skills: {count}')
print(f'Skill description tokens: ~{desc_tokens} ({skill_ratio:.1%} of {ctx} context)')
print(f'Thresholds: skill count > {SKILL_COUNT_THRESHOLD} OR skill ratio > {SKILL_RATIO_THRESHOLD:.0%}')

if count > SKILL_COUNT_THRESHOLD or skill_ratio > SKILL_RATIO_THRESHOLD:
    print('RECOMMEND: enable skill-retrieval plugin')
else:
    print('RECOMMEND: keep disabled — overhead within healthy range')
"
```

Two thresholds trigger the recommendation:

- **Skill count > 50** — the full skill list in the system prompt exceeds ~2.5K tokens. The plugin's compact index (~2.3K) saves more than it costs.
- **Skill description overhead > 5%** of context window — skill descriptions alone at 5% push total overhead above 15% when combined with fixed costs (tool schemas, system prompt, behavioral rules). The 15% threshold is the upper bound of the healthy range from the `input-token-overheads` skill. Load that skill for the full overhead audit if the customer wants a deeper analysis.

## Weekly health check design

Script: `~/.hermes/scripts/weekly_health_check.sh` (ships with this skill: `scripts/weekly_health_check.sh`). It always outputs a report (even when healthy); the cron delivers it to the customer's home channel. Four checks:

1. **Host status** — detects host type (Raspberry Pi, VM, bare metal, Mac, Windows/WSL) via `systemd-detect-virt` and `/proc/device-tree/model`. Reports uptime and load average.
2. **Disk usage** — `df -h` across all mounts. Alerts when any mount exceeds 80%.
3. **Log anomalies** — runs `log-analyzer` scan (`analyze_logs.py --since 7d --quiet`) + `state_failures.py --quiet --days 7`. Reports error clusters, rate limits, timeouts, tool failures, crashes, and session failures.
4. **Input token overhead** — counts skills and measures skill-description token overhead against context window. Alerts when skill count > 50 or skill overhead > 5% of context. Recommends enabling skill-retrieval plugin.

The script always outputs a report (even when healthy) and includes a **Suggested Actions** section with specific remediation steps when alerts are found. The cron delivers the report to the customer's home channel.

Suggested actions are conditionally generated per check:

| Alert | Suggested action |
|-------|-----------------|
| High load (> 80% CPU capacity) | Check for runaway processes with `top` or `htop` |
| Disk above 80% | Run `/disk-cleanup dry-run` (bundled plugin sweep) or disk-triage for the interactive deep clean (`skill_view(name='disk-triage')`) |
| Error clusters in logs | Review the most frequent error; schedule a fix if infrastructure issue |
| Rate limit hits | Check provider quotas or rotate API keys in `~/.hermes/.env` |
| Timeout clusters | Check network connectivity to affected endpoints |
| Tools below 95% success rate | Review failing tool calls and check configurations |
| Skill overhead exceeds threshold | Enable skill-retrieval plugin (`hermes plugins enable skill-retrieval`) |

When all checks pass, the Suggested Actions section reads: "No actions needed. All checks passed."

## Verification checklist

Walk top to bottom during Step 19; every item must pass before declaring onboarding complete. Failed items get troubleshooting steps from the Common Pitfalls section.

2. Verify each item:

| Item | Check |
|------|-------|
| Gateway | `systemctl status hermes-gateway` + test message |
| Dashboard | `systemctl status hermes-dashboard` + URL accessible |
| Dashboard auth | Browser shows login page (LAN mode) or SSH tunnel works (loopback) |
| Memory | `mnemosyne_recall` returns results |
| Search (primary) | `mcp_donsetch_web_search` test query returns results; session info shows donsetch connected with 3 tools |
| Search (fallback) | `web_search` test query returns results via keyless firecrawl |
| Web routing | SOUL.md contains the web-routing section (donsetch first, built-in for single-fact lookups) |
| Extraction | `web_extract` test URL returns content |
| Browser | CDP browser opens and navigates |
| Crons | `hermes cron list` shows 5 jobs (incl. DonSeTch weekly update) |
| Weekly health check | `~/.hermes/scripts/weekly_health_check.sh` exists and is executable |
| Input token audit | `hermes cron list` shows a 30-day audit job; `input-token-overheads` skill installed and `scripts/audit.py` runs |
| Timezone | `hermes config get timezone` matches customer input |
| Approvals | `hermes config get approvals.mode` returns `smart` |
| Terminal backend | `hermes config get terminal.backend` matches detection |
| Compression | `hermes config get compression.threshold` matches model context |
| Cron fleet default | `hermes config get cron.model` is set |
| Toolsets | `hermes tools list` shows only needed toolsets enabled |
| Verbosity | `hermes config get display.tool_progress` matches customer choice |
| show_cost | `hermes config get display.show_cost` returns `true` |
| Profile | `hermes profile list` shows customer profile |
| Soul.md | `~/.hermes/SOUL.md` exists and contains customer input |
| Skill guardrails | 7 principles loaded from references |
| Skill-retrieval plugin | `hermes plugins list` shows skill-retrieval installed (enabled or disabled per assessment) |
| Plugin baseline | `hermes plugins list` shows `disk-cleanup` enabled (or a recorded declination); enabled-plugin set matches the recorded Step 5c decision |
| Library-rag | `hermes skills list` shows library-rag (if opted in) |
| Use case | Customer answered, skills recommended |
