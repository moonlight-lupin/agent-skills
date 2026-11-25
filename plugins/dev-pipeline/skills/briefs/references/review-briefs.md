# Review Briefs — R1, confirm round, gate

Three templates for briefing reviewer lanes. Fill the `<…>` parts by hand;
leave the `{{…}}` parts for `scripts/stamp_brief.py`. Rules behind them:
`review-commit/references/confirm-round-protocol.md`.

## Severity block (stamped into every review brief as {{SEVERITY_BLOCK}})

```
SEVERITY (dev-pipeline — use exactly these labels):
- BLOCKING: wrong result, data loss, security hole, crash on a real path.
- MAJOR: real bug on a reachable path, or a spec requirement missing.
- MINOR: real but low-impact or edge-only. Does not block ship.
- NIT: style, wording, cleanup. Does not block ship.
For every BLOCKING/MAJOR/MINOR, name the production entry point (route, CLI
command, tool, job) that reaches it. A scenario no entry point can reach is a
NIT. Input from users, files, network or config always counts as reachable.
A finding about TEST code only (a test's dates, fixtures, an unasserted
field, test naming) is at most MINOR — unless that test is the only coverage
of a BLOCKING/MAJOR behavior; then say so.
Tag every finding with a CLASS: the mechanism, input family or invariant it
belongs to (e.g. "revision-state", "pagination", "auth-public-routes").
```

## R1 — first review

```markdown
# R1 review — <project>: <change title>

{{ROUND_LINE}}

SCOPE: review ONLY the diff {{DIFF}} ({{DIFF_LINES}} lines, {{DIFF_FILES}} files;
base {{BASE}} → head {{HEAD}}), plus the current files it touches. Do not
review files the diff does not touch.

## What the change is
<3-6 lines: purpose, the spec/plan path, the case-table path if any.>

## Invariants to hold it to
<numbered, from the spec — what must stay true.>

## Review focus (ranked)
<3-5 items.>

## Do not re-report
<accepted limitations, owner decisions, documented out-of-scope items.>

## Verified state (stamped)
`{{TEST_CMD}}` → exit {{TEST_EXIT}}: {{TEST_TAIL}}

{{SEVERITY_BLOCK}}

## Verdict (mandatory, at the end)
VERDICT: SHIP or DO-NOT-SHIP
FINDINGS: numbered; each with severity, class, entry point, file:line, concrete fix.
```

## Confirm round

Send only to reviewers that still have open BLOCKING/MAJOR findings, or whose
findings' code the fix diff touched. One brief per round, all findings in it.

```markdown
# Confirm round — <project>: <change title>

{{ROUND_LINE}}

SCOPE: the FIX diff only — {{DIFF}} ({{DIFF_LINES}} lines; {{BASE}} → {{HEAD}}).
Do NOT re-read the whole change. Read a touched file in full only when a hunk
needs its context.

## Your open findings and what was done
| ID | Severity | Class | Fix made (hunk) |
|---|---|---|---|
| <id> | <sev> | <class> | <one line> |

## Builder's declared interpretations (accept or reject each, with evidence)
<list, or "none".>

## Do not re-report
<carried forward from every earlier round, grown this round.>

## Verified state (stamped)
`{{TEST_CMD}}` → exit {{TEST_EXIT}}: {{TEST_TAIL}}

## Answer exactly
1. Per finding: RESOLVED | RESOLVED-BUT <residual> | NOT-RESOLVED — <why>.
2. Fix-induced problems: did these fix lines introduce a new problem? List as
   NEW-N with severity, class, entry point and fix-diff line — or "no new problems".
   Anything outside the fix lines is OUT-OF-SCOPE-N (reported, not looped on).
3. VERDICT: SHIP or DO-NOT-SHIP, one line why.

{{SEVERITY_BLOCK}}
```

## Gate — three-reviewer, before a live deploy

Run once, after the loop converged, on the net diff of ONE milestone (see
`confirm-round-protocol.md` § Milestones). A gate gets one fix round and one
re-gate by the reviewers that raised findings; the re-gate uses the Confirm
template, not this one.

```markdown
# Deployment gate — <project>: <milestone>

{{ROUND_LINE}}

SCOPE: the net diff of this milestone — {{DIFF}} ({{DIFF_LINES}} lines;
{{BASE}} → {{HEAD}}). Every earlier milestone already passed its own gate.

## What ships
<5-10 lines.>

## Invariants
<numbered.>

## Already reviewed in this milestone's loop (do not re-report)
<the loop's resolved findings by ID + accepted limitations + owner decisions.>

## Verified state (stamped)
`{{TEST_CMD}}` → exit {{TEST_EXIT}}: {{TEST_TAIL}}

{{SEVERITY_BLOCK}}

## Verdict (mandatory, at the end)
VERDICT: SHIP or NO-SHIP — SHIP means you would stake a live deploy on this diff.
FINDINGS: numbered; severity, class, entry point, file:line, concrete fix.
```
