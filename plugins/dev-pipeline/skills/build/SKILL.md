---
name: build
description: "Use when executing an implementation plan with subagents — delegate_task a fresh implementer per task that makes the plan's RED tests pass, per-task review sized by risk-derived tier (one combined reviewer at T2, spec-compliance then code-quality at T3), durable progress ledger, converge loop, per-task independent verification. Or whenever dispatching an implementer on a ticket: state the ticket title before starting, dependency injection for mockability, SDK-style interfaces, cadenced inner/outer test loop. The build stage of the dev-pipeline."
metadata:
  version: 2.1.0
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

Fix loops inside a task follow `review-commit/references/confirm-round-protocol.md`: only BLOCKING/MAJOR (Critical/Important) findings send the task back; Minor ones go to the ledger's deferred list.

**Tests:** `test-evals` has already written the plan's tests and run them RED. The implementer makes them GREEN and does not rewrite them (they are attested — `review-commit/scripts/attest_file.py`). It adds a test only for behavior the plan missed, under TDD, and lists it in its report.

**Why subagents:** You delegate tasks to specialized agents with isolated context. By precisely crafting their instructions and context, you keep them focused and preserve your own context for coordination work. They should not inherit your session history; you construct exactly what they need.

**Core principle:** Fresh subagent per task + review sized to the risk + orchestrator-run verification = high quality without paying T3 review cost on T2 work.

**Narration:** Between tool calls, narrate at most one short line. The todo list, progress ledger, report files, and tool results carry the durable record.

**Continuous execution:** Do not pause to check in with the human between tasks. Execute all tasks from the plan without stopping. The only reasons to stop are: `BLOCKED` status you cannot resolve, ambiguity that genuinely prevents progress, a plan contradiction requiring a `clarify` question, or all tasks complete. Do not ask "should I continue?" after each task.

## When to Use

Use this stage when:

- You have an implementation plan (from the `spec` stage or user requirements)
- Tasks are mostly independent, quality and spec compliance are important, and you want automated review between tasks — in this session, with fresh subagents

**Use another workflow when:** there is no spec/plan yet (`spec` stage first); tasks are tightly coupled and cannot be sequenced safely; the work should run in a separate parallel session.

## Before the loop: state the ticket title

Before starting on any ticket, fetch the ticket reference (the `.hermes/tickets/<feature-slug>/` file or plan task it points to), **restate the ticket title**, and ask now if it is ambiguous — never mid-build; ambiguity found at dispatch time is a `clarify` question, not a builder guess.

## The Process

### 1. Read and Parse Plan

Read the plan file. Extract ALL tasks with their full text, global constraints, dependencies, expected verification commands, and task boundaries upfront. Create a todo list:
Create the todo list from the extracted tasks — one item per task, tracked with the runtime's todo tool (the intent is in `references/per-task-workflow.md` §1; the §6 dispatch templates are there too).
**Key:** Read the plan ONCE. Extract everything. Do not make subagents read the whole plan file — provide the full task text directly or via a task brief file.

### 2. Pre-Flight Plan Review (summary)

Before dispatching Task 1, scan the plan once for contradictions and review traps — tasks contradicting each other or the plan's global constraints, plan-mandated requirements a review rubric would normally treat as defects, task ordering that makes later tasks impossible, and missing decisions that block the first task. If the scan is clean, proceed without comment; if not, batch the conflicts into one `clarify` question (each finding beside the exact plan text that mandates it). The full rule text lives in `references/per-task-workflow.md`.

### 3. Durable Progress Ledger

Conversation memory may not survive compaction. Track progress in a ledger file, not only in todos.

- Ledger path: `.hermes/sdd/progress.md` at the repository root.
- At skill start/resume, check whether the ledger exists. Tasks listed there as complete are DONE — do not re-dispatch them. Resume at the first task not marked complete.
- When a task's reviews come back clean and your independent verification passes, append one line to the ledger in the same bookkeeping step:
  `Task N: complete (commits <base7>..<head7>, spec PASS, quality APPROVED, verification <command/result>)`.
- Record minor deferred review findings in the ledger so the final integration reviewer can triage them.
- After compaction, trust the ledger and `git log` over memory.
- `git clean -fdx` can destroy this git-ignored scratch ledger; if that happens, recover from `git log`, review report files, and test output.

### 3b. Ledger curation rules (ported from GVS5H)

The ledger and shared report files coordinate work; they are not logs.

- **Curate, do not append.** When updating the ledger or a report after a fix round, rewrite the affected section to state the current truth (e.g. replace an issue line with its resolution) instead of stacking a new line under the old one. A stale "issue open" line next to a "fixed" line makes the next reviewer re-litigate settled findings.
- **Hard caps.** Keep `progress.md` under ~200 lines and each report file under ~8,000 characters. Near the cap, consolidate: collapse resolved findings into one summary line, drop superseded notes. Long files degrade the fresh-context readers (reviewers, converge) they exist for.
- **No-progress guard.** If two consecutive fix/review rounds on the same task produce the same finding or the same BLOCKED reason, stop the loop and escalate to the human (or split the task) instead of dispatching a third identical round. This mirrors GVS5H's guard that stops the manager re-issuing the task it just handed out.

