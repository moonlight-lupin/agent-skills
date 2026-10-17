# Step 3 — Iterative Loop

Full iterative-loop rules for deep research. SKILL.md keeps the round shape and a one-line skeleton of each substep.

## Contents

- Round structure
- 3a — Query Generation (gap-driven)
- 3b — Search and Fetch
- 3b.1 — Evidence Persistence (mandatory for 5+ source reports)
- 3c — Quality Filter and Extraction
- Verbatim snippet anchoring (mandatory for claims you store)
- Evidence basis — the four-label discipline
- 3d — Synthesis
- 3e — Structured Evidence (recommended for reports with 5+ sources)
- 3f — Stopping Check

## Step 3 — Iterative Loop

### Round structure

Each round follows: **Query → Search → Extract → Synthesize → Check Stop**

Run **max N rounds** where N = complexity cap from Step 1 (simple=2, moderate=3, complex=5). Most topics converge in 2-3 rounds. The cap is a ceiling, not a target.

### 3a — Query Generation (gap-driven)

**Per-round breadth** comes from the complexity preset (Step 1): simple=2, moderate=3, complex=4 queries per round. **Round 1** targets the sub-questions from the plan. **Round 2+** targets gaps identified in the previous synthesis **and** per-query follow-up directions recorded during extraction (below).

