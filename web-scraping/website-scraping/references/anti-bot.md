# Anti-bot — defences and how to handle them

Match your countermeasure to the actual challenge you observe. Most scrapers over-engineer this and either burn time on defences they don't need or pile fragile workarounds on top of each other.

## Detect what you're up against first

Open the URL in three ways and compare:

1. **Plain `curl` with a browser UA**: `curl -A "Mozilla/5.0 ..." <url>`
2. **Playwright headless, no stealth**
3. **Playwright headless, with stealth**

If (1) works, you're done — no defences needed. If (2) works but (1) doesn't, the site does a JS-execution check (very common). If (3) works but (2) doesn't, there's bot fingerprinting. If even (3) fails, you're in the harder tier — see escalation below.

## The escalation ladder

Apply countermeasures in order. Stop as soon as the page loads cleanly.

### Tier 0 — User agent

Default Python UAs (`Python-urllib/3.x`, `python-requests/2.x`) are an instant block on most sites. Always set a real browser UA:

```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}
```

Pick a current Chrome version — bumping the major version every 6 months keeps you in the "ordinary user" range. Don't rotate UAs randomly; that itself is a fingerprint.

### Tier 1 — Stealth

Default Playwright Chromium is detectable in three lines of JS:

```javascript
navigator.webdriver === true
navigator.plugins.length === 0
navigator.languages.length === 0
```

`playwright-stealth` patches these and ~20 other tells. Apply by default on any site that does any detection:

```python
from playwright_stealth import Stealth
Stealth().apply_stealth_sync(browser)
```

### Tier 2 — Fresh context per request

Cloudflare, Akamai, DataDome, and similar enterprise WAFs track per-context state via cookies, TLS session IDs, and behavioural fingerprints (mouse movement, timing patterns). The first visit may pass; subsequent visits in the same context get progressively more challenges.

**The fix**: open a new `browser.new_context()` per page, close it after. The browser stays warm (cheap), but the WAF sees a fresh session each time.

```python
def fetch(browser, url):
    ctx = browser.new_context(
        user_agent="...", locale="en-GB",
        viewport={"width": 1280, "height": 900},
    )
    try:
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        # Detect the Cloudflare interstitial title
        if "Just a moment" in (page.title() or ""):
            return None  # WAF still won; caller decides whether to retry
        page.wait_for_selector("[data-target]", timeout=20_000)
        return page.content()
    finally:
        ctx.close()
```

**Signature of a Cloudflare challenge that won**: title contains `"Just a moment..."` or `"Performing security verification"`, body is mostly empty, optional Turnstile iframe present.

This is a real and recurring pattern — we've hit it on RentCafe-backed sites, several US e-commerce platforms, and most "premium" content sites.

### Tier 3 — Headed browser

