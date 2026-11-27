# Workflow steps

Verbatim bodies for Workflow steps 1-11. SKILL.md keeps the ordered skeleton: one opening line per step, plus a pointer. Step 2b — integration boundaries and Hermes-written contract tests — is a subsection of this file.

## Contents

- Step 1 — Prepare the brief (if building from scratch)
- Step 2 — Initialize git (Codex needs a repo)
- Step 2b — Identify integration boundaries (Hermes, before build)
- Step 3 — Build loop (Cursor)
- Step 4 — Verify independently (Hermes)
- Step 4b — Spec-compliance pre-check (Hermes, before Codex)
- Step 5 — Commit the build (before review)
- Step 6 — Review (Codex)
- Step 7 — Synthesize review (Hermes)
- Step 8 — Fix loop (if issues found + loops remaining)
- Step 9 — Loop or deliver
- Step 10 — Review gate before push
- Step 11 — Push and monitor CI

### Step 1 — Prepare the brief (if building from scratch)

Write a self-contained brief at `<project-dir>/BRIEF.md`:
- Context (what the project is, why)
- Reference to spec file (SPEC.md)
- Reference code paths (proven code to adapt)
- Acceptance criteria / verification checks
- The builder block from `orchestrator/references/coding-principles.md` § Builder block, pasted verbatim (the builder reads only this brief)
- Constraints (what NOT to change), plus: "Do NOT `git commit` — the orchestrator commits after review." (See `review-lessons/references/loop-pitfalls.md` — "The reviewer commits — the implementer never commits".)

See `design-specs` skill for spec format. The brief is the spec's implementation-focused companion.

### Step 2 — Initialize git (Codex needs a repo)

```bash
cd <project-dir>
git init
git add -A
git commit -m "initial: pre-build scaffold"
```

Codex requires a git repo. Always init before dispatching the review.

### Step 2b — Identify integration boundaries (Hermes, before build)

Before dispatching the builder, identify every **integration boundary** that will
change shape — any function return type, API payload, event format, or data
structure that crosses a module seam. These are the points where a stale mock in
tests can silently mask a real bug.

For each boundary changed, write down:
1. **The old shape** (if it exists) — what callers currently expect
2. **The new shape** — what the builder will produce
3. **The test that covers it** — which test exercises this boundary
4. **Does the test use the real shape or a hand-rolled mock?** — if a mock,
   it must be updated to match the new shape

Add a section to the brief:

```markdown
## Integration boundaries changed

| Boundary | Old shape | New shape | Test | Mock updated? |
|---|---|---|---|---|
| _exec_run_backtest return | {metrics: {sharpe, cagr}} | {comparison: [{label, metrics}]} | test_agent.py::test_... | YES |
| data.load_panel | (new) | data.load_panel(cfg, override) | test_data.py | N/A (new) |
```

**For safety-critical paths** (evidence gates, trading logic, anything touching
money or agent answers): **Hermes writes the contract test first** — before
dispatching the builder. This is not full TDD — it's one test at the integration
boundary that encodes the expected behavior. The key: **Hermes writes the test,
Cursor writes the code.** Cross-model diversity at the test level is what makes
the test honest. Cursor has been caught writing `assert condition or True`
(always passes), deleting inconvenient test files, and mocking
wrong payload shapes. A Cursor-written test-first is no more trustworthy than a
Cursor-written test-after.

Workflow:
1. **Hermes** writes the contract test in the test file, encoding the expected
   behavior from the brief. The test should FAIL against the current code (red).
2. **Hermes** runs the test and confirms it fails for the right reason (not a
   syntax error or import failure — the assertion itself must fail).
3. **Hermes** commits the test.
4. **Cursor** builds the implementation. The brief tells Cursor: "a test at
   `tests/test_X.py::test_Y` already encodes the expected behavior — your
   implementation must make it pass. Do NOT modify or delete this test."
5. **Hermes** verifies after build: the test passes, AND the test file is
   unchanged (`git diff` shows no modifications to the test Hermes wrote).

```python
# Written by Hermes, not Cursor:
def test_run_backtest_comparison_evidence_recorded():
    """run_backtest returns {comparison: [{label, metrics}]} — evidence ledger
    must contain the nested metrics, not silently drop them."""
    # This test should FAIL before the fix is built, then PASS after.
```

**Why this matters:** One B1-class bug (2026-08-03) went undetected through
5 commits and 2 review rounds because the test mocking `run_backtest` used a
stale payload shape (`{"metrics": {...}}`) instead of the real shape
(`{"comparison": [{"label": ..., "metrics": {...}}]}`). The test passed, the
real code was broken, and the agent silently replaced backtest answers with
fallback. A Hermes-written contract test at the boundary would have caught this
immediately — and Cursor couldn't have weakened it.

