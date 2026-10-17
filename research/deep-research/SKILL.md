---
name: deep-research
description: "Use when the user asks for \"deep research\", a \"research report on\", a \"comprehensive analysis of\", to \"look into X in depth\", to \"write a report on X\", or any question needing multi-source synthesis beyond a single search — an autonomous multi-step deep research engine implementing an iterative Think → Search → Extract → Synthesize → Stop loop. The LLM drives every decision: what to search, what's relevant, what's missing, and when to stop. Produces a cited, magazine-quality report with inline citations, category-specific formatting, and research stats. For entity vetting/dossiers use entity-research; for news digests use news-monitoring; for source-grounded Q&A use notebooklm-mode."
license: MIT
metadata:
  version: 1.9.2
  author: moonlight-lupin
  platforms: [linux, macos, windows]
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

See `references/structured-evidence-format.md` for the evidence.json layer and
`references/docsgpt-concepts.md` for adaptive-depth concept mapping.

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
  → Step 0: Clarification (optional — assess if question is too vague)
  → Step 1: Plan (sub-questions, key topics, success criteria, category, language, complexity)
  → Step 2: Date grounding + language anchor
  → Step 3: Iterative loop (max rounds = complexity cap: simple=2, moderate=3, complex=5)
      ├─ 3a: Generate gap-driven queries (incl. refute queries from round 2+, empty-search refinement)
      ├─ 3b: Search (web_search) + fetch (web_extract)
      ├─ 3c: Quality filter + extraction + source quality classification + numbered citations
      ├─ 3d: Synthesize into cumulative research state (with token budget check)
      ├─ 3e: Structured evidence (optional: evidence.json for 5+ sources)
      └─ 3f: Stopping check (LLM evaluates coverage + token budget)
  → Step 4: Final report (overview-first structure, see template)
  → Step 5: Stats summary
```

**Report output order (overview-first):** Executive Summary → comparison/overview table → detailed analysis per sub-question → contradictions → gaps → conclusion → source table. Readers get the answer and the at-a-glance comparison before the detailed reasoning.

## Step 0 — Clarification (optional)

Before planning, assess whether the question is specific enough to research productively. This step prevents wasting rounds on a question that's too vague.

**When to clarify:**
- The question is 1-5 words with no scope ("research AI", "tell me about quantum computing")
- The question could mean very different things depending on intent ("is X good?" — good for what? for whom?)
- The question lacks a clear angle ("look into climate change" — scientific? policy? economic?)

**When NOT to clarify:**
- The question already has sub-questions or specific parameters
- The user explicitly says "just research it" or "don't ask, just go"
- The question is specific enough to generate productive search queries immediately
- The question is a simple factual lookup ("what is the latest version of X?", "when did Y happen?") — even if short, if the intent is clear, proceed
- The user is responding to a prior clarification (don't loop)

**How:** Present 1-3 short questions to the user that would narrow the scope. Keep it brief — this is a scope check, not an interview:

> "Before I start researching, I'd like to clarify:
> 1. [narrowing question 1]
> 2. [narrowing question 2]
>
> Please provide these details and I'll begin."

If the question is already specific, skip this step entirely and proceed to Step 1.

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

Complexity: [simple | moderate | complex]
```

**Complexity assessment and adaptive depth:**
Classify the question's complexity to determine the maximum number of research rounds. This prevents over-searching simple questions and under-searching complex ones.

| Complexity | Max rounds | Per-round breadth | When to use |
|---|---|---|---|
| **simple** | 2 | 2 | Single-factual question, narrow scope, 1-2 sub-questions. Example: "What is the latest version of Python?" |
| **moderate** | 3 | 3 | Multi-faceted question, 3-4 sub-questions, comparison or how-to. Example: "Compare Qdrant vs pgvector for RAG" |
| **complex** | 5 | 4 | Broad scope, 5-6 sub-questions, requires deep synthesis across domains. Example: "Comprehensive analysis of the self-hosting vs managed API tradeoff for AI infrastructure" |

The complexity cap is a **maximum**, not a target. The stopping check (Step 3f) still governs early termination. A simple question that finds comprehensive answers in 1 round should stop at 1 — the cap of 2 means it *can* go to 2 if needed, not that it *must*.

**Search budget** (adapted from upstream `research-input.ts` presets + `estimateMaxSearches`): announce the budget in the plan — "Search budget: ≤N queries", N = per-round breadth × max rounds (script: `estimate-budget --breadth B --rounds R`). When round 2+ runs deep-dive chains (§3a), the upper bound is tree-mode: `estimate-budget --breadth B --rounds R --halving`, upstream's breadth-halving recursion. The budget is a ceiling the loop must not exceed; prefer the cheapest round that answers well, per the §3f stopping check.

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

