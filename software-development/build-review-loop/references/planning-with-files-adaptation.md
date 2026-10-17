# Adaptation Reference: planning-with-files Port (2026-09-12)

Source: https://github.com/OthmanAdi/planning-with-files (OthmanAdi, MIT,
26.8k stars, v3.17.2; reviewed Sep 2026). Verdict on the repo: Watch —
strong engineering (706 tests, honest evals, real security-incident
disclosure), and it ships a NATIVE Hermes plugin (verified against Hermes
0.19.1, skills-guard SAFE). Decision (user, Sep 2026): option C — port the
concepts into this skill dependency-free; do NOT install the plugin.

## Ported

1. **3-file persistent loop state** — their `task_plan.md` / `findings.md`
   / `progress.md` pattern, adapted: renamed to `loop-plan.md` /
   `loop-findings.md` / `loop-progress.md` (distinct from repo docs),
   gitignored working state per this skill's release-hygiene rules,
   promoted into the repo at delivery. `references/persistent-loop-plan.md`.
2. **Phase-status + completion gate** — their `**Status:**` grammar and
   gated-stop concept, implemented as `scripts/loop_plan_check.py` with a
   `--gate` exit code instead of a `pre_verify` hook. Runs at session
   resume (resume pointer) and before loop completion.
3. **SHA-256 attestation** — their plan-tamper detection, applied to
   builder briefs and Hermes-written test/plan files:
   `scripts/attest_file.py attest|verify`. Turns pitfall #20's ad-hoc
   diff-reading into a mechanical check.

## Explicitly NOT adopted

- **The native Hermes plugin** — per-turn `pre_llm_call` injection,
  write reminders, `pre_verify` gate, `/pwf` commands. Standing ~1k
  token/turn cost on EVERY session to defend against context rot we only
  incur inside long loops; our loops read state on resume instead.
- **Injection-time attestation enforcement** — their hooks refuse to
  inject a tampered plan. We attest on demand (attest/verify around
  dispatches); no hook chain to enforce at.
- **Parallel-session write guard** — detects completed phases going DOWN
  between turns from concurrent sessions. Our loops are
  single-orchestrator; parallel BUILDERS never touch loop files.
- **PWF env knobs / .planning/<slug> isolation / .active_plan pointers** —
  multi-plan fleet machinery for multi-project agent seats; overkill here.
- **KV-cache-stable injection formatting** — no injection, so moot.

## Revisit trigger

If a real loop shows context rot despite this pattern (orchestrator
resumes wrong, loses a review verdict, or re-derives settled decisions),
re-evaluate installing the plugin (option A):
`hermes skills install OthmanAdi/planning-with-files/.hermes/skills/planning-with-files --yes`
then the plugin route per their docs/hermes.md. Verify with `/plan-doctor`.
