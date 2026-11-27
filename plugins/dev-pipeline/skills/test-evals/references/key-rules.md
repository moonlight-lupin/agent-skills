# Key Rules

Read before the first batch of every run. These rules gate RED/GREEN order, the Opus pin, review-before-commit, staging, and CI.

## Contents

- Key Rules

## Key Rules

- **RED before GREEN, no exceptions — even when both are already written.**
  The most common TDD violation in Hermes-led builds is writing the
  implementation first, then tests, and rationalizing "I already wrote both,
  let me just run the tests." This skips the RED step (watch the test fail
  for the right reason) — the step that catches spec misunderstandings
  before they're encoded in both code and test. Tests shaped by existing
  implementation confirm what you built, not what you *should* have built.
  When the user asks "are you doing the loops?" they have already noticed
  the skip. Don't defend the shortcut — acknowledge it, run tests as a
  *diagnostic* (not a RED substitute), and treat any failures as evidence
  the implementation is wrong, not evidence the tests are correct. For
  future builds: write the failing test FIRST, run it, watch it fail, THEN
  implement. The Hermes TDD process for smaller tasks is: all RED tests
  first → run and confirm they fail for the right reason → implement until
  all pass. Not "implement then test."
- **"Opus" = the current Opus generation** — the batch "Opus" lane in
  the lanes config (`orchestrator/config/lanes.default.toml` + override) — the generation the reviewer's pin names, not a remembered tier label.
  This is non-negotiable.
- **Review BEFORE commit, not after** — the review catches issues while you
  can still fix them without a separate fix commit.
- **Partition by shared-code dependency** — features that change shared types
  go in the first batch so downstream features can consume them.
- **Use `git add <specific files>`**, not `git add -A` — Cursor may create
  untracked junk (e.g. `docs/walkthrough/` screenshots) that you don't want
  in the commit.
- **After pushing, ALWAYS check CI**. The user expects CI-green verification
  as part of the push, not as a separate request. Fix lint failures and re-push.
- **Verify independently** — run tests yourself. "All checks passed" from
  Cursor is a claim, not a fact.
- **Pre-existing failures** — `git stash` + run test + `git stash pop` to
  confirm a failure exists on clean main (not caused by your changes).
- Use `execute_code` (not `terminal`) for running pytest when the project
  path or binary name triggers the gateway's false-positive lifecycle guard
  (e.g. paths containing "trader"). The `execute_code` tool uses a subprocess
  that bypasses the guard.
- Ruff F821 (undefined name in string annotation) is common with
  `from __future__ import annotations` — fix with `TYPE_CHECKING` import.
- **BLE001 (blind except) is often intentional for graceful degradation** —
  when a feature MUST fall back silently (HyDE, cache, CRAG timeout), a broad
  `except Exception` is the correct pattern. Don't "fix" it by narrowing the
  catch — narrowing risks leaking an unexpected exception type that breaks the
  degradation contract. The existing CRAG, decompose, and grounding modules all
  use this pattern. Leave the BLE001 and add a comment if needed.
- **Restore files deleted by other processes before generating the diff** —
  if `git status` shows a file deleted that you didn't touch (e.g. `BRIEF.md`
  deleted by a prior process), `git checkout main -- <file>` to restore it
  BEFORE generating the review diff. A stale deletion pollutes the diff and
  confuses the reviewer.
