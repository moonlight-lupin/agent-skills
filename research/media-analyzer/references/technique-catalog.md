# Media Technique Catalog

This catalog defines the seven technique categories used by the media-analyzer skill. The categories are technique-focused, not political-direction labels.

## 1. Loaded Language

**Definition:** Emotionally charged verbs, adjectives, nouns, or modifiers replace more neutral wording and guide the reader's reaction.

**Detection criteria:**

- A word carries evaluative force beyond the factual description.
- A neutral alternative could communicate the same event with less emotional pressure.
- The wording appears in news framing, headline, attribution, or summary rather than inside a clearly marked quote.

**Examples:**

- "The company **slammed** the report" vs. "The company **responded to** the report."
- "A **devastating** budget change" vs. "A **significant** budget change."
- "Residents were hit by a **shocking** fee increase" vs. "Residents received an **unexpected** fee increase."

**Script vs. judgment:**

- Script: counts built-in loaded terms and reports paragraph context.
- Analyst/LLM: decides whether the word is warranted by the evidence, whether it appears in a quote, and whether repetition creates a pattern.

**Edge cases:**

- Strong reporting about severe events can legitimately use strong language.
- Quoted language may reflect a source's rhetoric rather than the article's own voice.
- Technical terms can look loaded outside their field, such as "critical failure" in engineering.

## 2. Cherry-Picking

**Definition:** The article cites only the data, examples, or time windows that support its thesis while excluding readily available conflicting or qualifying data.

**Detection criteria:**

- A statistic is presented as representative without showing the comparison set.
- The selected time period creates a stronger impression than adjacent periods.
- Available primary data contains revisions, uncertainty intervals, counterexamples, or broader trends not mentioned.

**Examples:**

- Citing one month of retail sales without noting the annual trend moved in the opposite direction.
- Reporting a single school test score increase without mentioning district-wide results.
- Highlighting one company's successful quarter while omitting sector-wide losses that affect interpretation.

**Script vs. judgment:**

- Script: does not verify cherry-picking; it can help extract visible statistics for follow-up.
- Analyst/LLM with web search: compares cited data against primary datasets, longer time series, and independent summaries.

**Edge cases:**

- Short articles may reasonably cite only one number if they link to the full dataset.
- Editorials can use illustrative examples, but should not imply they are representative without support.
- Absence of data is not cherry-picking unless relevant data is available and material.

## 3. Source Selection Bias

**Definition:** Attributed sources come mainly from one institutional type, affected group, or perspective, causing the source mix to guide interpretation.

**Detection criteria:**

- Quotes or paraphrases are concentrated in one source type.
- The topic has clearly relevant perspectives that are not represented.
- The article relies on interested parties while presenting the account as broadly sourced.

**Examples:**

- A transportation article quotes only agency officials, with no riders, drivers, or independent planners.
- A workplace article quotes only management, with no employees, union representatives, or outside labor experts.
- A product safety article quotes only the manufacturer, with no regulator, customer, or independent test source.

**Script vs. judgment:**

- Script: extracts attribution patterns and categorizes sources as official, expert, citizen, organization, or unknown using keywords.
- Analyst/LLM: assesses whether the source mix is adequate for the topic and whether missing source types are material.

**Edge cases:**

- Breaking news may initially rely on officials because other sources are unavailable.
- Some technical topics legitimately require expert-heavy sourcing.
- A profile or interview format may intentionally focus on one voice; label the format rather than treating it as manipulation.

## 4. Framing

**Definition:** Presentation choices steer interpretation by naming, metaphor, order, presupposition, headline wording, or question structure.

**Detection criteria:**

- The wording implies a value judgment before evidence is presented.
- Naming choices activate a metaphor or moral category.
- Questions presuppose a contested fact.
- The lead emphasizes one consequence while burying another equally relevant consequence.

**Examples:**

- "Rightsizing" frames job cuts as correcting a size error; "staff reduction" is more neutral.
- "Streamlining" presupposes the existing process was inefficient; "reorganising" carries less of that load.
- "Gaming industry" and "gambling industry" use different naming frames for the same businesses — one chosen by the industry, one by its critics.
- "Pre-owned vehicle" and "used car" name the same product with different polish.
- "Security researcher" and "hacker" frame the same person as professional or threat.
- "Why did the safety plan fail?" presupposes failure before showing evidence.

