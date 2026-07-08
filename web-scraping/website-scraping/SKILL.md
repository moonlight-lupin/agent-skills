---
name: website-scraping
description: Generic playbook for extracting structured data from any website — hotel prices, flight fares, e-commerce listings, real estate, jobs, competitor product catalogues, anything where the goal is to turn one or more URLs into clean records on disk. Use this skill whenever the user mentions scraping, harvesting, extracting, or pulling data from a website; names a specific site or competitor they want data from; asks how to handle JavaScript-rendered pages, Cloudflare blocks, bot detection, Turnstile challenges, or Playwright; wants to monitor prices over time; needs to automate a copy-paste research task; or says things like "just get the data from X" or "I need a script that grabs N from site Y". Covers recon, picking the lightest extraction tool that works, surviving anti-bot defences, and writing clean JSONL output with a run manifest. Scope is scraping only — landing data in a database, scheduling, and downstream pipeline work are explicitly out of scope and live in other tools.
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
---

# Website scraping

A workflow for turning websites into structured data. Bias toward the **lightest tool that works**: static HTML → JSON-in-page → reverse-engineered API → browser automation, in that order. Skipping recon and reaching straight for Playwright is the single most common way to waste hours.

## When to use

This skill applies to any task shaped like "given a URL or a list of URLs, produce structured records". Examples:

- Competitor price monitoring (hotels, flights, retail, rentals, student housing, SaaS)
- E-commerce product catalogue extraction
- Real-estate or job-listing harvesting
- Reviews, ratings, availability calendars
- One-off "pull this table into a spreadsheet" jobs

Out of scope: database persistence, scheduling, dashboards, downstream normalisation against a fixed schema. This skill produces JSONL — what the caller does with it is their problem.

## Workflow

Follow these steps in order. Most failures come from skipping step 1.

### 1. Frame the goal before touching code

Pin down the answers in writing before opening an editor:

- **What records do you want?** One row per *what*? Per product? Per (product × variant × date)? Per (hotel × room-type × check-in)? Be explicit — many sites force you to choose between "one row per listing card" and "one row per price-variant", and the choice cascades through the whole scraper.
- **What fields per record?** Required vs nice-to-have. Mark anything the source might not publish on every record (sometimes-missing fields are normal, not a bug).
- **Input shape**: a single URL? A list of URLs? A search query you need to execute first? A seed listing page you crawl from?
- **Output shape**: this skill recommends **JSONL** (one JSON object per line, caller-defined keys) plus a sidecar manifest file. See "Output convention" below.
- **Scale & cadence**: how many records, how often? This one answer drives every downstream cost decision. A one-off harvest of 100 pages and a daily refresh of 10,000 SKUs are different projects: the first just needs a polite `time.sleep`; the second has to justify proxy/managed-service economics (see step 4, Tier 5+). Pin down volume *and* repeat-frequency now, not after you've built a single-shot scraper that can't keep up.
- **What's "ground truth"?** Pick one specific item you'll eyeball in the browser end-to-end to verify the scraper matches.

If the user hasn't been explicit about any of these, ask. A 30-second clarification saves an hour of wrong-shape extraction.

### 2. Recon the site — pick the lightest tool

Before writing the decision tree below, run two cheap sanity checks. Either can make the whole scraper unnecessary.

**2.0a — Is the data already one tool-call away?** You may be running inside an agent runtime that already exposes a fetch/scrape/SERP capability — Hermes's `web_search` + `web_extract` tools, a built-in search, or a scraping MCP server (Bright Data, Firecrawl, etc.). For a *one-off, low-volume* job, calling a tool that already exists is the lightest path of all — lighter than writing any code. Check what's available before you open an editor. (For repeatable, version-controlled, or high-volume work, still write a script — you want something you can re-run, diff, and hand off.)

**2.0b — Is this a hostile mega-platform?** A handful of sites — Amazon, LinkedIn, Instagram, TikTok, Facebook, YouTube, Zillow, Google Maps, Crunchbase, and similar — invest heavily in defeating DIY scraping and change their internals constantly. For these, hand-rolling a scraper is often poor ROI: it works for a week, then breaks. The lightest tool here may not be `urllib` at all — it's a commercial structured-data product (Bright Data's dataset/Web-Scraper APIs, Apify actors, etc.) that already maintains the extraction for that platform. **Surface this trade-off to the user** ("I can hand-roll this, but for $SITE a maintained data API will be more reliable and probably cheaper than the upkeep — your call") rather than silently grinding on a fragile custom scraper. If they want DIY anyway, proceed — but go in expecting the anti-bot ladder in step 4.

If neither shortcut applies, recon normally. Open the target URL in a real browser with DevTools open. Walk this decision tree top to bottom; **stop at the first match**. The earlier you stop, the simpler and more robust the scraper.