**For refactors** (moving code, deepening modules, deleting parallel
implementations): existing tests verify behavior preservation. The brief defines
the shape. Contract tests are optional — the existing test suite is the safety
net. But if a function's return shape changes, its callers' tests must be
updated to use the real shape, not a stale mock.

**For bug fixes:** Hermes writes a regression test first that reproduces the bug
(red), then Cursor fixes the implementation to make it pass. Same cross-model
principle: Hermes encodes "this is the correct behavior," Cursor makes it work.

| Change type | Who writes tests | When |
|---|---|---|
| New feature / safety-critical path | **Hermes** — contract test first | Before Cursor builds |
| Bug fix | **Hermes** — regression test first | Before Cursor fixes |
| Refactor (behavior preservation) | Existing tests | Already in place |

### Step 3 — Build loop (Cursor)

Dispatch Cursor with the builder model:

```bash
agent -p --force --model "$BUILDER_MODEL" --sandbox disabled \
  "Read the brief at BRIEF.md and spec at SPEC.md. Implement fully. Run verification checks and report." \
  2>&1 | tail -5
```

Run with `background=true, notify_on_complete=true`. Working directory = project dir.

After the process exits, capture the dispatch result (delegate-result.v1 — see `references/dispatch-result-contract.md`): `python3 <skill-dir>/scripts/capture_dispatch_result.py --repo <project-dir> --task "build R1" --implementer cursor --model <model-that-ran> --exit-code <N> --report <report-file> --out /tmp/<proj>-dispatch-r1.json`. Verification and review start from this file's `touchedFiles`, not from memory.
- `$BUILDER_MODEL` — the builder lane in `orchestrator/references/lanes.md` (full effort, normal speed — NOT fast)
- User may specify a different model — respect their choice

### Step 4 — Verify independently (Hermes)

**Do NOT trust the builder's self-report.** Run verification checks yourself:

1. Check files exist: `search_files` or `ls`
2. Run import checks: `python3 -c "from src.X import Y; print('OK')"`
3. Run schema tests: `python3 -c "from src.db import init_db; ..."`
4. Run any spec-defined verification commands
5. Check line counts, grep for expected patterns
6. **Check mock payload shapes match real outputs** — for each integration boundary
   listed in Step 2b, verify that the test uses the **actual payload shape** from the
   real function, not a hand-rolled approximation. Grep for the test's mock data and
   compare it to the real function's return. This is the check that would have caught
   the earlier B1-class bug (stale mock → silent evidence-gate failure).

If verification fails, the failing check is ground truth and **vetoes the build's "done" claim** — do not soften it into a review note. A failing test overrides any DONE/APPROVED signal, exactly as a public-test failure overrides the manager's verdict in the upstream ledger-orchestration pattern. Immediately:

1. Write the failure (command, expected vs actual, first failing case) into the review file as a BLOCKING Hermes-verified issue.
2. If the loop continues, the fix brief must lead with this failing check as its acceptance criterion — the fix round is not complete until that exact command passes.
3. On re-review, re-run the vetoing check first; a round that fixes other findings but leaves the vetoing check red is not a passing round.

### Step 4b — Spec-compliance pre-check (Hermes, before Codex)

Before dispatching Codex, add a spec-compliance pass to Hermes verification. This catches issues Hermes traditionally misses — tests pass but the behavior doesn't match the spec.

1. **Re-read the spec's component specs** — cross-check each config field, API contract, and constraint against the implementation
2. **Check whitelists and permission boundaries** — are there keys/endpoints that should be read-only but are writable? Are there fields the spec says to exclude that are present?
3. **Verify graceful-degradation paths** — does the code skip when a dependency is missing, or does it crash? Tests often only test the happy path
4. **Check for spec-mentioned features that are missing entirely** — did the builder skip a task from the brief?
5. **Cross-project checklist** — run the 7-item reviewer checklist: time helpers, config sprawl, god files, O(N) lookups, FTS5 usage, OAuth scope enforcement, degradation paths

The pattern: Hermes verifies *does it run + do tests pass + does it match the spec*, Codex verifies *is it correct + are there edge cases*. Both layers are needed; neither is sufficient alone.

### Step 5 — Commit the build (before review)

```bash
cd <project-dir>
git add -A
git commit -m "build: initial implementation (builder lane)"
```

Commit only what the dispatch result's `touchedFiles` captured (see `dispatch-result-contract.md`): any file present at commit time but absent from the capture is a scope deviation — adjudicate it, don't absorb it. This gives Codex a clean base to review against, and lets us diff fixes in later loops.

### Step 6 — Review (R1, reviewer lanes for the tier)

