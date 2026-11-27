# Ledger-Orchestration Concept Port — Adaptation Notes

Source: a public "ledger-based zero-shot
self-orchestration" (a 2026 conference submission).
Verdict on the repo itself: **Watch** (benchmark harness, not a tool; self-graded with a
patched LiveCodeBench evaluator; no independent replication yet).

## What was ported (additive changes only)

1. **Sample-test veto → build-review-loop Step 4 (v1.1.0).** In the upstream pattern, a failing public-test
   run overrides the manager's "done" verdict and forces a fix-or-switch task. Ported as:
   a failing Hermes verification check is ground truth, vetoes the build's DONE/APPROVED
   claim, becomes a BLOCKING issue, and becomes the fix brief's acceptance criterion.
   Added a Verification Checklist line to enforce it.
2. **Ledger curation rules → subagent-driven-development §3b (v1.4.0).** From the paper's
   ledger design (`plan.md` / `notes.md` / `solution.py`): notes are *rewritten* (curated)
   each round rather than appended, and capped at 4k/8k chars so context stays bounded.
   Ported as: curate-not-append for progress ledger and report files, ~200-line / ~8k-char
   caps with consolidation, and a no-progress guard (two identical rounds → escalate or
   split, stop the loop) mirroring the upstream re-issue guard.
3. **Orchestration-hurts caveat → subagent-driven-development §5.** The paper's negative
   result: one model regressed under orchestration — deliberation discarded correct
   approaches and unverified worker output overwrote correct work. Ported as a warning in
   Model Selection: if a post-fix output is worse than the first attempt, diff the attempts,
   keep the better one, consider single-context execution.

## What was deliberately NOT adopted

- The upstream pattern itself: an ICLR experiment harness tied to
  LiveCodeBench, `uv`-pinned deps, and pinned cloud backends. Our delegate_task/subagent
  workflows already cover the orchestration natively.
- The full manager→brainstorm→manage→worker→verifier loop: our two-stage review
  (spec → quality) plus final integration review is the equivalent structure with
  human-gated escalation. Porting the loop wholesale would duplicate it.
- The cut-off summarizer (summarizing a token-capped worker's partial reasoning): Hermes
  subagents do not hit per-call token caps the way the paper's 128k single-call workers do.
  Revisit if we ever run long-context worker loops.

## Efficacy test (2026-09-12, post-port)

Blind A/B on the same day's writing-for-agents refactor (BRL pitfalls split + Red Flags
dedupe; SDD rationalizations/remember dedupe + description fix): same model, same scenario
prompts, fresh subagent per arm. BRL arm reached equal-or-better-focused answers with
15 → 3 API calls per probe (~5× fewer) and rejected out-of-domain content the old arm
included; SDD behavior unchanged (dedupe removed only restatement). Both new pointers
(toolkits and past-project findings) fired correctly. Directional (n=1 per cell); the
guard scenario (S6) answered identically in both arms, confirming the port added no
behavioral regression.

## Re-evaluation triggers

- ICLR 2027 reviews land (~Nov–Dec 2026): check acceptance and reviewer-identified flaws.
- Independent replication of the Qwen3.8-27B 69.2→92.4 result.
- A maintained standalone extraction of the orchestrator loop (would change Watch → Adopt).

## Ledger curation rules (in-content rules verbatim from SKILL.md, v0.6.0)


The ledger and shared report files coordinate work; they are not logs.

- **Curate, do not append.** When updating the ledger or a report after a fix round, rewrite the affected section to state the current truth (e.g. replace an issue line with its resolution) instead of stacking a new line under the old one. A stale "issue open" line next to a "fixed" line makes the next reviewer re-litigate settled findings.
- **Hard caps.** Keep `progress.md` under ~200 lines and each report file under ~8,000 characters. Near the cap, consolidate: collapse resolved findings into one summary line, drop superseded notes. Long files degrade the fresh-context readers (reviewers, converge) they exist for.
- **No-progress guard.** If two consecutive fix/review rounds on the same task produce the same finding or the same BLOCKED reason, stop the loop and escalate to the human (or split the task) instead of dispatching a third identical round. This mirrors the upstream ledger-orchestration guard that stops the manager re-issuing the task it just handed out.

## Durable ledger usage rules (verbatim from SKILL.md, v0.6.0)

Conversation memory may not survive compaction. Track progress in a ledger file, not only in todos.

- Ledger path: `.hermes/sdd/progress.md` at the repository root.
- At skill start/resume, check whether the ledger exists. Tasks listed there as complete are DONE — do not re-dispatch them. Resume at the first task not marked complete.
- When a task's reviews come back clean and your independent verification passes, append one line to the ledger in the same bookkeeping step:
  `Task N: complete (commits <base7>..<head7>, spec PASS, quality APPROVED, verification <command/result>)`.
- Record minor deferred review findings in the ledger so the final integration reviewer can triage them.
- After compaction, trust the ledger and `git log` over memory.
- `git clean -fdx` can destroy this git-ignored scratch ledger; if that happens, recover from `git log`, review report files, and test output.
