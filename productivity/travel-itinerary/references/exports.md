# Exports — Templates and Formats

This file defines the output formats. Pick the variant that matches the
audience (see `references/privacy.md` for what to include vs hide per audience).

## File naming

```text
{YYYY-MM-DD}_{destination_slug}_business_trip_itinerary.md          # internal full
{YYYY-MM-DD}_{destination_slug}_business_trip_team_share.md         # team-share
{YYYY-MM-DD}_{destination_slug}_business_trip_exec_summary.md       # exec summary
{YYYY-MM-DD}_{destination_slug}_business_trip_admin.md              # travel-admin
{YYYY-MM-DD}_{destination_slug}_business_trip.ics                   # calendar
{YYYY-MM-DD}_{destination_slug}_business_trip_chat.txt              # chat-ready
```

`{YYYY-MM-DD}` is the trip's start date. `{destination_slug}` is the primary
destination city, lower-case, hyphenated (e.g. `tokyo`, `kuala-lumpur`).

## Output location

Save deliverables to the user's selected folder or agreed workspace, not to the
scratchpad. Working drafts and intermediate YAML can live in the scratchpad.
After writing, present files using the delivery method your environment supports:

- Chat / messaging environments: send the local file directly using the platform's file-attachment mechanism.
- CLI / desktop environments: provide the absolute file path or a supported local-file link.
- Cloud-doc exports (Google Docs / Drive, etc.): provide the verified share URL.


## Internal full — Markdown template

```markdown
# {Trip Title}

**Dates:** {start_date} – {end_date}  
**Destination:** {rough_destination}  
**Travel party:** {travellers}  
**Purpose:** {purpose}  
**Prepared:** {prepared_date}

## Quick Summary

- **Hotel / base:** {hotel_name_and_dates}
- **Arrival:** {arrival_summary}
- **Departure:** {departure_summary}
- **Main meeting location:** {main_meeting_location}
- **Notes:** {high_level_notes}

## Open Questions / Missing Details

- [ ] {missing_detail_1}
- [ ] {missing_detail_2}

## Day 1 — {weekday}, {date} ({local_timezone})

**Overnight stay:** {hotel_name / address / check-in notes}

### {HH:MM} — {node title}

- **Type:** {node_type}
- **Location:** {location_name}, {address}
- **Participants:** {participants}
- **Reference:** {confirmation_ref_if_appropriate}
- **Cost:** {amount} {currency} ({payer}) — *omit line if unknown*
- **Notes:** {notes}
- **Map:** {maps_url_if_available}

### Transfer / route to next item

- **From:** {origin}
- **To:** {destination}
- **Estimated travel:** {duration} by {mode}
- **Map:** {directions_url}

## Day 2 — {weekday}, {date} ({local_timezone})

...

## Cancelled / no longer happening

- ~~{HH:MM} — {cancelled node title}~~ — {reason if known}

## Reference Details

### Flights / Trains
...

### Accommodation
...

### Restaurants / Events / Tickets
...

## Source Notes

- {source summary, not full raw email unless asked}
```

## Team-share — Markdown template

Same skeleton as internal-full, but apply the redactions from
`references/privacy.md`:

- Drop the **Source Notes** section.
- Drop **Reference Details > Flights/Trains** confirmation refs unless flights
  are shared by the team.
- Drop `private_notes`.
- Cost lines: omit (per the privacy matrix — costs are not shared by default).
  Override only on explicit user request, e.g. when sharing a per-traveller
  budget summary.
- Cancelled nodes: omit entirely (do not show the strike-through section).

## Executive summary — Markdown template

One page, no longer than ~250 words.

```markdown
# {Trip Title} — {start_date} to {end_date}

**Destination:** {city, country}  
**Travel party:** {names}  
**Purpose:** {one-line purpose}

## Schedule

| Date            | AM                                  | PM                                  | Overnight |
|-----------------|-------------------------------------|-------------------------------------|-----------|
| {date, weekday} | {top item}                          | {top item}                          | {hotel}   |
| {date, weekday} | {top item}                          | {top item}                          | {hotel}   |

## Key meetings

- {date HH:MM} — {who with} @ {short location}
- {date HH:MM} — {who with} @ {short location}

## Logistics

- **Arrival:** {flight no., HH:MM at {airport}}
- **Departure:** {flight no., HH:MM from {airport}}
- **Hotel:** {name}, {short address}
```

## Travel-admin — Markdown template

For assistants / ops. Reference-heavy.

```markdown
# {Trip Title} — Travel Admin Pack

## Bookings

| Type   | Date         | Provider     | Ref         | Cost          | Cancellation deadline |
|--------|--------------|--------------|-------------|---------------|------------------------|
| Flight | {date}       | {airline}    | {ref}       | {amt} {cur}   | {date or n/a}          |
| Hotel  | {dates}      | {hotel}      | {ref}       | {amt} {cur}   | {date or n/a}          |

## Supplier contacts

- {Provider}: {phone}, {email}

## Traveler assignment

- {Name}: {flights/hotel/meetings}

## Expense routing

- {item} → {billable_to / cost-centre}

## Open admin items

- [ ] {item, owner, due}
```

