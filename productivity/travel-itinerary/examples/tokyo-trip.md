# Worked Example — Tokyo Business Trip

A synthetic end-to-end run: source emails → canonical YAML → all four export
variants. Use this to ground your reasoning when handling a real trip.

The user is **Alice Chan** (Partner). She is travelling with **Bob Lee**
(Manager) to Tokyo for a client meeting at Acme Robotics K.K. Dates:
**12–14 June 2026**.

---

## 1. Input materials (what Alice forwarded)

### Source A — Cathay Pacific outbound confirmation

```text
From: noreply@cathaypacific.com
To: alice.chan@firm.example
Subject: Your booking is confirmed — ABC123

CX548  Fri 12 Jun 2026
Hong Kong (HKG) Terminal 1   →   Tokyo Haneda (HND) Terminal 3
Departs 08:10  Arrives 13:40

Passenger 1: CHAN/ALICE MS    Seat 24A    e-ticket 160-2345678901
Passenger 2: LEE/BOB MR       Seat 24B    e-ticket 160-2345678902

Booking reference: ABC123
Frequent flyer: Marco Polo Club 1234567 (Alice)
Payment: Visa ending 4421
```

### Source B — Cathay Pacific return confirmation

```text
From: noreply@cathaypacific.com
Subject: Your booking is confirmed — ABC123

CX549  Sun 14 Jun 2026
Tokyo Haneda (HND) Terminal 3   →   Hong Kong (HKG) Terminal 1
Departs 16:55  Arrives 20:35
```

### Source C — Hotel confirmation (forwarded)

```text
From: reservations@celestinehotels.jp
Subject: Reservation confirmation — Hotel The Celestine Tokyo Shiba

Guest: Alice Chan (+1 guest)
Check-in: Fri 12 Jun 2026, from 15:00
Check-out: Sun 14 Jun 2026, by 11:00
Room: Twin Deluxe, 2 nights
Confirmation: H-778901
Address: 3-23-1 Shiba, Minato City, Tokyo 105-0014
Rate: JPY 84,000 total (incl. tax). Free cancellation until 10 Jun 23:59 JST.
Payment: Visa ending 4421
```

### Source D — Client meeting invite (Outlook .ics excerpt, paraphrased)

```text
Subject: Acme Robotics × Firm — Q2 Strategy Review
When: Sat 13 Jun 2026, 10:00 – 12:30 JST
Location: Acme Robotics K.K., 6F, 2-7-1 Marunouchi, Chiyoda-ku, Tokyo
Organiser: Yuki Tanaka <y.tanaka@acmerobotics.example>
Attendees: Alice Chan, Bob Lee, Yuki Tanaka, Hiroshi Sato, Mei Yamamoto
Agenda:
  1. Q1 recap (Hiroshi)
  2. Roadmap walkthrough (Mei)
  3. Commercial discussion (Alice & Yuki)
```

### Source E — Restaurant booking (OpenTable confirmation)

```text
Restaurant: Sushi Saito Annex (casual)
Date: Sat 13 Jun 2026, 19:00
Party: 5
Under name: Alice Chan
Address: 1-4-1 Roppongi, Minato City, Tokyo
Reservation ref: OT-99221
Dress code: smart casual
```

### Source F — Manual note from Alice

> "Bob wants to see TeamLab Borderless on Sunday morning before we fly out if
> we can squeeze it in. Also remind me to do online check-in 24h before
> return."

---

## 2. Canonical YAML (`trip.yaml`)

After geocoding via Nominatim, normalising times, and applying privacy
defaults, the structured representation:

