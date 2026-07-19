---
name: deep-research
description: >
  Autonomous multi-step deep research engine implementing an iterative
  Think → Search → Extract → Synthesize → Stop loop. The LLM drives every
  decision: what to search, what's relevant, what's missing, and when to stop.
  Produces a cited, magazine-quality report with inline citations, category-
  specific formatting, and research stats. Trigger when the user asks for
  "deep research", "research report on", "comprehensive analysis of", "look
  into X in depth", "write a report on X", or any question needing multi-source
  synthesis beyond a single search. For entity vetting/dossiers use entity-research;
  for news digests use news-monitoring; for source-grounded Q&A use notebooklm-mode.
version: 1.4.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, deep-research, report, synthesis, iterative, citations, evidence-basis, provenance]
    related_skills: [news-monitoring, entity-research, notebooklm-mode, youtube-topic-research, fact-checker, source-tracker]
---

# Deep Research — Iterative Research Engine

An autonomous, multi-step research engine that performs exhaustive information
gathering and synthesis. Unlike a single `web_search`, this skill implements an
iterative loop where the agent plans, searches, extracts, synthesizes, and
decides when to stop — producing a cited report with structured evidence,
source quality tiers, and explicit gaps/contradictions sections.

Inspired by PewDiePie's Odysseus project, Alibaba/Tongyi's IterResearch
approach, and the sn-deep-research evidence-structuring architecture
(OpenSenseNova/SenseNova-Skills, MIT). The full 9-role sn pipeline was
evaluated and intentionally NOT adopted — only the evidence.json layer and
refute-polarity requirement were ported, based on empirical side-by-side
testing (July 2026). See `references/structured-evidence-format.md`.

**v1.2.0 changes (July 2026):** overview-first report structure (comparison
table right after executive summary), language anchoring (BCP 47), structured
evidence step (3e), refute polarity requirement, source quality classification,
explicit contradictions + gaps sections. Architecture diagram corrected.

**v1.3.0 changes (July 2026):** source quality ranking and weighting —
primary (3×) > secondary (2×) > tertiary (1×). Conflict resolution by quality
tier. Quality distribution check (healthy/acceptable/weak) before writing.
Tertiary source overreliance pitfall. Source table now shows quality
distribution summary. Prompted by user noting too many tertiary sources in
the self-hosting vs API report.

## When to use

- User asks for "deep research", "research report", "comprehensive analysis"
- User wants a written report on a topic (not just a quick answer)
- Question requires multi-source synthesis with citations
- User says "look into X in depth" or "write a report on X"

## When NOT to use

- **Entity vetting/dossiers** → use `entity-research` (has sanctions screening, structured lenses)
- **Recurring news digests** → use `news-monitoring` (has cron, dedup, multi-language)
- **Source-grounded Q&A from collected sources** → use `notebooklm-mode` (has vault + RAG)
- **Quick factual question** → just use `web_search` directly
- **Single-source extraction** → use `web_search` + `web_extract`

## Architecture

```
User question
  → Step 1: Plan (sub-questions, key topics, success criteria, category, language)
  → Step 2: Date grounding + language anchor
  → Step 3: Iterative loop (max 5 rounds)
      ├─ 3a: Generate gap-driven queries (incl. refute queries from round 2+)
      ├─ 3b: Search (web_search) + fetch (web_extract)
      ├─ 3c: Quality filter + extraction + source quality classification
      ├─ 3d: Synthesize into cumulative research state
      ├─ 3e: Structured evidence (optional: evidence.json for 5+ sources)
      └─ 3f: Stopping check (LLM evaluates coverage)
  → Step 4: Final report (overview-first structure, see template)
  → Step 5: Stats summary
```

**Report output order (overview-first):** Executive Summary → comparison/overview table → detailed analysis per sub-question → contradictions → gaps → conclusion → source table. Readers get the answer and the at-a-glance comparison before the detailed reasoning.

