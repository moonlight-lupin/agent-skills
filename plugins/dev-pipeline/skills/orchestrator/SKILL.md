---
name: orchestrator
description: "Use when the user asks how to approach building a feature or says 'build X', 'implement X', 'add feature X' without naming a phase ('SDD it', 'spec-driven development', 'run the dev pipeline', 'what phase comes next') — the dev-pipeline stage router: complexity S0-S3 and risk R0-R3 first, then grill → spec (+clarify, plan, tickets) → test-evals → build → review-commit (two-axis pass, budgeted confirm rounds, commit/deploy gate). Owns risk-based review routing, complexity-aware planning, the model lanes, and the unattended execution / important-fork rule."
metadata:
  version: 2.3.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [sdd, spec-driven-development, orchestrator, dev-pipeline, routing, stages, workflow, size-tiers, lanes, kanban, converge]
    related_skills: [grill, spec, test-evals, build, review-commit, review-lessons, kanban-orchestrator, model-routing, improve-codebase-architecture, doubt-driven-development, cursor-cli, codex, claude-code]
---

# Orchestrator — Spec-Driven Development (SDD) Router

A **router**: it independently classifies complexity and risk, then picks the stage, then you load that stage
skill. It holds no stage content itself. It owns four single-home files every
stage points to:

- `references/risk-routing.md` — authoritative S0-S3 complexity and R0-R3 risk classification
- `references/unattended.md` — the important-fork definition: the pipeline runs unattended and stops only at important forks
- `references/size-tiers.md` — compatibility T0-T3 reviewer depths and budgets
- `references/lanes.md` — lane roles and rules, which model builds and
  which review; model pins live in the lanes config
- `references/coding-principles.md` — how code gets written (think first,
  simplicity, surgical changes, goal-driven), the S0/S1 plan format, the
  unreachable-scenario definition, and the builder block every brief carries
- `references/principles-index.md` — external one-principle skills (pstack), load on demand

The chain diagram lives in `references/flow-map.md`.

## When to use

- User says "build X", "implement X", "add feature X" and doesn't name a phase
- User asks "how should we approach building X?" or "what's next?"
- You need to decide how much process a change deserves

**Don't use** when the user already named a phase ("write a spec for X",
"review this diff") — load that stage skill directly.

## Step 0 — classify complexity and risk (always)

Read `references/risk-routing.md` first. State complexity S0–S3, risk R0–R3,
and the derived T0–T3 **review tier** with reasons. Complexity selects how
much planning/decomposition occurs; risk selects reviewers and loop budgets.
The existing reviewer lanes and confirm-round protocol remain authoritative
for executing that review tier.

| Complexity | Planning path |
|---|---|
| S0 | Direct edit, assumptions, verification |
| S1 | Short acceptance-criteria plan, test for behavior changes |
| S2 | Spec and task plan, RED tests, build |
| S3 | Full spec, cross-component plan, dependency/task slicing, RED tests, build |

| Risk | Review depth |
|---|---|
| R0 | T0 for S0; T1 otherwise |
| R1 | T1 (one reviewer, one confirm round) |
| R2 | T2 (two reviewers, two confirm rounds) |
| R3 | T3 (three reviewers, three confirm rounds) |

Any live deploy requires the three-reviewer gate. Never silently downgrade
risk, including for small changes. Every fix must be followed by the complete
acceptance suite; exhausted rounds with open blockers are NOT SHIP.

## Engineering evidence

Follow `references/engineering-evidence.md` for deterministic checks. Discover capabilities with `dev_pipeline_discover` and diagnose with `dev_pipeline_doctor`. Use the existing lane resolver; install only approved capabilities via `dev_pipeline_setup`. Execute selected checks with `dev_pipeline_engineering_run`, retain evidence, and run `dev_pipeline_gate` on the final clean commit before push/tag/deploy. NOT_SHIP blocks this workflow. Missing tools are not passes. Existing risk-tier gates and acceptance tests still apply.

## The stages

