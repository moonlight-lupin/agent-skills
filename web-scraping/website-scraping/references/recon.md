# Recon — picking the right extraction strategy

The recon decision tree from SKILL.md, expanded with concrete examples of how to spot each pattern and what the code looks like for each.

## Step 0 — Find the URLs you need

Before any of the five extraction strategies, you need a list of URLs to extract *from*. Often the user hands you a single seed page ("scrape this category"), or even just a domain ("scrape their products"), and you have to discover the individual item URLs yourself. Skipping this step and just clicking through to a few sample pages by hand is the slow path; the four techniques below cover most jobs.

**Try them in order — stop at the first one that gives you what you need.**

### 0a. Sitemaps

The single biggest win. Most sites publish a sitemap because Google demands it. The sitemap is a deliberately flat list of every URL the site owner wants indexed — usually exactly what you want to scrape.

Where to look:

1. `/sitemap.xml` and `/sitemap_index.xml` at the root.
2. `/robots.txt` — sitemaps are declared via `Sitemap:` directives at the bottom. **Always check robots.txt first**; it often points to multiple sitemaps you wouldn't have guessed (e.g. `/sitemap-products.xml`, `/sitemap-news.xml`).
3. Common namespaced paths: `/sitemap/products.xml`, `/wp-sitemap-posts-post-1.xml`, `/sitemap_index_1.xml`.

```python
import urllib.request
import xml.etree.ElementTree as ET

def discover_sitemaps(root_url: str) -> list[str]:
    """Read robots.txt and return all declared sitemap URLs."""
    req = urllib.request.Request(
        root_url.rstrip("/") + "/robots.txt",
        headers={"User-Agent": "Mozilla/5.0 ..."},
    )
    body = urllib.request.urlopen(req).read().decode("utf-8", errors="ignore")
    sitemaps = []
    for line in body.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemaps.append(line.split(":", 1)[1].strip())
    # Fallback if robots.txt was silent
    if not sitemaps:
        sitemaps = [root_url.rstrip("/") + "/sitemap.xml"]
    return sitemaps

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

def urls_from_sitemap(sitemap_url: str) -> list[str]:
    """Yield URLs from a sitemap, recursing into sitemap-indexes."""
    body = urllib.request.urlopen(sitemap_url).read()
    root = ET.fromstring(body)
    out = []
    # Sitemap index (points to other sitemaps)
    for sm in root.findall("sm:sitemap/sm:loc", NS):
        out.extend(urls_from_sitemap(sm.text))
    # Plain URL list
    for loc in root.findall("sm:url/sm:loc", NS):
        out.append(loc.text)
    return out
```

Then filter to the URL pattern you care about — usually a simple substring or regex match (`/product/`, `/listing/`, `/recipes/`).

**Sitemap gotchas**:

- **Stale**. Sitemaps are regenerated on a schedule, not in real time. New items can take hours to appear; deleted items can linger for days. Cross-check totals against the site's own "X results" count.
- **Gzipped**. `.xml.gz` is common — `gzip.decompress` before parsing.
- **Split across many files**. Sites with >50k URLs split into multiple sitemaps via a sitemap index. The recursive function above handles this.
- **Omits gated content**. Anything behind a login won't be in a public sitemap.

### 0b. The site's own search

If the site has an internal search box, the search-results page is usually the most efficient lister of items. It's deliberately designed to return many items per request, often with structured pagination (`?page=N` or `?offset=N`), and it accepts query terms that let you scope the scrape ("all properties in Edinburgh", "all jobs in marketing").

Two patterns:

1. The search page is server-rendered HTML — read it with `urllib`, extract item links, iterate pagination. Cheapest path.
2. The search page calls a JSON endpoint — even better; see Strategy 4 below.

### 0c. Category / browse pages

If neither sitemap nor search works, fall back to the category navigation. Walk the menu structure, collect every leaf category URL, then scrape each category's listing pages. This produces duplicates (the same item often appears under multiple categories) — dedup by URL after collection.

This is the slowest discovery method and most prone to missing items the site has but doesn't surface in its menus. Use only when the first two fail.

### 0d. Breadth-first crawl from a seed

When there's no sitemap, no search, and no clean category structure — usually a documentation site, a wiki, or a brochure-style site — crawl outward from a seed page. Rules to keep this safe and small:

