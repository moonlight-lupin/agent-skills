---
name: decision-log
description: "ADR-style decision journal for agents and teams. Create numbered decision records, track superseding chains, schedule periodic reviews, and search past decisions to avoid re-litigating settled questions."
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [decisions, adr, decision-log, architecture, review, superseding, decision-record]
  related_skills: []
---

# Decision Log

## Overview

Use this skill to keep durable, searchable decision records when a team or agent
needs to remember **what was decided, why it was decided, what alternatives were
considered, and when the decision should be reviewed**.

It solves recurring problems that chat history and meeting notes do not solve
well:

- Decisions get buried in long conversations and are hard to find later.
- The reasoning and constraints behind a choice are forgotten.
- Settled questions get re-litigated because there is no authoritative record.
- Reversals are made by deleting old context instead of preserving history.
- No review cadence exists, so time-sensitive decisions quietly go stale.

The pattern is ADR-style: one Markdown file per decision, numbered sequentially,
with status, context, options, decision, consequences, and review metadata. The
format follows the spirit of Michael Nygard's Architecture Decision Record (ADR)
pattern, generalized for product, operations, research, and team decisions.

Decision records live in a configurable directory:

- `--decisions-dir DIR` on every command, or
- `DECISIONS_DIR=/path/to/decisions`, or
- default `./decisions/` relative to the current working directory.

## Quick start

```bash
python scripts/decision_log.py new --title "Use SQLite for source-tracker"
```

The command creates the next numbered file, such as:

```text
./decisions/ADR-001-use-sqlite-for-source-tracker.md
```

Open the printed path, complete the sections, then change `## Status` from
`proposed` to `accepted` once the decision is approved.

## When to create an ADR

Create a decision record when the choice is meaningful enough that future people
will ask "why did we do this?" Examples:

- Architecture, storage, API, dependency, deployment, or security choices.
- Product or workflow choices that affect multiple users or future work.
- Trade-offs with real costs, constraints, or excluded alternatives.
- Decisions that may need review after a date, milestone, or external trigger.
- Reversals of previous decisions.

Do **not** create an ADR for trivial choices:

- Typo fixes, one-off refactors, or obvious implementation details.
- Choices already mandated by a clear standard or user instruction.
- Temporary scratch decisions that will not affect future work.

## ADR format

Each decision record is a Markdown file named:

```text
ADR-NNN-short-title.md
```

`NNN` is a zero-padded sequence number (`001`, `002`, ...). Do not hand-number
files unless you are migrating old records; use the CLI so numbers remain
consistent.

The sections are:

### Status

Allowed values:

- `proposed` — drafted but not yet adopted.
- `accepted` — active decision.
- `superseded by ADR-NNN` — replaced by a later decision.
- `deprecated` — intentionally retired without a direct replacement.

Never delete an old decision just because it changed. Supersede it so the audit
trail remains intact.

### Date

The date the record was created or accepted, in `YYYY-MM-DD` format.

### Context

The problem statement, background, constraints, forces, assumptions, and facts
that make the decision necessary. Good context explains why the decision is not
obvious.

### Options Considered

List meaningful alternatives and their pros/cons. Include the rejected options
that future readers are likely to ask about.

### Decision

State what was chosen and why. The "why" matters as much as the choice: tie the
selection back to constraints, trade-offs, and expected outcomes.

### Consequences

Record positive, negative, and neutral consequences. This prevents the record
from becoming only a justification memo; known downsides should be visible.

### Review

Record the review cadence, next review date, and trigger condition:

- Cadence: `monthly`, `quarterly`, `annually`, or `on-trigger`.
- Next review: `YYYY-MM-DD`, auto-computed for dated cadences.
- Trigger: optional condition that should prompt re-evaluation earlier than the
  scheduled review.

## Workflow 1: Create

Create a new decision with the default `quarterly` review cadence:

```bash
python scripts/decision_log.py new --title "Use SQLite for source-tracker"
```

Add initial context:

```bash
python scripts/decision_log.py new \
  --title "Use SQLite for source-tracker" \
  --context "Single-user local index, low write volume, simple backup needs."
```

Create in a specific directory:

```bash
python scripts/decision_log.py new \
  --title "Use hosted object storage for exports" \
  --decisions-dir ./docs/decisions
```

Choose a review cadence:

```bash
python scripts/decision_log.py new \
  --title "Adopt quarterly vendor review" \
  --cadence annually
```

Completion criterion: the CLI prints a new `ADR-NNN-short-title.md` path and the
file contains a filled title, date, cadence, and next review date when applicable.

## Workflow 2: List

List all decisions:

```bash
python scripts/decision_log.py list
```

Filter by status:

```bash
python scripts/decision_log.py list --status accepted
python scripts/decision_log.py list --status proposed
python scripts/decision_log.py list --status superseded
python scripts/decision_log.py list --status deprecated
```

Filter by topic text:

