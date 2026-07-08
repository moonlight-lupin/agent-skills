# Playwright patterns for scraping

Browser automation when none of the lighter strategies in `recon.md` work. Playwright is the right tool here — Selenium is older and lacks Playwright's quality-of-life features; pyppeteer/puppeteer are also acceptable but Playwright has better docs and active maintenance.

## Setup

```bash
pip install playwright playwright-stealth
playwright install chromium
```

Chromium specifically — Firefox and WebKit support is fine for compatibility testing but Chromium is what real users use, so anti-bot systems are tuned around it. Using Firefox actually makes you *more* fingerprint-distinct, not less.

## Minimal pattern

```python
from playwright.sync_api import sync_playwright

def scrape(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36",
                locale="en-GB",
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_selector("[data-test-id=product-card]", timeout=15_000)
            return page.content()
        finally:
            browser.close()
```

The two non-obvious choices here are the wait strategy and the selector gate — both worth understanding.

## Device emulation — when mobile HTML is different

Some sites serve materially different HTML to mobile vs desktop user-agents. Often the mobile site is leaner (less JS, more server-rendered markup, sometimes JSON-LD that desktop omits). If your scraper struggles against the desktop site, try the mobile profile before reaching for stealth or proxies.

Playwright ships built-in device presets (~140 of them) that bundle viewport, user-agent, device pixel ratio, and touch settings into one consistent profile:

```python
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    iphone = p.devices["iPhone 13"]
    context = browser.new_context(**iphone, locale="en-GB")
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded")
    # ...
```

`p.devices` keys are strings like `"iPhone 13"`, `"iPhone 15 Pro"`, `"Pixel 7"`, `"iPad Pro 11"`, `"Galaxy S9+"`, `"Desktop Chrome"`. Hand-assembling these by setting `user_agent`, `viewport`, `device_scale_factor`, and `is_mobile` separately is error-prone — small inconsistencies (mobile UA with desktop viewport) are themselves a bot fingerprint.

**When to switch profiles**: if recon shows the desktop page is client-rendered but `curl -A "<iPhone UA>" <url>` returns server-rendered HTML, scrape via the mobile profile and skip browser automation entirely.

## Wait strategies — `domcontentloaded` over `networkidle`

`page.goto()` accepts `wait_until` in:

- `load` — wait for the `load` event
- `domcontentloaded` — wait for the DOM to parse
- `networkidle` — wait for 500ms of zero network activity
- `commit` — wait only for the response headers

**Default to `domcontentloaded`.** Then gate on a specific selector that represents the content you actually need. `wait_for_selector("h1.product-name", timeout=15_000)` is more precise than waiting on global network state.

**Why `networkidle` is usually wrong**: many modern sites run continuous background traffic — analytics beacons, recommendation widgets, websockets, push notifications, polling for live availability. The network never goes idle, so Playwright hits its 30s default timeout on every page. We've seen this on student-housing sites (Unite Students), e-commerce checkout flows, and any site with a chat widget loaded.

**When `networkidle` is right**: simple static-ish sites where you genuinely want to wait for everything before reading. Try `domcontentloaded` first, fall back to `networkidle` only if you see the page hasn't finished rendering.

## Selector-based waiting

```python
# Wait for the thing you actually care about
page.wait_for_selector("[data-test-id=product-card]", timeout=15_000)

# Or wait for a specific condition (more flexible)
page.wait_for_function(
    "() => document.querySelectorAll('.product-card').length >= 10",
    timeout=15_000,
)
```

Pick selectors in this order of preference (most to least stable):

1. `[data-test-id=...]`, `[data-cy=...]`, `[data-product-id=...]` — test/data attributes, intentionally stable
2. `[itemprop=...]`, ARIA roles, semantic HTML (`<h1>`, `<main>`, etc.) — also stable
3. Class names that look hand-written (`.product-card`, `.price`) — usually stable
4. Class names that look generated (`.css-1a2b3c4`, `.sc-jKvBNL`) — change on every deploy. Avoid.
5. XPath with positional indexes (`/html/body/div[3]/div[2]/...`) — change with any layout tweak. Avoid.

If the site has zero stable selectors, your scraper is going to break frequently no matter what. Capture raw HTML and write a parser that's resilient to small layout changes (e.g. find by *text content* rather than position).

## Accessibility-tree locators — when CSS selectors aren't stable enough

For sites without data-attributes and with build-hashed class names (the common case for modern Vercel/Next.js / Vite SPAs), Playwright's accessibility-tree locators are usually more robust than CSS. They target elements by the same semantic primitives a screen reader would use — ARIA role, visible name, label, alt text. These rarely change between deploys because changing them breaks accessibility audits and SEO.

Playwright's own docs now recommend these as the *preferred* way to locate elements (CSS is the fallback, not the default):

