# Parallel Dual-Review (Codex + Opus simultaneously)

When the user asks for both Codex AND Opus to review (e.g. "have codex and opus review"), dispatch both in parallel from the same review prompt file. This catches more issues than sequential review because the two models have orthogonal blind spots.

## Contents

- Model specialisation
- Dispatch pattern
- Pitfalls
- Synthesis format
- Depth-tier asymmetry is normal — verify the second reviewer's headline
- Cross-model overlap case study (Aug 2026)

## Model specialisation

- **Codex (GPT-6 Sol)** — tends to focus on core logic, data integrity, control flow, per-file analysis
- **Opus (Claude Opus 5)** — tends to focus on cross-file analysis, architecture, edge cases, and reproduces issues empirically by running commands

## Dispatch pattern

1. Write ONE review prompt to `/tmp/review-prompt-final.md`
2. Dispatch Codex in background:
   ```bash
   codex exec --sandbox danger-full-access \
     "Read /tmp/review-prompt-final.md. Review the diff (git diff <base>..HEAD -- tests/). Write your review to /tmp/review-codex-final.md. Be thorough." \
     2>&1 | tail -5
   ```
   Run with `background=true, pty=true, notify_on_complete=true`.

3. Dispatch Opus in background:
   ```bash
   claude -p \
     "Read /tmp/review-prompt-final.md. Review the diff (git diff <base>..HEAD -- tests/). Write your review to /tmp/review-opus-final.md. Be thorough." \
     --model opus --max-turns 50 --allowedTools "Read,Bash" \
     2>&1 | tail -5
   ```
   Run with `background=true, notify_on_complete=true`.

4. Wait for both to complete (`process(action="wait")` on each session ID).
5. Read both review files with `read_file`.
6. Synthesize combined findings — dedup overlapping issues, merge unique findings, assign final severity.

## Pitfalls

### Opus refuses `--dangerously-skip-permissions` as root

Claude Code v2.x refuses `--dangerously-skip-permissions` when running as root/sudo. Error:
```
--dangerously-skip-permissions cannot be used with root/sudo privileges for security reasons
```
**Fix:** Omit the flag entirely in print mode (`-p`). Use `--allowedTools "Read,Bash"` to restrict capabilities. Print mode already skips interactive permission dialogs, so the flag is unnecessary.

### Opus needs `--add-dir` when the review prompt lives outside the repo

Claude Code's sandbox scopes file access to the working directory. A review prompt, spec, or diff staged in `/tmp/<proj>/` is invisible to a `claude -p` dispatch whose cwd is the repo: the lane exits after seconds with a ~100-byte log and a directory-access error, before doing any review work.
**Fix:** add `--add-dir /tmp/<proj>` to every Opus dispatch whose inputs live outside the repo. A near-empty Opus log right after launch is this failure, not a model refusal.

### A reviewer's failing-suite count is environment evidence, not regression evidence

A reviewer running the full suite inside its own sandbox may lack project deps (`google-auth`, `pymupdf`, `msal`-class packages) and report e.g. "2209 passed / 23 failed" with all failures being import errors. Read such a report as "trends tests green, environment incomplete" — never as a regression signal. The orchestrator's own full-suite run from the real environment is the only authority for "suite green"; when a reviewer's failure list names missing modules, confirm with your own run before treating it as a finding.

### Claude Code npm postinstall blocked

After `npm install -g @anthropic-ai/claude-code`, `claude --version` may fail with "claude native binary not installed" because npm blocks postinstall scripts by default.
**Fix:** `npm install -g --allow-scripts=@anthropic-ai/claude-code @anthropic-ai/claude-code`

### pytest-randomly breaks sequential test suites

Installing `pytest-randomly` to test for isolation issues will auto-activate random ordering. Test suites with sequential test methods (e.g. `test_01_create` → `test_03_list`) will fail because data created in earlier tests is expected by later ones. **Fix:** uninstall `pytest-randomly` after the isolation check. The random ordering test is a one-time diagnostic, not a permanent fixture.

### What each model catches that the other misses

In one test isolation review (2026-08-21):

- **Opus found** an entire unmigrated file (`test_phase_d_repetition.py` — 4 classes still using a shared `/tmp` dir) that Codex missed. Opus also empirically reproduced the concurrent-test failure by running two `pytest` processes simultaneously.
- **Codex found** env var leaks in `test_agent_runner.py` (pop instead of restore), missing `addCleanup` in `test_inventory.py` and `test_consolidation.py` engine classes that Opus marked as MINOR.

Both models were needed to achieve full coverage. Neither alone was sufficient.

## Synthesis format

After reading both reviews, produce a combined table:

```markdown
### Combined Review (Codex + Opus)

| # | Source | Severity | File | Issue | Fix |
|---|---|---|---|---|---|
| 1 | Opus M1 | MAJOR | test_phase_d_repetition.py | Entire file unmigrated | Apply mkdtemp+addClassCleanup |
| 2 | Codex M2 | MAJOR | test_inventory.py | TestInventoryEngine missing addCleanup | Convert tearDown→addCleanup |
| ... | ... | ... | ... | ... | ... |
```

Then dispatch Cursor to fix all MAJOR + MINOR issues in one batch, re-run tests, and commit.

## Depth-tier asymmetry is normal — verify the second reviewer's headline

