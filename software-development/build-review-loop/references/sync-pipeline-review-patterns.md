# Sync-pipeline review patterns (app ↔ external source of truth)

Depth for reviewing code that mirrors an external store (Google Sheets, an
exchange, a SaaS API) as the source of truth, with import / export / clear
operations. These five bug classes survived an initial build and one full
dual-review fix round before a confirmation pass caught them — reviewers
should probe for them explicitly, and briefs for sync features should
pre-empt them.

## Contents

- Locking
- Status-flag hygiene
- Idempotent append + reconcile
- Source-of-truth cell semantics
- Severity adjudication vs the live source of truth
- Deploy topology (tunnel + systemd + subdomain routing)
- Confirm-loop convergence signature (5-round case)
- PDPA / PII in check-in UIs
- Auth surface

## Locking

- **Fetch inside the lock.** Any fetch whose snapshot feeds a locked write
  must run inside the same lock. Fetch-before-lock reintroduces the race the
  lock exists to close: a destructive operation (clear) can commit between
  fetch and apply, and the stale snapshot then re-imports the cleared state.
  Sync operations are rare staff actions — holding the lock across
  fetch+apply is acceptable; a resurrected flag is not.
- **One writer lock across every mutating surface** — import, export, clear,
  and user mutations must serialize against each other, and read-only
  surfaces must either share the lock or fail fast (409 busy, retry) during a
  destructive window. Document that a threading.Lock is process-local; a
  multi-worker deployment needs a cross-process lock before this guarantee
  is real.

## Status-flag hygiene

- **Scope a bulk status-clear to the exact records processed in this run**
  (the snapshot IDs actually appended/written), never a blanket
  `UPDATE ... SET pending=0 WHERE pending=1`. Records that arrive between
  snapshot and update get their pending flag cleared without ever being
  processed — and are then stuck forever. Regression test: register a record
  mid-export; it must still carry the pending flag and export on the next
  run.
- **Destructive clears exclude retained history** (removed/flagged rows) in
  both the DB `WHERE` clause and the boundary computation for the external
  range. Compute the boundary from CURRENT live data, not retained history —
  a boundary derived from history can span rows the app no longer owns and
  wipe other parties' cells.

## Idempotent append + reconcile

- **Reconcile before append.** Before appending, search the external store
  for evidence the row already exists (stable marker text, then content
  identity such as name+category). An append that committed but whose
  response was lost must not produce a duplicate on retry — and an
  intervening import that created the same record under a different key must
  not become a second row. Reconcile must match by content identity as a
  fallback when the marker is missing.
- **Write any row marker AFTER field placements, or reserve its index.** A
  placement loop writing mapped fields into a dynamically-sized row will
  overwrite a marker written earlier into `row[0]` whenever a mapped field's
  resolved index is also 0 (e.g. the Name header sits in column A). Verified
  reproduction: marker written first, name placement last → marker replaced
  by the guest name. Write the marker last, or skip placements that collide
  with the marker index.
- **Skipping a placement is not discarding it.** The natural fix to the
  marker collision — `if index == marker_index: continue` — silently DROPS
  the displaced value (the guest name vanishes from the appended row).
  Verify both properties in the regression test: marker present AND every
  placement present. If index 0 is claimed by a placement, the marker must
  move (e.g. last column), not the placement disappear.
- **Reconcile that avoids a duplicate append but leaves two active records
  is incomplete.** When an import created the same party under a different
  key before export ran, clearing the orphan's pending flag leaves its
  future mutations never exporting (its key never matches the adopter) and
  both records visible to staff. Merge instead: adopt the record whose key
  matches the external store, carry the orphan's flags onto it (timestamp-
  newer wins), soft-delete the orphan (removed=1), preserve its audit
  trail. Test: two-phase fixture → exactly ONE active record after the
  next export, flags exported, audit events intact.