```python
# Roles + accessible name — works for buttons, links, headings, form controls
page.get_by_role("button", name="Add to cart").click()
page.get_by_role("heading", name="Product details").is_visible()
page.get_by_role("link", name="Next page").click()

# Visible text (substring or exact match)
page.get_by_text("In stock", exact=True)
page.get_by_text(re.compile(r"£\d+\.\d{2}"))  # any visible price

# Form fields by their visible label or placeholder
page.get_by_label("Search").fill("widget pro")
page.get_by_placeholder("Enter postcode").fill("EH3 9DR")

# Images by alt text
page.get_by_alt_text("Product photo")

# Test-id (preferred when the site sets it — same as [data-testid=...])
page.get_by_test_id("price")
```

**Why these survive deploys better than CSS**:

- A `<button class="css-1a2b3c4">Add to cart</button>` keeps its visible text and ARIA role across redesigns, even when the class hash rotates on every build.
- A label-driven form field stays findable as long as the label visible to the user doesn't change.
- An icon-only button that has `aria-label="Close"` keeps that label for accessibility reasons even when the markup around it is refactored.

**Recon trick**: in DevTools, click an element you want to scrape and open the *Accessibility* panel (next to Styles/Computed). The role + name you see there is the exact pair to pass to `get_by_role`. If the element has no accessible name in that panel, locating it by `get_by_role` won't work and you're back to CSS.

**Limits**:

- Doesn't work for elements without accessible names (decorative `<div>`s, custom components without ARIA). Common on older sites and some intentionally-stripped landing pages.
- Doesn't work well when there are many identical buttons ("Add to cart" on every product card). In that case, scope to a parent first: `page.locator(".product-card").nth(0).get_by_role("button", name="Add to cart")`.

Use accessibility-tree locators *first*; fall back to CSS only when the element has no semantic markup. This inverts the old habit of writing `.product-card .price` everywhere.

## Headless vs headed

`launch(headless=True)` — default, fastest, lowest memory.

`launch(headless=False)` — slower, but useful in three cases:

1. **Debugging** a flaky scraper. Run headed locally to *see* what's happening.
2. **Some anti-bot systems** flag headless Chromium specifically. Stealth (see below) papers over most of this but a small minority of sites still detect headless. Try headed before giving up.
3. **Manual captcha solve** for a one-off harvest where you sit at the keyboard.

Don't run headed in production. Headless is 2-3× faster and uses much less memory; the difference compounds across thousands of pages.

## Stealth

Default Playwright is *easy* to detect. The default Chromium has `navigator.webdriver = true`, missing plugins, a specific WebGL fingerprint, and no Notification API. Bot-detection scripts check all of these in milliseconds.

```python
from playwright_stealth import Stealth

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    Stealth().apply_stealth_sync(browser)  # patches the browser

    # ... or per-context:
    Stealth().use_sync(context)
```

Stealth patches the obvious tells: `navigator.webdriver`, plugin list, WebGL fingerprint, etc. Run it by default on any site that does *any* bot detection. The cost is ~50ms of context setup, negligible.

Stealth doesn't help with everything — see `references/anti-bot.md` for what's still detectable and the escalation ladder.

## Cookie / consent overlays

EU and California regulation has pushed most sites to ship a cookie-consent banner that mounts on first visit. For a *user* this is a click; for a scraper it's three quiet problems:

1. **Screenshots** capture the modal on top of the content you wanted.
2. **Clicks** through to buttons under the modal get intercepted (`Element is outside of the viewport` / `another element receives the pointer events`).
3. **Lazy-loading** that fires on scroll-into-view never triggers because the modal locks scrolling.

The reliable fix is to neutralise the overlays before the page hydrates, via an init script. Two practical options:

**Option A — CSS hide common consent containers:**

```python
HIDE_BANNERS_JS = r"""
const style = document.createElement('style');
style.textContent = `
  #onetrust-consent-sdk, #onetrust-banner-sdk,
  #CybotCookiebotDialog, #cookiebanner,
  .cc-window, .qc-cmp2-container, .truste_box_overlay,
  div[id*="cookie" i], div[class*="cookie-banner" i],
  div[id*="consent" i][class*="modal" i] {
      display: none !important;
  }
  html, body { overflow: auto !important; }
`;
document.documentElement.appendChild(style);
"""

context = browser.new_context(...)
context.add_init_script(HIDE_BANNERS_JS)
```

This catches OneTrust, Cookiebot, Quantcast, TrustArc, and most home-rolled banners. Run it *as an init script* (not a `page.evaluate` after load) so it applies before the banner has a chance to paint and lock scroll.

**Option B — click the "Accept all" button by selector:**

If hiding it leaves the page in a broken state (some sites refuse to load content until consent is recorded — usually via a cookie they set client-side), click through instead:

```python
ACCEPT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "button#CybotCookiebotDialogBodyButtonAccept",
    "button:has-text('Accept all')",
    "button:has-text('I accept')",
    "button[aria-label*='Accept' i]",
]

for sel in ACCEPT_SELECTORS:
    try:
        page.locator(sel).first.click(timeout=2_000)
        break
    except Exception:
        continue
```

