"""
Recon helper for the website-scraping skill.
============================================

Given a URL, fetch the page (first with plain HTTP, then optionally with
Playwright) and report which extraction strategies look viable. Run this
FIRST on any new site before writing a scraper — it tells you which of
the five strategies (static / JSON-LD / framework-blob / API / browser)
you should be using.

Usage:
    python recon.py <url>
    python recon.py <url> --playwright          # also try browser fetch
    python recon.py <url> --headers             # dump response headers too
    python recon.py <url> --save raw.html       # save the HTML body

Exit codes:
    0 = recon completed (regardless of what we found)
    1 = could not fetch the URL at all

The output is a short report identifying:
    - HTTP fetch result (status, size, content-type)
    - Whether the page looks Cloudflare-challenged
    - Presence of JSON-LD blocks (and their @types)
    - Presence of framework hydration blobs (Next.js, Nuxt, Drupal, etc.)
    - Whether the body has enough text to suggest static rendering
    - Suggested next-step extraction strategy

Designed to be readable — copy-paste the output into a scratch note when
you're starting a new operator.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', re.DOTALL,
)
NUXT_RE = re.compile(r'window\.__NUXT__\s*=\s*', re.IGNORECASE)
DRUPAL_RE = re.compile(
    r'<script[^>]+data-drupal-selector=["\']drupal-settings-json["\']',
    re.IGNORECASE,
)
INITIAL_STATE_RE = re.compile(
    r'window\.__(?:INITIAL_STATE|PRELOADED_STATE)__\s*=', re.IGNORECASE,
)
CLOUDFLARE_TITLES = (
    "just a moment",
    "performing security verification",
    "checking your browser",
    "attention required",
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------

def fetch_http(url: str, *, timeout: float = 30.0) -> dict:
    """Fetch with stdlib urllib + a real browser UA."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return {
                "ok": True,
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": body,
                "content_type": resp.headers.get("Content-Type", ""),
                "url_final": resp.url,
            }
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "status": e.code,
            "headers": dict(e.headers) if e.headers else {},
            "body": e.read() if hasattr(e, "read") else b"",
            "content_type": (e.headers.get("Content-Type", "") if e.headers else ""),
            "url_final": url,
            "error": f"HTTPError {e.code}: {e.reason}",
        }
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "error": str(e)}


