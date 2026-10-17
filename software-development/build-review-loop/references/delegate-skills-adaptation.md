# Adaptation Reference: delegate-skills Port (2026-09-12)

Source: https://github.com/amElnagdy/delegate-skills (amElnagdy, MIT,
reviewed Sep 2026). Verdict on the repo itself: Watch — it targets other
orchestrators (Claude Code/opencode via `npx skills`), and its relays
duplicate dispatch mechanics this skill already hardens. Concept port, not
adoption.

## Ported

1. **Dispatch result contract (`delegate-result.v1`)** — from their
   `delegate-relay.result.v1`. One machine-readable result file per
   dispatch: status, exitCode, model-that-actually-ran, touchedFiles,
   report path. Implemented as `scripts/capture_dispatch_result.py` +
   `references/dispatch-result-contract.md`. Their relay writes it
   automatically; we capture after exit because our CLIs run raw in
   background terminals.
2. **The reviewer commits** — from their core invariant "the relay never
   commits — committing belongs to the reviewer" and their commit-boundary
   discipline (working tree is evidence between dispatch and commit; no
   reflexive `git checkout`/`clean` before inspection). Encoded as
   Pitfall #32 in SKILL.md.

## Explicitly NOT adopted

- **Their relay scripts (`relay.mjs`)** — per-CLI wrappers for other
  orchestrators' headless modes. Our dispatches (Cursor CLI `agent`, Codex
  `exec`, Claude Code) already run with verified flags and pitfall
  handling; a wrapper would add a layer without removing any known
  failure mode.
- **Fleet lanes / `delegate-fleet.v1` config** — persistent lane maps with
  approval-hash binding. Designed for multi-CLI fleets and multiple
  orchestrator seats; this workspace runs a fixed builder/reviewer pair
  with Bot Mode. Model routing lives in the brief, not in config.
- **`delegate-setup` discovery/interview flow** — multi-CLI discovery and
  burn/spare economics; no fit for a 1-operator setup.

## Validation

- Script exercised 2026-09-12 on a scratch git repo: clean tree →
  `touchedFiles: []`; post-edit → exact porcelain lines; non-repo dir →
  `null`; exit-code mapping verified for 0/124/127/1.
