# Skill Governance v0.1.1 (P1 consolidation)

**Consolidated engine, verified.** This plugin combines the two existing
engines without altering their implementation logic. v0.1.1 passed the
pre-merge gate on an isolated real Hermes profile: real-loader registration,
migration parity (deep-equal v1 import, idempotent, sources byte-identical),
hook exercise with real advisories, cron opt-in/refusal, and config
round-trip (evidence in PR #24, /tmp/gov-verification/VERIFICATION.md at
review time).

- `manifest/`: skill provenance, drift/fingerprint tracking, acknowledgements.
- `contrastive/`: non-blocking edit observation, probe reminders, fire ledger.
- `core.py`: namespace isolation, non-destructive state import, conservative
  unified records and one optional clearance schedule.

## Installation / migration

**Never enable all three plugins simultaneously.** Both old plugins can
register the same CLI aliases or fire duplicate notifications. The transition
is deliberately manual and reversible:

1. Back up `<HERMES_HOME>/plugin-data/`, `config.yaml`,
   `skills/UPSTREAM_MANIFEST.md` and `skill-probes/`. Record the existing
   cron jobs and IDs. Install this directory as `plugins/skill-governance/`.
2. Disable **skill-manifest** and **contrastive-advisor** in Hermes; restart
   only after the new plugin is configured. Do NOT delete old plugin dirs or
   their data.
3. Transfer old plugin settings into **new** nested keys. E.g.:
   `plugins.entries.skill-governance.settings.manifest.track_changes` and
   `plugins.entries.skill-governance.settings.advisor.enabled`. The new
   plugin cannot read another plugin's settings via the scoped API. Advisor
   remains explicitly opt-in (default `false`).
4. Start an isolated profile. Registration copies each old plugin's
   `state.json["v1"]` to new keys `manifest.v1` and `advisor.v1`.
   It **never modifies or deletes** either legacy state file. If the legacy
   state is malformed, registration fails before hooks install.
   Existing destination state is never overwritten on a second start.
5. Review the new `governance.records` summary. Keep the old
   `plugin-data/skill-manifest/acks.json` and `skill-probes/` unchanged;
   they are still referenced by their original engines. This preserves
   fingerprint acknowledgements and fire-evidence paths.
6. If desired, manually remove or disable both old clearance jobs, then
   opt in to **one** new job with `cron.enabled: true` in the new plugin's
   settings. If either named legacy job remains, the new plugin will **not**
   create a duplicate. The new scheduler honors manual removal of its own job.
7. Verify ordinary arrivals, changed fingerprints, /skill-manifest-ack,
   behavioral edit advisories, and the probe ledger on disposable skills.
   Check the combined pre-LLM context contains both advisories, not just one.

**Rollback:** disable the new plugin, enable the two originals with their
original configuration, and restart. Disable the new cron first if one was
explicitly enabled. **Rollback is NOT lossless.** Know these three facts
before you roll back:

- The migration imports legacy state once, by copy. Afterwards the new
  plugin's `manifest.v1` / `advisor.v1` evolve independently and the legacy
  `state.json` files stay frozen at the migration snapshot.
- Ongoing operation writes SHARED stores the legacy engines also read:
  the fire ledger (`<HERMES_HOME>/skill-probes/fire-ledger.jsonl` — written
  whenever the advisor fires and closes rows in place) and the external
  acknowledgements file (`plugin-data/skill-manifest/acks.json` — written by
  the preserved `/skill-manifest-ack` CLI). "Never modified" applies to the
  legacy `state.json` envelopes only.
- On rollback the legacy engines restart from their frozen v1 state against
  these shared, newer stores: any dismissals, baseline adoptions,
  advisory-session state or pending probes recorded ONLY by the new plugin
  are lost. If you later re-enable the new plugin, the destination-wins rule
  (`manifest.v1`/`advisor.v1` already exist) silently ignores anything the
  legacy plugins recorded in the meantime — delete the new plugin's
  `state.json` namespace (or ask for a re-import) to force a fresh copy.

There is no reverse export in v0.1.1; treat rollback as a one-way step and
back up `<HERMES_HOME>/plugin-data/` first.

## New configuration

All options are plugin-local under
`plugins.entries.skill-governance.settings`:

- `manifest.*`: the original manifest fields, except `auto_resolve*` (legacy
  scheduler disabled; owned by `cron.*` now).
- `advisor.enabled` (false by default), `advisor.probe_root`,
  `advisor.excluded_skills`, `advisor.ttl_minutes`, `advisor.markers`,
  `advisor.ledger_enabled`. Legacy `sweeper*` options are replaced by
  `cron.*`.
- `cron.enabled` (false by default, to honor prior opt-outs),
  `cron.schedule` (default `0 9 * * *`),
  `cron.deliver` (default telegram).

The bundled skill is now
`skill-governance:contrastive-refinement`, not the original
`contrastive-advisor:contrastive-refinement`. Update hard-coded references
before disabling the old plugin.

## Semantics of the unified records

Records live at `ctx.state["governance.records"]`:

- `fingerprint`, `manifest_status`, `manifest_reason` and `provenance_status`
  summarize the manifest engine. `acknowledged` requires a matching external
  `acks.json` entry; `fingerprint_current` only records a matching in-state
  digest (possibly an automatically adopted baseline), **not proof of human
  review**.
- `validation_status` starts at `not_evaluated`, becomes `probe_advised`
  for an unresolved reminder, or `answered_unbound` for older answered
  probe-ledger rows. **Never treat `answered_unbound` as proof that the
  current fingerprint has been validated.** Legacy ledger rows have no
  fingerprint binding.
- Manifest keys are hashed paths; the advisor uses skill names. They are
  joined only when a manifest finding includes an explicit matching name.
  Other entries stay separate instead of guessing identity. This is a
  conservative *summary*, not a replacement for the original stores.
- Only the latest 200 ledger rows enter the summary; the original ledger is
  preserved and authoritative.

## Preserved surfaces and remaining limits

- One hook each for `on_skill_lifecycle`, `on_session_start`,
  `pre_tool_call` and `pre_llm_call`.
- Both engines' advice is returned in one `{"context": "..."}`.
- The existing `skill-manifest` CLI and `/skill-manifest-ack` command
  remain registered for backward-compatible manual acknowledgements.
- Bundled helper scripts and the contrastive-refinement skill are copied
  from the v0.3.0 sources **unchanged**.
- Existing source plugin directories remain in the repository for safe
  rollback. This PR does not automatically disable an already installed
  plugin, nor migrate another plugin's configuration.

**Acceptance gate:** unit/migration tests, all existing plugin suites, and an
isolated real Hermes profile migration with both plugins' real state and
clearance jobs. CI passing alone does not establish production parity.
