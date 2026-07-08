# Source Independence Rules

Source independence asks whether evidence comes from separate source origins, not merely separate URLs. A verification report should count source origins conservatively.

## What counts as independent

A source is likely independent when it has a different organization and appears to have obtained or checked the claim separately.

Examples:

- An official statistics release and an independent central bank report.
- A company filing and a regulator approval notice.
- Two news organizations with separate bylines, materially different reporting, and no shared wire attribution.
- A peer-reviewed paper and an official dataset, if each independently supports the same point.

Primary sources are often authoritative but not automatically independent from articles that quote them. If a news article only repeats an official release, the release remains the single source origin.

## What does NOT count as independent

Do not count these as separate independent confirmations:

- Syndicated articles republished across many domains.
- AP, Reuters, AFP, Bloomberg, or other wire copy reposted by local outlets.
- Three news stories all citing the same company press release.
- Aggregator pages, snippets, or AI-generated summaries that point back to the same original.
- Blog posts that quote the same article without new reporting.
- Identical wording published within minutes across unrelated domains.
- Articles that explicitly say `according to a press release`, `the company announced`, or `Reuters reported` without additional reporting.

## How to check independence

### 1. Compare root domains

Different root domains are a first-pass signal. Use:

```bash
python scripts/verify.py assess --urls "https://site-a.example/a,https://site-b.example/b"
```

Root-domain comparison catches obvious duplicates but cannot detect common source origin by itself.

### 2. Compare bylines and wire labels

Look for:

- `Associated Press`, `AP`, `Reuters`, `AFP`, `Bloomberg`, `PR Newswire`, `Business Wire`.
- Same author name across domains.
- Same organization name in the article footer or metadata.

If multiple domains carry the same wire story, count them as one source origin.

### 3. Compare publication date clustering

Many identical stories published in a tight window often come from a press release or wire feed. Clustered timing is not proof, but it is a warning sign.

### 4. Compare wording

Copy a distinctive sentence from the passage and search it. Identical wording across sites usually means syndication or reposting.

### 5. Trace citations backward

If a source says `according to X`, inspect X. The upstream document may be the real source origin. Count downstream summaries only as context unless they add original verification.

## Common patterns

### AP / Reuters syndication

A local newspaper may publish a story on its own domain while the byline or footer says `Associated Press` or `Reuters`. Treat all copies of that same wire article as one source origin.

### Press release reposts

Company announcements often appear on the company site, PR Newswire, Business Wire, Yahoo Finance, and local news sites. Unless another outlet independently checks the claim, count the release as one source origin.

### Aggregator sites

Search portals, stock quote pages, and content aggregators often mirror snippets. They are useful for discovery but weak as verification evidence.

### Official data reused by news

When news articles report a statistic from an official dataset, the dataset is the primary source. The article may help interpret the data, but it is not independent confirmation of the dataset unless it performs separate analysis.

## Reporting independence

In the verification report, include a note such as:

- `Source independence: 3 URLs from 3 root domains; two appear to cite the same official release, so evidence is counted as 2 source origins.`
- `Source independence: 4 URLs, but 3 are Reuters syndication. Counted as 2 source origins: Reuters and the official filing.`
- `Source independence: only one authoritative source found; verdict capped at Likely true.`
