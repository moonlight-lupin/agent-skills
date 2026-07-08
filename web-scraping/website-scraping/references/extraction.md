# Extraction patterns

Field-level patterns that recur across most scraping jobs, with concrete code.

## JSON-LD extraction

The cleanest source of structured data on the modern web. Most e-commerce, hotel, real-estate, job, news, recipe, and event sites emit JSON-LD because Google rewards it with rich SERP results.

```python
import json
import re

_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

def extract_jsonld(html: str) -> list[dict]:
    """Returns all JSON-LD objects on the page, flattening @graph wrappers."""
    out: list[dict] = []
    for m in _JSONLD_RE.finditer(html):
        try:
            blob = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(blob, list):
            out.extend(b for b in blob if isinstance(b, dict))
        elif isinstance(blob, dict) and "@graph" in blob:
            out.extend(b for b in blob["@graph"] if isinstance(b, dict))
        elif isinstance(blob, dict):
            out.append(blob)
    return out

def filter_by_type(items: list[dict], type_name: str) -> list[dict]:
    """Filter JSON-LD items by @type. Type can be a string or list."""
    def matches(item):
        t = item.get("@type")
        if isinstance(t, list):
            return type_name in t
        return t == type_name
    return [i for i in items if matches(i)]

# Usage
products = filter_by_type(extract_jsonld(html), "Product")
for p in products:
    name = p.get("name")
    sku = p.get("sku")
    offers = p.get("offers", {})
    if isinstance(offers, list):
        offers = offers[0]  # often a list when there are variants
    price = offers.get("price")
    currency = offers.get("priceCurrency")
```

**Common shapes**:

| `@type` | Useful fields |
|---|---|
| `Product` | name, sku, mpn, brand.name, offers.price, offers.priceCurrency, offers.availability, aggregateRating.ratingValue, aggregateRating.reviewCount |
| `Hotel` / `LodgingBusiness` | name, address (PostalAddress: streetAddress, postalCode, addressLocality), starRating.ratingValue, priceRange |
| `Apartment` / `Residence` | name, address, numberOfRooms, floorSize.value |
| `JobPosting` | title, hiringOrganization.name, jobLocation.address, baseSalary.value.minValue/maxValue, datePosted, validThrough, employmentType |
| `Event` | name, startDate, endDate, location.name, location.address, offers.price |
| `Recipe` | name, recipeIngredient (list), recipeInstructions, nutrition.calories |
| `Article` / `NewsArticle` | headline, datePublished, author.name, articleBody |

**Address from JSON-LD** — universal pattern:

```python
def address_from_jsonld(item: dict) -> dict | None:
    addr = item.get("address")
    if isinstance(addr, list):
        addr = addr[0] if addr else None
    if not isinstance(addr, dict):
        return None
    return {
        "street": addr.get("streetAddress"),
        "city": addr.get("addressLocality"),
        "region": addr.get("addressRegion"),
        "postcode": addr.get("postalCode"),
        "country": addr.get("addressCountry"),
    }
```

This works across 90%+ of UK/US/EU sites that publish addresses. Falls back to nothing if absent.

## Article-text extraction with readability-lxml

When the job is "just give me the readable body of this article" — news pieces, blog posts, long-form docs — and you don't need field-level structure, `readability-lxml` is the lightest path. It's the same algorithm Firefox Reader View and most "read later" apps use: score each block by text-density / link-density / tag weight, return the densest subtree.

```python
# pip install readability-lxml --break-system-packages
from readability import Document
import urllib.request

req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 ..."})
html = urllib.request.urlopen(req).read()

doc = Document(html)
title = doc.title()          # cleaned page title
summary_html = doc.summary() # the main article body as HTML (boilerplate stripped)
```

`summary()` returns HTML; pair with `BeautifulSoup(summary_html, "html.parser").get_text("\n")` for plain text, or pipe through `markdownify` for Markdown.

**When to reach for it**:

- Bulk-fetching articles for summarisation / RAG ingestion / archiving.
- The user says "scrape the text of these blog posts" — no schema, no fields.
- JSON-LD `Article.articleBody` is missing or truncated (some sites only inline the first paragraph).

**When *not* to use it**:

- You need specific fields (price, sku, address) — use JSON-LD or selectors instead. Readability throws away exactly the kind of structure you want.
- The page is a listing/grid (product cards, search results) — readability is designed for single-article pages and will pick one card at random.
- Heavily client-rendered SPAs where the article body is injected after load — readability sees the pre-hydration shell. Fetch via Playwright first, *then* feed `page.content()` into `Document`.

