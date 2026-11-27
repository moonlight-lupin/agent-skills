---
name: build
description: "Use when executing an implementation plan with subagents — a fresh implementer per task making the plan's RED tests pass, risk-tiered per-task review, durable progress ledger, converge loop, per-task independent verification; or any implementer dispatch on a ticket. The build stage of the dev-pipeline. Unattended: continuous execution between tasks, stops only at important forks (implementation rules: build-doctrine.md)."
metadata:
  version: 2.3.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [build, subagents, delegation, implementation, two-stage-review, ledger, converge, dependency-injection, file-handoffs, model-selection]
    related_skills: [test-evals, spec, grill, review-commit, model-routing, cli-auth-fallback, context-engineering, harness-engineering, systematic-debugging, doubt-driven-development]
---

# Build

## Overview

Execute implementation plans by dispatching a fresh implementer subagent per task, reviewing each task at the depth its tier sets, followed by a final integration review.

**Per-task review by risk-derived tier** (`orchestrator/references/risk-routing.md`, compatibility: `size-tiers.md`):

| Tier | Per-task review |
|---|---|
| T1 | none — a single-task build goes straight to `review-commit` Step A |
| T2 | ONE reviewer dispatch per task, one report with two verdicts: spec compliance first (PASS/FAIL), then code quality (APPROVED/CHANGES) |
| T3 | two separate reviewers: spec compliance, then code quality only after spec is PASS |

**Tests:** the plan's tests are already RED (written by `test-evals`). The implementer makes them GREEN, does not rewrite them (attested), and adds a test only for behavior the plan missed, under TDD. Full fix-loop/RED-contract wording: `references/build-doctrine.md`.

**Continuous execution:** run between tasks without pausing (stage wording: `references/build-doctrine.md`; fork-stop single home: `orchestrator/references/unattended.md`). Stop only for unresolvable `BLOCKED`, a new important fork, a genuine ambiguity, a plan contradiction, or completion.

## When to Use

Use this stage when:

- An implementation plan exists (from `spec` or the user)
- Tasks are mostly independent; quality and spec compliance matter; automated per-task review is wanted

**Use another workflow when:** there is no spec/plan yet (`spec` stage first); tasks are tightly coupled and cannot be sequenced safely; the work should run in a separate parallel session.

## Before the loop: state the ticket title

Before starting a ticket, fetch its reference (`.hermes/tickets/<feature-slug>/` or the pointed plan task), **restate the title**, and resolve ambiguity now — a `clarify` question at dispatch, never a builder guess mid-build.

## Engineering evidence

Follow `../orchestrator/references/engineering-evidence.md` for deterministic checks. Discover capabilities with `dev_pipeline_discover` and diagnose with `dev_pipeline_doctor`. Use the existing lane resolver; install only approved capabilities via `dev_pipeline_setup`. Execute selected checks with `dev_pipeline_engineering_run`, retain evidence, and run `dev_pipeline_gate` on the final clean commit before push/tag/deploy. NOT_SHIP blocks this workflow. Missing tools are not passes. Existing risk-tier gates and acceptance tests still apply.

## The Process

### 1. Read and Parse Plan

Read the plan ONCE; extract ALL tasks with full text, constraints, dependencies, and verification commands upfront; todo-list one item per task. Detail: `references/per-task-workflow.md` §1. Extract everything. Do not make subagents read the whole plan file — provide the full task text directly or via a task brief file.

### 2. Pre-Flight Plan Review (summary)

Before Task 1, scan the plan once for contradictions and review traps; clean → proceed silently; findings → one batched `clarify` question, each beside the exact plan text that mandates it. Full rule: `references/per-task-workflow.md`.

### 3. Durable Progress Ledger

Ledger rules and curation caps are in `references/build-doctrine.md` § ledger (curate-don't-append, ~200-line cap, no-progress guard) and `references/ledger-orchestration-adaptation.md`. Path: `.hermes/sdd/progress.md`; resume at the first task not marked complete; after compaction trust the ledger and `git log` over memory.

### 4. File handoffs

Pasted dispatch text and subagent printbacks stay resident in your context; bulky artifacts go through file handoffs. Contracts + context-budget rules: `references/context-discipline.md` (single home, shared with `context-engineering`).

### 5. Model selection (summary)

Least powerful model that reliably handles each role; full rules in `references/per-task-workflow.md`. Pins live only in the lanes config; benchmark table in `model-routing/references/subagent-model-benchmarks.md`.

## Per-task workflow (skeleton)

For EACH task: record the base commit → dispatch the implementer (task brief + report contract) → handle the status (never force the same retry without changing context, model, scope, or plan) → per-task review at the tier's depth → independently verify → mark complete in the ledger. Fix-round budget at the tier's confirm budget (T2: 2, T3: 3 — `orchestrator/references/size-tiers.md`); budget spent → escalate or split. Full step text, dispatch templates, report contracts, reviewer-prompt rules, and the worked example: `references/per-task-workflow.md`.

### Verify and Commit

This is the `review-commit` stage's **Step C — Commit/deploy gate**, not a per-task step: never push without a review pass; never deploy live before the three-reviewer gate. The orchestrator's independent verification is the input that gate consumes.

## Red Flags — Never Do These

Full compliance checklist: `references/build-doctrine.md` § Red Flags. Top structural flags: no plan or main-branch start without consent; skipping the pre-flight scan or tier review; implementers editing RED tests; unfixed Critical/Important findings; parallel implementers on overlapping files; reviews trusted without orchestrator-run verification; converge loop skipped or over-cap.

## Final verification rule

**Review reports are not proof of completion.** Validate with an independent, re-runnable artifact: run the test command; start the service and inspect output; query an HTTP endpoint; confirm expected file/DB state. Full rule: `references/build-doctrine.md` § Final verification rule.

## Verification

After completing all tasks, confirm:

- [ ] Every task on record: spec PASS + quality APPROVED (one report at T2, two at T3); Critical/Important fixed and re-reviewed; Minor deferred and later triaged
- [ ] Plan's RED tests GREEN and unmodified (attested); orchestrator ran independent verification per task; full suite green
- [ ] Ledger has a completion line per task (commit range + verdicts); final integration reviewer ran with branch-wide package
- [ ] S2/S3 converge loop ran within its cap; final commit made

## References

- `references/build-doctrine.md` — implementation doctrine, adjacent-work pointers, model pins, full Red Flags checklist, fix-loop + RED-test contract, continuous execution
- `references/per-task-workflow.md` — todo intent, pre-flight full rule, dispatch templates, report contracts, reviewer prompts, worked example, model-selection rules
- `references/converge-loop.md` — converge loop; `references/context-discipline.md` — file handoffs + context budget (shared home)
- `references/ledger-orchestration-adaptation.md` — ledger rules; `references/gates-taxonomy.md` — gate vocabulary
- `references/{model-benchmarks.md,spike.md,simplify-code.md,cross-project-quality-patterns.md,implementation-hygiene.md}` — as named

## Where it fits

Follows `test-evals`; hands to `review-commit` (confirm-round protocol lives there). `harness-engineering` and `context-engineering` stay standalone (pointers only).
