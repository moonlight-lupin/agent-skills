# Comparison mode and research recipes

## Comparison mode (items × fields)

For a question of the shape "compare these N things on these M points" — companies,
products, markets, providers, funds — run the research as a grid instead of free-form
sub-questions.

**1. Draft the outline and get it approved before any search.**

```
## Comparison outline
Question: [user's question]
Items (rows):    [item 1], [item 2], …          (up to ~12; more → split into batches)
Fields (columns):
| Field | Definition | Unit / format | Preferred source | Shelf life |
|---|---|---|---|---|
| [field] | [exactly what counts] | [units, %, date …] | [filing, own site, results …] | [from evidence-hygiene.md] |
Out of scope: [what is deliberately excluded]
```

Show it to the user and wait for approval. Adding, dropping or redefining an item or field is
cheap now and expensive after the searches. If the user is not available, proceed on the best
outline and state it in the plan and the report. Save it to `<run_dir>/outline.md`.

**Budget for the grid, not for a question.** The Step 1 presets are sized for sub-questions;
a grid needs more. Set the search budget to **at least one query per item plus two** for
market-wide context and one refute query, and the fetch cap to **one per item for its best
primary source** plus two. Quote the resulting budget in the plan. Never split a fixed preset
across the items — a 9-query budget over 8 items leaves each one a single snippet and the
context section empty.

**2. Research each item.**

**Latest primary disclosure first.** Each item's first query targets its own most recent
disclosure — results announcement, annual or interim report, the item's own site, a regulator
filing — and records its as-of date. Only then fill the cells:

- A cell takes the **newest** figure found anywhere in the run. Before writing a cell from a
  search summary or an older filing, check that the run has not already seen a later one
  (interims after full-year, a completion release after an offer).
- A figure from an aggregator, vendor table or summary site may fill a cell only when no
  disclosure by the item itself was found; label it ("vendor table, undated") and note it
  under Gaps. A page that summarises a filing (a market-data site, a news write-up) is
  secondary, not primary, even when it quotes the filing.

**Stay on the grid.** Every query answers a field of the approved outline or one of the
market-context lines. Anything else found on the way goes in at most one "Also noted" line,
never in the table, and earns no further searches.

One item per pass, or one subagent per item (`delegate_task`, Subagent Mode: split the search
and fetch budget, never delegate the synthesis, verify every URL, run `check-quote` yourself).
Each item fills one row per field:

| item | field | value | as_of | source [N] | label | note |
|---|---|---|---|---|---|---|

Save the rows to `<run_dir>/rows.csv`. A field with no source stays empty with a note ("not
published", "not found") — never estimated to fill the grid. Facts still go through §3c:
tier, label, quote anchoring, source families.

**3. Build the report from the rows.** The comparison table comes first (the overview
position), with empty cells shown as "—" and explained in Gaps. Then a short section per item
or per field, whichever reads better, and the usual Contradictions, Gaps and Sources sections.
Stale cells (older than their shelf life) are marked in the table.

**Tested** (Nov 2026, blind paired runs against the previous version on one company
comparison, judged on six criteria): with the latest-disclosure and stay-on-the-grid rules the
grid won 3 of 3 pairs (mean 23.3 vs 19.0 of 30), driven by current headline figures; without
them it had lost — a fixed budget spread across the grid and stale figures from search
summaries.

## Research recipes (reusable plans)

A recipe saves the plan for research the user repeats — a quarterly market scan, a competitor
screen, a monthly regulatory watch — so each run starts from the same questions, fields and
sources and results stay comparable over time.

**When to offer one:** at the end of a run the user is likely to repeat, or when the user asks
to "do the same as last quarter". Save it only with the user's agreement.

**Where:** a `research-recipes/` folder in the user's working folder, one Markdown file per
recipe, e.g. `research-recipes/quarterly-market-scan.md`.

**What it holds:**

```
# Recipe: [name]
Purpose: [what decision or report it feeds]
Last run: [date] → [report file]
Sub-questions: [the fixed list]            (standard mode)
Items / fields: [the approved outline]     (comparison mode)
Done when: [the checkable tests]
Preferred primary sources: [publishers, registries, statistics series]
Shelf lives: [any overrides of evidence-hygiene.md]
Out of scope: […]
Standing instructions: [focus / exclude rules carried forward]
Lessons from the last run: [sources that failed, better queries, gaps to chase first]
```

**Running from a recipe:** load it in Step 1, restate it as the plan (with today's date), and
ask whether anything has changed before searching. Search for releases newer than "Last run"
first. After delivery, update "Last run" and "Lessons" — with the user's agreement.

Recipes hold research *design* only: no private names or findings (those live in the reports).
