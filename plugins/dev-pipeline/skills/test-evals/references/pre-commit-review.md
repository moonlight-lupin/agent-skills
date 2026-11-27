# Pre-Commit Code Review

Moved verbatim from the `development-workflow` skill (2026-10-19 consolidation) into
the dev-pipeline **test-evals** stage. The review-commit stage (stage 5) owns the
convergence/confirm-round loop over review findings; this file stays the
pre-commit verification pipeline: five-axis review, severity labels, change
sizing, audits, and external-review verification.

## Contents

- 3. Pre-Commit Code Review (Five-Axis Review, Severity Labels, Change Sizing, Structural Remedies, Steps)
- Read-Only Codebase Audits
- Self-review + Codex review workflow
- Subagent-dispatched review for large codebases
- External Review Findings — Verify Before Fixing

## 3. Pre-Commit Code Review

Automated verification pipeline before code lands. **No agent should verify its own work.**

### Five-Axis Review

Every review evaluates code across five dimensions:

1. **Correctness** — Does it do what it claims? Edge cases handled? Error paths? Tests cover the change?
2. **Readability & Simplicity** — Can another engineer understand it without explanation? No unnecessary cleverness? Abstractions earning their complexity?
3. **Architecture** — Follows existing patterns? Clean module boundaries? No circular deps? Abstraction level appropriate? Does the refactor reduce complexity or just relocate it?
4. **Security** — Input validated? Secrets kept out? Auth checks? Parameterized queries? External data treated as untrusted?
5. **Performance** — N+1 queries? Unbounded operations? Missing pagination? Sync where async needed? Large objects in hot paths?

### Severity Labels

Label every finding so the author knows what's required vs optional:

| Prefix | Meaning | Author Action |
|---|---|---|
| **Critical:** | Blocks merge | Security vulnerability, data loss, broken functionality |
| *(no prefix)* | Required change | Must address before merge |
| **Optional:** / **Consider:** | Suggestion | Worth considering but not required |
| **Nit:** | Minor, optional | Author may ignore — formatting, style preferences |
| **FYI** | Informational only | No action needed — context for future reference |

**Lead with what matters.** Order findings by leverage: correctness and security first, then structural regressions, then everything else. Don't bury a real issue under cosmetic nits.

### Change Sizing

```
~100 lines changed → Good. Reviewable in one sitting.
~300 lines changed → Acceptable if it's a single logical change.
~1000 lines changed → Too large. Split it.
```

**Separate refactoring from feature work.** A change that refactors AND adds new behavior is two changes — submit separately. Small cleanups (variable renaming) can ride along at reviewer discretion.

### Structural Remedies

When you flag a structural problem, propose the move — not just the problem:

- Replace a chain of conditionals with a typed model or dispatcher
- Collapse duplicate branches into a single clearer flow
- Separate orchestration from business logic
- Move feature-specific logic out of a shared module into its owning layer
- Reuse the canonical helper instead of a near-duplicate
- Make a type boundary explicit so downstream branching disappears
- Delete a pass-through wrapper that adds indirection without clarifying the API

Prefer the remedy that removes moving pieces over one that spreads the same complexity around.