Before the first dispatch, open the loop's budget ledger and R1:

```bash
python3 <plugin>/skills/review-commit/scripts/review_budget.py init .hermes/reviews/<loop> --tier T2
python3 <plugin>/skills/review-commit/scripts/review_budget.py round .hermes/reviews/<loop> --scope round-1.diff
```

Then write the R1 brief from `briefs/references/review-briefs.md` § R1 and stamp
it (`briefs/scripts/stamp_brief.py ... --budget .hermes/reviews/<loop>`), which
exports the diff and fills SHAs, counts and the round line. The example prompt
below shows the content; the stamped template is the one to send. Keep the
brief inside the repo cwd (gitignored) so every reviewer can read it — see
`reviewer-dispatch.md`:

```markdown
# Review Task: <project name>

Review ONLY the diff at ./review-diff-<proj>.diff, plus the current files it
touches. Do not review files the diff does not touch. Focus on:
- Data-integrity bugs (wrong types, silent data loss, mixed contracts)
- Edge cases the builder likely missed (empty inputs, concurrent access, error paths)
- Spec compliance (read SPEC.md — does the code match the spec?)
- Security (auth bypass, injection, data leakage between tenants)
- Missing error handling, missing validation

Read SPEC.md first, then the diff.

Output a structured review (labels defined in confirm-round-protocol.md):
- BLOCKING: wrong result, data loss, security hole, crash on a real path
- MAJOR: real bug on a reachable path, or a spec requirement missing
- MINOR: real but low-impact or edge-only — does not block ship
- NIT: style/cleanup — does not block ship

Reachability: for any BLOCKING/MAJOR/MINOR, name the production entry point
(route, CLI command, tool, job) that reaches it. A scenario no entry point can
reach is a NIT. Input from users, files, network or config always counts as
reachable.

For each issue: file, line (approx), description, suggested fix.

Do NOT make file changes — review only.
```

**Delta-round prompt shape:** every re-review is a confirm round — its input is the FIX diff, and its three questions (per-finding RESOLVED/NOT-RESOLVED, fix-induced NEW-N scoped to the fix lines, verdict) are defined in `confirm-round-protocol.md` § Scope. Include "Do not re-report fixed items or accepted limitations"; anything outside the fix lines is OUT-OF-SCOPE-N and goes to the deferred list.

**Fix-brief acceptance gates:** every fix brief carries (a) the acceptance-criterion probes for the fix itself, and (b) at least one standing regression check that must NOT change — e.g. a byte-identical render probe against the PRE-FEATURE baseline (`git show <pre-feature-commit>:<file>`), a spec-named empty-state behavior, a live-install divergence probe. A fix round that satisfies all item probes while breaking a standing property is a failed round: a trend-CSS-gate fix was verified byte-identical against the PREVIOUS round's renderer (which already contained the CSS) instead of the commit BEFORE the feature series began — the wrong baseline reported a false diff and cost a re-derivation before the true baseline was found. Always diff byte-identity against the pre-feature commit, never the previous fix round.

**Post-fix confirmation pass (before ship):** this IS a confirm round — open it with `review_budget.py round` first; it counts against the budget like any other. After a fix round, dispatch the ORIGINAL reviewer scoped to the fix diff plus the files it touches: "verify each of your N findings is resolved — not superficially patched — RESOLVED/NOT-RESOLVED per finding, then a final SHIP/DO-NOT-SHIP verdict." A fix round can self-verify green (all tests passing, smoke checks clean) while leaving real residuals: the confirmation pass exists because the builder's fix verification and the reviewer's adversarial probe are different activities. Reproduce every NOT-RESOLVED claim yourself before dispatching the next fix round (see `review-lessons/references/loop-pitfalls.md` — "Reproduce every reviewer finding before it enters a fix brief") — reproduction separates real residuals from reviewer error and hands the builder exact probe scripts.

Dispatch reviewer A (other lanes: `reviewer-dispatch.md`):

```bash
codex exec --sandbox read-only -m "$REVIEWER_A_MODEL" -c model_reasoning_effort="high" \
  "Read ./review-prompt.md and review the diff it names. Output your review as text." \
  2>&1 | tail -800
```

Run with `background=true, pty=true, notify_on_complete=true`.

**Codex sandbox note:** `~/.hermes/` paths need `--sandbox danger-full-access`. For paths outside `~/.hermes/`, `--sandbox read-only` works for review-only, but can't run tests. Use `--sandbox workspace-write` if tests need to run.

**Codex output:** May be truncated with `tail -800`. Collect full output via `process(action="log", session_id=<id>, limit=800)`. If Codex just echoes file content without analysis, retry with a more explicit prompt.

### Step 7 — Synthesize review (Hermes)

