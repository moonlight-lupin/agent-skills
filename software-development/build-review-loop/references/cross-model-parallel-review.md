# Cross-Model Parallel Review: Codex + Opus

Technique for running two independent AI code reviewers in parallel, then
synthesizing their findings. Validated Aug 2026 on a SQLite
state store migration (a 2020-line module).

## Contents

- When to use
- Pattern
- What each model tends to catch
- Effort

## When to use

- User asks for "both Codex and Claude Code Opus review"
- Large diff (>500 lines) where multiple perspectives add value
- Architecture-changing refactors where correctness AND design matter
- Any review where the user wants maximum coverage before ship

## Pattern

### 1. Write one review prompt to a file

`/tmp/review-prompt.md` — same prompt for both reviewers. Include:
- What changed and why
- Focus areas (data integrity, concurrency, security, etc.)
- Output format (BLOCKING/MAJOR/MINOR/NIT with file/line/fix)
- "Do NOT make changes — review only"
- "Write your review to /tmp/<reviewer>-review.md"

### 2. Dispatch both in one tool batch (true parallelism)

**Codex (GPT-6 Sol):**
```bash
codex exec --sandbox danger-full-access \
  "Read /tmp/review-prompt.md and review the codebase. Write your full review to /tmp/codex-review.md. Do NOT make any changes to source files." \
  2>&1
```

**Opus (Claude Opus 5):**
```bash
claude -p \
  "Read /tmp/review-prompt.md and review the codebase. Write your full review to /tmp/opus-review.md. Do NOT make any changes to source files." \
  --model opus --allowedTools "Read,Write,Bash" --max-turns 50 --fallback-model sonnet \
  2>&1
```

Both run with `background=true, notify_on_complete=true`.

### 3. Both write to files — NEVER pipe through tail

Reviews are multi-page (one observed review was 64 lines / 8KB for Codex,
365 lines / 22KB for Opus). `tail -5` destroys the content at the shell level
before `process(action="log")` ever sees it. This happened in the session —
the first Codex and Opus runs were truncated to 5 lines each by `tail -5`.

Re-dispatch with "Write your review to /tmp/<name>-review.md" in the prompt.
Then `read_file("/tmp/codex-review.md")` and `read_file("/tmp/opus-review.md")`.

### 4. Synthesize findings

Read both reviews. Create a cross-model synthesis table:

| # | Severity | Issue | Codex | Opus |
|---|---|---|---|---|
| 1 | BLOCKING | KV lost updates | Finding 1 | Finding 1 |
| 2 | BLOCKING | Migration skips legacy data | Finding 2 | Finding 3 |
| 3 | MAJOR | Corrupt JSON silent | Finding 3 | Finding 6/10 |
| 4 | MAJOR | Lease token bypass | Finding 4 | Finding 7 |
| 5 | MAJOR | workspace_audit lost lock | Finding 5 | Finding 2 |
| 6 | MAJOR | _save swallows BEGIN | Finding 6 | NIT |

Classification:
- **Both agree** → highest confidence, fix first
- **Codex-only** → edge cases, correctness, cleanup gaps
- **Opus-only** → architecture, dead code, API divergence, security

### 5. Partition fixes

- Round 1: fix all both-agree BLOCKING + MAJOR findings
- Round 2: fix Opus-only findings (architectural — e.g. route compat functions
  through the new CAS path, enforce MAX_RETRIES in transition_action, add
  column allowlist for SQL injection defense-in-depth)
- Each round: Cursor builds → Hermes verifies → commit

### 6. Opus overload handling

Opus can return `529 Overloaded` during peak hours (happened in this session).
Recovery:
- Retry with `--fallback-model sonnet` — Sonnet completes the review, slightly
  lower quality but still valuable for cross-model coverage
- If Sonnet also fails, retry after 5 minutes
- The first truncated Opus run (tail -5) still produced partial output —
  check `process(action="log")` for fragments before re-dispatching

## What each model tends to catch

### Codex (GPT-6 Sol) tends to catch:
- Data integrity bugs (silent data loss, corrupt JSON handling)
- Concurrency edge cases (BEGIN IMMEDIATE swallowed, TOCTOU gaps)
- Missing terminal states in cleanup
- Duplicate constraints / schema inefficiency
- Version-counter and retry logic gaps

### Opus (Claude Opus 5) tends to catch:
- Dead code / unused new API paths (production callers never use the new CAS)
- State machine divergence between two implementations of the same logic
- SQL injection defense-in-depth (column names via f-string without allowlist)
- YAML mirror divergence risk (two write paths with different side effects)
- Pre-existing bugs faithfully preserved (not regressions but worth flagging)
- Broader architectural critique (O(n) full-table rewrite vs O(1) row update)

### Both tend to catch:
- Lost updates from no-op locks
- Migration failure modes (crash between commit and rename)
- Hash chain corruption from removed locking
- Replay protection bypass

## Effort

- Two parallel reviews: ~10-15 min wall time (vs 20-30 min sequential)
- Synthesis: ~5 min
- Total overhead vs single review: ~5 min, for significantly more coverage
- The Opus review was 3x longer than Codex (365 vs 64 lines) — Opus is more
  verbose but also catches more architectural issues
