---
name: disk-cleanup
description: "Use when df says disk is above 80% full or the user wants to reclaim storage space on a VM."
license: MIT
metadata:
  version: 1.3.0
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
df -h
```

**Done:** used and available numbers recorded for all mounts for the before/after comparison.

### 2. Survey

**Requires root** for apt, journalctl, and /var/log operations. Non-root users can survey but cannot clean system paths.

Build a ranked list of every consumer over ~50M. Survey all mounts, not just `/`.

```bash
# All mounts (not just /)
df -h
df -i                           # inode exhaustion — "No space left on device" with free blocks

# Deleted-but-open files (canonical "df says full, du says empty" case)
lsof +L1 2>/dev/null | head -20

# Hermes data + user caches + tmp (stay on one filesystem, don't cross mounts)
du -xsh ~/.hermes/*/ 2>/dev/null | sort -rh | head -20
du -xsh ~/.hermes/projects/*/ 2>/dev/null | sort -rh | head -20
du -xsh ~/.cache/*/ 2>/dev/null | sort -rh | head -15
du -xsh /tmp/* 2>/dev/null | sort -rh | head -15

# Memory store (if Mnemosyne is installed)
du -xsh ~/.hermes/mnemosyne/data/* 2>/dev/null | sort -rh

# Session checkpoints (if present)
du -xsh ~/.hermes/checkpoints/store/ 2>/dev/null

# Docker
docker system df                # shows build cache separately from images
docker images --format "{{.Size}}\t{{.Repository}}:{{.Tag}}" | sort -rh | head -25
docker ps -a --filter "status=exited" --format "{{.Image}}" | sort -u

# System
du -xsh /var/cache/apt /var/log ~/.cache/pip ~/.cache/uv 2>/dev/null
journalctl --disk-usage
find /var/log \( -name "*.gz" -o -name "*.1" -o -name "*.old" \) 2>/dev/null

# Bloated git repos (orphaned tmp_pack files from interrupted operations)
find ~/.hermes/projects -name ".git" -type d -exec sh -c 'du -sh "$1" 2>/dev/null' _ {} \; | sort -rh | head -10
```

**Done:** every consumer over 50M identified with its size. All mounts surveyed. Inode exhaustion and deleted-but-open files checked.

### 3. Triage

Split every found target into two buckets. Present the table to the user before executing.

**Safe — execute without asking:**

| Target | Command | Reclaims |
|--------|---------|----------|
| uv cache | `uv cache prune` | Up to full cache size |
| pip cache | `pip cache purge` | Up to full cache size |
| apt cache | `apt autoclean` | ~100M typical |
| Journal logs | `journalctl --vacuum-size=50M` | Down to 50M |
| Rotated logs | `find /var/log \( -name "*.gz" -o -name "*.1" -o -name "*.old" \) -delete` | ~20M typical |
| Browser automation caches | `rm -rf ~/.cache/puppeteer ~/.cache/ms-playwright` | ~650M; re-downloads if needed |
| Dangling Docker images | `docker image prune -f` | Varies |
| Docker build cache | `docker builder prune -f` | Often multi-GB; largest Docker consumer |

**Ask first — user must confirm:**

| Target | Risk | Command |
|--------|------|---------|
| git gc aggressive | Destroys recoverable objects (dropped stashes, orphaned commits after bad reset). Aggressive repack temporarily grows disk use. | `cd /repo && git gc --aggressive --prune=now` |
| apt autoremove | May remove wanted packages. Review the list before confirming. | `apt autoremove` (without -y) |
| Old DB backups | Confirm current DB is healthy first. Use explicit paths, not globs. | `rm /path/to/specific-backup.bak` |
| Stale /tmp dirs | Directory mtime does not track activity inside. List before deleting. | `find /tmp -maxdepth 1 -mtime +3 -type d -name "*_*" \| xargs ls -ld` then confirm |
| Docker images for stopped containers | May want to restart later | `docker rmi <image>` |
| Session checkpoint stores | May contain recoverable state | — |
| Large skill references (PDFs, maps, RAG indexes) | User data | — |
| Large project uploads | User data | — |
| Docker images for running services | Disruptive | — |

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
df -h
```

Compare per-mount against baseline from step 1.

**Done:** total reclaimed reported per mount. Used/free compared against baseline.

## Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| `df` shows free blocks but writes fail with ENOSPC | Inode exhaustion — millions of small files. Check `df -i`. | Locate with `find <mount> -xdev -type f \| head -100000 \| wc -l` per directory, then clear the offending cache/spool. Disk-size cleanup will not help. |
| `df` says full but `du` shows nothing | A process holds a deleted file open. Check `lsof +L1`. | Identify the holding process with `lsof +L1`, restart it (or truncate via `cat /dev/null > /proc/<pid>/fd/<n>`). No file deletion reclaims this. |
| `git gc` reclaims nothing | No orphaned objects — just large history | Accept the size or run `git repack -ad` for marginal compression |
| tmp\_pack files persist after gc | Git process still running or lock file | `fuser .git/objects/pack/*.pack` to find the process, retry after it ends |
| Docker rmi fails "image is in use" | Stopped container still references it | `docker rm` the container first, then `docker rmi` |
| `apt autoremove` lists wanted packages | Auto-removable deps flagged incorrectly | Review the list before confirming; skip with `apt-mark manual <pkg>` |
| `journalctl --vacuum-size` fails | Journald service issue | `systemctl restart systemd-journald` then retry |
| `uv cache prune` fails | uv not in PATH | Use `python -m uv cache prune` |