```yaml
trip:
  id: 2026-06-tokyo-acme
  title: Tokyo — Acme Robotics Q2 Review
  purpose: Client meeting with Acme Robotics K.K., Q2 strategy review and commercial discussion.
  destination:
    rough: Tokyo, Japan
    cities: [Tokyo]
    country: Japan
  date_range:
    start: 2026-06-12
    end: 2026-06-14
  timezone_default: Asia/Tokyo
  travel_party:
    - name: Alice Chan
      role: Partner
      email: alice.chan@firm.example
      notes: Lead for commercial discussion.
    - name: Bob Lee
      role: Manager
      notes: Roadmap walkthrough lead.
  privacy:
    sensitive_fields:
      - payment_details
      - personal_emails
      - passport_numbers
      - loyalty_numbers
      - booking_pin
    share_policy: hide sensitive fields in team-share export
  source_items:
    - source_id: email-001
      type: email
      received_at: 2026-05-20T09:14:00+08:00
      subject: "Your booking is confirmed — ABC123"
      sender: noreply@cathaypacific.com
      ocr_quality: high
    - source_id: email-002
      type: email
      sender: noreply@cathaypacific.com
      ocr_quality: high
    - source_id: email-003
      type: email
      sender: reservations@celestinehotels.jp
      ocr_quality: high
    - source_id: invite-001
      type: email
      sender: y.tanaka@acmerobotics.example
      ocr_quality: high
    - source_id: email-004
      type: email
      sender: noreply@opentable.com
      ocr_quality: high
    - source_id: note-001
      type: manual_note
  cost_summary:
    currency: JPY
    estimated_total: null   # not all costs known yet
    by_category:
      stay: 84000
      travel: null
      meals: null
      events: null
      other: null

  days:

    # ── Day 1: Arrival ─────────────────────────────────────────────────────
    - date: 2026-06-12
      local_timezone: Asia/Tokyo
      title: Arrival and check-in
      overnight_stay:
        node_id: stay-001
        hotel_name: Hotel The Celestine Tokyo Shiba
        address: 3-23-1 Shiba, Minato City, Tokyo 105-0014
        check_in: "15:00"
        check_out: "11:00"
        confirmation_ref: H-778901
        shareable: true
      day_notes:
        - First day arrival; keep schedule light.
      nodes:
        - id: flight-001
          type: travel
          subtype: flight
          title: CX548 HKG → HND
          status: confirmed
          visibility: team_share
          starts_at: 2026-06-12T08:10:00+08:00
          ends_at:   2026-06-12T13:40:00+09:00
          timezone: Asia/Tokyo
          location_start:
            name: Hong Kong International Airport
            code: HKG
            terminal: T1
            lat: 22.3080
            lon: 113.9185
          location_end:
            name: Tokyo Haneda Airport
            code: HND
            terminal: T3
            lat: 35.5494
            lon: 139.7798
          participants: [Alice Chan, Bob Lee]
          provider: Cathay Pacific
          confirmation_ref: ABC123
          cost:
            amount: null
            currency: HKD
            payer: Firm
            billable_to: "Acme Robotics — Q2"
            payment_method_redacted: "Visa **** 4421"
          private_notes: "Marco Polo Club number stored separately; do not include in team-share."
          source_refs: [email-001]
        - id: transfer-001
          type: transfer
          title: HND → Hotel
          status: confirmed
          visibility: team_share
          starts_at: 2026-06-12T14:15:00+09:00
          location_start:
            name: Tokyo Haneda Airport Terminal 3
            code: HND
            lat: 35.5494
            lon: 139.7798
          location_end:
            name: Hotel The Celestine Tokyo Shiba
            address: 3-23-1 Shiba, Minato City, Tokyo 105-0014
            lat: 35.6510
            lon: 139.7470
          mode: taxi
          route:
            mode: driving
            estimated_duration: "35–45 min"
            distance: "18 km"
            maps_url: "https://www.google.com/maps/dir/?api=1&origin=35.5494,139.7798&destination=35.6510,139.7470&travelmode=driving"
            checked_at: 2026-05-20T09:30:00+08:00
        - id: stay-001
          type: stay
          subtype: hotel
          title: Hotel check-in — Hotel The Celestine Tokyo Shiba
          status: confirmed
          visibility: team_share         # shared room logistics
          starts_at: 2026-06-12T15:00:00+09:00
          ends_at:   2026-06-14T11:00:00+09:00
          property_name: Hotel The Celestine Tokyo Shiba
          address: 3-23-1 Shiba, Minato City, Tokyo 105-0014
          check_in: "15:00"
          check_out: "11:00"
          nights: 2
          confirmation_ref: H-778901
          guests: [Alice Chan, Bob Lee]
          cancellation_deadline: 2026-06-10T23:59:00+09:00
          location:
            name: Hotel The Celestine Tokyo Shiba
            address: 3-23-1 Shiba, Minato City, Tokyo 105-0014
            lat: 35.6510
            lon: 139.7470
          cost:
            amount: 84000
            currency: JPY
            payer: Firm
            billable_to: "Acme Robotics — Q2"
            payment_method_redacted: "Visa **** 4421"
          source_refs: [email-003]
        - id: free-001
          type: free_time
          title: Evening — settle in / casual dinner near hotel
          visibility: internal           # Alice's personal block; not promoted to team-share
          starts_at: 2026-06-12T18:00:00+09:00
          ends_at:   2026-06-12T22:00:00+09:00

    # ── Day 2: Client meeting day ─────────────────────────────────────────
    - date: 2026-06-13
      local_timezone: Asia/Tokyo
      title: Acme Robotics client meeting + team dinner
      overnight_stay:
        node_id: stay-001
        hotel_name: Hotel The Celestine Tokyo Shiba
        address: 3-23-1 Shiba, Minato City, Tokyo 105-0014
        shareable: true
      nodes:
        - id: meeting-001
          type: meeting
          subtype: client_meeting
          title: Acme Robotics × Firm — Q2 Strategy Review
          status: confirmed
          visibility: team_share         # Bob is attending
          starts_at: 2026-06-13T10:00:00+09:00
          ends_at:   2026-06-13T12:30:00+09:00
          location:
            name: Acme Robotics K.K.
            address: 6F, 2-7-1 Marunouchi, Chiyoda-ku, Tokyo
            lat: 35.6824
            lon: 139.7649
          attending_from_travel_party: [Alice Chan, Bob Lee]
          meeting_with:
            - name: Yuki Tanaka
              role: Acme — Head of Strategy
              email: y.tanaka@acmerobotics.example
            - name: Hiroshi Sato
              role: Acme — Q1 recap lead
            - name: Mei Yamamoto
              role: Acme — Roadmap lead
          host_contact: Yuki Tanaka <y.tanaka@acmerobotics.example>
          agenda: "Q1 recap (Hiroshi) → roadmap walkthrough (Mei) → commercial (Alice & Yuki)."
          source_refs: [invite-001]
        - id: restaurant-001
          type: restaurant
          subtype: lunch
          title: Working lunch near Marunouchi
          status: tentative
          visibility: team_share
          starts_at: 2026-06-13T13:00:00+09:00
          location:
            name: TBC — Yuki to suggest venue
          participants: [Alice Chan, Bob Lee, Yuki Tanaka]
          notes: "Yuki offered to pick a venue near the office; awaiting confirmation."
        - id: restaurant-002
          type: restaurant
          subtype: dinner
          title: Team dinner — Sushi Saito Annex
          status: confirmed
          visibility: team_share
          starts_at: 2026-06-13T19:00:00+09:00
          location:
            name: Sushi Saito Annex
            address: 1-4-1 Roppongi, Minato City, Tokyo
            lat: 35.6627
            lon: 139.7307
          reservation_ref: OT-99221
          party_size: 5
          under_name: Alice Chan
          dress_code: smart casual
          participants: [Alice Chan, Bob Lee, Yuki Tanaka, Hiroshi Sato, Mei Yamamoto]
          cost:
            amount: null
            currency: JPY
            payer: Firm
            billable_to: "Acme Robotics — Q2"
          source_refs: [email-004]

      links:
        - from_node_id: meeting-001
          to_node_id: restaurant-002
          relationship: sequence
          route:
            mode: transit
            estimated_duration: "15 min"
            maps_url: "https://www.google.com/maps/dir/?api=1&origin=35.6824,139.7649&destination=35.6627,139.7307&travelmode=transit"
            checked_at: 2026-05-20T09:30:00+08:00

    # ── Day 3: Optional sightseeing + return ──────────────────────────────
    - date: 2026-06-14
      local_timezone: Asia/Tokyo
      title: Optional sightseeing and return to HKG
      nodes:
        - id: poi-001
          type: poi
          subtype: attraction
          title: TeamLab Borderless (optional, only if time allows)
          status: tentative
          visibility: team_share         # Bob requested it
          location:
            name: teamLab Borderless
            address: Azabudai Hills, Minato City, Tokyo
            lat: 35.6586
            lon: 139.7454
          opening_hours: "10:00 – 21:00"
          notes: "Requires pre-booked ticket; check availability the day before. Skip if morning runs late."
          source_refs: [note-001]
        - id: admin-001
          type: admin
          subtype: check_in_deadline
          title: Online check-in opens for CX549
          visibility: admin_only         # personal reminder; not on Bob's team-share
          due_at: 2026-06-13T16:55:00+09:00
          owner: Alice Chan
          notes: "24h before departure."
          source_refs: [note-001]
        - id: transfer-002
          type: transfer
          title: Hotel → HND
          status: confirmed
          visibility: team_share
          starts_at: 2026-06-14T14:00:00+09:00
          location_start:
            name: Hotel The Celestine Tokyo Shiba
            lat: 35.6510
            lon: 139.7470
          location_end:
            name: Tokyo Haneda Airport Terminal 3
            code: HND
            lat: 35.5494
            lon: 139.7798
          mode: taxi
          route:
            mode: driving
            estimated_duration: "35–50 min (weekend traffic)"
            distance: "18 km"
            maps_url: "https://www.google.com/maps/dir/?api=1&origin=35.6510,139.7470&destination=35.5494,139.7798&travelmode=driving"
            checked_at: 2026-05-20T09:30:00+08:00
        - id: flight-002
          type: travel
          subtype: flight
          title: CX549 HND → HKG
          status: confirmed
          visibility: team_share
          starts_at: 2026-06-14T16:55:00+09:00
          ends_at:   2026-06-14T20:35:00+08:00
          timezone: Asia/Hong_Kong
          location_start:
            name: Tokyo Haneda Airport
            code: HND
            terminal: T3
            lat: 35.5494
            lon: 139.7798
          location_end:
            name: Hong Kong International Airport
            code: HKG
            terminal: T1
            lat: 22.3080
            lon: 113.9185
          participants: [Alice Chan, Bob Lee]
          provider: Cathay Pacific
          confirmation_ref: ABC123
          source_refs: [email-002]
```

