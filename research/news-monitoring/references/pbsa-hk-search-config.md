# PBSA Hong Kong — Search Configuration & Source Map

## Topic Definition

**PBSA (Purpose Built Student Accommodation)** in **Hong Kong** with broader context. Covers:
- Investment/deals (land sales, acquisitions, JVs, REIT activity)
- Policy/regulation (student visa caps, subsidy schemes, zoning, land tenders)
- Supply/pipeline (new developments, completions, hotel/industrial conversions)
- Occupancy/rental rates (market performance, yields, rental trends)
- **Adjacent topics**: student enrollment trends, housing policy changes, APAC PBSA cross-border deals, HK property/REIT market updates where relevant to student accommodation

## Search Methods (Order of Preference)

### 1. SearXNG — Primary Method (Free, Direct URLs, Multi-Engine)

Set `SEARXNG_URL` to your self-hosted SearXNG instance (e.g. in `~/.hermes/.env`). Aggregates Google, Bing, DDG, Yahoo. Returns direct article URLs. No rate limits.

```bash
# Chinese news
curl -sL "$SEARXNG_URL/search?q=%E9%A6%99%E6%B8%AF+%E5%AD%B8%E7%94%9F%E5%AE%BF%E8%88%8D+%E6%8A%95%E8%B3%87&format=json&categories=news&language=zh-Hant&time_range=month"

# English news
curl -sL "$SEARXNG_URL/search?q=Hong+Kong+PBSA+student+accommodation+investment&format=json&categories=news&language=en&time_range=month"
```

- Chinese: `language=zh-Hant`
- English: `language=en`
- Time filter: `time_range=day|week|month|year`
- Each result: `title`, `url` (DIRECT link), `content`, `engines`, `publishedDate`
- **Always include `format=json`** or you get 403

### 2. DDGS — Fallback Method (Free, Direct URLs)

`ddgs` is installed in the Hermes venv (v9.14.4). No `PYTHONPATH` hacks needed. Returns direct article URLs.

```bash
ddgs news -q "QUERY" -m 15 -o json
```

Or via Python:
```python
from ddgs import DDGS
import json
with DDGS() as d:
    results = list(d.news('QUERY', region='hk-en', max_results=15))
    print(json.dumps(results, ensure_ascii=False))
```

- English: `region='hk-en'`
- Chinese: `region='hk-zh'`
- Each result: `title`, `url` (DIRECT link), `body`, `source`, `date`

### 3. BrowserAct Google News API — Paid Alternative

**Requires a separate Google News API skill** (not part of this repo — e.g. installed at `~/.hermes/skills/google-news-api-skill/`). Requires `BROWSERACT_API_KEY` env var. Paid service (~25-50 credits/run). Skip this method if you don't have such a skill installed.

```bash
export BROWSERACT_API_KEY="key-here"
python -u ~/.hermes/skills/google-news-api-skill/scripts/google_news_api.py "香港 學生宿舍" "past week" 10
```

Use this if DDGS is rate-limited or returning empty results. The script polls for results (10s intervals), so allow 1-3 minutes per run. Script returns: `headline`, `source`, `news_link` (direct URL), `published_time`, `author`.

### 4. Fallback: Bing News RSS (Free, Direct URLs)

```bash
curl -sL "https://www.bing.com/news/search?q=ENCODED_QUERY&format=rss" -H "User-Agent: Mozilla/5.0" --max-time 15
```

Extract direct URLs from `url=` parameter in apiclick links.

### 5. Fallback: Google News RSS (Free, Chinese Sources, Proxy URLs Need Resolution)

```bash
curl -sL "https://news.google.com/rss/search?q=ENCODED_QUERY&hl=zh&gl=HK&ceid=HK:zh-Hant" -H "User-Agent: Mozilla/5.0" --max-time 15
```

Links are Google proxy URLs. Resolve via Bing title-search if needed.

## Search Queries

### English Queries (Bing/DDGS)
```
"PBSA" "Hong Kong" student accommodation
Hong Kong student housing PBSA investment
Hong Kong student hostel subsidy policy
Hong Kong PBSA rental yield occupancy
Hong Kong student accommodation hotel conversion
Centurion Hong Kong student housing
```