### Steps
1. **Get diff** — `git diff --cached` (or `git diff HEAD`)
2. **Static security scan** — Check for hardcoded secrets, shell injection, eval/exec, pickle.loads, SQL injection
3. **Baseline tests + linting** — Capture failure count BEFORE changes. Only NEW failures block.
4. **Self-review checklist** — No secrets, input validation, parameterized queries, error handling, no debug prints
5. **Independent reviewer** — Use Claude Code or `delegate_task` for fresh-context review. Fail-closed.
6. **Evaluate** — All passed → commit. Any failures → auto-fix loop.
7. **Auto-fix loop** (within the tier's round budget — `review-commit/references/confirm-round-protocol.md`; only BLOCKING/MAJOR findings trigger another cycle) — Third agent context fixes reported issues. Re-verify.

See `requesting-code-review.md` (same directory) for full pipeline details.
See the `development-workflow` skill (outside skill, not bundled here; its accounting-ERP review-checklist reference) for a taxonomy of bugs found in a double-entry accounting/ERP codebase review (non-atomic postings, idempotency gaps, ignored dates, missing validation, test isolation, closed-period bypass, FX reversal metadata loss, API security attack surface, FX cumulative revaluation double-posting, idempotent intercompany elimination, recurring catch-up loops, skip+advance on closed periods, hardcoded account constants, pagination, FIFO cost rounding, CPF Board rounding, AW-ceiling tracking via stored ow_subject, remediation planning approach). Covers all 7 remediation phases (A–G) plus Phase G+ quality items with patterns, fixes, and test patterns.

### Read-Only Codebase Audits

When the user asks for a review without modifications (e.g. "find bugs/design issues/missing tests; do not edit files"):

1. **Stay read-only.** Use `read_file`, `search_files`, and test commands only; do not patch source or tests.
2. **Scope first.** Identify target modules, migrations, and tests; exclude explicitly out-of-scope areas even if adjacent code is tempting.
3. **Read implementation + schema + tests.** For each reviewed module, inspect engine/model code, relevant migrations, and test coverage. Missing validation often appears as a mismatch between models, DB constraints, and engine methods.
4. **Verify baseline.** Run the test suite or the relevant subset and report the real output; passing tests do not invalidate review findings, but they establish current coverage.
5. **Evidence standard.** Every finding needs `severity`, `file:line`, concrete behavior, and suggested fix. Prefer fewer high-confidence issues over broad speculation.
6. **Accounting/ERP review lens.** Prioritize money/correctness bugs: non-atomic multi-step postings, ignored dates, duplicate postings/idempotency gaps, bypassed closed periods, negative amounts, account type misuse, cross-company leakage, and subledger/GL divergence.
7. **Missing tests.** Tie missing-test notes to a specific bug/design gap (e.g. "no regression for duplicate revaluation") rather than listing generic coverage desires.

Pitfall: lifecycle methods that call helpers which each `commit()` are not transactionally atomic even if the top-level method looks like one business operation. In financial systems, flag partial-posting states as HIGH severity when failures can leave GL/subledger/voucher statuses inconsistent. When fixing this by adding `commit=False` parameters, watch for **hidden commits inside helper functions** — e.g. `_audit()` in this codebase calls `conn.commit()` unconditionally, defeating `commit=False` on the caller. The fix must thread `commit` through every function that commits internally, including audit/logging helpers. The `development-workflow` skill (outside skill, not bundled here) documents this as "Phase C: Atomicity — the _audit() commit trap".

Pitfall: **test isolation with `shutil.rmtree`** — integration tests that rmtree a shared data directory in `setUpClass` will randomly destroy other tests' databases under non-deterministic pytest ordering. If test A rmtrees `data/` and test B creates per-method DBs in `data/` without rmtreeing, random order can run A after B's setUp, wiping B's databases mid-suite. Symptoms: tests pass in isolation and with `-p no:randomly` but fail with setup errors in the full suite. Fix: each test class that rmtrees gets its own `data_<name>_test/` directory; tests that don't rmtree can share `data/` safely.

Pitfall: **hardcoded account constants are silent wrong-account bugs** — module engines that use string constants for GL account codes (e.g. `FX_GAIN_ACCOUNT = "4500"`, `AP_ACCOUNT = "2100"`) post successfully but to the wrong account when the constant doesn't match the chart of accounts. These are worse than crashes because the JE looks correct but financial statements are wrong. When correcting constants, search ALL tests for the old code and update every assertion — `self.assertIn("2100", ...)` and `l.account_code == "2100"` will break. Also check chart-of-accounts templates for missing accounts (e.g. US chart lacking 6100 FX Loss).

Pitfall: **external review catches what you miss — take it seriously** — when a second reviewer (another agent, a human, Codex CLI) reviews your fixes, they will find issues you missed. Common patterns: incomplete threading of a new parameter, rate data copied without verification, test files silently deleted by `git add -A`, API endpoint format that works from one network but isn't the documented format. Don't dismiss external findings as "already handled" — verify each one independently.

### Self-review + Codex review workflow

For repos with their own lint gate + test suite, the two-pass pattern works well:

1. **Self-review (you):** Read all files, run tests + lint, assess architecture, evidence each finding with `severity + file:line`.
2. **Fix all findings.** Commit.
3. **Codex review:** Send the commit to Codex CLI (`codex exec --sandbox workspace-write`) with an explicit "Do NOT make changes" prompt so it can run pytest (read-only sandbox blocks pytest) while still preventing source edits.
4. **Fix Codex findings.** Amend the commit.
5. **Re-verify:** tests + lint green.

Key Codex review tips:
- Use `--sandbox workspace-write` (not `read-only`) when tests need to run — read-only blocks pytest temp dirs.
- The prompt must say "Do NOT make any changes" — Codex respects this in workspace-write mode.
- Codex finds things you miss: contradictory help text, misleading docstring examples, overly narrow trigger phrases. Verify each finding before fixing.
- Background mode (`background=true, notify_on_complete=true, pty=true`) lets you do other work while Codex reviews.

Pitfall: **`when_to_use` frontmatter field budget** — when adding a `when_to_use` field to skills that have a `description` + `when_to_use` combined lint limit (e.g. 1024 chars), adding `when_to_use` to a long `description` requires **trimming trigger phrases out of `description`** to stay under budget. The `when_to_use` carries the trigger phrases; `description` carries the behavioral summary. Overly narrow `when_to_use` (only 1 trigger phrase) is a routing regression — include 5+ distinctive phrases. Verify with the project's lint tool after patching.

Pitfall: **external review catches what you miss — take it seriously** — when a second reviewer (another agent, a human, Codex CLI) reviews your fixes, they will find issues you missed. Common patterns: incomplete threading of a new parameter, rate data copied without verification, test files silently deleted by `git add -A`, API endpoint format that works from one network but isn't the documented format. Don't dismiss external findings as "already handled" — verify each one independently.

Pitfall: **pin each regression test to the behavior under test, or it cannot fail.** Give the fixture real values in EVERY dimension except the one under test, and assert the failure output names that dimension. A fixture that trips an unrelated gate (`cue: x` in a placeholder-parsing test) or an assertion on a path that can never trigger (a non-SKILL.md path against an observer that returns None regardless) passes with or without the fix — read the test against the hypothetical reverted fix and ask what would change; if the answer is nothing, the test proves nothing and the reviewer will flag it.

Pitfall: **full-suite runtime budget** — a large test suite (310+ tests) takes ~3.5 minutes. The default 120s terminal timeout is too short. Use `timeout 300 python -m pytest -q --timeout=60 -p no:randomly` for full runs. For targeted debugging, run individual test files with `--timeout=30`.

Pitfall: **FastAPI security regression fixtures must isolate mutable auth state** — when restoring or adding API tests for entity registry/API-key security, use `TestClient` with a temp `LEDGER_DATA_DIR`, create registered entities and keys in `setUpClass`, and keep last-key-guard assertions on a separate entity that has exactly one active key. Key-creation tests on the main entity otherwise invalidate the guard precondition. For "default bind is localhost," check both `serve()`/`uvicorn.run` defaults and CLI parser defaults if they are separate. The `development-workflow` skill (outside skill, not bundled here) carries an api-security-regression-tests.md reference with a compact recipe.

Pitfall: **branch hygiene when multiple agents commit to the same repo** — when another agent (Claude Code, Codex, a subagent, a human) is working on the same repository in parallel, your commits built on the previous HEAD may not include their fixes. Before pushing, `git fetch --all` and check `git log --oneline master..origin/<other-branch>` for commits you're missing. If the other branch is a clean superset (ahead, not behind), `git merge --ff-only origin/<other-branch>` to fast-forward. If the other branch diverged, cherry-pick their specific commits. The user will tell you which commits to cherry-pick (e.g. "cherry-pick b45ca28, ddc6bae, and 971c0b0") — don't guess. After merging, run the full test suite to verify integration, then push. Delete merged remote branches with `git push origin --delete <branch>` only after confirming the merge landed on master.

Pitfall: **date-effective computations should store results, not recompute** — when a calculation depends on date-effective parameters (rate tables, tax brackets, CPF ceilings), storing the computed result at write time is more correct than recomputing at read time. Recomputation uses the *current* parameters, not the *as-of* parameters that were in effect when the record was created. This is especially critical for annual cumulative calculations (AW ceiling, YTD tax brackets) where mid-year rate changes would corrupt the running total. Add a column (e.g. `ow_subject`) to store the computed value, and have subsequent calculations read the stored value instead of recomputing from raw fields. The `development-workflow` skill (outside skill, not bundled here) documents this as "AW-ceiling tracking — store `ow_subject` on pay slips".

### Subagent-dispatched review for large codebases

When a codebase has 10+ modules and a read-only audit is needed, dispatch a `delegate_task` subagent to do the review rather than reading every file in the parent context. The subagent reads all module engines, models, migrations, and tests, then returns a categorized findings list (HIGH/MEDIUM/LOW with `file:line`, description, suggested fix). The parent then batch-applies fixes.

**Why this works:** The subagent has a fresh context window dedicated to review — it can read 20+ files without polluting the parent's context with intermediate tool output. The parent receives a compact findings report and can immediately start patching.

**Pattern:**
```python
delegate_task(
    goal="Review [codebase] for bugs, design issues, and missing tests. Focus on [modules]. Return severity, file:line, description, and suggested fix for each issue. Read-only — do NOT modify files.",
    context="Key conventions: [money handling, validation rules, lifecycle]. Known constraints: [any intentional design decisions]. Check for: [money bugs, missing commits, audit gaps, idempotency, validation, race conditions]."
)
```

**While the subagent reviews,** the parent can handle infrastructure fixes (test isolation, documentation gaps, STATUS files) in parallel — these don't depend on the review findings.

## External Review Findings — Verify Before Fixing

When an external reviewer (Codex CLI, Claude Code, a subagent) reports bugs,
**verify each finding independently before fixing it.** Don't trust the report
blindly — construct a minimal reproduction that proves the bug exists in the
current code, THEN fix it.

**Why:** External reviewers sometimes report bugs that:
- Were already fixed upstream (stale review against an old commit)
- Are deliberate design decisions, not bugs (read the commit message)
- Are described correctly but don't reproduce at runtime

**Pattern:**
1. Read the finding (file, line, claimed behavior)
2. Construct a minimal reproduction (synthetic input, monkeypatch, unit test)
3. Run it against current code — does the bug actually manifest?
4. If yes: apply fix, write regression test
5. If no: check `git log` for recent fixes to that file — may be already resolved
6. If deliberate decision: note and move on, don't "fix" a design choice

**Cost-delta testing technique** (for financial/cost-model bugs):
To isolate transaction cost from gross return, run the same input at `cost=0`
and `cost=X`, then take the difference — gross return cancels out, leaving pure
cost. Avoids fragile fixtures where price movement dominates the cost signal.

```python
res_0 = backtest(panel, cost_bps=0.0)
res_x = backtest(panel, cost_bps=100.0)
cost_delta = res_0.returns[i] - res_x.returns[i]  # pure cost, gross cancelled
```
