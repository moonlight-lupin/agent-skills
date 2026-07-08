---
name: people-enrichment
description: >
  Enrich and search People Data Labs (PDL) Person and Company data, writing
  results to .xlsx. Five operations: enrich named PEOPLE into a profile,
  employment history and LinkedIn URL; IDENTIFY an ambiguous person as several
  scored candidates; SEARCH people by criteria (company, title, location);
  enrich COMPANIES into firmographics (industry, size, employees, HQ, founded,
  LinkedIn); and SEARCH companies by criteria. Use when the user has a list of
  names or companies and wants their job, employer, work history, LinkedIn URLs
  or company profiles looked up, or wants to find people or companies matching
  criteria. Trigger on phrases like "enrich these contacts", "find their
  LinkedIn", "look up these people", "who works at X", "find directors at Y",
  "enrich these companies", or "get firmographics for". Do not scrape LinkedIn
  directly — this uses a licensed data aggregator (PDL) instead, for legal and
  reliability reasons.
version: 1.0.1
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
---

# People Enrichment & Search (People Data Labs)

One script, `scripts/enrich.py`, with five subcommands over PDL's Person and Company datasets. All share the same API-key handling, the boolean-PII contact logic, status flags, `.xlsx` styling, and a `--dry-run` preflight mode.

| Subcommand | Input | Output | Billing |
| --- | --- | --- | --- |
| `person-enrich` | list of named people | profile + work history | 1 credit / match |
| `person-identify` | list of people (ambiguous) | several scored candidates each | per PDL identify terms |
| `person-search` | criteria flags | a list of matching people | 1 credit / record returned |
| `company-enrich` | list of companies | firmographics | 1 credit / match |
| `company-search` | criteria flags | a list of matching companies | 1 credit / record returned |

The two *search* commands return data per *result*, so cost scales with `--size`. Always state the rough cost before a large search and keep `--size` modest unless the user asks for more (max 100 per request).

## Scope and routing

Use this skill when the user wants PDL person/company enrichment or search for a legitimate, proportionate purpose. Do **not** use it to scrape LinkedIn directly, to compile an intrusive profile, or where a host environment mandates a different data provider.

## Why People Data Labs, not a LinkedIn scraper

Scraping LinkedIn is fragile and legally risky. This skill uses PDL as a licensed aggregator rather than live LinkedIn scraping. If the user insists on live scraping, explain the trade-off rather than building a scraper.

## The API key

`scripts/enrich.py` needs a PDL key, resolved at runtime in this order: `PDL_API_KEY` env var → `.env` in the cwd → `.env` next to the script. **The key must never be written into this skill or any script.** If absent, live commands exit with instructions. `--dry-run` and `--self-test` do not require a key.

Create the `.env` only locally:

```bash
echo 'PDL_API_KEY=their_key_here' > .env
```

Treat `.env` as a secret: don't print, commit, or upload it. `--self-test` runs offline (canned data, no key) and writes sample people + company sheets so the user can see the output format before spending credits.

## Dry-run preflight

Before spending credits, especially on larger files or searches, run the same command with `--dry-run`:

```bash
python scripts/enrich.py person-enrich --input people.csv --output out.xlsx --dry-run
python scripts/enrich.py person-search --company "Northwind Capital" --title director --size 25 --dry-run
python scripts/enrich.py company-search --industry "real estate" --country singapore --size 50 --dry-run
```

Dry-run validates the input/search, prints the planned output, and estimates maximum credits without requiring `PDL_API_KEY`, calling PDL, or writing `.xlsx` output.

## Contact fields and the free plan

On the free plan, PDL returns PII fields (`emails`, `phone_numbers`) as a boolean, not the value: `true` = a contact exists but is paywalled, `false` = none on file. The people sheets surface this in **Email status** / **Phone status** columns: `included` (real value present, Pro plans), `exists - upgrade to view` (paywalled but present), `none on file`, or `unknown`.

## The five commands

**person-enrich** — one-to-one match named people.

```bash
python scripts/enrich.py person-enrich --input people.csv --output out.xlsx
```

Recognised input columns (case/space-insensitive): name/full name, first name, last name, company/employer, title, location, email, linkedin/profile. More context per row = higher match rate.

