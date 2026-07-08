# Privacy — Sensitive Fields, Redactions, Variants

This file defines what data is sensitive, how to redact it, and which variants
include or hide what.

## Sensitive fields

Treat the following as sensitive by default:

- Payment card numbers and CVVs
- Passport / national ID numbers
- Loyalty / frequent-flier numbers
- Booking PINs / passwords
- Personal (non-work) email addresses and phone numbers of the travel party
- Supplier-side commercial terms not relevant to attendees (negotiated rates,
  contract clauses)
- Client-sensitive notes that are not needed by the attendees (deal context,
  internal strategy)

## Redaction patterns

When a sensitive field appears in source material and still needs to be
referenced (e.g. for the admin variant), redact rather than delete:

| Field                 | Redaction pattern                              | Example                |
|-----------------------|------------------------------------------------|------------------------|
| Payment card          | Brand + last 4 only                            | `Visa **** 1234`       |
| Passport / ID         | Full value replaced                            | `[REDACTED]`           |
| Loyalty number        | Omit entirely (not "last 4")                   | *(omitted)*            |
| Booking PIN / password| Full value replaced                            | `[REDACTED]`           |
| Personal email        | Mask local part                                | `j****@gmail.com`      |
| Personal phone        | Mask middle digits                             | `+852 9*** **34`       |
| Confirmation ref      | Show in internal/admin; mask in team-share unless flight/train and traveller needs it | `ABC1**` (team-share)  |

For storage in the canonical YAML, keep the **redacted form**, not the raw
value. If the user pastes a raw card number, redact before storing and confirm
back to the user.

## Visibility rules

Each node may carry:

```yaml
visibility: internal | team_share | private | admin_only
```

Use `visibility` as the first export filter, then apply field-level redaction
from the matrix below.

- `internal`: default; include in internal full. Include in share variants only
  if the node is relevant and safe after redaction.
- `team_share`: intended for the travelling group; include in team-share and
  chat exports after redaction.
- `private`: include only in internal full unless the user explicitly says to
  share it.
- `admin_only`: include in internal full and travel-admin; omit from
  team-share, exec, chat, and default `.ics`.

If there is any doubt, keep the node `internal` and ask before promoting it to
`team_share`.

## Variant inclusion matrix

| Field group               | Internal full | Team-share | Exec summary | Travel admin | Chat | `.ics` |
|---------------------------|:-------------:|:----------:|:------------:|:------------:|:----:|:------:|
| Schedule (times, titles)  | yes           | yes        | top items    | yes          | yes  | yes    |
| Locations & addresses     | yes           | yes        | short        | yes          | short| yes    |
| Map links                 | yes           | yes        | no           | yes          | one  | no     |
| Flight numbers & airports | yes           | yes        | yes (top)    | yes          | brief| yes    |
| Confirmation refs         | yes           | masked     | no           | yes          | no   | yes (internal `.ics`) / masked (team-share `.ics`) |
| Hotel name & address      | yes           | yes        | yes          | yes          | yes  | yes    |
| Hotel booking ref         | yes           | masked     | no           | yes          | no   | yes / masked |
| Cancellation deadlines    | yes           | no         | no           | yes          | no   | no     |
| Costs / payment method    | yes           | no         | no           | yes          | no   | no     |
| Personal email/phone      | masked        | no         | no           | masked       | no   | no     |
| Passport / loyalty IDs    | `[REDACTED]`  | no         | no           | `[REDACTED]` | no   | no     |
| Private notes             | yes           | no         | no           | as relevant  | no   | no     |
| Source emails (raw)       | yes           | no         | no           | no           | no   | no     |
| Cancelled nodes           | strikethrough | omit       | omit         | reference    | omit | STATUS:CANCELLED (internal-full) / omit (team-share) |

"masked" means apply the redaction pattern from the table above. "no" means
omit the field/section entirely.

## OCR and source-quality gate

When extracting from screenshots or scanned PDFs, the agent must not invent
fields it could not read confidently.

- Mark the `source_item.ocr_quality` as `high`, `medium`, `low`, or
  `unreadable`.
- List specific field names you could not read in
  `source_item.ocr_uncertain_fields`.
- For any uncertain field, prefer one of:
  1. Leave the field empty and add an entry to **Open Questions / Missing
     Details** asking the user to confirm.
  2. Quote the literal characters you saw, prefixed with `?`, e.g.
     `confirmation_ref: "?ABC12?"` — never silently normalise.
- If `ocr_quality: unreadable`, do not generate any node from that source.
  Ask the user to re-send or transcribe.

## Defaults when audience is not specified

If the user just says "export the itinerary" without specifying audience,
default to the **internal full** variant and ask whether they want a
team-share copy alongside. Never default to team-share — accidental
over-sharing is worse than accidental over-disclosure to oneself.
