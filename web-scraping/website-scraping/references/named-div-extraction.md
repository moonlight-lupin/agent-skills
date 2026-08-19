# Server-rendered content in named div containers

A simpler case than JSON-LD or framework blobs: the data you need is plain text or HTML inside a `<div>` with a predictable ID, server-rendered (no JS needed to populate it). Common on older ASP.NET / PHP / Django sites that render content directly into the page.

## When this pattern applies

- Subtitle/caption pages where text is embedded in `<div id="subtitle-0">`, `<div id="subtitle-1">`
- Article pages on legacy CMSes that render body text into a named container
- Any page where "View Source" shows the content you need inside a div with a stable ID

## Extraction approach

### Regex (fast, but fragile with nested divs)

```python
import re, html as html_module

def extract_div_content(html: str, div_id: str) -> str | None:
    """Extract text content from a named div. CAUTION: breaks on nested divs."""
    pattern = rf'<div\s+id="{div_id}"[^>]*>(.*?)</div>'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return None
    content = match.group(1)
    content = re.sub(r'<[^>]+>', '', content)  # strip inner HTML tags
    content = html_module.unescape(content)
    return content.strip()
```

### BeautifulSoup (handles nested divs correctly)

```python
from bs4 import BeautifulSoup

def extract_div_content_bs(html: str, div_id: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    el = soup.find(id=div_id)
    return el.get_text(separator="\n", strip=True) if el else None
```

### Browser fallback (for edge cases)

When urllib times out or the regex misses (nested divs, dynamic content):

```javascript
// In browser_console:
(() => {
  const el = document.getElementById('subtitle-1');
  return el ? el.textContent.trim() : 'not found';
})()
```

Then save the returned text to a file via `write_file`.

## Key pitfalls

### 1. Nested divs break regex

`<div id="x">...<div>nested</div>...</div>` — non-greedy `.*?` stops at the first `</div>`, truncating content. This was observed on STEMI.tv where one page's subtitle-1 div contained 137K chars of content but the regex match only captured a fraction.

**Fix:** Use BeautifulSoup for pages with nested divs, or fall back to browser extraction.

### 2. Multiple language variants

Some sites serve multiple translations in the same page. STEMI.tv serves:
- `subtitle-0` = 繁中 (Traditional Chinese)
- `subtitle-1` = 简中 (Simplified Chinese)

Toggled via JavaScript `showSubtitleLink(this, 'subtitle-N')`. Both divs are in the static HTML — no JS needed to access either. Pick the one matching the user's language preference.

**Some pages only have one variant.** Auto-translated pages may only have `subtitle-0` with no `subtitle-1`. Always check both and handle the missing case.

### 3. Bulk fetch + browser fallback pattern

For 20+ pages of the same pattern:

1. **Batch urllib fetch** (fast): Loop through URLs with `urllib.request`, extract div content via regex. Expect 90%+ success rate.
2. **Identify failures**: Track which pages failed (timeout, regex miss, missing div).
3. **Browser fallback** (slow but reliable): For each failure, `browser_navigate` to the URL, then `browser_console` to extract via `document.getElementById(id).textContent`.
4. **Save results**: Write each extracted text to an individual `.md` file via `write_file`.

This hybrid pattern is 10x faster than browser-only for bulk, and resilient for edge cases. In practice: 21 of 23 pages succeeded via urllib in ~90s; 2 required browser fallback (one timeout, one nested div).

### 4. Extract listing URLs first via browser

When the listing page uses JavaScript onclick handlers or dynamic content rendering, extract the content page URLs programmatically:

```javascript
// In browser_console on the listing page:
(() => {
  const rows = document.querySelectorAll('table tbody tr, table tr');
  const results = [];
  rows.forEach(row => {
    const cells = row.querySelectorAll('td');
    if (cells.length >= 2) {
      const titleText = cells[0].textContent.trim();
      const subtitleLink = row.querySelector('a[href*="Subtitle"], a[href*="subtitle"]');
      if (subtitleLink) {
        results.push({ title: titleText, subtitleUrl: subtitleLink.href });
      }
    }
  });
  return JSON.stringify(results, null, 2);
})()
```

Then use the returned URLs for batch urllib fetching.

### 5. Content may be very long

Subtitle transcripts can be 15K-23K characters each. When extracting via `browser_console`, the result is returned as a string. For very long content, the browser console return may be truncated by the runtime. In that case, use `write_file` directly from `execute_code` or write the content in chunks.

## Real-world example: STEMI.tv sermon subtitles

**Task**: Extract 23 sermon subtitle pages from stemi.tv into individual Markdown files.

**Approach**:
1. Navigate to listing page `https://stemi.tv/Home/ShowMovies/5` via `browser_navigate`
2. Extract all 23 subtitle URLs via `browser_console` (JavaScript DOM query)
3. Batch-fetch each subtitle page via `urllib.request` in `execute_code` Python loop
4. Extract `subtitle-1` (Simplified Chinese) div content via regex
5. For 2 failures: `browser_navigate` + `browser_console` to get text, then `write_file`
6. Save each as `NN_第NN讲_标题.md` with header (title + source URL + separator)
7. Verify all 23 files exist with `search_files`

**Result**: 23 subtitle files, ~350K total characters, in under 3 minutes.