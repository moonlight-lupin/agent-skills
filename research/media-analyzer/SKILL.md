---
name: media-analyzer
description: "Technique-focused media analysis. Detects rhetorical tools (loaded language, cherry-picking, source selection bias, framing, omission, emotional appeals, false balance) in articles and produces a structured analysis report. Identifies specific techniques and bias-signal intensity without labeling political positions."
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [media, bias, framing, rhetoric, propaganda, analysis, critical-thinking, source-evaluation]
  related_skills: [fact-checker, deep-research, source-tracker]
---

# Media Analyzer

## Overview

Media Analyzer is a technique-focused workflow for reading news articles, opinion pieces, press releases, and other media with a critical but neutral lens. Media texts often use rhetorical choices to shape perception: emotionally charged verbs, selective statistics, source mixes, framing metaphors, omissions, emotional appeals, and disproportionate presentation of evidence. This skill identifies those observable techniques systematically without deciding which political position is correct.

Use this skill when the goal is to understand **how** a text guides interpretation. Do not use it to label an outlet, author, or article as left-wing, right-wing, conservative, liberal, pro-X, or anti-Y. The output is a structured analysis report that surfaces technique usage and leaves conclusions to the reader.

## Core Principle: Detect Techniques, Not Positions

The central rule is: **DETECT TECHNIQUES, NOT POSITIONS.**

Never label a source as "left-wing," "right-wing," "conservative," "liberal," or "biased toward X." Instead, identify specific rhetorical tools:

- loaded words and their neutral alternatives;
- source types quoted or omitted;
- statistics cited and relevant data not cited;
- framing devices such as metaphor, naming choices, presupposition, or loaded questions;
- emotional appeal patterns;
- false balance between positions with unequal evidence weight.

A valid finding says: "The article uses three high-intensity verbs in the first four paragraphs." An invalid finding says: "The article is biased against the policy." Keep the analysis observable, specific, and politically direction-neutral.

## Quick Start

From this skill directory:

```bash
python scripts/analyze.py scan --input article.md
```

Save scan output and generate a report:

```bash
python scripts/analyze.py scan --input article.md --output analysis.json
python scripts/analyze.py report --scan analysis.json --output report.md
```

Review the loaded-language dictionary:

```bash
python scripts/analyze.py wordlist --format table
```

Completion criterion: the report lists detected technique signals, identifies where contextual research is still required, explains the bias-signal spectrum as intensity only, and avoids political-direction labels.

## The 7 Technique Categories

### 1. Loaded Language

**Definition:** Emotionally charged verbs, adjectives, nouns, or modifiers replace neutral wording and guide the reader's reaction.

**Detection criteria:** Compare word choice against neutral alternatives. Ask whether the same factual event could be reported with less emotional force.

**Examples:**

- "slammed" vs. "responded";
- "devastating" vs. "significant";
- "blasted" vs. "criticized."

**Script support:** `scripts/analyze.py` counts loaded words against a built-in word list of aggressive verbs, emotional adjectives, dismissive terms, and framing words. Each detected instance includes paragraph context and a neutral alternative.

### 2. Cherry-Picking

**Definition:** Citing only data, examples, or time periods that support a thesis while leaving out readily available qualifying or conflicting data.

**Detection criteria:** Compare cited statistics against available data on the topic. Check time windows, baselines, revisions, uncertainty, and representative comparison groups.

**Examples:**

- citing one month of sales growth while omitting the annual decline;
- highlighting one school result without district-wide comparison;
- reporting a single survey question while omitting the full survey context.

**Script support:** The script does not verify cherry-picking. Use it to scan the article, then use a web search tool and web extraction tool to locate primary data and compare what exists against what was cited.

### 3. Source Selection Bias

**Definition:** Quoting or paraphrasing sources from only one institutional type or perspective when the topic has relevant perspectives beyond that group.

**Detection criteria:** Count and categorize quoted or attributed sources by institutional type: official, expert, citizen, organization, or unknown. Then assess whether the source mix fits the topic.

**Examples:**

- a transit article quotes only agency officials and no riders or independent planners;
- a workplace article quotes only management and no employees or outside labor experts;
- a product safety story quotes only a manufacturer and no regulator or customer.

**Script support:** `scripts/analyze.py` extracts attribution patterns such as "according to X," "X stated," "said X," and quoted statements followed by attribution. It categorizes source mentions by keyword.

### 4. Framing

