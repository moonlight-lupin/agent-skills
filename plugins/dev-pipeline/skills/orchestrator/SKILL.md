---
name: orchestrator
description: "Use when the user asks how to approach building a feature or says 'build X', 'implement X', 'add feature X' without naming a phase ('SDD it', 'spec-driven development', 'run the dev pipeline', 'what phase comes next') — the dev-pipeline stage router: complexity S0-S3 and risk R0-R3 first, then grill → spec (+clarify, plan, tickets) → test-evals → build → review-commit (two-axis pass, budgeted confirm rounds, commit/deploy gate). Owns risk-based review routing, complexity-aware planning and the model lanes."
metadata:
  version: 2.1.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [sdd, spec-driven-development, orchestrator, dev-pipeline, routing, stages, workflow, size-tiers, lanes, kanban, converge]
    related_skills: [grill, spec, test-evals, build, review-commit, review-lessons, kanban-orchestrator, model-routing, improve-codebase-architecture, doubt-driven-development, cursor-cli, codex, claude-code]
---

# Orchestrator — Spec-Driven Development (SDD) Router

A **router**: it independently classifies complexity and risk, then picks the stage, then you load that stage
skill. It holds no stage content itself. It owns three single-home files every
stage points to:

- `references/risk-routing.md` — authoritative S0-S3 complexity and R0-R3 risk classification
- `references/size-tiers.md` — compatibility T0-T3 reviewer depths and budgets
- `references/lanes.md` — lane roles and rules, which model builds and
  which review; model pins live in the lanes config
- `references/coding-principles.md` — how code gets written (think first,
  simplicity, surgical changes, goal-driven), the S0/S1 plan format, the
  unreachable-scenario definition, and the builder block every brief carries

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
| **`review-commit`** | two-axis pass → R1 → budgeted confirm rounds → commit/deploy gate | after the build, through commit and deploy |

**Test ownership:** the plan names each test case (behavior, seam, expected
value and its source); `test-evals` writes those tests and runs them RED;
`build` implementers make them GREEN and don't rewrite them. An implementer
adds a test only for behavior the plan missed (a bug found mid-build) — under
TDD, and listed in its report.

## Two execution paths

**Path A — decomposed (S2/S3 default):** grill when fuzzy → spec → plan →
test-evals → build → review-commit. Use independent review at the risk-derived
T-tier; R1 does not become T3 just because the project is large.

**Path B — single CLI agent (S1 default, S2 greenfield when appropriate):**
short plan or spec → tests → builder lane CLI → review-commit. R2/R3 still
receive full respective review depth even in Path B.

## Routing rules

1. Classify **both** complexity S and risk R using `risk-routing.md`.
2. Plan and split work by S; stage selection does not determine reviewer count.
3. Select reviewer lanes and confirm budget by R-derived T-tier.
4. Offer Goldfish spec review for S2/S3 after the approved plan.
5. Start tests RED where behavior changes; verify GREEN and full acceptance
   after fixes. Never let an exhausted budget conceal failing tests.
6. Escalate risk immediately upon discovering a new trust boundary.
7. User-specified reviewers and budgets may add scrutiny; live deploy always
   retains the three-reviewer gate.

## Quick start

Classify S and R → state derived T review tier → make the S-sized plan →
write RED tests → build → run R-sized review → verify full acceptance →
commit/deploy gate.

Load one stage skill at a time — each is separate for context economy.

## Outside-skill pointers

- **Kanban orchestration** — `kanban-orchestrator` (devops) owns spreading
  tickets across worker lanes.
- **Model pins** — `config/lanes.default.toml` is the single source
  (machine overrides merge on top); `references/lanes.md` carries lane roles
  and rules only. The outside `model-routing` skill covers provider and
  budget choices; reconcile it with the config before relying on its pins.
- **Architecture health** — `improve-codebase-architecture` (outside skill).
- **Mid-build doubt** — `doubt-driven-development` (outside skill).
- **Briefs and case tables** — `briefs` (this plugin): every brief another
  agent acts on, stamped from commands; case tables for rules with state.
- **Lessons from past loops** — `review-lessons` (this plugin; load one file
  by case, on demand).
