# Tokenising guide — choosing and naming tokens well

The quality of a batch run is set at the **tokenise** step. Get the template right once, confirm it,
then fan it out. This guide is the curated knowledge for that step.

## What to tokenise (the parts that vary row to row)

Tokenise anything that changes from one output to the next:

- **Recipient identity** — name, salutation ("Dear Ms Lee,"), title, organisation, address lines.
- **Amounts** — price, fee, balance, quantity. (Format the *number* in the data file; the token just
  drops it in.)
- **Dates** — effective date, period, deadline. Dates from the data render **DD MMM YYYY**.
- **References** — account/order/reference numbers, project names.
- **Any other field that differs** — an account, a percentage, a location.

## What NOT to tokenise (the boilerplate that stays fixed)

Leave the standing text alone — the body prose, the organisation's name, the sign-off block, fixed
headings, header/logo, footer. If it's the same in every output, it's not a token.

> One subtle case: a phrase like the salutation often **repeats** (recipient line *and* "Dear …,").
> That's fine — `tokenise` replaces *every* occurrence of the matched phrase, so one `{{Name}}` token
> covers both. The hit count in the report tells you how many places it landed.

## Naming tokens

- **Match the data file's column headers** wherever you can — the token→column mapping then defaults
  automatically (case-insensitive). If the column is `Name`, call the token `{{Name}}` and skip a
  mapping entry.
- Use clear, specific names: `{{Amount}}`, `{{EffectiveDate}}`, `{{Reference}}` — not `{{Field1}}`.
- No spaces are needed inside the braces, but they're tolerated: `{{ Name }}` works.

## The `find` text must be exact

`tokenise` locates each phrase by an **exact** substring match against the master's text.

- Copy the phrase exactly as it appears — including punctuation and currency symbols (`$1,000,000`,
  not `$ 1,000,000`).
- After tokenising, check the report's `not_found` list. Anything there means the `find` text didn't
  match — fix the phrase and re-run *before* generating the batch.
- The `hits` count is a sanity check: if you expected a token in three places and it shows one, the
  other two are worded differently and need their own `find` entries.

## Letters (.docx) vs forms (.xlsx)

- **Letters / .docx forms** — tokens sit inside sentences and table cells. Replacement is run-aware,
  so a token inside a **bold** or coloured span keeps that formatting.
- **.xlsx forms** — put a token in the cell where the value belongs (e.g. `B5` = `{{Name}}`).
  Formulas, totals and formatting elsewhere are preserved. The data table is a *different* file from
  the form template — don't confuse the two.

## The confirm step (do not skip)

Before generating, present the proposed token list back to the user as plain language and **wait for
explicit sign-off**:

> Proposed tokens: `Ms Jordan Lee → {{Name}}`, `$1,000,000 → {{Amount}}`, `01 Jul 2026 →
> {{EffectiveDate}}`, `REF-0001 → {{Reference}}`. Shall I generate?

This is the cheapest place to catch a mistake — fixing the template once beats re-issuing a whole
batch.

## Never invent — the MISSING flag

If a token has no value for a row (no mapped column, or the cell is blank), the output shows
`«MISSING: Token»` in place — a visible, greppable flag, never a silent blank or a guessed value.
These are listed per file in the `generate` report. Resolve them by fixing the data or the mapping
and re-running; do not hand-edit an invented value into the output.
