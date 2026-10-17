# Architecture Refactor: Test Update Pattern

When a build-review-loop fix round changes the internal architecture (e.g.
routing compat functions through a new CAS path instead of the old full-table
rewrite), tests that patch the OLD internal mechanism will fail — and this is
correct behavior, not a regression.

## Pattern (validated Aug 2026, a SQLite state-store migration)

### The problem

Tests that validate the OLD architecture's internal mechanism:

```python
# OLD test — patches _save, expects retry behavior
with patch("state_db._save", side_effect=flaky_save):
    result = mark_executed(config, action["id"], {"success": True})
assert call_count["n"] >= 2  # must have retried
```

After the fix routes `mark_executed` through `transition_action()` (CAS),
`_save` is never called. `call_count` stays at 0. The test fails.

### The diagnosis

This is NOT a regression — the test validates an implementation detail that
was deliberately replaced. The test must be rewritten to validate the NEW
architecture's behavior:

```python
# NEW test — validates CAS behavior, not _save retry
result = mark_executed(config, action["id"], {"success": True})
assert result is not None
assert result["state"] == "executed"
```

### Decision matrix

| Test failure cause | Action |
|---|---|
| Test patches OLD internal function (`_save`, `_with_retry`) | Rewrite test to validate NEW mechanism |
| Test asserts OLD state machine path (e.g. retry count from `_save` calls) | Rewrite to assert NEW path (e.g. CAS rowcount, transition result) |
| Test asserts OLD error type (`ConcurrencyError` from version mismatch) | Update to assert NEW behavior (`None` return from CAS mismatch) |
| Test asserts OLD side effect (YAML mirror written by `save_store_atomic`) | Update to assert NEW side effect (SQLite row exists) |
| Test fails because a NEW behavior is correct (e.g. `StateCorruptionError` raised on corrupt JSON where before it was swallowed) | Update test to expect the raise (this is the fix working as intended) |

### Key principle

When the orchestrator changes architecture (routing through a new path,
deleting old machinery), the orchestrator is responsible for updating tests
that validated the old mechanism. These are NOT Cursor fixes — they are
Hermes fixes because:

1. The tests encode the OLD contract, which was deliberately changed
2. The new behavior is correct — the test is wrong
3. The fix is in test-only code (per pitfall #20 — safe for Hermes to fix directly)

### What NOT to do

- Do NOT revert the architecture change to make the test pass
- Do NOT add the old `_save` call back as a compatibility shim
- Do NOT skip the failing tests
- Do NOT mark the tests as `@pytest.mark.skip` with a TODO

### What TO do

1. Read the failing test
2. Identify what OLD mechanism it patches/asserts
3. Rewrite it to validate the NEW mechanism
4. Run the full suite to confirm no other tests broke
5. Commit with message explaining the test was updated for the new architecture