Run **max N rounds** where N = complexity cap from Step 1 (simple=2, moderate=3, complex=5). Most topics converge in 2-3 rounds. The cap is a ceiling, not a target.

Query rules, fetch budgets, quote anchoring, the synthesis template, the evidence store, and stop conditions are in `references/step3-iterative-loop.md`.

| When you hit | Read |
|---|---|
| Query generation, search and fetch, extraction, anchoring, synthesis, or the stopping check | `references/step3-iterative-loop.md` |
| Evidence-store commands and the three delivery gates | `references/validation-gates.md` |
| The evidence.json intermediate | `references/structured-evidence-format.md` |

1. **3a — Query Generation (gap-driven)** — Breadth comes from the Step 1 preset (simple=2, moderate=3, complex=4). Round 1 targets plan sub-questions; later rounds target gaps and recorded follow-ups.
2. **3b — Search and Fetch** — Use the donsetch MCP search/fetch tools when the user asked for them; otherwise `web_search` / `web_extract`. Never abort over a provider preference.
3. **3b.1 — Evidence Persistence (mandatory for 5+ source reports)** — From round 1, persist with `init-run`, `register-source`, `add-claim`, `add-evidence`, and `check-quote` on `scripts/research_validation.py`.
4. **3c — Quality Filter and Extraction** — Discard low-quality results before extracting.
5. **Verbatim snippet anchoring (mandatory for claims you store)** — Every stored claim carries a verbatim contiguous excerpt from that source's page text.
6. **Evidence basis — the four-label discipline** — Tag every material fact with the basis you are asserting it on.
7. **3d — Synthesis** — Fold this round's extractions into the cumulative research state.
8. **3e — Structured Evidence (recommended for reports with 5+ sources)** — Write the `evidence.json` intermediate before the final report. Format: `references/structured-evidence-format.md`.
9. **3f — Stopping Check** — After synthesis, decide whether the report is comprehensive enough. Otherwise open another round, up to the cap.

## Step 4 — Final Report

Produce the final report. Minimum 800 words (scale with topic complexity).

**Output order is overview-first**: the reader gets the answer and the at-a-glance comparison *before* the detailed reasoning. Do not bury the comparison table after the per-topic analysis.

Carry each material fact's **evidence-basis tag** inline (§3c), lead on `[VERIFIED]` / `[SOURCED]`, keep `[REASONED]` / `[ESTIMATED]` claims framed as indicative, and paste the **Evidence key** legend below the Sources table so the tags decode.

**Synthesis prompt structure:** When writing the final report, explicitly consult: (1) the original question, (2) the research plan (sub-questions, success criteria), (3) the cumulative research state from all rounds, (4) the evidence.json if produced, and (5) the numbered source list. Do not rely on the cumulative state alone if it has been compressed across many rounds — go back to the per-round findings to verify key claims. This prevents detail loss when the research state was aggressively summarized due to token budget pressure.

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
[What couldn't be determined from available sources. Each gap should note: what's unknown, why it matters, and whether it could be resolved with more research. If using structured evidence, reference the writing_context items. If no gaps, state "No significant gaps identified." **Source-set bias check (mandatory):** the first gap line must state the bias your whole source set shares — one dominant language, era, school, jurisdiction, or industry — adapted from Munger inversion. A homogeneous source set is itself a gap, even when every individual source is primary-tier.]

