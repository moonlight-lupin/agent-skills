# Case Tables — the spec sheet for rules with state

A rule written as prose ("corrections tombstone the old fact and re-ingest;
the oldest month is never corrected; aged-out rows are retained") reads as
complete and isn't. Each case it doesn't spell out becomes a reviewer
counterexample, a fix round, and a confirm round. A case table forces the
cases out BEFORE the build, where a missing row costs a line, not a round.

## When a case table is required

Write one in the `spec` plan turn (S2/S3 always; S1 when the rule below
applies) for any rule where the result depends on history, not only on the
current input:

- corrections, revisions, tombstones, soft deletes, versioning
- idempotence, retries, re-runs, duplicates, re-transmissions
- snapshots, rolling windows, age-out, floors, backfills
- caches and invalidation; sync with an external source of truth
- draft → post / pending → active lifecycles, holds, locks
- permission matrices (role × route × method), public vs signed-in surfaces
- time boundaries: month/day/quarter keys, time zones, DST

## Format

One table per rule. Columns:

| # | Prior state (history) | Event / input | Expected observable result | Invariant it protects | Test name |
|---|---|---|---|---|---|

- **Prior state** is what already exists (posted facts, holds, cache entries,
  sessions), written concretely: "month M has posted rows a, b".
- **Expected observable result** is what a caller sees through the public
  seam — a count on a page, an API response, an HTTP status — not internal
  table state. That keeps each row testable at the seam (`test-evals`).
- **Test name** is filled by `test-evals`, which writes each row as a RED test.

## Dimensions to enumerate (go down the list; skip only with a reason)

1. First sight (nothing exists yet)
2. Unchanged repeat (same input again)
3. Change to one item among several (one corrected, neighbours untouched)
4. Addition beside existing items
5. Absence (an item missing from the new input — deleted, or aged out?)
6. Revert (A → B → A)
7. Partial failure (some items fail mid-batch) and retry of the same batch
8. Duplicate items within one input
9. Boundaries: oldest/newest period, floor, window edge, time-zone edge
10. Ordering: out-of-order arrival, two batches in flight, concurrent writers
11. Who: anonymous, each role, the owner, a different tenant
12. Everything at once: the realistic mixed batch (unchanged + changed + new + missing)

## Worked example (shape only)

Rule: a feed delivers monthly snapshots; a posted fact is never edited — a
correction reverses it and adds a replacement; rows that drop out of the
source's rolling window are retained.

| # | Prior state | Event | Expected observable result | Invariant | Test |
|---|---|---|---|---|---|
| 1 | M empty | snapshot offers a, b | M shows 2 | first sight | |
| 2 | M posted a, b | snapshot offers a, b unchanged | M shows 2; nothing reversed | idempotent repeat | |
| 3 | M posted a, b | offers a, b′ (b corrected) | M shows 2; b reversed, b′ active | one active fact per row | |
| 4 | M posted a, b | offers a, b, c | M shows 3; nothing reversed | additions don't revise | |
| 5 | M = oldest window month, posted a, b | offers b only (a aged out) | M shows 2; a retained | age-out ≠ deletion | |
| 6 | M posted a; then corrected to a′ | offers a again | M shows 1 (a active, a′ reversed) | revert yields one fact | |
| 7 | M posted a, b | offers a, b′, row x fails | b′ not posted until a clean re-run; M shows 2 | no dual-active facts | |
| 12 | M posted a, b; M+1 empty | offers a, b′, c (M) + d (M+1) | M shows 3, M+1 shows 1 | mixed batch | |

The v0.3.0 project that prompted this skill found rows 2, 5, 6, 7 and 12 one
review round at a time — each as a BLOCKING/MAJOR finding after the code was
written.

## Rules

- **Review the table once, before the build** — one reviewer lane, or the
  Goldfish review at S2/S3. Reviewing twenty rows is cheaper than reviewing
  the code twenty times.
- **Each row becomes a RED test** in `test-evals`, at the public seam.
- **A review finding that is a missing row is a design change:** add the row
  (and its test) to the table first, then brief the fix from the table. Two
  missing rows of one rule is the confirm-round protocol's same-class stop —
  rework the rule against the whole table, don't patch rows one by one.
- **Keep the table with the spec** (`.hermes/specs/` or the project's design
  docs) and link it from every brief that touches the rule.
