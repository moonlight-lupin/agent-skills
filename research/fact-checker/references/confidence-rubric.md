# Confidence Rubric

Use this rubric to convert collected evidence into a calibrated verification verdict. The labels describe the evidence found, not absolute truth.

## ✅ Verified

### Definition
The claim is directly supported by multiple reliable, genuinely independent sources, and no credible contradiction or newer superseding data was found.

### Minimum requirements
- At least 2 independent confirming source origins.
- Sources directly address the same claim scope: entity, metric, value, date/time period, geography, and unit.
- No credible refuting source found in targeted contradiction searches.
- For time-bound claims, the data is current for the relevant period or no newer superseding source is available.

### Edge cases
- If 5 articles repeat one official release, count the official release as one source origin. This may be `Likely true`, not `Verified`.
- If two independent sources confirm but use old preliminary data and a newer final release differs, use `Outdated`.
- If sources agree on direction but not exact value, use `Likely true` or `Disputed` depending on materiality.

### Examples
- An official statistics release and an independent central bank report both state GDP grew 4.1% in the same year, with no later revision.
- A company filing and a regulator notice both confirm an acquisition closed on the stated date.

## ⚠️ Likely true

### Definition
The claim is supported by one authoritative source, or by limited corroboration that is credible but not independently strong enough for `Verified`.

### Minimum requirements
- One official, academic, audited, or primary source directly confirms the claim; or
- One reputable secondary source reports the claim and no contradiction is found, but original documentation is unavailable.
- Recency checks do not reveal a newer contradiction.

### Edge cases
- A government dataset alone may be enough for `Likely true`; add an independent analysis or second primary source to reach `Verified`.
- A single reputable article quoting a company statement is usually `Likely true` only if the claim is low-risk and uncontroversial.
- A claim from an old biography may be `Likely true` for historical relationship but `Unverified` for current relationship.

### Examples
- One official ministry release states a statistic, but no independent report repeats it yet.
- A court docket confirms a case filing, but no reputable news report has covered it.

## ⚖️ Disputed

### Definition
Reliable sources directly disagree about the claim, or one source confirms while another credible source refutes the same assertion.

### Minimum requirements
- At least one confirming source and one refuting source.
- The disagreement concerns the same scope, not a simple mismatch in dates, geography, or definitions.
- Neither side can be dismissed as irrelevant, duplicate, or obviously stale without explanation.

### Edge cases
- If the refuting source is newer and explicitly supersedes old data, use `Outdated` rather than `Disputed`.
- If sources use different definitions, report the definitional split and use `Disputed` or `Likely true` with caveats.
- If only low-quality sources disagree with authoritative sources, keep the stronger verdict but mention the weak contradiction in notes.

### Examples
- Two official bodies publish different figures for the same metric and period.
- A company says a transaction closed, but a regulator says approval remains pending.

## ❓ Unverified

### Definition
The collected sources do not provide reliable direct support for the claim.

### Minimum requirements
- No reliable confirming source found; or
- Sources mention related topics but do not address the assertion; or
- Sources are too weak, circular, anonymous, or inaccessible to support the claim.

### Edge cases
- `Unverified` does not mean false. It means the verification pass did not find enough evidence.
- If a reliable source directly contradicts the claim and no confirming source exists, the report can say `Unverified; one source refutes the claim` rather than upgrading to `Disputed`.
- For quotes, failure to find the original transcript should usually remain `Unverified` even if quote websites repeat it.

### Examples
- No official or reputable source supports a claimed statistic.
- Several blogs repeat a quote without a transcript, audio, video, or primary document.

## 📅 Outdated

### Definition
The claim appears to have been true for an earlier data vintage or previous state, but newer data or a superseding source contradicts it.

### Minimum requirements
- Older confirming evidence exists.
- Newer source(s) directly contradict, revise, restate, supersede, or update the claim.
- The newer source is at least as authoritative as the older source, or clearly represents a later official/current state.

### Edge cases
- Preliminary vs final economic data often produces `Outdated` if the final release changes the value.
- Leadership and ownership claims become outdated when an official page or filing shows a successor.
- Announced events can become outdated if later reporting says the deal failed, was cancelled, or closed on a different date.

### Examples
- A preliminary 2025 GDP release said 4.1%, but a later final release revised it to 3.9%.
- A 2024 company page listed a CEO, but a 2026 filing lists a replacement.

## Confidence mapping

- **High** — `Verified` with strong independence and recency, or `Outdated` with a clear superseding source.
- **Medium** — `Likely true` or `Disputed` with credible but incomplete evidence.
- **Low** — `Unverified`, weak-source disputes, or any report with major access gaps.
