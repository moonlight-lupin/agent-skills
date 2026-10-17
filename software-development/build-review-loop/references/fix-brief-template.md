# Fix-Brief Template for Review-Driven Fixes

When a review (Codex, Opus, or human) produces findings, the orchestrator
writes a fix brief that maps each finding to a concrete code change. The
builder (Cursor) reads the brief and implements all fixes in one pass.

## Contents

- Structure
- What Makes a Good Fix Brief
- Example (from a fix-round session, Aug 2026)
- Amend After Reviewer P3 Findings
- Superseding a fix brief mid-build
- Check the brief for self-contradiction before dispatching
- Orchestrator probe evidence in the brief
- Builder report items to adjudicate in the same round
- Probe every fix yourself before committing a round — including the negative space
- Version-bump rounds: bump all six pins in ONE commit, verify with the lockstep tests, never sed the changelog header blindly

## Structure

```markdown
# Fix Brief: <short title>

## Context

<1-2 sentences: what was reviewed, what was found, what is already done.>

The repo is at `<path>`, branch `<branch>`.

## Finding <ID>: <title>

**Files:** `<file paths>`

<1-2 sentence description of the problem.>

**Fix:**
1. <numbered steps — exact, actionable, no ambiguity>
2. <include line numbers or function names as anchors>
3. <if a test is needed, specify the test name and assertions>

<Repeat for each finding.>

## Constraints

- Do NOT modify <X> — it is already done / out of scope.
- Do NOT touch <Y> — separate concern.
- Run `<exact test command>` after all changes.

## Verification

After all fixes:
```
<exact test command>
```
All tests must pass. <Note expected skip count.>
```

## What Makes a Good Fix Brief

- **One finding per section** — the builder implements each fix independently.
- **Exact file paths and function names** — the builder does not search.
- **Numbered steps** — not prose. Each step is one action.
- **Constraints section** — what NOT to touch. This prevents the builder from
  re-implementing already-done fixes or touching unrelated code.
- **Exact verification command** — the builder runs this and reports results.
- **Do NOT include the review itself** — the brief distills the review into
  actionable steps. The builder does not need the review's reasoning.

## Example (from a fix-round session, Aug 2026)

The review produced 5 findings (F1-F5). F1 was already fixed by the
orchestrator (CSP header change). The brief covered F2-F5 only:

- F2: Delete dead `_pdf_reportlab()` function
- F3: Add `skipif` markers to 5 PDF tests
- F4: Split `ImportError` into `RenderError` + `ImportError`
- F5: Remove a stale unused constant, fix 2 vacuous tests

Each finding had exact file paths, numbered steps, and constraints
("Do NOT touch F1 — it is already done").

After the builder finished, Codex review found one P3 finding (stale
`pyproject.toml` comment). The orchestrator fixed it directly (a one-line
documentation fix) and amended the commit.

## Amend After Reviewer P3 Findings

When the reviewer (Codex) finds only minor (P3/Nit) findings — stale comments,
documentation typos, naming — the orchestrator can fix these directly and
`git commit --amend` rather than dispatching another full build round. This is
the exception to "orchestrator never hand-codes" (build-review-loop 'Cursor CLI is the BUILDER, Codex is the REVIEWER — never swap roles'):
P3 findings are documentation, not code logic, so cross-model diversity does
not apply. Use judgment — if the P3 finding touches code logic, dispatch
through the builder.

## Superseding a fix brief mid-build

