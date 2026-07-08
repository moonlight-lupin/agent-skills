---
name: travel-itinerary
description: "Create, update, sanitize, route, and export structured business-trip itineraries from booking confirmations, emails, tickets, PDFs, screenshots, calendar invites, or notes. Use for day-by-day itinerary generation, privacy-safe sharing, route links, and Markdown/PDF/DOCX/Google Doc/ICS exports."
version: 1.1.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
keywords: [travel, itinerary, business-trips, email-parsing, export, routing, markdown]
---

# Travel Itinerary

## Overview

Turn travel confirmations, booking emails, tickets, meeting notes, restaurant
reservations, and ad-hoc trip details into a structured, exportable itinerary
for internal business travel.

Mental model:

```text
Trip
└── Day
    ├── Stay / overnight base
    ├── Node 1
    ├── Link / route to next node
    ├── Node 2
    ├── Link / route to next node
    └── Node 3
```

- **Trip** — overall context: travel party, destination, date range, purpose,
  privacy preferences.
- **Day** — date, overnight stay, day notes, time-ordered nodes.
- **Node** — flight, train, hotel check-in, meeting, POI, restaurant,
  transfer, event, ticketed attraction, free block, admin reminder, or
  free-form note. Nodes carry `visibility` so internal, team-share, private,
  and travel-admin exports can differ safely.

The source of truth is the canonical YAML (see
`templates/itinerary-schema.yaml`). Markdown is the default rendered format,
with optional `.ics`, PDF, DOCX, Google Doc, and chat-ready variants.

## When to use

Use this skill when the user wants to:

- Build a business-trip itinerary from forwarded or pasted emails.
- Organise flights, hotels, trains, restaurants, tickets, meetings, attractions.
- Convert scattered booking confirmations into a clean day-by-day schedule.
- Create a team-share or exec version of an itinerary.
- Hide sensitive details before sharing.
- Add travel time or map links between itinerary points.
- Export to Markdown, PDF, DOCX, Google Doc, chat message, or calendar `.ics`.
- Update an existing itinerary with new confirmations or amendments.

Do **not** use this skill as a full travel-management backend. If the task
requires automatic inbox monitoring, persistent multi-trip databases, live
flight status, multi-user editing, or web-app sharing, suggest a separate tool
in addition to this skill.

This skill organises and renders user-provided or tool-retrieved travel facts.
Do not claim live flight status, current prices, venue opening hours, route
duration, ticket availability, or booking availability unless those facts were
verified with an available live tool during the current task.

## Reference files

This skill is split for progressive disclosure. Read the reference files when
you need depth on a topic:

- `templates/itinerary-schema.yaml` — canonical YAML structure, the source of
  truth.
- `references/node-types.md` — full per-node-type field tables, including
  flight/train-specific fields and the status lifecycle.
- `references/exports.md` — Markdown / chat / exec / admin templates, `.ics`
  spec, file-naming conventions.
- `references/privacy.md` — sensitive fields, redaction patterns, variant
  inclusion matrix.
- `references/routing.md` — coordinate hierarchy, Nominatim/OSM geocoding,
  Maps URL patterns, routes-by-default rules.
- `examples/tokyo-trip.md` — end-to-end worked example: source emails →
  YAML → all four export variants → `.ics`.
- `scripts/itinerary_utils.py` — lightweight stdlib helpers for deterministic
  chores: Google Maps direction URLs, iCalendar escaping/folding, and `.ics`
  sanity checks. Run with `python3`.

## Core workflow

1. **Collect inputs.** Forwarded emails, PDF confirmations, screenshots,
   manual notes, an existing itinerary if updating.
2. **Extract structured facts.** Supplier, booking refs, travellers,
   date/time/timezone, start/end locations, addresses, check-in/out rules,
   cancellation notes, ticket conditions, contact details, costs.
3. **Classify each item as a node.** Use the type enum in
   `references/node-types.md`.
