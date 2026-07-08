# Research lenses — what to look for, and how

Run each lens, capture the **source URL + date for every claim**, and weigh sources before writing.
The goal is a cited, balanced dossier — not a verdict.

## 0. Pin the subject first

Disambiguate before researching — same names are common.
- **Company:** legal name + registration no., jurisdiction, incorporation date, website, former names
  / trading names.
- **Person:** full name, role, current employer, location, and any public DOB — plus what
  distinguishes them from same-name others (employer + location usually suffice).
- If you can't tell two same-name entities apart, say so and present both.

## 1. Identity & background

Confirm the right entity exists and what it is. The companies registry (e.g. Companies House in the
UK, SEC EDGAR in the US, or the local equivalent), the entity's own site, LinkedIn, industry
databases. For a person: career history, current and prior roles, professional registrations.

Queries: `"<name>" <jurisdiction> registration`, `"<name>" company profile`, `"<name>" linkedin`,
`"<name>" official site`.

## 2. Ownership & key management

Shareholders / UBO signals, parent/group, directors and senior managers; for a person, their other
directorships/affiliations. **Run the `people-enrichment` skill (PDL)** for the people & firmographics
layer. Note where ownership is opaque (nominees, offshore layers).

Queries: `"<name>" ownership structure`, `"<name>" directors`, `"<name>" parent company`,
`"<name>" beneficial owner`, `"<person>" board OR director`.

## 3. Adverse / negative media

Allegations, investigations, scandals, fraud, insolvency, environmental/labour/safety issues, ESG
controversies. **Attribute and date each item; distinguish allegation → charge → outcome.** Don't
launder a single blog/forum claim into a finding — corroborate serious claims with ≥2 independent
reputable sources.

Queries: `"<name>" fraud OR investigation OR lawsuit OR scandal`, `"<name>" fined OR penalty OR
sanctioned`, `"<name>" insolvency OR liquidation`, `"<name>" controversy`, `"<name>" allegations`.
Check the date range — flag stale vs recent.

## 4. Sanctions / PEP / watchlist signals

Use `screen_lists(name)` (OFAC SDN/Consolidated, UK-OFSI, UN; extensible) for a **name-match signal**,
plus a web check of the official portals (OFAC, UN, EU, UK-OFSI, and the subject's local list) and PEP
indications (gov role, state-owned-enterprise senior officer, close associate). **This is a signal to
escalate — not a determination.** See `boundaries-and-sanctions.md` for the rules and the matcher's
limits.

## 5. Litigation & regulatory

Material lawsuits, regulator actions, enforcement, debarment, licence issues. Court records, regulator
press releases, legal news. Note jurisdiction, status (pending/decided), and outcome.

Queries: `"<name>" court OR lawsuit OR litigation`, `"<name>" regulator OR enforcement`, `"<name>"
debarred OR struck off`.

## 6. Summary & flags

A short, honest read: what's established, what's alleged, what's unknown. **List escalation flags**
(sanctions/PEP signal, serious adverse finding, integrity/AML concern) explicitly — each tagged
"escalate to your compliance / AML function".

## Source weighting (high → low)

1. **Primary / official** — registries, regulators, courts, the entity's filings.
2. **Reputable press / databases** — major outlets, established trade press.
3. **Secondary aggregators** — wikis, company-data sites (corroborate before relying).
4. **Low-trust** — blogs, forums, anonymous posts (signal only; never the sole basis).

Always: cite, date, distinguish allegation from outcome, note confidence, and prefer recent +
corroborated. When sources conflict, present the conflict rather than picking a side.
