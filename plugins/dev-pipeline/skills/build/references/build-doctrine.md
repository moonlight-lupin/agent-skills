---
name: build-doctrine
description: "Build-stage implementation doctrine: stamped briefs, coding principles, dependency injection, cadenced loops, adjacent-work pointers, model pins, and the full Red Flags compliance list. Load when running any build task or reviewing build behavior."
metadata:
  version: 1.0.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [build, doctrine, red-flags]
---

# Build doctrine

Moved verbatim from SKILL.md in v0.6.0 (always-loaded text shrink). SKILL.md points here.

## Build doctrine (implementation rules)

- **Stamped briefs** — implementer and fix briefs are stamped with `briefs/scripts/stamp_brief.py` (SHAs, test results, the builder block) — never typed from memory.
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
- `references/gates-taxonomy.md` / `references/ledger-orchestration-adaptation.md` — gate vocabulary (Pre-flight / Revision / Escalation / Abort) and the ledger-orchestration port notes
- **Unauthenticated coding CLIs:** if a local coding CLI fails auth repeatedly, stop retrying — switch per the `cli-auth-fallback` skill (the single auth authority)

## Model pins and benchmarks

Model pins live only in the lanes config (`orchestrator/config/lanes.default.toml`, machine overrides merge on top); the benchmark table's single home is `model-routing/references/subagent-model-benchmarks.md` (this skill's `references/model-benchmarks.md` is a pointer). Role/rule text for lanes: `orchestrator/references/lanes.md`.

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

## Continuous execution (build-stage wording)

**Continuous execution:** Do not pause to check in with the human between tasks. Execute all tasks from the plan without stopping. The only reasons to stop are: `BLOCKED` status you cannot resolve, a **new important fork** that grill and the spec did not settle (`orchestrator/references/unattended.md` — stop with one numbered question and a recommended answer, then continue), ambiguity that genuinely prevents progress, a plan contradiction requiring a `clarify` question, or all tasks complete. Do not ask "should I continue?" after each task — a stage or task handoff is not an important fork.

## Review fix loops and RED-test contract (verbatim from Overview, v0.6.0)

Fix loops inside a task follow `review-commit/references/confirm-round-protocol.md`: only BLOCKING/MAJOR (Critical/Important) findings send the task back; Minor ones go to the ledger's deferred list.

**Tests:** `test-evals` has already written the plan's tests and run them RED. The implementer makes them GREEN and does not rewrite them (they are attested — `review-commit/scripts/attest_file.py`). It adds a test only for behavior the plan missed, under TDD, and lists it in its report.
