# Lanes — roles and rules

Model names, CLI binaries, and invocation flags live ONLY in
`skills/orchestrator/config/lanes.default.toml` and never in this file, a
stage skill, or a reference. When a pin changes, edit the TOML only.

## Where the config lives

- Bundled default: `skills/orchestrator/config/lanes.default.toml` (the
  resolved schema: dev-pipeline-lanes.v1).
- Machine overrides, in precedence order: `$DEV_PIPELINE_LANES`,
  `~/.hermes/dev-pipeline/lanes.toml`, `~/.config/dev-pipeline/lanes.toml`,
  then project-level `<repo>/.dev-pipeline/lanes.toml` (untrusted surface:
  per-lane model and effort labels only — see its trust rules in
  `scripts/lanes.py`).
- Resolver and doctor: `skills/orchestrator/scripts/lanes.py`. Check a
  machine with `python3 skills/orchestrator/scripts/lanes.py doctor`.

## Lanes (roles, not models)

| Lane | Job | CLI family |
|---|---|---|
| **Builder** | implements briefs, fixes review findings | any coding lane the config resolves |
| **Reviewer A** | diff review, executes probes | per config |
| **Reviewer B** | deep read, per-ID fix map | per config |
| **Reviewer C** | re-probes prior cases, race/one-shot gaps | per config |
| **Batch review** (test-evals batched loop) | per-batch review before commit | per config |

All four CLI families (Claude Code, Cursor, Codex, Muse) stay declared in the
default config. A lane whose CLI or key is missing is skipped at resolve
time, so the default can list every lane a machine might use. The
Claude-Code-only example file (`config/examples/hermes-claude-code.toml`)
remains an override example for machines that have only that arm.

When fewer than the tier's independent families resolve, the resolver keeps
every lane but flags same-family seats: `review.same_family_seats` in the
TOML governs them (`ask` by default; `allow` fills the seat and notes it;
`never` refuses). T3 work and every live deploy still need THREE independent
families — a degraded bench can ask, never silently widen. This documents
the existing resolver behavior; it is not a policy change.

## Delegate pins (not lanes)

Delegate sub-tasks (for example the Goldfish spec-review children) never
count toward a tier's reviewer set or the three-reviewer gate. Their models
come from the config like every other pin; `delegate_task` children cannot
pin a per-child model — the dispatching session's model applies.

## Which reviewers a tier uses

From `risk-routing.md` via `size-tiers.md`: T1 = one reviewer (A by default);
T2 = two, cross-model (A + B); T3 and every live deploy = all three (A + B +
C, the three-reviewer gate). The builder lane's model must differ from every
reviewer lane's model.

## Rules

- **The TOML is the single source.** Never put a model id in a skill or
  reference; name the lane, not the model. Pins belong in the override file
  a machine owns.
- **Verify a pin before relying on it.** CLI catalogs rename models; a pin
  that worked last session can vanish. Check the live model list when a
  dispatch fails with an unknown-model error, then update the override TOML.
- **The user's explicit choice wins.** The user's named model or CLI
  overrides the config for that task.
- **Roles don't swap silently.** The builder lane builds and fixes; reviewer
  lanes review read-only. Asking for two CLIs to review means reviewer
  lanes, not the builder.
