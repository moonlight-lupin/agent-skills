# Unattended execution — the important-fork rule (single home)

The pipeline runs **unattended**: no stage pauses at a handoff to ask "shall
I proceed?". After a spec or plan is saved, the session states the artifact
path and continues. The pipeline stops **only** at an *important fork* as
defined here. Every stage skill points at this file; do not invent a looser
or tighter definition.

## What is an important fork

A decision is an **important fork** when it:

1. Changes a public contract (API, CLI flag,
   on-disk format, stored schema, or published event).
2. Touches a trust, auth, money, privacy, or irreversible-data boundary
   (anything that would raise or confirm risk R2 or R3 —
   `orchestrator/references/risk-routing.md`).
3. Chooses between incompatible approaches that would be expensive to
   reverse (architecture, storage engine, protocol, or a constitution-gate
   exception).
4. Relaxes a user-stated constraint, a constitution gate, or a decision
   already settled in `grill` or the spec.
5. Is a ship-gate choice with residual risk: the review budget is spent
   with open BLOCKING/MAJOR findings or failing acceptance tests; merging
   to the default branch; tagging a release; or deploying live.

## What is NOT an important fork

Record the assumption in the ledger or report and continue:

- Naming, file layout, or helper structure inside already-agreed seams.
- Equivalent implementation choices that satisfy the plan and the builder
  block in `orchestrator/references/coding-principles.md` (prefer the
  simpler one).
- "Shall I proceed to the next stage?" or "should I continue after this
  task?" — never ask these; a stage handoff is not a fork.
- Optional extras the docs used to *offer*: for S2/S3, **run** the Goldfish
  spec review after the approved plan, without prompting
  (`spec/references/goldfish-spec-review.md`); skip optional ticket
  slicing unless the user already asked for tickets.
- Pushing the feature branch and opening a **draft** PR after a SHIP review
  — proceed; that is not a fork.

## Where forks are collected

`grill` is the place that collects foreseeable important forks. It walks the
decision tree and settles every one **before the spec is written** — on S2/S3
when the plan is fuzzy, and on any S1 ask that is ambiguous. The session does
not proceed to spec while known important forks are open; later stages treat
forks that grill or the spec already settled as settled.

## A new important fork mid-pipeline

If a **new** important fork appears in a later stage — one that `grill` and
the spec did not settle — stop, write it down as a **single numbered question
with a recommended answer**, wait for the user's answer, fold it in, then
continue unattended. Do not silently resolve it, and do not ask anything more
than that one question. Review (confirm) budget exhaustion, a `BLOCKED` verdict, and a plan
contradiction stop the same way (they are already the review-commit gate's
stop conditions —
`review-commit/references/confirm-round-protocol.md`). The session goal's TURN
budget is a separate mechanical bound: running it out with clean progress is a
raise, not a stop — `goal-binding.md` § Budget-exhaust semantics.

Merging to the default branch, tagging a release, and deploying live are
**always** important forks, at every tier: stop and put the decision to the
user. The three-reviewer live-deploy gate is unchanged.
