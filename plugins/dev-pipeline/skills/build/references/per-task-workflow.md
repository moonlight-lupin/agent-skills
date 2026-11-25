# Per-Task Workflow

The dispatch workflow for building a plan task-by-task with `delegate_task`
subagents, two-stage review, and independent verification. Pre-flight scan,
full model-selection rules, dispatch templates, prompt-construction rules,
handling issues, efficiency notes, and the worked example live here; the
build stage's SKILL.md carries the compact skeleton.

## Contents

- 1. Read and Parse Plan (todo-list intent)
- 2. Pre-Flight Plan Review
- 5. Model Selection
- 6. Per-Task Workflow (Steps 1-6, with dispatch templates)
- 7. Constructing Reviewer Prompts
- 8. Final Review
- If Subagent Asks Questions / If Reviewer Finds Issues / If Reviewer Reports ⚠️ Cannot Verify / If Subagent Fails a Task
- Parallel Subagent Dispatch with Parent Integration
- If Local Coding CLIs Are Unauthenticated / Subagent Entry Point Naming / Subagent Argument Naming Diverges from Spec
- Efficiency Notes
- Task Granularity
- Example Workflow

> §1's plan-reading step creates the todo list: read the plan once, then
> track ONE todo item per task with the runtime's todo tool — mark it
> in_progress when the task dispatches and completed after the verdicts plus
> independent verification pass. The todo list is ephemeral scratch; the
> progress ledger (`.hermes/sdd/progress.md`) is the durable record.

### 2. Pre-Flight Plan Review

Before dispatching Task 1, scan the plan once for contradictions and review traps:

- tasks that contradict each other
- task text that contradicts the plan's global constraints
- requirements the plan explicitly mandates but the review rubric would normally treat as a defect (for example: a test that asserts nothing, intentional duplication, a deliberately hardcoded compatibility shim)
- task ordering that will make later tasks impossible or force rework
- missing decisions that genuinely block the first task

If the scan is clean, proceed without comment. If you find conflicts, batch them into one `clarify` question before execution begins. Put each finding beside the exact plan text that mandates it and ask which governs. Do not interrupt once per discovery mid-plan; the review loop remains the net for conflicts that only emerge during implementation.

### 5. Model Selection

Use the least powerful model that can reliably handle each role. When the dispatch tool supports explicit model/provider selection, specify it; otherwise state the intended tier in the prompt and choose the available subagent route that best matches it.

**Implementation tasks:**
- Complete spec, touches 1–2 files, mostly transcription or mechanical fix → cheap/fast model
- Multiple files, integration concerns, or debugging → standard model
- Design judgment, broad codebase understanding, or architecture → strongest available model

**Review tasks:** choose the model by diff size, complexity, and risk.
- Small mechanical diff → standard is usually enough
- Security, concurrency, migrations, cross-cutting behavior, or subtle API compatibility → strong model
- Final whole-branch review → strongest available model

**Turn count beats token price.** The cheapest model can take 2–3× more turns on multi-step work. Use a mid-tier model as the floor for reviewers and for implementers working from prose descriptions. Use the cheapest tier only when the plan text is complete enough that implementation is transcription plus testing, or for isolated single-file fixes.

**Orchestration can hurt (negative result, GVS5H).** Fresh-subagent delegation is not a universal win. In the GVS5H benchmark one model regressed under orchestration: transcripts showed it discarding correct approaches during deliberation and letting unverified worker output overwrite correct work. Watch for the failure mode: if an implementer's post-fix output is worse than its first attempt, stop adding review rounds — diff the attempts, keep the better one, and consider running the task single-context instead.

### 6. Per-Task Workflow

For EACH task in the plan:

#### Step 1: Record Base and Dispatch Implementer Subagent

Record the current commit before dispatch so reviews can use the exact task diff.

Use `delegate_task` with complete context and Hermes toolsets:

