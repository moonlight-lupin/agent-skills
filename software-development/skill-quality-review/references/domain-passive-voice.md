# Domain-Specific Passive Voice False Positives

When reviewing skills in regulated or technical domains (accounting, law, medicine, engineering), the passive voice heuristic (`is \w+ed`, `are \w+ed`, `was \w+ed`, `were \w+ed`) flags domain-standard terminology as passive voice. These are correct usage, not writing failures.

## Examples by domain

### Accounting (SG FRS, IFRS)
- "revenue is recognised when earned" — SG FRS 18 standard phrasing
- "the period is closed" — period status terminology
- "receipts are recorded as deferred income" — accounting policy description
- "items are matched" — reconciliation terminology
- "output tax is recorded as a liability" — GST phrasing

### Legal
- "the contract is governed by" — jurisdiction phrasing
- "damages are awarded" — court terminology

### Medical
- "the patient is administered" — clinical phrasing
- "the dose is adjusted" — protocol phrasing

## When to fix vs when to leave

**Fix** — passive voice hides a knowable actor the agent needs to understand:
- "is enforced in approve_entry()" → "the engine enforces this in approve_entry()" ✓
- "are stored as hashes" → "the store hashes all secrets" ✓

**Leave** — passive construction names a domain-standard phrase from an authoritative source:
- "revenue is recognised when earned" — leave (SG FRS 18 standard)
- "the period is closed" — leave (period status terminology)
- "tax is recorded as a liability" — leave (accounting policy)

## Rule of thumb

If the passive construction names a domain-standard phrase from an authoritative standard (FRS, IFRS, IAS, legal statute, clinical protocol), leave it. The connection to the standard matters more than active voice style.

If the passive construction hides a knowable actor that the agent needs to understand (engine, system, user, store), fix it to active voice.