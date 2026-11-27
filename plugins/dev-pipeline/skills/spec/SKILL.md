---
name: spec
description: "Use when pinning intent before code — capture a spec (user stories, acceptance criteria, [NEEDS CLARIFICATION] markers), then plan the HOW (bite-sized tasks, blocking edges, gates) or slice tracer-bullet tickets. Triggers: 'write a spec', 'plan this', 'break this into tickets', 'slice this up', 'create tickets', 'what are the work units'."
metadata:
  version: 2.1.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [spec, specification, planning, plan-mode, to-tickets, tickets, tracer-bullet, requirements, constitution-gates, no-placeholders, vertical-slice]
    related_skills: [grill, orchestrator, test-evals, build, doubt-driven-development]
---

# Spec

Three jobs, one stage, in order of invocation:

1. **Spec** — capture WHAT/WHY before planning: user stories, acceptance criteria, `[NEEDS CLARIFICATION]` markers, seam sketch. No tech stack.
2. **Plan** — write an actionable implementation plan consuming the spec: bite-sized tasks, exact paths, interfaces, the test cases each task must pass, complete production code where the HOW isn't obvious, no placeholders.
3. **Tickets** — slice a settled spec or plan into tracer-bullet tickets with blocking edges (see `references/ticket-slicing.md`).

Do the job the user invoked — specifying only, or planning only. The `grill` stage hardens the plan first if decisions are unresolved.

**By complexity** (`orchestrator/references/risk-routing.md`): S0 skips this stage. S1 skips the spec turn — the plan header carries an assumptions line and 3-6 acceptance criteria written as `step → verify: check` (format in `orchestrator/references/coding-principles.md` § Plan format for S0/S1), and the plan is one task. S2/S3 run all turns. Review depth (the risk-derived T-tier) does not select spec turns: an S3/R1 change still gets the full spec with T1 review.

**Case tables for rules with state.** Any rule whose result depends on
history — corrections, retries, idempotence, rolling windows, caches, sync,
draft/post lifecycles, permission matrices, time boundaries — gets a case table
in the plan turn (`briefs/references/case-tables.md`): one row per case, with
the expected result at the public seam. Prose is not enough: each case it
leaves out becomes a review round later. S2/S3 always; S1 when such a rule is
in scope. The table is reviewed once, before the build.

**Test cases, not test code.** For each task the plan names its test cases: behavior, seam (with its seam note), inputs, expected value and where that value comes from. The `test-evals` stage writes the test code and runs it RED; the `build` implementer makes it GREEN.

## When to Use

- User says "write a spec for X", "plan X", "plan mode", "break this into tickets", "slice this up", "create tickets", "what are the work units"
- Starting a non-trivial build from scratch — pin intent first; or a spec exists and you need the HOW
- The work would lose track in one context window, or you want parallelizable work units with dependency edges

**Don't use for:**