```python
from urllib.parse import urljoin, urlparse
import collections

def bfs_crawl(seed: str, *, max_pages: int = 500, same_host_only: bool = True,
              url_filter=lambda u: True) -> list[str]:
    """Discover URLs by following links from a seed. Stops at max_pages."""
    seed_host = urlparse(seed).netloc
    seen = {seed}
    queue = collections.deque([seed])
    out = []
    while queue and len(out) < max_pages:
        url = queue.popleft()
        out.append(url)
        try:
            html = fetch(url)  # your urllib wrapper
        except Exception as e:
            continue
        for link in extract_links(html, base=url):
            if link in seen:
                continue
            if same_host_only and urlparse(link).netloc != seed_host:
                continue
            if not url_filter(link):
                continue
            seen.add(link)
            queue.append(link)
    return out
```

Three non-negotiable safety rules for crawling:

1. **`max_pages` is mandatory.** Without it, you'll discover the whole web. A real-world crawl rarely needs more than a few thousand pages.
2. **`same_host_only=True` by default.** Following external links turns your scraper into an unbounded web crawler.
3. **`url_filter` to scope.** Pass a function that filters out `/admin/`, `/login/`, `/cart/`, `mailto:`, `tel:`, etc. before they ever enter the queue.

**Anti-pattern**: crawling without a sitemap check first. Sitemaps are flat, predictable, and authoritative; crawling reinvents that with more requests and more risk of getting blocked.

### How to choose between 0a–0d

```
Is there a /robots.txt with Sitemap: directives, or a /sitemap.xml?
├─ YES → Use it. Filter to your URL pattern. Done.
│
└─ NO → Does the site have an internal search that lists items?
    │
    ├─ YES → Hit the search endpoint (JSON if you can find it, HTML otherwise),
    │        paginate through. Done.
    │
    └─ NO → Is there a clean category / browse hierarchy?
        │
        ├─ YES → Walk the menu, collect category URLs, list items per category,
        │        dedup by URL.
        │
        └─ NO → BFS crawl from a seed with max_pages + same-host + filter.
                Last resort.
```

Once you have the URL list, hand it to the extraction strategies below.

---

## Before the five strategies: is DIY even the right call?

Two cheap checks precede the extraction strategies (they mirror SKILL.md step 2.0):

- **Is a fetch/scrape tool already available in your runtime?** For a one-off, low-volume pull, Hermes's `web_search` + `web_extract` tools or a scraping MCP server beats writing any code. Use it. For anything repeatable or high-volume, write a script you can diff and re-run.
- **Is the target a hostile mega-platform?** Amazon, LinkedIn, Instagram, TikTok, Facebook, YouTube, Zillow, Google Maps, Crunchbase and their peers spend real engineering on defeating DIY scraping and rotate their internals constantly. For these, a custom scraper tends to work briefly then break — the genuinely lightest tool is often a maintained commercial data product (Bright Data Web-Scraper/dataset APIs, Apify actors, etc.) that already owns the extraction. Flag this trade-off to the user before committing to a hand-rolled scraper; if they still want DIY, expect to live on the anti-bot ladder (`references/anti-bot.md`).

If neither shortcut applies, pick from the five strategies below.

## The five strategies, in order of preference

| # | Strategy | Cost | When to use |
|---|---|---|---|
| 1 | Static HTML parse | Cheapest | Data is in the page source as plain HTML |
| 2 | JSON-LD extraction | Very cheap | Data is in a `<script type="application/ld+json">` block |
| 3 | Framework JSON-in-page (Next.js/Nuxt/Drupal/etc.) | Cheap | Data is in a single `<script>` JSON blob meant for client-side hydration |
| 4 | Reversed REST API | Cheap once found | Data comes from an XHR/fetch call you can replay directly |
| 5 | Browser automation (Playwright) | Expensive | Content is client-rendered and none of the above apply |

**Always recon before coding.** The 5 minutes you spend in DevTools saves hours of writing the wrong scraper.

---

## Strategy 1 — Static HTML

**Signature**: right-click → "View Page Source", search for one of the field values you want. If you find it, the page is server-rendered.

