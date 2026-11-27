# Spec Review Convergence

Multi-round review of a SPEC (or plan/design doc) until a SHIP verdict, before any implementation. Distinct from code-diff confirm rounds and the `test-evals` batched per-batch review: the artifact under review here is the document, and the quality gate is reviewer convergence.

## Round 1: two diverse reviewers

Dispatch at least two reviewers with different strengths on the SAME axes. Proven pair: reviewer lanes A (Codex) + B (Claude Code Opus) — models from the lanes config (`orchestrator/config/lanes.default.toml` + override). They catch different classes:
- Codex: completeness, contradictions, scope risk, feasibility against the actual codebase (it cites file:line when given repo access via `codex exec --sandbox read-only -C <repo>`).
- Claude Code Opus: invariant conflicts, untestable acceptance criteria, and mechanisms the codebase doesn't actually provide. Use `--permission-mode plan`; `--max-turns 25` if it must read files (each Read = 1 turn; name exactly which files).
- Reviewer lane C (Muse) is a strong third eye — see `muse-review-quirks` for invocation. It excels at re-observation/race gaps and one-shot-event misses others pass over.

Review prompt shape (all reviewers): name the exact files to read (spec + repo contract file like CLAUDE.md), give 4-6 review axes, cap findings (10-15), require `VERDICT: SHIP | REQUEST CHANGES` + findings tagged MAJOR/MINOR/NIT each with a concrete suggested fix, no code proposals.

## Fold findings into the next spec version

- Fix every BLOCKING/MAJOR finding in one pass — don't cherry-pick; batch cheap MINOR/NIT fixes into the same pass or defer them. Add a **revision note** at the top mapping which round's findings drove the change; this makes the next confirm round cheap to verify.
- When a finding is declined, state the decision IN the spec (a decision line where the question arose), not just in chat — reviewers re-raise unstated decisions every round.
- Re-check the spec for contradictions introduced by the fixes BEFORE dispatching the confirm round: fix rounds commonly create new conflicts between sections that no reviewer explicitly flagged.
- Keep the spec as ONE versioned file with revision notes, not v1/v2 file copies — reviewers read the current version; the revision note is the history.

## Confirm rounds: RESOLVED / RESOLVED-BUT / NOT-RESOLVED + NEW hunt

Each confirm-round prompt:
1. Lists every prior finding (number, tag, one-line summary — the reviewer has no memory of prior rounds).
2. Asks per finding: `RESOLVED` | `RESOLVED-BUT <residual>` | `NOT-RESOLVED — <why>`.
3. Demands a NEW-problem hunt: "did the revision introduce new problems (contradictions between sections, untestable criteria, over-engineering)? List as NEW-N with severity, or 'no new problems'." This is mandatory — pure-verify prompts miss fix-induced contradictions, which are common (4 new MAJORs appeared in one round after all 10 prior findings resolved).
4. Ends with VERDICT + one line of justification.

- A RESOLVED-BUT residual that is BLOCKING/MAJOR is fix-in-this-pass; a MINOR one is recorded as a decision line or deferred — never silently accepted (an unstated one resurfaces next round).
- Reproduce reviewer claims against the actual spec text before folding them in — a mis-cited line number once pointed at the wrong finding; the claim was real but lived elsewhere. Triage scope yourself rather than accepting findings as written.
- Findings should narrow each round. If they grow, a fix round is thrashing — stop, re-read the spec yourself, and decide with the user.
- Convergence across 11 user stories took 4 confirm rounds with ONE Muse reviewer (lane-resolved pin, effort=high, artifact-by-path prompts, bounded tool calls). Muse confirmed with per-finding RESOLVED/NOT-RESOLVED verdicts + NEW-N hunt each round; the NEW-N hunt caught real fix-induced regressions in every round that introduced them (skip-semantics contradiction, kv-read conflict, dedup-wakeup ambiguity). When a NEW finding is genuinely about the fix's own wording rather than the design, fix in place and re-confirm cheaply.

## Ship criteria

Ship after one confirm round reports: no open BLOCKING/MAJOR finding (MINOR/NIT resolved, accepted or deferred), no BLOCKING/MAJOR NEW-N, VERDICT: SHIP. Do not require both original round-1 reviewers to independently SHIP — one reviewer running confirms to convergence is sufficient when round 1 already converged on the same blockers from both reviewers. Re-running the full review for a redundant second SHIP adds cost, not information.

Remaining [NEEDS CLARIFICATION] markers are acceptable at SHIP when the reviewer explicitly says they don't block planning; default each one to a sensible default in the implementation plan and mark it as a default, not a decision.

Budget: the round budget and stop conditions are the shared ones in `confirm-round-protocol.md` (spec reviews use the tier of the work they specify). MINOR/NIT findings and contradictions outside the revised sections go to the deferred list; they do not keep the loop open.

## Artifacts and ledger

Durable record = the spec's revision notes + a per-round ledger in chat (round, reviewer, findings, verdict) — the user pings 'status' and expects current round state instantly. Keep confirm prompts/logs under /tmp per round; do not commit them.
