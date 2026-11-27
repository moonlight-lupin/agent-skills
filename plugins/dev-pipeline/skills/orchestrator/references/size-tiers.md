# Review Tiers — compatibility reference

**Risk-first routing is authoritative:** read
[`risk-routing.md`](risk-routing.md) first. It independently classifies
complexity (S0–S3, planning and decomposition) and risk (R0–R3, review depth).
The result is an **effective review tier T0–T3** used by downstream skills.

This file retains the review-loop budget contract for existing consumers.
**Do not select T2 solely because a diff is large or touches many files.**

| Effective review tier | Per-task review | Step A | Step B reviewers | Confirm rounds |
|---|---|---|---|---|
| T0 (S0/R0 only) | none | skipped | 0–1 | 0 |
| T1 (low-risk behavior or nontrivial R0) | none | yes | 1 | 1 |
| T2 (R2 external/untrusted exposure) | one combined spec + quality review | yes | 2 cross-model | 2 |
| T3 (R3 security/irreversible/live release) | two-stage spec then quality | yes | 3 | 3 |

- R0/S0 → T0; R0/S1–S3 and R1 → T1; R2 → T2; R3 → T3.
- T0/S0 behavioral change with untrusted input is impossible under this
  mapping: classify its risk independently and escalate.
- Any live deployment gets the three-reviewer gate regardless of other
  classifications or instructions.
- R1 with S2/S3 still needs a detailed *plan*, despite getting T1 review.
- Goldfish spec review is run (unattended, no prompt) for **S2/S3**, not inferred from T-tier.
- The user may request extra reviewer rounds; no automatic downgrade of
  discovered risk is allowed.
- T0 no-behavior changes may commit with basic verification; all other
  paths require their applicable review pass before pushing.

## Confirmation protocol

R1 is the initial review. Confirm budgets count rounds AFTER R1; maximum
ordinary sequences are R1+1 at T1, R1+2 at T2, R1+3 at T3. Confirm the
fixed code and rerun full acceptance tests after each fix. Open BLOCKING /
MAJOR findings, or new failing acceptance tests, mean NOT SHIP even if
the round budget is exhausted. The user must decide whether to extend the
budget, redesign, or accept the remaining risk.

See `review-commit/references/confirm-round-protocol.md` for the detailed
loop and three-reviewer deployment gate. Model pins remain in
the lanes config (`orchestrator/config/lanes.default.toml` + override).
