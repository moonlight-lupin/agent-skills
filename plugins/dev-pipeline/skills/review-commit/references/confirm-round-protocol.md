# Confirm-Round Protocol (single home for loop rules)

The one home for review-loop rules: what a round is, what keeps a loop open,
the round budget, the stop conditions, and the three-reviewer gate. Every
other file that mentions a round cap points here (and to
`orchestrator/references/size-tiers.md` for the per-tier numbers).

Consumers: this `review-commit` stage (code diffs and spec/design docs), the
`test-evals` batched loop, the `build` converge loop, and the `grill` stage's
spec-confirmation rounds.

## Round names

**Every reviewer dispatch after R1 is a confirm round — whatever the brief
calls it.** A "fix review", "re-close", "re-gate", "verification pass" or a
single reviewer checking one line: each is a round and counts against the
budget. One reviewer or three, one finding or twenty, it's one round. Run
`scripts/review_budget.py round <ledger-dir>` before every dispatch; it
refuses the rounds this protocol doesn't allow, and the brief's round line is
stamped from it (`briefs/scripts/stamp_brief.py`).

- **R1 — first review.** Full review of the work's diff against its base
  (after Step A's two-axis pass). Reviewers may report anything in the diff.
- **R2, R3, … — confirm rounds.** Each one checks the previous fix round. Its
  scope is the FIX DIFF only (see *Scope*), not the whole change again.
- **Gate round.** The three-reviewer pass before a live deploy, on the NET diff
  (session base → HEAD). It sits OUTSIDE the tier's confirm-round budget: a
  live deploy adds exactly one gate round plus at most one re-gate (see
  *Three-reviewer deployment gate*), on top of R1 + the tier budget. T0 has a
  0-round budget but still runs the gate before a live deploy — it is that
  tier's only review round.

## Severity — and what keeps a loop open

Every finding carries one label:

| Label | Meaning | Keeps the loop open? |
|---|---|---|
| **BLOCKING** | wrong result, data loss, security hole, crash on a real path | yes |
| **MAJOR** | real bug on a reachable path, or a spec requirement missing | yes |
| **MINOR** | real but low-impact, edge-only, or hardening | **no** |
| **NIT** | style, naming, wording | **no** |

Only open BLOCKING/MAJOR findings justify another confirm round. MINOR and
NIT findings go to the **deferred list** (one line each, in the ledger or the
fix brief's "deferred" section). They are fixed in ONE batch with the last
real fix round if cheap, or left recorded — they never trigger a round on
their own.

Severity is the orchestrator's call, not the reviewer's: re-rate each finding
after reproducing it (see *Repro-before-fix*), and record it with
`review_budget.py finding` (which applies the two caps below).

**Test-only findings are at most MINOR.** A finding about test code alone —
a fixture date that expires, a test's time zone, an unasserted field, a test
name — is MINOR whatever the reviewer called it, unless that test is the ONLY
coverage of a BLOCKING/MAJOR behavior (`--sole-coverage`). Fix them in the
last real fix round or defer them; they never open a round.

**Every finding gets a class**: the mechanism, input family or invariant it
belongs to ("revision-state", "pagination", "public-route auth"). The
same-class stop counts by class, so name it consistently across rounds.

**Reachability sets the ceiling:**

- **Unreachable scenario → NIT.** If no production entry point can produce
  the scenario (definition and examples in
  `orchestrator/references/coding-principles.md` § Unreachable scenarios), the
  finding is a NIT whatever the reviewer called it — recorded, never looped
  on — and the usual fix is no code at all: adding handling for an impossible
  case is the speculative error handling the coding principles rule out. To
  rate it higher, the reviewer (or your repro) must name the entry point that
  reaches it.
- **Reachable but can't trigger on the live surface → MINOR.** Real code, a
  real path, but the production data or layout can't hit it today (e.g. a
  header layout the live sheet doesn't have).
- **Input from outside the process is always reachable.** User input, files,
  network, environment, config, other services, concurrent writers: missing
  validation, auth or error handling there is rated on impact like any other
  bug — never discounted as "impossible".

## Scope — confirm rounds look at the fix, not the whole change

A confirm round's input is `git diff <previous-round-commit>..<fix-commit>`.
The reviewer answers three things, nothing more:

1. **Per prior finding:** `RESOLVED` | `RESOLVED-BUT <residual>` |
   `NOT-RESOLVED — <why>`. List every prior BLOCKING/MAJOR finding by ID (the
   reviewer has no memory) with the fix made for it.
2. **Fix-induced problems (NEW-N):** "Did these fix lines introduce a new
   problem? List as NEW-N with severity and the fix-diff line, or 'no new
   problems'." Mandatory — fixes cause regressions — but scoped to lines the
   fix diff changed.
3. **Verdict:** `SHIP | DO-NOT-SHIP` (code) or `SHIP | REQUEST CHANGES`
   (spec), one line of justification.

Anything else a reviewer reports — issues in code the fix did not touch,
pre-existing behavior, design re-litigation — is labeled **OUT-OF-SCOPE-N**.
It goes to the deferred list and does not keep the loop open, with one
exception: an out-of-scope BLOCKING that you reproduce is promoted to a
finding (security holes and data loss don't wait).

Carry two lists in every confirm prompt so reviewers don't re-litigate:
- **Accepted limitations / decisions** — do NOT re-report.
- **Builder's declared interpretations** — accept or reject each, with evidence.

RESOLVED-BUT residuals: a BLOCKING/MAJOR residual stays open; a MINOR one is
deferred like any other MINOR.

## Who reviews each confirm round

- R1: every reviewer the tier uses (roles in `orchestrator/references/lanes.md`; pins in the lanes config).
- Confirm rounds: a reviewer is re-dispatched only if it still has an open
  BLOCKING/MAJOR finding, or the fix diff touches code its findings were
  about. A reviewer that returned SHIP with nothing open drops out.
- With several reviewers, HOLD the fix round until every dispatched reviewer's
  verdict lands, then merge into ONE deduped fix list and fix once. Patching
  between verdicts makes late reviewers judge stale code. A brief-supersede
  mechanism exists (`briefs/references/fix-brief-template.md`) for a fix dispatch that already
  started against an incomplete verdict set — it is a recovery path, not an
  exception to this rule.
- **Freeze the tracked tree between dispatch and read verdicts.** Reviewer CLI
  processes run against the checked-out tree: no code edits, no commits to
  tracked files, no regenerating derived files a reviewer might read until
  every verdict is in. (A reviewer that catches mid-review churn must re-read
  every cited region at `git show <target-sha>:<path>` and say so — that
  weakens its citations and can void the round.) Fix-commits and brief/diff
  artifacts for the NEXT round wait in the working tree or a scratch dir.
- Track every dispatch to a read verdict: ledger row per (round, reviewer,
  log path, verdict-read Y/N).

## Round budget (hard)

The budget is the risk-derived tier's confirm-round count
(`orchestrator/references/risk-routing.md`; compatibility table in
`size-tiers.md`): T0 = 0, T1 = 1, T2 = 2, T3 = 3. Set it before R1 and say it:
"T2: R1 + up to 2 confirm rounds."

When the budget is spent and BLOCKING/MAJOR findings are still open, STOP.
Do not dispatch another round. Give the user the open set and a choice:

- **Redesign** the part that keeps failing (see *Same-class stop*),
- **One more round** on the named findings only — an explicit budget extension, or
- **Explicitly accept the residual risk**, with the open findings recorded
  at the acceptance. An exhausted budget by itself is never SHIP;
  open BLOCKING/MAJOR or failing acceptance tests are NOT SHIP.

A user's "review loop N times" means N reviews in total — R1 plus up to N−1
confirm rounds — for that task, whatever the tier. "Review
loop until clean" means: until no open BLOCKING/MAJOR, within the tier's
budget — then ask.

## Stop conditions — check after every round, in this order

1. **Ship.** No open BLOCKING/MAJOR (deferred MINOR/NIT/OUT-OF-SCOPE are fine)
   and every dispatched reviewer's verdict is in, and the full acceptance
   suite ran green after the last fix. → SHIP. Don't run another
   round to get a cleaner report.
2. **Same-class stop.** The second finding of the same class (same mechanism,
   same input family, same invariant — e.g. a second escaping bypass, a
   second race on the same lock) → stop patching instances. Update the rule's
   case table first (`briefs/references/case-tables.md` — the missing cases
   are rows), then write ONE redesign brief from the table and ask reviewers
   to probe that class. A third same-class finding means the design is wrong:
   take it to the user. (`review_budget.py status` reports REDESIGN at two and
   refuses the next round at three.)
3. **No-progress stop.** Open BLOCKING+MAJOR count did not go down from the
   previous round, or a RESOLVED finding re-opened → stop, re-read the code
   yourself, and decide with the user. A fix round that makes things worse is
   not fixed by another fix round.
4. **Fix-quality stop.** More than half of a round's findings are
   fix-induced (NEW-N) → the fix briefs are too loose or the fixes too wide.
   Before the next round: tighten the brief (one finding per item, named
   failing test, "touch only these lines"), or make the trivial fixes
   yourself.
5. **Budget stop.** Budget spent → the choice above.

## Repro-before-fix

For each claimed finding, reproduce it with a minimal probe BEFORE it enters a
fix brief. Reviewer claims are mostly real (~80%); reproducing tells you the
true severity and gives the builder a failing case.

- Construct the exact pre-state the reviewer described, not a nearby one.
- A probe only counts if it could have shown the bug: seed it with the data
  the bug would consume. Zero-effect probe = no evidence.
- If the reviewer saved probe scripts, read the script before rebuilding the
  repro from its prose.
- A finding you cannot reproduce goes in as "verify-first" with your probe
  evidence — never silently accepted, never silently dropped.
- Re-run against current HEAD: a report is a snapshot; fixes may have landed.
- Build each round's repro fresh in a new temp dir; old probes carry state.

## Fix rounds

- One fix round per review round: all of that round's reproduced
  BLOCKING/MAJOR findings, deduped across reviewers, in one brief. Never a
  brief — or a review — per finding: a one-line fix rides in the round's fix
  diff with everything else, and the next confirm round checks them together.
- Brief per finding: behavior contract, exact fix, the failing-first test by
  name, "touch only what this finding needs". Multi-mechanism bugs: both
  halves in the same item.
- Trivial fixes (≤ ~10 lines, mechanical, no design choice) the orchestrator
  may make directly — say so. Everything else goes to the builder lane.
- Before the next confirm round, verify the fix LANDED (re-read the region,
  re-run the regression test, see the case flip) and that the new test fails
  with the fix reverted (gut the fixed function, run, restore). A test that
  passes without the fix is not coverage.
- Commit each fix round after your own verification; the next confirm round's
  diff is that commit against the previous round's commit.

## Ledger — `scripts/review_budget.py`

Every loop keeps its ledger in `.hermes/reviews/<loop>/budget.json`,
maintained only through the script:

```
review_budget.py init     <dir> --tier T2 [--kind gate]   # before R1
review_budget.py round    <dir> --scope <diff>            # before EVERY reviewer dispatch
review_budget.py dispatch <dir> --reviewer codex          # per reviewer in the round
review_budget.py finding  <dir> --id C1 --severity MAJOR --class revision-state [--test-only] [--unreachable]
review_budget.py close    <dir>                           # when every verdict is read
review_budget.py resolve  <dir> --id C1 --status fixed    # after the fix round
review_budget.py resolve  <dir> --id C1                   # the confirm verdict says RESOLVED
review_budget.py status   <dir>                           # SHIP / CONTINUE / REDESIGN / ASK-USER
review_budget.py extend   <dir> --by 1 --reason "..." --approved-by <user>   # the user's decision
```

`round` refuses (non-zero) when the budget is spent with BLOCKING/MAJOR
open, when a same-class or no-progress stop applies, and when nothing is
open (SHIP). Only `extend`, recording the USER's decision, lets the loop
continue past a refusal. Report `status` to the user when they ask how the
review is going; it is also what the stop conditions read.

## Three-reviewer deployment gate

User's standing instruction: before any LIVE deploy, all three reviewer lanes
(A + B + C per the roles in the lanes config) must return SHIP.

- Run it ONCE, as the gate round, after the loop has converged — not on every
  round (user-confirmed 2026-10-26). It reviews the NET diff (session base → HEAD), dispatched in
  parallel from the repo cwd, read-only.
- The gate round follows this protocol: severity floor, stop conditions, with
  one scope difference: it reviews the FULL net diff, and OUT-OF-SCOPE here
  means "outside the net diff" — not "outside the last fix diff". A
  gate-round BLOCKING/MAJOR gets one fix round and a re-gate by the reviewers
  that raised it; anything beyond that goes to the user.
- The gate keeps its own ledger (`review_budget.py init <dir> --kind gate`):
  the gate round plus ONE re-gate, whatever the tier. The re-gate is a
  confirm round — it reviews the fix diff, not the net diff again, with the
  Confirm brief from `briefs/references/review-briefs.md`.
- For a port/adoption from a public repo, the net diff is the whole session
  delta against the pre-session baseline.

Worked example (T3 — a live deploy classifies R3, so its review tier is T3):
budget = R1 + 3 confirm rounds → R1 (all three lanes, 1 BLOCKING) → second
confirm round (fix confirmed clean) → third confirm round (fix confirmed
clean) → Step B loop converges → gate round = all three lanes on the NET diff
(outside the budget) → one reviewer raises a gate BLOCKING → one fix round →
re-gate by that reviewer → all three SHIP → push. If the third confirm round
still left BLOCKING/MAJOR open, budget stop → ask the user before any further
round. The gate runs only after the loop converges.

## Milestones — the gate never meets a whole product

A gate (or any R1) reviews one milestone: one build phase, one feature, or one
reviewable slice — a net diff a reviewer can hold in mind, as a guide ≤ ~3,000
changed lines of code (`stamp_brief.py` refuses review diffs over 5,000 lines
unless `--allow-large` records why). A greenfield product is reviewed phase by
phase as it is built (the build plan's phases), each through its own loop and,
if it goes live, its own gate. A final gate over several milestones reviews
only what changed since the last milestone that passed, plus the integration
seams between milestones — never the whole product as its first full review.

## Spec and design documents

Same protocol, with these differences (details in `spec-convergence.md`):
the artifact is the document, the verdict is `SHIP | REQUEST CHANGES`, the
NEW-N hunt asks about contradictions the revision introduced between
sections, and ONE reviewer running confirms to SHIP is enough once R1's
reviewers agreed on the blockers.

## What made loops run to R10+ (don't reintroduce these)

v0.1.x loops ran past ten rounds because these rules stacked:

- every confirm round re-read the "fresh full-state diff", so reviewers kept
  finding new issues in code the fixes never touched;
- a mandatory NEW-problem hunt with no severity floor, so any MINOR or NIT
  kept the loop open;
- all three reviewers on every round, and "never end on a single reviewer's
  confirm", so the union of three fresh hunts had to come back empty;
- RESOLVED-BUT residuals always "fix in this pass";
- a "deep sweep" exception that excused rising finding counts, and worked
  examples (6 rounds, 5 rounds) presented as normal;
- three different caps (3 cycles, 5 rounds, "> 5 rounds means churn") and no
  rule saying which one wins;
- even one-line fixes had to go through a builder dispatch, and loose fix
  briefs caused fix-induced regressions that the next round then found.

v0.3.0 had the rules but not the counting, and one gate still ran 15 fix
rounds and 8 re-close rounds in an evening:

- single-reviewer "fix reviews" (lettered D, E, F … P) were treated as not
  being rounds, so the budget never applied — now every dispatch after R1 is
  a round, counted by `review_budget.py`;
- test-only findings (a fixture month expiring next year, a test's time zone,
  an unasserted field) were rated MAJOR and each got a round — now capped at
  MINOR;
- one-line fixes got their own review round — now they ride in the round's
  batch;
- re-close rounds re-reviewed the full 40,000-line diff — now re-gates use the
  fix diff;
- a correction rule written as one paragraph was designed by reviewer
  counterexample, one round per case — now stateful rules get a case table
  before the build, and the same-class stop sends missing cases back to it;
- briefs carried facts typed from memory (two different SHAs, stale test
  counts, "two fix rounds" after fifteen) — now briefs are stamped;
- the gate was the first full review of the whole product — now gates review
  one milestone.
