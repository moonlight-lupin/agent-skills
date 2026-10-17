# SQLite WAL Migration: Review Findings (Codex + Opus)

Catalog of findings from a cross-model review (Aug 2026).
11 total findings across two reviewers. Use this as a checklist when
reviewing future SQLite state store migrations.

## Contents

- Both-reviewer findings (highest confidence)
- Codex-only findings
- Opus-only findings
- What was confirmed solid
- Fix sequencing
- Session outcomes (Aug 2026)

## Both-reviewer findings (highest confidence)

### BLOCKING 1: KV read/modify/write lost updates
- `put_kv()` atomic but caller's load→mutate→save is NOT one transaction
- `with_store_lock()` is now a no-op — callers still depend on it
- Fix: `mutate_kv()` method with `BEGIN IMMEDIATE` wrapping entire sequence

### BLOCKING 2: Auto-migration can skip legacy data
- Migration runs only when `state.db` doesn't exist
- Crash between commit and rename = permanent data loss
- YAML parse errors silently `continue`d while other sources commit
- Fix: idempotent per-source check on every open, raise on parse errors

### MAJOR: workspace_audit.py lost its lock
- `file_lock.py` deleted, audit's graceful fallback means no locking at all
- Concurrent writers can fork the hash chain
- Fix: SQLite-based lock (BEGIN EXCLUSIVE on sidecar DB)

### MAJOR: Corrupt JSON silently accepted
- `_loads()` returns default on malformed JSON — masks corruption
- `get_kv()` swallows `SchemaError` with `pass`
- Fix: strict `_loads()` raises `StateCorruptionError`, propagate `SchemaError`

### MAJOR: _save() swallows BEGIN IMMEDIATE failure
- `except sqlite3.OperationalError: pass` — proceeds without write lock
- Version check runs unprotected
- Fix: retry with backoff on SQLITE_BUSY, do not swallow

### MAJOR: Replay lease token bypass
- `reserve_delivery()` returns `(bool, str)` — no token
- `complete_delivery(None)` accepted even when token stored
- Stale worker can complete/release a reclaimed delivery
- Fix: return token from reserve, reject tokenless complete/release
- Note: Opus identified this as pre-existing, not a regression

## Codex-only findings

### MINOR: Cleanup omits terminal states
- `cleanup_old_actions()` only removes `executed`, `cancelled`, `expired`
- `dismissed` and `failed` accumulate indefinitely
- Fix: add both states to cleanup query

### NIT: Duplicate event key uniqueness
- `key TEXT UNIQUE NOT NULL` + `CREATE UNIQUE INDEX idx_ev_key` = redundant
- Fix: remove the named index, keep the column constraint

## Opus-only findings

### MAJOR: Production code never uses the new CAS path
- `transition_action()` exists but no production caller uses it
- All callers use old `_load/_save` full-table rewrite compat layer
- The "retired" pattern is actually what runs in production
- Fix: route compat functions through `transition_action()`, delete duplication

### MAJOR: transition_action("failed") bypasses MAX_RETRIES
- Goes straight to "failed" on first call — no retry logic
- The two implementations of the state machine have already diverged
- Fix: move retry-cap logic into `transition_action` or shared helper

### MINOR: _cas_update column names via f-string without allowlist
- `f"{key}=?"` from caller kwargs — no SQL injection today but no guard
- Fix: `_ALLOWED_CAS_COLUMNS` frozenset, check membership before interpolation

## What was confirmed solid

- `webhook_validation.py` extraction is byte-for-byte behavior-preserving
- Event idempotency via UNIQUE constraint is correct
- No stale imports of deleted modules
- No live SQL injection vectors
- Migration is transactional on the happy path
- Full suite passes, ruff clean

## Fix sequencing

1. **Round 1** (Cursor): fix all 8 Codex findings → verify → commit
2. **Round 2** (Cursor): fix 3 Opus-only findings → verify → commit
3. **Test updates** (Hermes): update tests that patched old `_save` mechanism
   to validate new CAS architecture — see
   `references/architecture-refactor-test-updates.md`
4. **Test updates** (Hermes): update test expecting graceful degradation on
   corrupt JSON to expect `StateCorruptionError` (fail-loud is the new contract)

## Session outcomes (Aug 2026)

- **11 findings total**: 8 Codex + 3 Opus-only (6 overlapped = high confidence)
- **Fix round 1**: Cursor fixed 8 Codex findings (mutate_kv, idempotent migration,
  strict _loads, lease token return, workspace_audit lock, BEGIN IMMEDIATE retry,
  cleanup terminal states, remove duplicate index). 2043 tests pass.
- **Fix round 2**: Cursor fixed 3 Opus findings (route compat through transition_action,
  MAX_RETRIES in transition_action, _ALLOWED_CAS_COLUMNS allowlist). 2043 tests pass.
- **Hermes test fixes**: 4 tests updated across 3 files (test_phase2_loop1, test_phase3_loop1,
  test_review_queue_v025, test_phase5_review) — old mechanism tests rewritten for new CAS architecture.
- **Cursor API down for v0.5.0 build**: Hermes built HTML briefing + attachment hook directly
  (Cursor API resource_exhausted 3x). 27 contract tests validated correctness. 2070 full suite pass.
- **Final**: 2070 tests, CI green (Py 3.11 + 3.12), v0.5.0-beta tagged and released.