## Finding JSON-in-page blobs

When JSON-LD is missing or incomplete, look for the framework's hydration blob. The path varies; **explore interactively first**.

```python
# Common signatures
_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.DOTALL,
)
_NUXT_RE = re.compile(r'window\.__NUXT__\s*=\s*(\{.*?\});', re.DOTALL)
_DRUPAL_RE = re.compile(
    r'<script[^>]+data-drupal-selector=["\']drupal-settings-json["\'][^>]*>(.*?)</script>',
    re.DOTALL,
)
_INITIAL_STATE_RE = re.compile(
    r'window\.__(?:INITIAL_STATE|PRELOADED_STATE)__\s*=\s*(\{.*?\});', re.DOTALL,
)

def find_framework_blob(html: str) -> tuple[str, dict] | None:
    """Returns (framework_name, blob) or None."""
    for name, pat in [
        ("next", _NEXT_DATA_RE),
        ("nuxt", _NUXT_RE),
        ("drupal", _DRUPAL_RE),
        ("initial_state", _INITIAL_STATE_RE),
    ]:
        m = pat.search(html)
        if m:
            try:
                return name, json.loads(m.group(1))
            except json.JSONDecodeError:
                continue
    return None
```

**Exploration first, code second.** Drop into a REPL with the blob loaded; walk `list(blob.keys())` to figure out the path. Don't write speculative `blob["props"]["pageProps"]["data"]["items"]` chains based on assumptions about the framework.

## Deduplication

Real scrapes always produce duplicates — pagination overlaps, the site renders some items twice (see "Double-render" below), retry logic re-scrapes successful items. Dedup by a **stable canonical identifier**:

```python
def dedup(records: list[dict], key: callable) -> list[dict]:
    seen, out = set(), []
    for r in records:
        k = key(r)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out

# Usage — by site-provided ID
deduped = dedup(records, key=lambda r: r["product_id"])

# Usage — by URL when no ID exists
deduped = dedup(records, key=lambda r: r["url"])

# Usage — composite key for products with variants
deduped = dedup(records, key=lambda r: (r["sku"], r.get("variant_id")))
```

**Why not `set(tuple(r.items()) for r in records)`**: real records have minor variations (whitespace, timestamp, run id) that you don't want to count as differences. Stable id is the right granularity.

**Identifier hierarchy**:

1. Site-provided numeric ID (`data-product-id`, `id="hotel-12345"`) — most stable
2. URL slug (`/products/widget-pro-2024`) — stable until the site rewrites URLs
3. SKU / model number from the page content — stable but watch for sites where multiple variants share a SKU
4. Normalised name + first identifier-ish field — last resort

## Double-render workaround

Some SPAs mount the same element twice in the DOM — once in a "featured" list and once in the main grid. A naive `querySelectorAll('.product-card')` returns 23 cards when there are only 15 real products. Symptoms in your output: every item appears twice, or some items have correct data while their duplicates have stale data.

**Detection**: count the visible cards in the browser, compare to your scraper's output. If they differ predictably (the scraper has more), dedup by visible-content identifier (the H1/H2/title) before doing anything else.

**Page-side dedup**:

```javascript
// Inside page.evaluate()
const seen = new Set();
const cards = Array.from(document.querySelectorAll('.product-card')).filter(card => {
    const id = card.querySelector('h2')?.textContent?.trim();
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
});
```

## Polling for value change after click

In React/Vue SPAs, clicking a tab/option triggers an async re-render. A fixed `time.sleep(0.5)` works most of the time but produces silently wrong data when the re-render is slow (network call, conditional state).

**The pattern**: snapshot the value before the click, poll until it changes, then read.

```python
def click_and_wait_for_change(page, click_selector, read_selector, timeout_ms=2500):
    prev = page.evaluate(f"() => document.querySelector('{read_selector}')?.textContent")
    page.click(click_selector)
    page.wait_for_function(
        f"() => document.querySelector('{read_selector}')?.textContent !== {json.dumps(prev)}",
        timeout=timeout_ms,
    )
    return page.evaluate(f"() => document.querySelector('{read_selector}')?.textContent")
```

The first click on a freshly-loaded card has nothing to compare to — handle by reading on first tick rather than polling.

## Field-level parsing recipes

Common field shapes that take a few minutes to get right and then never need touching again.

### Money