**When neither works**: a small number of sites (paywalled news, some EU news outlets) use a hard consent gate that won't even render the article body without an accepted cookie. If both options fail, run with `storage_state` from a session where you've accepted manually once.

## Fresh context per page

Cloudflare and similar WAFs track per-context state. If you visit the same protected site twice in the same context, the second visit is often challenged even though the first wasn't.

```python
def fetch_one(browser, url: str) -> str | None:
    context = browser.new_context(
        user_agent="...",
        locale="en-GB",
        viewport={"width": 1280, "height": 900},
    )
    try:
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_selector("[data-target]", timeout=20_000)
        return page.content()
    finally:
        context.close()
```

Cost of opening a fresh context: ~200-500ms (much cheaper than launching a new browser). Worth it for any site fronted by Cloudflare, Akamai, DataDome, PerimeterX, or similar.

## Injecting a page-side scraper

For SPAs with complex client-rendered state (modals, dropdowns, dynamic lists), it's often easier to run JavaScript *inside* the page than to drive it from Python. The page-side JS has direct access to the React/Vue component state, the DOM as-rendered, and any in-page caches.

```python
result = page.evaluate("""
() => {
    const cards = document.querySelectorAll('[data-test-id=product-card]');
    return Array.from(cards).map(card => ({
        name: card.querySelector('h3')?.textContent?.trim(),
        price: card.querySelector('.price')?.textContent?.trim(),
        sku: card.dataset.productId,
    }));
}
""")
```

When the JS gets bigger than ~30 lines, extract it to a `.js` file and load it:

```python
scraper_js = (Path(__file__).parent / "scraper.js").read_text()
result = page.evaluate(f"() => {{ {scraper_js} }}")
```

Or inject it once and call its exported functions:

```python
page.add_script_tag(content=scraper_js)
result = page.evaluate("() => window._scraperRun()")
```

**Why this beats Python-side DOM scraping**: page-side JS can wait for things synchronously (`await new Promise(r => setTimeout(r, 100))`), can read computed styles, can detect React state via `__REACT_DEVTOOLS_GLOBAL_HOOK__` if needed, and runs at native speed. Python-driven CSS-selector loops are an order of magnitude slower for the same work.

## Click-and-wait patterns

Many SPAs only render data after user interaction (clicking a tab, selecting an option from a dropdown). Pattern:

```python
# Snapshot the "before" state so we can detect change
prev = page.evaluate("() => document.querySelector('.price').textContent")

# Click
page.click("button[data-tab=51-week]")

# Poll for the value to actually change — don't trust a fixed sleep
page.wait_for_function(
    f"() => document.querySelector('.price')?.textContent !== '{prev}'",
    timeout=2_500,
)

# Now read
new_price = page.evaluate("() => document.querySelector('.price').textContent")
```

The "poll for change" pattern is critical for SPAs because React re-renders are asynchronous. A fixed `wait_for_timeout(350)` will work *most* of the time and produce subtly wrong data the rest. Always wait for a specific condition.

If you can't find a stable post-click signal, fall back to `page.wait_for_load_state("networkidle")` — for click handlers the network usually does briefly go quiet, even on otherwise-busy sites.

## Errors and retries

Playwright raises `TimeoutError` when a selector or navigation doesn't complete in time. Catch it per-item, not per-batch:

```python
from playwright.sync_api import TimeoutError as PWTimeout

for url in urls:
    try:
        html = fetch_one(browser, url)
        records.extend(parse(html))
    except PWTimeout as e:
        log.warning("timeout on %s: %s", url, e)
        errors.append({"url": url, "reason": "timeout"})
```

Retry once on timeout if it's cheap; don't retry on the same URL more than 2-3 times — repeated timeouts usually mean the site is rate-limiting you or has changed shape.

## Concurrency

Playwright is single-threaded per `sync_playwright()` instance. To parallelise:

- **Multiple pages, one browser**: `context.new_page()` for each — share the browser, run pages concurrently with `asyncio.gather` (use `async_playwright`).
- **Multiple workers, one process**: `ThreadPoolExecutor` with one browser per thread. Each thread gets its own `sync_playwright()`.
- **Multiple processes**: heaviest, but the cleanest isolation. Use only if memory pressure is a problem (each Chromium instance is ~300-500MB).

For most scraping jobs, 3-5 concurrent pages on a single browser is plenty. More concurrency triggers more rate-limiting from the target and rarely speeds things up.

## Resource hints

- Disable images and CSS to speed up: `context.route("**/*.{png,jpg,css}", lambda r: r.abort())`. Only do this if you've verified your selectors don't depend on them (some sites lazy-load via CSS background-image).
- Save state between runs: `context.storage_state(path="state.json")` and `browser.new_context(storage_state="state.json")`. Useful for auth'd sites where the login flow is expensive.
- Block ads/trackers explicitly: route `**/google-analytics.com/**`, `**/doubleclick.net/**` to abort. Speeds up some sites noticeably.
