---
name: test-evals
description: "Use when writing tests or verifying behavior before code lands — the stage that writes the plan's tests and runs them RED before build; TDD red-green-refactor, the iron law (no production code without a failing test first), seam-first public-interface tests, test sizes, mock discipline. Or when the user says \"TDD N loops each batch Opus loop\", \"batch properly, Opus on each batch before commit\", \"implement, use TDD\", or wants multi-feature TDD with per-batch Opus review before commit. Supports both Hermes-builds and Cursor-builds. Covers pre-commit five-axis review, severity labels, and verifying external review findings before fixing. Unattended: state the RED results and continue — stops only at important forks."
metadata:
  version: 2.1.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [tdd, testing, red-green-refactor, seams, test-sizes, mocks, batched-tdd, opus-review, pre-commit-review, severity-labels, test-evals]
    related_skills: [build, spec, review-commit, skill-quality-review, model-routing, doubt-driven-development, hermes-agent-skill-authoring]
---

# Test Evals

## Overview

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

## 1. Test-Driven Development (TDD)

**Core principle:** the Overview's — the one stated there is the rule this cycle enforces (see Overview; restated once, applied everywhere in this stage).

### RED-GREEN-REFACTOR Cycle
1. **RED** — Write one minimal failing test. Run it. Watch it fail for the right reason (feature missing, not typo).
2. **GREEN** — Write simplest code to pass. Cheating is OK (hardcode, copy-paste). Run test to verify pass.
3. **REFACTOR** — Clean up duplication, improve names, extract helpers — in code THIS cycle wrote or changed, nothing else (surgical changes, `orchestrator/references/coding-principles.md`). Keep tests green throughout.
4. **Repeat** — Next test for next behavior.

### Iron Law
```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```
Code before test? Delete it. Start over. No "keep as reference."

### Common Rationalizations to Reject
- "Too simple to test" → Simple code breaks too.
- "I'll test after" → Tests passing immediately prove nothing.
- "Already manually tested" → Ad-hoc ≠ systematic.
- "TDD will slow me down" → TDD is faster than debugging.

### Seam first, then size

Pick WHERE a test attaches before deciding how big it is (see *Seams and mock
discipline* below):

1. **Test at the highest seam that exists** — the public API, CLI command, MCP
   tool, or module's public function the behavior is observed through. Fewer
   seams are better; one is ideal.
2. **Go lower only for logic the high seam can't reach cheaply** — dense
   pure-logic edge cases (parsers, money math, date rules) get small tests at
   their own public function.
3. **Keep the slow end small** — full-system E2E runs are for the few
   acceptance paths that need the real thing (pre-deploy smoke).

There is no target ratio of unit to integration tests. A seam test that runs
against a temp DB is the right test even if that makes "integration" the
majority. (v0.1.x carried an 80/15/5 pyramid; it pulled against the seam
rule and was dropped.)

### Test Sizes

| Size | What it touches | Speed | When to use |
|---|---|---|---|
| **Small** | One function, no I/O, no network, no DB, no filesystem | Sub-ms | Pure logic, edge cases, regression tests |
| **Medium** | Multiple functions or real I/O (filesystem, temp DB, localhost network) | Seconds | Integration, API surface, DB roundtrip |
| **Large** | Full system, external services, real network, multi-machine | Minutes | End-to-end acceptance, pre-deploy smoke |

**Label tests by size.** If a test is slow, it should be because it's doing real integration — not because it's a unit test with accidental I/O.

### DAMP over DRY

