# Agentic browsing — when the blocker is navigation, not parsing

Everything else in this skill assumes the hard part is *parsing* — once you can see the
page, the data is there for the taking. This file is about the other failure mode: the
data is trivial to read, but *getting to it* requires a multi-step interactive sequence
that's painful to hand-script. Log in, set four filters spread across three screens,
dismiss two modals, pick a tag from a dropdown that only populates after you choose an
author, click "show more" eleven times — *then* the listings appear. Hand-writing and
debugging that Playwright choreography is where scraping projects quietly burn a day.

For that specific case, an **agentic browser framework** can write the navigation script
for you. The current best-in-class is Microsoft's **Webwright**
(https://github.com/microsoft/Webwright, first public release 2026-05-04).

> The notes below were **smoke-tested first-hand** (May 2026) against a deliberately fiddly
> target — the dependent Author→Tag dropdowns on `quotes.toscrape.com/search.aspx`, where
> selecting an author fires an AJAX call that repopulates the tag dropdown. The Webwright
> *workspace contract* (plan → explore → instrumented `final_script.py` → self-verify) was
> run by hand and completed the task end-to-end. Corrections from that run are folded in.
> The full runnable artifact set lives in
> [`../examples/agentic-browsing-quotes-demo/`](../examples/agentic-browsing-quotes-demo/).

## What Webwright is

A browser *agent* framework — tagline *"Turn Your Coding Models to Be State-of-the-art
Browser Agents."* Instead of predicting one click at a time, it puts a coding model in a
loop where it **writes, runs, and debugs Playwright scripts** against a disposable
browser, keeping the verified script as the durable artifact. The core loop is ~450 lines;
runtime deps are just `httpx`, `pydantic`, `pyyaml`, `jinja2`, `typer`, `rich`, and
`playwright`. It reports strong results on long-horizon *interactive* web benchmarks;
see its own repo for current numbers.

## When to reach for it — and when NOT to

**This is the single most important section.** Webwright's *own* documentation says it is
*"less suited for pure bulk data extraction or scraping, which requires less reasoning and
benefits less from disposable browser sessions and code composition."* Take that at face
value. It is not a faster scraper — it's a navigation-task solver.

Use it when **all** of these hold:

- You've already lost the recon decision tree — the data is genuinely client-rendered and
  behind interaction (Strategy 5 territory, see `recon.md`).
- The interaction is **multi-step and stateful** — not "click accept-cookies once" (the
  consent-overlay patterns in `playwright.md` already cover that), but a real sequence with
  branching, waits, and state that depends on earlier steps (e.g. a control that only
  populates after a prior selection).
- The sequence is **fiddly enough that hand-scripting it is the bottleneck**, not the
  parsing afterward.
- You want a **reusable, inspectable script** out the other end — Webwright's output is a
  `final_script.py` you can lift, version, and run yourself without the agent in the loop.

Do **not** reach for it when:

- A lighter strategy works. If `urllib` + JSON-LD gets the data, an LLM-driven browser
  agent is absurd overkill — slower, costs API tokens per run, and far more fragile. The
  whole thesis of this skill is *lightest tool that works*; Webwright is the heaviest tool
  in the box.
- The job is **bulk extraction over many similar pages**. Once you have a URL list and the
  pages are uniform, a plain Playwright loop (or, better, a reversed API) wins on speed,
  cost, and determinism. Webwright shines on *one gnarly path*, not *ten thousand uniform
  fetches*.
- You need **determinism per run**. An agent loop can take different paths on different
  runs. For monitoring/diffing, you want the *frozen* script, not the agent regenerating it.

**The pragmatic pattern**: use Webwright *once* to discover and harden the navigation
script for the gnarly path, then lift its `final_script.py` into your own scraper and run
*that* deterministically for the actual harvest. You pay the agent cost once, not per page.

## Two ways to run it — pick by where you are

Webwright ships **two surfaces**, and the difference decides whether you need an API key at
all. This was the biggest correction from the smoke test.

### Path A — the agent-plugin surface (NO API key needed)

Webwright ships a plugin for agentic coding harnesses (it provides both a Claude Code and a
Codex manifest): the skill lives at `skills/webwright/` with slash commands
`/webwright:run <task>` (one-shot) and `/webwright:craft <task>` (parameterized reusable
CLI). **On this path the agent itself runs the loop** — the shipped `SKILL.md` explicitly
replaces Webwright's externally-modelled `image_qa` and `self_reflection` tools with the
agent's *own* native abilities (read PNGs, self-verify against `plan.md` by reasoning). So
**no model API key is required** on this path — confirmed first-hand. The only setup is a
browser:

```bash
playwright install firefox
```

**Firefox, not Chromium** — the skill defaults to Playwright Firefox because some
Akamai-fronted sites (e.g. cars.com) reject Playwright *Chromium* with
`ERR_HTTP2_PROTOCOL_ERROR` from TLS/H2 fingerprinting, but load cleanly under Firefox. For
sites that don't fingerprint TLS (most), Chromium is fine and you can skip the Firefox
download.

The **workspace contract** is the whole methodology, and you can follow it by hand without
even installing the package — it's just discipline:

1. **plan.md** — break the task into a numbered checklist of *critical points* (every
   filter, selection, datum). Each must be independently verifiable from a screenshot or
   log line.
2. **Explore** — scratch Playwright scripts to find stable selectors and confirm controls
   exist. Print ARIA snapshots; `Read` the saved PNGs to inspect UI state.
3. **Author `final_runs/run_<id>/final_script.py`** — instrument it: reset
   `final_script_log.txt`, write a `step <n> action: …` line per constraint-relevant
   interaction, save a screenshot per critical point, print the final datum at the end.
4. **Run** it once inside that run folder.
5. **Self-verify** — walk `plan.md`, `Read` each cited screenshot, tick a CP only when the
   evidence is unambiguous. On failure, fix the script and re-run in `run_<id+1>/`.

This contract is *exactly* compatible with this skill's own conventions — the screenshots
and action log are the "verify against ground truth" step (SKILL.md §6), and the run folder
is the natural home for the `records.jsonl` + raw-payload output (SKILL.md §5, §7).

### Path B — the standalone CLI harness (NEEDS an API key)

This is the original benchmark harness, where an external model drives the loop. Here you
*do* need a backend key. It's a separate repo, not a pip-installable library:

```bash
git clone https://github.com/microsoft/Webwright && cd Webwright
pip install -e .
playwright install chromium          # CLI harness default is Chromium
export ANTHROPIC_API_KEY=...         # or OPENAI_API_KEY / OPENROUTER_API_KEY
```

Run via the installed `webwright` console script (or `python -m webwright.run.cli`).
Configs **stack** from `src/webwright/config/` via repeated `-c` flags — a base plus a
model modifier plus optional extras:

```bash
webwright \
    -c base.yaml -c model_claude.yaml \
    -t "Select author 'Albert Einstein', then his 'deep-thoughts' tag, search, \
        and list the resulting quote" \
    --start-url http://quotes.toscrape.com/search.aspx \
    --task-id quotes_demo \
    -o outputs/default
```

Real config files present in the repo: `base.yaml`; model modifiers `model_openai.yaml`,
`model_claude.yaml`, `model_openrouter.yaml`; `local_browser.yaml` vs
`persistent_browser.yaml`; `task_showcase.yaml`; `crafted_cli.yaml`. Browser mode is set in
config — `local` (a local Playwright launch, no extra creds) or `browserbase` (a
Browserbase cloud session, needs `BROWSERBASE_API_KEY` + `BROWSERBASE_PROJECT_ID`).

Each run produces a durable workspace: exploratory scripts, an action log, screenshots per
step, and the verified `final_script.py`. That script is the thing you keep.

**Task2UI mode** (add `-c task_showcase.yaml`) additionally renders the run into an HTML
dashboard (`task.json` + `report.json`), viewable via the bundled Flask app at
`assets/task_showcase/app.py` on `http://127.0.0.1:5005`. Handy for eyeballing a tricky
multi-step run, irrelevant for headless harvesting.

## How it slots into this skill's workflow

It doesn't replace any of the five extraction strategies in `recon.md` — it sits *beside*
Strategy 5 as the tool you use when the obstacle is the *path to the page*, after which the
extraction recipes in `extraction.md` take over exactly as before. Webwright gets you a
rendered, navigated page; pulling clean records out of it is still your job, and the
lightest-tool-that-works discipline still applies to *that* half. In the smoke test the
navigated page yielded its data via a one-line `page.evaluate` over `.quote` cards and went
straight to `records.jsonl` — the agent earned its keep on the *navigation*, not the parse.

It also overlaps the bottom of the anti-bot ladder (`anti-bot.md`, Tier 6): because it
drives a real browser through a real session, it inherits whatever the browser establishes
(cookies, solved challenges). That makes it a reasonable option for "the data is reachable
in a logged-in browser but the path is too fiddly to script by hand" — but it is *not* a
bot-detection bypass. If a site blocks headless Chromium, it blocks Webwright too (switching
to the Firefox engine helps only with TLS/H2 *fingerprinting*, not with real WAF
challenges); apply the Tier 0–5 countermeasures first.
