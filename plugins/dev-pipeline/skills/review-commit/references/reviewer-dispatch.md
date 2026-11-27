# Reviewer Dispatch — running the builder and reviewer CLIs

How to dispatch the lanes (roles/rules in `orchestrator/references/lanes.md`; pins in the lanes config) so a round
produces a verdict instead of an environment error. Model names live in
the lanes config (`orchestrator/config/lanes.default.toml` + a machine
override); this file uses `$BUILDER_MODEL`, `$REVIEWER_A_MODEL` etc. for them.
(Extracted in v0.2 from the old `build-review-loop.md` and
`codex-confirm-loop.md`.)

## Prerequisites

- Cursor CLI (builder): binary is `agent` (`~/.local/bin/agent`), not
  `cursor`. Auth: `CURSOR_API_KEY` in `~/.hermes/.env`.
- Codex CLI (reviewer A): `npm install -g @openai/codex`; Codex OAuth or
  `OPENAI_API_KEY`; needs `pty=true` and a git repo.
- Claude Code (reviewer B): `claude -p`.
- Muse (reviewer C): `muse exec --trust-workspace`.
- Check before the first dispatch: `which agent codex claude muse`.
- Auth failures that repeat: stop retrying and switch per `cli-auth-fallback`.

## The review input is a pre-generated diff

Don't point reviewers at the tree. Export the exact delta and reference it:

```bash
git diff <base>..<round-commit> > <repo>/review-diff-<proj>.diff   # gitignored
codex exec --sandbox read-only -m "$REVIEWER_A_MODEL" -c model_reasoning_effort="high" \
  "Read ONLY ./review-diff-<proj>.diff (plus the current files it touches).
   <confirm-round prompt per confirm-round-protocol.md>. Review only, change nothing."
```

Bounded context, no re-litigating untouched files, and the diff doubles as
the fix brief's evidence. Muse needs this shape to finish at all. R1 uses the
change's full diff; confirm rounds use the FIX diff
(`confirm-round-protocol.md` § Scope).

Write the review prompt to a file inside the repo cwd (gitignored) and pass
its path — Muse cannot read `/tmp`, and `claude -p` reads only under its cwd.

## Working directory and sandbox

- `codex exec` refuses to run outside a git repo ("Not inside a trusted
  directory", exit 1 in < 2 s). Run it from the repo root; reference the diff
  by absolute path.
- `claude -p` reads only files under its allowed dirs. Run it from the
  directory holding the diff.
- Codex sandbox values are exactly `read-only`, `workspace-write`,
  `danger-full-access`. `read-only` cannot run pytest; `workspace-write` can
  hang inside slow DB-backed suites. Default: read-only static review with
  "do NOT run the test suite" — the orchestrator runs the suite.
- An exit with only an environment error is a failed dispatch, not a clean
  review. Never record "no findings" from it.

## Timing

- Codex confirm on a ~2k-line diff: ~10 min. Codex + Muse in parallel at high
  effort: ~15-20 min typical; a Muse confirm with a long finding list can run
  ~50 min. Don't diagnose a hang before ~60 min; Muse finishes last.
- Opus high: 5-8 min per review.
- One timer per background process. A late timer is "stale — superseded";
  take elapsed time from `ps -o lstart -p <pid>`, not from counting timers.
- Background polling cadence: `background-build-polling.md`.

## Reading each reviewer's output

- **Reviewer A (Codex):** executes probes from the diff — name the exact
  probes to re-run in the confirm prompt.
- **Reviewer B (Opus):** reads deeply; ask for a per-ID fix-map table and a
  must-fix vs low-priority split.
- **Reviewer C (Muse):** verdict block of per-item RESOLVED/NOT-RESOLVED with
  an ID map, then new issues (severity + file:line), then what it ran. Its
  NOT-RESOLVED list can include items it scoped out of its own R1 — check the
  ID map before treating them as regressions. New MAJORs are usually real;
  MINORs skew to publication/portability.
- Different reviewers find different bug classes — that is why R1 uses
  several. It is not a reason to keep every reviewer on every confirm round
  (`confirm-round-protocol.md` § Who reviews each confirm round).

## Reviewer death, usage limits, substitution

- Usage limit mid-run ("retry at HH:MM"): don't rewrite the prompt. Harvest
  the partial log as leads to reproduce (never as findings), note the reset,
  re-dispatch the IDENTICAL prompt after it.
- Reviewer 529 overload: retry with the fallback model configured on the lane (`--fallback-model <lane fallback>`); the fallback id is a config value, not a remembered name.
- Builder `resource_exhausted`: drop one effort tier, per the pin-drift rule — the resolved lane's current pin is the source of truth, not a remembered fallback.
- "Assess yourself instead of <reviewer>": do the confirm yourself against
  the prior round's exact finding list (probe each open item, per-item
  verdicts, check fix-induced regressions), record who was substituted and on
  whose instruction, and cancel any timer waiting on that reviewer.
- A lane is DEAD (tool gone, outage beyond its fallback, no usage window)
  during a CONFIRM round: record the outage in the ledger, then substitute
  the dead lane's coverage per
  `review-lessons/references/generated-frontmatter-and-reviewer-outages.md`
  §1 (cross-family substitution — one lane re-probes the dead lane's prior
  cases under its own harness). Model names in that lesson are historical;
  the lanes config wins (`orchestrator/config/lanes.default.toml` + override; resolve with `lanes.py doctor` first).
- **At the GATE a dead lane cannot be substituted.** The gate requires every
  lane's own SHIP on the net diff (`confirm-round-protocol.md` §
  Three-reviewer deployment gate). If a lane is dead at gate time: record the
  outage, hold the deploy, and re-dispatch that lane when its tool or usage
  window returns. Only the USER can approve shipping with a lane's gate SHIP
  missing, in writing, recorded in the ledger.
- Killing a respawning `codex exec` worker: loop `os.kill` over `pgrep -f`
  output until it returns empty; a single `kill <pid>` loses to the respawn.

## Bot Mode (optional)

Two bot profiles can run the lanes with persistent context:

| Bot | Profile | Role |
|---|---|---|
| Coder | `coder` | builder lane — drives Cursor CLI with `$BUILDER_MODEL` |
| Code Reviewer | `code_reviewer` | reviewer lanes A/B/C — Codex, Claude Code (Opus), Muse |

```bash
hermes -p coder chat --in ~ -c "Bot Chat" --create-if-missing -Q -q \
  "Message from 🤖 hermes (@hermes): <task>"
```

Run with `background=true, notify_on_complete=true`. Use `delegate_task` for
quick same-model subtasks; bots for cross-model build/review with memory
across rounds. The confirm-round protocol applies unchanged.