**person-identify** — when a single enrich is ambiguous, get the candidate set.

```bash
python scripts/enrich.py person-identify --input people.csv --max-candidates 5
```

Same input as enrich. Output has multiple rows per input person, each a scored candidate (Match score column), so the user can pick the right one.

**person-search** — find people by criteria, no name list needed.

```bash
python scripts/enrich.py person-search --company "Northwind Capital" --title director --size 25
```

Flags: `--company --title --location --country --industry --name`, plus `--size` (1–100), `--dataset` (default all), and `--sql` to pass a raw PDL SQL query for full control. Flags are combined with AND.

**company-enrich** — match a list of companies to firmographics.

```bash
python scripts/enrich.py company-enrich --input companies.csv --output firms.xlsx
```

Recognised input columns: name/company, website/domain, ticker, linkedin/profile, location/country/region/locality. Needs at least one of name/website/ticker/profile per row.

**company-search** — find companies by criteria.

```bash
python scripts/enrich.py company-search --industry "real estate" --country singapore --min-employees 50 --size 50
```

Flags: `--name --industry --country --locality --tag --min-employees`, plus `--size` and `--sql`.

## Reviewing output with the user

People sheets have two tabs: **People** (one row per person, status colour-coded) and **Employment history** (one row per past role). Company sheets have a single **Companies** tab. The **Status** column is the first thing to check: `matched` (green), `needs_review` (amber), `no_match` (red), `error` (orange). Call out the amber/red rows explicitly so the user knows what to double-check.

## Tuning matches

`--min-likelihood N` (1–10) is the confidence floor for the enrich/identify commands. Raise it (6–8) when names/companies are common and you'd rather miss than mis-match; lower it when you have rich context and want coverage. Company enrichment is most reliable with a website/domain; person enrichment with a company or email alongside the name.

## Swapping providers later

The PDL-specific pieces are the `*_params` builders, `pdl_request`, and the `parse_person` / `parse_company` mappers. To support another provider, implement those against its API and keep the same record dict shape; input parsing, status logic, SQL/flag handling, dry-run summaries, and `.xlsx` writing stay as is.

## Principles

- **Drafts, not advice** — output is a research aid for a person to review, not a determination.
- **Never invent** — surface only what PDL returns; mark `no_match`/`needs_review` honestly rather than guessing an identity.
- **Deterministic where it counts** — input parsing, status logic, dry-run estimates and `.xlsx` writing are deterministic.
- **Honesty and calibration** — flag low-confidence matches and show the rough credit cost up front.
- **Workspace hygiene** — write outputs where the user expects; never write the API key to disk in the skill.

## Data handling

**PDL is a third party and enrichment sends the real name/company to it** — it cannot be tokenised, because the name *is* the lookup. Treat the `.env` / `PDL_API_KEY` as a secret: never print, commit or upload it. For people, confirm a legitimate and proportionate purpose and collect only fields relevant to that purpose.

## Pitfalls

1. **Free plan hides contact values** — emails/phones come back as booleans; read the status columns.
2. **Search cost scales with `--size`** — quote the rough credit cost and keep `--size` modest.
3. **Common names mis-match** — raise `--min-likelihood` or add context columns (company/email).
4. **Never commit `.env`** — the key is a secret; `--self-test` and `--dry-run` need no key.
5. **Dry-run is an estimate** — actual billing follows PDL's endpoint terms and returned records/matches.

## Verification checklist

- [ ] Legitimate, proportionate purpose confirmed for any person enrichment/search.
- [ ] `--dry-run` used for large files or searches to validate scope and estimate credits.
- [ ] `PDL_API_KEY` available via env or `.env` for live runs (never written into the skill).
- [ ] Rough credit cost stated before any large search.
- [ ] Amber/red status rows flagged to the user.
- [ ] `.env` not printed/committed.

## Requirements

- Python 3.8+
- `pip install openpyxl` (HTTP uses the stdlib `urllib` — no `requests` needed)
- `PDL_API_KEY` (env var or `.env`) for live API calls; get one at https://www.peopledatalabs.com
- Network access to the PDL API. `--self-test` and `--dry-run` run fully offline.