### 4. File handoffs

Everything pasted into a dispatch prompt — and everything a subagent prints back — stays resident in the orchestrator context. File handoffs (briefs, reports, review-input diffs) keep bulky artifacts on disk. The full scratch layout, brief/report/review-input contracts, and the shared context-budget rules (read-depth tiers, degradation model) live in `references/context-discipline.md` — the single home for this doctrine, shared with the `context-engineering` skill.

### 5. Model selection (summary)

Use the least powerful model that can reliably handle each role; the full rules (tiering by task shape, turn count beats token price, and the negative result that fresh-subagent orchestration can hurt) are kept verbatim in `references/per-task-workflow.md`. Model pins live only in `orchestrator/references/lanes.md`; benchmarks in `model-routing` (`references/model-benchmarks.md` here is a pointer).

## Per-task workflow (skeleton)

For EACH task: record the base commit → dispatch the implementer (task brief + report contract) → handle the status (`DONE` / `DONE_WITH_CONCERNS` / `NEEDS_CONTEXT` / `BLOCKED`; never force the same retry without changing context, model, scope, or plan resolution) → per-task review at the tier's depth (T2: one combined reviewer, spec verdict then quality verdict; T3: spec-compliance reviewer, then code-quality reviewer only after spec is PASS; resolve "⚠️ Cannot Verify" items yourself) → independently verify, then mark complete in the ledger. A task whose review keeps returning Critical/Important findings follows the confirm-round stop conditions (`review-commit/references/confirm-round-protocol.md`) — budget per-task fix rounds at the tier's confirm budget (T2: 2, T3: 3, `orchestrator/references/size-tiers.md`); when the budget is spent, escalate or split the task. Dispatch templates, report contracts, reviewer-prompt rules, the "If Subagent …" handling playbook, and the worked example are verbatim in `references/per-task-workflow.md`.

### Verify and Commit

This is the `review-commit` stage's **Step C — Commit/deploy gate**, not a
step of this stage's per-task loop: never push without a review pass and
never deploy live before the three-reviewer gate (see the review-commit
stage). The orchestrator's independent verification above (run the test
command, start the service, inspect the output) is the input that gate
consumes; the full-suite run and final commit happen there.

## Build doctrine (implementation rules)

- **Coding principles** — every implementer dispatch pastes the builder block from `orchestrator/references/coding-principles.md` verbatim: state assumptions or report `NEEDS_CONTEXT`, minimum code, every changed line traces to the task, mention unrelated dead code instead of deleting it. The builder reads only its brief, so the block has to be in it.
- **Dependency injection for mockability** — pass external dependencies in as arguments; never construct them from the environment inside the unit. A class that builds its own HTTP client or reads its own config at construction cannot be tested at a seam without mocks outside a boundary.
- **SDK-style interfaces over generic fetchers** — one named function per external operation (`create_issue()`, not `fetch("post", "/issues")`). Named SDK surfaces are greppable, mockable, and pinned by tests at one seam.
- **Cadenced inner/outer loop** — during work, run the typecheck and the single test file for the behavior under construction; run the full suite once at the end, before commit. Do not run the full suite per loop, and do not end a ticket with only the inner loop green.
- **Tests come from `test-evals`, already RED.** Implementer dispatches name the RED tests the task must turn GREEN (paths + test names) and say: don't edit those tests; implement minimally; keep REFACTOR inside the cycle and scoped to code the task wrote or changed; run the named tests to GREEN. If a named test looks wrong, report `NEEDS_CONTEXT` instead of changing it. New behavior the plan missed (a bug found mid-build) gets its own failing-first test, listed in the report. If no RED tests exist for a task (T0, or test-evals skipped), the implementer writes the failing test first under TDD — and the report says so.

## Adjacent work in this stage

- `references/spike.md` — throwaway feasibility experiments before a build; VALIDATED spikes are discarded and re-implemented with TDD
- `references/simplify-code.md` — parallel 3-agent cleanup (reuse / quality / efficiency), user-asked only; the review gate before commit is the review-commit stage's job
- `references/cross-project-quality-patterns.md` — recurring DRY / architectural / security patterns, applied as a checklist when writing or reviewing code
- `references/implementation-hygiene.md` — verify requested command surfaces (not just canonical files), verify known bugs before fixing, batch read → batch fix
- `references/gates-taxonomy.md` / `references/ledger-orchestration-adaptation.md` — gate vocabulary (Pre-flight / Revision / Escalation / Abort) and GVS5H ledger-port notes
- **Unauthenticated coding CLIs:** if a local coding CLI fails auth repeatedly, stop retrying — switch per the `cli-auth-fallback` skill (the single auth authority)

## Model pins and benchmarks

Model pins live only in `orchestrator/references/lanes.md`; the benchmark table's single home is `model-routing/references/subagent-model-benchmarks.md` (this skill's `references/model-benchmarks.md` is a pointer).

