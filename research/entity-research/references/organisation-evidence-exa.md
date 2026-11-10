# Organisation evidence via the Exa Agent API (optional, paid)

A hosted web-research agent that collects **public facts about organisations** into structured
rows, each fact with a source URL and date. Use it when several organisations need the same few
facts — size, assets or revenue, mandate or business lines, sector exposure, recent commitments
or announcements — and researching each one by hand would be slow. It **adds to** the research
lenses and to a deep-research pass; it replaces neither, and it is **never a screening tool**
(sanctions-list and PEP signals stay on `screen_lists()` and official checks).

## When to use it, and when not

| Use it for | Never use it for |
|---|---|
| The identity & background lens for **organisations**: size, assets, mandate, sector exposure, recent commitments or announcements | **People** — no officers, contacts, emails or phones. The API can enrich contacts; keep that off |
| A batch of up to ~10 organisations needing the same fields | Sanctions, PEP or watchlist conclusions |
| Structured, cited facts you will spot-check and label | Any task whose wording would reveal your relationship to the organisations (a deal, a client, a target) |

## The API

- `POST https://api.exa.ai/agent/runs` with header `x-api-key: $EXA_API_KEY`; poll
  `GET https://api.exa.ai/agent/runs/{id}` until `status` is `completed`, `failed` or
  `cancelled`. (`POST /agent/runs/{id}/cancel` cancels; usage accrued before a cancel or stop is
  billed.)
- Body: `query` (the task), `effort`, `input.data` (one object per organisation, e.g.
  `{"organisation": "Northwind Holdings"}`), `outputSchema` (JSON Schema for the rows, returned
  validated in `output.structured`), `budget`.
- **Effort and price** (listed 10 Nov 2026 — confirm on Exa's pricing page): flat-priced efforts
  `minimal` 12, `low` 25, `medium` 100, `high` 500, `xhigh` 1,000 credits (1 credit = US$0.001),
  so `medium` is **US$0.10 per run** — for the whole batch, not per row. `auto` and `ultra` are
  metered.
- **`budget.maxCostDollars` accepts US$1 to US$100 — you cannot set less than US$1.** On a flat
  effort it caps **contact enrichment** (emails and phones) on top of the flat price. Send
  `{"maxCostDollars": 1}` explicitly; with no contact fields in the task or schema nothing is
  enriched and the bill is the flat price. Quote it as "expected US$0.10, ceiling US$1.10".
- The response carries `output.grounding` (per-field citations with a confidence),
  `stopReason` and `usage` (`searches`, `emails`, `phoneNumbers`). **Check that `emails` and
  `phoneNumbers` are 0.**

A minimal stdlib call (Python):

```python
import json, os, time, urllib.request
KEY = os.environ["EXA_API_KEY"]                     # never print or commit it
def call(method, path, body=None):
    req = urllib.request.Request("https://api.exa.ai" + path, method=method,
                                 data=json.dumps(body).encode() if body else None,
                                 headers={"x-api-key": KEY, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))
run = call("POST", "/agent/runs", {"query": TASK, "effort": "medium",
                                   "input": {"data": [{"organisation": n} for n in NAMES]},
                                   "outputSchema": SCHEMA, "budget": {"maxCostDollars": 1}})
while run.get("status") not in ("completed", "failed", "cancelled"):
    time.sleep(5); run = call("GET", f"/agent/runs/{run['id']}")
json.dump(run, open("exa_run.json", "w"), indent=2)  # keep the raw run as the working record
```

**Live test, 10 Nov 2026** (three listed insurers, `medium`, organisation facts only):
US$0.10 billed, ~75 seconds, 12 searches, 0 emails. Every field was cited. Two figures
spot-checked against the companies' own documents matched exactly. Weaknesses seen: it used an
older reporting period where a later one had probably been published; a few statements were its
own inference rather than the source's; trade-press articles were mixed with primary documents.

## The task wording

State the organisations, the fields and the evidence standard — nothing about why you are asking.

```
For each organisation, find [the fields]. Cite a source URL and date for every fact; prefer the
organisation's own annual report, results or website; use the most recent reporting period
available and state it; leave a field empty if no source states it.
```

- **Bare organisation names** in `input.data`, plus neutral disambiguators (country, website).
- No people fields in the `outputSchema`.

## Cost and confirmation

Quote before running: "Exa organisation evidence × [n] runs at US$0.10 (ceiling US$1.10 each)",
with the organisation names and the exact task wording, and wait for the user's go-ahead. One
run can cover a batch, so prefer one run for several organisations over one run each.

## Using the results

1. **Every fact keeps its cited source**, and the dossier cites that source — the annual report,
   the filing, the article — not the research agent. Keep the raw run (`exa_run.json`) as the
   working record.
2. **Label each fact** — `[VERIFIED]` once you have opened the primary source and matched it;
   `[SOURCED]` when the citation is a primary document you have not opened; `[REASONED]` for the
   agent's own inferences (anything the cited page does not say). The API's "high" confidence is
   not a label.
3. **Spot-check at least one figure per organisation** against the primary source, and **check
   the reporting period** — look for a later annual report or results release.
4. **Trade press** is a lead; prefer the organisation's own announcement where one exists.
5. If the API is unavailable, unfunded or errors, say so in one line and continue with the
   lenses alone. Do not retry in a loop.