- **Close both sides of a merge/export window in the same round.** A merge
  that sets the adopter's pending flag is only half the fix when the merge
  runs AFTER the flag-export pass (flags land one cycle late) AND the
  import's blank-cell clear does not honor the pending flag (a stale
  snapshot in that window wipes the merged flag). Two cooperating gaps —
  ordering and clear-semantics — need both closed; fixing either alone
  fails the next confirmation round. Also verify import does not ingest the
  reconcile marker string as a field value (a `door:`/`gid…` marker parked
  in a name column gets upserted as the guest name); skip marker-shaped
  values before upsert.
- **Append rows built from the fetched header mapping**, never a fixed
  column layout — the external layout can reorder between runs.

## Source-of-truth cell semantics

- Decide and pin with tests: does a blank external cell mean "no data" or
  "clear the local value"? A `if not cell: return` early-return silently
  PRESERVES stale local state (a locally-set flag survives a blanked cell).
  For sheet-wins semantics, blank must clear. State the choice in the brief;
  a test must pin it either way.
- **"Value was inferred" flags are per-field, never per-record.** A single
  boolean covering N independent fields blanks all N in the UI when one is
  missing (adults blank + children=1 rendered as both unknown). Add one
  flag per field (additive columns with defaults; keep the old column for
  compatibility), set each independently, render `–` per-field.
- **Sheet-wins blanks meet pending exports.** The blank-cell clearing rule
  needs a pending-export exception: a locally-set flag whose export has not
  landed yet would be wiped by the next import's stale blank snapshot.
  Blank clears only rows WITHOUT a pending export (`AND needs_export = 0`
  in the clearing UPDATE); a non-blank sheet cell (staff ticked on the
  sheet) still wins over pending local state. Pair this with the
  merge-window rule above — they are two halves of the same race.

## Severity adjudication vs the live source of truth

Before accepting a reviewer's severity on a data-shape finding, read the
ACTUAL production data once (fetch the live header/rows). A real code defect
whose trigger case cannot occur with the live layout (e.g. the collision
requires a header position the production sheet never uses) is hardening,
not ship-blocking — classify it so, fix it for reorder-resilience, and say
so in the synthesis. The distinction matters both ways: a "cosmetic" finding
on a field staff tap hundreds of times on the day is not cosmetic.

## Deploy topology (tunnel + systemd + subdomain routing)

- **A running tunnel's ingress is extensible without new tunnels or
  credentials**: append a hostname entry to the local `config.yml`, restart
  the systemd unit, and add a proxied CNAME `<sub>.<zone>` →
  `<tunnel-id>.cfargotunnel.com` via the CF API (zone-scoped token with
  DNS + tunnel read works). Verify BOTH the new route and the existing
  route after the restart — a bad ingress edit takes the existing site
  down too.
- **Find which tunnel serves a domain empirically.** A `100::` AAAA on a
  proxied record means 'routed at the Cloudflare edge', not a normal
  origin — enumerate account tunnels + their configurations
  (`/cfd_tunnel/<id>/configurations`) before assuming; token-run tunnels
  (service binary with a JWT) decode via the `t` field of the base64
  token payload. A zone in the account does not mean the site's origin is
  in that account.
- **Remotely-managed tunnels show EMPTY local config** — a local
  `/etc/cloudflared/config.yml` may hold one tunnel's config while a
  different tunnel's rules live only in the CF API. Check both.
- **Systemd env-file + explicit venv python**: services need
  `EnvironmentFile=` (chmod 600) with every runtime secret and the exact
  venv interpreter path (`/usr/bin/python3` may lack the deps); a plain
  `python3` in ExecStart is the deploy-breaker. Verify with a full
  auth flow through the tunnel (no-auth 401, login, health, sync), not
  just a 200 on the index.

## Confirm-loop convergence signature (5-round case)

Diff-only confirmation rounds that name the prior findings explicitly
converge fast and predictably: full review (15 findings) → fix → confirm
finds 7 narrower residuals → 3 → 2 → 1 → SHIP. Two mechanics make it work:

