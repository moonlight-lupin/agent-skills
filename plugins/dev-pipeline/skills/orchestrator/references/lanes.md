# Lanes — roles and rules

Lane configuration — lane definitions, CLI binaries, argv templates, and
effort flags — lives in the lanes TOML (`skills/orchestrator/config/
lanes.default.toml`) and never in this file, a stage skill, or a reference.
The bundled default sets NO model pins: every lane ships with `model = ""`
(the CLI's default). A model pin belongs in a machine override TOML that you
own — see `config/examples/hermes-claude-code.toml` for a filled override.
When a pin changes, edit your override TOML only.

## Where the config lives

- Bundled default: `skills/orchestrator/config/lanes.default.toml`
  (schema `dev-pipeline-lanes.v1`).
- Env override: `$DEV_PIPELINE_LANES` REPLACES the machine files when set.
- Otherwise the FIRST existing machine file is used — `~/.hermes/dev-pipeline/
  lanes.toml` and `~/.config/dev-pipeline/lanes.toml` are alternatives, not
  layers.
- Project: `<repo>/.dev-pipeline/lanes.toml` merges on top (untrusted
  surface: per-lane model and effort labels only — trust rules in
  `scripts/lanes.py`).
- Explicit `--config` files are trusted, apply LAST, and win.
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

All four model-family lanes (anthropic, openai, cursor, muse — driven by the
Claude Code, Codex, Cursor, and Muse CLIs) stay declared in the default
config. A lane whose CLI or key is missing is skipped at resolve time, so the
default can list every lane a machine might use. The example override file
(`config/examples/hermes-claude-code.toml`) shows a machine where Claude Code
is the only CODING arm while other families still cover reviewer seats.

When seats cannot be filled with independent model families, the resolver
flags same-family fills; `review.same_family_seats` in the TOML governs them,
documenting the existing resolver behavior (not a policy change):
- `ask` (default): the seat is filled and the verdict becomes ASK-USER
  (exit 3) — the gate surfaces the degraded bench instead of widening it.
- `allow`: the seat is filled, the verdict stays OK, and a note records the
  same-family fill.
- `never`: the seat is left empty; the shortfall makes the verdict ASK-USER
  (a gate holds the deploy until the user decides).
A same-family fill never counts as an independent family; T3/gate panels are
three seats, and only the override policy can let them share a family.

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