**Tools**: `urllib.request` (stdlib, no deps) or `requests`. Parse with `html.parser`, `lxml`, or `BeautifulSoup` — pick by team taste. Regex is acceptable for one-off extraction of a single fragment but breaks badly on real HTML.

**Common gotchas**:

- **Default UA is blocked.** `urllib.request.urlopen()` ships `Python-urllib/3.x` as UA, which many sites refuse. Always set a real browser UA:
  ```python
  req = urllib.request.Request(url, headers={
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36",
      "Accept-Language": "en-GB,en;q=0.9",
  })
  ```
- **Cookies / sessions matter for some sites.** Use `requests.Session()` if a CSRF cookie or session cookie is needed.
- **Pagination is usually a `?page=2` or `?offset=20` parameter.** Reconnaissance: increment the page number in the browser and confirm. Stop when you see an empty result page, not when you see an HTTP error.

**Example signature** — what tells you the data is static:

```
$ curl -A "Mozilla/5.0" https://example.com/products/widget-42 | grep -i "£89.99"
<span class="price">£89.99</span>
```

If `curl` (or `urllib`) returns the value, you're done with recon.

---

## Strategy 2 — JSON-LD

**Signature**: search the page source for `application/ld+json`. Almost every modern e-commerce, hotel, news, recipe, real-estate, and event site emits JSON-LD for SEO. Shapes follow schema.org.

**Universal shapes you'll meet most often**:

- `Product` → name, sku, offers (price, priceCurrency, availability)
- `Hotel` / `LodgingBusiness` → name, address (PostalAddress), starRating, aggregateRating
- `Apartment` / `Residence` / `Place` → address, geo (latitude/longitude)
- `JobPosting` → title, hiringOrganization, baseSalary, datePosted
- `Event` → name, startDate, location, offers
- `Recipe` → ingredients, instructions, nutrition
- `BreadcrumbList`, `Organization`, `WebPage` → mostly noise, usually skip
- `FAQPage` → Q&A pairs (handy for reviews/specs)

**Extraction pattern**:

```python
import json
import re
from html.parser import HTMLParser

JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

def extract_jsonld(html: str) -> list[dict]:
    out = []
    for m in JSONLD_RE.finditer(html):
        try:
            blob = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        # JSON-LD blocks can be a single object, a list, or have a @graph wrapper
        if isinstance(blob, list):
            out.extend(blob)
        elif isinstance(blob, dict) and "@graph" in blob:
            out.extend(blob["@graph"])
        else:
            out.append(blob)
    return out
```

**Why prefer JSON-LD over HTML scraping** even when both work: JSON-LD is schema-stable. Sites change their visual layout every few months; the underlying schema.org markup tends to stick around for years because changing it affects SEO ranking.

**Gotcha**: some sites emit *placeholder* JSON-LD that's incomplete (e.g. price is `0` or missing). Always validate by cross-checking against the visible HTML for at least one item.

---

## Strategy 3 — Framework JSON-in-page

Modern JS frameworks server-render the initial state into a JSON blob inside the HTML so the client can hydrate without a second request. These blobs typically contain *more* data than the page visually displays (admin fields, draft state, related items).

**Common signatures**:

| Framework | Look for | Notes |
|---|---|---|
| Next.js | `<script id="__NEXT_DATA__" type="application/json">` | Usually rich. Page-specific data under `props.pageProps`. |
| Nuxt.js | `window.__NUXT__ = ...` or `<script id="__NUXT_DATA__">` | Older Nuxt 2 uses a JS assignment, Nuxt 3 uses a script tag. |
| Drupal | `<script data-drupal-selector="drupal-settings-json">` | All settings in one big object. |
| Generic Redux/Vuex SSR | `window.__INITIAL_STATE__ = ...` or `window.__PRELOADED_STATE__` | Common across hand-rolled SPAs. |
| Gatsby | `window.___INITIAL_PROPS___` | Less common now. |
| Shopify (storefront) | `var meta = {...}` near top of `<head>`, plus Liquid-rendered product objects | Often has full product JSON. |
| Wordpress with WooCommerce | `var wc_single_product_params = {...}` | Limited; usually still need HTML fallback. |

**Extraction pattern** (Next.js example):

```python
NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)

def extract_next_data(html: str) -> dict | None:
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    return json.loads(m.group(1))

data = extract_next_data(html)
products = data["props"]["pageProps"]["products"]  # path varies per site
```

