# Evidence hygiene: source families, shelf life, money bases, user-supplied reports

Five rules that keep the evidence labels honest. §3c, Step 5.5 and the Pitfalls point here.

## 1. Count one story once (source families)

Several pages repeating the same underlying document are **one source family**, not
independent corroboration. Typical families:

- a press release and the trade-press articles that reprint or paraphrase it;
- a filing, results PDF or dataset and the pages that quote its figures;
- an analyst or agency report and the articles summarising it;
- syndicated copies of one news article (same wording, different sites).

**How to apply:**

- When two sources carry the same figure, check where each got it. Shared wording, the same
  figure to the same decimal place, or "according to [X]" means one family.
- Cite the **original** (the release, the filing, the report) as the source; the copies add
  nothing to the label. If the original cannot be found, cite the best copy and say it repeats
  another source.
- **`[VERIFIED]` needs two independent families**, not two sites. One family stays
  `[SOURCED]` however many sites repeat it.
- Record the family in the research state next to the source number (e.g. `[3] = family of
  [1]`) so synthesis and the source-set bias line see it.
- The deterministic gate counts *sites*, not families: it cannot catch this. The check is yours.

## 2. Shelf life for time-sensitive facts

Every time-sensitive fact carries its **as-of date** (the period it describes, not the date
of the article). Flag a fact older than its shelf life as stale in the report — state it with
its date and say a newer figure may exist; never present it as current. A figure with no date
at all is flagged as undated, never used as current.

| Fact type | Default shelf life | Note |
|---|---|---|
| Prices, rents, occupancy, usage or traffic metrics | 12 months | Monthly series: use the latest month published |
| Yields, valuations, multiples | 6 months | Quote the quarter or valuation date |
| Comparable transactions | 24 months | Older deals as context only |
| Pipelines, roadmaps, planned supply | 6 months | These change quickly |
| Interest rates, FX, inflation | As of the report date | Give the date of the figure |
| Regulation, tax rules, guidance | The version in force | Check for amendments and open consultations |
| Company figures (headcount, assets, units) | The latest reporting period | Look for a newer annual or interim report |

The user or a recipe (see `comparison-mode-and-recipes.md`) can set different shelf lives.
Before using a fact near its limit, run one query for a newer release.

## 3. State the basis of every money figure

A deal value, price or fee means nothing without its basis, and different bases of the same
deal circulate side by side. Before using an amount, establish:

- **When:** the announced or offer value vs the value at completion (offers move: price
  adjustments, dividends, share-price changes in a share-for-share deal);
- **What it covers:** enterprise vs equity value, including or excluding debt, a dividend or
  costs; gross vs net; headline vs effective (after incentives or discounts);
- **Whose share:** 100% of the asset vs the reporting party's share in a joint venture;
- **Currency and date** of any conversion.

State the basis next to the figure ("$720m offer value incl. dividends, Aug; c.$530m
consideration at completion, Jan"). When sources give different amounts for one thing,
reconcile them by basis before choosing — list it under Contradictions only if the bases
cannot be found. Never present a headline or offer figure as the final value.

## 4. Reports the user supplies

The user may hand over material the open web does not have: a subscription research report,
a consultant's pack, their own data.

- Read it **locally**; never upload it to an external tool or quote it into a web query.
- Register it as a source with its title, publisher, date and "supplied by user"; cite it as
  such in the Sources table (no URL needed).
- It can support a claim (`[SOURCED]`). It counts as an independent family only against
  sources outside its own publisher; the user's own records establish internal facts but are
  never external confirmation.
- Respect its licence: quote briefly, don't reproduce tables wholesale.

## 5. Write dates the way local sources do

When a query needs a date, use the forms the target sources use, alongside the relative
wording: "Nov 2026", "November 2026", "2026-11"; in Japanese and Chinese, "2026年11月" (and the
era year, e.g. "令和8年", for Japanese government sources). A single form misses releases titled
the other way.
