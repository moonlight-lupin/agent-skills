---
name: debug
description: "Use when the user says 'fix this bug', 'this is broken', 'debug X', or hands you a failing test, stack trace, or crash with no feature ask. Process in order: reproduce; write a failing test at the highest public seam (or name why not); minimal fix; run the named test and the full acceptance suite; then enter review-commit at the risk-derived tier. The dev-pipeline bug-fix route. Unattended: proceed without asking; stops only at important forks."
metadata:
  version: 1.0.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [debug, bugfix, failing-test, stack-trace, reproduce]
    related_skills: [orchestrator, test-evals, build, review-commit, systematic-debugging, doubt-driven-development]
---

# Debug

Bug-shaped work: a defect with no feature ask. The orchestrator routes here instead of running the full feature chain (`orchestrator/references/risk-routing.md`).

## Scope

- In: failing test or suite; stack trace or crash; wrong output vs stated expectation; regression after a change — each with the reproduction material the user already has.
- Out: new behavior requests (that is the orchestrator's feature chain: `grill` → `spec` → `test-evals` → `build`); post-hoc review (that is `review-commit`). If the fix surfaces a **new important fork**, stop as an important fork (`orchestrator/references/unattended.md`) — do not silently expand scope.

## The Process (in order)

1. **Reproduce.** Build the reproduction from the user's report or the failing test. A bug you cannot reproduce is a question, not a fix: report exactly what you ran, the expected vs actual, and the missing input — then continue with any part you CAN execute (read-only diagnosis). Never "fix" from the stack trace alone.
2. **Failing test at the highest public seam.** Write the test that fails because of the bug, at the highest seam the fix will be visible at (public API over internals; the seam vocabulary is `test-evals`'s: `../test-evals/references/test-doctrine.md` § Seams). Name why no automated test is possible (not reachable at any public seam / reproduction needs a live external system) and say exactly what verification replaces it (the command, the observed output). An unreproducible claim is not a fix.
3. **Minimal fix.** Change the least code that makes the test pass without breaking the contract around it: state assumptions or return `NEEDS_CONTEXT`; every changed line traces to the defect; no drive-by refactors; unrelated dead code is mentioned, not deleted; dependency-injected seams stay injectable. Coding principles verbatim: `../orchestrator/references/coding-principles.md`.
4. **Run the named test, then the full acceptance suite.** Both, in that order, and both green. If the full suite exposes another failing test, either it is the same defect (fix covers it) or it is a second defect — fix it through this process again, its own test, rather than editing the failing test into passing.
5. **Enter `review-commit` at the risk-derived tier.** A one-line typo with no behavior change may be T0/T1 (skill_create gate + self-check); a production bug at a trust boundary is still R2/R3 with its tier's reviewer dispatch and confirm budget. The tier comes from `orchestrator/references/risk-routing.md` — severity of what the bug touches, not the diff size.

**Unattended:** all five steps run without asking; the only stops are an unresolvable reproduction (report it), an unresolvable ambiguity, or a new important fork. Commit author, message, and the CI/PR rules are `review-commit`'s.

**Attack the premise.** When two fixes fail at the same gate and both share one premise, STOP before a third attempt: write the premise down and test the premise itself, directly, before fix #3. If the premise is false, stop fixing and report the refuted premise — the repair plan is invalid, not the two patches. The premise test is part of the current fix round, never an extra one (it consumes this round's budget, not the next).

## Red Flags — Never Do These

- "Fix" without a reproduction or a named reproducible claim
- A third fix attempt without testing the premise the first two shared
- Edit a failing test into passing, or delete a failing test, as a "fix"
- Skip the full suite after the named test passes
- Expand the fix into a refactor, or delete unrelated dead code
- Hide an unreproducible bug in "probably fixed, close it"
- Route scope-creating asks through this skill (feature asks go to the orchestrator)

## Verification

- [ ] Reproduction recorded (command + expected vs actual) or the missing input named
- [ ] Failing test added at the highest public seam — or the no-test reason + replacement verification named
- [ ] Named test GREEN after the minimal fix; suite GREEN after it
- [ ] No test edited into passing; nothing outside the defect changed
- [ ] review-commit entered at the risk-derived tier with the fix diff

## References

- `../test-evals/references/test-doctrine.md` — seam vocabulary and TDD law the failing test follows
- `../orchestrator/references/coding-principles.md` — the builder block pasted into any fix dispatch
- `../orchestrator/references/unattended.md` — important-fork stop rules
- `../orchestrator/references/risk-routing.md` — the tier the fix enters review at