Combine:
- Hermes verification results (Step 4)
- Codex review findings (Step 6)

Produce a structured review:

```markdown
## Review Round N — <project>

### Verdict: APPROVE / APPROVE WITH FIX / REQUEST CHANGES

### Hermes Verification
| Check | Result |
|---|---|
| Import check | ✅/❌ |
| Schema init | ✅/❌ |
| Chunker test | ✅/❌ |
| ... | ... |

### Codex Findings
| # | Severity | File | Issue | Suggested Fix |
|---|---|---|---|---|
| 1 | BLOCKING | ... | ... | ... |

### Combined Issues (deduplicated, Hermes-verified)
...

### Acceptance Criteria
- [ ] Criterion 1
- [ ] Criterion 2
```

### Step 8 — Fix loop (if issues found + loops remaining)

Write a fix brief for Cursor (template in `briefs/references/fix-brief-template.md`, stamped with `briefs/scripts/stamp_brief.py`; the brief carries the
reproduced, deduplicated findings and named failing tests — the builder never reads the raw
review log):

```bash
agent -p --force --model "$BUILDER_MODEL" --sandbox disabled \
  "Read the fix brief at .hermes/reviews/fix-brief-N.md. Fix every BLOCKING and MAJOR issue. Read the spec at SPEC.md for context. Do NOT change anything not mentioned in the brief. Run verification checks after fixing." \
  2>&1 | tail -5
```

Run with `background=true, notify_on_complete=true`.

After Cursor finishes:
1. Re-run Hermes verification (Step 4)
2. Commit only the touched files: `git commit -m "fix: round N issues"`
3. Dispatch the confirm round on the FIX diff (`confirm-round-protocol.md` § Scope), only to reviewers with open findings
4. Synthesize re-review (Step 7)

### Step 9 — Loop or deliver

Check the stop conditions in `confirm-round-protocol.md` after every round:

- **No open BLOCKING/MAJOR** → deliver final verdict (APPROVE, or APPROVE WITH FIX listing the deferred MINOR/NIT items)
- **BLOCKING/MAJOR open + budget left + no stop condition hit** → go to Step 8
- **Stop handling follows the protocol exactly** (`confirm-round-protocol.md`, *Stop conditions*): Ship → SHIP. Budget spent with BLOCKING/MAJOR open → give the user the open set with redesign / one-more-round / explicit risk acceptance; open BLOCKING/MAJOR or failing acceptance tests are NOT SHIP. Second same-class stop → ONE redesign brief in-process, third same-class → user. No-progress stop → stop, re-read the code, decide with the user. Fix-quality stop → tighten the fix brief and continue; it is not a user escalation by itself.

### Step 10 — Review gate before push

**NEVER push without a review pass from reviewer lane A** (the gate's minimum; "Codex review" historically = reviewer lane A). **Exception:** T0 changes with no behavior change may push directly at the user's instruction (review-commit SKILL Step C). The user requires: build → commit → review → fix → push. A prior session pushed code without a separate review pass and the user corrected it explicitly: "Codex review first before push please." (Model pins live in `orchestrator/references/lanes.md`.)

A green live smoke or e2e run does NOT satisfy this gate: it proves the feature works under production conditions, not that the code is review-clean. Run the review before merge or push even when the smoke evidence is fresh and complete — a verified runtime run is not review approval, and closing the loop without it costs a full user-visible correction round.

The gate applies to every batch, not just the final one. In multi-batch work:
1. Commit each batch locally (Step 5)
2. After all batches complete, dispatch the review covering the full diff (`git diff <base>..HEAD`) — reviewer count per `orchestrator/references/size-tiers.md` (T0/T1: one lane; T2: two cross-model; T3/live deploy: all three, the three-reviewer gate)
3. Fix findings (trivial fixes — ≤ ~10 lines, mechanical, no design choice — may be applied by the orchestrator directly, saying so; everything else goes through the builder lane)
4. Push only after the review returns SHIP/APPROVE with no open BLOCKING/MAJOR

Alternatively, review each batch separately if the diff is large. The key: no push until a reviewer lane has reviewed and no BLOCKING/MAJOR finding is open (deferred MINOR/NIT are fine).

### Step 11 — Push and monitor CI

After Codex approves and fixes are committed:

```bash
git push origin <branch>
```

Before pushing, embed **evidence pairs** (see `review-lessons/references/evidence-pairs.md`): capture the before state while reproducing the issue, the after with the same method, and put the pair in the PR body or delivery message. No visual surface → measured numbers or output pairs.

Monitor CI:
```bash
gh run list --limit 1 --json status,conclusion
```

Wait for `conclusion: "success"` before telling the user the work is shipped. If CI fails, investigate before reporting success.
