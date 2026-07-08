# Review Cadence Rules

A decision record is useful only if stale decisions are revisited. The review
section gives each active decision either a date-based review schedule or a
concrete trigger condition.

## Cadence options

### monthly

Use `monthly` for decisions that can become wrong quickly:

- experiments and pilots;
- temporary process choices;
- vendor trials;
- operational workarounds;
- decisions tied to fast-changing usage, cost, or reliability data.

Computation: decision date + 1 calendar month.

Example:

```markdown
## Review
- Cadence: monthly
- Next review: 2026-08-06
- Trigger: review earlier if weekly failure rate exceeds 2%.
```

### quarterly

Use `quarterly` as the default for active architecture, product, workflow, and
operations decisions. It is frequent enough to catch drift without making review
noise too high.

Computation: decision date + 3 calendar months.

Example:

```markdown
## Review
- Cadence: quarterly
- Next review: 2026-10-06
- Trigger: review earlier if a second team depends on this interface.
```

### annually

Use `annually` for stable decisions where the environment changes slowly:

- durable standards;
- mature dependencies;
- naming conventions;
- stable governance or documentation practices;
- low-risk decisions whose cost of change is low.

Computation: decision date + 1 calendar year.

Example:

```markdown
## Review
- Cadence: annually
- Next review: 2027-07-06
- Trigger: review earlier if the underlying dependency enters maintenance mode.
```

### on-trigger

Use `on-trigger` when a calendar date is less meaningful than an event. Leave
`Next review` blank and make the trigger concrete.

Good triggers:

- `review if monthly volume exceeds 1M records`;
- `review if write concurrency becomes a product requirement`;
- `review if the vendor changes pricing materially`;
- `review if a second deployment environment is added`;
- `review if the dependency has no security update for 12 months`.

Weak triggers:

- `review later`;
- `review if needed`;
- `review if things change`.

Example:

```markdown
## Review
- Cadence: on-trigger
- Next review:
- Trigger: review if any customer requires SSO enforcement.
```

## Calendar-month calculation

The CLI computes next review dates by adding calendar months, not fixed day
counts:

- `monthly` = +1 calendar month;
- `quarterly` = +3 calendar months;
- `annually` = +12 calendar months.

When the target month has fewer days, the day clamps to the last day of that
month:

| Start date | Cadence | Next review |
| --- | --- | --- |
| 2026-01-31 | monthly | 2026-02-28 |
| 2024-01-31 | monthly | 2024-02-29 |
| 2026-11-30 | quarterly | 2027-02-28 |
| 2026-02-28 | annually | 2027-02-28 |

This matches how people usually interpret "one month later" and avoids drifting
reviews by using fixed 30- or 90-day offsets.

## How due review detection works

`decision_log.py due-review` scans all ADR files matching
`ADR-NNN-short-title.md`, extracts `Next review: YYYY-MM-DD`, and prints records
whose next review date is today or earlier. It ignores superseded and deprecated
records.

`review_checker.py` is designed for cron schedulers. It only reports accepted
records due for review and stays silent when nothing is due. This makes it easy
to wire into a weekly reminder without producing empty messages.

## Choosing the right cadence

Use the highest cadence that still protects the decision from going stale:

1. Is the decision temporary, experimental, or high-change? Use `monthly`.
2. Is it an active normal decision with meaningful future risk? Use `quarterly`.
3. Is it stable and low-change? Use `annually`.
4. Is a measurable event more important than a date? Use `on-trigger`.

If unsure, start with `quarterly`. You can change the cadence at the first
review.

## Review meeting prompt

When an ADR is due, answer these questions:

1. Is the original context still true?
2. Did any assumption fail?
3. Did any negative consequence become unacceptable?
4. Are the rejected options now better because constraints changed?
5. Should the decision remain accepted, be superseded by a new ADR, or be
   deprecated?

If the decision changes, create a new ADR and supersede the old one rather than
editing the old record into the new truth.
