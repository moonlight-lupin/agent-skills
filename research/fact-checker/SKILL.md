---
name: fact-checker
description: "Targeted claim verification pipeline. Given a factual assertion, search multiple independent sources, cross-check for agreement or contradiction, rate confidence (verified / likely true / disputed / unverified / outdated), and produce a cited verification report."
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [fact-check, verification, claims, citations, cross-check, confidence, research]
  related_skills: [deep-research, source-tracker, entity-research]
---

# Fact Checker

## Overview

Fact Checker is a targeted verification workflow for **one factual assertion at a time**. It exists because agents often produce claims that sound plausible but may be hallucinated, copied from a weak source, contradicted by later data, or stale after new reporting. A normal research pass can gather useful background while still failing to answer the narrow question: **is this specific claim supported, contradicted, outdated, or not verifiable from available sources?**

Use this skill to turn a claim into structured search queries, collect confirming and contradicting passages from multiple independent sources, assess source independence and recency, then produce a concise verification report with citations and a calibrated verdict.

## Quick Start

From this skill directory:

```bash
python scripts/verify.py structure --claim "Singapore's GDP grew 4.1% in 2025"
```

Or use the compatibility shortcut:

```bash
python scripts/verify.py --claim "Singapore's GDP grew 4.1% in 2025"
```

After collecting source passages with a web search tool and web extraction tool, generate a report:

```bash
python scripts/verify.py report \
  --claim claim.json \
  --sources sources.json \
  --output verification-report.md
```

Completion criterion: the report states a verdict, lists every cited source, surfaces contradictions if present, and includes a source-independence note.

## When to Use

- Verify a single factual claim before publishing, sending, or relying on it.
- Check whether a statistic, event, relationship, quote, or date is supported by sources.
- Cross-check an agent-written paragraph by verifying its highest-impact claims one by one.
- Audit a cited claim for source independence and recency.

## When NOT to Use

- Broad topic research or literature review → use a deep research workflow.
- Full entity background dossiers → use an entity research workflow.
- Citation database management → use a source tracking workflow.
- Propaganda, bias, or intent analysis → this skill only verifies factual support.
- Real-time market, weather, emergency, legal, medical, or regulatory determinations → use authoritative live systems and human review.

## The 5-Stage Pipeline

### 1. Parse Claim

Extract the assertion into a structured object:

- **Claim text** — exact wording to verify.
- **Claim type** — statistic, event, relationship, quote, or date.
- **Key terms** — entities, metrics, values, years, dates, and distinctive nouns.
- **Time period** — explicit year/date range if present.
- **Entity / metric / value** — when detectable.
- **Search queries** — 3-5 targeted searches.

Command:

```bash
python scripts/verify.py structure --claim "Singapore's GDP grew 4.1% in 2025" > claim.json
```

Completion criterion: the JSON contains enough terms to search for the claim without relying on memory.

### 2. Search

Run 3-5 targeted searches across **different source families**. Combine:

- Primary/official source query: regulator, statistics agency, company filing, court document, government release.
- Independent news/report query: reputable outlet or analyst report.
- Contradiction query: add terms like `not`, `revised`, `correction`, `dispute`, or an alternative value/date.
- Recency query: add `latest`, current year, `revised`, `updated`, or `final` when the claim has a time period.

Do not treat repeated versions of the same press release as separate evidence.

Completion criterion: the search set includes at least one query likely to find contradiction or newer data, not only confirmation.

### 3. Extract

For each candidate source, extract a short passage that directly confirms, refutes, or nuances the claim. Store sources as JSON:

```json
[
  {
    "url": "https://example.org/report",
    "title": "Example Report",
    "passage": "The economy grew 4.1% in 2025...",
    "stance": "confirm",
    "source_type": "official",
    "accessed_at": "2026-07-06"
  }
]
```

Use `stance` values:

- `confirm` — directly supports the claim.
- `refute` — directly contradicts the claim.
- `nuance` — partially supports, qualifies, or changes scope.

Completion criterion: every source has a URL, title, quoted passage, stance, source type, and access date.

### 4. Cross-Check

Assess four dimensions before deciding:

1. **Source independence** — different root domains are a start, but not enough. Check whether sources rely on the same wire story, press release, filing, or dataset.
2. **Agreement** — count confirming, refuting, and nuancing sources separately.
3. **Contradictions** — if credible sources disagree, present both positions with citations.
4. **Recency** — if the claim refers to a time period, check for later revisions, final data, restatements, or updated filings.

Use the URL assessment helper:

```bash
python scripts/verify.py assess --urls "https://a.example/report,https://b.example/story,https://c.example/data"
```

Completion criterion: the final report explains whether evidence is genuinely independent and current.

### 5. Verdict

Generate the report:

```bash
python scripts/verify.py report --claim claim.json --sources sources.json --output report.md
```

The verdict is a confidence label, not a truth oracle. The report should state what the collected evidence supports, where it conflicts, and what remains unknown.

Completion criterion: the verdict follows the rubric below and the report includes citations, contradictions, notes, and verification date.

## Confidence Rubric

