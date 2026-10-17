# Upgrade-Path Test Pattern

Learned from a sixth-pass review (Aug 2026). The reviewer identified that migration 055's data-loss bug was invisible to all 1272 passing tests because every test bootstraps a fresh database — migrations run on an empty schema where cascade-deletes have nothing to delete.

## The Problem

Migration tests typically verify that `migrate(conn)` succeeds on a fresh in-memory database. But migrations that rebuild tables (DROP + CREATE + INSERT) can silently destroy data when run against a populated database. The fresh-DB test pattern cannot catch this because:

1. All migrations run in order on an empty schema
2. The table being rebuilt has zero rows
3. CASCADE-deletes have nothing to cascade to
4. The test passes, the bug ships

## The Fix: Upgrade-Path Tests

Write tests that:
1. Bootstrap a fresh database (migrate runs all migrations)
2. Seed real data (company, accounts, entries, lines)
3. Assert row counts are non-zero
4. Re-run migrate (idempotent — nothing to apply)
5. Assert row counts are unchanged

```python
class TestUpgradePath:
    def test_journal_lines_survive_full_migration_chain(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "upgrade.db"))
        conn.row_factory = sqlite3.Row
        migrate(conn)

        # Seed real data
        company = setup_company(conn, Company(name="Upgrade Co"))
        cid = company.id
        seed_accounts_from_template(conn, cid, "sg_sme_default")
        create_fiscal_period(conn, FiscalPeriod(...))
        entry = create_entry(conn, JournalEntry(..., lines=[...]))
        submit_entry(conn, cid, entry.id)
        approve_entry(conn, cid, entry.id)

        lines_before = conn.execute("SELECT COUNT(*) FROM journal_lines").fetchone()[0]
        assert lines_before == 2

        # Re-run migrate — should be idempotent
        applied = migrate(conn)
        assert applied == []

        # CRITICAL: lines must survive
        lines_after = conn.execute("SELECT COUNT(*) FROM journal_lines").fetchone()[0]
        assert lines_after == lines_before, (
            f"Journal lines lost during migration: {lines_before} -> {lines_after}"
        )
```

## Also Test DB Constraints Accept New Values

After a migration that widens a CHECK constraint, verify the new value is accepted at the DB level:

```python
def test_fx_revaluation_entry_type_accepted_in_db(self, tmp_path):
    conn = sqlite3.connect(str(tmp_path / "fxr.db"))
    conn.row_factory = sqlite3.Row
    migrate(conn)
    # ... setup ...
    conn.execute(
        "INSERT INTO journal_entries (..., entry_type, ...) VALUES (..., 'fx_revaluation', ...)",
        (...)
    )
    conn.commit()
    row = conn.execute("SELECT entry_type FROM journal_entries WHERE entry_no = ?", ...).fetchone()
    assert row["entry_type"] == "fx_revaluation"
```

## General Rule

Any migration that rebuilds a table (DROP + CREATE + INSERT pattern) needs an upgrade-path test that seeds data before the migration and verifies data survives after. Fresh-DB tests alone cannot catch cascade-delete data loss.
