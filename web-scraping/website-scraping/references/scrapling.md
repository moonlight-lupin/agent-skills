# Scrapling — Optional Parser and CLI Tool

Scrapling is a Python web scraping library (BSD-3-Clause, v0.4.14) installed
parser-only on this system. It provides an adaptive HTML parser, CSS/XPath/BS4
selectors, and element similarity matching. Browser fetchers (StealthyFetcher,
DynamicFetcher) and spiders require `scrapling[all]` + `scrapling install` —
not installed on the VM due to RAM constraints.

## When to reach for Scrapling vs our default tools

| Situation | Use | Why |
|---|---|---|
| Static HTML, simple structure | `urllib` + `lxml` or Scrapling parser | Both work. Prefer urllib if no Scrapling-specific feature needed. |
| Site changed structure, selectors broke | Scrapling parser with `adaptive=True` | Scrapling relocates elements by similarity. See concept 2 below. |
| Need CSS + XPath + BS4-style selectors in one API | Scrapling parser | Single API, no switching between libraries. |
| Cloudflare / anti-bot | `web_extract` tool first, then Playwright+stealth | Scrapling's StealthyFetcher needs full install + browsers. Not available on VM. |
| Full crawl with proxy rotation | Scrapling spiders (needs full install) | Run on Win PC or NAS Docker, not the VM. |
| CLI one-off scrape for LLM consumption | `scrapling extract get` with `--ai-targeted` | Sanitizes output for prompt injection safety. See concept 1 below. |

## Concept 1 — `--ai-targeted` prompt injection protection

When scraped content will feed into an LLM, hidden elements (script tags, hidden
divs, data attributes) can carry prompt injection payloads. Scrapling's
`--ai-targeted` flag strips these before saving.

**CLI usage:**
```bash
scrapling extract get "https://example.com" output.md --ai-targeted
```

**Without Scrapling (apply the same principle manually):**
```python
# After fetching HTML, strip dangerous elements before passing to LLM
from lxml import html as lxml_html

def sanitize_for_llm(html_text: str) -> str:
    tree = lxml_html.fromstring(html_text)
    # Remove script, style, template, and hidden elements
    for tag in tree.iter(['script', 'style', 'template', 'noscript']):
        tag.getparent().remove(tag)
    for el in tree.iter():
        if el.get('style') and 'display:none' in el.get('style', '').replace(' ', ''):
            el.getparent().remove(el)
        if el.get('hidden') is not None:
            el.getparent().remove(el)
    return lxml_html.tostring(tree, encoding='unicode', method='text')
```

**Done when**: every `<script>`, `<style>`, `<template>`, `<noscript>`, and
hidden element is removed from the HTML before it enters any LLM prompt.

## Concept 2 — Adaptive element relocation

When a site changes its HTML structure, CSS selectors break. Scrapling solves
this by saving element fingerprints on the first successful scrape, then finding
similar elements later when selectors fail.

**Scrapling API:**
```python
from scrapling.fetchers import Fetcher

# First scrape — save element signatures
page = Fetcher.get('https://example.com')
products = page.css('.product', auto_save=True)  # saves fingerprints

# Later, after site redesign — find by similarity
page = Fetcher.get('https://example.com')
products = page.css('.product', adaptive=True)  # relocates using saved fingerprints
```

**Parser-only (no fetcher, works with our urllib flow):**
```python
from scrapling.parser import Selector

# Parse HTML we already fetched with urllib
page = Selector(html_text)
products = page.css('.product', auto_save=True)

# Next run, after site change
page = Selector(new_html_text)
products = page.css('.product', adaptive=True)
```

**Without Scrapling (manual fallback):**
```python
# If selectors break, use element similarity heuristics
# 1. Find elements with similar tag + class patterns
# 2. Match by text content similarity
# 3. Match by structural position (nth child, parent context)
```

**Done when**: the scraper returns the same records after a site structure
change, using saved fingerprints from the prior run. Use for monitoring jobs
that run repeatedly against the same site over weeks/months. For one-off
scrapes, `auto_save` adds no value.

## Concept 3 — CLI escalation ladder

Scrapling's CLI provides a clean `get → fetch → stealthy-fetch` escalation that
maps to our recon decision tree. Use it as a quick-test tool before writing a
full scraper.

```bash
# Step 1: Try plain HTTP (like our urllib path)
scrapling extract get "https://example.com" page.md

# Step 2: If empty or JS-rendered, try browser (needs scrapling[fetchers])
scrapling extract fetch "https://example.com" page.md --network-idle

# Step 3: If Cloudflare/anti-bot, try stealth (needs scrapling[fetchers])
scrapling extract stealthy-fetch "https://example.com" page.md --solve-cloudflare
```

**On the VM**: only `get` works (parser-only install). `fetch` and
`stealthy-fetch` need the full install with browsers.

**Output format trick**: change the file extension to control output.
- `.md` — converts HTML to Markdown (best for LLM consumption)
- `.html` — raw HTML
- `.txt` — clean text only
- `.json` — structured extraction (with CSS selectors)

```bash
# Extract specific content with CSS selector, output as markdown
scrapling extract get "https://blog.example.com" article.md -s "article"
```

**Done when**: you have identified which escalation rung succeeds, then write
the scraper using that rung's approach.

## Installation details

**Installed on this system (parser-only):**
```
pip install scrapling
# Packages: cssselect, orjson, scrapling, tld, w3lib
# Size: ~2MB, no browsers, no Playwright
```

**Full install (not on VM, available on Win PC or NAS):**
```
pip install "scrapling[all]"
scrapling install --force
# Adds: playwright, patchright, curl_cffi, browserforge, MCP server deps
# Downloads: Chromium browsers (~300MB)
# RAM per browser instance: 200-500MB
```

**Docker (NAS):**
```bash
docker pull pyd4vinci/scrapling
# All deps + browsers pre-installed
```

## MCP server

Scrapling includes an MCP server (`pip install scrapling[ai]`). This exposes
scraping tools to AI agents via the MCP protocol. Not installed on the VM. If
needed, run on the NAS Docker image and connect via MCP client.