#!/usr/bin/env bash
# Weekly health check — consolidated report
# Chains: host status, disk usage, log anomalies, input token overhead
# Always outputs a report. Includes suggested actions when alerts are found.
# Runs as a no_agent cron job. No LLM cost.
set -euo pipefail

# Load env vars from .env (for any skill scripts that need them)
if [ -f ~/.hermes/.env ]; then
  set -a
  while IFS='=' read -r key val; do
    [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
    export "$key=$val"
  done < ~/.hermes/.env
  set +a
fi

REPORT=""
HAS_ALERTS=0
ACTIONS=""

# ─── 1. Host status ───────────────────────────────────────────────

HOST_TYPE="unknown"
HOST_INFO=""

if [ -f /proc/device-tree/model ]; then
  HOST_TYPE="raspberry-pi"
  HOST_INFO=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo "Raspberry Pi")
elif command -v systemd-detect-virt &>/dev/null; then
  VIRT=$(systemd-detect-virt 2>/dev/null || echo "none")
  if [ "$VIRT" = "none" ] || [ "$VIRT" = "bare-metal" ]; then
    HOST_TYPE="bare-metal"
    HOST_INFO=$(uname -srm)
  else
    HOST_TYPE="vm"
    HOST_INFO="${VIRT} $(uname -srm)"
  fi
elif [ "$(uname -s)" = "Darwin" ]; then
  HOST_TYPE="mac"
  HOST_INFO=$(uname -srm)
elif grep -qi microsoft /proc/version 2>/dev/null; then
  HOST_TYPE="windows-wsl"
  HOST_INFO="WSL $(uname -srm)"
else
  HOST_TYPE="linux-unknown"
  HOST_INFO=$(uname -srm)
fi

UPTIME=$(uptime -p 2>/dev/null | sed 's/up //' || echo "unknown")
LOAD=$(cat /proc/loadavg 2>/dev/null | awk '{print $1, $2, $3}' || echo "n/a")

# CPU count for load context
CPU_COUNT=$(nproc 2>/dev/null || echo "?")

REPORT+="## Host Status"$'\n'
REPORT+="- Type: ${HOST_TYPE}"$'\n'
REPORT+="- Info: ${HOST_INFO}"$'\n'
REPORT+="- Uptime: ${UPTIME}"$'\n'
REPORT+="- Load: ${LOAD} (${CPU_COUNT} CPUs)"$'\n'$'\n'

# High load check
LOAD1=$(echo "$LOAD" | awk '{print $1}' 2>/dev/null || echo "0")
LOAD_HIGH=$(python3 -c "print(1 if float('${LOAD1}') > ${CPU_COUNT} * 0.8 else 0)" 2>/dev/null || echo "0")
if [ "$LOAD_HIGH" = "1" ]; then
  REPORT+="⚠️  Load average (${LOAD1}) exceeds 80% of CPU capacity (${CPU_COUNT} cores)"$'\n'$'\n'
  ACTIONS+="- **High load** (${LOAD1} on ${CPU_COUNT} CPUs): check for runaway processes with \`top\` or \`htop\`"$'\n'
  HAS_ALERTS=1
fi

# ─── 2. Disk usage ─────────────────────────────────────────────────

DISK_OUTPUT=""
DISK_ALERTS=0
DISK_THRESHOLD=80

while IFS= read -r line; do
  [ -z "$line" ] && continue
  PCT=$(echo "$line" | awk '{print $5}' | tr -d '%')
  MOUNT=$(echo "$line" | awk '{print $6}')
  if [ -n "$PCT" ] && [ "$PCT" -ge "$DISK_THRESHOLD" ] 2>/dev/null; then
    DISK_OUTPUT+="⚠️  ${MOUNT}: ${PCT}% full"$'\n'
    DISK_ALERTS=1
    HAS_ALERTS=1
  fi
done < <(df -h 2>/dev/null | tail -n +2)

