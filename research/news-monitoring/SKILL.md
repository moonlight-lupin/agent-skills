---
name: news-monitoring
description: "Recurring topic/news monitoring with web search, multi-language sources, digest formatting, and automated delivery via Hermes cron jobs. Covers search strategy, source selection, Chinese-language platforms, and digest templates."
version: 2.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [news, monitoring, digest, cron, research, chinese, HK, PBSA]
    related_skills: [deep-research, youtube-topic-research, website-scraping]
---

# News Monitoring & Digest Delivery

Set up recurring topic/news monitoring that searches the web for recent articles, compiles a headline digest, and delivers it to a messaging channel or document pipeline.

## Workflow

### Step 1 — Define Topic

Work with the user to define:
- **Subject**: what to monitor (e.g. PBSA in Hong Kong, AI regulation, self-hosting tools)
- **Geography**: which region(s) matter (e.g. Hong Kong, Singapore, global)
- **Angles**: which aspects to track — investment/deals, policy/regulation, supply/pipeline, occupancy/rental, general commentary
- **Velocity**: how fast-moving the field is — determines acceptable article age (see Step 5)

### Step 2 — Create Search Keywords

Build search queries from the topic definition:
- **Multi-angle**: one query per angle (investment, policy, supply, etc.)
- **Multi-language**: English keywords + native language keywords for each geography
- **Time-bounded**: specify recency in the query where possible (e.g. "2026", "latest")
- Keep queries concise — 3-7 terms works best. Overly long queries return thin results.

### Step 3 — Select Sources

Identify which sources matter for the topic and geography:
- **English-language**: international outlets, local English press, industry publications
- **Native-language**: local press in the geography's primary language(s) — these often break news first
- **Industry-specific**: trade publications, research houses, REIT/sector-specific sites
- **Closed-ecosystem platforms** (小红书, 抖音, 微信公众号): content is NOT web-indexed. Be upfront about this limitation — options are manual monitoring or third-party analytics tools.

Record the source list in the topic's reference file (see Reference Files section).

### Step 4 — Run Searches

**Date grounding (mandatory).** Before running any search, ground the model in the real current date. LLMs default to training-cutoff years in queries — this produces stale results. Inject:

> Today's date is {current date as "DD Month YYYY"}. When a search query needs a year or refers to "latest"/"current"/"this year", use {current year} or relative wording — never a year inferred from training data.

**Primary method: use the harness `web_search` tool.**

```
web_search(query="Hong Kong PBSA student accommodation investment 2026", limit=10)
```

The tool uses whatever backend is configured in `config.yaml` (e.g. SearXNG → DDGS fallback). The skill is backend-agnostic — it does not prescribe which search engine to use. Run one `web_search` call per query from Step 2.

**Advanced option: SearXNG direct curl for news-specific filters.**

When you need news-category filtering, language selection, or time bounding that `web_search` doesn't expose:

```bash
# English news, last month
curl -sL "${SEARXNG_URL}/search?q=ENCODED_QUERY&format=json&categories=news&language=en&time_range=month"

# Chinese news, last month
curl -sL "${SEARXNG_URL}/search?q=ENCODED_ZH_QUERY&format=json&categories=news&language=zh-Hant&time_range=month"
```

Key SearXNG parameters:
- `format=json` — mandatory (omitting returns 403)
- `categories=news` — news-only results
- `language=zh-Hant` / `language=en`
- `time_range=day|week|month|year`
- Results include direct source URLs (no proxy resolution needed)

**RSS feeds** for curated must-track sources that search engines may not surface quickly:

```bash
curl -sL "https://example.com/feed/"
```

Parse `<item>` blocks for `<title>`, `<pubDate>`, `<link>`, `<description>`.

### Step 5 — Process Results

Go through all search results and:

1. **Quality filter** — before any ranking, discard low-quality results:
   - **Thin content**: page is a landing page, aggregator stub, or has no substantive text (<100 words of actual article content)
   - **Irrelevant**: result doesn't match any defined topic angle despite keyword overlap (e.g. "port" matching "transport" when the topic is about a seaport)
   - **Duplicate URLs**: same article appearing in multiple search results (keep the first occurrence)
   - **Non-article**: video-only pages, image boards, login walls with no preview
   - Use word-boundary matching for topic terms to avoid false-relevance from substring matches (e.g. "us" matching "business")
2. **Deduplicate** — same article appearing across multiple queries or engines appears once (match by title similarity, not just exact URL)
3. **Sort** by the user's priority order:
   - **Recency**: most recent first (default)
   - **Relevance**: how directly it matches the topic angles
   - **Source priority**: Tier 1 sources rank higher (see topic reference files)