**Script vs. judgment:**

- Script: can count questions and loaded terms that may be framing signals.
- Analyst/LLM: identifies metaphors, presuppositions, headline framing, naming choices, and order effects.

**Edge cases:**

- All writing frames information to some extent; the question is whether the framing materially guides interpretation.
- Standard legal, medical, or administrative terms may be precise rather than manipulative.
- A headline may be written by an editor rather than the article author; analyze it separately when relevant.

## 5. Omission

**Definition:** Relevant context is absent in a way that materially changes how readers understand the article.

**Detection criteria:**

- The article discusses an event without prior history needed for interpretation.
- It cites an effect without the baseline rate or comparison group.
- It excludes a known correction, limitation, or key caveat from primary sources.

**Examples:**

- Reporting a rise in reported incidents without noting a change in reporting rules.
- Covering a drug study without mentioning sample size or study limitations.
- Discussing a budget increase without inflation-adjusted or population-adjusted context.

**Script vs. judgment:**

- Script: cannot know what context is missing.
- Analyst/LLM with web search: identifies relevant primary sources, timelines, baselines, and omitted caveats.

**Edge cases:**

- Not every absent detail is an omission; relevance and materiality matter.
- Space limits can justify leaving out secondary background.
- Follow-up articles may rely on context established earlier; check the series if available.

## 6. Emotional Appeals

**Definition:** The article appeals to fear, outrage, pity, anger, urgency, or authority in a way that may substitute for evidence or steer response.

**Detection criteria:**

- Emotionally salient terms cluster around a preferred interpretation.
- The text asks the reader to feel before supplying supporting evidence.
- Vulnerable groups, crisis language, or authority claims are used without proportionate factual support.

**Examples:**

- "Think of the children" used to close debate rather than provide child-specific evidence.
- "A catastrophe is coming" without showing scale, likelihood, or uncertainty.
- "Experts prove" when the article cites only one preliminary study.

**Script vs. judgment:**

- Script: detects surface terms for fear, outrage, pity, authority appeals, and urgency.
- Analyst/LLM: decides whether the emotional language is proportionate to the facts and whether evidence follows the appeal.

**Edge cases:**

- Human-impact reporting legitimately includes emotion.
- Safety warnings may need urgency when risk is immediate and well supported.
- Authority citations are normal when source expertise is relevant; the issue is overclaiming or substituting authority for evidence.

## 7. False Balance

**Definition:** Unequal evidence positions are presented as equivalent, giving a minority or weakly supported position the same weight as a well-supported position.

**Detection criteria:**

- The article gives equal space to positions with very different evidentiary support.
- It frames a settled factual matter as a two-sided debate without explaining evidence weight.
- It quotes a fringe or low-evidence view as a peer to a broad expert consensus.

**Examples:**

- If 97% of relevant scientists support X and 3% reject X, the article gives equal space to both without explaining the imbalance.
- A medical article pairs a large clinical guideline with one anecdotal objection as if they carry equal evidentiary weight.
- A product review gives equal weight to thousands of verified defect reports and one manufacturer denial without testing or context.

**Script vs. judgment:**

- Script: source counts can suggest whether space is balanced, but cannot determine evidence weight.
- Analyst/LLM with web search: compares source weight, quality, expertise, consensus, and proportional coverage.

**Edge cases:**

- Legal disputes may require presenting both parties' claims even when evidence later favors one side.
- Emerging topics may not have a settled evidence distribution.
- A feature about a minority view can be legitimate if it clearly identifies the view's status.

## Cross-Technique Review Sequence

1. Run the script to identify surface signals: loaded words, source types, emotional terms, questions, exclamation marks.
2. Extract factual claims and statistics for separate verification if needed.
3. Use web search and web extraction to find primary data and independent context.
4. Mark each technique as detected, not detected, or uncertain.
5. Write observations in neutral language and avoid political-direction labels.
