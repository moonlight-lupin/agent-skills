# Routing — complexity and risk (single home)

This replaces size-driven review depth with **two independent classifications**.
Use this file for routing decisions. Older stage documents may say "tier";
that means the *effective review tier* below, not the complexity band.

## Step 0 — classify both axes, before building

**Complexity S0–S3** selects planning and task-decomposition work.
**Risk R0–R3** selects independent review depth. State both and the derived
review tier. Do not infer safety from a small diff. Reclassify when the actual
diff or exposed boundary changes; never change either axis silently. Lowering a
classification requires the user's consent.

| Band | Complexity signal | Planning path |
|---|---|---|
| S0 | Trivial, one obvious change, ~20 lines or less | Intent/assumptions, edit, verify |
| S1 | Small, one behavior/seam, ~300 lines or less | Short acceptance-criteria plan, RED test if behavior changes |
| S2 | Multiple behaviors/seams, >300 lines, or >5 files | Spec, plan, named test cases, task decomposition |
| S3 | Large, cross-component, multi-team, or difficult migration plan | Full spec, dependencies, milestones, task slices and integration checks |

Take the highest applicable complexity signal. Complexity does **not** by
itself increase the number of reviewer lanes or confirmation rounds.

| Band | Exposure / consequence (highest matching risk wins) | Review tier |
|---|---|---|
| R0 | Documentation, metadata, mechanical change; no observable behavior change and no sensitive boundary | T0 for S0; otherwise T1 |
| R1 | Bounded internal behavior, trusted inputs, reversible changes, no outside trust boundary | T1 |
| R2 | Untrusted/externally supplied data, user-controlled parsing, resource exhaustion, nontrivial concurrency or filesystem access without established security isolation | T2 |
| R3 | Authentication, authorization, permissions, secrets, money, irreversible data loss/migration, trust-boundary escape (e.g. symlink/path traversal), public release or live deployment | T3 |

For ambiguous external exposure, choose the higher risk until evidence rules
it out. A five-line auth edit is R3. A 1,000-line internal refactor may be
S3/R1. A CSV importer consuming user-provided files is at least R2 even if
its diff is only ten lines.

## Derive effective review tier (compatibility contract)

Downstream skills continue to read T0–T3 *review tiers*; their existing
reviewer lanes, confirm-round budgets, and live-deploy three-reviewer gate
remain unchanged. Do **not** take max(complexity, risk): complexity selects
the planning path, risk selects review depth.

| Risk | Effective review tier | Step A | Step B reviewer lanes | Confirm budget |
|---|---|---|---|---|
| R0 / S0 | T0 | none | 0–1 | 0 |
| R0 / S1–S3 or R1 | T1 | two-axis pass | 1 (A) | 1 |
| R2 | T2 | two-axis pass | 2 (A+B) | 2 |
| R3 | T3 | two-axis pass | 3 (A+B+C) | 3 |

The full acceptance suite MUST run again after each fix before a review
finding is closed. Add focused regression tests for reproduced failure modes;
check the net diff after fixes, not only the specific repaired lines.
An exhausted budget with open BLOCKING/MAJOR findings is **NOT SHIP**;
stop and ask the user whether to redesign, spend another round, or explicitly
accept the residual risk. A test failure introduced by a fix cannot be
waived merely because the original finding was resolved.

## Stage routing: complexity first, risk reviews afterward

Bug-shaped work (failing test, stack trace, "fix this" with no feature ask) routes to the `debug` skill instead of the chain: reproduce, failing test at the highest public seam, minimal fix, full suite, then review-commit at the R-tier the bug's blast radius sets. Complexity sets only the fix's planning path; the R-tier alone sets review depth (S0/R3 is still T3).


- S0: edit + verification, with risk-appropriate review (S0/R3 is still T3).
- S1: short plan + test-evals (behavior changes) + build + review-commit.
- S2/S3: grill if fuzzy, spec, plan, test-evals, build, review-commit.
- Goldfish spec review: run for S2/S3 after the approved plan, without asking — except that plans of 3 tasks or fewer may skip it with a recorded ledger reason (stated, then continue); it is a
  planning aid, NOT a reviewer lane or a substitute for security checks.
- Per-task review and confirm budgets come from the effective T-tier, NOT
  from S-size. For large S2/R1 work, separate planning tasks but use T1
  review depth.
- User-requested review counts or models may add scrutiny beyond the default
  depth; they may not reduce required security review or remove the
  three-reviewer gate. Lowering a risk classification always needs the user's
  consent. Any live deploy requires the three-reviewer gate whatever the
  requested depth.
- A new or discovered risk boundary upgrades R immediately. Do not silently
  downgrade R after a review passes.
- Review happens per milestone (one build phase or feature, as a guide
  ≤ ~3,000 changed lines), never the whole product at once — see
  `review-commit/references/confirm-round-protocol.md` § Milestones.
- Converge loop eligibility and caps follow complexity, not the T-tier:
  S0/S1 skip the loop; S2 caps at 2 rounds, S3 at 3
  (see `build/references/converge-loop.md`).

## Empirical basis and caution

Four paired pilots found costly T1/T2 review did not help in ordinary tasks,
while the two attacker-facing tasks benefited from deeper review. This is a
directional sample, NOT proof of a general effect. Preserve the risk-based
heuristic as an explicit, revisable policy rather than promising that review
can catch every bug.

## Legacy note

T0–T3 are retained as *review depth aliases* for compatibility with
`build`, `review-commit`, and review-lane reference documents. Older wording
that says size selects T-tier is superseded by this document. Do not change
their model pins or require new CLI capabilities merely to adopt routing.