4. **Rank** — assign each article a priority/impact score based on recency × relevance × source tier
5. **Flag stale content** — highlight to the user when results are dated relative to the field's velocity:
   - **Fast-moving fields** (AI, crypto, tech regulation): articles >2-3 months old may be stale — flag them or exclude
   - **Slow-moving fields** (real estate, infrastructure, policy): articles up to 6 months old may still be relevant
   - Use the velocity defined in Step 1 to calibrate
6. **Filter** — remove articles outside the topic scope, outside the geography, or behind the recency threshold

### Step 6 — Compare With Previous Digests

If this is a recurring digest (cron job), check for overlap:
- Use `context_from` on the cron job to inject the previous digest output as context (see Cron Setup section)
- Compare new results against the previous digest — match by **title similarity**, not exact string match
- Remove articles that already appeared in the previous run
- For niche/low-activity topics where overlap is high, consider broadening scope or reducing frequency

### Step 7 — Compile Digest

Format the ranked, deduplicated results into a readable digest:

```
📰 [TOPIC] — Headline Digest
🗓 [Today's date as DD Mon YYYY]

1. [Date] — Source
   **Headline**
   1-2 line summary. Key stat or implication.
   🔗 Direct source URL

2. [Date] — Source
   ...

---
🔑 Key themes:
- Theme 1: brief summary
- Theme 2: brief summary
```

**Formatting rules:**
- Always include the **publish date** on every item
- Headline + 1-2 line summary (not a paragraph analysis)
- Sort by priority/impact (highest first)
- Source links as 🔗 + **direct URL** to the publisher's site — never Google News proxy URLs or Bing apiclick URLs
- Use 🆕 for articles from the last 7 days
- Max items: 5 by default (configurable per topic). Reduce frequency rather than padding with stale content.
- Key themes summary at the bottom — one-line takeaways of dominant trends

**URL rules:**
- Every link MUST resolve directly to the article on the publisher's website
- Google News RSS links (`news.google.com/rss/articles/CBMi...`) are protobuf-encoded proxy URLs — unresolvable by any method. If using Google News RSS for discovery only, resolve the actual source URL via SearXNG title-search or `web_search` before including.
- Bing News RSS links are `apiclick.aspx` redirects — extract the real URL from the `url=` parameter.
- If resolution fails: include the article with `⚠️ Direct link unavailable — search [SOURCE] for: [title]`

### Step 8 — Delivery

Deliver the digest to the user via one of:

- **Chat channel** (Telegram, WhatsApp) — most common. Use `deliver` parameter on cron jobs (e.g. `deliver=telegram`, `deliver=whatsapp:<HANDLE>`). WhatsApp requires an explicit target — bare `deliver=whatsapp` fails.
- **Document generation** — pass the compiled digest to a document generation skill to produce a formatted PDF, slide deck, or article. The skill should output the digest content in a structured format (markdown) that the downstream skill can consume.

For one-off digests: deliver directly in the current chat.
For recurring digests: set up a cron job (see below).

### Step 9 — Cron Setup (Reference)

For recurring digests, create a scheduled job using the `cronjob` tool. This is optional — one-off digests don't need it.

