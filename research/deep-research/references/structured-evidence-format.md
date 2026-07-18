# Structured Evidence Format

A lightweight intermediate representation for research evidence, inspired by
the sn-deep-research architecture (OpenSenseNova/SenseNova-Skills) but adapted
for single-agent use without the full 9-role pipeline.

## When to Use

- Reports with 5+ sources
- Comparison or fact-check categories
- When the user may want to verify claims
- When fabrication prevention matters (research informing decisions)

Skip for quick 2-3 source reports — the overhead isn't worth it.

## Schema

```json
{
  "headline": "one-line summary of findings",
  "key_findings": [
    {"finding": "load-bearing conclusion", "claim_ids": ["c1", "c2"]}
  ],
  "claims": [
    {
      "id": "c1",
      "text": "the factual assertion (5-500 chars, verifiable statement)",
      "kind": "factual|interpretive|projective",
      "polarity": "support|refute|neutral",
      "topic_tag": "short_snake_case_tag",
      "source_id": "src1",
      "snippet": "exact text from the source (NOT paraphrased from memory)",
      "source_url": "https://...",
      "source_title": "Page Title",
      "source_quality": "primary|secondary|tertiary"
    }
  ],
  "sources": [
    {"id": "src1", "url": "https://...", "title": "...", "quality": "primary"}
  ],
  "writing_context": [
    {
      "id": "w1",
      "kind": "scope_boundary|availability_gap|methodology|unresolved_gap",
      "text": "what's unknown or limited",
      "source_ids": ["src1"],
      "use": "how the writer should handle this in the report"
    }
  ]
}
```

## Claim Rules

| Field | Rule |
|---|---|
| `kind` | `factual` = verifiable stat (needs ≥1 primary/secondary source). `interpretive` = analysis (needs ≥2 different sources). `projective` = prediction (needs stated assumptions). **No normative claims** ("should/must") — research states facts, not opinions. |
| `polarity` | `support` = supports the hypothesis. `refute` = counter-evidence. `neutral` = descriptive. **At least 1 refute claim is required** — refute=0 means biased research. |
| `snippet` | Must be exact text from the fetched source, NOT reconstructed from memory. This is the fabrication-detection mechanism. |
| `source_quality` | `primary` = official docs, model cards, SEC filings, original papers, vendor pricing pages. `secondary` = tech journalism, analyst reports, benchmarks aggregator. `tertiary` = Wikipedia, forum posts (Reddit, HN), blog aggregators, social media. |
| `topic_tag` | Reuse existing tags when possible. Same topic = same tag. |

## Source Quality Ranking and Weighting

Source quality is not just a label — it determines **evidentiary weight** when sources conflict or when claims rest on a single source.

### The ranking hierarchy

| Tier | Weight | Examples | When it wins |
|---|---|---|---|
| **primary** | 3× | Official docs, model cards, SEC filings, API pricing pages, original research papers, vendor spec sheets | Always preferred for factual claims. A single primary source outweighs multiple tertiary sources. |
| **secondary** | 2× | Tech journalism (TechCrunch, Ars Technica), analyst reports (Gartner, Forrester), benchmark aggregators (Artificial Analysis) | Reliable for synthesis and interpretation. Needs ≥2 independent secondary sources to match 1 primary. |
| **tertiary** | 1× | Reddit, HN, forum posts, Wikipedia, blog aggregators, social media | Useful for community sentiment, real-world anecdotes, and gap-filling. **Never the sole support for a factual claim if a primary/secondary source exists.** Best used to surface counter-evidence (refute polarity) or document real-world experience that primary sources don't cover. |

### Conflict resolution by quality

When sources disagree on a fact:

1. **Primary > secondary > tertiary.** If a vendor pricing page says $5/1M tokens and a Reddit post says $3/1M, the pricing page wins. Present the tertiary view as "community reports suggest X, but official pricing confirms Y."
2. **2 secondary ≈ 1 primary.** Two independent secondary sources corroborating each other match the weight of one primary source.
3. **Tertiary cannot override secondary/primary.** A Reddit anecdote contradicts an official spec sheet → the spec sheet wins; the Reddit post becomes "refute" counter-evidence or writing_context, not the basis for the factual claim.
4. **Tertiary is valuable for refute polarity.** Community sources often surface real-world problems (latency, break-even misses, hidden costs) that official sources won't acknowledge. Use tertiary for refute claims and writing_context, not for the main factual claims.

### Quality distribution check (during evidence review)

Before writing the report, check the source quality distribution:

- **Healthy**: ≥30% primary, ≤30% tertiary. Evidence base is strong.
- **Acceptable**: ≥1 primary for key factual claims, <50% tertiary. Note as a gap if primary coverage is thin.
- **Weak**: 0 primary sources, >50% tertiary. **Flag explicitly in the Gaps section** — the evidence base rests on secondary/tertiary interpretation, not direct sources. Attempt to fetch primary sources (official docs, model cards, pricing pages) before finalizing the report.

### Weighting in the report

When citing sources in the final report:
- State the quality tier in the source table (already required).
- When a claim rests primarily on tertiary sources, qualify it: "Community reports suggest..." or "According to forum discussions..." — don't present tertiary-sourced claims with the same confidence as primary-sourced claims.
- When sources conflict, present the higher-weight source as the primary finding and the lower-weight as the counter-evidence or context.