Tests favor **DAMP** (Descriptive And Meaningful Phrases) over **DRY** (Don't Repeat Yourself). Some duplication in tests is good — each test should read as a standalone narrative. A reader should understand a test without scrolling to shared helpers.

- **DRY** is for production code — shared logic, one source of truth.
- **DAMP** is for test code — readability first, some repetition acceptable.

Over-abstracted test helpers (`setupGenericFixture(Options)`) are worse than 3 tests with copy-pasted setup — the abstraction hides what each test actually tests.

### The Beyonce Rule

> If you liked it, you should have written a test for it.

Any behavior the system depends on should have a test. "Obvious" behavior that breaks in production was never obvious — it was untested. If a refactor could break it silently, it needs a test.

See `references/test-driven-development.md` for full methodology.

## Seams and mock discipline

A **seam** is the public boundary where behavior is observed — the place a
test attaches to the running system: an API route, an MCP tool, a CLI
subcommand, a module's public function.

- **Tests verify behavior through public interfaces.** A bad test is one that
  breaks on a refactor without a behavior change. If deleting the test only
  breaks when internal code is reshaped, the test is implementation-coupled.
- **No test at an unconfirmed seam.** If you cannot name which public boundary
  the test observes behavior through, do not write it — it is coupled to
  internals that can be reshaped without the behavior changing.

For every seam, leave a **one-line note on what the test at that seam catches
and what it misses** (e.g. "the create-order API test catches payload-shape
regressions, misses queue-timeout behavior"). The **spec stage records** these
seam notes next to the behavior; the **test stage consumes** them — every RED
test cites the seam note it pins.

**Anti-pattern checks** — each is a test to rewrite, not a style nit:

- **Implementation-coupled:** internal-collaborator mocks, or tests against
  private methods. Rewrite against the public surface.
- **Tautological expected values:** the test recomputes the truth the same
  way the code does — it can never fail on a real bug.
- **Side-channel verification:** asserting through `db.query` instead of the
  API. Assert what the caller observes, not where the data happened to land.

**Expected values must come from an independent source of truth:** a literal,
a worked example you did by hand, or the value stated in the spec. Never the
same computation the code performs.

**One logical assertion per test.** "and" in the test name means two tests.

**Mocks only at system boundaries**: external APIs, time/randomness,
filesystem (sometimes); prefer a test DB over a mocked DB. Never mock your
own classes or internal collaborators.

## Batched TDD + Opus loop

For multi-feature builds the user may structure TDD in batches: features are
grouped into batches, each batch gets N TDD loops (build → verify + fix),
then an actual Opus review before commit — spec → batch features → TDD loops
per batch → Opus review → fix → commit → push → CI. The trigger phrase is
"TDD N loops each batch Opus loop". The full process is kept verbatim in
`references/batched-tdd-opus-loop.md`, with the rule files below.

## Pre-commit review

Before code lands, run the verification pipeline in
`references/pre-commit-review.md`: five-axis review, severity labels, change
sizing, structural remedies, and the independent-reviewer steps. The
review-commit stage OWNS the convergence loop over review findings
(confirm-round protocol) — this stage runs the pre-commit pass that precedes
it. "If Local Coding CLIs Are Unauthenticated" territory resolves through the
`cli-auth-fallback` skill — never guess credentials.

## Integration Between Patterns

- **TDD → Code Review**: After TDD implementation, run pre-commit review before push.
- **Spike → TDD**: Once a spike is VALIDATED, discard the spike code and implement properly with TDD.
- **Simplify → Review**: Simplify-code is a cleanup pass AFTER implementation. Code review is a quality gate BEFORE commit.
- **Debug → TDD**: Bug found? Write failing test reproducing it (TDD RED). Fix it (GREEN). Test prevents regression.

## Red Flags

- Writing production code without a failing test first
- "It works, that's good enough" — working but unreadable/insecure/architecturally wrong creates compounding debt
- "I wrote it, so I know it's correct" — authors are blind to their own assumptions
- "We'll clean it up later" — later never comes; the review is the quality gate
- "AI-generated code is probably fine" — AI code needs MORE scrutiny, not less; it's confident and plausible even when wrong
- "The tests pass, so it's good" — tests are necessary but not sufficient; they don't catch architecture, security, or readability issues
- "The refactor makes it cleaner" — relocating complexity isn't reducing it; count the concepts a reader must hold
- A refactor that moves code around without making branches disappear
- A change that grows an already-large file instead of decomposing it
- New conditionals scattered into unrelated code paths (a missing abstraction)
- A near-duplicate of an existing canonical helper
- Review comments without severity labels — makes it unclear what's required vs optional
- Accepting "I'll fix it later" — it never happens
- A bulk "bump dependencies" PR with no changelog review
- Spiking without a verdict (spike code left in the codebase)
- Trusting the builder's self-report without independent verification
- Hand-coding fixes when the review loop is the active workflow — non-trivial code changes are delegated to the builder lane; hand-editing is only acceptable for trivial mechanical fixes, and say so explicitly when deviating (the `review-commit` stage's delegate rule)

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

- `references/batched-tdd-opus-loop.md` — verbatim batched TDD + Opus review process ("TDD N loops each batch Opus loop"); §6 points at the review-commit stage's confirm-round-protocol
- `references/test-driven-development.md` — full TDD methodology: iron law, cycle detail, rationalization tables, red flags, bug-fix example, Hermes integration, testing anti-patterns
- `references/pre-commit-review.md` — pre-commit verification pipeline: Five-Axis Review, Severity Labels, Change Sizing, Structural Remedies, Steps, Read-Only Codebase Audits, external-review verification
- `references/requesting-code-review.md` — pre-commit code verification dimensions (also used by the build stage's final integration review)
- `references/pitfalls-loop-convergence.md` — loop convergence: public-interface tests, RED delegation, pins, reachability, downstream review
- `references/pitfalls-cli-and-env-mechanics.md` — CLI, env, dispatch timing, turn caps, gh, pre-existing CI
- `references/pitfalls-review-findings.md` — review findings: warnings, payloads, provenance, injection, concurrency, timestamps
- `references/review-report-shape.md` — report shape to demand in every review brief; per-batch review session records stay in the source archive
- `references/key-rules.md` — read before the first batch: RED before GREEN, review-before-commit, specific `git add`, CI after push, independent verification, BLE001

## Where it fits

Test-evals is stage 3 of the dev-pipeline pipeline: `grill` → `spec` →
**`test-evals`** → `build` → `review-commit`. Tests are written in this
stage; the build stage runs the implementation (ticket title restated before
starting, dependency injection for mockability). Each seam note written at
the spec stage is consumed here at test-writing time.