### Chinese (Traditional) Queries (Google News/DDGS)
```
香港 學生宿舍 投資
香港 學生公寓 租金 回報
香港 學生住宿 供不應求
香港 專上學生宿舍 資助
香港 學生宿舍 地皮 招標
香港 學生公寓 改裝 酒店
```

### RSS Parameters
- Bing: `&format=rss` appended to search URL
- Google EN: `hl=en&gl=HK&ceid=HK:en`
- Google ZH: `hl=zh&gl=HK&ceid=HK:zh-Hant`
- BrowserAct: `Publish_date` param = "past week", "past 24 hours", etc.

## Key Sources (Ranked by Relevance)

### Tier 1 — Most Reliable for HK PBSA
- SearXNG (self-hosted, `$SEARXNG_URL`) — primary free method, multi-engine aggregation, direct URLs, good EN+ZH coverage
- DDGS — fallback free method, direct URLs, good EN+ZH coverage
- BrowserAct — paid, reliable, direct URLs, uses Google News directly
- HK01 (hk01.com) — breaks news fast, wide HK coverage
- 香港經濟日報 HKET (hket.com) — financial/property focus
- SCMP — paywalled, but titles surface in News
- The Standard HK — free, good policy coverage
- Mingtiandi — APAC property investment focus
- Now財經 — financial news, property analysis

### Tier 2 — Industry/Research
- Colliers — regular HK property research with PBSA sections
- JLL — student housing market reports
- CBRE — APAC capital flows reports
- Savills — student accommodation research
- PBSA News (pbsanews.com) — global PBSA industry site
- Global Student Living — student housing research/analysis

### Tier 3 — Chinese-Language Outlets
- 明報 Ming Pao (mingpao.com) — good policy/education coverage
- 文匯報 Wen Wei Po (wenweipo.com) — pro-govt angle, policy announcements
- 東方日報 on.cc — property market news
- 信報 HKEJ (hkej.com) — financial analysis
- 香港商報 (hkcd.com.hk) — business/property focus
- 香港電台 RTHK — government policy announcements
- 星島頭條 — general HK news

### Unreachable Platforms (App-Only)
- 小红书 (Xiaohongshu) — not web-indexed, requires Newrank.cn or manual checking
- 抖音 (TikTok/Douyin) — not web-indexed
- 微信公众号 — partially indexed via `site:mp.weixin.qq.com`, coverage is spotty

## Key Themes to Watch (Current as of May 2026)

1. **Govt land policy**: First student-hostel-specific land tenders (3 sites, 4,500 beds); no commercial land in FY2026 budget
2. **Conversion wave**: Hotels & commercial → PBSA; 16 deals in 10 months totalling HK$6.1B (as of Nov 2025)
3. **Rental yields**: ~6% for PBSA conversions vs lower for regular residential
4. **Policy shift**: Non-local student cap raised to 50% at UGC-funded universities
5. **Institutional entry**: CMH REIT HK$206M Kowloon acquisition; Centurion REIT IPO on SGX
6. **Supply gap**: Projected 120,000 bed shortfall by 2028

## Delivery Configuration

- **Delivery channel**: WhatsApp (`whatsapp:<HANDLE>` — must use an explicit target; bare `whatsapp` fails)
- **Frequency**: Biweekly — 1st and 15th of each month at 9:00 AM HKT (`0 9 1,15 * *`). PBSA is a niche; biweekly allows more fresh content to accumulate and reduces overlap with previous digests.
- **Dedup**: Enabled via `context_from` (the job's own ID). Each run receives the previous digest as context and must skip articles already covered.
- **Format**: Top 5 items max, headline + date + 1-2 line summary + **direct source link**, max 3 months old
- **Cron job ID**: `<CRON_JOB_ID>` (assigned when the job is created)
- **Critical**: Every 🔗 link MUST be a direct URL to the article on the publisher's website. Never output Google News proxy URLs or Bing apiclick URLs.