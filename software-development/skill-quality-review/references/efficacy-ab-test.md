# Efficacy A/B Testing for Skill Refactors

A refactor's structural checks (sizes, fences, dedupe) prove shape, not behavior. To answer
"did the refactor actually help the agent?", run a controlled A/B: same model, same scenario
prompts, same tools — the ONLY variable is the skill version. Controlled by the repo-adoption-review
side-by-side fairness rule.

## Contents

- Procedure (freeze arms, scenarios, dispatch, artifacts, scoring, before-arm lifecycle)
- Evaluation coverage (library metric; Check 19)
- Quick variant — used vs no-skill A/B

## Procedure

### 1. Freeze the arms

Copy each arm to a neutral test directory (e.g. `test-<skill>` and `test-<skill>-n`) via copytree.
The new arm is the current files. The before-arm must be reconstructed byte-exactly. Reconstruction
sources, in priority order:

1. The session's earlier `skill_view` spillover cache — a `skill_view` result over ~100KB persists
   to `/root/.hermes/cache/spillover/call_*.txt` as ONE JSON line; `json.load` it and take `content`.
2. Retired-content archives under the skill's `references/` — re-apply archived blocks at their
   recorded positions.
3. Inverse-patch from the current file (reverse each applied edit).

**Byte-exactness gate:** assert the reconstructed char count equals the known pre-edit count, then
verify structural parity (heading inventory, list-item counts, fence balance) before any testing.
Re-inserting archived blocks commonly double-prints their `##` heading — strip the heading from the
archive and print your own. A drifted before-arm invalidates the whole comparison.

Give the before-arm the same `references/` directory contents as the new arm, except the refactor's
own outputs — both arms must be able to resolve every pointer their SKILL.md carries, or pointer
failure gets blamed on the wrong variable.

### 2. Write scenarios and rubric BEFORE dispatching

Each scenario targets one thing the refactor changed — pointer firing, dedupe, noise rejection,
a new rule's recall. Use the rubric template (`templates/efficacy-rubric-template.md`): per scenario,
a verbatim prompt plus 2-3 checkable scoring points (a/b/c). Keep scenario prompts verbatim-identical
across arms; store them in one file the dispatches read from.

### 3. Dispatch one blind child per arm

- Build the dispatch prompt ONCE with a path placeholder; inject the arm's path per dispatch.
  Hand-typing the same prompt twice invites a typo that breaks input parity — that happened and
  cost a stop-and-redispatch cycle.
- Same `goal` text for both arms; the context differs ONLY in the directory path. State "blind"
  and forbid skill summarization — the deliverable is scenario answers only.
- `delegate_task` runs children up to `delegation.max_concurrent_children` (default 2). Dispatch
  in waves; queue the remaining arms rather than erroring on a 4-way dispatch.
- Stop-and-redispatch on prompt defects is fine (a stopped child's partial result still arrives —
  ignore it), but each correction wastes a cycle: reread the prompt before dispatching.

### 4. Artifacts before dispatch

Create every directory and file the child will read BEFORE dispatching. A child dispatched against
a missing path returns junk or wanders the filesystem. This bit once: a test dir was referenced in
a dispatch before it was created.

### 5. Score and report honestly

Score each cell 0-3 against the rubric; report per-scenario and aggregate. State the limits in the
deliverable: n=1 per cell is directional, not statistical; the probe measures single-turn rule
recall/compliance with the material, not end-to-end loop outcomes. If a scenario's rubric point is
untestable in one arm (the rule exists only in the new arm by design), mark it structural-by-design
rather than a behavioral fail.

### 6. Before-arm lifecycle

Keep the reconstructed before-arms under the test workspace (e.g. `old/` next to `new/`) until the
report is delivered — the user may ask to re-run a scenario. Delete after delivery; they duplicate
live skill content and will go stale.

## Evaluation coverage (library metric; Check 19)

The A/B procedure above measures one refactor. A skill library also needs a coverage metric, reported alongside review findings:

- **Evals per skill** — map the repo's eval/scenario files to skills and report the count per skill. Flag skills with zero scenarios (Anthropic suggests ≥3 scenarios per skill as a floor).
- **Model scope** — record which models the plugin targets (from README / plugin.json) and run evals only on those. A judgement-heavy skill excluded from smaller models (an owner's scope call on pere-toolkit, 6 Oct 2026: Haiku out of scope) must never be probed with them — a Haiku run there is noise, not signal. Record the scope decision and rationale next to the eval plan so later runs don't re-litigate it.

Report format: one line per skill — `skill | scenarios=N | models=[...]` — plus the flagged zero-scenario list. A coverage gap is MINOR per skill, and a signal to schedule eval work, not to block a release on its own.

## Quick variant — used vs no-skill A/B (default when asked "is the skill helping?")

The full byte-exact before-arm protocol is for refactor comparisons (v1 vs v2). A simpler and
usually more useful question: does the skill change the outcome at all? Run the task twice on
fresh subagents:

- **Arm A (with):** the live skill is available (normal dispatch).
- **Arm B (without):** the same goal and context, but the skill's content is withheld — do not
  load it, do not mention it.

Same goal text verbatim for both arms; only skill availability differs. Score three things:

1. **Output quality** — score against a fixed rubric (use `templates/efficacy-rubric-template.md`).
2. **Time** — wall-clock seconds per dispatch (children report duration; the delegation result carries it).
3. **Tokens/cost** — api_calls from the delegation result as the cheap proxy; read exact token counts
   from the child transcript log if needed.

No byte-exact reconstruction is needed: there is no before-arm, only a missing arm. This answers
"was the skill worth having", which is the effectiveness question behind most refactor asks — run
this variant FIRST, and escalate to the full byte-exact protocol only when comparing two versions
of the skill. Same honesty rules: n=1 per cell is directional; report the numbers even when the
skill loses.
