# Boundaries & sanctions — signal, not determination

The single most important rule for this skill: it **researches and compiles**; it does **not
determine, screen, clear, rate or block**. Get this wrong and it impersonates a regulated function (a
CDD/AML screening function, a compliance decision).

## The signal-not-determination rule

- A sanctions / PEP / watchlist name-match is a **potential-match SIGNAL** → **escalate to your
  compliance / AML function** for verification. Never write "X is sanctioned" or "X is clear".
- **No match is NOT a clearance.** The lists aren't exhaustive and the matcher is basic (below).
  Absence of a hit means *this check found nothing* — nothing more.
- Negative media is **allegation + source + date**, not a finding. Distinguish allegation → charge →
  outcome. Avoid defamatory framing; report what the source says, attributed.

## The lists (`screen_lists`)

Official government consolidated lists, fetched live and cached (`~7 days`):
- **OFAC-SDN** — US Treasury Specially Designated Nationals (≈19k).
- **OFAC-CONS** — US Treasury Consolidated (non-SDN) list (≈0.4k).
- **UK-OFSI** — UK consolidated list of asset-freeze targets (≈20k; *this is what catches a UK-only
  designation an OFAC/UN check misses*).
- **UN** — UN Security Council consolidated list (≈1k).

**National / local lists.** Many countries maintain their own autonomous lists, and several have **no
clean machine-readable feed**. For the subject's home jurisdiction, do a **manual portal check** of
the relevant authority's site — and don't represent the absence of a feed as having fully screened
that jurisdiction.

*Extensible:* EU and others — add a fetcher/parser + URL to `LIST_URLS` / `_PARSERS` and
`DEFAULT_LISTS`. (EU's official download needs a free token, so it isn't bundled.)

URLs can drift (OFAC has migrated endpoints before) — if a list shows as `unavailable`, update the URL
constant or do an official-portal web check for it. Fetch failures degrade gracefully (the list is
skipped and reported in `unavailable`, with a fallback to stale cache).

## Matcher limits (why it's only a signal)

`screen_lists` does **token-based** matching (normalised, corporate-suffix-stripped):
- **Catches:** exact and token-subset matches ("Northwind Bank" → "NORTHWIND BANK"; "Acme Trading" →
  "ACME TRADING CO") and strong multi-token overlap.
- **Misses:** **transliteration / spelling variants** (e.g. a name romanised differently),
  **phonetic** matches, heavy typos, and single-token names listed under a variant spelling. It is
  **not** fuzzy/phonetic like a professional tool (World-Check, Dow Jones).

→ This is precisely why a no-match is not a clearance, and why a **professional screening tool /
your compliance function is authoritative**. Use this for a fast first signal only.

## False positives

Common names produce matches that aren't your subject. Before flagging, sanity-check the matched entry
against your subject's identifiers (jurisdiction, type, DOB, program). Present a match as "potential
match on '<matched name>' (list, score) — to verify", with the detail, so a reviewer can adjudicate.

**Generic-word guard.** A match needs at least one **distinctive** shared token — generic business
words (`capital`, `management`, `partners`, `investment`, `group`, `global`, `trading`, `properties`,
…; see `_GENERIC`) don't create a match on their own. This stops "X Capital Management" from matching
an unrelated "Y Capital Management". Screen on the **distinctive** part of a name where possible (e.g.
"Northwind", not "Northwind Capital Management").

## Persons — privacy guardrails

- Research a person **only for a legitimate purpose** (vetting a counterparty, hire, partner) and only
  **publicly-available** information.
- Don't compile **sensitive** personal data (health, religion, sexuality, political views) or build an
  intrusive profile; stay on integrity/role/affiliation relevant to the purpose.
- Keep the dossier **local**; it's internal and may name individuals.

## Data handling — search the name, not the relationship

A bare name with no client/deal link is **not sensitive** to search. But never put your **relationship**
into an external query ("our client X", "we're buying X"). If the subject is tied to a live deal or a
client, that *relationship* stays confidential (omit it from queries); the public research on the name
still proceeds.
