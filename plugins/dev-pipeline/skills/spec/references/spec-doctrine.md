---
name: spec-doctrine
description: "Spec-stage deep craft moved from SKILL.md in v0.6.0: WHAT/WHY boundary table, seam sketching rules, Goldfish review pointer, spec-consumption rules, constitution gates, cross-artifact analyze, plan self-review, no-placeholders rule, and the two handoff paths. Load when running a spec or plan turn."
metadata:
  version: 1.0.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [spec, doctrine, seams, handoff]
---

# Spec doctrine

Moved verbatim from SKILL.md in v0.6.0 (always-loaded text shrink). SKILL.md points here.

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
- Check with the user that these seams match their expectations **only when a seam choice is an important fork** (a public-contract change or an expensive-to-reverse shape — `orchestrator/references/unattended.md`); otherwise record the assumption in the spec and continue.
- **Record a one-line seam note next to each behavior** the seam pins: what a test at this seam catches and what it misses (e.g. "the create-order API test catches payload-shape regressions, misses queue-timeout behavior"). The `test-evals` stage consumes these notes — every RED test there must cite the seam note it pins.
- **Include the seam list (with its notes) in the handoff**: the notes travel with the spec artifact into the plan turn and the handoff to `test-evals` — a seam without its note is not recorded.

This matters for agentic development: a good interface gives tests something durable to target, so the code underneath can change without the tests moving.

See the `improve-codebase-architecture` skill (outside skill, not bundled here) — its codebase-design reference — for the full vocabulary (module, interface, depth, seam, adapter, leverage, locality).

## Goldfish spec review (pre-implementation gate)

After the plan turn is saved and approved, and BEFORE the `test-evals` stage, **run** the Goldfish spec review — a zero-context subagent swarm (Zoom Out, Comprehension, Design Critic, Implementation Readiness personas) that stress-tests the plan. It runs at S2 and S3 without prompting — the unattended default (`orchestrator/references/unattended.md`); S0, S1, and research are exempt. Optional spec-range pass after the spec turn when intent risk is high. Persona files, dispatch contract, and convergence rules: `references/goldfish-spec-review.md` (single home — dispatch from there).

## Consume the spec first (plan turn)

Before understanding requirements from scratch, check for a spec artifact under `.hermes/specs/` (Step 0 of the writing process in `references/plan-template.md`). If one exists, read it and treat it as the **source of truth for WHAT and WHY**: every story covered and every acceptance criterion mapped to a task's verification step, NFRs and constraints copied into Global Constraints *verbatim*, tasks for every edge case, and surviving `[NEEDS CLARIFICATION]` markers resolved with the user or carried in as flagged assumptions — never silently resolved.

The spec tells you **what** to build. Your plan decides **how**.

## Constitution gates

Skip if no `.hermes/constitution.md` exists and the user stated no governing principles. Otherwise encode them as pre-implementation gates the plan must pass before any task runs — compile-time checks on architectural decisions. A failed gate does not block the plan; it requires a documented justification in the "Complexity Tracking" note rather than silent proceeding. Gate checks run during self-review.

Standard gates (full checklists in `references/plan-template.md`): **Simplicity Gate**, **Anti-Abstraction Gate**, **Test-First Gate**, **Integration-First Gate**, plus a **[Project-Specific Gate]** per stated governing principle.

## Cross-Artifact Consistency (analyze)

If a spec artifact exists, check the plan against the spec, not just the plan against itself — the `analyze` phase from spec-kit, full checklists at Step 7 of `references/plan-template.md`. Three checks: **Coverage** (every user story, acceptance criterion, non-functional requirement, edge case, and verbatim constraint maps to a task or is explicitly deferred with a note), **Drift** (no scope creep, no contradiction, no silently resolved `[NEEDS CLARIFICATION]` marker), **Gates** (every constitution gate passes or carries a Complexity Tracking justification). Coverage gaps → add the task; drift → fix the plan. This catches the most common planning failure: an internally consistent plan that has drifted from its intent.

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

## Handoff to plan

Unattended (`orchestrator/references/unattended.md`): after saving the spec, **state the spec path and continue** — no "shall I proceed?" question. Say what runs next and keep going.

**Path A — subagent-driven (default):** "Spec saved at `<path>`. Continuing to the plan turn — it consumes this spec and produces a task breakdown with test cases; then `test-evals` writes those tests RED and `build` executes the tasks with per-task review at this work's tier (T_)."

**Path B — single CLI agent orchestrate-and-review:** for builds dispatched to a single external coding CLI (Cursor, Codex, Claude Code), the spec feeds a self-contained implementation brief the CLI reads end-to-end — the brief draws WHAT/WHY and constraints from the spec, but holds the task breakdown itself. "Spec saved at `<path>`. Continuing to write a self-contained implementation brief — the brief consumes this spec as the WHAT/WHY source."

Path A for multi-task per-task review gates; Path B for greenfield builds on a strong single-agent CLI where the orchestrate-and-review loop is the quality gate.

## Case tables (rules with state)

**Case tables for rules with state.** Any rule whose result depends on
history — corrections, retries, idempotence, rolling windows, caches, sync,
draft/post lifecycles, permission matrices, time boundaries — gets a case table
in the plan turn (`briefs/references/case-tables.md`): one row per case, with
the expected result at the public seam. Prose is not enough: each case it
leaves out becomes a review round later. S2/S3 always; S1 when such a rule is
in scope. The table is reviewed once, before the build.

### Execution Handoff

After saving the plan, state the plan path and continue without asking: **"Plan complete and saved at `<path>`. Continuing: `test-evals` writes the plan's test cases and runs them RED, then `build` dispatches a fresh subagent per task with T_ review."** Execution is the `build` stage: fresh `delegate_task` per task; per-task review per tier (T2: one combined reviewer; T3: spec compliance, then code quality); proceed only when the verdicts approve. For S1 plans, execute **inline** with checkpoints, without asking.

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

---

## Self-review checklist (the spec's unit tests)

Run this on the completed spec:

- [ ] Every user story has testable acceptance criteria ("returns 200 with JSON body containing field X", not "works correctly")
- [ ] No tech stack, library names, file paths, or architecture choices leaked in
- [ ] Every `[NEEDS CLARIFICATION]` marker is resolved or genuinely unresolvable until the user returns
- [ ] Non-functional requirements are measurable (target numbers, not "fast" / "secure")
- [ ] Edge cases cover: empty state, max/over-limit, invalid input, concurrency (if relevant), failure modes
- [ ] No speculative or "might need" features; every item traces to a user story or stated constraint
- [ ] Constraints copied verbatim from the user's words, not paraphrased into ambiguity

If any check fails, fix the spec before saving.