---

## 3. Internal full Markdown (Alice's own copy)

```markdown
# Tokyo — Acme Robotics Q2 Review

**Dates:** 2026-06-12 – 2026-06-14  
**Destination:** Tokyo, Japan  
**Travel party:** Alice Chan (Partner), Bob Lee (Manager)  
**Purpose:** Client meeting with Acme Robotics K.K., Q2 strategy review.  
**Prepared:** 2026-05-20

## Quick Summary

- **Hotel / base:** Hotel The Celestine Tokyo Shiba (12–14 Jun, 2 nights)
- **Arrival:** CX548 HKG 08:10 → HND 13:40, Fri 12 Jun
- **Departure:** CX549 HND 16:55 → HKG 20:35, Sun 14 Jun
- **Main meeting location:** Acme Robotics K.K., Marunouchi
- **Notes:** Light schedule Day 1; client meeting + dinner Day 2; optional teamLab Sunday morning.

## Open Questions / Missing Details

- [ ] Lunch venue on Sat 13 Jun — Yuki to propose.
- [ ] Flight cost in HKD — not on the confirmation; pull from finance.
- [ ] teamLab Borderless tickets — confirm availability for Sun morning.

## Day 1 — Friday, 12 Jun 2026 (Asia/Tokyo)

**Overnight stay:** Hotel The Celestine Tokyo Shiba, 3-23-1 Shiba, Minato City. Check-in from 15:00.

### 08:10 — CX548 HKG → HND
- **Type:** travel / flight
- **Location:** HKG T1 → HND T3
- **Participants:** Alice Chan, Bob Lee
- **Reference:** ABC123
- **Cost:** TBC (Visa **** 4421, billable to Acme Robotics — Q2)
- **Notes:** Arrives Tokyo 13:40 local.

### 14:15 — Transfer HND → Hotel
- **From:** HND Terminal 3
- **To:** Hotel The Celestine Tokyo Shiba
- **Estimated travel:** 35–45 min by taxi (~18 km)
- **Map:** [open in Google Maps](https://www.google.com/maps/dir/?api=1&origin=35.5494,139.7798&destination=35.6510,139.7470&travelmode=driving)

### 15:00 — Hotel check-in — Hotel The Celestine Tokyo Shiba
- **Type:** stay / hotel
- **Location:** 3-23-1 Shiba, Minato City
- **Reference:** H-778901
- **Cost:** JPY 84,000 (Visa **** 4421, billable to Acme Robotics — Q2)
- **Notes:** Twin Deluxe, 2 nights. Free cancellation until 10 Jun 23:59 JST.

### 18:00–22:00 — Free time / casual dinner near hotel

## Day 2 — Saturday, 13 Jun 2026 (Asia/Tokyo)

**Overnight stay:** Hotel The Celestine Tokyo Shiba.

### 10:00 — Acme Robotics × Firm — Q2 Strategy Review
- **Type:** meeting / client_meeting
- **Location:** Acme Robotics K.K., 6F, 2-7-1 Marunouchi, Chiyoda-ku
- **Attending from our side:** Alice Chan, Bob Lee
- **Meeting with:** Yuki Tanaka (Head of Strategy), Hiroshi Sato, Mei Yamamoto
- **Host contact:** Yuki Tanaka <y.tanaka@acmerobotics.example>
- **Agenda:** Q1 recap (Hiroshi) → roadmap walkthrough (Mei) → commercial (Alice & Yuki).
- **Map:** [open in Google Maps](https://www.google.com/maps/search/?api=1&query=35.6824,139.7649)

### 13:00 — Working lunch near Marunouchi *(tentative)*
- **Participants:** Alice, Bob, Yuki
- **Notes:** Yuki to pick venue.

### 19:00 — Team dinner — Sushi Saito Annex
- **Type:** restaurant / dinner
- **Location:** 1-4-1 Roppongi, Minato City
- **Reservation:** OT-99221, under "Alice Chan", party of 5
- **Dress code:** smart casual
- **Map:** [open in Google Maps](https://www.google.com/maps/search/?api=1&query=35.6627,139.7307)

### Transfer / route to next item (meeting → dinner)
- **From:** Acme Robotics, Marunouchi
- **To:** Sushi Saito Annex, Roppongi
- **Estimated travel:** ~15 min by transit
- **Map:** [directions](https://www.google.com/maps/dir/?api=1&origin=35.6824,139.7649&destination=35.6627,139.7307&travelmode=transit)

## Day 3 — Sunday, 14 Jun 2026 (Asia/Tokyo)

### Morning — teamLab Borderless *(optional, tentative)*
- **Type:** poi / attraction
- **Location:** Azabudai Hills, Minato City
- **Hours:** 10:00 – 21:00
- **Notes:** Pre-book ticket the night before; skip if morning runs late.

### 14:00 — Transfer Hotel → HND
- **Estimated travel:** 35–50 min by taxi (weekend traffic)
- **Map:** [directions](https://www.google.com/maps/dir/?api=1&origin=35.6510,139.7470&destination=35.5494,139.7798&travelmode=driving)

### 16:55 — CX549 HND → HKG
- **Type:** travel / flight
- **Reference:** ABC123
- **Notes:** Arrives HKG 20:35 local.

### Admin reminders
- [ ] **Sat 13 Jun, 16:55 JST** — online check-in opens for CX549 (Alice).

## Reference Details

### Flights
- CX548 Fri 12 Jun, HKG T1 08:10 → HND T3 13:40. Ref ABC123. Seats 24A/24B.
- CX549 Sun 14 Jun, HND T3 16:55 → HKG T1 20:35. Ref ABC123.

### Accommodation
- Hotel The Celestine Tokyo Shiba, 3-23-1 Shiba, Minato City. 12–14 Jun, 2 nights, Twin Deluxe. Ref H-778901. JPY 84,000.

### Restaurants / Events
- Sat 13 Jun 19:00 — Sushi Saito Annex, Roppongi. Ref OT-99221.

## Source Notes
- 5 emails + 1 invite + 1 manual note from Alice. Raw payment refs redacted to last 4.
```