```python
delegate_task(
    goal="Implement Task 1: Create User model with email and password_hash fields",
    context="""
    READ FIRST:
    - .hermes/sdd/task-1-brief.md (authoritative task requirements)

    REPORT CONTRACT:
    - Write full report to .hermes/sdd/task-1-report.md
    - Return only: STATUS, one-line test summary, concerns (do NOT commit — the orchestrator commits after review)
    - STATUS must be one of: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, BLOCKED
    - The full report lists: assumptions made, any unrelated dead code noticed (not deleted)

    {{BUILDER_BLOCK}}

    RED TESTS (written by test-evals — do NOT edit them):
    - tests/models/test_user.py::test_create_user_hashes_password
    - tests/models/test_user.py::test_verify_rejects_wrong_password
    1. Run: pytest tests/models/test_user.py -v (confirm they FAIL for the stated reason)
    2. Write minimal implementation; refactor only code this task wrote or changed, while green
    3. Run: pytest tests/models/test_user.py -v (verify PASS)
    4. Run: pytest tests/ -q (verify no regressions)
    5. If a named test looks wrong: STOP and report NEEDS_CONTEXT — don't change it.
       New behavior the plan missed gets its own failing-first test; list it in the report.
    6. Do NOT commit — the orchestrator commits after verification.

    PROJECT CONTEXT:
    - Python 3.11, Flask app in src/app.py
    - Existing models in src/models/
    - Tests use pytest, run from project root
    - bcrypt already in requirements.txt
    """,
    toolsets=['terminal', 'file']
)
```

If you are not using file handoffs for a small task, include the full task text directly in the context. Never make the subagent infer requirements from the entire plan.

#### Step 2: Handle Implementer Status

Implementer subagents report one of four statuses. Handle each explicitly:

**DONE:** Create/update the review input file with the task brief, implementer report, commit range, diff stat, and full task diff. Then dispatch the spec-compliance reviewer.

**DONE_WITH_CONCERNS:** Read the concerns before review. If concerns are about correctness, scope, or failed/partial verification, address them before review. If they are non-blocking observations (for example, “this file is getting large”), note them in the ledger and proceed to review.

**NEEDS_CONTEXT:** Provide the missing context and re-dispatch. If the missing context should have been in the brief, update the brief/report files so later reviewers see the resolution.

**BLOCKED:** Assess the blocker:
1. If it is a context problem, provide more context and re-dispatch.
2. If it requires more reasoning, re-dispatch with a stronger model.
3. If the task is too large, split it into smaller pieces and update the ledger/todos.
4. If the plan itself is wrong or ambiguous, ask one batched `clarify` question with the plan text and proposed resolution.

**Never** ignore an escalation or force the same retry without changing context, model, scope, or plan resolution.

#### Step 3: Dispatch Spec Compliance Reviewer

After the implementer completes and you have a review input file, verify against the original spec. This is a separate review gate before code quality.

Tier depth (`orchestrator/references/size-tiers.md`): at **T3** run this as one reviewer, then code quality as a second dispatch (Step 5 — the template below is the T3 shape). At **T2** merge both into ONE reviewer dispatch that returns the spec verdict first and the code-quality verdict second — do not dispatch twice at T2; combined goal text for T2: `goal="Review Task 1: verdict on spec compliance FIRST, then code quality"` with the same review-input context. At **T1** there is no per-task reviewer dispatch (Step A covers it).

```python
delegate_task(
    goal="Review Task 1 for spec compliance only",
    context="""
    REVIEW INPUT:
    - Read .hermes/sdd/task-1-review-input.md first. It contains the task brief,
      implementer report path, commit range, and task diff.

    ORIGINAL TASK SPEC:
    - Create src/models/user.py with User class
    - Fields: email (str), password_hash (str)
    - Use bcrypt for password hashing
    - Include __repr__

    CHECK:
    - [ ] All requirements from spec implemented?
    - [ ] File paths match spec?
    - [ ] Function signatures match spec?
    - [ ] Behavior matches expected?
    - [ ] Nothing extra added (no scope creep)?
    - [ ] Any requirement cannot be verified from this diff? Mark it ⚠️.

    OUTPUT: PASS or list of specific spec gaps to fix. Write full report to
    .hermes/sdd/task-1-spec-review.md.
    """,
    toolsets=['file']
)
```

**If spec issues found:** dispatch a fix subagent, update the diff/review input, and re-run spec review. Continue only when spec-compliant.

#### Step 4: Handle Reviewer ⚠️ Items

A reviewer may report “⚠️ Cannot verify from diff” items — requirements that live in unchanged code, external state, or future tasks. These do not automatically block the rest of review, but you must resolve each before marking the task complete.

For each ⚠️ item:
- inspect the relevant file/state yourself with tools
- if satisfied, record the evidence in the ledger or task report
- if it is a real gap, treat it as failed spec review: send it back to the implementer and re-review
- if it conflicts with plan text, ask the human to choose which governs

#### Step 5: Dispatch Code Quality Reviewer