4. **Group into trip and day structure.** Infer rough destination and date
   range. Assign each node to the correct local day. Place hotel info on the
   relevant nights via `overnight_stay`. Sort timed nodes chronologically.
   Keep untimed nodes in a separate "To schedule / notes" section.
5. **Geocode locations selectively.** Geocode route-critical and share-critical
   locations by default: hotels, airports/stations, meeting venues, reserved
   restaurants, and booked transfers. Geocode optional POIs or every located
   node only when the user asks for a map-rich / route-rich itinerary. Never
   invent coordinates — see `references/routing.md`.
6. **Link nodes in sequence.** Add route links for high-value transitions
   only (airport ↔ hotel, hotel ↔ client office, meeting ↔ important
   dinner, intercity transfers). Don't route every short walk unless asked.
7. **Flag uncertainty.** Missing terminal, address, timezone, passenger
   name, confirmation number, check-in time, or date. Conflicts, duplicates,
   ambiguous hotel nights, ambiguous traveller assignment. Put these in
   "Open Questions / Missing Details".
8. **Produce export variants.** Internal full, team-share, executive
   summary, travel-admin, chat, `.ics` as requested. See
   `references/exports.md` and `references/privacy.md`.

## Output location

Save final deliverables to the user's selected folder or agreed workspace.
Working drafts and intermediate YAML can live in the scratchpad. Use the naming
convention in `references/exports.md`.

When presenting files, use the delivery method your environment supports:

- Chat / messaging environments: send the local file directly using the platform's file-attachment mechanism.
- CLI / desktop environments: provide the absolute file path or a supported local-file link.
- Cloud-doc exports (Google Docs / Drive, etc.): provide the verified share URL.


## Time and timezone conventions

- All `starts_at` / `ends_at` / `due_at` values in the YAML are **ISO 8601
  with an explicit timezone offset**, e.g. `2026-06-12T08:10:00+09:00`.
- For flights and trains that cross a timezone, the `starts_at` offset is
  the **departure** local offset and the `ends_at` offset is the **arrival**
  local offset. Also populate `timezone_start` and `timezone_end` when the
  IANA names differ or when generating `.ics`.
- Each day carries a `local_timezone` (IANA name). It overrides
  `trip.timezone_default` for that day — needed when a trip crosses a
  timezone boundary mid-trip.
- Rendered Markdown uses **24-hour `HH:MM`** in the local timezone of the
  containing day, with the timezone shown in the day heading
  (e.g. `## Day 1 — Friday, 12 Jun 2026 (Asia/Tokyo)`).
- For overnight or red-eye journeys, place the node on the **day of
  departure** in Markdown and add an arrival-time admin note on the next day.

## Status lifecycle (brief)

Each node has a `status` of `confirmed | tentative | cancelled | unknown`.
Default to `confirmed` for items built from confirmations. Use `tentative`
for held or "maybe" items. **Never delete** a cancelled node — set
`status: cancelled` and keep it for the audit trail; rendering hides it from
share variants and strikes it through in the internal version. Full
rendering rules and amendment handling: see `references/node-types.md`.

## OCR and source quality

When extracting from screenshots or scanned PDFs:

- Set `source_item.ocr_quality` to `high`, `medium`, `low`, or `unreadable`.
- List uncertain fields in `source_item.ocr_uncertain_fields`.
- For uncertain fields, leave the field empty and add to "Open Questions",
  or quote what you saw with a `?` prefix (`"?ABC12?"`). Never silently
  normalise.
- If a source is `unreadable`, do not generate nodes from it — ask the user
  to re-send or transcribe.

## Privacy and export variants

Always distinguish the internal full version from shareable variants.
Sensitive fields (payment, passport, loyalty, booking PINs, personal
contacts) are redacted or omitted per the matrix in `references/privacy.md`.
**Defaults:** if the user asks for "the itinerary" without an audience,
default to internal-full and ask before producing a team-share. Never
default to team-share — accidental over-sharing is worse than accidental
over-disclosure to oneself.

## Routing and map links

Use a geocoding/maps tool when available (Nominatim/OSM or a maps MCP). If no
mapping tool is available, leave coordinates empty and use human-readable
addresses or codes in map links.

