# ADR Format Guide

Architecture Decision Records (ADRs) are short documents that capture an
important decision and its rationale. This skill uses the ADR pattern popularized
by Michael Nygard's original blog post on documenting architecture decisions,
then broadens it for product, operations, research, and team workflow choices.

An ADR should be durable enough that a future reader can answer:

1. What did we decide?
2. Why did we decide it?
3. What alternatives did we reject?
4. What consequences did we knowingly accept?
5. When or why should this decision be revisited?

## File name and title

Use one file per decision:

```text
ADR-NNN-short-title.md
```

The first heading mirrors the number and title:

```markdown
# ADR-001: Use SQLite for source-tracker
```

Keep the title concrete. Prefer "Use SQLite for source-tracker" over "Database
choice".

## Status

The status section contains a single value:

```markdown
## Status
accepted
```

Allowed values:

- `proposed` — still under discussion.
- `accepted` — current active decision.
- `superseded by ADR-NNN` — replaced by a later decision.
- `deprecated` — retired with no direct replacement.

Use `superseded by ADR-NNN` instead of editing old records to pretend the newer
decision was always true. The point of an ADR log is to preserve the reasoning
chain.

## Date

Use ISO date format:

```markdown
## Date
2026-07-06
```

The date is usually the draft date for proposed records and the acceptance date
for accepted records. If a proposed record sits for a while before acceptance,
update the date when you change the status to `accepted` if that distinction
matters for review cadence.

## Context

Context is the most important section. It should explain the forces around the
decision, not just restate the title.

Include:

- Problem statement.
- Current state and pain points.
- Constraints: time, cost, privacy, portability, performance, maintenance,
  user expectations, compliance, integration boundaries.
- Assumptions that might later prove false.
- Prior decisions that shaped this choice.

Example:

```markdown
## Context
The source-tracker needs a local index for fewer than 100k source records per
user. It must run without a server, be easy to back up, and support simple
queries by URL, status, and last-seen timestamp. Concurrent writes are rare.
```

Avoid:

```markdown
## Context
We need a database.
```

That does not explain why the choice was non-trivial.

## Options Considered

List the real alternatives. Include enough pros and cons that future readers can
see why rejected options were rejected.

Example:

```markdown
## Options Considered

### Option A: SQLite
- Pros: local file, no service dependency, easy backups, mature tooling.
- Cons: limited concurrent writes, migrations still need discipline.

### Option B: Postgres
- Pros: strong concurrency, familiar SQL, production-grade operational model.
- Cons: requires a running service, heavier setup for a single-user tool.
```

Good options are comparable. If an option was never viable, say why briefly, but
do not pad the section with straw men.

## Decision

State the choice and rationale directly:

```markdown
## Decision
Use SQLite for the first source-tracker implementation. It satisfies the local,
serverless, low-write-volume constraints with the least operational overhead.
If multi-user writes become a requirement, revisit this decision.
```

A good decision section includes both:

- **What** was chosen.
- **Why** this option won given the context.

## Consequences

Document positive, negative, and neutral consequences. This makes trade-offs
explicit and prevents the ADR from becoming a one-sided justification.

Example:

```markdown
## Consequences
- Positive: setup remains single-file and portable.
- Negative: write concurrency is limited; long-running writes need care.
- Neutral: schema migrations still need versioning even though deployment is
  local.
```

Consequences can become review prompts later.

## Review

Every ADR should say how it will be revisited:

```markdown
## Review
- Cadence: quarterly
- Next review: 2026-10-06
- Trigger: review earlier if two or more users need concurrent writes.
```

Use a date cadence when the decision could age out quietly. Use `on-trigger`
when a measurable event matters more than time.

## Complete example

```markdown
# ADR-001: Use SQLite for source-tracker

## Status
accepted

## Date
2026-07-06

## Context
The source-tracker needs a local index for fewer than 100k source records per
user. It must run without a server, be easy to back up, and support simple
queries by URL, status, and last-seen timestamp. Concurrent writes are rare.

## Options Considered

### Option A: SQLite
- Pros: local file, no service dependency, easy backups, mature tooling.
- Cons: limited concurrent writes, migrations still need discipline.

### Option B: Postgres
- Pros: strong concurrency, familiar SQL, production-grade operational model.
- Cons: requires a running service, heavier setup for a single-user tool.

## Decision
Use SQLite for the first implementation because it satisfies the local,
serverless, low-write-volume constraints with the least operational overhead.

## Consequences
- Positive: setup remains single-file and portable.
- Negative: write concurrency is limited; long-running writes need care.
- Neutral: schema migrations still need versioning.

## Review
- Cadence: quarterly
- Next review: 2026-10-06
- Trigger: review earlier if multi-user concurrent writes become required.
```

## Writing checklist

- [ ] Title is concrete.
- [ ] Status is one of the allowed values.
- [ ] Context explains the forces and constraints.
- [ ] Options include real alternatives with pros and cons.
- [ ] Decision states what and why.
- [ ] Consequences include at least one downside or risk when one exists.
- [ ] Review cadence and trigger are explicit.
