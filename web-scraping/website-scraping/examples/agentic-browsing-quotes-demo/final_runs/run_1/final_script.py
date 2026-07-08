"""Webwright-contract final script: dependent-dropdown filter + extract.

Task: on quotes.toscrape.com/search.aspx, select author "Albert Einstein",
select tag "deep-thoughts" (AJAX-populated after the author pick), search,
and extract the resulting quote(s).
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright

RUN_DIR = Path(__file__).parent
SHOTS = RUN_DIR / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)
LOG = RUN_DIR / "final_script_log.txt"
LOG.write_text("")  # reset at start of clean run

START = "http://quotes.toscrape.com/search.aspx"
AUTHOR = "Albert Einstein"
TAG = "deep-thoughts"


def log(step: int, msg: str) -> None:
    line = f"step {step} action: {msg}\n"
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line)
    print(line, end="")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await ctx.new_page()

        await page.goto(START, wait_until="domcontentloaded")
        log(1, "opened search.aspx")

        # CP1 — select the author
        await page.select_option("#author", AUTHOR)
        await page.screenshot(path=str(SHOTS / "final_execution_1_author_selected.png"))
        log(2, f"selected author = {AUTHOR!r} (CP1)")

        # CP2 — wait for the AJAX-repopulated tag dropdown, then select the tag.
        # Poll for the option to actually exist rather than a fixed sleep.
        await page.wait_for_function(
            "() => Array.from(document.querySelector('#tag').options)"
            f".some(o => o.value === {json.dumps(TAG)})",
            timeout=8000,
        )
        await page.select_option("#tag", TAG)
        await page.screenshot(path=str(SHOTS / "final_execution_2_tag_selected.png"))
        log(3, f"tag dropdown repopulated via AJAX; selected tag = {TAG!r} (CP2)")

        # CP3 — submit the search and wait for result cards
        await page.click("input[value='Search']")
        await page.wait_for_selector(".quote", timeout=8000)
        await page.screenshot(path=str(SHOTS / "final_execution_3_results.png"))
        n = await page.locator(".quote").count()
        log(4, f"submitted search; {n} result quote(s) displayed (CP3)")

        # CP4 — extract the final datum
        quotes = await page.evaluate(
            """() => Array.from(document.querySelectorAll('.quote')).map(q => ({
                text: q.querySelector('.content')?.textContent?.trim(),
                author: q.querySelector('.author')?.textContent?.trim(),
                tags: Array.from(q.querySelectorAll('.tag')).map(t => t.textContent.trim()),
            }))"""
        )
        with LOG.open("a", encoding="utf-8") as f:
            f.write("\nFINAL_RESPONSE:\n")
            for i, q in enumerate(quotes, 1):
                f.write(f"  {i}. {q['text']}  — {q['author']}  tags={q['tags']}\n")
        print(f"\nExtracted {len(quotes)} quote(s) for ({AUTHOR}, {TAG}).")

        # Also drop clean JSONL next to the run, mirroring the scraping skill's
        # output convention.
        with (RUN_DIR / "records.jsonl").open("w", encoding="utf-8") as f:
            for q in quotes:
                f.write(json.dumps({**q, "filter_author": AUTHOR, "filter_tag": TAG}) + "\n")

        await browser.close()


asyncio.run(main())