## Chat-ready — plain text

For WhatsApp / Telegram / Slack. Short. No sensitive details.

```text
{Trip Title} — {dates}

{Day 1 date}
• {HH:MM} {short item}
• {HH:MM} {short item}
• Overnight: {hotel/base}

{Day 2 date}
• {HH:MM} {short item}
• {HH:MM} {short item}
• Overnight: {hotel/base}

Notes:
• {important note}
• {map/share link if any}
```

## Calendar `.ics` export

Use one `VEVENT` per timed node. Skip `note`, `free_time`, and untimed `poi`
nodes by default unless the user asks to include them. `admin` nodes with a
`due_at` become `VTODO`s (Apple Calendar and Outlook support VTODO; Google
Calendar ignores VTODO — fall back to a 15-minute VEVENT if the user uses
Google Calendar).

Required structure:

```ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//travel-itinerary skill//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH

BEGIN:VTIMEZONE
TZID:Asia/Hong_Kong
BEGIN:STANDARD
DTSTART:19700101T000000
TZOFFSETFROM:+0800
TZOFFSETTO:+0800
TZNAME:HKT
END:STANDARD
END:VTIMEZONE

BEGIN:VTIMEZONE
TZID:Asia/Tokyo
BEGIN:STANDARD
DTSTART:19700101T000000
TZOFFSETFROM:+0900
TZOFFSETTO:+0900
TZNAME:JST
END:STANDARD
END:VTIMEZONE

BEGIN:VEVENT
UID:flight-001@travel-itinerary
DTSTAMP:20260610T120000Z
DTSTART;TZID=Asia/Hong_Kong:20260612T081000
DTEND;TZID=Asia/Tokyo:20260612T134000
SUMMARY:CX548 HKG → HND
LOCATION:Hong Kong International Airport (HKG) → Tokyo Haneda (HND)
DESCRIPTION:Cathay Pacific CX548. Ref ABC123. Terminal 1 → Terminal 3.
CATEGORIES:Travel,Flight
STATUS:CONFIRMED
END:VEVENT

END:VCALENDAR
```

Rules:

- `UID` — use the node `id` + `@travel-itinerary` so re-exports update rather
  than duplicate.
- `DTSTART` / `DTEND` — for same-timezone nodes, use `TZID=` with
  `node.timezone` (fall back to `day.local_timezone`, then
  `trip.timezone_default`). For cross-timezone travel, use `timezone_start`
  for `DTSTART;TZID=` and `timezone_end` for `DTEND;TZID=`. Always include a
  matching `VTIMEZONE` block for every `TZID` used.
- `STATUS:` map from the node `status`: `confirmed → CONFIRMED`,
  `tentative → TENTATIVE`, `cancelled → CANCELLED`, `unknown → CONFIRMED`
  (most permissive default).
- `CATEGORIES:` derive from `type` and `subtype` (e.g. `Travel,Flight`,
  `Meeting,Client`).
- `DESCRIPTION:` include `provider`, `confirmation_ref`, and key practical
  notes. Escape `\n` with `\\n`, commas with `\\,`, semicolons with `\\;`.
  Apply the same privacy rules as the equivalent Markdown variant — by default
  the `.ics` matches the **internal full** variant; produce a separate
  `*_team_share.ics` if needed.
- Lines must not exceed 75 octets; fold continuation lines with a leading
  space (RFC 5545). Prefer generating `.ics` with CRLF line endings.
- Each `VEVENT` must include at least `UID`, `DTSTAMP`, `DTSTART`, `SUMMARY`,
  and `END:VEVENT`.
- Each `VTODO` must include at least `UID`, `DTSTAMP`, `SUMMARY`, and
  `END:VTODO`; use `DUE` when there is a deadline.
- Final line is `END:VCALENDAR`.

Untimed admin items as `VTODO`:

```ics
BEGIN:VTODO
UID:admin-001@travel-itinerary
DTSTAMP:20260610T120000Z
DUE;TZID=Asia/Tokyo:20260612T230000
SUMMARY:Online check-in opens for return flight
STATUS:NEEDS-ACTION
END:VTODO
```

## Export workflow

1. Confirm target audience (internal / team-share / exec / admin).
2. Confirm format (Markdown / PDF / DOCX / Google Doc / chat / `.ics`).
3. Apply redactions per `references/privacy.md`.
4. Render from the canonical YAML — do not re-derive facts from source emails
   at this step. Apply node-level `visibility` first, then field-level
   redactions per `references/privacy.md`.
5. Write file to the user's selected folder using the naming convention above.
6. Verify the file exists and opens cleanly before telling the user it's ready.
   For `.ics`, use `python3 scripts/itinerary_utils.py ics-check <file>` or an
   equivalent sanity check: `BEGIN:VCALENDAR` … `END:VCALENDAR` present,
   balanced `BEGIN`/`END` blocks, required VEVENT/VTODO fields present, and
   every used `TZID` has a matching `VTIMEZONE` block.