A small minority of sites detect headless Chromium specifically (the `--headless` flag leaves a subtle fingerprint that stealth doesn't fully erase on some Chrome versions). Try `headless=False`:

```python
browser = p.chromium.launch(headless=False)
```

This is slower and uses more memory, but for sites stuck at this tier it's often what gets the page to render. If you need it long-term, run a virtual display (Xvfb on Linux) so it doesn't pop up a window every run.

### Tier 4 — Slow down

If pages succeed in isolation but fail under any concurrency or after a few requests, the site is rate-limiting your IP. Options in order:

1. **Add per-request delay** — `time.sleep(1-3)` between requests. Use a small random jitter to avoid hitting clock boundaries.
2. **Reduce concurrency** — drop from 4 workers to 1.
3. **Backoff on 429/503** — retry with exponential backoff, max 3 attempts.

If even one request per 5 seconds gets blocked, the site is enforcing a per-IP daily quota and the next tier is the only fix.

### Tier 5 — Residential / mobile proxies

When per-IP limits are tight enough that legitimate scraping at any volume gets blocked, residential proxies (BrightData, Smartproxy, Oxylabs, etc.) rotate IPs through real consumer connections. They cost real money (typically $10-15 per GB) and are detectable to sophisticated targets, but they handle a wide range of sites.

**Before reaching for this**: confirm with the user that the use case justifies the cost. For a one-off harvest of 100 pages, it's overkill — just slow down. For monitoring a competitor's catalogue daily across 10,000 SKUs, it's the realistic option.

Setup with Playwright:

```python
browser = p.chromium.launch(
    headless=True,
    proxy={
        "server": "http://proxy.example.com:8080",
        "username": "...",
        "password": "...",
    },
)
```

### Tier 5.5 — Managed unblocker APIs

Tier 5 assumes *you* assemble the solution: buy proxies, wire them into Playwright, tune stealth, solve captchas. A managed unblocker collapses all of that into one HTTP call. Services like **Bright Data Web Unlocker, Zyte API, ScraperAPI, ScrapingBee, Oxylabs Web Unblocker** accept a target URL (plus optional country / render-JS / wait-for flags) and return clean HTML or JSON. Proxy rotation, TLS/JA3 fingerprinting, retry, and CAPTCHA solving are all handled server-side. You pay per successful request rather than per GB.

When this is the right tier:

- DIY (Tiers 0–5) works intermittently but the maintenance burden is real — the site changes its defences faster than you want to keep patching.
- The target is a hostile mega-platform (Amazon, LinkedIn, etc.) where the unblocker vendor already specialises in staying ahead of that specific WAF.
- The scrape is worth a per-request cost and you'd rather buy reliability than own the arms race.

**The key discipline: swap only the fetcher.** A managed unblocker sits exactly at your fetch boundary — it changes *how the HTML arrives*, nothing else. Keep `extract_one`, dedup, the JSONL writer, and the manifest untouched, so dropping the vendor (or swapping to another) is a one-function change and the rest of the pipeline stays vendor-neutral:

```python
def fetch(url: str) -> str:
    # DIY path was: urllib / Playwright. Managed path is one POST.
    resp = requests.post(
        "https://api.unblocker.example/v1/request",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"url": url, "render_js": True, "country": "gb"},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.text  # same string your parser already expects
```

Record the swap in the manifest (`"tool": "brightdata-unblocker"` / `"zyte-api"` / etc.) so a consumer reading the data later knows its provenance. Still apply the block-page gate from SKILL.md step 6 — managed services mostly return real content, but a failed solve can still hand back a challenge page, and you want that counted as an error rather than written as a record.

**Retry the incomplete render, not just the failed request.** A browser render (DIY or managed) has *three* failure modes, and the vendor's own server-side retry only covers one of them:

- a hard error (429/5xx/timeout) → retry with backoff, as in Tier 4;
- a challenge page → the block-page gate catches it;
- a **stub** — HTTP 200, real-looking HTML, but the DOM hadn't settled, so the price/rate/marker your parser needs isn't there yet. This is the one that silently corrupts, because the vendor sees a 200 and calls it success.

Guard the third with a **validate predicate** that re-fetches when the render is missing the markers you actually need, rather than dropping the item on one flaky render:

```python
def fetch(url, *, validate=None, retries=2):
    for attempt in range(retries + 1):
        html = _one_fetch(url)                     # POST to the unblocker
        if html and (validate is None or validate(html)):
            return html
        time.sleep(2 ** attempt)                   # backoff on stub / transient
    raise FetchError(f"no complete render for {url}")

# The caller says what "complete" means for THIS page — the markers the parser
# will need. Use the unblocker's own wait-for-selector flag first (cheaper than
# a re-fetch); the validate hook is the backstop for when the wait wasn't enough.
fetch(url, validate=lambda h: "data-price" in h and "selected_currency=" in h)
```

A determinate wrong value (see next) should *pass* validate and be caught by the assert — don't retry it, the re-fetch returns the same wrong value.

**The exit country changes the DATA, not just whether you get in.** Managed unblockers and residential proxies let you pick an exit country — and for anything localised (travel, retail, marketplaces) that flag changes *what the page says*, not only whether it loads: the currency, the language, the tax treatment, sometimes which items and prices are shown at all. So:

- **Pin the country deliberately and record it in the manifest.** The same URL fetched from `gb` and from `jp` are different observations; a series that silently changed exit country changed its own units mid-stream.
- **Assert the money/locale convention on every fetch, and refuse to record a mismatch.** Read the currency the page actually rendered (`selected_currency=`, a `data-currency`, a `¥`/`£`/`$` marker) and compare it to what you asked for. A silently converted price is worse than a gap — it's a wrong number that looks right. This is a *determinate* failure (re-fetching from the same country returns the same currency), so abort or skip that item; don't feed it to the render-retry above.

**Caveats**: it costs money (typically a few dollars per thousand requests, more for JS rendering); it's a third-party dependency and ToS still applies to *you*, not the vendor; and for trivial one-off jobs it's overkill — Tiers 0–2 are free and instant.

### Tier 6 — Specialised tooling

For the hardest targets (sites that have actively reverse-engineered Playwright and patched their detection):

- **`undetected-playwright` / `nodriver`** — Playwright forks that patch the harder-to-detect tells. Maintained by the bot-detection arms-race community.
- **Manual session handoff** — open the site in a real Chrome with the user, solve any captcha by hand, dump `storage_state` to a file, then run the scraper using that storage state until it expires.
- **Accept partial data** — scope the scraper to whatever loads without authentication or behind a single solved challenge, and document the limit.
- **Agentic navigation (different problem)** — if the wall isn't bot-*detection* but a fiddly multi-step path to the data (login → filters → modals → the listings), an agentic browser framework like Webwright can author the navigation script for you; see `references/agentic-browsing.md`. Note this is *not* a detection bypass — it drives the same browser and gets blocked by the same WAFs. Apply Tiers 0–5 first.

This tier is where ROI starts to drop sharply. Sites that have invested this much in keeping scrapers out will keep doing so; your scraper will need ongoing maintenance every few months. If you find yourself here, consider whether there's an official API or data-licensing option.

## Things that look like good ideas but aren't

- **Rotating UA randomly on every request.** This is itself a fingerprint — real browsers don't change UA mid-session. Pick one realistic UA and stick with it for the whole session.
- **Spoofing `Referer` headers to look like Google.** Sites cross-check Referer against the rest of the session. Setting it without the matching cookies/history makes you *more* suspicious.
- **Solving captchas via third-party services.** Generally a ToS violation, often a sign that you're at the wrong tier of effort — step back and consider the legitimacy of the scrape.
- **Disabling JavaScript to "look more like a search bot".** Most sites differentiate googlebot by IP range (reverse-DNS to `googlebot.com`), not by UA. Pretending to be a bot just makes you a different kind of bot.

## When to stop

If you're four tiers deep and the site still refuses, ask why you're doing this:

- Is there a public API? Many sites have an official one for a fee that's cheaper than residential proxies.
- Could the user get permissioned access? Sometimes a polite email + ToS acknowledgement gets a special-purpose endpoint.
- Is the scope reducible? Maybe you only need the data for 10 cities, not 200; or weekly, not hourly.
- Is the project worth it? Some sites are actively user-hostile to scraping for legitimate competitive reasons; that's their call to make.

It's a valid outcome to report "this site cannot be scraped within reasonable constraints" rather than to keep escalating indefinitely.
