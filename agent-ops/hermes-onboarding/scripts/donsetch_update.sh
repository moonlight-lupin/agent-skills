#!/usr/bin/env bash
# DonSeTch weekly release-binary updater (self-update path, no source build).
# Gates on GitHub releases/latest (published releases with assets), not tags —
# a tag without published assets made `donsetch update` 404 in Aug 2026.
set -u
BIN=/usr/local/lib/node_modules/donsetch/binaries/donsetch
DIR=$(dirname "$BIN")
BACKUP_DIR=/root/.hermes/backups/donsetch
REPO=dondai44423/donsetch
export DONGHOST_CHROME=/usr/bin/google-chrome-stable DONGHOST_NO_SANDBOX=1

parse_ver() { grep -oE '[0-9]+\.[0-9]+\.[0-9]+' <<< "$1" | head -1; }

cur=$(parse_ver "$("$BIN" --version 2>/dev/null)") || cur=""
if [ -z "$cur" ]; then
  echo "donsetch-updater: FAIL cannot read current version at $BIN"
  exit 1
fi

latest=$(curl -sf --max-time 30 "https://api.github.com/repos/$REPO/releases/latest" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tag_name","").lstrip("v"))' 2>/dev/null) || latest=""
if [ -z "$latest" ]; then
  echo "donsetch-updater: SKIP cannot read releases/latest (network or API issue). Staying on $cur."
  exit 0
fi

if [ "$cur" = "$latest" ]; then
  # Healthy no-op: silent for the cron watchdog (empty stdout sends nothing).
  exit 0
fi

echo "donsetch-updater: update $cur -> $latest"
mkdir -p "$BACKUP_DIR"
cp -a "$BIN" "$DIR/libonnxruntime.so" "$BACKUP_DIR/" 2>/dev/null

# Let the tool self-update (SHA256-verified asset from GitHub Releases).
"$BIN" update > /tmp/donsetch_update.log 2>&1
rc=$?
new=$(parse_ver "$("$BIN" --version 2>/dev/null)") || new=""

if [ $rc -ne 0 ] || [ "$new" != "$latest" ]; then
  echo "donsetch-updater: FAIL self-update (rc=$rc, now at ${new:-unknown}). Log tail:"
  tail -3 /tmp/donsetch_update.log
  # restore backup in case the self-update half-swapped files
  cp -a "$BACKUP_DIR/donsetch" "$BACKUP_DIR/libonnxruntime.so" "$DIR/" 2>/dev/null
  echo "donsetch-updater: rolled back to $cur."
  exit 1
fi

# Health gate: doctor (non-deep) must pass
if ! "$BIN" doctor > /tmp/donsetch_doctor.log 2>&1; then
  echo "donsetch-updater: FAIL doctor after update to $new. Rolling back."
  cp -a "$BACKUP_DIR/donsetch" "$BACKUP_DIR/libonnxruntime.so" "$DIR/" 2>/dev/null
  tail -3 /tmp/donsetch_doctor.log
  echo "donsetch-updater: rolled back to $cur."
  exit 1
fi

# Smoke gate: tier-1 fetch must return content_ok=true
ok=$("$BIN" fetch https://example.com --json 2>/dev/null \
  | python3 -c 'import json,sys
d=json.load(sys.stdin)
m=d.get("structuredContent",d).get("meta",{})
print("yes" if (m.get("content_ok") or d.get("content_ok")) else "no")' 2>/dev/null) || ok="no"
if [ "$ok" != "yes" ]; then
  echo "donsetch-updater: FAIL smoke fetch after update to $new. Rolling back."
  cp -a "$BACKUP_DIR/donsetch" "$BACKUP_DIR/libonnxruntime.so" "$DIR/" 2>/dev/null
  echo "donsetch-updater: rolled back to $cur."
  exit 1
fi

echo "donsetch-updater: UPDATED $cur -> $new (doctor+smoke passed). New version active on next Hermes session."