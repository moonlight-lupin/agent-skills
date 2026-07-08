# Routing, Coordinates, and Map Links

This file defines how the skill geocodes locations, builds Maps URLs, and
decides when to add routing between nodes. Use a mapping/geocoding tool
(Nominatim/OSM, a maps MCP, or equivalent) when available. If no tool is
available, leave coordinates empty and use addresses or location codes in map
links. The hierarchy below is mandatory.

## Coordinate hierarchy

Do not geocode every possible location by default. Geocode selectively so the
itinerary remains fast, low-noise, and focused on useful routes.

### Geocode by default

Attempt to populate `lat` and `lon` for route-critical and share-critical
locations:

- Hotels / overnight bases.
- Airports and major train stations, especially when used for arrival or
  departure.
- Meeting venues and client offices.
- Reserved restaurants or hosted meals.
- Booked transfers or scheduled intercity ground movements.

### Geocode only when useful or requested

Geocode these only if they are used in a route, appear in a map-rich export, or
the user explicitly asks for fuller mapping:

- Optional POIs and sightseeing ideas.
- Untimed attractions.
- Admin reminders with locations.
- Vague areas such as "Ginza" or "near the station".

### Decision tree

For locations selected for geocoding:

1. **Geocode via available tool.** Call Nominatim/OSM (or the maps MCP) with
   the full address. On a confident match, store `lat`, `lon`, and the
   `osm_id` (for traceability). This is the default path.
2. **No tool available, or no confident match.** Leave `lat` and `lon` as
   `null`. Use the human-readable address in any Maps URLs and add an entry
   to **Open Questions / Missing Details** so the user can confirm the venue.
3. **Never invent coordinates.** A "looks about right" lat/lon from memory is
   worse than no coordinate at all. If the geocoder returns multiple
   candidates with no clear winner (e.g. "St. Regis" matches in 30 cities),
   ask the user to disambiguate rather than picking one.

Always keep the human-readable address alongside coordinates. The Markdown
must remain readable even if the URL is ugly or coordinate-based.

## Airports, stations, and codes

For airports and major train stations, prefer the IATA / station code as the
machine-readable identifier and resolve coordinates separately:

- IATA airport codes: `HKG`, `HND`, `SIN`.
- IATA station codes / national rail codes where applicable.

Coordinates for an airport should point to the **terminal** the traveller is
using, not the airport centroid, when the terminal is known.

## Google Maps URL patterns

Two patterns. Prefer pattern A whenever lat/lon are known.

### A. Coordinate-based (preferred when geocoded)

```text
https://www.google.com/maps/dir/?api=1
  &origin=35.5494,139.7798
  &destination=35.6586,139.7454
  &travelmode=driving
```

(Render as a single line — wrapping shown only for readability.)

### B. Address / place-based (fallback)

URL-encode the full address. Spaces → `+`, other special characters via
percent-encoding. Airport codes and clean place names work without encoding.

```text
https://www.google.com/maps/dir/?api=1
  &origin=HND
  &destination=Hotel+The+Celestine+Tokyo+Shiba,+Minato+City,+Tokyo
  &travelmode=transit
```

`travelmode` is one of `driving | walking | transit | bicycling`. Choose
based on `route.mode`:

| `route.mode` value     | `travelmode` |
|------------------------|--------------|
| `driving`              | driving      |
| `taxi`, `ride_hail`, `private_car`, `shuttle` | driving |
| `transit`              | transit      |
| `walking`              | walking      |
| `unknown` or missing   | driving      |

After building the URL, set `route.checked_at` to the current ISO 8601
timestamp to record when it was last validated. Only write a route duration or
distance if a routing tool actually returned one, or explicitly label it as an
estimate.

For deterministic URL generation, you may use the helper script. Paths
throughout this skill are relative to the skill root (the directory containing
`SKILL.md`); resolve `$SKILL_DIR/scripts/itinerary_utils.py` for your
environment, or `cd` into the skill root before invoking:

```bash
python3 scripts/itinerary_utils.py \
  maps-url --origin "HND" \
  --destination "Hotel The Celestine Tokyo Shiba" \
  --mode transit
```

## Distance and duration estimates

When a routing tool returns a distance/duration, store it verbatim in
`route.distance` and `route.estimated_duration`. When no tool is available:

- Skip the estimate and let the URL speak for itself. Don't write "≈ 30 min"
  unless something actually computed it.
- If the user asks for a guess, label it explicitly: `"~30–45 min (estimate,
  not tool-checked)"`.

## When to add routes by default

Do **not** add a route for every gap between nodes. Add by default only for
high-value transitions:

- Airport / train station ↔ hotel.
- Hotel ↔ main client office / primary conference venue.
- Meeting → important dinner (where lateness matters).
- Intercity transfers (city A hotel → city B hotel).
- The morning-of return leg: hotel → departure airport.

Skip by default:

- Movements ≤ 5 minutes' walk between adjacent nodes in the same building or
  district.
- Untimed POIs.
- Anywhere the user has already given the route in source notes.

Ask the user if they want exhaustive routing across every node — don't assume.

## Cross-timezone and overnight journeys

For a flight or train that crosses a time zone:

- `starts_at` carries the **departure timezone offset**.
- `ends_at` carries the **arrival timezone offset**.
- Populate `timezone_start` with the departure IANA timezone and `timezone_end`
  with the arrival IANA timezone when known. This is especially important for
  `.ics` generation, where `TZID` values must match the local wall-clock time.
- Place the scheduled travel node on the **day of departure** in the rendered Markdown. This keeps the itinerary aligned with when the traveller needs to act.
- If the journey arrives on a different local calendar day, add a lightweight arrival note on the arrival day so the destination-day schedule remains clear.

For an overnight journey (sleeper train, red-eye flight):

- Place the node on the day of **departure** in the rendered Markdown.
- Add an `admin` note on the day of arrival summarising the arrival time.
- In the `.ics`, the single VEVENT spans the real ISO 8601 range — calendar clients will display it correctly across the midnight boundary.

## Geocoding sanity checks

Before trusting a Nominatim/OSM result:

- Confirm the result's country/region matches the trip destination. A hotel
  named "The Westin" might match in Tokyo, Singapore, and Boston — verify the
  country before storing.
- Prefer results with `osm_type: way` or `relation` over `node` for large
  venues (terminals, campuses), since a node may represent a single entrance.
- If the address contains a unit/suite, drop it for the geocode query but
  keep it in the human-readable `address` field.
