# Beta Gate Release-Hardening Cycle (Aug 2026)

Session record of the 0.1.0-beta.1 Beta Gate: five hardening items run as
orchestrated build-review batches. Complements the multi-batch-sequencing
reference with a release-hardening-shaped batch plan.

## Batch plan (execution order, not brief order)

| Batch | Item | Class | Build model | Test author |
|---|---|---|---|---|
| 1 | G2 CSRF protection | security code | grok-4.6-high | Hermes (red contract tests first) |
| 2 | G1 backup archive format | money-adjacent code | grok-4.6-high (parallel) | Hermes (red contract tests first) |
| 2 | G3+G4 docs + runbook | docs-only | composer-2.5 (parallel) | N/A |
| 2 | G5 constraints file | release engineering | composer-2.5 (parallel) | builder (guard test) |
| 3 | Codex+Opus dual review | review | — | — |

Highest-risk/highest-leverage first: CSRF is the smallest security gap and
unblocks docs (security.md references it). Docs and constraints are disjoint
from code files → safe to run in parallel with the code build (SKILL.md
pitfall #69).

## Contract-test pattern that worked

For each code item, Hermes wrote red tests BEFORE dispatching, encoding the
acceptance criterion as behavior:

- CSRF (`tests/test_csrf.py`): module contract (create/verify roundtrip,
  wrong-user rejection, garbage input → False never raise), template embeds
  `name="csrf_token"`, mutating routes 403 without/with-forged/with-foreign
  token, happy path extracts the embedded token and succeeds.
- Backup (`tests/test_backup_archive.py`): tarball contains manifest.json +
  master.db + entity DBs; manifest fields (format_version, app_version,
  created_at, entries[path, sha256, bytes]); checksum verification;
  `backup verify` detects tampered member / missing member / corrupt
  manifest; restore roundtrip reproduces trial balance + hash chain;
  refuse-without-force preserved; single-entity archive excludes others.

Before running red: probe the CLI's real contract once (`_error()` → stderr +
nonzero; success → stdout JSON) and fix wrong command names in the tests —
harness failures are not honest RED (SKILL.md pitfall #64/#47).

## Session-specific findings

- **Claim-vs-repo delta first**: a strategy brief said backup/restore was
  "missing"; the repo already had `ledger backup/restore/vacuum` +
  `tests/test_backup_restore.py`. The actual gap was narrower (archive
  format, verify, PG path, CI recovery test). Verify each brief claim with
  grep before scoping the build — this halved G1's scope.
- **Clean reference venv** (`/tmp/<proj>-venv`, SKILL.md pitfall #68) — host
  venv had a stale `mcp` package producing unrelated ImportErrors; the clean
  venv turned those into honest RED. Its `pip freeze` then became the G5
  constraints file directly.
- **Builder deviation caught at verification** (SKILL.md pitfall #50): the
  G1 builder added a global `tarfile.TarFile.addfile` monkeypatch in the
  package `__init__.py` that nothing needed — flagged for removal at review
  instead of being committed silently.

## Outcomes (test-level, before dual review)

- G2: 11 contract tests + 108 related tests green.
- G1: 11 contract tests green; 32 combined Beta-Gate tests green.
- G3/04: README reconciled (bootstrap-mode API-key drift fixed), 9 docs
  files, deployment runbook with "never expose port 8000" rule.
- G5: constraints.txt + Dockerfile `-c constraints.txt` + guard test.