```python
import re

_MONEY_RE = re.compile(
    r"([£$€¥])\s*([\d,]+(?:\.\d{1,2})?)",
)

def parse_money(text: str) -> tuple[str, float] | None:
    m = _MONEY_RE.search(text or "")
    if not m:
        return None
    symbol, amount = m.group(1), m.group(2).replace(",", "")
    currency = {"£": "GBP", "$": "USD", "€": "EUR", "¥": "JPY"}[symbol]
    return currency, float(amount)
```

Don't try to handle every currency in one regex — start with the symbols you actually meet, expand as needed.

### Ranges (price, size, capacity)

When sites show "£89–£129" or "15-17 sqm", capture both ends and a midpoint:

```python
_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–—to]+\s*(\d+(?:\.\d+)?)")

def parse_range(text: str) -> tuple[float, float] | None:
    m = _RANGE_RE.search(text or "")
    if not m:
        return None
    return float(m.group(1)), float(m.group(2))

def parse_value_or_range(text: str) -> dict:
    """Returns {'min', 'max', 'mid', 'raw'} — min==max when not a range."""
    rng = parse_range(text)
    if rng:
        lo, hi = rng
        return {"min": lo, "max": hi, "mid": (lo + hi) / 2, "raw": text}
    # Single value
    m = re.search(r"(\d+(?:\.\d+)?)", text or "")
    if m:
        v = float(m.group(1))
        return {"min": v, "max": v, "mid": v, "raw": text}
    return {"min": None, "max": None, "mid": None, "raw": text}
```

### Postcodes / ZIP codes

UK postcodes:
```python
_UK_POSTCODE_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b", re.IGNORECASE)
```

US ZIP:
```python
_US_ZIP_RE = re.compile(r"\b(\d{5}(?:-\d{4})?)\b")
```

Run against the *entire page body* as a fallback when structured address fields aren't present. Postcodes/ZIPs are short and specific, so false positives are rare.

### Dates

Sites use a mind-numbing variety of date formats. Use `dateutil.parser` for permissive parsing, then validate:

```python
from dateutil import parser as date_parser

def parse_date(text: str, *, dayfirst: bool = True) -> str | None:
    """Returns ISO date 'YYYY-MM-DD' or None. dayfirst=True for UK/EU sites."""
    try:
        dt = date_parser.parse(text, dayfirst=dayfirst, fuzzy=True)
        return dt.date().isoformat()
    except (ValueError, TypeError, OverflowError):
        return None
```

**Critical**: `dayfirst=True` for UK/EU sites (DD/MM/YYYY), `dayfirst=False` for US sites (MM/DD/YYYY). Get this wrong and you'll silently produce nonsense for ~30% of dates (those where the day is ≤12).

### Geocoding (if you actually need lat/lng)

For UK addresses, prefer postcode-first via Nominatim:

```python
import time
import urllib.parse
import requests

def geocode_uk(postcode: str | None, address: str | None, city: str | None) -> tuple[float, float] | None:
    """Try postcode first (most reliable in UK), then full address, then city."""
    candidates = []
    if postcode and city:
        candidates.append(f"{postcode}, {city}, UK")
    if postcode:
        candidates.append(f"{postcode}, UK")
    if address and postcode and city:
        candidates.append(f"{address}, {postcode}, {city}, UK")
    if address and city:
        candidates.append(f"{address}, {city}, UK")

    for q in candidates:
        time.sleep(1.1)  # Nominatim's 1 req/sec rate limit — be polite
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": q, "format": "json", "limit": 1},
            headers={"User-Agent": "my-scraper/1.0 (contact@example.com)"},
        )
        results = r.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    return None
```

**Why postcode first**: Nominatim sometimes prioritises a street-name match over a postcode constraint and returns the wrong city. UK postcodes are tighter than street names (each maps to ~30 addresses), so leading with the postcode is more deterministic.

For US ZIP codes: order is similar but the trade-off is different (ZIPs cover broader areas, so address-first is fine if you trust the city). Always test against a few known cases when starting on a new region.

## Schema robustness — missing fields are normal

Real sites have missing fields on real items. A product without a price (sold out), an event without an end date (ongoing), a job listing without a salary (undisclosed). Code for it:

```python
def extract_one(item) -> dict:
    return {
        "id": item.get("id"),                # required, KeyError if absent in your assertion
        "name": item.get("name"),
        "price": _safe_float(item.get("price")),  # missing → None
        "currency": item.get("currency"),
        "url": item.get("url"),
        "scraped_at": datetime.utcnow().isoformat() + "Z",
    }

def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
```

When a field is *unexpectedly* missing (you expected it to be there, but it's not), log a warning with the item's identifier. Don't crash — the rest of the batch is still valuable.