**Definition:** Presenting information in a way that guides interpretation through naming, metaphor, order, headline wording, presupposition, or question structure.

**Detection criteria:** Identify framing devices such as metaphor, presupposition, loaded questions, and naming choices.

**Examples:**

- "rightsizing" frames job cuts as correcting a size error;
- "gaming industry" vs. "gambling industry" uses different naming frames for the same businesses;
- "streamlining" presupposes the existing process was inefficient;
- "Why did the plan fail?" presupposes failure before demonstrating it.

**Script support:** The script can count questions and loaded words that may indicate framing. Framing judgment requires analyst or LLM review.

### 5. Omission

**Definition:** Relevant context is left out in a way that changes how readers understand the article.

**Detection criteria:** Check what topics, baselines, time periods, caveats, or primary-source context are absent but relevant.

**Examples:**

- incident counts without a baseline rate;
- budget changes without inflation-adjusted context;
- study results without sample size or limitations.

**Script support:** The script cannot know what is missing. Use a web search tool to identify available context, primary sources, timelines, and caveats.

### 6. Emotional Appeals

**Definition:** Appeals to fear, outrage, pity, anger, urgency, or authority that may steer reader response or substitute for evidence.

**Detection criteria:** Identify emotional manipulation patterns and compare their intensity against the evidence provided.

**Examples:**

- "think of the children" used as a debate-closing appeal;
- fear-mongering language such as "catastrophe" without scale or likelihood;
- outrage manufacturing through repeated scandal terms without proportional evidence.

**Script support:** `scripts/analyze.py` detects fear words, outrage words, pity appeals, appeal-to-authority phrases, and urgency phrases.

### 7. False Balance

**Definition:** Presenting unequal evidence positions as equivalent.

**Detection criteria:** Compare the weight given to majority and minority positions, including source expertise, evidence quality, and consensus level.

**Example:** If 97% of relevant scientists say X and 3% say Y, an article gives equal space to both without explaining the evidence imbalance.

**Script support:** Source counts can suggest a space-allocation pattern, but false-balance analysis requires contextual research into evidence weight.

## The 4-Stage Pipeline

### 1. Extract

Pull the article text into Markdown or plain text. Identify the title, author, publication date, source URL if available, sources cited, direct quotes, and visible statistics.

Completion criterion: the article text is available locally and source metadata is recorded if available.

### 2. Scan

Run rule-based analysis:

```bash
python scripts/analyze.py scan --input article.md --output analysis.json
```

The scan reports:

- loaded-language count and instances;
- source mention extraction and source-type counts;
- emotional appeal patterns;
- paragraph count, average sentence length, questions, and exclamation marks;
- technique-count intensity score.

Completion criterion: `analysis.json` exists and includes the article's word count, technique count, and bias-signal spectrum score.

### 3. Contextualize

Use contextual research for what the script cannot know:

- **Cherry-picking:** use web search to find primary datasets, longer time series, revisions, and independent summaries.
- **Omission:** search for relevant baselines, caveats, event history, and missing affected groups.
- **False balance:** compare evidence weight, source expertise, and consensus level.
- **Framing:** review headline, lead, order, naming choices, and presupposed questions.

Completion criterion: the analyst can state what relevant context was checked and whether missing context was detected, not detected, or uncertain.

### 4. Report

Generate a draft report:

```bash
python scripts/analyze.py report --scan analysis.json --output report.md
```

Then fill in context-dependent sections using the contextual research. Use `templates/analysis-report.md` when writing a report manually.

Completion criterion: the final report contains specific instances, a bias-signal spectrum, and a "What's Missing" section populated from research or marked "not detected / insufficient context."

## Output Format

Reports should follow this structure:

```markdown
# Media Analysis Report

## Source: [title or filename]

## Overview
- Word count: N
- Techniques detected: N
- Bias-signal spectrum: [Neutral/Slight lean/Clear lean/Partisan]
- Spectrum note: intensity of observable rhetorical and source-selection signals; not ideology or political direction.

## Techniques Detected

### 1. Loaded Language (N instances)
- "slammed" (para 3) — neutral alternative: "responded"
- "devastating" (para 7) — neutral alternative: "significant"

### 2. Source Selection (N sources)
- Official: 2, Expert: 1, Citizen: 1, Organization: 0, Unknown: 0
- [Any source-type concentration noted]

### 3. Emotional Appeals (N instances)
- Fear-based: 1
- Appeal to authority: 1

## Bias-Signal Spectrum
Neutral ──── Slight lean ──── Clear lean ──── Partisan ──── Propaganda
              ↑ here

This spectrum rates the density and intensity of observable rhetorical tools, framing choices, and source-selection signals. It does not label the outlet, author, article, or political position.

## What's Missing
[Contextual research findings: relevant context omitted, not detected, or uncertain]

## Notes
- Analysis detects techniques, not political positions
- Intensity rating reflects density of rhetorical tools, not direction of bias
```

