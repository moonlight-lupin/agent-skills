# Lanes — which model does which job (single home for model pins)

Every model name the dev-pipeline uses lives in THIS file. Stage skills and
references name the LANE ("the builder lane", "reviewer lane B"), never the
model. When a pin changes, edit this table only.

> The outside `model-routing` skill was older than this table when v0.2 was
> written (it still listed Grok 4.5 / GPT-5.5). Until the two are reconciled,
> this table wins for dev-pipeline work.

## Lanes

| Lane | Job | Tool | Model / flags (as of 2026-10-25) | Fallback |
|---|---|---|---|---|
| **Builder** | implements briefs, fixes review findings | Cursor CLI `agent -p --force --sandbox disabled` | `cursor-grok-4.7-high` | `cursor-grok-4.7-medium` on `resource_exhausted`; then Hermes `delegate_task` per `cli-auth-fallback` |
| **Reviewer A** | diff review, executes probes | Codex `codex exec --sandbox read-only` | `gpt-6-sol` with `-c model_reasoning_effort="high"` (default effort is `none` — never omit) | wait for the usage-limit reset and re-dispatch the identical prompt |
| **Reviewer B** | deep read, per-ID fix map | Claude Code `claude -p --model opus` | Opus 5.5 (`--model opus` resolves to latest) | Cursor CLI `--model "claude-opus-5-5-high"`; on 529 add `--fallback-model sonnet` |
| **Reviewer C** | re-probes prior cases, race/one-shot gaps | Muse `muse exec --trust-workspace` | `--model muse-spark-1.3 --reasoning-effort high --disable-web-tools` | none — record the outage and substitute per `review-commit/references/reviewer-dispatch.md` |
| **Batch "Opus" review** (test-evals batched loop) | per-batch review before commit | Claude Code / Cursor CLI | Opus 5.5 — "Opus" means the current Opus generation, never Grok or an older Opus | as Reviewer B |

## Delegate pins (not lanes)

These run sub-tasks and are NOT reviewer lanes: they never count toward a
tier's reviewer set or the three-reviewer gate. Their model names still live
here, so this file stays the only place pins live.

| Delegate | Job | Model / provider | Dispatch | Pinned |
|---|---|---|---|---|
| **Goldfish children** | the four zero-context personas of the Goldfish spec review (`spec/references/goldfish-spec-review.md`) | `glm-5.3` (non-flash) on `ollama-cloud`, whatever model the dispatching session runs | one-shot child: `hermes chat -Q -m glm-5.3 --provider ollama-cloud --query-file <task-file>` (`delegate_task` children can't pin a per-child model) | pinned by the operator, this setup only |

## Which reviewers a tier uses

From `risk-routing.md` via `size-tiers.md`: T1 = one reviewer (A by default); T2 = two, cross-model
(A + B); T3 and every live deploy = all three (A + B + C, the three-reviewer
gate). The builder lane's model must differ from every reviewer lane's model.

## Rules

- **Verify a pin before relying on it.** CLI catalogs rename models; a pin
  that worked last session can vanish. Check the live model list when a
  dispatch fails with an unknown-model error, then update this table.
- **The user's explicit choice wins.** "Have Opus review it" or "use Codex as
  the builder" overrides the table for that task.
- **Roles don't swap silently.** The builder lane builds and fixes; reviewer
  lanes review read-only. "Have cursor and Claude Code review" means reviewer
  lanes, not the builder.