## Step 1 — Research Plan

Before searching, break the question into a research plan. Output:

```
## Research Plan
Question: [user's question]
Date: [current date]
Language: [BCP 47 tag — e.g. en, zh-Hans, ja. Detect from query; user's explicit language preference overrides. Use consistently throughout the report.]

Sub-questions:
1. [specific sub-question 1]
2. [specific sub-question 2]
3. [specific sub-question 3]
4. [up to 6 total]

Key topics:
- [topic 1]
- [topic 2]

Success criteria:
- [what would comprehensive coverage look like?]
- [minimum: each sub-question has ≥1 source]

Report category: [factual | comparison | product | how-to | fact-check | explainer]
```

**Language anchoring:** Detect the output language from the query and normalize to a BCP 47 tag (e.g. `en`, `zh-Hans`, `zh-Hant`, `ja`). Use it consistently throughout — executive summary, analysis, contradictions, gaps, conclusion. Source titles, URLs, proper nouns, and code may stay in their original language; search queries may use any language that helps evidence gathering. If the user explicitly switches language mid-research, update the anchor and use the new language for all subsequent output.

**Report category detection:**
- "vs", "compare", "better than" → **comparison**
- "best", "top", "recommend", "buy" → **product**
- "how to", "guide", "steps" → **how-to**
- "is it true", "verify", "fact check" → **fact-check**
- "what is", "explain", "overview" → **explainer**
- default → **factual**

## Step 2 — Date Grounding

Inject the current date before any search. This is **mandatory** — LLMs default to training-cutoff years, producing stale queries.

> Today's date is {current date as "DD Month YYYY"}. When a search query needs a year or refers to "latest"/"current"/"this year", use {current year} or relative wording — never a year inferred from training data.

## Step 3 — Iterative Loop

### Round structure

Each round follows: **Query → Search → Extract → Synthesize → Check Stop**

Run **max 5 rounds**. Most topics converge in 2-3 rounds.

### 3a — Query Generation (gap-driven)

Generate 2-4 search queries per round. **Round 1** targets the sub-questions from the plan. **Round 2+** targets gaps identified in the previous synthesis.