Reviews from different models are not symmetric in depth. On one repo round,
Codex returned 8 findings (3 BLOCKING) while Opus returned 35 (5 BLOCKING)
including a structural artifact defect that BOTH the orchestrator's contract
tests and Codex missed — the contract test grepped concatenated output, which
masks per-item duplication (every generated file wrong, test still green).
Rules:

1. **Probe the second reviewer's most-severe claim directly before acting on
   either review** — if it reproduces, it re-frames the whole fix round; if
   not, it is dismissed with cause like any other finding.
2. **Contract tests must assert a single generated artifact's full content**
   (fill one row → read one file → assert whole text). Aggregate/concatenation
   greps cannot catch per-item shape defects.
3. **Budget the fix round from the UNION of findings, not the first review** —
   the merged fix brief supersedes the first (see `fix-brief-template.md`
   supersede rule and `persistent-loop-plan.md` steering rule #6).
4. **Delta re-reviews converge on different defect classes per reviewer —
   expect each delta round to demand its own fix round.** In the first delta,
   Codex caught the perimeter (manifest-clobber, slug-collision, path-escape
   classes) while Opus caught artifact-shape defects (schema-invalid XML from
   collapse, containment bypass via mid-string placeholders, invalid env
   placeholder names) — neither overlap was redundant with the other's list.
   A delta round that returns REQUEST CHANGES from both reviewers is normal,
   not a stalled loop: findings narrow in scope each round even when counts
   stay high. The convergence signal to watch is the CLASS of finding (new
   subsystems → fresh ground; same subsystem → fix regression), not the
   count. Commit between fix rounds so each delta review diffs against the
   last fixed state, and route each reviewer's OWN findings back into its
   own delta prompt (they spot-check their own findings more reliably than
   they check another reviewer's).
5. **Write a NEW review-prompt file per delta round, never reuse the round
   before it.** A r3 round pointed reviewers at the previous round's prompt by
   name in one lane and the same-turn file-write race hit both lanes in
   another; either mistake feeds reviewers a stale or missing prompt and they
   adjudicate the wrong diff. Per round: `review-prompt-r<N>.md`, written and
   verified (`wc -c`) BEFORE either dispatch (tool-mechanics #37), containing:
   the commit range, the prior round's finding IDs, the binding-adjudication
   list, and the "already verified — do not redo" list.
6. **A reviewer that cannot execute code still earns its keep — read its
   opening line for the admission.** The static lane may lose ALL code
   execution (sandbox denies probes) yet still return the round's most
   valuable finding (a status-vocabulary regression, a silent `except:
   return {}`). Treat its runtime claims as needing orchestrator probes and
   its FIXED/PARTIAL table as code-quote evidence; see
   review-findings-adjudication.md for the full static-only pattern.
7. **Split verdicts on one delta are probe-adjudicated per finding, not
   majority-voted.** The execution lane's REQUEST CHANGES with a probe-reproduced
   MAJOR beats the static lane's SHIP: fix the reproduced finding. Static-lane
   minors split three ways: fix-now (cheap, testable), document-only (a
   consequence of the orchestrator's own upstream adjudication, e.g. daily vs
   weekly AR semantics pinned by an attested test), or skip-listed nit. Record
   the routing per finding in the next brief. See review-findings-adjudication.md
   'Split verdicts' for the full rule.
8. **Both lanes agreeing on a wrong premise is possible — check your own probe's
   fixture first.** Two reviewers both claiming "migration clobbers the store"
   on the same delta were both reproducing an orchestrator fixture bug (DB at a
   path the module does not open). A probe contradicting the code's own passing
   tests is suspect before the code is; rebuild the fixture through the module's
   path resolver and schema, re-run, then adjudicate.

## Cross-model overlap case study (Aug 2026)

One SQLite WAL migration review produced 11 findings across Codex and Opus.
6 were flagged by both reviewers (high confidence). The overlap table:

| # | Severity | Issue | Codex | Opus |
|---|---|---|---|---|
| 1 | BLOCKING | KV lost updates — with_store_lock no-op | ✅ | ✅ |
| 2 | BLOCKING | Auto-migration skips legacy data | ✅ | ✅ |
| 3 | BLOCKING | workspace_audit.py lost hash-chain lock | ✅(MAJOR) | ✅ |
| 4 | MAJOR | Corrupt JSON silently returns None | ✅ | ✅ |
| 5 | MAJOR | _save() swallows BEGIN IMMEDIATE failure | ✅ | ✅(NIT) |
| 6 | MAJOR | Replay lease token never returned | ✅ | ✅(MINOR) |
| 7 | MAJOR | Production code never uses new CAS path | — | ✅ |
| 8 | MAJOR | transition_action("failed") bypasses MAX_RETRIES | — | ✅ |
| 9 | MINOR | _cas_update column names without allowlist | — | ✅ |
| 10 | MINOR | Cleanup omits dismissed/failed states | ✅ | — |
| 11 | NIT | Duplicate event key uniqueness | ✅ | — |

Key takeaway: both reviewers independently found the same 3 BLOCKING issues
but classified them differently (Codex called the audit lock MAJOR, Opus called
it BLOCKING). Both classifications are valid — the issue is the same. The
synthesis should use the higher severity when reviewers disagree.

See `references/sqlite-wal-review-findings.md` for the full finding details.