if [ "$DISK_ALERTS" -eq 1 ]; then
  REPORT+="## Disk Usage"$'\n'
  REPORT+="${DISK_OUTPUT}"$'\n'
  ACTIONS+="- **Disk above ${DISK_THRESHOLD}%**: run the disk-cleanup skill to reclaim space (\`skill_view(name='disk-cleanup')\`)"$'\n'
else
  ROOT_PCT=$(df -h / 2>/dev/null | tail -1 | awk '{print $5}')
  REPORT+="## Disk Usage"$'\n'
  REPORT+="- All mounts below ${DISK_THRESHOLD}% threshold (root: ${ROOT_PCT})"$'\n'$'\n'
fi

# ─── 3. Log anomalies ──────────────────────────────────────────────

LOG_SCRIPT=~/.hermes/skills/agent-ops/log-analyzer/scripts/analyze_logs.py
LOG_FILE=~/.hermes/logs/agent.log
LOG_SCAN="/tmp/weekly-log-scan.json"
LOG_ALERTS=0

if [ -f "$LOG_SCRIPT" ] && [ -f "$LOG_FILE" ]; then
  python3 "$LOG_SCRIPT" scan --log-file "$LOG_FILE" --since 7d --quiet --output "$LOG_SCAN" 2>/dev/null || true
  if [ -s "$LOG_SCAN" ]; then
    LOG_REPORT=$(python3 "$LOG_SCRIPT" report --scan "$LOG_SCAN" 2>/dev/null || echo "")
    if [ -n "$LOG_REPORT" ]; then
      REPORT+="## Log Anomalies (7d)"$'\n'
      REPORT+="${LOG_REPORT}"$'\n'$'\n'
      HAS_ALERTS=1
      LOG_ALERTS=1
    fi
  fi
fi

# Also check state.db failures
STATE_SCRIPT=~/.hermes/skills/agent-ops/log-analyzer/scripts/state_failures.py
STATE_ALERTS=0
if [ -f "$STATE_SCRIPT" ]; then
  STATE_OUTPUT=$(python3 "$STATE_SCRIPT" --quiet --days 7 2>/dev/null || true)
  if [ -n "$STATE_OUTPUT" ]; then
    REPORT+="## Session Failures (7d)"$'\n'
    REPORT+="${STATE_OUTPUT}"$'\n'$'\n'
    HAS_ALERTS=1
    STATE_ALERTS=1
  fi
fi