```
Is the data you need visible in "View Source" (right-click → View Page Source)?
├─ YES → Static HTML. Use urllib / requests + an HTML parser. Done.
│
└─ NO → Is there a <script type="application/ld+json"> block with what you need?
    │
    ├─ YES → JSON-LD. Universal schema (schema.org), present on most modern
    │        sites for SEO. Often has product, price, address, rating, etc.
    │        Parse the JSON block directly. No JS execution needed.
    │
    └─ NO → Is there a JSON blob in a <script id="__NEXT_DATA__">, __NUXT__,
            drupal-settings-json, window.__INITIAL_STATE__, or similar?
        │
        ├─ YES → Framework JSON-in-page. Pull the blob, json.loads it, navigate
        │        to the fields you want. Still no browser needed.
        │
        └─ NO → Open DevTools Network tab. Reload. Filter to XHR/Fetch.
                Does a clear JSON endpoint return the data?
            │
            ├─ YES → Reverse the API. Copy as cURL, port to Python.
            │        Often the cleanest path — same data the site uses, no scraping
            │        of HTML at all. Watch for auth tokens / CSRF / rate limits.
            │
            └─ NO → It's client-rendered. Browser automation required.
                    Use Playwright. See references/playwright.md.
```

**Hard rule**: only use Playwright when one of the earlier paths genuinely doesn't work. Playwright is 10-50× slower, 10× more memory-hungry, and 10× more fragile than urllib. Sites change their HTML structure every few months but tend not to change their JSON-LD or their backing API as often.

For an automated recon helper that hits the URL and reports which paths look viable, see `scripts/recon.py`. Run it as the first thing you do on any new site.

### 3. Build the smallest possible extractor

Start with **one item**, not the whole catalogue. Get the field extraction correct against a single known target, then generalise to the list. Two reasons:

1. Field-extraction bugs are easier to spot on one item than buried in 200.
2. You'll iterate the parser 5-10 times before it's right — doing that against the whole site burns rate-limit budget and trains the site's WAF on your fingerprint.

Code shape for the inner loop:

```python
def extract_one(html_or_json) -> dict | None:
    # one item -> one dict; None if this item is unparseable.
    ...

def extract_many(items_iter) -> list[dict]:
    out, seen = [], set()
    for item in items_iter:
        try:
            rec = extract_one(item)
        except Exception as e:
            log.warning("extract failed for %s: %s", _label(item), e)
            continue
        if rec is None:
            continue
        key = rec.get("id") or rec.get("url") or _hash(rec)
        if key in seen:
            continue
        seen.add(key)
        out.append(rec)
    return out
```

Three things this shape enforces and explanations of why each matters:

- **`try/except` per item, not over the whole batch.** One malformed listing should not lose you the other 199. Log the failure with enough context to find the item later (the URL or a stable id), then move on. Silently swallowing exceptions is worse — the failure rate becomes invisible.
- **Dedup by stable canonical id, not by record-equality.** If the site exposes a numeric id, a SKU, a URL slug — use that. Don't dedup by `hash(record_dict)`, because real-world records have minor variations (a whitespace change, a price tick) that you'd miss as duplicates.
- **`None` means "this item is intentionally skipped"**, exception means "I tried and failed". Different signals, log them differently.

**Concurrency.** The loop above is sequential, which is the right default — it's the politest to the site and the easiest to debug. Reach for parallelism only when sequential is genuinely too slow, and bound it:

- **Up to ~20 URLs**: stay sequential with a small `time.sleep` between requests. Not worth the complexity.
- **~20–200 URLs**: bounded concurrency — an `asyncio.Semaphore(N)` (or a thread pool of N) with N small (4–8). Never fire all requests at once; an unbounded `asyncio.gather` over 200 URLs is a self-inflicted DoS that gets your IP blocked.
- **Hundreds+**: you're now firmly in anti-bot territory (step 4). The semaphore size is capped by whatever the site tolerates, not by your CPU — start low and raise it only while the success rate holds.

The concurrency ceiling is set by the site's rate-limiting (step 4, Tier 4), not by your hardware. When in doubt, slower and complete beats faster and blocked.

### 4. Handle anti-bot defences with proportional response

Modern sites push back on scraping in escalating ways. Match your defence to what you actually see, not what you fear.

