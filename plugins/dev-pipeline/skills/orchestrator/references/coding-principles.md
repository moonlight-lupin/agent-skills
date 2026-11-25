# Coding Principles (single home)

Four principles for anyone who writes code in this pipeline — the
orchestrator, implementer subagents, and the builder lane. Adapted from
[andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)
(MIT), which distills Andrej Karpathy's observations on LLM coding pitfalls,
and fitted to this pipeline's stages and tiers.

Other files point here; they don't restate the principles. The one deliberate
copy is the **builder block** below: the builder lane reads only its brief,
never these skills, so every implementer brief and fix brief pastes that block
verbatim.

The principles bias toward caution over speed. Size the rigor with the tier
(`size-tiers.md`): a T0 typo needs none of the ceremony, only the habits.

## 1. Think before coding

Don't assume. Don't hide confusion. Surface tradeoffs.

- State assumptions explicitly. When the ask has more than one reading, name
  the readings — don't pick one silently.
- If a simpler approach exists, say so and push back.
- If something is unclear, stop and name what's confusing.

**Where it runs in the pipeline:** questions are asked BEFORE dispatch — in
`grill`, in the spec's `[NEEDS CLARIFICATION]` markers, and in the build's
pre-flight scan. Mid-task, an implementer never silently picks: it reports
`NEEDS_CONTEXT`. S0/S1 work, which skips grill and the spec, states its
assumptions in one line instead (see *Plan format for S0/S1*).

## 2. Simplicity first

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstraction for single-use code.
- No flexibility or configuration that wasn't requested.
- No error handling for scenarios that can't happen (see *Unreachable
  scenarios* — this is not a license to skip input validation).
- If 200 lines could be 50, rewrite it. Ask: would a senior engineer call
  this overcomplicated?

## 3. Surgical changes

Touch only what you must. Clean up only your own mess.

- Don't "improve" adjacent code, comments or formatting.
- Don't refactor what isn't broken. TDD's REFACTOR step covers only code this
  task wrote or changed.
- Match the existing style, even if you'd do it differently.
- Unrelated dead code: mention it in the report, don't delete it.
- Orphans YOUR change created (imports, variables, functions it made unused):
  remove them.

**The test:** every changed line traces to the task or finding.

## 4. Goal-driven execution

Define success criteria. Loop until verified.

- "Add validation" → "write tests for invalid inputs, then make them pass".
- "Fix the bug" → "write a test that reproduces it, then make it pass".
- "Refactor X" → "tests pass before and after".

In this pipeline the plan's test cases and `test-evals`' RED tests are the
success criteria at T1-T3, and "review reports are not proof" means the
orchestrator re-runs the checks itself.

## Plan format for S0/S1

S0 and S1 skip the spec turn, so they carry two lines of intent-pinning
instead. State them to the user with the classification line:

```
S1/R1 (T1 review) — one endpoint, ~150 lines, no external exposure.
Assumptions: <each assumption, or "none">. Readings considered: <if the ask had more than one>.
1. <step> → verify: <check>
2. <step> → verify: <check>
3. <step> → verify: <check>
```

Each step's check is something that can be run or observed (a test, a
command and its expected output, a page state), never "it works". At T1 the
plan header's 3-6 acceptance criteria are written in this form. T0 may be a
single step.

## Unreachable scenarios

A scenario is **unreachable** when no production entry point (API route, CLI
command, MCP tool, scheduled job, public function the product calls) can
produce it — e.g. a `None` from a function whose every caller passes a
checked value, or a branch the type system rules out.

A scenario is **reachable** — never "impossible" — whenever its input comes
from outside the process: user input, files, network, environment,
configuration, another service, concurrent writers. Validation, auth checks
and error handling for those are required, not speculative.

Reviews apply this through the severity rule in
`review-commit/references/confirm-round-protocol.md`.

## Builder block

`briefs/scripts/stamp_brief.py` stamps this block into every builder brief as
`{{BUILDER_BLOCK}}` (implementer, fix and feature briefs:
`build/references/per-task-workflow.md`, `briefs/references/fix-brief-template.md`,
`briefs/references/feature-build-brief.md`,
`review-commit/references/workflow-steps.md` Step 1). Keep it a single fenced
block directly under this heading: the script reads the first fence here.

```
CODING PRINCIPLES (dev-pipeline):
- Assumptions: list every assumption you made in your report. If the task has
  more than one reading, or something is unclear, STOP and report
  NEEDS_CONTEXT — never pick a reading silently.
- Simplicity: write the minimum code that passes the named tests. No
  features, abstractions, options or error handling the task didn't ask for.
  Inputs from outside the process (user, files, network, config) still get
  validated.
- Surgical: every changed line must trace to this task. Don't reformat,
  rename or refactor code the task doesn't touch; match the existing style.
  Refactor only code you wrote or changed in this task.
- Dead code: mention unrelated dead code in your report — don't delete it.
  Remove only imports/variables/functions YOUR change made unused.
- Done means the named checks pass when run, not that the code looks right.
```
