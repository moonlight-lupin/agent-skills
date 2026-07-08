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
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, deep-research, report, synthesis, iterative, citations]
    related_skills: [news-monitoring, entity-research, notebooklm-mode, youtube-topic-research, fact-checker, source-tracker]
---

# Deep Research — Iterative Research Engine

An autonomous, multi-step research engine that performs exhaustive information
gathering and synthesis. Unlike a single `web_search`, this skill implements an
iterative loop where the agent plans, searches, extracts, synthesizes, and
decides when to stop — producing a cited report.

Inspired by PewDiePie's Odysseus project and Alibaba/Tongyi's IterResearch
approach, adapted for Hermes's tool architecture.

## When to use

- User asks for "deep research", "research report", "comprehensive analysis"
- User wants a written report on a topic (not just a quick answer)
- Question requires multi-source synthesis with citations
- User says "look into X in depth" or "write a report on X"

## When NOT to use

- **Entity vetting/dossiers** → use `entity-research` (has sanctions screening, structured lenses)
- **Recurring news digests** → use `news-monitoring` (has cron, dedup, multi-language)
- **Source-grounded Q&A from collected sources** → use `notebooklm-mode` (has vault + RAG)
- **Verifying a single, specific claim** ("is it true that X?") → use `fact-checker` (confidence rubric, source-independence checks; never renders "false"). The fact-check *report category* below is for claims that surface during a broader research topic.
- **Quick factual question** → just use `web_search` directly
- **Single-source extraction** → use `web_search` + `web_extract`

## Architecture

```
User question
  → Step 1: Plan (sub-questions, key topics, success criteria)
  → Step 2: Date grounding
  → Step 3: Iterative loop (max 5 rounds)
      ├─ 3a: Generate gap-driven search queries
      ├─ 3b: Search (web_search) + fetch (web_extract)
      ├─ 3c: Quality filter + goal-based extraction
      ├─ 3d: Synthesize into cumulative research state
      └─ 3e: Stopping check (LLM evaluates coverage)
  → Step 4: Final report (category-specific format)
  → Step 5: Stats summary
```

## Step 1 — Research Plan

Before searching, break the question into a research plan. Output:

```
## Research Plan
Question: [user's question]
Date: [current date]

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

### 3d — Synthesis

After extracting from all sources in the round, integrate findings into the **cumulative research state**:

```
## Research State (after Round N)
[evolving synthesis of all findings so far]

### Sub-question 1: [question]
Status: [answered / partially answered / unanswered]
Findings: [synthesized facts with inline citations like (Source: URL, Title)]

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
- **Update gap list** — what sub-questions are still unanswered or thin?

### 3e — Stopping Check

After synthesis, evaluate whether the report is comprehensive enough:

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

### Structure

```markdown
# [Report Title]

> **Research date:** [date] · **Rounds:** [N] · **Sources:** [N] · **Category:** [type]

## Executive Summary
[2-3 paragraph overview of key findings]

## [## Section per sub-question]
[Detailed analysis with inline citations]

### [### Subsections as needed]
[...]

## Conclusion
[Synthesis of findings, implications, remaining uncertainties]

---
## Sources
| # | Title | URL | Accessed |
|---|-------|-----|----------|
| 1 | [title] | [url] | [date] |
```

### Category-specific formats

| Category | Format |
|---|---|
| **comparison** | Markdown table comparing options across criteria, pros/cons per option, verdict |
| **product** | Ranked list with pros/cons, "where to buy" or availability, price range if found |
| **how-to** | Numbered steps with prerequisites, common mistakes section, troubleshooting |
| **fact-check** | Evidence for/against the claim, source credibility assessment, final verdict (True/False/Mixed/Unverified) |
| **explainer** | Progressive depth — start simple, go deeper. Glossary of terms if technical. |
| **factual** | Standard report structure above |

### Fallback report

If LLM synthesis fails (timeout, error, garbled output), compile raw findings into a basic report:
- List all findings grouped by sub-question
- Include source URLs
- Add note: "This is a raw findings compilation; synthesis was not completed."
- Never output "No information could be gathered" if any sources were fetched — always compile what exists.

## Step 5 — Research Stats

After the report, output a compact stats block:

```
---
📊 Research stats: [duration] · [N] rounds · [N] queries · [N] URLs fetched · [N] sources cited
```

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
- **Synthesis failure produces nothing** — always use the fallback report if synthesis fails. Raw findings > no output.
- **Ignoring contradictions** — if sources disagree, present both. Don't silently pick one.
- **Fabricating sources** — never invent URLs, titles, or facts. If a sub-question can't be answered, document it as a gap.
- **Subagent synthesis** — never delegate the synthesis step. The orchestrator must see all findings to synthesize honestly.

## Related Work

[Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) — PewDiePie's self-hosted AI workspace — includes a "Deep Research" feature with multi-step web research and source reading, conceptually similar to this skill's Think → Search → Extract → Synthesize → Stop loop. This skill is a pure-prompt workflow (no UI, no server) designed to run inside any agent's tool loop.

## Evals

`evals/routing-fixtures.json` holds lightweight contract fixtures — sample
request → expected routing (including when a request should go to
`entity-research` / `notebooklm-mode` / `news-monitoring` instead), required
output fields, and forbidden output patterns. They are specs, not run against a
live model; the repo-root `tests/test_routing_fixtures.py` validates they stay well-formed and
route to real skills.