Before generating queries, review:
- Original question and research plan
- Current research state (what's already found)
- Round number
- What's still missing

Generate queries that target the **gaps**, not repeat what's already found.

**Refute polarity requirement:** Round 2+ must include at least one query targeting counter-evidence, opposing viewpoints, or criticisms of the leading hypothesis. If no counter-evidence is found after searching, note it explicitly in the synthesis — refute count = 0 usually means you didn't search well, not that no counter-evidence exists. This prevents confirmation-biased research.

### 3b — Search and Fetch

```
web_search(query="...", limit=10)
```

Run one `web_search` per query. From the results, pick 3-5 URLs per round to fetch in full:

```
web_extract(urls=["url1", "url2", "url3"])
```

**Track URLs already fetched** — do not re-fetch the same URL across rounds. Maintain a mental list of analyzed URLs.

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
- Record the source URL and title with each extracted fact
- **Classify source quality** for each source: `primary` (official docs, model cards, SEC filings, original papers), `secondary` (tech journalism, analyst reports, reviews), `tertiary` (Wikipedia, aggregators, forum posts). This tier appears in the final source table and signals evidence strength to the reader.
- **Grade each fact's evidence basis** as you extract (see below) — you can't tag a report you didn't grade while reading

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

```
## Research State (after Round N)
[evolving synthesis of all findings so far]

### Sub-question 1: [question]
Status: [answered / partially answered / unanswered]
Findings: [synthesized facts, each with an inline citation (Source: URL, "Title") and an evidence-basis tag, e.g. "adoption grew 40% in 2025 (Source: …) [VERIFIED]"]

### Sub-question 2: [question]
Status: [...]
Findings: [...]

### Gaps identified:
- [what's still missing for round N+1 to target]
```

Synthesis rules:
- **Deduplicate** — if multiple sources say the same thing, cite the best one (or cite both for corroboration)
- **Resolve contradictions** — if sources disagree, present both with attribution. Do not arbitrate silently.
- **Inline citations** — every factual claim references its source: `(Source: URL, "Title")`
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

**Quality distribution check before writing the report:**
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
>
> Reply YES (stop) or NO (continue) + one-sentence reason.

**Stop if:**
- All sub-questions have ≥1 source → YES
- 3+ rounds completed and remaining gaps are minor → YES
- 5 rounds completed (hard limit) → YES
- Web search returning diminishing returns (same URLs, no new info) → YES

**Continue if:**
- Major sub-questions unanswered → NO
- Contradictions unresolved → NO
- Only 1-2 rounds done and topic is broad → NO

## Step 4 — Final Report

Produce the final report. Minimum 800 words (scale with topic complexity).

**Output order is overview-first**: the reader gets the answer and the at-a-glance comparison *before* the detailed reasoning. Do not bury the comparison table after the per-topic analysis.

Carry each material fact's **evidence-basis tag** inline (§3c), lead on `[VERIFIED]` / `[SOURCED]`, keep `[REASONED]` / `[ESTIMATED]` claims framed as indicative, and paste the **Evidence key** legend below the Sources table so the tags decode.

### Structure

```markdown
# [Report Title]

> **Research date:** [date] · **Rounds:** [N] · **Sources:** [N] · **Category:** [type]

## Executive Summary
[2-3 paragraph overview of key findings — the answer up front. If using structured evidence, note claim count and refute count here so the reader knows the evidence base.]

## [Comparison Table | Overview | Key Findings at a Glance]
[For comparison reports: a markdown table comparing options/entities across criteria. For factual/explainer reports: a numbered list of key findings with claim references. This section gives the reader the complete picture in one screen — the detailed analysis below is the supporting reasoning, not the main event. If using structured evidence, cite claim IDs like [c1], [c3] in table cells or list items.]

## [## Section per sub-question]
[Detailed analysis with inline citations — this is the supporting reasoning for the overview above. Each section traces back to the overview claims.]

### [### Subsections as needed]
[...]

## Contradictions
[If sources disagree, present both sides with attribution. Do not silently arbitrate. If no contradictions found, state "No direct contradictions between sources." This section is REQUIRED — its absence is a quality signal that counter-evidence wasn't searched.]

## Gaps
[What couldn't be determined from available sources. Each gap should note: what's unknown, why it matters, and whether it could be resolved with more research. If using structured evidence, reference the writing_context items. If no gaps, state "No significant gaps identified."]

## Conclusion
[Synthesis of findings, implications, remaining uncertainties — ties back to the executive summary and overview. The conclusion confirms or qualifies the overview, it doesn't introduce new analysis.]

---
## Sources

**Quality distribution:** [N] primary · [N] secondary · [N] tertiary — [healthy/acceptable/weak]

| # | Title | URL | Quality | Accessed |
|---|-------|-----|---------|----------|
| 1 | [title] | [url] | primary/secondary/tertiary | [date] |

**Evidence key** — `[VERIFIED]` corroborated across ≥2 independent, cited, dated sources · `[SOURCED]` from one named source, not independently corroborated · `[REASONED]` analytical judgement / inference · `[ESTIMATED]` calculation or stated assumption.
```

### Category-specific overview sections

| Category | Overview section format |
|---|---|
| **comparison** | Markdown table comparing options across criteria, with a verdict row or column. The detailed sections below provide the reasoning per option. |
| **product** | Ranked list with pros/cons, price range, and a "top pick" callout. Detailed sections cover each product. |
| **how-to** | Numbered overview of the steps. Detailed sections cover prerequisites, execution, and troubleshooting per step. |
| **fact-check** | Evidence for/against the claim in a two-column table, with a preliminary verdict. Detailed sections assess source credibility and reasoning. |
| **explainer** | Numbered key findings or a "progressive depth" overview (simple → deep). Detailed sections go deeper per concept. Glossary if technical. |
| **factual** | Numbered key findings with claim references. Detailed sections provide the supporting evidence per finding. |

### Fallback report

If LLM synthesis fails (timeout, error, garbled output), compile raw findings into a basic report:
- List all findings grouped by sub-question
- Include source URLs and keep each finding's evidence-basis tag
- Add note: "This is a raw findings compilation; synthesis was not completed."
- Never output "No information could be gathered" if any sources were fetched — always compile what exists.

## Step 5 — Research Stats

After the report, output a compact stats block:

```
---
📊 Research stats: [duration] · [N] rounds · [N] queries · [N] URLs fetched · [N] sources cited
```

## Follow-on Investment Analysis (optional)

When the research report covers a real estate or investment question and the
user subsequently provides specific deal parameters (price, area, location),
build a quantitative pro-forma using `execute_code`. The pattern:

1. **Benchmark the asking price** against recent transaction comparables
   (Cushman & Wakefield, CBRE, Savills, JLL — cap rates + price per tsubo)
2. **Model alternative uses** (e.g., office as-is vs hotel converted) with
   full P&L: revenue → operating expenses → NOI
3. **Estimate conversion costs** (per-tsubo renovation rates, per-room costs)
4. **Compute return metrics**: NOI yield vs market cap rates, payback period
5. **Sensitivity table**: 3 revenue scenarios × 3 cost scenarios
6. **Break-even analysis**: what price/ADR/occupancy achieves market yield?

**Critical:** Always model the as-is use case as a baseline. If the
alternative-use NOI exceeds the converted-use NOI, the conversion destroys
value at that acquisition price — say so clearly.

See `references/real-estate-investment-analysis.md` for the full template,
Japan-specific data sources, renovation cost benchmarks, and cap rate ranges.

See `references/structured-evidence-format.md` for the evidence.json schema,
claim rules, writing-context vs claims distinction, and the side-by-side test
results that validated the structured-evidence approach (July 2026).

## Vault Integration (optional)

For larger research tasks (10+ sources) or when the user may want to follow up with grounded Q&A:

1. Create a vault per `notebooklm-mode` at `<project_folder>/research-<topic>/`
2. Save each source as a numbered file in `sources/` with verbatim extracts
3. Use `ingest_source.py` to write + index atomically
4. After the report, tell the user: "Sources saved to vault at [path]. You can ask follow-up questions grounded in these sources — say 'notebooklm mode' to query the vault."

This is optional — the skill works fully without a vault for one-off reports.

## Subagent Mode (optional)

For genuinely parallel research across distinct sub-topics (e.g. researching 3 unrelated companies):

```
delegate_task(
  goal="Research [sub-topic] as part of a deep-research project. Run web searches, extract content, and return findings with source URLs and titles.",
  context="You are a research subagent. Topic: [sub-topic]. Sub-questions: [list]. Use web_search and web_extract. Return structured findings with citations.",
  toolsets=["web"]
)
```

**Rules:**
- Only use subagents when sub-topics are genuinely independent
- Collect results from all subagents, then synthesize yourself
- Never delegate the synthesis step — the orchestrator must see all findings
- Subagent summaries are self-reports — verify source URLs exist before citing

## Concurrency and Rate Limits

- Fetch 3-5 URLs per round (not all 10 search results) to avoid rate-limiting
- If `web_extract` fails on a URL, note it and move on — don't retry endlessly
- If `web_search` returns no results, try rephrasing the query once, then move on
- Track fetched URLs across rounds to avoid re-processing

## Pitfalls

- **Skipping the research plan** — without sub-questions, the loop has no direction and the stopping check has no baseline. Always plan first.
- **Stale year in queries** — always inject date grounding. Models default to training-cutoff years.
- **Re-fetching same URLs** — track analyzed URLs across rounds. Wastes time and tokens.
- **Over-searching** — most topics converge in 2-3 rounds. Don't pad to 5 rounds if the stopping check says YES at round 2.
- **Under-searching** — broad topics with 1 round produce shallow reports. If the stopping check says NO, continue.
- **No quality filter** — including thin/irrelevant sources dilutes the report. Filter before extraction.
- **Listing instead of synthesizing** — the report should synthesize findings, not list them. Resolve contradictions, identify themes, draw conclusions.
- **Missing citations** — every factual claim in the final report must have an inline citation with URL + source title.
- **Missing evidence-basis tags** — a material fact with a citation but no `[VERIFIED]`/`[SOURCED]`/`[REASONED]`/`[ESTIMATED]` tag is half-graded. Tag it, and include the Evidence key so the tags decode.
- **Improvised evidence labels** — use only the four canonical tags. A synonym like `[Official]`, `[Confirmed]`, or `[Consensus]` breaks the discipline; map it to one of the four.
- **Overclaiming basis** — don't tag a single-source fact `[VERIFIED]`, and don't restate precision the source didn't give. When torn between two labels, pick the weaker one.
- **Synthesis failure produces nothing** — always use the fallback report if synthesis fails. Raw findings > no output.
- **Ignoring contradictions** — if sources disagree, present both. Don't silently pick one.
- **Fabricating sources** — never invent URLs, titles, or facts. If a sub-question can't be answered, document it as a gap — never a `[REASONED]` guess dressed as a sourced fact.
- **No counter-evidence search** — only searching for supporting evidence produces biased research. Round 2+ must include at least one counter-evidence query. If none found, say so explicitly.
- **Missing gaps/contradictions sections** — the report must surface what's unknown and where sources disagree. Omitting these sections hides uncertainty from the reader and signals incomplete research.
- **No source quality classification** — unclassified sources make it impossible to judge evidence strength. Always tag primary/secondary/tertiary in the source table.
- **Tertiary source overreliance** — if 0 primary sources and >50% tertiary, the evidence base is weak. Flag it in the Gaps section and attempt to fetch primary sources (official docs, model cards, pricing pages) before finalizing. Tertiary sources are valuable for refute polarity and real-world anecdotes, but should never be the sole support for a factual claim when primary/secondary sources exist. Qualify tertiary-sourced claims: "Community reports suggest..." not "X is true."
- **Conflating claims with context** — facts about the research subject (claims) vs boundary conditions (scope limits, methodology notes, availability gaps) are different things. Use the writing_context concept from the structured evidence format to separate them.
- **Burying the comparison table** — the overview/comparison table goes right after the executive summary, not after the detailed analysis. Readers need the at-a-glance picture first; the detailed sections are supporting reasoning. Putting the table last forces readers to scroll through analysis before seeing the answer.
- **Subagent synthesis** — never delegate the synthesis step. The orchestrator must see all findings to synthesize honestly.
- **CBD rents for non-CBD locations** — when modeling real estate income, do not apply Marunouchi/Otemachi Grade A office rents (¥70K–100K/tsubo) to secondary locations like Koto-ku. Use submarket-appropriate rents (¥20K–30K/tsubo for mid-tier Koto-ku). This single mistake can inflate projected NOI by 3× and make a bad deal look good.

## Related Work

[Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) — PewDiePie's self-hosted AI workspace — includes a "Deep Research" feature with multi-step web research and source reading, conceptually similar to this skill's Think → Search → Extract → Synthesize → Stop loop. This skill is a pure-prompt workflow (no UI, no server) designed to run inside any agent's tool loop.

## Evals

`evals/routing-fixtures.json` holds lightweight contract fixtures — sample
request → expected routing (including when a request should go to
`entity-research` / `notebooklm-mode` / `news-monitoring` instead), required
output fields, and forbidden output patterns. They are specs, not run against a
live model; the repo-root `tests/test_routing_fixtures.py` validates they stay well-formed and
route to real skills.