After spec compliance passes (T3: second dispatch; at T2 this is part of ONE combined dispatch — see the tier note at Step 3, and the combined goal text above). The quality verdict includes the two change-discipline checks from Step A's baseline — **Overbuilt** and **Drive-by Change** (`orchestrator/references/coding-principles.md`):

```python
delegate_task(
    goal="Review Task 1 code quality after spec compliance passed",
    context="""
    REVIEW INPUT:
    - Read .hermes/sdd/task-1-review-input.md first. It contains the task brief,
      implementer report path, commit range, and task diff.
    - Spec compliance review passed: .hermes/sdd/task-1-spec-review.md

    FILES TO REVIEW:
    - src/models/user.py
    - tests/models/test_user.py

    CHECK:
    - [ ] Follows project conventions and style?
    - [ ] Proper error handling?
    - [ ] Clear variable/function names?
    - [ ] Adequate test coverage?
    - [ ] No obvious bugs or missed edge cases?
    - [ ] No security issues?

    OUTPUT FORMAT:
    - Critical Issues: [must fix before proceeding]
    - Important Issues: [should fix]
    - Minor Issues: [record but do not block unless risk demands]
    - ⚠️ Cannot Verify: [items requiring orchestrator verification]
    - Verdict: APPROVED or REQUEST_CHANGES
    Write full report to .hermes/sdd/task-1-quality-review.md.
    """,
    toolsets=['file']
)
```

**If quality issues found:** dispatch a fix subagent for Critical and Important issues, update review inputs, and re-review. Record Minor issues in the ledger for final triage. Continue only when approved.

#### Step 6: Final Task Verification and Mark Complete

Before marking complete, the orchestrator must independently verify the task with real execution or observable state. Review reports are not proof.

```python
# Mark the task's todo item completed as part of the same bookkeeping step
# (runtime todo tool: one item per task, completed after verdicts + verification)
```

Append the completion line to `.hermes/sdd/progress.md` with the commit range, review verdicts, and verification command/result.

### 7. Constructing Reviewer Prompts

Per-task reviews are task-scoped gates. The broad cross-task review happens at the final integration review. When constructing reviewer prompts:

- Do not add open-ended directives like “check all uses” or “run race tests if useful” without a concrete, task-specific reason.
- Do not ask a reviewer to re-run tests the implementer already ran on the same code unless the task risk requires independent execution; the implementer's report carries test evidence, and the orchestrator performs final verification.
- Do not pre-judge findings for the reviewer. Never instruct a reviewer to ignore or not flag a specific issue. If you believe a finding would be a false positive, let the reviewer raise it and adjudicate it in the review loop. If your prompt contains “do not flag,” “don't treat X as a defect,” “at most Minor,” or “the plan chose,” stop: you are pre-judging.
- Copy binding requirements verbatim from the plan's global constraints or spec: exact values, exact formats, file paths, signatures, and stated relationships between components. The constraints block is for what THIS project demands.
- Pass reviewers a diff/review input file path, not a pasted diff. Include commit list, stat summary, and full diff with context in that file. Use the base commit recorded before the implementer ran; never rely on `HEAD~1` for multi-commit tasks.
- A dispatch prompt describes one task, not the session history. Do not paste accumulated prior-task summaries into later dispatches. Provide only the task, touched interfaces, needed decisions, and global constraints.
- Dispatch fix subagents for Critical and Important findings. Record Minor findings in the progress ledger and point the final integration review at that list.
- A finding labeled plan-mandated — or any finding that conflicts with plan text — is the human's decision. Present the finding and plan text, ask which governs, and do not dispatch a contradictory fix without confirmation.
- Every fix dispatch carries the implementer contract: re-run the covering tests, name the test files/commands, and report output. Before re-dispatching the reviewer, confirm the fix report contains the covering tests, commands, and output.
- If the final integration review returns findings, dispatch ONE fix subagent with the complete findings list rather than one fixer per finding.

### 8. Final Review

After ALL tasks are complete, dispatch a final integration reviewer. Use the requesting-code-review skill's review dimensions and include pointers to the ledger, deferred Minor findings, and a branch-wide diff/review package file.

```python
delegate_task(
    goal="Review the entire implementation for consistency and integration issues",
    context="""
    All tasks from the plan are complete. Review the full implementation:
    - Read .hermes/sdd/progress.md for completed tasks and deferred minor findings.
    - Read .hermes/sdd/final-review-input.md for branch diff/stat/commit summary.
    - Do all components work together?
    - Any inconsistencies between tasks?
    - Are deferred Minor findings actually safe to defer?
    - Ready for merge?
    """,
    toolsets=['terminal', 'file']
)
```