| Verdict | Use when | Minimum evidence |
| --- | --- | --- |
| ✅ Verified | The claim is directly supported by multiple independent reliable sources and no credible contradiction was found. | At least 2 independent confirming sources, current data, no credible refutation. |
| ⚠️ Likely true | The claim is supported by one authoritative source or limited corroboration, with no contradiction found. | 1 official/academic/report source or one strong source plus weak corroboration. |
| ⚖️ Disputed | Reliable sources disagree about the claim. | At least one confirming and one refuting source, neither obviously irrelevant. |
| ❓ Unverified | No reliable source directly supports the claim. | No reliable sources, only weak/irrelevant mentions, or sources do not address the assertion. |
| 📅 Outdated | The claim appears to have been true for an earlier data vintage but newer data contradicts or supersedes it. | Older confirmation plus newer contradictory/revised source. |

### No Hallucination Rule

If no sources are found, the verdict is **Unverified** — never `false`. Absence of evidence in a quick search does not prove the claim is false. Say what was searched, what was not found, and what would be needed for a stronger conclusion.

### Outdated Detection

If a claim references a year, quarter, event date, filing period, or named data release:

- Search for `revised`, `final`, `updated`, `restated`, `latest`, and the current year.
- Prefer the newest official data vintage over older preliminary coverage.
- If older sources confirm but newer sources contradict, use **Outdated** rather than **Disputed** when the newer source supersedes the older one.

### Contradiction Surfacing

When sources disagree, present both sides. Do not silently pick the side that matches the expected answer. Explain differences in wording, scope, units, dates, and data vintages.

## Claim Types

| Claim type | Detection clues | Verification approach | Best sources |
| --- | --- | --- | --- |
| Statistic | Numbers, percentages, currency, rates, rankings | Find original dataset/release; verify units, time period, geography, and revisions. | Statistics agencies, filings, official data portals, audited reports. |
| Event | Acquired, launched, announced, resigned, won, filed, approved | Confirm event happened, date, parties, and status; check follow-up if announced vs completed. | Press releases, filings, regulator notices, reputable news. |
| Relationship | `is CEO of`, `belongs to`, `owned by`, `subsidiary of`, `partnered with` | Verify current relationship and effective dates; check whether relationship changed. | Company pages, filings, registries, official bios, reputable profiles. |
| Quote | Quotation marks, `said`, `wrote`, `according to` | Find original transcript/document/audio; verify exact wording and speaker. | Transcripts, speeches, interviews, primary documents. |
| Date | Explicit year/date, `founded in`, `launched on`, `as of` | Verify exact date and whether it is start, announcement, completion, publication, or effective date. | Official timelines, filings, primary documents, encyclopedic references with citations. |

## Source Independence Rules

Source count is not evidence count. Three articles that all cite one press release count as **one source origin**, not three independent confirmations.

Treat sources as independent only when they come from different organizations and appear to have independently obtained or verified the fact. Root-domain comparison is a useful first pass, but also check:

- Same byline or wire service across multiple sites.
- Same wording and publication timestamp.
- Explicit phrases like `according to the company`, `according to a press release`, or `reported by Reuters`.
- Aggregator pages that summarize another outlet.
- Official data reused by many articles; the dataset is the primary source.

When in doubt, count conservatively and explain the limitation.

## Integrations

- **Deep research workflow** — verify key claims before a long report is published. Run this skill on the most important statistics, dates, and potentially controversial assertions.
- **Source tracker** — log every source used in the verification report with topic tags and notes so citations remain reusable.
- **Entity research** — verify entity-specific claims such as ownership, leadership, registration status, adverse-media assertions, and sanctions-list signals before including them in a dossier.

## Common Pitfalls

1. **Treating secondary sources as independent.** Multiple articles can repeat the same source origin. Trace back to the original.
2. **Confirmation bias.** Queries that only include the asserted value tend to find confirmations. Always run at least one contradiction or revision query.
3. **Declaring `false` without evidence.** A failed search means unverified unless a reliable source directly refutes the claim.
4. **Ignoring recency.** Preliminary data, old bios, and announced-but-not-completed events often become stale.
5. **Mismatched scope.** A source may confirm a similar claim with a different country, time period, unit, denominator, or entity.
6. **Quote laundering.** Do not verify a quote from a quote roundup; find the original transcript, video, speech, or document.
7. **Overweighting domain count.** Different domains can still carry the same syndicated article or press release.

## Verification Checklist

- [ ] Claim is quoted exactly and scoped to one assertion.
- [ ] Claim type, key terms, time period, entity, metric, and value were extracted where possible.
- [ ] Search included official/primary, independent secondary, contradiction, and recency queries.
- [ ] Every source has URL, title, passage, stance, source type, and access date.
- [ ] Source independence was checked beyond root domains.
- [ ] Confirming, refuting, and nuancing sources were counted separately.
- [ ] Contradictions were surfaced with citations.
- [ ] Recency and data vintage were checked for time-bound claims.
- [ ] Verdict follows the confidence rubric.
- [ ] No unsupported claim was upgraded beyond the evidence.

## What This Skill Is NOT

- Not a general research engine.
- Not a propaganda, bias, or intent detector.
- Not a real-time data feed.
- Not a substitute for official databases, professional judgment, legal advice, medical advice, or domain experts.
- Not authoritative on its own; it produces a cited verification report for a person to review.

## Files

- `scripts/verify.py` — rule-based claim structuring, URL independence assessment, and Markdown report generation.
- `references/confidence-rubric.md` — detailed verdict criteria, edge cases, and examples.
- `references/source-independence.md` — source-origin and syndication rules.
- `templates/verification-report.md` — report template used by the CLI output.
- `tests/test_verify.py` — pytest coverage for parsing, reporting, and independence assessment.