| Stage | Produces | Load when |
|---|---|---|
| **`grill`** | hardened plan — every decision branch settled with the user | plan is fuzzy (S2/S3; S1 only if ambiguous) |
| **`spec`** — spec turn | user stories, acceptance criteria, `[NEEDS CLARIFICATION]` markers, seam sketch + seam notes → `.hermes/specs/` | intent not pinned (S2/S3) |
| `spec` — clarify | markers resolved and folded back | markers remain after the spec turn |
| **`spec`** — plan turn | tasks with tracer-bullet slices, blocking edges, file paths, interfaces, the test cases each task must pass → `.hermes/plans/` | spec exists (or clear requirements), need the HOW |
| `spec` — tickets turn (optional) | tickets with blocking edges → `.hermes/tickets/` | want parallel work units |
| **`test-evals`** | the RED tests for the plan's test cases, each citing its seam note, run to failure | after the plan, before `build` |
| **`build`** | working code; per-task review per tier; final integration review; converge loop | plan (or tickets) ready and tests RED |
| **`debug`** | reproduced bug → failing test at the highest public seam → minimal fix → suite green → review-commit at tier | bug-shaped work: "fix this", "this is broken", failing test/stack trace, no feature ask |
| **`review-commit`** | two-axis pass → R1 → budgeted confirm rounds → commit/deploy gate (+ the CI watch-and-fix loop and PR rules) | after the build or the fix, through commit and deploy |

**Bug-shaped asks** route to `debug` (reproduce → failing test → minimal fix → suite → review-commit), bypassing grill/spec/test-evals/build; a feature ask inside a bug report is a fork — route the feature part back to the orchestrator.

**Test ownership:** the plan names each test case (behavior, seam, expected
value and its source); `test-evals` writes those tests and runs them RED;
`build` implementers make them GREEN and don't rewrite them. An implementer
adds a test only for behavior the plan missed (a bug found mid-build) — under
TDD, and listed in its report.

## Two execution paths

**Path A — decomposed (S2/S3 default):** grill when fuzzy → spec → plan → test-evals → build → review-commit; independent review at the risk-derived T-tier; R1 does not become T3 because the project is large.
**Path B — single CLI agent (S1 default; S2 greenfield when appropriate):** short plan/spec → tests → builder-lane CLI → review-commit; R2/R3 keep full review depth in Path B.

## Unattended execution

The pipeline runs **unattended**: stages do not pause at handoffs to ask
"shall I proceed?". Stops happen only at *important forks* — public-contract
changes, trust/auth/money/privacy/irreversible-data boundaries,
expensive-to-reverse architecture, a relaxed constraint, or a ship-gate
choice with residual risk. The full definition (and what is explicitly *not*
a fork: stage handoffs, optional extras, push + draft PR after SHIP) lives
in `references/unattended.md` — the single home every stage points to.
`grill` settles every foreseeable fork before the spec; a *new* fork
mid-pipeline stops the session with one numbered question and a recommended
answer, then continues.

## Routing rules

1. Classify **both** S and R via `risk-routing.md`; plan and split by S; lanes and confirm budget by the R-derived T-tier; stage selection does not determine reviewer count.
2. Goldfish spec review runs for S2/S3 after the approved plan — without prompting (`references/unattended.md`).
3. Tests start RED where behavior changes; verify GREEN plus full acceptance after fixes; never let an exhausted budget conceal failing tests.
4. Escalate risk on any new trust boundary; user-specified reviewers may add scrutiny; live deploy always retains the three-reviewer gate.
5. An existing (non-blank) repo without a stamped context doc → `repo-context` bootstrap before spec/build planning begins (`../repo-context/SKILL.md`); at the commit gate a `stale` verdict is that skill's maintenance, not a routing question.

## Goal binding

Bind the pipeline to a session goal (`/goal`) with the plan's acceptance command as a
hard gate and a turn budget computed from the plan (never the shipped 20-turn
fallback): `references/goal-binding.md` — the single home for the contract template,
the gate rule, and the budget formula. Set the goal at pipeline start; the chain
consumes it (build: ledger shares the gate command; review-commit: done requires the
gate green).

## Quick start

Classify S and R → state derived T review tier → make the S-sized plan →
write RED tests → build → run R-sized review → verify full acceptance →
commit/deploy gate.

Load one stage skill at a time — each is separate for context economy.

## Outside-skill pointers

- **Kanban orchestration** — `kanban-orchestrator` (devops).
- **Model pins** — `config/lanes.default.toml` is the single source (machine overrides merge on top); `references/lanes.md` has lane roles only; outside `model-routing` covers provider/budget choices — reconcile before relying on its pins.
- **Architecture health** — `improve-codebase-architecture`; **mid-build doubt** — `doubt-driven-development` (both outside skills).
- **Briefs and case tables** — `briefs` (this plugin); **lessons** — `review-lessons` (this plugin; by case, on demand).
