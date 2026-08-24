---
name: disk-cleanup
description: "Reclaim disk space on a Linux VM. Surveys every space consumer, splits targets into safe vs ask-first, executes the approved set, then verifies the delta."
license: MIT
metadata:
  version: 1.2.0
  author: moonlight-lupin
  platforms: [linux]
  tags: [disk, cleanup, storage, cache, git, docker, vm]
  related_skills: []
---

# Disk Cleanup

Reclaim disk space on a Linux VM. The skill runs a **triage** — survey every space consumer, split targets into *safe* vs *ask*, execute the approved set, then verify the delta.

## When to Use

- User says "disk cleanup", "free up space", "clean up the VM"
- Disk usage above 80%
- After large builds, git operations, or Docker image accumulation

## Procedure

### 1. Baseline

```bash
df -h /
```

**Done:** used and available numbers recorded for the before/after comparison.

### 2. Survey

Build a ranked list of every consumer over ~50M.

```bash
# Hermes data + user caches + tmp
du -sh ~/.hermes/*/ 2>/dev/null | sort -rh | head -20
du -sh ~/.hermes/projects/*/ 2>/dev/null | sort -rh | head -20
du -sh ~/.cache/*/ 2>/dev/null | sort -rh | head -15
du -sh /tmp/* 2>/dev/null | sort -rh | head -15

# Memory store (if Mnemosyne is installed)
du -sh ~/.hermes/mnemosyne/data/* 2>/dev/null | sort -rh

# Session checkpoints (if present)
du -sh ~/.hermes/checkpoints/store/ 2>/dev/null

# Docker
docker system df
docker images --format "{{.Size}}\t{{.Repository}}:{{.Tag}}" | sort -rh | head -25
docker ps -a --filter "status=exited" --format "{{.Image}}" | sort -u

# System
du -sh /var/cache/apt /var/log ~/.cache/pip ~/.cache/uv 2>/dev/null
journalctl --disk-usage
find /var/log \( -name "*.gz" -o -name "*.1" -o -name "*.old" \) 2>/dev/null

# Bloated git repos (orphaned tmp_pack files from interrupted operations)
find ~/.hermes/projects -name ".git" -type d -exec sh -c 'du -sh "$1" 2>/dev/null' _ {} \; | sort -rh | head -10
```

**Done:** every consumer over 50M identified with its size.

### 3. Triage

Split every found target into two buckets. Present the table to the user before executing.

**Safe — execute without asking:**

| Target | Command | Reclaims |
|--------|---------|----------|
| Orphaned git tmp\_packs | `cd /repo && git gc --aggressive --prune=now` | Often multi-GB |
| uv cache | `uv cache prune` | Up to full cache size |
| pip cache | `pip cache purge` | Up to full cache size |
| apt cache | `apt autoclean && apt autoremove -y` | ~100M typical |
| Journal logs | `journalctl --vacuum-size=50M` | Down to 50M |
| Rotated logs | `find /var/log \( -name "*.gz" -o -name "*.1" -o -name "*.old" \) -delete` | ~20M typical |
| Stale /tmp dirs | `find /tmp -maxdepth 1 -mtime +3 -type d -name "*_*" -exec rm -rf {} +` | Varies |
| Browser automation caches | `rm -rf ~/.cache/puppeteer ~/.cache/ms-playwright` | ~650M; re-downloads if needed |
| Old DB backups | `rm /path/to/*.bak.*` when current DB is healthy | Varies |
| Dangling Docker images | `docker image prune -f` | Varies |

**Ask first — user must confirm:**

| Target | Risk |
|--------|------|
| Docker images for stopped containers | May want to restart later |
| Session checkpoint stores | May contain recoverable state |
| Large skill references (PDFs, maps, RAG indexes) | User data |
| Large project uploads | User data |
| Docker images for running services | Disruptive |

**Done:** table presented with safe-only total and with-ask total. User has approved a set.

### 4. Execute

Run the commands from the Safe table for each approved target. Capture before/after size for each.

For **Docker stopped containers + images** (requires two steps):

```bash
docker rm $(docker ps -a --filter "status=exited" --filter "ancestor=IMAGE" -q)
docker rmi IMAGE
```

**Done:** every approved target cleaned. Before/after size captured for each.

### 5. Verify

```bash
df -h /
```

**Done:** total reclaimed reported. Used/free compared against baseline from step 1.

## Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| `git gc` reclaims nothing | No orphaned objects — just large history | Accept the size or run `git repack -ad` for marginal compression |
| tmp\_pack files persist after gc | Git process still running or lock file | `fuser .git/objects/pack/*.pack` to find the process, retry after it ends |
| Docker rmi fails "image is in use" | Stopped container still references it | `docker rm` the container first, then `docker rmi` |
| `apt autoremove` lists wanted packages | Auto-removable deps flagged incorrectly | Review the list before confirming; skip with `apt-mark manual <pkg>` |
| `journalctl --vacuum-size` fails | Journald service issue | `systemctl restart systemd-journald` then retry |
| `uv cache prune` fails | uv not in PATH | Use `python -m uv cache prune` |