---
name: entity-research
description: >
  Deep background research on an entity — a company OR a person — into a cited
  dossier: identity & background, ownership & key management, adverse / negative
  media, public sanctions-list name-match signals, PEP indications from public
  research, and litigation / regulatory history. Use when the user says
  "research this company / person", "background check on X", "any negative
  press / adverse media on X", "who owns / who runs X", "is X sanctioned /
  sanctions check on X", "vet this vendor / counterparty / candidate /
  partner", or "entity search". It RESEARCHES and COMPILES with sources; it is
  NOT a compliance/AML/CDD determination and NOT a sanctions or PEP clearance.
  A sanctions-list or PEP signal is a SIGNAL to escalate to a human compliance
  function, never a "clear" or "block". Research a person only for a legitimate
  purpose and only from public information.
version: 1.0.1
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
---

# Entity Research

Deep background research on a **company or a person** → a **cited dossier** for a human to read and act on. General-purpose research — vetting a vendor, a counterparty before a contract, a prospective hire, a partner, or verifying a media claim.

> **Research & compilation — NOT a determination.** This skill does **not** screen, clear, rate, or block anyone. A sanctions-list / PEP / watchlist signal is a **SIGNAL to escalate** to a qualified compliance / AML function, not a finding; negative press is an **allegation with a source and date**, not a proven fact. Everything is **cited**; nothing is auto-acted on.

## Scope and routing

Use this skill for general background research and fast public **signals**. Do **not** use it as a substitute for professional CDD/AML screening, sanctions clearance, PEP screening, or a compliance decision, and do not build an intrusive profile of a private individual.

## When to use it

- Vet a **vendor / supplier / counterparty** before engaging or signing a contract.
- Background on a **prospective hire**, a **partner**, or a co-investor's principal.
- Check for **negative / adverse media** or **litigation** on a name.
- A quick **public sanctions-list signal** check (to escalate, not to clear).
- A quick **PEP indication** check from public research (to escalate, not to clear).
- "Who actually owns / runs X?" — ownership & key-management background.

## The research lenses

1. **Identity & background** — confirm you have the right entity (registration no., jurisdiction, incorporation date, website, aliases / former names; for a person: role, employer, location, DOB if public). Disambiguate same-name entities early.
2. **Ownership & key management** — shareholders / UBO signals, directors, senior managers; group/parent structure. Use the `people-enrichment` skill / PDL for people & firmographics where appropriate.
3. **Adverse / negative media** — allegations, investigations, scandals, insolvency, fraud, environmental/labour issues — each with **source, date, and allegation-vs-outcome**.
4. **Sanctions / PEP / watchlist signals** — `screen_lists(name)` checks public sanctions lists only (OFAC SDN + Consolidated, UK OFSI, UN). PEP indications are manual/open-web research signals, such as public office, senior state-owned enterprise role, close-associate indications, or official biographies. **Neither is a clearance.**
5. **Litigation & regulatory** — material lawsuits, regulator actions, fines, debarments.
6. **Summary & flags** — a short read with **escalation flags** for a compliance reviewer.

## Data sources (self-sufficient core + optional depth)

- **Open web** — `web_search` + `web_extract` for press, litigation, registry mentions, ownership clues, and public PEP indications.
- **Deep-research engine** — for a thorough pass, hand the entity + lenses to a deep-research engine/skill if available; otherwise run fan-out searches directly.
- **PDL (people / firmographics)** — run the **`people-enrichment`** skill for the owner / key-management / company layer where appropriate (needs `PDL_API_KEY`).
- **Public sanctions lists** — `scripts/entity_research.py` → `screen_lists(name)` fetches + token-name-matches the official government consolidated lists: **US (OFAC SDN + Consolidated), UK (OFSI), UN**. It returns **potential-match signals** only. It is not fuzzy/phonetic screening and does not cover all local autonomous lists. For a country's **local autonomous measures**, do a manual official-portal check. **A match is a signal to verify with a compliance function; no match is NOT a clearance**.

## Workflow

1. **Pin the subject** — name + identifiers (jurisdiction, registration no., website, role/employer for a person). Resolve same-name ambiguity before researching.
2. **Plan the research** — break the entity into 3-6 research sub-questions across the lenses (e.g. "Who owns X?", "Any litigation against X?", "Is X on any sanctions list?"). Define success criteria: what would a complete dossier cover? This plan guides which lenses to prioritize and prevents skipping lenses.
3. **Run the lenses** — fan-out web search per lens; PDL for people/firmographics; `screen_lists()` for public sanctions-list signals; manual official/public checks for PEP indications and local sanctions lists. **Capture the source URL + date for every claim.**
   - **Date grounding (mandatory).** Before searching, ground in the real current date: "Today's date is {current date}. Use {current year} in queries — never a year inferred from training data."
   - **Quality filter.** Discard thin/irrelevant results before extraction: landing pages, aggregator stubs (<100 words of substantive content), pages with keyword overlap but no actual relevance (word-boundary match entity name, not substring), and duplicate URLs.