## Writing Context vs Claims

- **Claims** = facts about the research subject (numbers, events, states, trends)
- **Writing context** = boundary conditions (scope limits, methodology notes,
  availability gaps, unresolved uncertainties) — NOT facts, but things the
  writer needs to acknowledge when presenting facts

This separation prevents the report from overstating certainty. A gap in
available data is not a claim — it's writing context.

## Worked Example (from July 2026 side-by-side test)

Research question: "Best open-weight LLMs for 5GB RAM CPU-only server?"

13 claims, 9 sources, 1 refute claim, 2 writing_context items.

Key finding: the refute polarity requirement forced a search for
counter-evidence to "GLM-5.2 is impossible on CPU" — which found a Reddit
thread showing GLM-5.2 CAN run on CPU, just needs 192-256GB RAM (not 5GB).
This nuance would have been missed without the refute requirement.

## Side-by-Side Test Results (July 2026)

| Metric | Iterative loop only | + Structured evidence |
|---|---|---|
| Final report words | 1,307 | 1,255 |
| Inline citations | 10 | 40 (claim ID refs) |
| Source quality tiers | ❌ | ✅ |
| Refute polarity | ❌ | ✅ (1 explicit refute) |
| Gaps section | ❌ | ✅ (3 documented) |
| Contradictions section | ❌ | ✅ (1 tension surfaced) |
| Fabrication detectability | Low | High (snippet in JSON) |
| Traceability | Citation → URL | Claim ID → snippet → URL |
| Artifacts | 1 file | 2 files (evidence.json + report) |
| Total output bytes | 8,473 | ~20,000 |

**Conclusion:** Structuring evidence before writing adds ~2.5× output overhead
but produces materially higher quality: explicit gaps, forced counter-evidence,
source quality awareness, and full traceability. The full multi-agent pipeline
(scout → research → review → planner → writer → stitcher) is NOT needed — the
evidence.json layer alone captures ~80% of the quality gain at ~20% of the
complexity cost.

## Second Validation: Multi-Dimensional Topic (July 2026)

A deeper test ran the v1.2.0 methodology end-to-end on a 5-dimension research question: *"Self-hosted vs cloud API for AI agents in 2026: when does self-hosting become cheaper — considering hardware depreciation, electricity, capability parity, and operational overhead?"*

**Results:** 15 claims, 10 sources, 4 refute-polarity claims, 3 writing_context items. 3 research rounds, 9 queries, ~6 minutes.

**What this validated beyond the first test:**

1. **Refute polarity scales with topic depth.** The first test (LLM comparison) produced 1 refute claim. This deeper topic produced 4 — the r/LocalLLaMA $6.4K server counter-analysis, the "API rates are subsidized" argument, the talent-cost trap, and the latency penalty. The refute requirement forced engagement with the strongest counter-arguments, not just the supportive ones.

2. **Contradictions section captured genuine tension.** Three sources gave different break-even points (50M vs 30M vs "never" tokens/month). Without the structured contradictions section, these would have been smoothed into a single number. The synthesis explained *why* they differ (utilization patterns), which is more honest and more useful than picking one.

3. **Writing context separated facts from boundary conditions.** Three items: regional cost variance (scope), talent cost region-dependence (methodology), and "no CPU-only break-even exists" (availability gap). These aren't claims — they're caveats the reader needs to interpret the claims correctly. This distinction prevented overstating certainty.

4. **Source quality revealed a weakness.** 0 primary sources (all secondary/tertiary). The gaps section flagged this explicitly. A single-pass report would not have surfaced this evidence-strength limitation.

5. **Overview-first report structure worked at scale.** The comparison-at-a-glance table (11 rows × 4 columns) right after the executive summary gave the complete answer in one screen. The 6 detailed sections below were supporting reasoning. The user confirmed this structure is preferred.

**Cost overhead:** evidence.json was 18.6KB + report 14KB = ~33KB total, vs ~14KB for a single-pass report. ~2.4× overhead for materially higher quality (explicit gaps, forced counter-evidence, source quality awareness, full traceability). Worth it for research informing decisions; skip for quick lookups.

## What NOT to Adopt from sn-deep-research

- **Full 9-role multi-agent dispatch** — 9 agent invocations = massive token/latency overhead. Our single-agent loop with evidence.json is sufficient.
- **Content-addressed source snapshots** — good for institutional research with link-rot risk, overkill for everyday reports. The snippet field in evidence.json provides adequate fabrication detection.
- **Python validator scripts (40 rules)** — too heavy. A mental checklist during review is enough: every claim has a real snippet? refute count ≥1? sources classified?
- **Separate format-discovery skill** — our 6-category detection (comparison/product/how-to/fact-check/explainer/factual) is simpler and self-contained.
- **Perspective/supplement loops** — adds 2-3 extra rounds for marginal quality gain on typical tasks.

## Source

Architecture concepts adapted from [OpenSenseNova/SenseNova-Skills](https://github.com/OpenSenseNova/SenseNova-Skills)
(MIT license), specifically the `sn-deep-research` skill's evidence schema v1.2.
The full 9-role pipeline was evaluated and intentionally NOT adopted — only the
evidence structuring layer was ported, based on empirical side-by-side testing.