## The Bias-Signal Spectrum

Use the spectrum as an **intensity scale for observable bias signals**, not a political label:

```text
Neutral ──── Slight lean ──── Clear lean ──── Partisan ──── Propaganda
```

The score rates density and intensity of rhetorical tools, framing choices, source-selection patterns, and other observable signals. It does **not** say what direction the article leans. The script counts signals only for things that are unusual in neutral copy — normal journalism must not score:

- loaded-language hits (any) → 1 signal;
- single-perspective sourcing (3+ sources, all one type) → 1 signal — plain attribution never counts;
- distinct emotional-appeal patterns → up to 2 signals (capped, so a wordlist pile-up alone can't reach "Partisan");
- 2+ rhetorical questions → 1 signal (a single question is ordinary);
- any exclamation marks → 1 signal (rare in straight news copy).

The total maps to the label:

- `0` signals → Neutral;
- `1-2` signals → Slight lean;
- `3-4` signals → Clear lean;
- `5+` signals → Partisan.

Reserve the word "Propaganda" for exceptional human-reviewed cases with dense, coordinated technique usage and strong evidence that informational accuracy is subordinated to persuasion. Do not apply it casually.

## Neutrality Rules

Critical rules:

- Never label political direction: left/right/conservative/liberal/pro-X/anti-Y.
- Describe techniques, not positions.
- Present findings as observations, not judgments.
- Use neutral language in the report itself; practice what the analysis asks of the article.
- If a technique is not detected, write "not detected" or "insufficient context"; do not invent.
- Quote the article text or cite contextual evidence before interpreting.
- Treat script output as signals, not proof of intent.

See `references/neutrality-rules.md` for the full checklist.

## Integration with Related Skills

- **Fact-checker:** verify factual claims and statistics found in the article. Media Analyzer identifies technique usage; it does not determine truth or falsehood.
- **Source-tracker:** log article URLs, primary data, contextual sources, and access dates for reproducible analysis.
- **Deep-research:** investigate omitted context, evidence weight, consensus level, and broader source landscape.

## Common Pitfalls

1. **Labeling positions instead of techniques.** Replace "biased toward X" with a specific observation such as "all attributed sources are officials."
2. **Confusing strong opinion with propaganda.** Opinion writing can be forceful without using manipulative technique density.
3. **Treating all emotional language as manipulation.** Human-impact reporting may legitimately include emotion; assess proportionality and evidence.
4. **Letting the analyst's own bias drive detection.** Apply the same criteria to articles you agree with and articles you disagree with.
5. **Over-detecting.** A single loaded word does not prove a pattern. Count it, contextualize it, and avoid overstating.
6. **Ignoring legitimate editorial voice.** Feature writing, columns, reviews, and advocacy pieces have different norms than straight news. Identify the format before evaluating technique use.
7. **Treating source count as source quality.** Five sources from the same institutional perspective may be less diverse than two sources from distinct relevant perspectives.
8. **Treating the spectrum as political direction.** The spectrum is bias-signal intensity only.

## What This Skill Is NOT

- Not a political bias classifier.
- Not a truth/falsehood detector; use a fact-checking workflow for claim verification.
- Not a censorship tool.
- Not authoritative; it is a lens for critical reading.
- Not a substitute for primary-source research when detecting omission, cherry-picking, or false balance.

## Verification Checklist

- [ ] Article text was extracted and scanned.
- [ ] Loaded-language instances include neutral alternatives and paragraph context.
- [ ] Source mentions were categorized by institutional type.
- [ ] Emotional appeal signals were reported without assuming intent.
- [ ] Cherry-picking, omission, framing, and false balance were checked with contextual research or marked uncertain.
- [ ] The report contains no political-direction labels.
- [ ] The bias-signal spectrum is explained as intensity, not direction.
- [ ] Every uncertain or absent finding is marked "not detected" or "insufficient context."