- Plans so fuzzy that decisions hide in them — use the `grill` stage first
- Single-task features that fit in one plan task (plan directly; skip ticket slicing), research or exploration, post-hoc code review (use the pipeline's review stage)

## Spec turn — Core behavior

When the job is to define **what** to build and **why**, before any implementation plan:

- Do not design the implementation.
- Do not choose a tech stack, architecture, libraries, or data structures.
- Do not write code, file paths, or task breakdowns.
- You may inspect the repo or other context with read-only tools when needed.
- Your deliverable is a markdown spec saved under `.hermes/specs/`.

**Core principle:** A spec captures intent — what users need and why. Implementation is the job of the plan. Mixing them produces specs that break every time the tech stack changes and plans that bake in unexamined assumptions.

## Plan turn — Core behavior

When the job is a plan instead of execution:

- Do not implement code.
- Do not edit project files except the plan markdown file.
- Do not run mutating terminal commands, commit, push, or perform external actions.
- You may inspect the repo or other context with read-only commands/tools when needed.
- Your deliverable is a markdown plan saved inside the active workspace under `.hermes/plans/`.

**Core principle:** A good plan makes implementation obvious. If someone has to guess, the plan is incomplete. Write for an implementer with zero context: bite-sized tasks, DRY, YAGNI, TDD, frequent commits (full craft in `references/task-doctrine.md`).

### Output requirements

Write a markdown plan that is concrete and actionable: Goal; current context / assumptions; proposed approach; step-by-step plan; files likely to change; tests / validation; risks, tradeoffs, and open questions — and for code tasks, exact file paths, likely test targets, and verification steps.

Full header, Constitution Gates, and Task Structure templates plus the writing process (Steps 0–7): `references/plan-template.md`.

### Interaction style

If the request is clear enough, write the plan directly; with no explicit instruction, infer the task from the conversation context; if genuinely underspecified, ask a brief clarifying question instead of guessing. After saving, reply briefly with what you planned and the saved path.

## The WHAT/WHY boundary

| Belongs in `spec` (WHAT/WHY) | Belongs in `plan` (HOW) |
|---|---|
| User stories and goals | Tech stack and libraries |
| Acceptance criteria | Architecture and file layout |
| Non-functional requirements (performance targets, security posture) | Specific tools that meet those targets |
| Constraints (organizational, compliance, platform) | How those constraints are satisfied in code |
| Edge cases and error behavior (from the user's perspective) | Error handling implementation |
| Data the user cares about (entities, relationships) | Data model, schema, migrations |

If you catch yourself writing "use React" or "store in PostgreSQL" or "create `src/models/user.py`", stop — that belongs in `plan`. The one exception: constraints the **user** stated as requirements ("must run on our existing Postgres cluster", "security-first: all inputs validated") belong in the spec — they are intent, not implementation choice. In the plan, those constraints are copied *verbatim, as data*, into Global Constraints (template in `references/plan-template.md`).

## Seam sketching (before writing the spec)

Before writing the spec, sketch the **seams** at which the feature will be tested:

- A **seam** is the stable interface a feature is tested at — where tests cross from outside to inside.
- **Prefer existing seams**; use the **highest seam possible** (public API, not internal helpers). The fewer seams, the better — the **ideal number is one**. New seams should sit as high as possible.
- Check with the user that these seams match their expectations before proceeding.
- **Record a one-line seam note next to each behavior** the seam pins: what a test at this seam catches and what it misses (e.g. "the create-order API test catches payload-shape regressions, misses queue-timeout behavior"). The `test-evals` stage consumes these notes — every RED test there must cite the seam note it pins.
- **Include the seam list (with its notes) in the handoff**: the notes travel with the spec artifact into the plan turn and the handoff to `test-evals` — a seam without its note is not recorded.

This matters for agentic development: a good interface gives tests something durable to target, so the code underneath can change without the tests moving.

See the `improve-codebase-architecture` skill (outside skill, not bundled here) — its codebase-design reference — for the full vocabulary (module, interface, depth, seam, adapter, leverage, locality).

## Scope Check

If the spec covers multiple independent subsystems, suggest breaking it into separate plans — one per subsystem. Each plan should produce working, testable software on its own.

## Task decomposition doctrine

Stated once, in full, in `references/task-doctrine.md`: tracer-bullet tasks, explicit blocking edges with frontier scheduling, the expand-contract exception for wide refactors, sizing to a fresh context window, task right-sizing, pre-agreed seams, and bite-sized 2-5-minute granularity. Apply it to every task breakdown in this stage and to tickets (`references/ticket-slicing.md`).

## Spec document structure

Write the spec into the full template in `references/spec-template.md` (user stories, decisions, NFRs, constraints, edge cases, open questions), following the WHAT/WHY boundary and the seam sketch.

## `[NEEDS CLARIFICATION]` markers — first-class ambiguity

**Never guess.** If the user's description does not specify something, mark it explicitly rather than filling in a plausible assumption.

- `[NEEDS CLARIFICATION: auth method not specified — email/password, SSO, OAuth?]`
- `[NEEDS CLARIFICATION: should albums be nestable? description says "never in other albums" but photo-of-photo case unclear]`
- `[NEEDS CLARIFICATION: offline-first or online-only?]`

This complements the plan's "No Placeholders" rule. The plan forbids TBD in the implementation plan; the spec **surfaces** ambiguity so it can be resolved before planning, not buried in a guess.

## Clarify phase (before planning)

Before handing off to the plan, attempt to resolve open questions:

1. List all `[NEEDS CLARIFICATION]` markers.
2. Ask the user targeted questions, batching related ones — don't ping-pong one at a time.
3. Fold answers back into the spec — marker becomes a resolved requirement or an explicit constraint.
4. If the user is unavailable, keep the markers; the plan will see them. Never silently resolve them.

**Do not plan on top of ambiguity you can resolve.** A spec with unresolved markers produces a plan with guessed requirements, which produces code doing the wrong thing confidently.

## Goldfish spec review (pre-implementation gate)

After the plan turn is saved and approved, and BEFORE the `test-evals` stage, offer the Goldfish spec review — a zero-context subagent swarm (Zoom Out, Comprehension, Design Critic, Implementation Readiness personas) that stress-tests the plan. Offered at S2 and S3 (`orchestrator/references/risk-routing.md`); S0, S1, and research are exempt. Optional spec-range pass after the spec turn when intent risk is high. Persona files, dispatch contract, and convergence rules: `references/goldfish-spec-review.md` (single home — dispatch from there).

## Consume the spec first (plan turn)

Before understanding requirements from scratch, check for a spec artifact under `.hermes/specs/` (Step 0 of the writing process in `references/plan-template.md`). If one exists, read it and treat it as the **source of truth for WHAT and WHY**: every story covered and every acceptance criterion mapped to a task's verification step, NFRs and constraints copied into Global Constraints *verbatim*, tasks for every edge case, and surviving `[NEEDS CLARIFICATION]` markers resolved with the user or carried in as flagged assumptions — never silently resolved.

The spec tells you **what** to build. Your plan decides **how**.

## Constitution gates

Skip if no `.hermes/constitution.md` exists and the user stated no governing principles. Otherwise encode them as pre-implementation gates the plan must pass before any task runs — compile-time checks on architectural decisions. A failed gate does not block the plan; it requires a documented justification in the "Complexity Tracking" note rather than silent proceeding. Gate checks run during self-review.

Standard gates (full checklists in `references/plan-template.md`): **Simplicity Gate**, **Anti-Abstraction Gate**, **Test-First Gate**, **Integration-First Gate**, plus a **[Project-Specific Gate]** per stated governing principle.

## Cross-Artifact Consistency (analyze)

If a spec artifact exists, check the plan against the spec, not just the plan against itself — the `analyze` phase from spec-kit, full checklists at Step 7 of `references/plan-template.md`. Three checks: **Coverage** (every user story, acceptance criterion, non-functional requirement, edge case, and verbatim constraint maps to a task or is explicitly deferred with a note), **Drift** (no scope creep, no contradiction, no silently resolved `[NEEDS CLARIFICATION]` marker), **Gates** (every constitution gate passes or carries a Complexity Tracking justification). Coverage gaps → add the task; drift → fix the plan. This catches the most common planning failure: an internally consistent plan that has drifted from its intent.

## Self-review checklist

Run this on the completed spec — "unit tests for the spec":

- [ ] Every user story has testable acceptance criteria ("returns 200 with JSON body containing field X", not "works correctly")
- [ ] No tech stack, library names, file paths, or architecture choices leaked in
- [ ] Every `[NEEDS CLARIFICATION]` marker is resolved or genuinely unresolvable until the user returns
- [ ] Non-functional requirements are measurable (target numbers, not "fast" / "secure")
- [ ] Edge cases cover: empty state, max/over-limit, invalid input, concurrency (if relevant), failure modes
- [ ] No speculative or "might need" features; every item traces to a user story or stated constraint
- [ ] Constraints copied verbatim from the user's words, not paraphrased into ambiguity

If any check fails, fix the spec before saving.

## Self-Review

After writing the complete plan, run a final pass yourself (not a subagent dispatch): re-run the Cross-Artifact Consistency (analyze) checks, scan for placeholders, and check type consistency — types, method signatures, and property names used in later tasks must match those defined in earlier tasks (`clearLayers()` in Task 3 vs `clearFullLayers()` in Task 7 is a bug). Fix issues inline and move on.

## No Placeholders

Every plan step must contain the actual content an engineer needs. These are **plan failures** — never write them:

- "TBD", "TODO", "implement later", "fill in details"
- "Add appropriate error handling" / "add validation" / "handle edge cases"
- "Write tests for the above" (without naming each test case, its seam, and its expected value with source)
- "Similar to Task N" (repeat the code — the engineer may be reading tasks out of order)
- Steps that describe what to do without showing how (code blocks required for code steps)
- References to types, functions, or methods not defined in any task

## Save location

Save with `write_file`, relative to the active working directory:

- Spec: `.hermes/specs/YYYY-MM-DD_HHMMSS-<slug>.md`
- Plan: `.hermes/plans/YYYY-MM-DD_HHMMSS-<slug>.md`
- Tickets: `.hermes/tickets/<feature-slug>/` (see `references/ticket-slicing.md`)

## Ticket slicing

When the plan is settled and you want parallelizable work units, slice it into tracer-bullet tickets with blocking edges ("break this into tickets", "slice this up", "create tickets"). The process, ticket file format and template, granularity quiz, frontier scheduling, and the integrate-and-verify option live in `references/ticket-slicing.md`.

## Handoff to plan

After saving the spec, reply with the spec path and offer the execution path ("Path A — subagent-driven (default)"): **"Spec saved. Ready for the plan turn — it consumes this spec and produces a task breakdown with test cases; then `test-evals` writes those tests RED and `build` executes the tasks with per-task review at this work's tier (T_). Shall I proceed?"**

**Path B — single CLI agent orchestrate-and-review:** for builds dispatched to a single external coding CLI (Cursor, Codex, Claude Code), the spec feeds a self-contained implementation brief the CLI reads end-to-end — the brief draws WHAT/WHY and constraints from the spec, but holds the task breakdown itself. **"Spec saved. Ready to write a self-contained implementation brief for [Cursor/Codex/Claude Code] — the brief consumes this spec as the WHAT/WHY source. Shall I proceed?"**

Path A for multi-task per-task review gates; Path B for greenfield builds on a strong single-agent CLI where the orchestrate-and-review loop is the quality gate.

### Execution Handoff

After saving the plan, offer the next step: **"Plan complete and saved. Next: `test-evals` writes the plan's test cases and runs them RED, then `build` dispatches a fresh subagent per task with T_ review. Shall I proceed?"** Execution is the `build` stage: fresh `delegate_task` per task; per-task review per tier (T2: one combined reviewer; T3: spec compliance, then code quality); proceed only when the verdicts approve. For S1 plans, offer **inline execution** with checkpoints.

## Verification

Before proceeding to implementation, confirm: the Self-review checklist above passes; the spec is saved under `.hermes/specs/`; the human has reviewed and approved it.

For the plan: tasks sequential, sized per `references/task-doctrine.md`, exact paths, interfaces, named test cases with expected values and their source, copy-pasteable production code where the HOW isn't obvious, exact commands with expected output, gates checked or justified.

## Remember

WHAT/WHY only — no HOW; stories with testable criteria; `[NEEDS CLARIFICATION]` for every ambiguity; consume the spec first; no placeholders; gates checked or justified; cross-artifact analyze against the spec.

**A good spec makes the intent unambiguous. A good plan makes the implementation obvious.**