### Parallel Subagent Dispatch with Parent Integration

When a release requires both new file creation and integration into
existing files, dispatch 2 subagents in parallel for the new files while
the parent handles integration work:

1. **Dispatch 2 subagents simultaneously** (e.g., one for a CLI script,
   one for a shared actions module)
2. **Parent does integration work while subagents run**: version bumps,
   action_risk.py updates, webhook_events routing, briefing integration,
   docs, test file creation
3. **When subagents complete**: compile their output, run tests, fix
   test-level issues (argument names, entry point names)

This pattern keeps the parent productive during subagent wait time and
typically completes a full release in ~3-5 minutes total.

### If Subagent Asks Questions

- Answer clearly and completely
- Provide additional context if needed
- Update the task brief/report if the answer affects requirements
- Do not rush them into implementation

### If Reviewer Finds Issues

- Implementer subagent (or a new fix subagent) fixes Critical/Important issues
- Fix subagent re-runs covering tests and reports command/output
- Update the review input/diff file
- Reviewer reviews again
- Repeat until approved
- Do not skip the re-review

### If Reviewer Reports ⚠️ Cannot Verify

- Resolve it yourself using tools before marking the task complete
- Record evidence or send back for a fix
- If it is plan-mandated but questionable, ask the human which governs

### If Subagent Fails a Task

- Dispatch a new fix/retry subagent with specific instructions about what went wrong
- Change something material: context, model tier, task size, or clarified requirements
- Do not try to fix manually in the controller session unless the user explicitly wants that trade-off

### If Local Coding CLIs Are Unauthenticated

If a local coding CLI returns auth/credential errors consistently after setup attempts, stop retrying that path and switch to Hermes built-in `delegate_task`. Repeating an authenticated CLI failure is rarely productive; `delegate_task` preserves execution while avoiding duplicate auth dead-ends.

The **Subagent Output Size Varies by Model** and the **Grok-4.5 vs GPT-5.5 for Coding Subagents** benchmark live in `model-benchmarks.md` (pending move into model-routing).

### Subagent Entry Point Naming

Subagents may name the CLI entry point `main()` or `_main()`. Check the
actual function name before writing tests that call it directly. This is
not predictable from the dispatch prompt — the subagent chooses the name.
A quick `grep "^def main\|^def _main" <file>` saves debugging time.

### Subagent Argument Naming Diverges from Spec

Subagents may choose different CLI argument names than the spec suggests.
For example, a spec saying `--deal-id` may be implemented as `--id`, or
`--text` may become `--note`. Always check the actual parser before
writing tests that call specific arguments:

```bash
python3 -c "
import sys; sys.path.insert(0, 'skills/X/scripts')
import module
parser = module.build_parser()
try:
    args = parser.parse_args(['--config', '/tmp/test.yaml', 'subcommand', '--expected-flag', 'val'])
    print('args:', vars(args))
except SystemExit:
    print('parse failed — check actual argument names')
"
```

This saves 5-10 minutes of trial-and-error test fixes when the subagent's
naming choices don't match the test's assumptions.

## Efficiency Notes

**Why fresh subagent per task:**
- Prevents context pollution from accumulated state
- Each subagent gets clean, focused context
- No confusion from prior tasks' code or reasoning

**Why two-stage review:**
- Spec review catches under/over-building early
- Quality review ensures the implementation is well-built
- Catches issues before they compound across tasks

**Why file handoffs:**
- Large diffs and reports do not stay in the orchestrator context
- Reviewers can read one purpose-built file instead of reconstructing state
- The ledger survives compaction and prevents duplicate dispatches

**Cost trade-off:**
- More subagent invocations (implementer + 2 reviewers per task)
- More orchestration prep (briefs, reports, review input files)
- But catches issues early and avoids expensive final-review fix waves

## Task Granularity

**Each task = 2–5 minutes of focused work when implemented by a subagent.**

**Too big:**
- "Implement user authentication system"

**Right size:**
- "Create User model with email and password fields"
- "Add password hashing function"
- "Create login endpoint"
- "Add JWT token generation"
- "Create registration endpoint"

If a task returns `BLOCKED` because it is too broad, split it and update the todo list plus `.hermes/sdd/progress.md` before continuing.

## Example Workflow