**Gotcha — exploration first**:

The path to the data inside the blob varies per site. Don't guess — dump the blob, navigate it interactively (in a Python REPL, Jupyter, or with `jq`), find the path, *then* code the extraction. Trying to write the path without exploring leads to deep `KeyError` chains.

```python
# Throwaway exploration
import json
blob = extract_next_data(html)
print(list(blob.keys()))
print(list(blob.get("props", {}).keys()))
# ... walk down
```

**Why this is often the best path** even when other strategies work: the blob is the same JSON the client uses to render. Edge cases like "this field is null on some items" are explicit in the JSON rather than hidden in conditional HTML rendering.

---

## Strategy 4 — Reversed REST API

**Signature**: in DevTools → Network → XHR/Fetch, you can see the page fetch JSON from `/api/...` or a GraphQL endpoint. The response contains your target fields.

**Reverse it**:

1. In DevTools, right-click the request → "Copy as cURL".
2. Replay in a terminal — confirm the same response.
3. Trim headers progressively. Most sites only need `User-Agent` and `Accept`. A surprising number need nothing else.
4. Some sites require: a session cookie (load the page first to get it), a CSRF / anti-forgery token (read it from the HTML form), a signed `Authorization` header (harder — usually means JWT or HMAC; may or may not be replayable).
5. Code it up:
   ```python
   import requests
   r = requests.get("https://example.com/api/v2/products", params={"city": "edinburgh"},
                    headers={"User-Agent": "Mozilla/5.0 ...", "Accept": "application/json"})
   r.raise_for_status()
   for product in r.json()["data"]:
       ...
   ```

**Why this is often the cleanest path**: you're consuming the same API as the site itself. Fields are named, types are predictable, pagination is explicit (cursor or offset/limit). No HTML parsing fragility.

**When the API requires auth you don't have**: stop. Either get explicit permission to use the API, or fall back to Strategy 5 (browser automation, which uses the session the browser establishes automatically).

**GraphQL gotcha**: GraphQL endpoints want a POST with a query body. The query in the browser's request is usually fine to replay verbatim. If the site uses *persisted queries* (a hash, not the query text), you may need to either send the query text (sometimes still accepted) or extract the hash from a JS bundle. The former is much easier.

---

## Strategy 5 — Browser automation

You've reached this point because:

- The data is not in page source (Strategy 1 fails)
- There's no JSON-LD with what you need (Strategy 2 fails)
- No framework blob has the data (Strategy 3 fails)
- The API requires complex auth, or is rate-limited tighter than the website, or doesn't expose the field you need (Strategy 4 fails)

Now use Playwright. See `references/playwright.md` for the full pattern.

**If the obstacle is multi-step *navigation*, not parsing** — login flows, filter wizards
spread across several screens, calendar pickers, "load more" sequences you'd otherwise
hand-script and debug for an hour — consider an agentic browser framework (Microsoft's
Webwright) to *write* the navigation script for you, then lift the resulting script into
your scraper. This is for the gnarly-path case only, not bulk extraction. See
`references/agentic-browsing.md` for when it pays off and when it's overkill.

**Last sanity check before committing to Playwright**: open the page in a browser with JS disabled (DevTools → Settings → Debugger → "Disable JavaScript", reload). If the data is still there, the page is server-rendered and you missed Strategy 1. If the data disappears, you genuinely need browser automation.

---

## Hybrid strategies

Real scrapers often mix strategies across pages:

- **Search page is Playwright, detail page is static HTML.** The search page renders results client-side, but each result link goes to a server-rendered detail page. Use Playwright once to harvest the URLs, then `urllib` per detail page. (Pattern: the PBSA `downing_scraper.py` does exactly this.)
- **Listing is static, prices are XHR.** The listing HTML names the products but prices come from a per-product API call. Static parse + API call per product.
- **Page is server-rendered but uses a modal for variant selection.** The base data is in the HTML; the variant-specific data requires clicking. Often the variants are also in the HTML, hidden in `<select>` options or `data-` attributes — look harder before reaching for click automation.

The point of hybrid: use the cheapest viable tool *for each piece of data*, not the cheapest tool that handles all of it.