---

## 4. Team-share Markdown (for Bob)

Same skeleton, with redactions applied:

- Drop **Source Notes** section.
- Drop confirmation refs that don't help Bob (hotel ref kept because he may
  need to check in; flight ref kept because it's the same PNR for both).
- Drop cost lines.
- Drop **Open Questions** unless they concern Bob.
- Drop the cancellation deadline.

```markdown
# Tokyo — Acme Robotics Q2 Review

**Dates:** Fri 12 – Sun 14 Jun 2026  
**Travel party:** Alice Chan, Bob Lee  
**Purpose:** Client meeting with Acme Robotics K.K.

## Quick Summary
- **Hotel:** Hotel The Celestine Tokyo Shiba, 3-23-1 Shiba, Minato City (2 nights)
- **Outbound:** CX548 HKG 08:10 → HND 13:40, Fri 12 Jun. Seats 24A/24B. Ref ABC123.
- **Return:** CX549 HND 16:55 → HKG 20:35, Sun 14 Jun. Ref ABC123.

## Day 1 — Fri 12 Jun
- 08:10 — CX548 HKG T1 → HND T3 (arr 13:40 JST).
- 14:15 — Taxi HND → hotel (~35–45 min). [Map](https://www.google.com/maps/dir/?api=1&origin=35.5494,139.7798&destination=35.6510,139.7470&travelmode=driving)
- 15:00 — Check in at Celestine Tokyo Shiba (ref H-778901).
- Evening — free / dinner near hotel.

## Day 2 — Sat 13 Jun
- 10:00 — Acme Robotics × Firm Q2 review, 6F, 2-7-1 Marunouchi, Chiyoda-ku.
  Attending: Alice, Bob. With: Yuki Tanaka, Hiroshi Sato, Mei Yamamoto.
- 13:00 — Working lunch with Yuki *(venue TBC)*.
- 19:00 — Team dinner, Sushi Saito Annex, 1-4-1 Roppongi (smart casual).
  Reservation under Alice Chan.

## Day 3 — Sun 14 Jun
- Morning — optional teamLab Borderless (Azabudai Hills).
- 14:00 — Taxi hotel → HND.
- 16:55 — CX549 HND T3 → HKG T1 (arr 20:35 HKT).

**Maps for the main legs:** see the Day 1/2/3 links above. Shout if you want anything added.
```