4. **Gap analysis** — after the first pass, review findings against the research plan from step 2. Which sub-questions are unanswered? Which lenses have thin coverage? Generate targeted follow-up queries for the gaps and run a second search pass. Repeat once more if significant gaps remain (max 3 passes).
5. **Weigh** — primary/official sources > reputable press > blogs/forums; allegation vs outcome; recency; corroboration (≥2 independent sources for a serious claim). Flag low-confidence items as such; don't launder rumour into fact.
6. **Assemble** — `dossier(...)` builds the cited markdown dossier (the six lenses + a "not a determination" header + escalation flags). Deliver to chat or save as `.md`.
7. **Flag escalations** — any sanctions-list signal, PEP indication, serious adverse finding, or integrity concern → call out **"escalate to a compliance / AML reviewer"** explicitly.

See `references/research-lenses.md` (what to look for + query patterns) and `references/boundaries-and-sanctions.md` (the signal-not-determination rule, false positives, and privacy guardrails).

## Output pattern

For adverse / litigation / regulatory findings, prefer a compact table:

| Item | Source | Date | Allegation / charge / outcome | Confidence | Escalate? |
| --- | --- | --- | --- | --- | --- |

For sanctions / PEP / watchlist signals, never write "clear" or "blocked". Use language like:

- `Public sanctions-list check found no potential matches in OFAC SDN/Consolidated, UK OFSI and UN via screen_lists() as of [date]. This is not a clearance; local lists and professional screening remain outside this helper.`
- `Potential sanctions-list name match on "[matched name]" ([list], score [x]) — escalate to compliance / AML reviewer for verification.`
- `Public PEP indication: [public office / SOE role / close associate indication] from [source, date] — escalate for compliance review. This is not a PEP-screening determination.`

## Boundaries & safety

- **Research, not a determination / clearance.** Sanctions-list or PEP signal = **escalate**, never "clear" or "block". No match ≠ clean.
- **PEP clarity.** `screen_lists()` is not a PEP screener. PEP indications come from public-source research and must be reviewed by a qualified compliance function.
- **Allegations vs facts.** Attribute and date every negative item; distinguish allegation, charge, and outcome. Avoid defamatory framing; report what sources say, with the source.
- **Persons — legitimate purpose, public info only.** Research a person only for a legitimate purpose (vetting), and only **publicly-available** information; don't compile sensitive personal data (health, beliefs, sexuality, etc.) or build an intrusive profile.
- **A dossier is a draft for a human** — never the basis for an automated action.

## Principles

- **Drafts, not advice** — a dossier is a research aid for a person to read and act on.
- **Never invent** — cite every claim with a source + date; mark thin/uncorroborated items as such.
- **Signal, not determination** — a sanctions-list / PEP / watchlist signal escalates; it never clears or blocks.
- **Honesty and calibration** — distinguish allegation from outcome; present conflicts, note confidence.
- **Workspace hygiene** — keep the dossier local; it's internal and may name individuals.

## Data handling — search the name, not the relationship

A **bare name with no relationship attached is fine** to research on the open web. But:

- **Never leak the context.** Search "[entity]", not "we're investing in [entity]" or "[entity] our client" — keep your deal/client relationship out of external queries.
- If the entity **is** tied to a live deal or a client, the relationship stays confidential (omit it from queries); the public research on the name still proceeds.
- Keep the dossier on the local machine; it may name individuals.

## Files

- `scripts/entity_research.py` — `screen_lists` (public sanctions-list name-match signal, cached, graceful), `dossier` (assemble the cited markdown dossier + escalation flags), name-normalisation/citation helpers; `--self-test` (offline; matcher + dossier).
- `references/research-lenses.md` — per-lens checklist + good query patterns + source weighting.
- `references/boundaries-and-sanctions.md` — the lists, signal-not-determination, false positives, escalation, and person-privacy guardrails.

## Verification checklist

- [ ] Subject pinned; same-name ambiguity resolved (or both presented).
- [ ] Research plan created (3-6 sub-questions across lenses, success criteria defined).
- [ ] Date grounding applied — queries use current year, not training-cutoff year.
- [ ] Quality filter applied — thin/irrelevant/duplicate results discarded before extraction.
- [ ] Gap analysis run — at least 2 search passes; remaining gaps documented.
- [ ] Every claim carries a source URL + date; serious claims corroborated (≥2 sources).
- [ ] Allegations attributed and distinguished from outcomes; thin items flagged as thin.
- [ ] `screen_lists()` presented as public sanctions-list signal only, never PEP screening or clearance.
- [ ] PEP indications, if any, came from public sources and are presented as escalation signals only.
- [ ] Person research limited to a legitimate purpose and public info only.
- [ ] Escalation flags listed explicitly; dossier kept local.

## Requirements

- Python 3.8+ (stdlib only for `screen_lists`/`dossier`).
- Session **web search + fetch** tools for the research lenses (not bundled).
- **Network** for `screen_lists` (public lists) — `--self-test` runs offline.
- Optional: `PDL_API_KEY` + the `people-enrichment` skill for the people/firmographics layer; a deep-research engine/skill for a deeper pass.
