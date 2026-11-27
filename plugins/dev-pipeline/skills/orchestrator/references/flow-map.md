# Flow-Map — the SDD chain (single home)

The single home of the chain diagram. Other stage skills and the orchestrator
SKILL.md point here instead of redrawing it. Complexity (`risk-routing.md`) decides planning stages; risk decides review depth.

```
 complexity S0-S3 + risk R0-R3 → review T0-T3
     │
 grill  →  spec ──────────────────────────────→  test-evals  →  build  →  review-commit
(harden    spec turn → clarify → plan turn       (RED tests     (per-task    (two-axis pass → R1
 the plan)  → tickets (optional)                  for the plan's  review per  → confirm rounds within
                                                  test cases)    tier, final  budget → commit/deploy gate)
                                                                 review,
                                                                 converge)
```

Phase → stage:

| Phase | Stage skill |
|---|---|
| grilling | `grill` |
| spec / clarify / plan / tickets | `spec` (turns of one stage) |
| goldfish spec review (S2/S3) | `spec` — swarm via `spec/references/goldfish-spec-review.md`, after the approved plan, before `test-evals` |
| tests written RED | `test-evals` |
| implement, converge | `build` |
| code review of a diff, fix loop, commit, deploy | `review-commit` |

Model lanes for build and review: roles/rules in `orchestrator/references/lanes.md`; pins in the lanes config (`orchestrator/config/lanes.default.toml` + a machine override).
