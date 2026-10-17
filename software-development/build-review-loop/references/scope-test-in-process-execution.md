# Scope Property Test — In-Process Execution Patterns

Patterns from a 5th-pass Codex review (Aug 2026) that refined
the scope property test beyond the initial implementation.

## Contents

- Problem 1: Exception paths skip snapshot comparison
- Problem 2: Missing-arg failures counted as meaningful execution
- Problem 3: Bare namespace limits meaningful coverage
- Updated EXEMPT_PATHS

## Problem 1: Exception paths skip snapshot comparison

**Codex MAJOR:** If the snapshot comparison is inside a `try` block or
after a `continue` on exception, a handler that mutates the database and
then raises escapes detection. The mutation is never compared.

**Fix:** The snapshot check must run unconditionally after every handler
invocation, regardless of whether the handler succeeded or raised:

```python
for cmd in read_cmds:
    if any(p in cmd.name for p in SKIP_PATTERNS):
        skipped.append(cmd.name)
        continue

    try:
        COMMAND_REGISTRY.execute(cmd.name, default_args)
        ran_ok += 1
    except SystemExit:
        ran_ok += 1
    except (AttributeError, TypeError, KeyError):
        ran_with_error += 1
    except Exception:
        ran_ok += 1  # business-logic exception = handler reached DB logic

    # ALWAYS check — even if the handler raised, it may have mutated first
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    after = snapshot_fn(conn)
    conn.close()

    changed_tables = [t for t, before in before_state.items()
                      if after.get(t) != before]
    if changed_tables:
        mutated.append(f"{cmd.name} mutated {changed_tables}")

    before_state = after  # update for next iteration
```

## Problem 2: Missing-arg failures counted as meaningful execution

**Codex MAJOR:** `AttributeError` on a missing namespace attribute means
the handler never reached its DB logic — it died at `args.status` before
opening a connection. Counting these as "executed" inflates the number
without proving anything ran.

**Fix:** Split into `ran_ok` (handler returned data, raised `SystemExit`
after printing, or hit a business-logic exception like `LedgerError`/
`ValueError`) vs `ran_with_error` (handler raised `AttributeError`/
`TypeError`/`KeyError` on a missing arg). Assert `ran_ok >= 30`, not
`executed >= 30`.

## Problem 3: Bare namespace limits meaningful coverage

Handlers access optional args directly (`args.status`, `args.type`,
`args.from_date`) rather than via `getattr(args, "status", None)`. With a
bare `{"entity": "prop_test"}` namespace, 74/89 handlers raise
`AttributeError` before reaching DB logic — only 15 meaningfully execute.

**Fix:** Provide `None` for 23+ common optional args. This lets handlers
proceed past arg access to their DB read logic, increasing meaningful
coverage from 15 to 45.

```python
default_args = {
    "entity": "prop_test",
    "company_id": None, "account_id": None, "account_code": None,
    "entry_id": None, "entry_no": None, "invoice_id": None,
    "bill_id": None, "payment_id": None, "item_id": None,
    "contact_id": None, "counter_party": None, "group_id": None,
    "period_id": None, "period": None, "schedule_id": None,
    "run_id": None, "id": None, "name": None, "status": None,
    "type": None, "stage": None, "direction": None,
    "from_date": None, "to_date": None, "as_of": None,
    "include_inactive": None, "entity_type": None,
    "entity_model": None, "username": None, "amount": None,
    "base_currency": None, "path": None, "json": False,
}
```

**Discovery script** — find all missing attributes for a new codebase:

```python
import re
missing = set()
for cmd in read_cmds:
    try:
        COMMAND_REGISTRY.execute(cmd.name, {"entity": "test"})
    except AttributeError as e:
        m = re.search(r"has no attribute '(\w+)'", str(e))
        if m:
            missing.add(m.group(1))
# missing = {'status', 'type', 'from_date', 'id', ...}
```

## Updated EXEMPT_PATHS

The GUI action route (`/ui/entries/{entry_id}/action`) was removed from
EXEMPT_PATHS after a viewer test was added to `test_web_gui.py`. The
exemption comment "tested separately" was a lie — the separate tests all
used admin sessions. Either remove the path from EXEMPT_PATHS or write an
explicit viewer test. Don't exempt without verifying the separate test
covers the same property.