```
[Read plan: docs/plans/auth-feature.md]
[Pre-flight scan: no contradictions]
[Create todo list with 5 tasks]
[Create/check .hermes/sdd/progress.md]

--- Task 1: Create User model ---
[Write .hermes/sdd/task-1-brief.md]
[Record base commit]
[Dispatch implementer subagent with delegate_task]
  Implementer: "Should email be unique?"
  You: "Yes, email must be unique" [update task brief/report]
  Implementer: STATUS DONE. Implemented, 3/3 tests passing, committed.

[Write .hermes/sdd/task-1-review-input.md with commit range + diff]
[Dispatch spec reviewer]
  Spec reviewer: ✅ PASS — all requirements met

[Dispatch quality reviewer]
  Quality reviewer: ✅ APPROVED — clean code, good tests

[Run verification command]
[Mark Task 1 complete in todo + .hermes/sdd/progress.md]

--- Task 2: Password hashing ---
[Dispatch implementer subagent]
  Implementer: STATUS DONE_WITH_CONCERNS — unsure whether min length belongs here.
  You: Concern affects scope; check task brief/global constraints before review.

[Dispatch spec reviewer]
  Spec reviewer: ❌ Missing: password strength validation (spec says "min 8 chars")

[Dispatch fix subagent with all findings]
  Fixer: Added validation, 7/7 tests passing.

[Dispatch spec reviewer again]
  Spec reviewer: ✅ PASS

[Dispatch quality reviewer]
  Quality reviewer: Important: Magic number 8, extract to constant
  Fixer: Extracted MIN_PASSWORD_LENGTH constant, tests passing
  Quality reviewer: ✅ APPROVED

[Run verification command]
[Mark Task 2 complete]

... (continue for all tasks without asking whether to continue)

[After all tasks: dispatch final integration reviewer with final-review-input.md]
[Run full test suite: all passing]

--- Converge ---
[Dispatch converge reviewer: assess codebase against spec + plan]
  Converge iteration 1: 2 gaps found (T046: missing spec edge case, T047: NFR not verified end-to-end)
[Execute T046, T047 through per-task workflow: implementer → spec review → quality review → verify]
[Dispatch converge reviewer again]
  Converge iteration 2: CONVERGED
[Proceed to final verify + commit]
[Done!]
```

## Integration with Other Skills

### With the `spec` stage

This stage EXECUTES plans from the `spec` stage's plan turn:
1. User requirements → `spec` (spec turn, plan turn) → implementation plan
2. Plan → `test-evals` → RED tests for each task's test cases
3. RED tests + plan → `build` → working code

### With `test-evals`

`test-evals` writes each task's tests and runs them RED before dispatch. Every
implementer context names those tests and says not to edit them (template
above). The implementer turns them GREEN with minimal code, refactors while
green, and writes a failing-first test only for behavior the plan missed.

### With the final review

Per-task review follows the tier (`build/SKILL.md` Overview). For the final
integration review, use `test-evals/references/requesting-code-review.md`'s
review dimensions.

### With systematic-debugging

If a subagent encounters bugs during implementation:
1. Follow systematic-debugging process
2. Find root cause before fixing
3. Write regression test
4. Resume implementation

## Further reading (load when relevant)

When the orchestration involves significant context usage, long review loops, or complex validation checkpoints, load these references for the specific discipline:

- **`references/context-discipline.md`** — Four-tier context degradation model (PEAK / GOOD / DEGRADING / POOR), read-depth rules that scale with context window size, and early warning signs of silent degradation. Load when a run will clearly consume significant context (multi-phase plans, many subagents, large artifacts).
- **`references/gates-taxonomy.md`** — The four canonical gate types (Pre-flight, Revision, Escalation, Abort) with behavior, recovery, and examples. Load when designing or reviewing any workflow that has validation checkpoints — use the vocabulary explicitly so each gate has defined entry, failure behavior, and resumption rules.

Both references adapted from gsd-build/get-shit-done (MIT © 2025 Lex Christopherson). Original repo [gsd-build/get-shit-done](https://github.com/gsd-build/get-shit-done) (archived); now at [open-gsd/gsd-core](https://github.com/open-gsd/gsd-core).

Other references (load when relevant):
- **Unauthenticated coding CLIs** — fallback order and cut-over rules live in the `cli-auth-fallback` skill (outside skill; extends "If Local Coding CLIs Are Unauthenticated" in §Handling Issues).
- **`references/ledger-orchestration-adaptation.md`** — adaptation notes for the GVS5H ledger-based zero-shot self-orchestration port (which §3b Ledger curation rules came from).
