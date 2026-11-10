# Search and fetch fallbacks (any provider)

The host's own tools stay the default: `web_search` and `web_extract`, or the donsetch
search/fetch tools when the user asked for them. This page says when a run may step up to
another search or page-reading tool, and how to judge one. It is written by **capability**, not
by vendor, because users connect different tools: a search API (Brave, SerpApi, Tavily,
Parallel, Keenable, Exa search …), a page reader (Firecrawl, Jina Reader, Litescrape,
Context.dev, ScrapingBee …), an MCP server, or the same providers reached through an API
marketplace. Treat each one by the slot it fills.

## The two slots

| Slot | What it must return | Use it when |
|---|---|---|
| **Page reader** | The page's own text (Markdown or plain text), not a summary written by a model, with a way to cap the size or save the output to a file | The default reader fails on the page, or a key claim needs exact wording |
| **Search provider** | Ranked results with URL, title, date and a text excerpt; ideally country, language, date-window and domain filters | The default search is thin after the refinement ladder, or the plan needs a filter it cannot express |

A tool that takes a question and returns its own written answer is a **research agent**, not
either slot. Use it only through its own procedure (for organisations,
`entity-research/references/organisation-evidence-exa.md`) and cite the pages it cites.

## When to step up

Step up for a **named reason**, never by habit:

| Trigger | Step up to | Ask the tool for |
|---|---|---|
| The default reader returns binary, an empty page or an error (many PDFs, script-built pages) | Page reader | Text or Markdown, size capped (for example a token limit) or saved to `<run_dir>/pages/` |
| A key claim's quote fails `check-quote` twice and the stored page text looks incomplete | Page reader | The same page, so the excerpt can be copied from the full text |
| `no_results` or `irrelevant` on the 2nd rung of the refinement ladder (§3a) | Search provider | The same frozen query, with the country or language set to the subject's |
| Source preference `primary`, and every result so far is secondary (trade press, blogs) | Search provider | A country-targeted query; a domain filter only for a domain already verified in earlier sources |
| A time window the default search cannot pin down | Search provider | A published-after or published-before filter |

**When not to step up.** Some pages are not text at all: a Tableau or Power BI dashboard, a
chart drawn in the browser, a download behind a sign-up form. A page reader gets only the
menus and headings. Search for the publisher's PDF or CSV release of the same figures instead;
if there is none, record a gap.

## Judging a tool you have not used before

Read its documentation or schema before the first paid call, and note the answers in the run
manifest:

1. **Raw text or a summary?** A reader that rewrites the page cannot support `check-quote`.
2. **Size control?** A full annual report can be 250,000 characters. Without a cap, save the
   output to a file and read it in parts.
3. **Filters?** Country, language, date window, domain allow-list.
4. **Billing:** per call, per page or per token; whether empty, failed or timed-out calls are
   billed.
5. **Data handling:** where queries and pages go, and whether the provider keeps them. Use only
   providers the user has chosen for this purpose.

## Cost, approval and data handling

- **Default tools first.** A fallback is used only after the default route has failed for the
  reason recorded.
- **Paid tools: one quote, one budget per run.** Quote the tool, the expected calls and the
  ceiling (for example "up to 20 page reads and 10 searches, at most US$0.50"), wait for the
  user's go-ahead, then work inside it. Never switch from a free tool to a paid one silently.
- **Budgets still apply.** A page read through a fallback counts against the §3b fetch budget
  (≤2 per round; ≤4 moderate, ≤6 complex), and a fallback search counts as one of the round's
  queries.
- **Query hygiene.** Research the public topic; keep private context (a client, a deal, the
  user's own relationship to the subject) out of every query and URL. Every new provider sees
  the query text.
- **Cite the page, never the tool.** The report's Sources list names the publisher and URL; the
  tool, run IDs and costs go in the run manifest and stats block.

## Feeding the evidence store

- Text from a page reader is registered with `register-source` as that page's text, with the
  page URL as the source (not the tool's URL), and saved to `<run_dir>/pages/<source_id>.txt`
  for `check-quote`.
- Excerpts from any search provider are snippets: at most `[SOURCED]`, never independent
  corroboration, until re-anchored to page text (§3b).
- Record which slot and tool produced each source in the run manifest, so the fetch can be
  repeated.

## Worked test (Nov 2026)

The same three public pages and two searches were run on four tools through an API marketplace,
for about US$0.016 in total (prices as listed that day; check before relying on them).

| Test | Built-in fetch | Reader A (Litescrape, ~US$0.00015 a page, size cap) | Reader B (Context.dev, ~US$0.002 a page, no cap) |
|---|---|---|---|
| A results PDF of about 135 pages | Failed: binary only | Full text; figures matched the document exactly | Full text, about 256,000 characters; had to be read from a file |
| A government index page (Japanese) | Fine | Exact table and links | Exact table and links |
| A statistics dashboard | No figures | Menus only | Menus only |

| Test | Search A (Keenable, ~US$0.004, date filter) | Search B (Parallel, ~US$0.001, country filter) |
|---|---|---|
| A national hotel-occupancy statistic (English and Japanese queries) | Dated results, mostly trade press | Every result a primary government release, with exact excerpts |

Lessons: the page reader earned its place on the PDF; the dashboard needed its published
release, not a better scraper; a country-targeted search found primary sources that a plain
search ranked below trade press.
