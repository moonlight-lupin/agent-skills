---
name: review-commit
description: "Use when the user says 'review loop N times', 'build then review', 'fix and re-review', 'review loop until clean', 'have cursor build, codex review', or wants the dev-pipeline review stage: a two-axis single pass (Standards + Spec, parallel, never merged) FIRST, then a budgeted confirm-round loop on the fix diffs until no BLOCKING/MAJOR is open, then the commit/deploy gate — three-reviewer gate before live deploy, release hygiene before tagging. Also triggers: 'two-axis review', 'confirm rounds', 'review diff until SHIP', 'N confirm rounds', ship gate."
metadata:
  version: 2.1.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [review, code-review, confirm-round, convergence, two-axis, fowler-smells, ship-gate, three-reviewer-gate, commit, push-gate, release-hygiene, cross-model, spec-review]
    related_skills: [orchestrator, build, test-evals, spec, review-lessons, council-code-review, cli-auth-fallback]
---

# Review-Commit

Stage 5 of the dev-pipeline: everything after the build, through commit and
deploy. This file and its `references/` hold the PROCESS. Lessons from past
loops (SQLite, MCP, REST, sync, mobile, test-quality traps, CLI quirks) live
in the separate `review-lessons` skill — load a lesson file only when its
case comes up, never at stage start.

## Before you start: tier, lanes, budget

1. **Tier** — risk-derived review tier from `orchestrator/references/risk-routing.md` (compatibility table: `size-tiers.md`). It sets how many
   reviewers run and how many confirm rounds the loop may spend. Say it:
   "T2: two reviewers, R1 + up to 2 confirm rounds."
2. **Lanes** — which model builds and which review:
   `orchestrator/references/lanes.md` (the only place model names live).
3. **User overrides** — "review loop 3 times", "all three reviewers" — set the
   budget or reviewer set for this task.

## The review sequence

A runs once; B loops within budget; C is the gate at the end.

### Step A — Two-axis single pass (cheap, first)

`references/two-axis-single-pass.md`: two parallel sub-agents review the
diff along two separate axes — **Standards** (repo conventions + the 12
Fowler smells + the Overbuilt and Drive-by Change checks) and **Spec** (faithfulness to the spec/issue). Never merged or
re-ranked. Fail fast first: the base ref must resolve and the diff must be
non-empty. Label every finding BLOCKING / MAJOR / MINOR / NIT; they enter
Step B as named findings. Skipped at T0.

### Step B — R1 review, then confirm rounds

**All loop rules live in `references/confirm-round-protocol.md`.** Read it
before R1. The short version:

- **R1** reviews the change's diff with the tier's reviewer lanes.
- **Only BLOCKING/MAJOR keep the loop open.** MINOR/NIT go to the deferred
  list and never trigger a round.
- **Confirm rounds review the FIX diff**, with full acceptance suite and new adversarial regression checks rerun after each fix.
  Anything outside the fix lines is OUT-OF-SCOPE-N → deferred (unless a
  reproduced BLOCKING).
- **Only reviewers with open findings** are re-dispatched.
- **Hard budget** per tier (T1 = 1, T2 = 2, T3 = 3 confirm rounds). When it's
  spent, stop and give the user redesign / another round / explicit risk acceptance; open BLOCKING/MAJOR or failing acceptance tests are NOT SHIP.
- **Stop early** on the second same-class finding (redesign the class), on no
  progress, or when most findings are fix-induced (tighten the briefs).
- **Reproduce before fixing**; verify each fix landed and its test fails
  without it.

Mechanics:
- Step-by-step bodies (brief, build, verify, commit, review, synthesize, fix,
  push, CI): `references/workflow-steps.md`.
- Dispatching the CLIs (cwd, sandbox, timing, outages, bot mode):
  `references/reviewer-dispatch.md`.
- Fix briefs: `references/fix-brief-template.md`; new-capability briefs
  against pre-written tests: `references/feature-build-brief.md`.
- Spec/design documents instead of code: `references/spec-convergence.md`.
- Multi-session or multi-batch loops: `references/persistent-loop-plan.md`
  (`scripts/loop_plan_check.py`, `scripts/attest_file.py`); dispatch capture:
  `references/dispatch-result-contract.md`
  (`scripts/capture_dispatch_result.py`); polling:
  `references/background-build-polling.md`.

### Step C — Commit/deploy gate

- **Never push without a review pass** (R1 at least, no open BLOCKING/MAJOR). T0 changes with no behavior change may push directly at the user's instruction.
- **Never deploy live without the three-reviewer gate** — all three reviewer
  lanes SHIP on the net diff, run once after the loop converges
  (`confirm-round-protocol.md` § Three-reviewer deployment gate). This is the
  user's standing instruction and applies at every tier.
- **Before tagging or releasing:** `references/release-hygiene.md`.

## Who writes the code during the loop

- The builder lane implements and fixes. The orchestrator verifies
  independently and does not hand-code non-trivial fixes.
- **Trivial fixes** (≤ ~10 lines, mechanical, no design choice — a typo, a
  missing import, a pinned off-by-one) the orchestrator may make directly,
  and must say so. If unsure whether it's trivial, delegate.
- Reviewers run read-only. The builder never commits; the orchestrator
  commits after its own verification.

## Quick reference — user says

| User says | Do |
|---|---|
| "review loop N times" | R1 + up to N−1 confirm rounds (N reviews total); stop early on SHIP |
| "build then review with codex" / "have cursor build, codex review" | build (builder lane) → R1 (reviewer A) → fix → one confirm round if anything BLOCKING/MAJOR |
| "fix and re-review" | fix round → confirm round on the fix diff |
| "review loop until clean" | until no open BLOCKING/MAJOR, within the tier budget — then ask |
| "ship it" / "deploy" | Step C; live deploy needs the three-reviewer gate |

## Convergence check

Each round should have fewer open BLOCKING/MAJOR than the last. The ledger
line per round (`confirm-round-protocol.md` § Ledger) records the counts the
stop conditions read. If the count doesn't fall, stop — another round won't
fix a fix that made things worse.

## Pitfalls — CLI arm dispatch guards

- Never launch a bounded CLI arm job with `&` inside a foreground call — the
  subshell is killed when the call returns. Arm jobs must run as Hermes
  background jobs with notify enabled.
- Write each concurrent dispatch to its own absolute log path. Two
  dispatches sharing one log corrupt both runs' records.
- Run gate claude reviews with route isolation: a clean config dir whose
  settings copy has no env block. Otherwise `--model` resolves against the
  wrong provider.

## Lessons (load on demand)

`review-lessons` is the index. Common ones:

| Case | Lesson file (in `review-lessons/references/`) |
|---|---|
| Reviewer BLOCKING contradicts the brief or a contract test | `review-findings-adjudication.md` |
| A test that passes but checks nothing; property tests | `security-property-tests.md`, `confirm-loop-lessons.md` |
| Feature wired but dead in production | `production-reachability-review.md` |
| Data integrity, migrations, idempotency | `data-integrity-principles.md` |
| CLI flags, git mechanics, push hygiene | `tool-mechanics-pitfalls.md` |
| Fix rounds at the wrong layer, two-sided fixes | `pitfalls-fix-round-verification.md` |