- **Prompt the confirm round to also hunt for NEW bugs introduced by the
  fixes** — a pure verify prompt confirms fixes and stops hunting; the only
  rounds that found real regression-class bugs were the ones with a literal
  'check no new ordering bug was introduced' clause.
- **Reproduce every NOT-RESOLVED claim with an in-memory probe against the
  actual functions before writing the fix brief.** Reviewer claims are
  mostly real but scoped imprecisely; the probe gives the true severity and
  a failing case for the builder. One round's claim (merge flag loss) needed
  only a static trace to confirm; another (marker-as-name) needed a live
  probe. Probe both halves of a claimed two-mechanism bug — a claim can be
  real in one mechanism and wrong in the other.

## PDPA / PII in check-in UIs

Personal data from the source of truth may be REQUIRED in the DB (sync
columns) but forbidden in the UI. Separate the two: hide at render time
(`guest.mobile ? ... : ""` segments removed from the card template), keep
the DB/sheet path untouched, and say this split explicitly to the operator —
'hidden, not deleted' is a compliance claim they may need to defend. Same
pattern for any field that carries PII: mobile, ID numbers, full birthdate.
Apply this to intake forms too: if the UI must not SHOW mobile numbers,
the register form must not COLLECT them either — a hidden field still
creates a data liability (operator feedback on the deployed wedding
check-in: both the display and the intake field went).

Related UI-feedback pattern from the same operator round: terse toggle
labels are wanted but must stay decodable — replace word chips with
single-letter chips ONLY alongside `aria-label`s with the full word
("A" with `aria-label="Arrived"`), and never relabel a control in a way
that changes its API contract (the field name in the POST body stays
`arrived`/`gift` regardless of display). Category filters on a
mobile-first list UI want a `<select>`, not horizontally scrollable
pills — but a select that can hold an empty/"all" value needs an explicit
default: a fresh session with an empty value renders an empty list (see
pitfall #43 in SKILL.md) — default to the first real category on first
visit.

Post-launch operator feedback rounds on a staff UI (pattern from the
wedding check-in's post-deploy rounds):
- **"All" filters must fetch everything, and a first-visit default can
  mask the bug.** If the loader early-returns an empty list for the
  "all" value, verify by explicitly selecting it — the default-selected
  category hides the defect from casual checks.
- **Filter-side categories must come from the source's own catalog,
  not from guest rows** — a category defined in the source tab with zero
  tagged records must still appear; if the catalog persists only on
  sync-in, trigger one sync to populate it after deploying the fix.
- **RSVP-excluded guests must be filtered in the backend**, so footer
  and dashboard denominators stay consistent with the visible list (M
  parties = invited-excluding-No).
- **Role-split trays: the user may reject new auth in favor of
  ordering.** When two user roles share one login and destructive
  actions already sit behind a second password, put the staff-only
  action first and let the gate do the security — do not build an auth
  split nobody asked for.
- **Toggle chips read best light-until-active** — cream fill + thin
  gold border at rest, dark fill only when toggled on. A state-color
  treatment the operator calls "weird" reverts to this pattern.
- **Small visual deltas (name size, monogram text) are same-session
  one-line CSS/HTML fixes** — patch, bump the cache-bust query, restart,
  grep the served asset for the new value. Do not dispatch a builder for
  a token change; do say so explicitly per the delegation contract.

## Auth surface

- **Whitelist public static assets instead of blacklisting the sensitive
  file.** An exact-path deny (`path != "/static/index.html"`) is bypassed by
  duplicate slashes, trailing slashes, and dot segments
  (`/static//index.html/`, `/static/index.html/`) — normalization is fragile;
  a whitelist (`style.css`, `app.js` are public; everything else 401) is not.
  Test the bypass shapes explicitly.
- **Tokens never travel in URLs.** GET query tokens land in access logs and
  browser history. Login = POST body + HttpOnly cookie; legacy `?token=` URLs
  redirect to the login page, they do not authenticate.
- **Remove superseded routes entirely; do not leave a legacy alias behind.**
  A forgotten alias that skips the newer password/role gate is a bypass that
  every later review must rediscover.