Before generating queries, review:
- Original question and research plan
- Current research state (what's already found)
- Round number
- What's still missing

Generate queries that target the **gaps**, not repeat what's already found.

**Mini search plan per query** (adapted from upstream `search-plan.ts`): plan a search task, not a bag of keywords. Each generated query carries:
- **one angle** — a concise domain-keyword query, an exact identifier, or a natural-language question. Preserve error messages, standards, paper titles, model numbers, and technical terminology verbatim in the query text; never force them into a conversational sentence or truncate by word count. Avoid unrelated keyword piles ("official blog OR paper").
- **intent** — the donsetch `web_search` `intent` vertical: `web` (default), `news`, `paper`, `entity`, `code`. Broad AI news gets complementary discovery queries across models, products, and industry — never silently narrowed to LLM papers.
- **time window + domain scope** — recorded in the research state and expressed in the query text (the donsetch tier has no structural SERP filters). Never invent a domain or publisher whitelist; scope domains only when the user requested it or the domain is already verified in earlier sources. **Publication metadata is a hint, not proof** — a search result's date never becomes the claim's date; verify event dates in source text (§3c).
- **source preference** — `any` or `primary`; `primary` steers §3c toward official docs, filings, papers. It is an extraction preference, never a keyword or a fabricated tier.

**Frozen constraints on rewrite:** the time window and domain scope stay fixed across rounds and rewrites — a weak result is not permission to broaden them. On empty or thin results, only the query text changes:
- 1st empty → broader query or synonyms. 2nd consecutive → fundamentally different angle/domain/language. 3rd → move on; document as a gap rather than burning rounds on dead-end queries.
- **Identical-rewrite stop** — if the refined query equals the previous one modulo whitespace, stop refining that angle: move to the gap list, don't re-run the same search.

**Round-outcome classification** (adapted from upstream `search-assessment.ts`): after each round's extraction settles, classify the round outcome and let the reason pick the next move — the taxonomy replaces ad-hoc retry judgement with a bounded, reason-specific response. Classify exactly one of:

| Outcome | Meaning | Next move |
|---|---|---|
| `verified` | ≥1 stored claim anchored per §3c | No retry; proceed to synthesis / stop check |
| `no_results` | Search returned nothing | Refinement ladder above |
| `irrelevant` | Results exist, none survive §3c triage | One fundamentally-different-angle rewrite; treat as the 2nd-empty rung |
| `no_findings` | Relevant pages found but nothing goal-relevant extracted in them | One targeted re-read (a §3b fetch budget event, `focus`/`section`); then move on |
| `unmatched_sources` | A stored claim cites a source absent from the registered set | Re-anchor the claim to its correct registered source; never cite an unmatched source |
| `unmatched_quotes` | Stored excerpts fail §3c verbatim anchoring | `check-quote` repair-once (§3c) |

Relevance itself stays agent-judged — the taxonomy assigns each reason a single bounded response and forbids retry without a new move. Record the classification with your working state so the next round's query generation starts from the named gap.

**Follow-up threading (deep-dive chains, upstream's breadth-halving recursion, bounded):** while extracting (§3c), each query thread records ≤2 follow-up directions when a material gap remains — empty when covered, never padded. Round 2+ queries draw from these per-thread directions plus global gaps, and every thread carries the **original user goal** so deep queries stay aligned with it (drift guard). At most one active deep-dive chain per sub-question, width = ceil(preset breadth / 2) at each level below its first, all inside the plan's search budget.

**Coverage balancing (round 2+):** before following the loudest gap, put a query at any planned sub-question still at **zero coverage**. A gap list ordered by noise lets one loud thread starve a silent one; balancing is mandatory before generating optional deep-dive queries.

**Refute polarity requirement:** Round 2+ must include at least one query targeting counter-evidence, opposing viewpoints, or criticisms of the leading hypothesis. If no counter-evidence is found after searching, note it explicitly in the synthesis — refute count = 0 usually means you didn't search well, not that no counter-evidence exists. This prevents confirmation-biased research.

### 3b — Search and Fetch

**Provider preference (optional, user-set):** On request, use the donsetch MCP search/fetch tools, falling back to `web_search`/`web_extract` if unavailable. Never abort over a provider preference. Record the provider used in the run manifest and stats block.
```
web_search(query="...", limit=10)
```

Run one `web_search` per query (plus `query_variants` when two distinct angles serve one requirement). Then apply **snippet-first triage** — adapted from upstream `read-source.ts`'s on-demand reading, search results and their snippets are first-class evidence:

- **Triage before fetching.** Run §3c's quality filter on snippets and titles; a fetched page is a budgeted event, not a default. Fetch full page text only when a **concrete missing question** exists that the snippet cannot answer (missing date, statistic, named entity, or evidence for a targeted sub-question), or when the source is a primary-tier candidate for a key claim. Do not reject a promising candidate solely because its snippet lacks a date — that is exactly the fetch signal.
- **Budget the fetches.** ≤2 full-page fetches per round; run-wide ≤4 for moderate, ≤6 for complex reports (simple reports rarely need any). Track URLs already fetched — never re-fetch across rounds. Count page fetches in the stats block.
- **Keep evidence source types separate.** A snippet supports what it *states* — at most `[SOURCED]`, never independently corroborated. The fetched page text is the verbatim-quote substrate for §3c anchoring: a claim whose snippet was thin must be re-anchored to the page text before its snippet goes in the store.
- **Reading tools.** donsetch `web_fetch` modes are the primary reading path (`scan`/`read`/`deep` budgets, `focus`/`section` for targeted reading, `toc` for structure); built-in `web_extract` (head+tail with an on-disk full-text path) is the fallback.

```
web_extract(urls=["url1", "url2"])
```

### 3b.1 — Evidence Persistence (mandatory for 5+ source reports)

Persist evidence to disk from the first round so it survives context compaction: `init-run`, `register-source`, `add-claim`, `add-evidence`, `check-quote` subcommands of `scripts/research_validation.py`. Add claims and evidence **during** the loop (§3d), not at the end — the append-only `claims.jsonl` is the fabrication-detection backbone for the gates. On context compaction, re-read `claims.jsonl` instead of trusting compressed memory. **Also save each fetched page's text** to `<run_dir>/pages/<source_id>.txt` (write_file right after registering the source; for pages `web_extract` stored to disk, its reported path can be passed to `check-quote --file` directly). That page-text file is the substrate for verbatim quote anchoring (§3c). Full contract: `references/validation-gates.md`.

### 3c — Quality Filter and Extraction

Before extracting content, **discard low-quality results**:

- **Thin content**: landing pages, aggregator stubs, <100 words of substantive text
- **Irrelevant**: keyword overlap without topical relevance. Use word-boundary matching for topic terms — "port" should not match "transport" or "support"
- **Duplicate URLs**: already fetched in a previous round
- **Non-text**: video-only pages, image boards, login walls with no preview

For each quality source, extract **goal-relevant facts**:
- What facts in this source address a sub-question from the research plan?
- Ignore noise, navigation, ads, boilerplate
- Prefer specific data, statistics, named sources, dates over vague claims
- Record the source URL and title with each extracted fact. Assign each unique source a **numbered citation** `[1]`, `[2]`, etc. on first encounter — reuse the same number for subsequent facts from the same source. This produces cleaner inline citations than full URLs (especially on mobile/messaging platforms) and matches academic/magazine citation style. Deduplicate by URL: the same URL seen twice gets the same number.
- **Classify source quality** for each source: `primary` (official docs, model cards, SEC filings, original papers), `secondary` (tech journalism, analyst reports, reviews), `tertiary` (Wikipedia, aggregators, forum posts). This tier appears in the final source table and signals evidence strength to the reader.
- **Grade each fact's evidence basis** as you extract (see below) — you can't tag a report you didn't grade while reading

### Verbatim snippet anchoring (mandatory for claims you store)

Every factual claim recorded in the store (`add-claim` / `add-evidence`) carries a **verbatim contiguous excerpt** from that source's page text: copied exactly — original language, no paraphrase, no splicing across paragraphs, no added ellipses — 8–1500 characters (a tighter supporting run, not a whole paragraph). Anchor it **at extraction time, not at gate time**: before storing, run the deterministic check

```
python3 <skill_dir>/scripts/research_validation.py check-quote \
  --dir <run_dir> --source-id <sid> --snippet "<copied excerpt>" [--snippet "..."]
```

(a `--file <path>` variant anchors against any saved page text; repeated `--snippet`s check in one call). The check is exact substring matching modulo Unicode whitespace runs — no tokenizer, so CJK and any script anchor reliably where the tokenized support scorer struggles. **Keep the claim text itself quote-shaped**: the support scorer supports a claim only when one stored snippet covers every figure/year/entity the claim carries — split multi-fact claims or byte-align the claim to its snippet (see Pitfalls; prose paraphrase stays in the report body).

- **On a mismatch (`ok: false`): repair once** — re-copy the excerpt exactly from the page text (the `hint` field tells you when only quote/dash style differs). Never massage the snippet toward the claim, never splice.
- **No contiguous supporting excerpt exists?** The claim is not evidence-backed. Store it honestly — as `[REASONED]`/interpretive without a stored quote, or accept that `verify-claims` will flag `unsupported`. A truthful red is the correct outcome; never fix it by editing the quote.
- **Self-verification from memory does not count** — recall-level eyeballing is exactly how paraphrases slip through. Run the script; it reads the page text from disk.

### Evidence basis — the four-label discipline

Tag every **material fact** with the basis on which you're asserting it. A material fact is any substantive claim a reader would act on or challenge: a statistic, date, named entity or relationship, causal claim, or direct quote. This is deep-research's adaptation of pere-toolkit's canonical evidence discipline — the **same four labels**, applied to *facts* rather than financial figures.

| Label | A fact is `[LABEL]` when it is… |
|---|---|
| `[VERIFIED]` | corroborated across ≥2 independent, cited, dated sources |
| `[SOURCED]` | stated by one named / cited source, not independently corroborated |
| `[REASONED]` | your own analytical judgement or inference — not stated by any source |
| `[ESTIMATED]` | a calculation or stated assumption (e.g. a figure you derived from source data) |

Rules:
- **Lead on `[VERIFIED]` / `[SOURCED]`.** Present `[REASONED]` / `[ESTIMATED]` claims as *indicative* ("likely", "suggests", "on these figures") — never as hard fact.
- **Use these four exact labels** — never an improvised synonym (`[Official]`, `[Expert]`, `[Consensus]` → these are `[SOURCED]`, or `[VERIFIED]` only if independently corroborated).
- **Don't restate precision you don't have** — a source's "about half" is `~50% [SOURCED]`, not `50.0%`.
- **Never fabricate to fill a gap** — an unanswerable sub-question is a documented gap, not a `[REASONED]` guess dressed as fact.

**Relationship to source-quality tiers:** the `primary`/`secondary`/`tertiary` tier (above) classifies the *source*; the `[VERIFIED]`/`[SOURCED]`/`[REASONED]`/`[ESTIMATED]` label classifies the *fact*. They are orthogonal: a fact from a single primary source is `[SOURCED]` (strong source, but uncorroborated); the same fact from two independent primary sources becomes `[VERIFIED]`. Use both: tier in the source table, label inline on each claim.

### 3d — Synthesis

After extracting from all sources in the round, integrate findings into the **cumulative research state**:

**Token budget awareness:** Track approximate context consumption across rounds. If the cumulative research state + extracted content is approaching the model's context window or a self-imposed budget (suggested: ~50K tokens for moderate, ~100K for complex), prioritize synthesis and stopping over gathering more sources. When the budget is tight, summarize earlier rounds' findings more aggressively rather than carrying full extracts forward.

**Passage selection over summarization** (adapted from upstream `source-context.ts`): when a must-keep source is huge, do not summarize its evidence away — select the **original passages** scoring highest on query-term overlap, keep them verbatim (they stay anchor-eligible for §3c), and mark elided spans. A generated paraphrase cannot later pass `check-quote`; a verbatim passage can. donsetch `web_fetch focus`/`section` does this natively; with built-in `web_extract`, re-read the on-disk full-text path around term-matching sections instead of trusting the truncated head+tail window.

**Rough estimation heuristic:** You can't count tokens precisely, but you can estimate: each `web_extract` returning ~5K characters contributes ~1.5K tokens; the research state after N rounds with 3-5 sources per round is roughly N × 8-12K tokens. If you're on round 3+ of a complex topic and the last `web_extract` returned >10K characters, you're likely past 50K — summarize aggressively and head toward synthesis. When in doubt, treat any round-3+ complex research as budget-tight.

```
## Research State (after Round N)
[evolving synthesis of all findings so far]

### Sub-question 1: [question]
Status: [answered / partially answered / unanswered]
Findings: [synthesized facts, each with a numbered inline citation [N] matching the source table, and an evidence-basis tag, e.g. "adoption grew 40% in 2025 [1] [VERIFIED]"]

### Sub-question 2: [question]
Status: [...]
Findings: [...]

### Gaps identified:
- [what's still missing for round N+1 to target]
```

Synthesis rules:
- **Deduplicate** — if multiple sources say the same thing, cite the best one (or cite both for corroboration)
- **Resolve contradictions** — if sources disagree, present both with attribution. Do not arbitrate silently.
- **Inline citations** — every factual claim references its source using the numbered citation `[N]` assigned in §3c, matching the source table
- **Evidence basis** — tag each material fact `[VERIFIED]` / `[SOURCED]` / `[REASONED]` / `[ESTIMATED]` (see §3c). A fact becomes `[VERIFIED]` only once ≥2 *independent* sources corroborate it; a single source is `[SOURCED]`. Corroboration during dedup is what promotes `[SOURCED]` → `[VERIFIED]`.
- **Update gap list** — what sub-questions are still unanswered or thin?

### 3e — Structured Evidence (recommended for reports with 5+ sources)

Before writing the final report, structure the extracted evidence into a lightweight `evidence.json` intermediate. This separates evidence gathering from report writing and makes fabrication detectable. See `references/structured-evidence-format.md` for the schema, source quality ranking/weighting rules, and worked example.

**When to use:** reports with 5+ sources, comparison/fact-check categories, or when the user may want to verify claims. Skip for quick 2-3 source reports.

**Benefits validated in side-by-side testing** (July 2026):
- Forced claim precision (every assertion gets a kind + polarity + snippet)
- Refute polarity requirement surfaced counter-evidence the iterative loop missed
- Source quality tiers revealed evidence-strength gaps (too many tertiary sources)
- Explicit gaps + contradictions sections in the final report
- Full traceability: claim ID → snippet → source URL

**Source quality ranking and weighting** (see `references/structured-evidence-format.md` for full rules):
- **primary** (3× weight): official docs, model cards, SEC filings, API pricing pages, original papers
- **secondary** (2× weight): tech journalism, analyst reports, benchmark aggregators
- **tertiary** (1× weight): Reddit, forums, Wikipedia, blog aggregators — useful for refute polarity and real-world anecdotes, but **never the sole support for a factual claim if a primary/secondary source exists**

**Quality distribution check before writing the report** (`verify-claims` computes it from the store as `source_quality`):
- **Healthy**: ≥30% primary, ≤30% tertiary → proceed
- **Acceptable**: ≥1 primary for key claims, <50% tertiary → note thin primary coverage as a gap
- **Weak**: 0 primary, >50% tertiary → **flag in Gaps section** and attempt to fetch primary sources (official docs, model cards, pricing pages) before finalizing. If primary sources are unavailable, qualify tertiary-sourced claims explicitly ("community reports suggest..." not "X is true")

**Conflict resolution by quality:** When sources disagree, primary > secondary > tertiary. 2 independent secondary sources ≈ 1 primary. Tertiary cannot override secondary/primary — it becomes refute counter-evidence or writing_context instead.

### 3f — Stopping Check

After synthesis (and optional evidence structuring), evaluate whether the report is comprehensive enough:

> Given the research plan's success criteria:
> - Are all key sub-questions addressed with at least one source?
> - Are there significant gaps or unanswered aspects?
> - Is the evidence sufficient and corroborated?
> - Am I approaching the token budget? (tight context = prioritize synthesis)
>
> Reply YES (stop) or NO (continue) + one-sentence reason.

**Stop if:**
- All sub-questions have ≥1 source → YES
- **Saturation ≤5% for 2 consecutive rounds** — new material findings this round ≤5% of all accumulated findings, two rounds running → YES (quantified convergence measure, adapted from Anjos2/recursive-research; the threshold is unvalidated upstream — treat as a strong signal, never a substitute for the qualitative checks below)
- Most of the complexity cap used (e.g. round 2 of 2 for simple, round 3 of 3 for moderate) and remaining gaps are minor → YES
- Complexity cap reached (simple=2, moderate=3, complex=5) → YES
- Token budget approaching limit → YES (synthesize with what you have)
- Web search returning diminishing returns (same URLs, no new info) → YES

**Continue if:**
- Major sub-questions unanswered → NO
- Contradictions unresolved → NO
- Only 1-2 rounds done and topic is broad → NO
