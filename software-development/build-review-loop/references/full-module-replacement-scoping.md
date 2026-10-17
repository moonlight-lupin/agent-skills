# Full-Module-Replacement Scoping + SQLite WAL Migration

Concrete pattern for replacing N existing modules with a new module, where every
caller must be updated. Extracted from a SQLite state store
migration (2026-08-24).

## Contents

- When this applies
- Scoping methodology
- SQLite WAL as state store replacement
- Contract test patterns for SQLite migrations
- Pitfall: brief must list every caller file

## When this applies

- Replacing multiple file-based state stores with a single database
- Replacing a set of modules with a new module that consolidates them
- Any refactor where you are DELETING modules that have many importers

This is a specific case of the build-review-loop where the "brief" must cover
the full import surface area — every file that imports from the modules being
replaced must be listed, or Cursor will miss some and the build will fail.

## Scoping methodology

### 1. Map the modules being replaced

For each module being deleted, identify:
- Its public API (every `def` / `class` at module level)
- Its file path
- Its line count

```bash
grep -n "^def \|^class " shared/scripts/module_being_replaced.py
```

### 2. Grep every caller

Run three greps per module being replaced:

```bash
# Import statements
grep -rn "from module_name import\|import module_name" --include="*.py" shared/scripts/ skills/

# Qualified calls (module.function)
grep -rn "module_name\.\(" --include="*.py" shared/scripts/ skills/

# String references (file paths, config keys)
grep -rn "module_name" --include="*.py" shared/scripts/ skills/
```

Exclude the module itself and test files from results. What remains is the
caller surface area — every file that must be updated.

### 3. Categorize callers

Group callers by what they import:
- **Direct API users** — call public functions, must switch to new API
- **Type/exception users** — import exception classes (StateCorruptionError,
  ConcurrencyError) — must update to new equivalents
- **Path references** — reference file paths of old state files (e.g.
  `.pending_actions.json` in doctor checks) — must point at new file

### 4. Write the brief with full caller inventory

The brief must list:
- **Modules to create** — new files and their public API
- **Modules to modify** — every caller file, what import changes
- **Modules to delete** — old files being removed
- **Modules that stay unchanged** — explicitly call out what is NOT changing

This inventory is what prevents Cursor from missing a caller. Without it,
Cursor will update the obvious callers and miss the ones buried in skill
scripts.

## SQLite WAL as state store replacement

### Pattern

Replace N file-based stores (JSON/YAML + fcntl locks + version counters) with
one SQLite database in WAL mode. This retires:
- `file_lock.py` (manual advisory locking)
- `.tmp` + `os.replace` + `fsync` atomic write dance
- Version counter defense-in-depth
- `ConcurrencyError` + `_with_retry` optimistic concurrency

SQLite handles all of this natively.

### PRAGMA settings

```python
conn = sqlite3.connect(str(db_path), check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA busy_timeout=10000")    # matches old lock timeout
conn.execute("PRAGMA foreign_keys=ON")
conn.execute("PRAGMA synchronous=NORMAL")    # safe with WAL, fast
```

### Connection management

- NOT a singleton. Callers create `StateDB(config)` per operation or per session.
- WAL mode allows concurrent readers + one writer without application-level locks.
- `check_same_thread=False` is safe because SQLite handles its own locking.

### Atomic state transitions (compare-and-swap)

For state machine transitions (e.g. approved → executing):

```sql
UPDATE pending_actions
SET state='executing', executing_at=?
WHERE id=? AND state='approved'
```

If `cursor.rowcount == 0`, the state changed concurrently — return `None`.
This replaces the old `expected_version` + `ConcurrencyError` + `_with_retry`
pattern with a single SQL statement. No application-level locking needed.

### Auto-migration from legacy files

On first open, if `state.db` does not exist but legacy files are present:

1. Read each legacy file (`.pending_actions.json`, `.events.json`, etc.)
2. Insert rows into the appropriate SQLite table
3. Rename legacy file to `.migrated` suffix (not deleted — operator can verify)
4. Record migration timestamp in a metadata table

Run the entire migration inside a single transaction. If any file fails to
parse, raise an error — do not partially migrate.

### Splitting mixed-concern modules

When a module has two distinct concerns (e.g. `webhook_security.py` had both
replay-cache storage AND payload validation), split it:

- **Storage concern** → moves into the new state store module
- **Validation concern** → moves into a new focused module
  (`webhook_validation.py`)

List every function and where it moves in the brief. Callers of the validation
functions need their import paths updated to the new module.

## Contract test patterns for SQLite migrations

Write these BEFORE the implementation (Hermes-authored TDD red):

- `test_db_creates_schema_on_first_open` — tables exist after init
- `test_kv_store_roundtrip` — save/load works for each store type
- `test_pending_action_full_lifecycle` — state machine transitions
- `test_concurrent_transition_only_one_wins` — two connections, one compare-and-swap wins
- `test_event_idempotency` — same source+source_id returns None
- `test_webhook_replay_first_delivery_allowed` / `test_webhook_replay_duplicate_blocked`
- `test_auto_migration_from_legacy_files` — legacy JSON → SQLite, files renamed
- `test_wal_mode_enabled` — `PRAGMA journal_mode` returns `wal`
- `test_corrupt_db_raises_not_silent` — garbage in state.db raises, not returns empty

The concurrent-transition test opens TWO `StateDB` instances on the same database
to simulate two processes. Both try the same `approved → executing` transition.
Exactly one must succeed. This is the test that proves the compare-and-swap works
without file locks.

## Pitfall: brief must list every caller file

One session had 20+ caller files across `shared/scripts/` and `skills/` dirs.
A brief that says "update all callers" without listing them will result in
Cursor missing skill scripts (e.g. `skills/document-preparer/scripts/send_email.py`)
that import from the old modules. Always grep, always list.