| What you observe | Likely cause | Fix |
|---|---|---|
| 403 / 429 from `urllib.request` with default UA | Bot UA filter | Set a real browser UA in the request header. Often enough on its own. |
| Empty body, but browser shows full content | Client-side render | Need a browser. Playwright with default settings. |
| HTML body title says "Just a moment..." or "Performing security verification" | Cloudflare challenge | Add `playwright-stealth`. If still failing, open a **fresh `browser.new_context()` per page** — Cloudflare flags repeat visits within the same context. See references/anti-bot.md. |
| Works once, fails on the 5th request | Per-IP rate limit | Insert `time.sleep(1-3)` between requests. If still failing, the site needs proxy rotation — push back on the user about whether the scrape volume is reasonable. |
| Captcha (visible) on every visit, even from a real browser | Aggressive WAF | Stealth + fresh context. If that still fails, you're at the boundary of "scrape this site at all". Options: a **managed unblocker API** (see below), residential-IP proxies, `undetected-playwright`, manual captcha solve in a headed browser, or accept a degraded scope (e.g. capture only what's on the unauthed landing page). Document the limit and move on. |
| Login required | Auth-gated content | Out of scope for this skill. Auth requires per-site work that needs to be agreed with the user separately (credentials, ToS, 2FA). Surface as a blocker. |

**Don't reach for residential proxies on day 1.** They cost real money and signal that you're operating at a scale or aggression level the site is actively trying to prevent. Make sure the use case justifies it.

**The managed-unblocker off-ramp.** Between "configure your own residential proxies" and "give up" sits a whole managed tier worth knowing about: services like Bright Data's Web Unlocker, Zyte API, ScraperAPI, and similar take a URL and hand back clean HTML — proxy rotation, TLS fingerprinting, and CAPTCHA solving all handled server-side. When DIY stalls on a site that's worth the spend, the right move is usually to **swap only the fetcher** and leave everything else alone: your `extract_one`, dedup, JSONL writer, and manifest stay byte-for-byte identical, you just change *how the HTML arrives*. Record the swap in the manifest (`"tool": "managed-unblocker"` or the specific vendor) so consumers know the provenance. This keeps the skill vendor-neutral — the managed service is an implementation detail behind the same fetch boundary, not a rewrite. See `references/anti-bot.md` for where it sits on the escalation ladder.

Reference: `references/anti-bot.md` has the full escalation ladder and the specific patterns for surviving Cloudflare/Turnstile.

### 5. Capture the raw payload, not just the parsed output

For every item you scrape, save the raw HTML / JSON response alongside the parsed record. This is the single highest-value piece of robustness you can build in. Reasons:

- **Replay**: when your parser has a bug (and it will), you can re-parse from the saved raw payload without re-fetching. The site might be down, rate-limiting you, or have changed by the time you notice.
- **Forensics**: when the site changes and the parser breaks, the diff between the working raw payload and the broken one tells you what changed.
- **Cheap**: HTML compresses well. A 1MB page is ~100KB gzipped.

Convention: write raw payloads to `raw/<id_or_hash>.html` or `.json` next to your output JSONL. Reference the filename from the parsed record so you can find it later.

### 6. Verify against ground truth

Before declaring done:

0. **Block-page gate (do this at fetch time, not just at the end).** A `200 OK` does not mean you got real content. Before parsing, assert the payload is non-empty *and* free of block-page signatures — `"Just a moment"`, `"Performing security verification"`, `"Access denied"`, `"unusual traffic"`, a Cloudflare/Turnstile iframe, or a body that's suspiciously short for the page. A scraper that silently writes 200 challenge-page records looks successful (`status: "ok"`, 200 rows) but contains zero usable data. Fail loud — count these as errors in the manifest, don't let them masquerade as records. This is the single most common silent-corruption failure.

1. **Smoke test**: run the scraper against the single known-good item from step 1. Eyeball every field of the resulting record against what the browser shows.
2. **Sample of N**: pull 5-10 records at random from a full run and verify each in the browser. Look for: column-shift bugs (every field off by one), unit confusions (£ vs $, weekly vs monthly), date-format errors (MM/DD vs DD/MM), and silently-empty fields.
3. **Count check**: if the site reports a total ("234 properties in this city"), check your output has roughly that many records (allowing for things the site lists but you filtered out).
4. **Re-run determinism**: scrape the same URL twice within a few minutes. If the records or field values differ randomly, you've got a race condition in browser-driven extraction — see the double-render gotcha in `references/extraction.md`.

### 7. Write output in JSONL + manifest

The skill recommends this output convention because it's the simplest format that survives schema evolution:

```
output/
├── records.jsonl          # one JSON object per line, caller-defined keys
├── manifest.json          # run metadata: timestamp, source URLs, status, counts
└── raw/                   # raw payloads, named by stable id
    ├── abc123.html
    └── def456.json
```

**JSONL**: each line is `json.dumps(record) + "\n"`. No header. Add fields freely between runs without breaking older consumers. Stream-readable.

**Manifest** structure (write this even on partial-failure runs):

