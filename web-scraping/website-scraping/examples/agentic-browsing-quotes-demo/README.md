# Worked example — agentic browsing against dependent dropdowns

A real, runnable demonstration of the **Webwright workspace contract** described in
[`../../references/agentic-browsing.md`](../../references/agentic-browsing.md), executed by
hand (the agent-plugin path, where the agent itself runs the loop — no API key).

## The fiddly bit

Target: `http://quotes.toscrape.com/search.aspx` (a purpose-built scraping sandbox).
The two dropdowns are **dependent**: selecting an **Author** fires an AJAX call that
repopulates the **Tag** dropdown with only that author's tags. So you can't just GET a URL
— you have to drive the form in order, waiting for the second control to populate before
you can touch it. That "second control depends on the first" shape is exactly when an
agentic browser framework earns its keep over a hand-script.

## What's here

| File | Role in the contract |
|---|---|
| `plan.md` | The 4 critical points (CP1–CP4) the run must satisfy. |
| `explore.py` | Exploration script — discovered that the tag dropdown goes from 1 option → 24 after the author is picked. |
| `final_runs/run_1/final_script.py` | The instrumented final artifact: a screenshot + log line per critical point, final datum printed to the log. |
| `final_runs/run_1/final_script_log.txt` | The action log + `FINAL_RESPONSE`. |
| `final_runs/run_1/records.jsonl` | Clean output in this skill's JSONL convention (one record, with the filter provenance). |
| `final_runs/run_1/screenshots/` | Per-CP evidence used for self-verification. |
| `screenshots/` | Exploration screenshots. |

## The key technique

The dependent dropdown is handled by **polling for the option to exist**, not a fixed
sleep — consistent with this skill's anti-pattern guidance:

```python
await page.wait_for_function(
    "() => Array.from(document.querySelector('#tag').options)"
    f".some(o => o.value === {json.dumps(TAG)})",
    timeout=8000,
)
```

## Re-run it

```bash
# Chromium is fine here (this sandbox doesn't TLS-fingerprint); the Webwright
# plugin would default to Firefox for Akamai-fronted sites.
python final_runs/run_1/final_script.py
```

Expected final datum (one quote for author=Albert Einstein, tag=deep-thoughts):

> "The world as we have created it is a process of our thinking. It cannot be changed
> without changing our thinking." — Albert Einstein

## The takeaway

The agent earned its keep on the **navigation** (ordered form-driving + the AJAX wait), not
the parse — the extraction itself was a one-line `page.evaluate` over `.quote` cards. That's
the dividing line for reaching for Webwright at all: use it when the *path to the data* is
the hard part, then hand the rendered page to the ordinary extraction recipes.
