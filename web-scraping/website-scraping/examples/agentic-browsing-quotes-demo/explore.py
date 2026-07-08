"""Webwright-style exploration: discover the dependent-dropdown structure."""
import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright

WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "."))
SHOTS = WORKSPACE / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

START = "http://quotes.toscrape.com/search.aspx"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 1800})
        page = await ctx.new_page()

        await page.goto(START, wait_until="domcontentloaded")
        await page.screenshot(path=str(SHOTS / "explore_1_start.png"))
        print("URL:", page.url)
        print("TITLE:", await page.title())

        # What selects exist and what are their options?
        info = await page.evaluate(
            """() => {
                const out = {};
                document.querySelectorAll('select').forEach(sel => {
                    out[sel.id || sel.name] = {
                        name: sel.name,
                        options: Array.from(sel.options).slice(0, 6).map(o => o.value),
                        count: sel.options.length,
                    };
                });
                return out;
            }"""
        )
        print("SELECTS (before author pick):", info)

        # Pick the author and watch the tag dropdown change via AJAX
        await page.select_option("#author", "Albert Einstein")
        # Tag dropdown is repopulated by an AJAX call — wait for options to appear
        await page.wait_for_function(
            "() => document.querySelector('#tag') && document.querySelector('#tag').options.length > 1",
            timeout=8000,
        )
        tags = await page.evaluate(
            "() => Array.from(document.querySelector('#tag').options).map(o => o.value)"
        )
        print("TAGS for Albert Einstein:", tags)
        await page.screenshot(path=str(SHOTS / "explore_2_after_author.png"))

        await browser.close()


asyncio.run(main())
