# Node Types — Field Reference

This file expands the `nodes:` section of `templates/itinerary-schema.yaml`. The
parent `SKILL.md` only summarises node types; consult this file when you need
the full per-type field list.

All nodes share a base set of fields:

```yaml
id:                   # stable slug, e.g. flight-001
type:                 # see enum below
subtype:              # type-specific refinement
title:                # short human-readable label
status:               # confirmed | tentative | cancelled | unknown
visibility:           # internal | team_share | private | admin_only
starts_at:            # ISO 8601 with offset
ends_at:              # ISO 8601 with offset, if applicable
timezone:             # IANA name for display/local rendering; overrides day local_timezone
timezone_start:       # IANA name for departure/start, mainly cross-timezone travel and .ics
timezone_end:         # IANA name for arrival/end, mainly cross-timezone travel and .ics
location:             # or location_start / location_end for travel/transfer
participants: []      # NOT used for meeting nodes — see `## meeting` for the split fields
notes: ""
private_notes: ""
cost:                 # see schema; null when unknown
source_refs: []
```

Type enum: `travel | stay | meeting | poi | restaurant | transfer | event | admin | free_time | note`.

## Status lifecycle

The `status` field tracks the booking state of a node, not the trip's progress.

| Status      | When to set                                                                 | Rendering rule                                                                 |
|-------------|------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| `confirmed` | Booking is paid and confirmed. Default for nodes built from confirmations.   | Render normally.                                                               |
| `tentative` | Held/optional/awaiting confirmation, or the user said "maybe".               | Render with a `(tentative)` suffix in the title.                               |
| `cancelled` | Booking is cancelled and not being replaced.                                 | Move to a "Cancelled / no longer happening" section at the bottom of the day. Do **not** delete — keep the audit trail. Strike through the title in Markdown. In `.ics`: keep in the **internal-full** export with `STATUS:CANCELLED` for the audit trail; omit from team-share, exec summary, chat, and team-share `.ics`. |
| `unknown`   | The agent could not determine status from the source material.               | Render normally with a flag in "Open Questions / Missing Details".             |

When a node is replaced by an amendment (re-booked flight, hotel night moved),
mark the old node `cancelled`, add a `private_notes` reference to the new
node's `id`, and create the replacement as `confirmed`.

## Visibility lifecycle

The `visibility` field controls which export variants may include a node by
default. It is separate from `status`: a confirmed node can still be private or
admin-only.

| Visibility | Use for | Rendering rule |
|------------|---------|----------------|
| `internal` | Default for normal trip nodes when no audience is specified. | Include in internal full. Include in other variants only if appropriate after privacy redaction. |
| `team_share` | Items the travelling group should see: flights they share, hotels, meetings, dinners, major transfers. | Include in team-share and chat exports after redaction. |
| `private` | Personal side items, sensitive meetings, private notes, or anything the user explicitly marks private. | Include only in internal full unless the user explicitly overrides. |
| `admin_only` | Cancellation deadlines, supplier contacts, expense routing, invoice notes, visa/admin reminders not useful to attendees. | Include in internal full and travel-admin; omit from team-share, exec, chat, and default `.ics`. |

Default new nodes to `internal` unless the source or user intent makes the
sharing scope obvious. If generating a team-share export, promote obviously
shareable logistics (shared hotel, shared flight, team dinner, client meeting)
to `team_share` only when the content itself is safe after redaction.

## `travel`

Flights, trains, ferries, long-distance coaches, car-rental pickups, and
intercity transfers where the journey itself is a scheduled item.

```yaml
type: travel
subtype: flight | train | ferry | coach | car_rental | intercity_transfer
title:
provider:
confirmation_ref:
starts_at:
ends_at:
timezone_start:                # IANA name for departure/start, e.g. Asia/Hong_Kong
timezone_end:                  # IANA name for arrival/end, e.g. Asia/Tokyo
location_start:                # see schema; lat/lon if geocoded
location_end:
participants:
source_refs:
cost:
```

Flight-specific extensions:

```yaml
flight_number:
airline:
booking_ref:
ticket_number:
departure_airport:             # IATA code
arrival_airport:               # IATA code
departure_terminal:
arrival_terminal:
baggage_allowance:
check_in_url:
```

Train-specific extensions:

```yaml
train_number:
operator:
departure_station:
arrival_station:
coach:
seat:
fare_class:
```

## `stay`

Hotels, serviced apartments, Airbnb, guest houses, overnight bases.

```yaml
type: stay
subtype: hotel | serviced_apartment | airbnb | guest_house | other
title:
property_name:
address:
check_in:                      # 24-hour HH:MM local
check_out:                     # 24-hour HH:MM local
nights:                        # integer; derived from check-in to check-out
confirmation_ref:
guests:
night_of:                      # date this stay covers; one stay node per booking, populate overnight_stay per night
cancellation_deadline:
source_refs:
cost:
```

Every stay also populates `overnight_stay` on each day it covers. The single
`stay` node remains the booking-level record; `overnight_stay` is the per-day
display pointer. Do **not** create one `stay` node per night for the same
booking.

## `meeting`

Client meetings, internal meetings, site visits, conferences, workshops, calls.

```yaml
type: meeting
subtype: client_meeting | internal_meeting | site_visit | conference | workshop | call
title:
starts_at:
ends_at:
location:
attending_from_travel_party:   # required if available
meeting_with:                  # external attendees and/or organisation
host_contact:
agenda:                        # optional
materials:
dial_in:                       # for calls / hybrid meetings
```

Meeting nodes **do not use** the base-level `participants` field at all. They
use only the two split fields:

- `attending_from_travel_party` — who from the trip's travel party is attending.
- `meeting_with` — external/client/host attendees or the organisation being met.

Renderers and `.ics` exporters treat an empty `participants` plus a populated
split pair as the canonical meeting shape. Team-share and exec exports depend
on this split — a meeting with `participants` set and the split fields empty
will fail the verification checklist.

## `poi`

Attractions, landmarks, museums, optional sightseeing, non-meal venues.

```yaml
type: poi
subtype: attraction | museum | landmark | shopping | activity | optional
title:
starts_at:                     # optional; untimed POIs live in a notes section
ends_at:                       # optional
location:
ticket_ref:
opening_hours:
notes:
cost:
```

## `restaurant`

Restaurants, cafes, bars, team dinners, hosted meals.

```yaml
type: restaurant
subtype: breakfast | lunch | dinner | coffee | drinks | hosted_meal
title:
starts_at:
ends_at:                       # optional
location:
reservation_ref:
party_size:
under_name:                    # name the reservation is held under
contact:                       # phone for the venue
dress_code:
notes:
cost:
```

## `transfer`

Short transfers between nodes when the movement itself should appear in the
itinerary (and is meaningful enough to schedule).

```yaml
type: transfer
title:
starts_at:                     # optional
ends_at:                       # optional
location_start:
location_end:
mode: taxi | transit | walking | driving | ride_hail | private_car | shuttle
route:                         # see schema
cost:
```

Most short walks should be modelled as a `link.route` between two nodes rather
than a standalone transfer node. Use transfer nodes for booked or scheduled
movements: pre-booked car services, intercity ground transfer between cities,
shuttle to a remote venue.

## `event`

Ticketed events, conferences, performances, games, receptions, ceremonies.

```yaml
type: event
subtype: conference | performance | reception | ceremony | sports | networking | other
title:
starts_at:
ends_at:
location:
ticket_ref:
entry_requirements:            # ID, dress code, arrival window
notes:
cost:
```

## `admin`

Check-in deadlines, visa reminders, luggage storage, expense deadlines,
document submission, travel-admin reminders.

```yaml
type: admin
subtype: check_in_deadline | visa | luggage | expense | document | reminder
title:
due_at:                        # ISO 8601 with offset
owner:                         # who is responsible
notes:
```

## `free_time`

Deliberate open blocks on the schedule.

```yaml
type: free_time
title:
starts_at:
ends_at:
suggestions:                   # optional ideas to fill the block
```

## `note`

Unscheduled notes, risks, reminders, context that does not belong on the
timeline.

```yaml
type: note
title:
body:
```

`visibility` is taken from the base fields (4-value enum). For notes that are
inherently personal (e.g. journal entries, draft commentary), default to
`visibility: private`.

## Anti-examples

Do **not**:

- Use a `meeting` node for "I might grab coffee with a colleague" — that's a
  `restaurant` (coffee) or `note`.
- Create one `stay` node per night for a single hotel booking — model it as one
  `stay` plus per-day `overnight_stay` pointers.
- Set `status: cancelled` and then delete the node — keep cancelled nodes for
  the audit trail; rendering hides them from share variants.
- Fill `participants` for a meeting and leave `attending_from_travel_party` /
  `meeting_with` empty.
- Put a flight crossing midnight on the destination day only — set
  `starts_at` and `ends_at` with their real offsets and let the renderer split.
