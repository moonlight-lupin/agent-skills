---
name: file-organizer
description: "Use when the user wants to organize, tidy, or restructure a messy directory (Downloads, Desktop, documents folder). LLM-powered file organizer that scans content, proposes a structure, and executes moves in chunks with a mandatory user confirmation gate."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [file-management, organization, cleanup, productivity]
---

# File Organizer

An LLM-powered file organizer that reads file contents, proposes a sensible folder
structure with renamed files, and executes moves in chunks — with a mandatory user
confirmation gate before any filesystem changes.

## Overview

Inspired by [LlamaFS](https://github.com/iyaja/llama-fs) but designed for Hermes:
the script handles filesystem I/O (scan, read snippets, execute moves). The agent's
own LLM does the reasoning by default. An optional `propose` subcommand can call a
cheaper external LLM (deepseek, openrouter, ollama) for cost-conscious runs on large
directories. Uses stdlib-only HTTP (urllib) — no requests/openai SDK needed.

## When to Use

- User says "organize my Downloads" / "tidy my Desktop" / "clean up this folder"
- User has a messy directory and wants files sorted into categories
- User wants files renamed based on their content (not just moved)
- User wants to organize files on a local disk, network mount, or remote filesystem

**Don't use for:**
- Bulk file deletion (this skill only moves and renames, never deletes)
- Deduplication (use a dedicated dedup tool)
- File content search (use `search_files` instead)

## Workflow

### Step 1 — Scan

Run the scan script to get file metadata + content snippets:

```bash
python3 scripts/organize.py scan --path <directory> [--depth N] [--max-snippet-chars 500]
```

Output is a JSON array. Each file entry contains:
- `path`: full file path
- `relative_path`: path relative to scanned directory
- `name`: current filename
- `size`: bytes
- `mtime`: ISO timestamp
- `type`: text, image, audio, pdf, office, archive, other
- `mime`: detected MIME type
- `snippet`: first N chars of content (text/pdf) or metadata (image/audio)

Flags: `--depth N` (max directory depth), `--max-snippet-chars N` (per-file snippet limit, default 500), `--include-hidden` (include dotfiles, skipped by default).

### Step 2 — Propose Organization (Agent LLM — Default)

Using the scan output, reason about:
- Natural categories based on file content and types
- A clean folder hierarchy (not too deep — 2-3 levels max)
- Descriptive filenames that reflect content (not `IMG_3847.jpg` → `Hawaii-Beach-Sunset.jpg`)
- Time-based grouping when appropriate (e.g., `2024-Taxes/`, `2023-Receipts/`)

Build a plan JSON:
```json
{
  "source_dir": "<scanned dir>",
  "moves": [
    {"source": "<full path>", "destination": "<full path>"}
  ],
  "folders_to_create": ["<full path>", ...]
}
```

**Cost-saving offer:** When presenting the plan (Step 3), mention to the user:
> "This used the agent's own model. For larger directories, I can run the reasoning
> through a cheaper LLM to save costs. Available options:"
>
> | Provider | Model | Cost | Notes |
> |----------|-------|------|-------|
> | deepseek | deepseek-chat | ~$0.14/M in, $0.28/M out | Cheapest cloud |
> | openrouter | deepseek/deepseek-chat | pay-as-you-go | Multi-model routing |
> | ollama | llama3.2:3b | Free (local CPU) | Slow but zero cost |
>
> Just say "use deepseek" or "use ollama" and I'll re-run via the cheaper model.

Only offer this if the scan had 20+ files (not worth it for tiny directories).

**Using a cheaper model (opt-in):** If the user requests a cheaper model, or if the
directory is very large (100+ files), use the `propose` subcommand instead:

```bash
python3 scripts/organize.py propose --scan /tmp/scan.json --source-dir <dir> \
  --provider deepseek [--model <model-id>]
```

Provider priority: `--provider` flag > `DEEPSEEK_API_KEY` env > `OPENAI_API_KEY` env
> `OPENROUTER_API_KEY` env > `OLLAMA_HOST` env > error

If `propose` fails (network, auth, parse), fall back to agent reasoning manually.

### Step 3 — Present Plan to User (MANDATORY GATE)

**This step is non-negotiable.** Present the plan as a formatted table:

| # | Current Name | → | New Location | Type | Snippet Preview |
|---|---|---|---|---|---|

Ask the user to:
- Confirm the plan as-is
- Adjust specific moves (rename, re-categorize, skip)
- Cancel entirely

**Never proceed to execution without explicit user confirmation.**

### Step 4 — Execute in Chunks

After user confirms, write the plan to a temp file and execute:

```bash
python3 scripts/organize.py execute --plan /tmp/plan.json --chunk-size 10
```

The script:
- Creates destination folders first
- Moves files in chunks of 10 (configurable)
- Prints progress after each chunk: `[chunk 2/5] moved 10, failed 0`
- Skips conflicts (destination exists) — never overwrites
- Logs per-file errors without aborting the batch

### Step 5 — Report Results

Present the final summary to the user:
- Files moved successfully
- Files skipped (conflicts)
- Files failed (errors)
- Suggest next steps (e.g., "want me to organize another directory?")

## Cross-Filesystem Support

The organizer works on any path accessible from the host:

| Target | Path Format | Notes |
|--------|-------------|-------|
| Local disk | Any local path | Direct filesystem access |
| Network mount | NFS, SMB/CIFS, SSHFS mounts | Use smaller chunk sizes for latency |
| Remote filesystem | Any path Python `shutil.move` can handle | SSHFS, FUSE, etc. |

## Key Guardrails

1. **Never delete** — only move and rename. If the user wants deletions, that's a
   separate task with its own confirmation flow.
2. **Never overwrite** — if a destination file exists, skip and log.
3. **Always gate** — present plan to user before executing. No silent moves.
4. **Chunk execution** — process in batches of 10 to manage failures gracefully.
5. **Agent LLM by default, cheap LLM opt-in** — `scan` and `execute` are pure
   filesystem I/O. The agent's own LLM does the reasoning by default. The `propose`
   subcommand is an opt-in for cheaper external models on large directories.

## Common Pitfalls

1. **Huge directories** — scanning 10,000+ files will produce massive output. Use
   `--depth 1` first to survey, then drill into subdirectories. Or scan by file type
   subsets.

2. **Binary files with no snippet** — images, audio, office docs get metadata only.
   The LLM must infer categories from filename, size, and mtime.

3. **Paths with spaces** — always quote paths in the plan JSON. The script handles
   this correctly via Python pathlib.

4. **Network filesystem latency** — organizing files on SSHFS/NFS/SMB mounts is
   slower due to network round-trips. Use smaller chunk sizes (5) for remote targets.

5. **Permission errors** — some files may not be readable. The scan script handles
   this gracefully (returns metadata with `snippet: null`).

## Verification Checklist

- [ ] Scan completed and returned JSON output
- [ ] Plan includes `source_dir`, `moves`, and `folders_to_create`
- [ ] Plan presented to user as a table with clear before → after mapping
- [ ] User explicitly confirmed the plan
- [ ] Plan written to temp JSON file
- [ ] Execution completed with chunked progress output
- [ ] Final summary reported (moved / failed / skipped counts)
- [ ] No files were deleted or overwritten

## One-Shot Recipes

### Organize Downloads folder
```bash
# 1. Scan
python3 scripts/organize.py scan --path ~/Downloads --depth 2 > /tmp/scan.json

# 2. Agent reasons over scan JSON, builds plan (default — uses agent's own LLM)
#    OR for large directories, use cheap LLM:
#    python3 scripts/organize.py propose --scan /tmp/scan.json --source-dir ~/Downloads --provider deepseek > /tmp/plan.json

# 3. Agent presents plan to user (with cost-saving offer if 20+ files)

# 4. After confirmation:
python3 scripts/organize.py execute --plan /tmp/plan.json --chunk-size 10
```

### Organize a network-mounted directory
```bash
# 1. Scan
python3 scripts/organize.py scan --path /mnt/remote/Desktop --depth 2 > /tmp/scan.json

# 2. Agent reasons over scan JSON, builds plan (default)
#    OR: python3 scripts/organize.py propose --scan /tmp/scan.json --source-dir /mnt/remote/Desktop --provider deepseek > /tmp/plan.json

# 3. Agent presents plan to user

# 4. After confirmation (smaller chunks for network latency):
python3 scripts/organize.py execute --plan /tmp/plan.json --chunk-size 5
```

### Dry run (preview only)
```bash
python3 scripts/organize.py execute --plan /tmp/plan.json --dry-run
```

### Cheap LLM (opt-in for large directories)
```bash
# Scan → Propose via deepseek → Execute
python3 scripts/organize.py scan --path ~/Downloads > /tmp/scan.json
python3 scripts/organize.py propose --scan /tmp/scan.json --source-dir ~/Downloads --provider deepseek > /tmp/plan.json
# Agent reviews plan, presents to user, then:
python3 scripts/organize.py execute --plan /tmp/plan.json --chunk-size 10
```

### Run self-tests
```bash
python3 scripts/organize.py --self-test
```

## Script Reference

| Command | Purpose |
|---------|---------|
| `scan --path <dir> [--depth N] [--max-snippet-chars N] [--include-hidden]` | Scan directory, output JSON with file metadata + snippets |
| `propose --scan <json> --source-dir <dir> [--provider <p>] [--model <m>]` | **Opt-in**: call a cheap external LLM to generate plan JSON |
| `execute --plan <json> [--chunk-size N] [--dry-run]` | Execute move plan in chunks, print progress per chunk |
| `--self-test` | Run built-in test suite (19 tests, self-contained in tempdir) |

Optional Python deps (degrade gracefully if missing):
- `Pillow` — image dimensions and EXIF dates
- `mutagen` — audio duration and ID3 tags
- `PyMuPDF` (fitz) — PDF first-page text extraction