---

## 5. Executive summary

```markdown
# Tokyo — Acme Robotics Q2 Review — 12–14 Jun 2026

**Destination:** Tokyo, Japan  
**Travel party:** Alice Chan, Bob Lee  
**Purpose:** Q2 strategy review and commercial discussion with Acme Robotics K.K.

## Schedule

| Date         | AM                              | PM                              | Overnight                       |
|--------------|---------------------------------|---------------------------------|---------------------------------|
| Fri 12 Jun   | CX548 HKG → HND (08:10–13:40)   | Check in, settle               | Celestine Tokyo Shiba           |
| Sat 13 Jun   | Acme client meeting (10:00)     | Team dinner, Sushi Saito Annex | Celestine Tokyo Shiba           |
| Sun 14 Jun   | Optional teamLab Borderless     | CX549 HND → HKG (16:55–20:35)  | —                               |

## Key meetings
- Sat 13 Jun 10:00 — Acme Robotics K.K. @ Marunouchi, Chiyoda-ku.

## Logistics
- **Arrival:** CX548, 13:40 HND T3.
- **Departure:** CX549, 16:55 HND T3.
- **Hotel:** Hotel The Celestine Tokyo Shiba, Minato City.
```

---

## 6. Chat-ready (for WhatsApp)

```text
Tokyo — Acme Robotics Q2 — 12–14 Jun

Fri 12 Jun
• 08:10 CX548 HKG → HND (arr 13:40 JST)
• 15:00 Check in — Celestine Tokyo Shiba
• Evening free

Sat 13 Jun
• 10:00 Acme client meeting, Marunouchi
• 13:00 Working lunch with Yuki (venue TBC)
• 19:00 Team dinner — Sushi Saito Annex, Roppongi
• Overnight: Celestine Tokyo Shiba

Sun 14 Jun
• AM optional teamLab Borderless
• 14:00 taxi → HND
• 16:55 CX549 HND → HKG (arr 20:35 HKT)

Hotel: 3-23-1 Shiba, Minato City. See ya at HKG T1 06:30.
```

