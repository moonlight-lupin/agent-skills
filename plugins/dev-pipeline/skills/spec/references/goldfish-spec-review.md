# Goldfish spec review — pre-implementation stress test

Fresh-context, zero-history subagent review of a finished spec or plan,
before `test-evals` runs. Adapted from the Elephant-Goldfish Model (EGM,
Apache-2.0, created at Google); personas vendored at pinned commit
`3d0b348` — see `goldfish/ATTRIBUTION.md`.

## When to run

Complexity gate comes from `orchestrator/references/risk-routing.md`
(single home): the gate **runs at S2 and S3**, right after the plan turn is saved
(and its own verify checklist passed — approval here means the spec's
self-check, not a user prompt; the run is unattended), BEFORE `test-evals` runs. S0 and S1 are
exempt. So is research. Unattended semantics
(`orchestrator/references/unattended.md`): the stage runs the swarm (the 4
dispatches, ~2–4 min each) without an offer or a prompt — an optional extra
the docs used to offer is not a question in unattended mode. State that the
swarm ran (or why it was skipped) in the ledger and execution continues.
- **Optional gate (spec range):** after the spec turn, before the plan turn,
  when intent risk is high — e.g. a wrong assumption here is expensive
  (new external integration, migration, public API). S2/S3 only. Skip by
  default; run it only when intent risk is actually high (say so).
- **Skip entirely for:** trivial single-task builds, research spikes, and
  anything where the user invoked review-commit directly on a diff.

Economy of scale rule: for plans of 3 tasks or fewer, skip the swarm only
with a recorded reason in the ledger (state it and continue).

## The default swarm (4 personas)

| Persona file (`references/goldfish/personas/`) | Role (one line) | Standard applied |
|---|---|---|
| `zoom_out.md` | Skeptical architect; kills over-engineering, dead-ends, speculative scope (YAGNI) | `goldfish/standards/zoom-out-standard.md` |
| `comprehension.md` | Naive fresh reader; flags anything not self-contained or hand-waved | `goldfish/standards/feature-spec-standard.md` |
| `design_critic.md` | Hostile senior critic; hidden risks, bottlenecks, unmitigated failure modes | `goldfish/standards/feature-spec-standard.md` |
| `implementation_readiness.md` | Tech lead as implementer; flags plans not immediately actionable | `goldfish/standards/implementation-readiness-standard.md` |

Off by default (enable only when the user asks):

- `structural.md`, `style.md` — layout and copy-editing. The controlled
  English style and the spec template already cover this locally.
- `codebase_details.md` — pedantic doc-vs-code audit. Only for rework of
  existing code, not greenfield.
- `synthesizer.md`, `bootstrap_orchestrator.md` — orchestrator synthesis is
  done by the pipeline stage itself; bootstrap is out of the trial scope.
- Upstream skills `egm_brainstorm` (overlaps `grill`), `egm_draft`
  (overlaps the spec turn), `egm_drift_report`, `egm_resolve`
  (converge loop covers findings) — not vendored; reconsider separately.

## Zero-context dispatch contract (Hermes `delegate_task`)

Each persona runs as ONE fresh, isolated subagent child. A goldfish review
with conversation history is not a goldfish review — never reuse a child.

Per child, pass ONLY:

1. The instruction to read its persona file first (absolute path) and the
   assigned standard file (absolute path), and to follow them verbatim.
2. The artifact under review: absolute path (spec or plan file under
   `.hermes/specs/` / `.hermes/plans/`).
3. An explicit read-only allow-list: files the persona may additionally read
   (e.g. live source dirs the plan touches, `.hermes/constitution.md`).
   Everything not listed is assumed unknown to it.
4. Its read-only protocol and severity labels: Blocker / Major / Nit, plus
   "Affected Scope" (file/line/section) and "Finding & Recommendation" per
   finding — the upstream output format.
5. Report destination: write its full report to
   `<artifact-dir>/goldfish/<persona-stem>.report.md` — artifact-first, no
   large findings dumped in the chat return. The child's text return states
   the report path plus a count per severity, nothing more.
6. If it lacks context it must report that as a finding, not guess.

Do not pass: project history, prior discussion, other personas' findings,
the user's expectations, or any review-model hints. Children answer nothing
from an allowed file they did not read.

## Convergence (runs in the stage, not in a child)

1. Read all four reports. Deduplicate overlapping findings.
2. Rank: Blockers first, then Majors, then Nits. Nits are listed, not
   discussed, unless the user asks.
3. Present the ranked list to the user; recommend accept/reject per Blocker
   and Major. The user owns acceptance — personas are advisory.
4. Approved fixes go into the spec/plan edits the stage already performs.
   No separate EGM resolve step.
5. Re-audit at most once: re-dispatch only personas that produced accepted
   Blocker/Major findings, on the changed ranges. Two rounds at most.
6. Proceed to `test-evals` with all remaining Nits attached to the plan
   as open review findings, if the user accepted them.

Model selection for the Goldfish children: declare a `[lanes.goldfish-glm]`
lane in your machine override TOML (model + provider + family) and list it in
`[roles] goldfish = [...]`. Resolve the lane with the resolver
(`skills/orchestrator/scripts/lanes.py resolve`) to get the model and
provider; the bundled default only sets `roles.goldfish = ["controller"]`,
which has NO model of its own — with only the controller lane resolving, the
children inherit the dispatching session's model. Override the lane when you
want children pinned independently. When the resolved lane HAS no model pin,
the dispatch command DROPS `-m` and `--provider` entirely (CLI defaults /
inherited session model) — do not pass empty values. Mechanism: `delegate_task` children cannot pin a per-child
model (they inherit the parent's model), so dispatch each persona as a
one-shot child with the resolved lane's model and provider:

```
hermes chat -Q -m "$GOLDFISH_MODEL" --provider "$GOLDFISH_PROVIDER" --query-file <task-file>
```

When the resolved Goldfish lane has no model pin (bundled default: only the
controller lane resolves), DROP both `-m` and `--provider` — an empty value
must never be passed:

```
hermes chat -Q --query-file <task-file>
```

`$GOLDFISH_MODEL` / `$GOLDFISH_PROVIDER` are the resolved Goldfish lane's
values (export them from the resolver output before dispatching; do not
hard-code ids here).

`<task-file>` is `<artifact-dir>/goldfish/<persona-stem>.task.md` and holds
the full per-child instruction block from the contract above (persona file,
standard file, artifact path, allow-list, protocol, report destination) —
never on the command line. Zero-context rules, read-only protocol, and the
report destination are unchanged; a `-Q` one-shot child is as isolated as a
`delegate_task` child. They remain NOT reviewer lanes — their pin sits in the machine override's
Goldfish lane, not in a reviewer seat, and never counts toward a tier's
reviewer set. Record the dispatch route (one-shot child, model that
ran) in the ledger.

## Trial envelope (bounded trial — operator policy)

- Started 2026-10-25. Exclusions above are load-bearing-path exclusions:
  the swarm is advisory-only and adds no new mutation steps.
- Review decision after the earlier of: 2 calendar weeks, or 3 non-trivial
  builds that used the gate. Criteria: did a Blocker/Major finding land
  before implementation in at least one build; was dispatch overhead
  acceptable; no persona prompt caused scope creep or question-asking.
- If kept: fold the trigger line into the spec stage SKILL.md flow table
  permanently and drop this trial note. If dropped: delete `goldfish/`
  and this file (ask before the deletion — operator policy).