When a second review round lands while the fix builder is already running (dual
reviews return at different times), do not wait — rewrite the brief file in
place so its content IS the merged round (round-2 wins where it overlaps; map
round-1 IDs to round-2 IDs so nothing double-fixes). The builder re-reads the
brief by path between findings. Then verify uptake from the builder's log
(see `persistent-loop-plan.md` steering rule #6): items it never re-read must
be re-probed after exit and dispatched as an enumerated follow-up if unfixed.
Also include in the merged brief: "note the F→O mapping in your report" so the
verification report is auditable against both reviews.

Timing caveat: a supersede only takes effect if the builder has not yet passed
its brief-read checkpoint. If the round-2 review arrives while the builder is
already deep in the old brief, expect the old scope to complete; grep the log
for the new item IDs — if absent, the round delivered round-1 only. The
follow-up dispatch then carries ONLY the still-failing items, each with fresh
orchestrator probe output as evidence. When the builder has just started,
killing it and re-dispatching with the merged brief is cheaper than supersede
plus follow-up.

## Check the brief for self-contradiction before dispatching

When one item gives two adjacent instructions, verify they agree against the
code they reference BEFORE dispatching — e.g. "exclude drafts" AND "mirror
pl_report.py's bucket logic" contradict when pl_report does NOT exclude
drafts. The builder implements instructions literally and will not flag a
contradiction; you get one of the two behaviors at random, and the next
reviewer flags the divergence against the source of truth as a fresh finding.
Self-contradiction in a brief is an orchestrator error that costs a round.
Also carry domain invariants as explicit brief rules, not assumptions:
financial aggregators must preserve currency buckets (sum per currency, never
across them — a unitless USD+JPY total is a wrong number that a trends chart
will render forever). Also check the brief's items for cross-surface drift:
when an item changes a metric's shape (string→bucket dict, scalar→dict),
enumerate EVERY consumer of the old shape in the brief — display formatters,
flattener metric lists, and the r3-era test file expectations (the r3 file is
the builder's own and editable; attested files are not). A missed consumer is
how a fixed producer leaves a stale display format or an orphan metric key
behind, reappearing as a fresh finding next round.

## Orchestrator probe evidence in the brief

Each finding carries the orchestrator's probe verdict (confirmed / variant /
not-reproduced) with the observed output inline — the builder should not
re-derive a reproduction that already exists. A 'not reproduced' verdict must
say why the orchestrator's own probe was ambiguous (aliasing, missing
reference bytes) and instruct the builder to re-probe first. Findings the
orchestrator could neither confirm nor dismiss go to the builder marked
'RE-VERIFY FIRST, then fix or report back' — never silently dismissed.

## Builder report items to adjudicate in the same round

Read the builder's final report for three item classes and rule on each before
the next dispatch: (1) **accommodations** — 'left lenient where the strict form
would break an attested fixture' → accept as fixture-mandated and bind it in
the next review prompt, or schedule a re-attestation; (2) **disagreements** —
'the brief's clause was wrong because X' → verify the reason, accept as settled
design or re-dispatch with corrected reasoning; an accepted disagreement that
stays unbound re-enters the next review as a fresh finding; (3) **line-count
or size gates tripped** — a builder hitting a file-size cap may extract a
helper into a NEW module; treat the extraction as a
reviewable structural change, not a mechanical move: it creates a new import
surface the next brief's consumer inventory must include.

Fourth item class: **contract-test contradictions** — 'test X assumes Y, the
spec says Z, I stopped instead of touching the test'. That stop is the
contract working; treat it as success (SKILL.md see `review-findings-adjudication.md` — own the fixture fix). Adjudicate by
checking the SPEC first: when the builder is right, the fix is an
orchestrator-side test edit (test-only code, no builder dispatch) that makes
the test deterministic against the spec — then re-run the suite before
committing, and re-attest the test in the same commit if it was attested.
Record the adjudication in the delivery so the reviewer sees the contract
test changed and why.

## Probe every fix yourself before committing a round — including the negative space

The orchestrator's verification after each fix round is probe-first: import
the fixed function, run the minimal temp-dir probe with the REAL producer
shape, and compare observed vs wanted output. Probe the ADJACENT behavior in
the same pass — the guard's sibling call sites, the same rule's boundary
values, the standing properties (byte-identical render vs pre-feature
baseline, real settlement still works after adding false-settlement guards,
live-install divergence probe still reports the known divergence). A fix
brief's item list can be fully green while a standing property broke
undetected; the standing probes are what catch that. Record each probe's
want/observed pair in the round report — it is the evidence the delivery and
the next review prompt reuse.

## Version-bump rounds: bump all six pins in ONE commit, verify with the lockstep tests, never sed the changelog header blindly

For a release round:
bump plugin.yaml, pyproject.toml, the entrypoint VERSION constant,
.claude-plugin/plugin.json, .claude-plugin/marketplace.json, and the README
status line with one targeted sed each (verify each file with grep after),
then run the lockstep tests (`test_plugin_structure.py`) BEFORE the full
suite — 87 tests, seconds — so version drift fails locally instead of in CI.
Finalize the CHANGELOG entry in the same commit (a builder-era entry headed
"Pre-release round of..." must be rewritten to the release framing before the
push), commit "release: vX.Y.Z", push, then watch CI with
`gh run watch <id> --exit-status` in a background session before tagging.
