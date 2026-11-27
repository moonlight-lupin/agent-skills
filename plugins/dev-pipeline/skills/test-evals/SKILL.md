---
name: test-evals
description: "Use when writing tests or verifying behavior before code lands — the stage that writes the plan's tests and runs them RED before build; TDD red-green-refactor, the iron law (no production code without a failing test first), seam-first public-interface tests, test sizes, mock discipline. Or when the user says \"TDD N loops each batch Opus loop\", \"batch properly, Opus on each batch before commit\", \"implement, use TDD\", or wants multi-feature TDD with per-batch Opus review before commit. Supports both Hermes-builds and Cursor-builds. Covers pre-commit five-axis review, severity labels, and verifying external review findings before fixing. Unattended: state the RED results and continue — stops only at important forks."
metadata:
  version: 2.2.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [tdd, testing, red-green-refactor, seams, test-sizes, mocks, batched-tdd, opus-review, pre-commit-review, severity-labels, test-evals]
    related_skills: [build, spec, review-commit, skill-quality-review, model-routing, doubt-driven-development, hermes-agent-skill-authoring]
---

# Test Evals

The test-and-evaluation stage of the dev-pipeline: how behavior is pinned
before it ships. Test-driven development is the core discipline; the batched
multi-feature TDD loop with a per-batch Opus review, the pre-commit
verification pipeline, and external-review-finding verification hang off it.

**Core principle:** If you didn't watch the test fail, you don't know if it tests the right thing.

**Tests verify behavior through public interfaces.** A bad test is one that
breaks on a refactor without a behavior change.

## This stage owns the tests

In the pipeline, the plan names each task's test cases (behavior, seam,
expected value and where it comes from). This stage turns them into real
tests, runs each one to a failure for the right reason, and attests the files
(`review-commit/scripts/attest_file.py attest`) so the build can't quietly
rewrite them. The `build` implementer makes them GREEN; it adds a test only
for behavior the plan missed, and says so. Output of this stage: the test
files, a RED run log, and one line per test naming the seam note it pins.

**Case tables:** when the plan has a case table for a stateful rule
(`briefs/references/case-tables.md`), every row becomes one RED test at the
public seam, named in the table's Test column. A row without a test is a gap
to report, not to skip.

## When to Use

- User says "TDD N loops each batch Opus loop" or "batch properly, Opus on each batch before commit"
- User says "implement, use TDD" or "TDD, 2 loops each batch, Opus on each batch"
- Writing new features, bug fixes, or behavior changes that need failing tests first
- Reviewing or sizing a change before commit (five-axis review, severity labels)
- Verifying external review findings before fixing them

**Don't use for:**

- Iterative post-commit review convergence — the `review-commit` stage owns that
- In-flight doubt about a mid-build step — that's `doubt-driven-development`
- Judging a skill's own quality — the `skill-quality-review` efficacy rubric and
  its Checks stay owned by that skill; this stage links to it, it does not
  duplicate the rubric
## Craft pointers

Full TDD methodology (RED-GREEN-REFACTOR, Iron Law, rejected rationalizations, seam-first sizing, test sizes, DAMP over DRY, Beyonce rule), seam and mock discipline, batched TDD + Opus loop, pre-commit review, pattern integration, and the full Red Flags list: `references/test-doctrine.md` — load when writing or reviewing tests. Methodology: `references/test-driven-development.md`; the batched loop: `references/batched-tdd-opus-loop.md`.

## Red Flags — top structural

Governing list (single home): `references/test-doctrine.md` § Red Flags — the lines below are a compressed summary picked FROM that list, not the authority. Top from the governing list: writing production code without a failing test first; a refactor that relocates complexity instead of making branches disappear; a bulk "bump dependencies" PR with no changelog review; spiking without a verdict (spike code left behind); trusting the builder's self-report without independent verification; hand-coding fixes while the review loop is active.

## Verification

After completing any development workflow task, confirm:

- [ ] Tests written before production code (TDD) — or explicit justification for skipping
- [ ] Every test attaches at a named seam (the highest that reaches the behavior) and cites its seam note
- [ ] Independent review completed (not self-verified) — another agent or model
- [ ] Findings labeled with severity (Critical / Required / Optional / Nit / FYI)
- [ ] Change size within target (~100 lines good, ~300 acceptable, ~1000 split)
- [ ] No dead code left behind (or explicitly listed for future removal)
- [ ] Refactoring separated from feature work (or explicitly combined at reviewer discretion)
- [ ] Simplification reduced concepts, not relocated them
- [ ] Spike code discarded or explicitly marked for reuse
- [ ] External review findings verified independently before fixing

## Stage-exit confirmation
After this stage, the TDD verification checklist above must pass and
every rule file listed in References must be reachable from this file.
The stage runs unattended (`orchestrator/references/unattended.md`):
after the RED run, state the test paths and results and continue to
`build` — no stage-handoff question; a stop happens only at an important
fork (one numbered question with a recommended answer).

## References

- `references/test-doctrine.md` — full TDD methodology, seam/mock discipline, batched loop, pre-commit review, full Red Flags list
- `references/{test-driven-development,batched-tdd-opus-loop,key-rules}.md` — methodology, the batched loop, stage key rules
- `references/{pre-commit-review,requesting-code-review,review-report-shape}.md` — review mechanics
- `references/{pitfalls-cli-and-env-mechanics,pitfalls-loop-convergence,pitfalls-review-findings}.md` — pitfall notes

## Where it fits

Owns the tests between the plan and the build. Follows `spec` (test cases come from the plan); hands to `build` (implementers turn RED tests GREEN; they do not rewrite them). The stage-exit confirmation above is the handoff contract.