**Key parameters:**
- `schedule`: cron expression (e.g. `0 9 1,15 * *` for biweekly at 9am, `0 3 */3 * *` for every 3 days)
- `prompt`: self-contained instructions including topic, search queries, source lists, digest format, output language, and output discipline
- `deliver`: target channel (`telegram`, `whatsapp:<HANDLE>`, etc.)
- `context_from`: list of job IDs whose previous output should be injected as context (for dedup — typically the job's own ID for self-referencing)
- `enabled_toolsets`: restrict to `["web", "terminal"]` to reduce token overhead

**Cron prompt template:**
```
You are a [TOPIC] news scout. Find recent articles (within the last [N] months ONLY) and compile a concise digest.

## Date grounding
Today's date is {current date}. When a search query needs a year or refers to "latest"/"current"/"this year", use {current year} or relative wording — never a year inferred from training data.

## Search
Run [N] searches using the web_search tool — one per angle, in both English and [native language]:

1. web_search("[English query 1]", limit=10)
2. web_search("[English query 2]", limit=10)
3. web_search("[Native language query 1]", limit=10)
...

If results need news-specific filtering (categories, language, time_range), use SearXNG directly:
curl -sL "${SEARXNG_URL}/search?q=ENCODED_QUERY&format=json&categories=news&language=[lang]&time_range=month"

If SearXNG is unreachable, the web_search tool will fall back automatically.

## Processing
1. Quality filter — discard thin content (landing pages, stubs, <100 words), irrelevant results (word-boundary match topic terms, not substring), duplicate URLs, and non-article pages
2. Deduplicate across queries (match by title similarity)
3. Filter: only articles from the last [N] months, directly related to [TOPIC]
4. Compare against previous digest (provided as context) — remove articles already covered
5. Sort by recency, then by relevance
6. Pick TOP [5] articles

## Output
📰 [TOPIC] — Headline Digest
🗓 [today's date]

1. **{Headline}**
   📅 {DD Mon YYYY} · {Source}
   {1-2 line summary}
   🔗 {DIRECT article URL}

...up to [5] items

---
🔑 Key themes: {one-line takeaway}

## Rules
- Every 🔗 link MUST be a direct URL to the publisher's site
- Always include publish date
- Use 🆕 for articles from last 7 days
- Do NOT fabricate articles
- OUTPUT DISCIPLINE: Output EXACTLY ONE copy of the digest. The VERY FIRST LINE must be '📰'. The VERY LAST LINE must be the last theme bullet. No thinking, reasoning, planning, or meta-commentary.
**IMPORTANT: Write ALL output in [LANGUAGE].** Preserve original [native language] headlines as-is when the source article is in [native language].
```

**Dedup via context_from:**
Set `context_from: ["<job_id>"]` on the cron job (using the job's own ID) so each run receives the previous digest. Add to the prompt: *"Review the previous digest output (provided as context). Do NOT include any article that already appeared — match by title similarity, not exact string match."*

**Frequency tuning:**
- High-volume topics: daily or every 2-3 days
- Medium topics: weekly
- Niche/low-activity topics: biweekly (1st and 15th) — allows more content to accumulate, reduces overlap

## Source Selection Reference

### Hong Kong Sources

**English:** SCMP, The Standard HK, Hong Kong Business, Mingtiandi, Colliers/JLL/CBRE/Savills research, ResearchAndMarkets

**Chinese (Traditional):** HK01, 香港經濟日報 HKET, 明報 Ming Pao, 文匯報 Wen Wei Po, 東方日報 on.cc, Now財經, 信報 HKEJ, 香港商報

**Industry-specific:** PBSA News, Global Student Living, Centurion announcements (SGX-listed PBSA REIT)

## Pitfalls

- **No dates in digest = rejected.** User explicitly asked for publish dates on every item.
- **Stale articles = rejected.** Filter strictly by the field's velocity — flag or exclude articles past their relevance window.
- **Over-summarizing.** User wants headline + 1-2 lines, not a paragraph analysis.
- **Too many items.** User wants max 5 items by default. Reduce frequency rather than padding with stale content.
- **Missing native-language sources.** Local-language outlets often break news first. Always search in both English and the geography's native language(s).
- **Don't promise closed-ecosystem platforms.** 小红书, 抖音, 微信公众号 are app-locked. Be upfront.
- **Google News RSS links are unresolvable.** Never include `news.google.com/rss/articles/CBMi...` URLs. Resolve to the publisher's direct URL first.
- **Output duplication — digest rendered twice.** Some models write the full digest during "thinking" then write it again. Fix: add "OUTPUT DISCIPLINE: Output EXACTLY ONE copy." and specify first/last line anchors.
- **Output language drift.** The skill contains native-language search queries (input). Multilingual models may interpret this as a signal to produce output in that language. Always specify output language explicitly — anchor at both top and bottom of the prompt.
- **"Must-include" RSS sources crowded out by discovery results.** Use quotas (e.g. 5 discovery + 5 RSS) or guarantee minimum slots per must-include source.
- **WhatsApp cron delivery requires explicit target.** `deliver=whatsapp` fails. Use `deliver=whatsapp:<HANDLE>` or an explicit chat ID.
- **delegate_task with web toolset is unreliable for search-heavy tasks.** Run searches directly and parse output yourself.
- **SearXNG address changed.** If the NAS IP changes, update `SEARXNG_URL` in `~/.hermes/.env` and the curl commands in topic reference files.
- **DDGS installed in Hermes venv.** No `PYTHONPATH` hacks needed — `ddgs` CLI and `from ddgs import DDGS` work directly. Do not use stale paths like `/root/.hermes/ddgs_lib` or `/opt/hermes/.venv/bin/python`.

## Reference Files

- `references/web-search-fallback.md` — How the Hermes web search backend dispatch works, current config (SearXNG → DDGS fallback), runtime fallback patch details, and env var verification tips. Load when debugging search issues.
- `references/pbsa-hk-search-config.md` — PBSA Hong Kong specific: search queries, source tiers, key themes, delivery config. Load when running the PBSA HK monitoring scan.
- `references/selfhosting-digest-config.md` — Self-hosting & homelab digest: search queries, RSS must-track sources, delivery config. Load when running the Self-Hosting weekly digest.

## Evals

`evals/routing-fixtures.json` holds lightweight contract fixtures — sample
request → expected routing (including when a request should go to
`deep-research` or `youtube-topic-research` instead), required digest output
fields, and forbidden output patterns. They are specs, not run against a live
model; the repo-root `tests/test_routing_fixtures.py` validates they stay well-formed and
route to real skills.