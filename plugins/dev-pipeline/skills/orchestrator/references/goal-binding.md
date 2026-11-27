# Goal binding — running the pipeline under /goal

The pipeline runs best **bound to a session goal** (`/goal` — the persistent per-session
Ralph loop: judge-checked after every turn, kicked until done, or paused/cleared).
The goal enforces "building according to objective"; the acceptance command becomes a
deterministic gate the judge cannot talk around. This file is the single home for the
contract templates, the gate rule, and the **derived** turn budget. The orchestrator
applies it at pipeline start; `build`/`review-commit` consume it mid-chain.

## The contract — set at pipeline start

Planned work: after the plan exists. The S0/S1 bug route has no plan — before setting
its goal, name the short task line and the **executable acceptance check** (the command
that proves the fix: the named test, the repro command, or the measured number); budget
from `base(S) + 2 per suspected root cause`, minimum 8. Then set the goal with inline
contract lines:

```
/goal <objective headline> — plan at .hermes/plans/<id>.md; route via skill dev-pipeline:orchestrator
  outcome: plan executed; ledger complete; review gate SHIP; branch pushed with
  draft PR; CI on the pushed head watched to completion, every failure fixed in the
  loop or named per ci-loop-and-pr-hygiene.md
  verify: cd <repo> && <the plan's acceptance command(s), verbatim>
  constraints: RED tests unmodified (attested); forbidden-identity grep = 0; no force-push to shared branches
  boundaries: <the plan's file set / repo path>
  stop_when: an important fork (one numbered question, then wait) — orchestrator/references/unattended.md
```

Aliases the parser accepts: `verify:` = `verification:` (also `evidence`, `proof`),
`done when:` = `outcome:`, `must not:`/`do not change:` = `constraints:`,
`scope:`/`files:` = `boundaries:`. A bare free-form goal still works — but every
pipeline goal carries at least `verify:`.

## The gate — deterministic, not judge-dependent

Add the acceptance command as a hard gate once the goal is set:

```
/goal gate add cd <repo> && <acceptance command>
```

Gates run at the turn boundary **before** the LLM judge; a failing gate short-circuits
judging and its output becomes the continuation prompt. Multiple gates allowed
(`/goal gate list|add|remove <N>|clear`); add the identity grep as a second gate when
the work touches the public repo. Harness errors fail open — the turn budget and the
review gate remain the backstops.

## Turn budget — derived, never the shipped default

The budget binds from `goals.max_turns` in `config.yaml` at goal-set time (shipped
fallback: 20 — a fallback, never the target). **Compute it from the plan and set
`hermes config set goals.max_turns <N>` before `/goal`**, in the session that will
hold the goal (the manager reads the value when the goal is set, so set the config
first, then the goal — mid-goal changes do not apply):

```
N ≈ base(S) + Σ per task (dispatch + review + one fix round) + loops
  base:        S0: 4   S1: 8   S2: 12   S3: 18
  per task:    S0: 2   S1: 2   S2: 3    S3: 4
  + 2 per anticipated important fork + 2 per planned converge cycle
```

State the computed number in the plan turn and in the goal's `constraints:` line
("budget N turns").

**Budget-exhaust semantics — two budgets, never confused.** The goal turn budget is a
MECHANICAL bound on the session (config-tied `goals.max_turns`); the confirm budget is a
REVIEW budget (tier-scaled, `review-commit/references/confirm-round-protocol.md`).
Exhausting the mechanical bound with clean progress and zero open BLOCKING/MAJOR
findings is a raise, not a stop: clear and re-set the SAME contract, remaining work as
the outcome, recomputed budget — no user question, the same move as resuming after
compaction. Exhaustion WITH an open BLOCKING/MAJOR finding, an unverified claim, or a
`BLOCKED` verdict is the important-fork stop — `orchestrator/references/unattended.md`
§ "A new important fork mid-pipeline": budget exhaustion "stops the same way" as a fork
there. The rules compose: the mechanical bound never overrides a review-gate stop; the
review-gate stop never requires burning the mechanical bound.

## Mid-chain consumption

- `build`: the ledger (`.hermes/sdd/progress.md`) and the goal contract share the same
  acceptance command — one `verify:`, enforced twice. A task's completion line cites
  the command result; the gate re-runs it for the whole suite at the stage boundary.
- `review-commit`: do not declare the goal done while a gate fails or open
  BLOCKING/MAJOR findings exist (review-commit/SKILL.md § Step C — Commit/deploy gate: never push without a
  review pass; the draft PR after the converged loop is not an important fork).
- `test-evals`: the plan's test cases feed `verify:` — the gate command names the
  suite path, so RED tests land inside the gate's blast radius, not outside it.

## What the goal must NOT contain

- No fixed turn number inherited from the default — an explicit, computed one only.
- No `stop_when` that stops on normal progress ("pause after each task" — the unattended anti-pattern; see unattended.md § "When to stop: important forks only" wording and the never-ask rule).
- No secrets or personal paths in the goal text (it is stored per session and shown
  by `/goal show`).