# Suggest actions for log anomalies
if [ "$LOG_ALERTS" -eq 1 ]; then
  # Extract top error cluster count for a more specific suggestion
  CLUSTER_COUNT=$(python3 -c "
import json
try:
    with open('$LOG_SCAN') as f:
        data = json.load(f)
    clusters = data.get('anomalies', {}).get('error_clusters', [])
    print(len(clusters))
except: print(0)
" 2>/dev/null || echo "0")
  if [ "$CLUSTER_COUNT" -gt "0" ]; then
    ACTIONS+="- **${CLUSTER_COUNT} error cluster(s)** in logs: review the most frequent error — if it is a recurring infrastructure issue (git gc, adapter rebuild), schedule a fix"$'\n'
  fi
  # Check for rate limits
  HAS_RATE_LIMITS=$(python3 -c "
import json
try:
    with open('$LOG_SCAN') as f:
        data = json.load(f)
    rl = data.get('anomalies', {}).get('rate_limits', [])
    print(1 if rl else 0)
except: print(0)
" 2>/dev/null || echo "0")
  if [ "$HAS_RATE_LIMITS" = "1" ]; then
    ACTIONS+="- **Rate limit hits detected**: check provider quotas or rotate API keys in \`~/.hermes/.env\`"$'\n'
  fi
  # Check for timeouts
  HAS_TIMEOUTS=$(python3 -c "
import json
try:
    with open('$LOG_SCAN') as f:
        data = json.load(f)
    to = data.get('anomalies', {}).get('timeouts', [])
    print(1 if to else 0)
except: print(0)
" 2>/dev/null || echo "0")
  if [ "$HAS_TIMEOUTS" = "1" ]; then
    ACTIONS+="- **Timeout clusters detected**: check network connectivity to the affected endpoints"$'\n'
  fi
fi

# Suggest actions for session failures
if [ "$STATE_ALERTS" -eq 1 ]; then
  # Extract low success rate tools
  LOW_TOOLS=$(python3 "$STATE_SCRIPT" --days 7 --json 2>/dev/null | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    tools = data.get('tools', [])
    low = [t['tool'] for t in tools if t.get('success_rate', 100) < 95]
    print(', '.join(low) if low else '')
except: print('')
" 2>/dev/null || echo "")
  if [ -n "$LOW_TOOLS" ]; then
    ACTIONS+="- **Tools below 95% success rate**: ${LOW_TOOLS} — review failing tool calls and check configurations"$'\n'
  fi
fi

# ─── 4. Input token overhead ───────────────────────────────────────

OVERHEAD_OUTPUT=$(python3 -c "
import yaml, pathlib, glob, os, re, sys

files = glob.glob(os.path.expanduser('~/.hermes/skills/**/SKILL.md'), recursive=True)
count = 0; total_chars = 0
for f in files:
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
    except: pass

desc_tokens = total_chars // 4
ctx = 128000
try:
    with open(os.path.expanduser('~/.hermes/config.yaml')) as fh:
        cfg = yaml.safe_load(fh) or {}
    ctx = cfg.get('model', {}).get('context_length', 128000)
except: pass

skill_ratio = desc_tokens / ctx if ctx else 0
SKILL_COUNT_THRESHOLD = 50
SKILL_RATIO_THRESHOLD = 0.05

lines = []
lines.append(f'- Skills: {count}')
lines.append(f'- Skill description tokens: ~{desc_tokens} ({skill_ratio:.1%} of {ctx} context)')

alert = False
if count > SKILL_COUNT_THRESHOLD:
    lines.append(f'⚠️  Skill count {count} exceeds threshold {SKILL_COUNT_THRESHOLD}')
    alert = True
if skill_ratio > SKILL_RATIO_THRESHOLD:
    lines.append(f'⚠️  Skill overhead {skill_ratio:.1%} exceeds {SKILL_RATIO_THRESHOLD:.0%} threshold')
    alert = True

print('\n'.join(lines))
sys.exit(1 if alert else 0)
" 2>/dev/null > /tmp/overhead_check.txt) && OVERHEAD_EXIT=0 || OVERHEAD_EXIT=$?
OVERHEAD_OUTPUT=$(cat /tmp/overhead_check.txt 2>/dev/null || true)
if [ -n "$OVERHEAD_OUTPUT" ]; then
  REPORT+="## Input Token Overhead"$'\n'
  REPORT+="${OVERHEAD_OUTPUT}"$'\n'$'\n'
  if [ "$OVERHEAD_EXIT" -ne 0 ]; then
    HAS_ALERTS=1
    ACTIONS+="- **Skill overhead exceeds threshold**: enable skill-retrieval plugin (\`hermes plugins enable skill-retrieval\`) to reduce per-turn token cost"$'\n'
  fi
fi

# ─── Suggested actions ─────────────────────────────────────────────

if [ "$HAS_ALERTS" -eq 1 ]; then
  REPORT+="## Suggested Actions"$'\n'
  REPORT+="${ACTIONS}"$'\n'
  REPORT+="Run \`hermes chat -q \"Fix the issues from the weekly health check\"\` to let the agent investigate and resolve."$'\n'
else
  REPORT+="## Suggested Actions"$'\n'
  REPORT+="- No actions needed. All checks passed."$'\n'
fi

# ─── Output ────────────────────────────────────────────────────────

echo "# Weekly Health Check"
echo
echo "$REPORT"
exit 0