## Conclusion
[Synthesis of findings, implications, remaining uncertainties — ties back to the executive summary and overview. The conclusion confirms or qualifies the overview, it doesn't introduce new analysis.]

---
## Sources

**Quality distribution:** [N] primary · [N] secondary · [N] tertiary — [healthy/acceptable/weak]

| # | Title | URL | Quality | Accessed |
|---|-------|-----|---------|----------|
| 1 | [title] | [url] | primary/secondary/tertiary | [date] |

**Citation format:** Inline citations use `[N]` matching the source table above. On first mention of a source, include `[N]` — subsequent mentions may use `[N]` alone. For claims from the same source, cite the number once per paragraph unless the source is paginated.

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
📊 Research stats: [duration] · [N] rounds · [N] queries · [N] page fetches · [N] sources cited · provider: [donsetch/built-in]
```

## Step 5.5 — Validation Gates (mandatory before delivery)

**Deterministic gates** — `scripts/research_validation.py`, stdlib-only, checks structure not judgment. Every report with 5+ sources passes three gates before delivery: `validate-report` (structure), `verify-citations` (inline `[N]` ↔ Sources rows), and `verify-claims --strict` (stored evidence must support each factual claim; a claim stored with `basis: verified` needs sources on ≥2 different sites; at least one `polarity: refute` claim, or `--refute-none "<what you searched>"`). **Loop:** validate → fix → re-run all three, max 3 cycles; still failing → stop and report the remaining problems to the user honestly. Never skip the gates, never deliver with a red gate. Quick 2-3 source reports (no store): `verify-claims` warns instead of failing — record it in the stats block. Full contract, flags, and the failure loop: `references/validation-gates.md`.

**Optional Jev pre-screen.** On instances with TypeSafe Jev configured, add `--jev-prescreen` to `verify-claims` for an advisory semantic pre-check that flags gate false-reds/false-greens before the deterministic run. It degrades to a clean SKIPPED line when Jev is not set up — never blocks, never changes the gate's exit code. See the contract in `references/validation-gates.md`.

**Snippet anchoring prerequisite.** `verify-claims` scores the *stored* snippets — it cannot tell a well-copied quote from a well-paraphrased one. That is what `check-quote` (§3c) is for: a red gate whose snippets never passed `check-quote` means anchoring was skipped, which is itself a defect. Anchor first, store second, gate third.

## Step 6 — Follow-up Report Revision (optional)

For "verify X in the earlier report" / "update the pricing section" requests on a delivered report. Adapted from upstream's evidence panel + `report-revision.ts`: a follow-up researches narrowly and patches **only the passages citing the finding** — the rest of the report stays byte-identical.

1. **Map.** `python3 <skill_dir>/scripts/research_validation.py map-citations --report <report.md> [--citation N]` returns the top-level blocks citing each `[N]` (code fences excluded; exit 1 = no block cites N). This defines exactly what a follow-up may touch — nothing else.
2. **Bounded follow-up research.** One round, ≤2 query directions derived from the target finding and the user's instruction. Same snippet-first triage and quality filter (§3b/§3c); new page text joins the existing run dir; register new sources before citing them.
3. **Patch cited blocks only.** Revise the blocks from step 1 (tables and lists are updated as whole blocks). Leave unrelated paragraphs untouched. If the evidence contradicts the existing claim, state the correction; if it is insufficient, say so instead of inventing a fix.
4. **Sources.** Append new entries to the Sources table with the next free numbers; never renumber existing citations — old inline `[N]`s must keep resolving.
5. **History.** Save the revision as `<name>-rev.md` next to the original (`-rev2`, `-rev3`, … for further rounds). The original file stays untouched; on failure or cancellation, nothing is saved.
6. **Re-run all three gates** (Step 5.5) on the revised report before delivery. A red gate after revision means the revision did not land cleanly — fix, don't ship.

## Follow-on Investment Analysis (optional)

When the report covers an investment question and the user provides deal parameters, build a quantitative pro-forma using `execute_code`. Always model the as-is use as a baseline. See `references/real-estate-investment-analysis.md` for the template.

See `references/structured-evidence-format.md` for the evidence.json schema and writing-context vs claims distinction.

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

- Full-page fetches are on-demand and budgeted (§3b): ≤2/round, run-wide cap by complexity — snippets carry the triage
- If `web_extract` fails on a URL, note it and move on — don't retry endlessly
- If `web_search` returns no results, apply the §3a refinement protocol including the identical-rewrite stop

## Pitfalls

- **Overclaiming basis** — when torn between two labels, pick the weaker one. A source's "about half" stays `~50% [SOURCED]`.
- **Conflating claims with context** — subject facts are claims; scope, methodology, and availability limits are writing_context.
- **Subagent self-reports** — verify source URLs exist before citing. The orchestrator synthesizes.
- **Clarification: one round** — if the reply is still vague, proceed with the best interpretation of intent.
- **Complexity misclassification** — complexity is breadth of synthesis, not how impressive the topic sounds. A narrow factual topic with six sub-questions is moderate.
- **Token budget fills before the cap** — on long extractions, summarize aggressively when context is tight rather than waiting for the round ceiling.
- **Word-boundary matching** — "port" matching "transport" or "support" is a false hit; filter on topical relevance, not substring overlap.
- **Store claims are quote-shaped** — the deterministic scorer supports a claim only when ONE stored snippet covers every figure, year AND entity the claim text carries; anything else caps at `partial`−0.01 (strict red for factual). The law, validated live three times in one session: multi-fact claims split per snippet, claim text byte-aligns to its quote, and prose paraphrase stays in the report body. Instances of the same law: **CJK claims** extract no tokens, so even an identical snippet scores ~0.33 — byte-identical claim text (entity axis 1.0) or anchor via `check-quote` (tokenization-free) instead; **glommed capitalized runs** ("Scrape URL FIRECRAWL" → one entity `scrape url`) never set-match a claim that says "Firecrawl" alone; **alphanumeric brand prefixes** ("x402" → figure `402`) cap unless the snippet carries the brand text. Diagnose with the script's `_figures`/`_entities`/`_tokens` helpers before rewriting.
- **Anchored to the wrong substrate** — `check-quote --source-id` reads `pages/<source_id>.txt`; verify the id resolves to the URL the sentence actually came from before treating a mismatch as fabrication — the same sentence on another page's file gives a false red.
- **Unanchored snippets** — storing a snippet (or evidence) that never passed `check-quote` is how a smooth paraphrase becomes "evidence": the scorer sees familiar tokens and rates it supported. Verbatim excerpt, checked against the saved page text (`<run_dir>/pages/<source_id>.txt`), repair-once on mismatch — never massage the snippet toward the claim, never splice across paragraphs. No contiguous excerpt exists? The claim is not evidence-backed; store it honestly and let the gate flag it.
- **Store CLI ordering and field pairs** — the subcommand must precede `--dir` (`research_validation.py add-claim --dir <d> ...`, never `--dir <d> add-claim`). `add-claim` takes claim+kind+polarity+basis+snippet+source_id; `add-evidence` takes evidence_snippet+source_id — swapping the pairs stores the snippet in source_id and surfaces later as unregistered-source_id warnings. `basis` takes ONLY the four labels — a source TIER name (`primary`/`secondary`) is rejected (rc 2), and `kind` takes no `refute` value: refute is a **polarity**. When looping store calls in a script, check every response's JSON — a rejected call exits 2 silently while the loop's "stored" message lies.
- **Citation density in the body** — every Sources row must be cited at least once (`verify-citations` fails on uncited rows); required sections (`## Executive Summary`, `## Contradictions`, `## Gaps`, `## Conclusion`) must be `##`-level, not `#`.
- **Fallback if synthesis fails** — compile raw findings with citations and tags; empty output is the failure mode.
- **Evidence key** — paste the four-label legend under the Sources table so `[VERIFIED]` / `[SOURCED]` / `[REASONED]` / `[ESTIMATED]` decode.

## Related Work

[Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) — PewDiePie's self-hosted AI workspace — includes a "Deep Research" feature with multi-step web research and source reading, conceptually similar to this skill's Think → Search → Extract → Synthesize → Stop loop. This skill is a pure-prompt workflow (no UI, no server) designed to run inside any agent's tool loop.

[AnotiaWang/deep-research-web-ui](https://github.com/AnotiaWang/deep-research-web-ui) (MIT) — Nuxt UI wrapping dzhng/deep-research with a hardened engine, and the main vendor source for this skill. **Vendored:** verbatim-quote evidence anchoring, v1.8.2 (`shared/utils/search-learning.ts` → `check-quote`, §3c); structured search mini-plans with frozen constraints, planning discipline and provider guidance, v1.9.0 (`shared/utils/search-plan.ts` → §3a); search-budget presets + breadth-halving estimate, v1.9.0 (`shared/utils/research-input.ts` → Step 1 + `estimate-budget`); bounded deep-dive threading on follow-up directions, v1.9.0 (`lib/core/deep-research.ts` → §3a); six-way round-outcome taxonomy with per-reason bounded retry, v1.9.1 (`shared/utils/search-assessment.ts` → §3a); snippet-first on-demand reading with fetch budgets, v1.9.0 (`lib/core/read-source.ts` → §3b); term-scored verbatim passage selection, v1.9.0 (`lib/core/source-context.ts` → §3d); surgical report revision with citation→block mapping, v1.9.0 (`shared/utils/report-revision.ts` → Step 6 + `map-citations`). **Evaluated, not vendored:** full tree recursion, streaming-JSON structured-output repair, UI/deployment layers, and dzhng's "the source is irrelevant" prompt (contradicts this skill's provenance discipline). Full two-sided map: `references/anotiawang-deep-research-concepts.md`.

[Anjos2/recursive-research](https://github.com/Anjos2/recursive-research) (MIT) — Claude Code prompt skill for long-cycle recursive research. **Vendored (v1.9.2, guidance-level):** saturation-based stop signal (§3f), coverage balancing across plan sub-questions (§3a), mandatory source-set bias check in the Gaps section (Step 4). **Not vendored:** cycle machinery, WDM weighted-source scoring, per-domain seed source lists, preventive context-pause thresholds, local-corpus mode. The ≤5% threshold is unvalidated upstream (repo last pushed 2026-04-22, no field hardening); it ships as a signal, not a rule. Map: `references/recursive-research-concepts.md`.

[DocsGPT](https://github.com/arc53/DocsGPT) (arc53, MIT) — ResearchAgent Plan → Research → Synthesize with adaptive depth, clarification, token-budget tracking, and empty-search refinement. Mapping: `references/docsgpt-concepts.md`.

`references/skills-monetization.md` — condensed AI-skills monetization knowledge bank (marketplaces, what sells, pricing) from the 2026-07-01 research dossier.

## Evals

`evals/routing-fixtures.json` holds lightweight contract fixtures — sample request →
expected routing, required output fields, and forbidden output patterns. They are
specs, not run against a live model; the repo-root `tests/test_routing_fixtures.py`
validates they stay well-formed and route to real skills.