```bash
python scripts/decision_log.py list --topic storage
```

Completion criterion: the table shows ADR number, date, status, title, and path.

## Workflow 3: Supersede

When a decision changes, create the new decision first, then mark the old one as
superseded:

```bash
python scripts/decision_log.py new --title "Move source-tracker storage to Postgres"
python scripts/decision_log.py supersede 001 --by 005
```

This updates `ADR-001...md` to:

```text
## Status
superseded by ADR-005
```

and appends a link to the replacing ADR. The old context remains searchable.

Completion criterion: `list --status superseded` includes the old ADR, and
`timeline` shows the chain.

## Workflow 4: Search

Search full text across decisions:

```bash
python scripts/decision_log.py search "SQLite"
python scripts/decision_log.py search "backup"
```

The search returns matching ADRs and context snippets so you can avoid
re-litigating previously settled questions.

Completion criterion: matching ADR numbers, titles, paths, and snippets are
printed, or the CLI explicitly says no matches were found.

## Workflow 5: Review Schedule

Show decisions whose next review date is due:

```bash
python scripts/decision_log.py due-review
```

Use the cron-compatible checker for scheduled reminders:

```bash
python scripts/review_checker.py --decisions-dir ./decisions
```

Example weekly cron scheduler entry:

```cron
0 9 * * MON DECISIONS_DIR=/path/to/decisions python /path/to/scripts/review_checker.py
```

The checker is silent when nothing is due. When accepted decisions are due, it
prints a concise summary that can be delivered to a messaging platform by the
scheduler or wrapper you already use.

Completion criterion: due accepted decisions produce a message beginning with
`N decisions due for review:`; no due decisions produce no output from the
checker.

## Workflow 6: Timeline

Show superseding chains:

```bash
python scripts/decision_log.py timeline
```

Filter chains by topic:

```bash
python scripts/decision_log.py timeline --topic storage
```

Example output:

```text
ADR-001 → ADR-005 → ADR-012
```

Completion criterion: every chain shows oldest decision first and follows
`superseded by ADR-NNN` links forward.

## Review cadence options

- `monthly` — use for fast-moving decisions, experiments, vendor trials, or
  operational choices that could become stale quickly. Next review is date + 1
  calendar month.
- `quarterly` — default for most active product, architecture, and workflow
  decisions. Next review is date + 3 calendar months.
- `annually` — use for stable decisions where yearly validation is enough. Next
  review is date + 1 calendar year.
- `on-trigger` — use when a date is not meaningful. Leave `Next review` blank
  and write a concrete trigger, such as "review if monthly volume exceeds 1M
  records" or "review if a second team adopts this workflow."

Calendar-month calculations clamp to the last valid day of the target month. For
example, a monthly review from January 31 becomes February 28 or 29.

## File delivery

When a workflow produces or updates a file, provide the file path to the user so
they can open, review, and edit the Markdown record in their normal editor.

## Common pitfalls

1. **Deleting instead of superseding.** Deletion loses history. Mark old records
   `superseded by ADR-NNN` and keep the file.
2. **Missing context.** A decision without constraints and rejected options will
   not prevent future re-litigation. Write enough background for a new reader.
3. **No review date.** Accepted decisions with dated cadences should have a
   `Next review` value. Use `on-trigger` only when the trigger is concrete.
4. **Unnumbered files.** Files outside the `ADR-NNN-short-title.md` pattern will
   not be included in list, review, or timeline commands.
5. **Status drift.** Use exactly `proposed`, `accepted`, `superseded by ADR-NNN`,
   or `deprecated` so filters and reminders work.
6. **Superseding before writing the replacement.** Create the new ADR first so
   the old ADR can point to an existing record.
7. **Vague triggers.** "Review later" is not a trigger. Use measurable events,
   dates, thresholds, or dependency changes.

## Verification checklist

- [ ] New files are named `ADR-NNN-short-title.md` and numbers are sequential.
- [ ] Each ADR has Status, Date, Context, Options Considered, Decision,
      Consequences, and Review sections.
- [ ] Active decisions have `accepted` status once approved.
- [ ] Changed decisions are superseded, not deleted.
- [ ] `python scripts/decision_log.py list` shows the expected records.
- [ ] `python scripts/decision_log.py due-review` finds due records.
- [ ] `python scripts/decision_log.py timeline` shows superseding chains.
- [ ] The cron scheduler runs `review_checker.py` with the intended
      `DECISIONS_DIR` or `--decisions-dir`.
- [ ] When files are created or updated, their paths are provided to the user.

## Files

- `scripts/decision_log.py` — main CLI for create, list, supersede, search,
  due-review, and timeline.
- `scripts/review_checker.py` — silent-when-empty reminder checker for cron
  schedulers.
- `templates/decision-template.md` — blank ADR template.
- `references/adr-format.md` — section-by-section ADR writing guide.
- `references/review-cadence.md` — cadence and trigger rules.