- Geocode route-critical and share-critical locations by default: hotels,
  airports/stations, meeting venues, reserved restaurants, and booked
  transfers.
- Geocode optional POIs or every located node only when the user asks for a
  map-rich / route-rich itinerary.
- Build Maps URLs using coordinates when available; fall back to URL-encoded
  addresses or IATA codes. Never invent coordinates.
- Route by default only for high-value transitions (see workflow step 6).
- Always keep the human-readable address alongside any coordinate so the
  Markdown stays readable.

Full rules: `references/routing.md`.

## Clarification policy

Ask only when ambiguity changes the itinerary materially.

Ask if:

- Two bookings conflict.
- Traveller assignment is unclear (e.g. one flight, two travellers, only one
  passenger named).
- A hotel booking could be for different nights/travellers.
- A meeting does not specify who from the travel party is attending, or who
  they are meeting with (the two split fields — not the generic
  `participants`).
- A time lacks a timezone in a way that could affect sequence.
- The user requests sharing but the privacy level is unclear.
- A geocoder returns multiple confident matches with no clear winner.
- A source has `ocr_quality: unreadable`.

Don't ask if:

- A sensible default exists and uncertainty can be flagged in "Open
  Questions".
- Missing details are minor.
- The user explicitly asked for a quick draft.

## Common pitfalls

1. **Overbuilding into a full app too early.** Markdown + files + optional
   Google Doc/PDF/.ics export is enough for internal use.
2. **Mixing private and shareable details.** Always produce separate
   internal and team-share variants when exporting for others.
3. **Over-routing every node.** Route only important transitions unless
   asked otherwise.
4. **Ignoring timezones.** Cross-border travel must preserve local times
   and offsets at both ends.
5. **Treating a hotel stay as a single check-in node.** Also point to it via
   per-day `overnight_stay` for each night it covers; don't create one stay
   node per night.
6. **Duplicating updated confirmations.** New emails may be amendments;
   compare provider, ref, date/time, and location before appending. Mark
   the old node `cancelled` and add a private note pointing at the new one.
7. **Forcing untimed POIs into the schedule.** Keep them in optional /
   unscheduled sections unless the user gave a time.
8. **Overclaiming route accuracy.** If a duration is not tool-checked,
   either omit it or label it as an estimate.
9. **Inventing coordinates.** Lat/lon must come from a geocoder. A
   memory-recall coordinate is worse than no coordinate.
10. **Putting a generic `participants` on a meeting and skipping the split
    fields.** Always populate `attending_from_travel_party` and
    `meeting_with` for meeting nodes.
11. **Claiming live facts from static sources.** Do not present route
    duration, venue hours, availability, prices, or flight status as current
    unless a live tool verified them in the current task.

## Verification checklist

Before final output, check:

- [ ] Trip title, date range, destination, and travel party are present or
      explicitly marked unknown.
- [ ] Each day has the right date, a `local_timezone`, and the right
      overnight stay where relevant.
- [ ] Nodes are chronological within each day.
- [ ] Flight/train times preserve local time and timezone at both ends.
- [ ] Hotel check-in/check-out dates match the nights shown via
      `overnight_stay`.
- [ ] `lat`/`lon` come from a geocoder where present; no invented
      coordinates.
- [ ] Important addresses and Maps links are present for high-value
      transitions.
- [ ] Any live status, availability, route duration, opening-hours, or price
      claim is either tool-verified or clearly labelled as source-provided /
      not currently verified.
- [ ] Sensitive details are redacted or omitted from team-share, exec,
      and chat exports per `references/privacy.md`.
- [ ] Cancelled nodes are kept with `status: cancelled`, not deleted.
- [ ] Meeting nodes use `attending_from_travel_party` and `meeting_with`
      only — `participants` is empty for meetings.
- [ ] Open questions are listed rather than hidden.
- [ ] Output file is written to the user's selected folder and verified
      readable (for `.ics`, BEGIN/END blocks balanced).
