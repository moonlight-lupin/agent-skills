---
name: spec
description: "Use when pinning intent before code — capture a spec (user stories, acceptance criteria, [NEEDS CLARIFICATION] markers), then plan the HOW (bite-sized tasks, blocking edges, gates) or slice tracer-bullet tickets. Triggers: 'write a spec', 'plan this', 'break this into tickets', 'slice this up', 'create tickets', 'what are the work units'. Unattended: after saving a spec or plan, state the path and continue — stops only at important forks."
metadata:
  version: 2.3.0
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

Do the job the user invoked — specifying only, or planning only. The `grill` stage hardens the plan first if important forks are unresolved (definition: `orchestrator/references/unattended.md`); the session does not proceed to a spec while known important forks are open.

**By complexity** (`orchestrator/references/risk-routing.md`): S0 skips this stage. S1 skips the spec turn — the plan header carries an assumptions line and 3-6 acceptance criteria written as `step → verify: check` (format in `orchestrator/references/coding-principles.md` § Plan format for S0/S1), and the plan is one task. S2/S3 run all turns. Review depth (the risk-derived T-tier) does not select spec turns: an S3/R1 change still gets the full spec with T1 review.

**Case tables for rules with state:** any rule depending on history (retries, idempotence, windows, caches, lifecycles, permissions, time boundaries) gets a case table in the plan turn — one row per case, expected result at the public seam. S2/S3 always; S1 when such a rule is in scope. Rules: `references/spec-doctrine.md` § Case tables.

**Test cases, not test code.** Each task names its test cases: behavior, seam + seam note, inputs, expected value and its source. `test-evals` writes the code RED; `build` makes it GREEN.

## When to Use

- "write a spec for X", "plan X", "plan mode", "break this into tickets", "slice this up", "create tickets", "what are the work units"; a non-trivial build pinning intent first; a spec exists and you need the HOW; one context window may lose the work; parallelizable work units with dependency edges are wanted

**Don't use for:**

- Plans so fuzzy that decisions hide in them — use the `grill` stage first
- Single-task features that fit in one plan task (plan directly; skip ticket slicing), research or exploration, post-hoc code review (use the pipeline's review stage)

## Spec turn — Core behavior

When the job is to define **what** to build and **why**, before any implementation plan:

- No implementation design, tech stack, architecture, libraries, data structures, code, file paths, or task breakdowns.
- Read-only repo inspection allowed; deliverable: a markdown spec under `.hermes/specs/`.

**Core principle:** A spec captures intent — what users need and why. Implementation is the job of the plan. Mixing them produces specs that break every time the tech stack changes and plans that bake in unexamined assumptions.

## Plan turn — Core behavior

When the job is a plan instead of execution:

- No implementation code; only the plan markdown file is edited; no mutating commands, commits, pushes, or external actions; read-only inspection allowed.
- Deliverable: a markdown plan under `.hermes/plans/`. Interaction: clear → write directly; no instruction → infer from context; underspecified → one clarifying question. After saving, state the path briefly.

**Core principle:** A good plan makes implementation obvious. If someone has to guess, the plan is incomplete. Write for an implementer with zero context: bite-sized tasks, DRY, YAGNI, TDD, frequent commits (full craft in `references/task-doctrine.md`).

### Output requirements

Concrete and actionable: goal; assumptions; approach; step-by-step; files changed; tests/validation; risks and open questions — exact paths, likely test targets, verification steps for code tasks.

Full header, Constitution Gates, and Task Structure templates plus the writing process (Steps 0–7): `references/plan-template.md`.

## Craft pointers

Load `references/spec-doctrine.md` when running a spec or plan turn: WHAT/WHY boundary table, seam-sketching rules (highest existing seam; one seam ideal; seam notes travel), Goldfish review, spec consumption, constitution gates, cross-artifact analyze, plan self-review checklist, no-placeholders rule, both handoff paths. Task doctrine: `references/task-doctrine.md`. Multiple independent subsystems → suggest one plan per subsystem, each producing working testable software.

## Task breakdown

Task decomposition doctrine (tracer-bullet tasks, blocking edges + frontier scheduling, expand-contract for wide refactors, fresh-context sizing, 2-5-minute granularity) is stated once in `references/task-doctrine.md`; apply it to breakdowns and to tickets.

## `[NEEDS CLARIFICATION]` markers — first-class ambiguity

**Never guess.** Mark unspecified things explicitly: `[NEEDS CLARIFICATION: <open question>]`. The plan forbids TBD in implementation; the spec **surfaces** ambiguity so it resolves before planning, never buried in a guess. Examples: `references/spec-doctrine.md` § markers.

## Review gates

Run the spec self-review checklist ("unit tests for the spec") and the clarify-phase procedure: `references/spec-doctrine.md` — fix before saving; never plan on top of resolvable ambiguity.

## Save location

Save with `write_file`, relative to the active working directory:

- Spec: `.hermes/specs/YYYY-MM-DD_HHMMSS-<slug>.md`
- Plan: `.hermes/plans/YYYY-MM-DD_HHMMSS-<slug>.md`
- Tickets: `.hermes/tickets/<feature-slug>/` (see `references/ticket-slicing.md`)

## Ticket slicing

Opt-in only, when the user already asked for tickets — never offered unprompted. Process, format, granularity, frontier scheduling: `references/ticket-slicing.md`.

## Verification

Before implementation: spec saved under `.hermes/specs/` with path stated, then continue (no approval request); surviving `[NEEDS CLARIFICATION]` markers resolved or carried as flagged assumptions. Plan: sequential bite-sized tasks, exact paths, interfaces, named test cases with expected value + source, production code where the HOW isn't obvious, exact commands, gates checked or justified.

**A good spec makes the intent unambiguous; a good plan makes the implementation obvious.** WHAT/WHY only; testable criteria; mark every ambiguity; no placeholders; gates justified.

## References

- `references/spec-doctrine.md` — WHAT/WHY table, seam rules, case tables, clarify phase, self-review checklist, goldfish, gates, analyze, no-placeholders, handoff paths
- `references/{plan-template,spec-template,task-doctrine,ticket-slicing,goldfish-spec-review}.md` — templates and dispatch contracts; `briefs/references/case-tables.md` — case-table format

**A good spec makes the intent unambiguous; a good plan makes the implementation obvious.**
