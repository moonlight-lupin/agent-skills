# Persistent Loop Plan (planning-with-files port)

Ported concepts (Sep 2026) from OthmanAdi/planning-with-files (MIT, reviewed
Sep 2026; verdict Watch — concepts ported, plugin NOT installed). The
problem: a multi-batch build-review loop spans days and sessions. Execution
state that lives only in the orchestrator's context or in chat history dies
with compaction. The fix: the loop's working memory lives on disk in plain
markdown, and every session resumes by reading it — not by recalling.

## Contents

- The three files
- loop-plan.md format (what loop_plan_check.py parses)
- Loop discipline
- Token economics
- What was NOT ported

## The three files

For any loop with 2+ batches or an expected lifespan past one session, the
orchestrator creates, in the PROJECT directory (gitignored — see below):

```
<project>/
├── loop-plan.md     ← phases (= batches) + **Status:** fields; the resume point
├── loop-findings.md ← review insights, decisions, verified root causes
└── loop-progress.md ← one entry per round: dispatch result path, verdict, commit
```

Naming is deliberately distinct from the repo's own docs so nothing ships by
accident. These are WORKING STATE, never committed: add
`loop-*.md` + `*.attest` to the project's `.gitignore` (or a local exclude:
`git config core.excludesFile`). At delivery, durable insights are promoted
into the repo (ADR, docs, CHANGELOG) — the loop files are not the record.

## loop-plan.md format (what loop_plan_check.py parses)

```markdown
# Loop Plan: <project> — <theme>

## Goal
<one paragraph, restated in full — a resuming session reads ONLY this file>

### Phase 1 - Batch A: money correctness
**Status:** in_progress
- [x] Red contract tests committed (9 tests)
- [ ] Cursor build R1
- [ ] Dual review + fix round

### Phase 2 - Batch B: entity deepening
**Status:** pending
- [ ] ...

## Errors Encountered
<one line per failure worth remembering, with the verified cause>

## Decisions Made
<design calls with their rationale, dated>

## Current Phase
Phase 1 — resume at: Cursor build R1 (dispatch result /tmp/...-r1.json)
```

Rules: status tokens are exactly `pending` / `in_progress` / `complete` in
`**Status:**` lines. Checkboxes `- [ ]` / `- [x]` carry the phase's tasks.
The Goal section must be self-contained — write it as if the reader has no
conversation history, because it will have exactly that.

## Loop discipline

1. **Create at loop start** (Phase 0): write loop-plan.md from the batch
   plan, attest it (`scripts/attest_file.py attest loop-plan.md`), commit
   the .gitignore change if any. Phase statuses start `pending`.
2. **Resume ritual** — the FIRST action of any session joining the loop:
   read loop-plan.md, run `scripts/loop_plan_check.py loop-plan.md` for the
   resume pointer, read loop-progress.md's last entry, read the referenced
   dispatch result file. Only then act. No memory-based resumption.
3. **Update after every state change** (dispatch captured, review verdict,
   commit, fix round): tick checkboxes, set statuses, append to
   loop-progress.md, update `## Current Phase`. Keep `## Errors
   Encountered` and `## Decisions Made` current — these are what the
   review round and the next session actually reuse.
4. **Gate before done**: run `scripts/loop_plan_check.py loop-plan.md
   --gate`. Exit 1 = work remains; the loop is not done regardless of what
   any round reported. Exit 0 = deliver. This is the completion gate
   WITHOUT a hook — it lives in the delivery checklist instead of in
   Hermes' hook chain (deliberate: no third-party per-turn hooks).
5. **Brief attestation**: after writing a builder brief, run
   `attest_file.py attest <brief>`; after the build exits, `verify` it. A
   TAMPERED result is a BLOCKING finding — the builder edited its own
   instructions (pitfall #20 made mechanical). Same for Hermes-written
   contract-test files: attest before dispatch, verify after.
6. **Steering a running builder: supersede the brief file in place, never
   assume stdin** — background `agent` dispatches on non-local backends have
   closed stdin, so mid-flight `process(action="write")` steering fails. The
   builder re-reads its brief by PATH at natural checkpoints (it re-reads when
   transitioning between findings). To course-correct a running build, rewrite
   the brief file the builder was pointed at (`cp NEW.md BRIEF.md`) and verify
   uptake by output: the builder's log must name the new items, and the
   canary must change (e.g. the probe for the headline fix flips). If the log
   shows it never re-read the file (no mention of the new items), treat
   that build as working from the stale brief and verify every stale item
   independently after exit — a partial fix round then needs a follow-up
   dispatch enumerating exactly the un-fixed items. Cheaper alternative when
   the builder has just started: kill it and re-dispatch with the full new
   brief. Uptake is also TIME-SENSITIVE: if the builder already passed its
   brief-read checkpoint when you supersede, it completes the OLD scope —
   grep its log for the supersede marker before interpreting silence as
   uptake. Recovery for a mid-loop `git stash pop` conflict caused while
   verifying a base branch in the live tree: `git checkout -q HEAD -- <files>`
   restores the committed state (see `tool-mechanics-pitfalls.md` #28 — use
   `git worktree` next time); untracked leftover test files from earlier
   sessions run in the suite and fail without belonging to the branch —
   check `git status --short` before diagnosing suite failures.
7. **Orchestrator-owned test fixes: fix the test expectation directly, in
   the same turn it is diagnosed** — when a builder correctly stops with
   "blocked: contract test asserts the wrong path/shape" (pitfall #24's
   stop-signal), the fix is a one-line test edit by the orchestrator — do
   NOT route it back through Cursor and do not leave it pending. The stop
   message names the exact assertion; the fix is a test-only edit (no
   production code), which pitfall #24 already exempts from the
   no-hand-coding rule. Re-run the test file immediately to confirm green,
   then re-dispatch the builder with "the test is fixed, resume". Waiting
   on this fix blocks every dependent item behind it (e.g. removing a
   backward-compat shim the test was accidentally rewarding).

## Token economics

This costs tokens only when the orchestrator reads/writes the files — a few
hundred per state change, no per-turn hook, no injection into builder or
reviewer contexts unless the brief chooses to include the plan excerpt.
The planning-with-files plugin pays ~1k tokens/turn on every session for
always-on injection; we pay only inside active loops.

## What was NOT ported

See `references/planning-with-files-adaptation.md` — the native Hermes
plugin, per-turn injection hooks, SHA attestation enforced at injection
time, and the parallel-session write guard (our loops are single-orchestrator).
