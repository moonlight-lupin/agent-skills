---
name: fill-template
description: >
  Bulk-fill ONE master template — a Word (.docx) letter/form or an Excel (.xlsx)
  form — from a data table, producing one filled file per row (mail-merge). Use
  whenever the user wants to "fill in this letter for each person", "mail merge",
  "generate letters for this list", "run this template over a spreadsheet", or
  hands over a template plus a list. The skill reads the master, proposes a
  TOKENISED version (varying parts become {{tokens}}), confirms the template and
  the token-to-column mapping with the user, then regenerates one output per data
  row — preserving the master's layout and styling exactly. Data is an .xlsx or
  .csv (one row per output); outputs are one named file per record. Never invents:
  a token with no data is written as a VISIBLE flag, never a silent blank. Runs
  fully local and generates files only — it does not send, post or sign. Not for
  extracting data OUT of documents, and not a substitute for a hand-crafted single
  letter.
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
---

# Fill Template (mail-merge)

Turn **one master template** + **a data table** into **many filled copies** — one per row — swapping
only the parts that vary and leaving the master's layout and styling untouched. Document generation
only: nothing is sent, posted or signed.

## Scope and routing

Use this skill when the user has **one** template and **a list**, and wants a filled copy per row. Do
**not** use it to get data *out* of documents (that's an extraction task), to produce a single bespoke
letter (just edit one document), or where the host environment mandates a different document pipeline.

## Inputs the user provides

1. **The master template** — a `.docx` letter or form, **or** a `.xlsx` form. One master per run.
   This is the source of truth for layout and styling.
2. **The data table** — a `.xlsx` or `.csv`, **one row per output**, with a header row. Columns supply
   the values that vary (names, amounts, dates, references…).
3. **(Optional) a naming pattern** — how each output file is named, e.g. `Letter_{Name}`. Defaults to
   `<template>_<row-number>`.

## Workflow (do this, in order)

1. **Analyse the master.** Read it with `read_content(path)` and identify the parts that **vary** row
   to row — names, salutations, amounts, dates, reference numbers — versus the boilerplate that stays
   fixed. `read_content` shows repeated paragraph text once with a `(×N)` count — that's how many
   places `tokenise` will replace it (e.g. a name in both the body and the header). See
   `references/tokenising-guide.md` for what to tokenise and how to name tokens well.
2. **Propose a tokenised template.** Build a `mapping` of each varying phrase → a token name, and
   present it to the user as a plain list ("`Ms Jordan Lee` → `{{Name}}`, `$1,000,000` →
   `{{Amount}}`, …"). Token names should match the data file's column headers where possible — that
   makes the mapping automatic.
3. **Confirm with the user.** Show the proposed tokens (and, if helpful, save the tokenised template
   and show its text) and **wait for explicit confirmation** before generating anything. This is the
   review gate — get the template right once, then fan it out.
   ```python
   from fill_template import read_content, tokenise, tokens_in, load_rows, generate

   print(read_content("Letter_master.docx"))                       # step 1

   rep = tokenise("Letter_master.docx",                            # step 2
                  "Letter_tokenised.docx",
                  [{"find": "Ms Jordan Lee", "token": "Name"},
                   {"find": "$1,000,000",    "token": "Amount"},
                   {"find": "01 Jul 2026",   "token": "EffectiveDate"},
                   {"find": "REF-0001",      "token": "Reference"}])
   # rep["not_found"] lists any phrase that wasn't located — fix those before generating.
   print(tokens_in("Letter_tokenised.docx"))
   ```
   `tokenise` finds each exact phrase and replaces it with `{{Token}}`, **preserving the formatting of
   the run/cell it sits in** (a bold figure stays bold). It reports a hit count per token and flags any
   phrase it could not find, so a typo in the `find` text is caught before you generate 200 letters.
4. **Load the data and check the mapping.** `headers, rows = load_rows("recipients.xlsx")`. The
   token→column map defaults to *token name == column header* (case-insensitive); override any that
   differ. Any template token with no column, or a mapped column blank for a given row, becomes a
   visible `«MISSING: Token»` flag — never a guess.
5. **Generate one file per row.**
   ```python
   report = generate(
       "Letter_tokenised.docx", rows,
       token_to_column={"Name": "Recipient"},   # only the ones whose token != column
       outdir="out",
       name_pattern="Letter_{Recipient}",
   )
   ```
   `report` lists every file written, the rows skipped (e.g. a name-pattern column missing from the
   data), any `unmapped_tokens`, and per-file `missing` tokens.
6. **Report back honestly.** Tell the user how many files were produced and **where**, and surface
   every `missing` flag and `unmapped_tokens` entry so blanks are dealt with before the batch is used.
   Outputs are **drafts for a person to review** before they go out.

## How tokenising and replacement work

- **Token syntax** is `{{TokenName}}` (spaces inside the braces are ignored).
- **`.docx`** — replacement is run-aware: the value lands in the run where the token begins (inheriting
  its formatting) and any other runs the token spans are trimmed; runs outside the token are left
  exactly as they were. Body text, tables (including nested), and header/footer text are all covered.
- **`.xlsx`** — tokens inside any cell on any sheet are replaced; all other cell content, formulas and
  formatting are preserved (openpyxl). Put a token anywhere the value should appear, e.g. cell `B5` =
  `{{Name}}`.
- **Dates** in the data render as **DD MMM YYYY** by default; whole numbers drop a trailing `.0`. For
  currency or specific number formats, **format the column in the data file** — the helper inserts the
  value as supplied.
- **Never invent.** A token with no value for a row is written as `«MISSING: Token»` and recorded in
  the report. Fix the data (or the mapping) and re-run; don't hand-edit blanks into invented values.

## Safety

- **Files only.** Generates documents; never sends, posts, emails, signs or files anything.
- **One master per run.** Don't mix two different templates in a single batch.
- **Match the master.** Preserve the supplied template's layout and styling; only swap tokens.
- **Confirm before fan-out.** Get explicit sign-off on the tokenised template and mapping before
  generating the batch.
- **Surface every blank.** Report all `«MISSING:…»` flags and unmapped tokens; never paper over them.

## Files

- `scripts/fill_template.py` — the engine: `read_content` (analyse) · `tokenise` / `tokens_in` ·
  `load_rows` (.xlsx/.csv) · `generate` (one file per row + report).
- `references/tokenising-guide.md` — how to choose and name tokens, letters vs forms, the confirm
  step, and the MISSING-flag rule.
- `examples/example-run.md` — a worked end-to-end run (bring your own master + data; no binaries are
  shipped).

## Principles

- **Drafts, not advice** — outputs are drafts for a person to review, not finished correspondence.
- **Never invent** — a missing value is a visible `«MISSING: Token»` flag, never a silent blank or a
  guess.
- **Deterministic where it counts** — tokenising, mapping and generation are deterministic and
  reported; the LLM only proposes the token list for the user to confirm.
- **Honesty and calibration** — surface every missing/unmapped token and where files were written.
- **Workspace hygiene** — write outputs to a clear folder; keep the master and data untouched.

## Data handling

Runs **fully local** — the template and data stay on your machine and nothing crosses to an external
tool, so names, amounts and references are handled in place. If any step *would* send data to an
external or third-party service, de-identify sensitive personal data first and confirm the egress with
the user. This skill itself needs no network and no credentials.

## Pitfalls

1. **`find` text must be exact** — copy the phrase verbatim (punctuation, currency symbols); check the
   `not_found` list before generating.
2. **Token == column header** wherever possible — then the mapping is automatic; otherwise pass
   `token_to_column`.
3. **Confirm before fan-out** — fixing the template once beats re-issuing a whole batch.
4. **MISSING flags are not failures to hide** — surface them; fix the data/mapping and re-run.
5. **The data table is a separate file** from an `.xlsx` form template — don't confuse the two.

## Verification checklist

- [ ] Master analysed; varying parts identified vs boilerplate.
- [ ] Token list proposed and **confirmed by the user** before generating.
- [ ] `not_found` list from `tokenise` is empty (or resolved).
- [ ] Token→column mapping checked; defaults verified.
- [ ] Batch generated; file count and output folder reported.
- [ ] Every `«MISSING:…»` and `unmapped_tokens` entry surfaced to the user.

## Requirements

- Python 3.8+
- `pip install python-docx openpyxl`
- No network access and no credentials — fully local file I/O.