def fetch_playwright(url: str) -> dict:
    """Fetch with Playwright + stealth (if installed). Skipped if not available."""
    try:
        from playwright.sync_api import sync_playwright  # noqa
    except ImportError:
        return {"ok": False, "error": "playwright not installed (pip install playwright && playwright install chromium)"}
    try:
        from playwright_stealth import Stealth  # noqa
        have_stealth = True
    except ImportError:
        have_stealth = False

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            if have_stealth:
                from playwright_stealth import Stealth
                Stealth().apply_stealth_sync(browser)
            ctx = browser.new_context(
                user_agent=UA, locale="en-GB",
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(2000)  # let initial XHRs land
            html = page.content()
            title = page.title()
            return {"ok": True, "body": html.encode("utf-8"), "title": title,
                    "url_final": page.url, "stealth": have_stealth}
        except Exception as e:
            return {"ok": False, "error": f"playwright: {type(e).__name__}: {e}"}
        finally:
            browser.close()


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyse(body: bytes, *, label: str) -> dict:
    """Look for extraction-strategy signatures in an HTML body."""
    try:
        html = body.decode("utf-8", errors="replace")
    except Exception:
        return {"label": label, "decode_error": True}

    title_m = TITLE_RE.search(html)
    title = (title_m.group(1).strip() if title_m else "").lower()
    cf_challenged = any(s in title for s in CLOUDFLARE_TITLES)

    # JSON-LD
    jsonld_types: list[str] = []
    for m in JSONLD_RE.finditer(html):
        try:
            blob = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        items = blob if isinstance(blob, list) else (blob.get("@graph", [blob]) if isinstance(blob, dict) else [])
        for item in items:
            if isinstance(item, dict):
                t = item.get("@type")
                if isinstance(t, list):
                    jsonld_types.extend(t)
                elif t:
                    jsonld_types.append(t)

    # Framework signatures
    has_next = bool(NEXT_DATA_RE.search(html))
    has_nuxt = bool(NUXT_RE.search(html))
    has_drupal = bool(DRUPAL_RE.search(html))
    has_initial_state = bool(INITIAL_STATE_RE.search(html))

    # Text-density heuristic for "static enough to scrape from HTML"
    # Strip tags crudely and measure visible text length
    text_only = re.sub(r"<script.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text_only = re.sub(r"<style.*?</style>", "", text_only, flags=re.DOTALL | re.IGNORECASE)
    text_only = re.sub(r"<[^>]+>", " ", text_only)
    text_only = re.sub(r"\s+", " ", text_only).strip()
    text_len = len(text_only)

    return {
        "label": label,
        "size_bytes": len(body),
        "title": title_m.group(1).strip() if title_m else "(no title)",
        "cf_challenged": cf_challenged,
        "jsonld_count": len(jsonld_types),
        "jsonld_types": sorted(set(jsonld_types)),
        "next_data": has_next,
        "nuxt": has_nuxt,
        "drupal": has_drupal,
        "initial_state": has_initial_state,
        "visible_text_chars": text_len,
    }


# JSON-LD types that are almost always metadata-only (no useful payload data).
# When these are the ONLY @types present, JSON-LD is unlikely to carry your
# target fields and you should look at framework blobs / static HTML instead.
_METADATA_ONLY_TYPES = {
    "WebPage", "WebSite", "Organization", "BreadcrumbList", "SearchAction",
    "ImageObject", "SiteNavigationElement",
}


def suggest_strategy(analysis: dict) -> str:
    """Recommend viable strategies in priority order.

    Returns a multi-line string listing every signal that fired, so the
    user can pick the right one for their target field. Reporting one
    suggestion is misleading on sites where JSON-LD has only metadata
    (LocalBusiness, WebPage) but the actual data is in a framework blob.
    """
    if analysis.get("cf_challenged"):
        return (
            "Cloudflare challenge detected — apply stealth + fresh-context-per-call "
            "(see references/anti-bot.md). Re-run recon after stealth to see what's "
            "underneath."
        )

    suggestions: list[str] = []

    if analysis["jsonld_count"] > 0:
        types = analysis["jsonld_types"]
        metadata_only = all(t in _METADATA_ONLY_TYPES for t in types)
        if metadata_only:
            suggestions.append(
                f"Strategy 2 (JSON-LD) — {analysis['jsonld_count']} block(s): "
                f"{', '.join(types)}. ⚠ These are metadata-only types — useful for "
                f"company name / page identity but unlikely to carry product/listing "
                f"data. Check the framework blobs below for the real payload."
            )
        else:
            suggestions.append(
                f"Strategy 2 (JSON-LD) — {analysis['jsonld_count']} block(s): "
                f"{', '.join(types)}. Likely carries your target fields if any are "
                f"product/price/listing-shaped. Try this first."
            )

    if analysis["next_data"]:
        suggestions.append(
            "Strategy 3 (framework blob) — Next.js __NEXT_DATA__. Parse the JSON; "
            "data usually under props.pageProps."
        )
    if analysis["nuxt"]:
        suggestions.append(
            "Strategy 3 (framework blob) — Nuxt.js __NUXT__. Parse the assignment."
        )
    if analysis["drupal"]:
        suggestions.append(
            "Strategy 3 (framework blob) — Drupal settings JSON. Often rich on Drupal "
            "sites (the full page state lives here)."
        )
    if analysis["initial_state"]:
        suggestions.append(
            "Strategy 3 (framework blob) — Redux/Vuex __INITIAL_STATE__. Parse the "
            "assignment."
        )

    if analysis["visible_text_chars"] > 5000:
        suggestions.append(
            f"Strategy 1 (static HTML) — {analysis['visible_text_chars']} visible chars, "
            f"looks server-rendered. Check page source for your target fields before "
            f"committing."
        )
    elif not suggestions:
        # Sparse HTML and nothing else fired
        suggestions.append(
            f"Strategy 4/5 — sparse HTML ({analysis['visible_text_chars']} visible chars), "
            f"likely client-rendered. Check DevTools → Network for an XHR/fetch endpoint "
            f"(Strategy 4). If none, fall back to Playwright (Strategy 5)."
        )

    if len(suggestions) == 1:
        return suggestions[0]
    return "Multiple viable strategies — pick by which one carries your target field:\n    " + \
           "\n    ".join(f"- {s}" for s in suggestions)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(*, http: dict, pw: dict | None, args) -> None:
    print(f"\n=== Recon for {args.url} ===\n")

    # HTTP fetch
    print("--- HTTP (urllib) ---")
    if not http.get("ok"):
        print(f"  ✗ fetch failed: {http.get('error') or 'status ' + str(http.get('status'))}")
        if http.get("status"):
            print(f"  status: {http['status']}")
        if http.get("body"):
            preview = http["body"][:200].decode("utf-8", errors="replace")
            print(f"  body preview: {preview!r}")
    else:
        print(f"  ✓ {http['status']} {http['content_type']}")
        print(f"  url final: {http['url_final']}")
        print(f"  size: {len(http['body'])} bytes")
        if args.headers:
            print("  headers:")
            for k, v in http["headers"].items():
                print(f"    {k}: {v}")

    if http.get("ok") or http.get("body"):
        a = analyse(http.get("body", b""), label="http")
        print(f"  title: {a['title']!r}")
        if a["cf_challenged"]:
            print(f"  ⚠ Cloudflare interstitial in title")
        print(f"  JSON-LD: {a['jsonld_count']} block(s), types={a['jsonld_types']}")
        print(f"  framework blobs: "
              f"next={a['next_data']} nuxt={a['nuxt']} drupal={a['drupal']} "
              f"initial_state={a['initial_state']}")
        print(f"  visible text: {a['visible_text_chars']} chars")
        print()
        print(f"  → {suggest_strategy(a)}")
        if args.save and http.get("body"):
            Path(args.save).write_bytes(http["body"])
            print(f"  saved body to {args.save}")

    # Playwright fetch (optional)
    if pw is not None:
        print("\n--- Playwright (headless + stealth if available) ---")
        if not pw.get("ok"):
            print(f"  ✗ {pw.get('error')}")
        else:
            print(f"  ✓ rendered, url={pw.get('url_final')}")
            print(f"  title: {pw.get('title')!r}")
            print(f"  stealth applied: {pw.get('stealth')}")
            a = analyse(pw["body"], label="playwright")
            if a["cf_challenged"]:
                print(f"  ⚠ Cloudflare interstitial in title — stealth alone isn't enough; try fresh-context-per-call")
            print(f"  JSON-LD: {a['jsonld_count']} block(s), types={a['jsonld_types']}")
            print(f"  framework blobs: "
                  f"next={a['next_data']} nuxt={a['nuxt']} drupal={a['drupal']} "
                  f"initial_state={a['initial_state']}")
            print(f"  visible text: {a['visible_text_chars']} chars (vs HTTP: see above)")
            print()
            print(f"  → {suggest_strategy(a)}")

    print()


def main():
    ap = argparse.ArgumentParser(description="Recon a URL for scraping strategy.")
    ap.add_argument("url", help="The URL to probe")
    ap.add_argument("--playwright", action="store_true",
                    help="Also fetch with Playwright (slower; tells you whether JS render adds anything)")
    ap.add_argument("--headers", action="store_true",
                    help="Dump response headers from the HTTP fetch")
    ap.add_argument("--save", metavar="PATH",
                    help="Save the HTTP-fetched body to this path for further inspection")
    args = ap.parse_args()

    http = fetch_http(args.url)
    pw = fetch_playwright(args.url) if args.playwright else None

    print_report(http=http, pw=pw, args=args)
    sys.exit(0 if (http.get("ok") or (pw and pw.get("ok"))) else 1)


if __name__ == "__main__":
    main()