## Red Flags — Never Do These

Compliance checklist. Each flag's governing rule lives in the section shown — that section is the
single source of truth; this list exists so violations are checkable at a glance.

- Start implementation without a plan → §1
- Start implementation on `main`/`master` without explicit user consent
- Skip the pre-flight contradiction scan → §2
- Skip the tier's per-task review (T2 combined reviewer; T3 spec compliance AND code quality) → Overview, §6 Steps 3/5
- Accept a review report missing either verdict (spec or quality) → §6 report contracts
- Run T3 per-task review on T2 work without saying why → Overview
- Let an implementer edit the RED tests from `test-evals` → Build doctrine
- Proceed with unfixed Critical/Important issues → §6
- Dispatch multiple implementation subagents in parallel for tasks that touch the same files
- Make a subagent read the whole plan file (provide the task brief or full task text instead) → §1
- Skip scene-setting context → §6 Step 1
- Ignore subagent questions → Handling Issues
- Accept "close enough" on spec compliance → §6 Step 3
- Skip review loops (reviewer found issues → implementer fixes → review again) → Handling Issues
- Let implementer self-review replace actual review → §7 (self-review shares blind spots)
- Start code quality review before spec compliance is PASS → §6 (wrong order)
- Move to next task while either review has open Critical/Important issues → §6
- Tell a reviewer what not to flag, or pre-rate a finding's severity → §7 (pre-judging biases the reviewer)
- Dispatch a task reviewer without a task diff/review input file → §7
- Paste large diffs, reports, or accumulated history into dispatch prompts → §4 (use file handoffs)
- Re-dispatch a task the progress ledger already marks complete → §3
- Treat review reports as final proof without orchestrator-run verification → Final verification rule
- Skip the converge loop at S2/S3 → §9 (final review passing ≠ spec intent satisfied end-to-end)
- Exceed the complexity band's converge cap (S2: 2, S3: 3) without escalating to the human → §9
- Accept a reviewer verdict without evidence → §6 ("APPROVED" without a written report file is a claim)
- Launch a bounded CLI arm job with `&` inside a foreground call — the subshell is killed when the call returns; arm jobs must run as Hermes background jobs with notify enabled
- Share one log path between concurrent dispatches — each dispatch writes its OWN absolute log path
- Run a gate claude review without route isolation (clean config dir without the settings `env` block) — `--model` resolves against the wrong provider

## Final verification rule

**Review reports are not proof of completion.** Before marking a task done, validate achievement with an independent, re-runnable artifact:
- run the test command
- start the service and inspect its output
- query an HTTP endpoint and inspect status/body/headers
- confirm the expected file or DB state on disk

Reviewers document findings; the orchestrator verifies outcomes. Final acceptance must use real execution, not a narrative report.

## Verification

After completing all tasks in the plan, confirm:

- [ ] Every task has the tier's review on record: a spec verdict (PASS) and a quality verdict (APPROVED) — one report at T2, two at T3
- [ ] Every Critical and Important finding was fixed and re-reviewed (Minor ones deferred in the ledger)
- [ ] The plan's RED tests are GREEN and unmodified (attestation verified)
- [ ] Orchestrator ran independent verification (not trusting subagent self-report) for each task
- [ ] Progress ledger (.hermes/sdd/progress.md) has a completion line for every task with commit range + review verdicts
- [ ] Final integration reviewer dispatched with branch-wide diff/review package
- [ ] S2/S3: converge loop ran at least once (CONVERGED or gaps executed), within the complexity band's cap without human escalation
- [ ] Full test suite green
- [ ] No deferred Minor findings left untriaged
- [ ] Final commit made

## References

- `references/per-task-workflow.md` — pre-flight scan, model selection rules, Steps 1-6 dispatch templates, reviewer-prompt construction, final review, handling issues, task granularity, worked example
- `references/converge-loop.md` — the converge loop (spec ↔ code reconciliation) after the final review
- `references/context-discipline.md` — context budget discipline (four-tier degradation model) + file handoffs; the shared home for this doctrine
- `references/gates-taxonomy.md` — Pre-flight / Revision / Escalation / Abort gate vocabulary
- `references/ledger-orchestration-adaptation.md` — adaptation notes for the GVS5H ledger-based zero-shot orchestration port
- `references/model-benchmarks.md` — pointer only; the benchmark table's sole copy lives in model-routing/references/subagent-model-benchmarks.md
- `references/spike.md` — throwaway feasibility experiments
- `references/simplify-code.md` — parallel 3-agent cleanup
- `references/cross-project-quality-patterns.md` — recurring DRY/architectural/security patterns
- `references/implementation-hygiene.md` — command-surface verification, known-bug verification, batch read/fix

## Where it fits

The build stage follows `test-evals` and hands to `review-commit` (the
confirm-round protocol lives there). `harness-engineering` remains a
standalone skill outside the pipeline (pointer only); `context-engineering`
stays outside too and links to `references/context-discipline.md`.
