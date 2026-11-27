---
name: test-doctrine
description: "Test-evals deep craft moved from SKILL.md in v0.6.0: the full TDD methodology (RED-GREEN-REFACTOR, Iron Law, rationalizations, seams/sizes/DAMP/Beyonce rule), seam and mock discipline, batched TDD + Opus loop, pre-commit review, pattern integration overview, and the full Red Flags list. Load when writing or reviewing tests."
metadata:
  version: 1.0.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [tdd, doctrine, mocks, seams]
---

# Test doctrine

Moved verbatim from SKILL.md in v0.6.0 (always-loaded text shrink). SKILL.md points here.

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
