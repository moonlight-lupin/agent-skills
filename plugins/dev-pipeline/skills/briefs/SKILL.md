---
name: briefs
description: "Use when writing any brief another agent will act on in the dev-pipeline — a builder or fix brief, an R1 review brief, a confirm-round brief, a gate brief — or a case table (spec sheet) for a rule with state: corrections, retries, idempotence, rolling windows, caches, sync, permission matrices. Fills SHAs, diff paths, line counts, test results and the round line from commands (stamp_brief.py), never from memory. Triggers: 'write the brief', 'brief the builder', 'review brief', 'fix brief', 'gate brief', 'spec sheet', 'case table', 'decision table'."
metadata:
  version: 1.0.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [briefs, spec-sheet, case-table, decision-table, fix-brief, review-brief, gate-brief, dev-pipeline]
    related_skills: [spec, test-evals, build, review-commit, orchestrator]
---

# Briefs

A brief is the only thing a builder or reviewer knows about the task. Every
fact in it a command can produce comes from that command, and every brief
says what it is: its scope, its round, what not to re-report. This skill is
the single home for brief templates and for case tables.

Why it exists: a v0.3.0 gate ran 15 fix rounds and 8 re-close rounds on one
project. Three things in its briefs fed that: facts typed from memory (two
different SHAs and stale test counts in one brief, flagged by a reviewer in
three rounds), confirm briefs that sent reviewers back to the whole diff, and
a correction rule written as one paragraph of prose that reviewers then
designed one counterexample per round.

## The two jobs

1. **Briefs** — fill a template from `references/`, then stamp it with
   `scripts/stamp_brief.py`. Never dispatch an unstamped brief.
2. **Case tables (spec sheets)** — for any rule with state, write the table in
   `references/case-tables.md` BEFORE the build. Each row becomes a RED test.

## Which template

| You are briefing | Template | Read by |
|---|---|---|
| an implementer for one task | `build/references/per-task-workflow.md` § Step 1 | builder lane / subagent |
| a builder for a new capability against pre-written tests | `references/feature-build-brief.md` | builder lane |
| a builder fixing reproduced findings | `references/fix-brief-template.md` | builder lane |
| reviewers for R1 | `references/review-briefs.md` § R1 | reviewer lanes |
| reviewers for a confirm round | `references/review-briefs.md` § Confirm | only reviewers with open findings |
| the three-reviewer gate | `references/review-briefs.md` § Gate | lanes A + B + C |

Builder briefs carry the builder block from
`orchestrator/references/coding-principles.md`. Review briefs carry the
severity block from `references/review-briefs.md`.

## Stamping (mandatory)

```bash
python3 <plugin>/skills/briefs/scripts/stamp_brief.py brief.tmpl.md \
  --repo <repo> --base <sha> --head HEAD \
  --diff-out .hermes/reviews/<loop>/round-N.diff \
  --test-cmd "npm test" \
  --budget .hermes/reviews/<loop> \
  --out .hermes/reviews/<loop>/brief-round-N.md
```

It fills `{{BASE}}`, `{{HEAD}}`, `{{DIFF}}`, `{{DIFF_LINES}}`, `{{DIFF_FILES}}`,
`{{TEST_CMD}}`, `{{TEST_EXIT}}`, `{{TEST_TAIL}}`, `{{ROUND_LINE}}` and
`{{DATE}}`, and refuses (non-zero exit, nothing written) when:

- a `{{PLACEHOLDER}}` is left unfilled;
- the brief names a commit SHA that is neither BASE nor HEAD (stale SHA) —
  pass `--allow-sha` for a SHA you cite on purpose;
- `--budget` is given and no review round is open (run
  `review-commit/scripts/review_budget.py round` first — the round line comes
  from the ledger, so the brief can't claim "two fix rounds" when there were
  fifteen);
- the diff exceeds `--max-diff-lines` (default 5000) without `--allow-large`
  — split the review by milestone instead (`confirm-round-protocol.md`
  § Milestones).

## Rules for every brief

- **Scope line first.** R1: the change's diff. Confirm round: the fix diff
  only. Gate: the net diff, once. Never "the whole tree".
- **Round line.** `{{ROUND_LINE}}`, stamped from the ledger.
- **One brief per round,** listing every finding the round covers. No
  single-finding briefs with their own review: a one-line fix rides in the
  next round's fix diff.
- **Do-not-re-report list** — accepted limitations, adjudicated decisions,
  deferred items — carried forward and grown every round.
- **Facts from commands only.** Test counts, SHAs, line counts: stamped. If a
  fact can't be stamped, state where it came from.
- **No re-design in a fix brief.** If a fix changes a rule's behavior, update
  the case table first and brief from the new rows.

## Where it fits

`spec` (plan turn) writes case tables for stateful rules → `test-evals` turns
each row into a RED test → `build` dispatches with builder briefs →
`review-commit` dispatches with stamped review briefs, one per round, under
the budget ledger.
