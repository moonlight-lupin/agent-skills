# Changelog

## v0.1.1 — panel fixes (review gate: opus + codex, all findings fact-checked)

Fixes from the pre-merge review panel (PR #24); vendored engines stay byte-identical.

- `build_records`: a ledger row closed via `record_fire`'s cycle path
  (`answered_at` + `cycle`, no `answered_with`) now labels `answered_unbound`
  instead of `not_evaluated`. Both live closure shapes count; `not_evaluated`
  remains only for rows with no closure evidence.
- `ensure_single_cron`: the check-then-create sequence now runs under a
  non-blocking `flock` with short retries (same discipline as the vendored
  manifest engine), so concurrent session starts cannot each create a
  clearance job and contention cannot stall a session start; non-POSIX hosts
  degrade to the v0.1.0 unlocked behavior. A hand-recreated job
  with the exact name opts the operator back in after a removal.
- Registration never touches plugin state: migration, the coexistence check
  and the first records build run lazily on the first hook call — and the
  bootstrap runs BEFORE any vendored-engine call (an engine state write would
  create the destination namespace and make the legacy import a no-op).
  Bootstrap is serialized with a lock; a corrupt legacy store leaves all four
  hooks inert (the engines never run on empty namespaces).
- README rollback section states the shared-store reality plainly (the fire
  ledger and the legacy acks.json are written during normal operation; legacy
  v1 state stays frozen at the snapshot; rollback divergence and the
  destination-wins rule are documented).
- `sync_records` parses the probe ledger and acks file only when their
  mtime/size signature changes; parsed rows are cached in memory only
  (per process — the authoritative stores stay on disk), a failed parse never
  replaces the cached good rows, and records are still rebuilt from plugin
  state on every refresh.
- Home resolution matches the vendored engines (`hermes_constants.get_hermes_home()`),
  so records can never read a different profile's acks.json than the CLI writes.
- A legacy envelope with no `v1` key (or `"v1": null`) reads as "nothing to
  migrate" instead of failing registration; genuinely corrupt or wrong-typed
  `v1` payloads still fail closed inside the hooks.
- Records: baseline lookups are case-insensitive (the engine lowercases its
  baseline keys), and same-basename skills under different manifest paths no
  longer overwrite each other — the plain name belongs to the smallest
  manifest key (deterministic) and colliding keys get a `#<key-prefix>` ref;
  advisor/ledger rows join by plain display name (documented limitation).
- Runtime warning when skill-manifest or contrastive-advisor are still enabled
  alongside this plugin (duplicate advisories, CLI collision risk).
- The vendored first-fire note advertising the legacy "contrastive-advisor fire
  clearance" cron is suppressed at the adapter boundary; that job never exists
  under governance.
- Known semantics (documented): bootstrap runs once per process; a failure
  (e.g. a corrupt legacy store) keeps governance hooks inert until the next
  gateway restart — fail-closed, no silent retry. The preserved
  `/skill-manifest-ack` CLI writes the shared acks.json regardless of
  bootstrap state; it never creates the `manifest.v1` destination, so it
  cannot re-trigger the destination-wins skip.
- Tests: `test_cron_default_off` now installs fake cron modules and asserts no
  create is attempted; new coverage for cycle-only closure labels, envelope
  edge cases, opt-back-in adoption, name collisions and case-insensitive
  provenance.

Plugin version 0.1.0 → 0.1.1.

## v0.1.0 — P1 consolidation

- Consolidated `skill-manifest` + `contrastive-advisor` engines (vendored
  byte-identical) behind one composed hook surface: `on_skill_lifecycle`,
  `on_session_start`, `pre_tool_call`, `pre_llm_call`.
- Non-destructive legacy state import (`manifest.v1`, `advisor.v1`);
  destination-wins; sources never modified.
- Conservative unified `governance.records` view; acknowledged never implies
  validated (legacy ledger rows are `answered_unbound`, never `validated`).
- One opt-in clearance job (`cron.*`, default off) that refuses to duplicate
  the legacy named jobs; both legacy clearance procedures preserved verbatim.
- Bundled skill registered as `skill-governance:contrastive-refinement`.