```json
{
  "scrape_started_at": "2026-05-24T10:34:00Z",
  "scrape_finished_at": "2026-05-24T10:36:12Z",
  "source_urls": ["https://example.com/listings"],
  "status": "ok",                  // "ok" | "partial" | "failed"
  "records_written": 187,
  "items_attempted": 200,
  "items_skipped": 13,
  "errors": [
    {"url": "...", "reason": "..."}
  ],
  "user_agent": "Mozilla/5.0 ...",
  "tool": "urllib" | "playwright" | "playwright+stealth"
}
```

The manifest lets the caller (and you, three months later) know whether to trust the data. A run with `status: "partial"` and `items_skipped: 13` is a different consumption story to `status: "ok"`.

## References

Deeper material is in `references/` — load as needed, don't read upfront:

- **`references/recon.md`** — the recon decision tree in full, with concrete examples of how to spot each pattern in the wild (JSON-LD shapes, Next.js / Nuxt / Drupal blob locations, common framework signatures, hidden REST APIs). Also covers the two pre-recon shortcuts: reusing an existing runtime fetch/scrape tool, and recognising hostile mega-platforms where a maintained commercial data product beats DIY.
- **`references/playwright.md`** — browser automation patterns: when to use it, `domcontentloaded` vs `networkidle` (and why the latter is usually wrong), waiting on selectors, stealth, headless vs headed, injecting page-side JS scrapers for SPAs.
- **`references/anti-bot.md`** — escalation ladder for Cloudflare, Turnstile, rate limits, and IP-based blocking. Specific patterns (fresh context per request, stealth library setup, the managed-unblocker off-ramp and how to swap only the fetcher, when to give up).
- **`references/extraction.md`** — pulling JSON-LD, finding JSON-in-page blobs in Next.js/Nuxt/Drupal/etc., handling double-rendered DOMs, polling for value-change on click, robust dedup, parsing common field shapes (size ranges, price ranges, dates, postcodes/zip codes, addresses).
- **`references/agentic-browsing.md`** — the narrow case where the blocker is multi-step *navigation* rather than parsing (login flows, filter wizards, calendar pickers). Covers Microsoft's Webwright agentic browser framework: when it earns its keep, when it's overkill, install/CLI, and the "use it once to harden the script, then run that script deterministically" pattern. Not for bulk extraction — its own docs say so.

## Helper scripts

- **`scripts/recon.py`** — `python recon.py <url>` fetches the page with plain HTTP, then with Playwright if needed, and reports which extraction strategies look viable (static HTML hits, JSON-LD blocks, framework blobs, anti-bot signatures). Run this on every new site before writing anything.

## Anti-patterns to avoid

Things that look like good ideas but cost more than they save:

- **Starting with Playwright "just in case".** Recon first. If urllib works, every minute of Playwright debugging is wasted.
- **Aggressive global try/except.** Catches your own bugs and ships silent corruption. Per-item handling with logged failures is the right granularity.
- **Hard-coding values that vary by tenant.** Internal IDs in URLs (e.g. `academicYear=82`, `region_id=14`), CSRF tokens, signed query parameters — read them from the page rather than hard-coding. Sites rotate them and you'll wake up to "scraper returns 0 rows" with no obvious cause.
- **Relying on CSS class names that look generated** (e.g. `.css-1a2b3c4`). They're build-hash artifacts and change on every deploy. Prefer semantic selectors (`[data-product-id]`, `[itemprop=price]`, `<h1>`, structured data, ARIA roles).
- **`time.sleep(N)` as a substitute for waiting on a selector.** Fixed sleeps are the single biggest source of flake. Always wait on a specific DOM condition.
- **Discarding the raw payload.** Re-fetching to debug a parse bug is slow, rate-limit-burning, and often impossible (the site may have changed). Keep raw payloads cheap.
- **Caring about every field on every item.** Some sites legitimately have missing data on some items. Mark fields as optional in step 1 and don't crash on absence.

## A note on ethics and ToS

This skill helps with the *mechanics* of scraping, not the question of whether you should. Before running a scraper at any meaningful scale, the caller is responsible for:

- Checking the site's `robots.txt` and Terms of Service.
- Considering whether a public API is available that does the same job.
- Throttling traffic to a respectful level (a single user's worth of browsing, not a DDoS).
- Not scraping personal data without a lawful basis.
- Not scraping content behind a login they don't have explicit permission to access programmatically.

Flag any of these as a concern if the user's scope crosses a line. "We can do this, but check that ToS first" is a legitimate response.

## Evals

Two eval sets live under `evals/`:
- `evals.json` — runnable end-to-end scraping tasks against stable practice
  sites (static HTML and JS-rendered), with the expected extraction strategy.
- `routing-fixtures.json` — lightweight contract fixtures: sample request →
  expected routing (including when a request belongs to `entity-research` or
  `people-enrichment` instead), required output fields, and forbidden patterns.

The routing fixtures are specs, not run against a live model;
the repo-root `tests/test_routing_fixtures.py` validates they stay well-formed.