---

## 7. `.ics` (calendar) — first VEVENT shown in full

The full file would contain a `VTIMEZONE` block for `Asia/Tokyo` and
`Asia/Hong_Kong`, then one `VEVENT` per timed node plus one `VTODO` for the
online-check-in admin reminder.

```ics
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//travel-itinerary skill//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH

BEGIN:VTIMEZONE
TZID:Asia/Tokyo
BEGIN:STANDARD
DTSTART:19700101T000000
TZOFFSETFROM:+0900
TZOFFSETTO:+0900
TZNAME:JST
END:STANDARD
END:VTIMEZONE

BEGIN:VTIMEZONE
TZID:Asia/Hong_Kong
BEGIN:STANDARD
DTSTART:19700101T000000
TZOFFSETFROM:+0800
TZOFFSETTO:+0800
TZNAME:HKT
END:STANDARD
END:VTIMEZONE

BEGIN:VEVENT
UID:flight-001@travel-itinerary
DTSTAMP:20260520T013000Z
DTSTART;TZID=Asia/Hong_Kong:20260612T081000
DTEND;TZID=Asia/Tokyo:20260612T134000
SUMMARY:CX548 HKG → HND
LOCATION:HKG T1 → HND T3
DESCRIPTION:Cathay Pacific CX548. Ref ABC123. Seats 24A/24B.
CATEGORIES:Travel,Flight
STATUS:CONFIRMED
END:VEVENT

BEGIN:VTODO
UID:admin-001@travel-itinerary
DTSTAMP:20260520T013000Z
DUE;TZID=Asia/Tokyo:20260613T165500
SUMMARY:Online check-in opens for CX549
STATUS:NEEDS-ACTION
END:VTODO

END:VCALENDAR
```

---

## What this example demonstrates

- Every node type the skill defines except `event` (no ticketed event on this
  trip).
- A `tentative` lunch and `tentative` POI, plus a `confirmed` everything else
  — see how the renderer treats them.
- Cross-timezone flights with explicit offsets on both ends, and how `.ics`
  encodes them with `TZID=` plus `VTIMEZONE` blocks.
- Coordinate-based Maps URLs (preferred form) wherever Nominatim resolved a
  venue, including airport terminals.
- A redacted payment method (`Visa **** 4421`) instead of a full PAN.
- Reuse of one `stay` node across two days via the per-day `overnight_stay`
  pointer.
- An admin `VTODO` for the online-check-in reminder.
- Open questions captured in the internal version but dropped from the
  team-share, exec, and chat variants.
- A spread of `visibility` values demonstrating the share-filter:
  `team_share` on most shared logistics and meetings, `admin_only` on the
  personal check-in reminder, and `internal` on Alice's free-time block.
