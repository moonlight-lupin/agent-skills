# SQLite Migration Pitfalls

Learned from one migration build (Aug 2026). Codex review caught a BLOCKING data-loss bug in migration 055.

## Contents

- PRAGMA foreign_keys=OFF Inside a Transaction
- CHECK Constraint Changes Require Table Rebuild
- PostgreSQL Migrations Are Different

## PRAGMA foreign_keys=OFF Inside a Transaction

### The Problem

The migration runner (`_migrate_sqlite` in `core/db.py`) wraps each migration file in `BEGIN`/`COMMIT`:

```python
conn.execute("BEGIN")
for stmt in statements:
    conn.execute(stmt)
conn.execute("COMMIT")
```

`PRAGMA foreign_keys=OFF` has **no effect** inside an active transaction. SQLite ignores it. So when a migration does:

```sql
PRAGMA foreign_keys=OFF;           -- NO-OP (inside BEGIN)
CREATE TABLE journal_entries_new (...);
INSERT INTO journal_entries_new SELECT * FROM journal_entries;
DROP TABLE journal_entries;        -- CASCADES to journal_lines!
ALTER TABLE journal_entries_new RENAME TO journal_entries;
PRAGMA foreign_keys=ON;            -- NO-OP (inside BEGIN)
```

The `DROP TABLE journal_entries` triggers `ON DELETE CASCADE` on `journal_lines.entry_id`, deleting ALL journal lines.

### The Fix: Rename Dependent Tables Aside

Instead of relying on `PRAGMA foreign_keys=OFF`, rename dependent tables out of the way before dropping the parent:

```sql
-- Step 1: Rename journal_lines out of the way (breaks the FK reference)
ALTER TABLE journal_lines RENAME TO journal_lines_temp_055;

-- Step 2: Rebuild journal_entries with the new CHECK constraint
CREATE TABLE journal_entries_fxr_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ...
    entry_type TEXT NOT NULL DEFAULT 'general'
        CHECK(entry_type IN (..., 'fx_revaluation')),
    ...
);

-- Step 3: Copy all data
INSERT INTO journal_entries_fxr_new (...) SELECT ... FROM journal_entries;

-- Step 4: Drop old table (no CASCADE — journal_lines was renamed)
DROP TABLE journal_entries;

-- Step 5: Rename new table
ALTER TABLE journal_entries_fxr_new RENAME TO journal_entries;

-- Step 6: Recreate indexes
CREATE INDEX IF NOT EXISTS idx_je_company ON journal_entries(company_id);
...

-- Step 7: Rename journal_lines back (FK now points to rebuilt table)
ALTER TABLE journal_lines_temp_055 RENAME TO journal_lines;
```

### Why This Works

- `ALTER TABLE ... RENAME TO` breaks the FK reference from `journal_lines` to `journal_entries`
- `DROP TABLE journal_entries` has no children to cascade to
- `ALTER TABLE ... RENAME TO` on the temp table re-creates the FK reference to the rebuilt parent
- No data loss, no dependency on PRAGMA behavior

### Detection

Codex reproduced this by running the migration against an in-memory SQLite DB with existing entries and lines:

```python
c.executescript('''CREATE TABLE journal_entries(...); CREATE TABLE journal_lines(... REFERENCES journal_entries(id) ON DELETE CASCADE); INSERT ...; INSERT ...;''')
c.execute('BEGIN')
# Execute migration 055 statements...
print('journal lines after rebuild=', c.execute('select count(*) from journal_lines').fetchone()[0])
# Output: 0  ← DATA LOSS
```

### General Rule

Any SQLite migration that rebuilds a table with `ON DELETE CASCADE` children must use the rename-aside pattern. Never rely on `PRAGMA foreign_keys=OFF` inside a transaction-wrapped migration runner.

## CHECK Constraint Changes Require Table Rebuild

SQLite cannot `ALTER` a CHECK constraint in place. To add a new value to a CHECK constraint:

1. Create a new table with the updated CHECK
2. Copy all data from the old table
3. Drop the old table
4. Rename the new table

This is the standard SQLite table-rebuild pattern. The rename-aside fix above is the safe variant when the table has CASCADE children.

## PostgreSQL Migrations Are Different

PostgreSQL can `ALTER TABLE ... DROP CONSTRAINT` and `ADD CONSTRAINT` without rebuilding the table. The PG variant of migration 055 is simpler:

```sql
ALTER TABLE journal_entries DROP CONSTRAINT IF EXISTS journal_entries_entry_type_check;
ALTER TABLE journal_entries ADD CONSTRAINT journal_entries_entry_type_check
    CHECK (entry_type IN (..., 'fx_revaluation'));
```

No data loss risk, no table rebuild needed.
