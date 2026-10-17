# Security Property Tests — Implementation Patterns

Patterns from writing three cross-surface security property tests (Aug 2026).
These tests loop over registries and route tables
instead of hand-picked names, so new surfaces inherit the invariants.

## Contents

- The Three Tests
- Key Implementation Patterns
- Critical Pitfalls (from 5th-pass review)
- When to Write These Tests
- File Location
- Relationship to build-review-loop

## The Three Tests

| Test | Surface | What It Asserts | Registry Looped |
|---|---|---|---|
| Isolation | MCP | Principal scoped to A cannot access B — even when B is smuggled in args | 12 domain tools |
| Scope | MCP | Every READ_COMMANDS entry leaves all DB tables byte-identical | 80+ read commands |
| Role | REST | Viewer-role principal gets 403 from every write route | 120 routes from OpenAPI schema |

## Key Implementation Patterns

### 1. Enumerate REST routes from OpenAPI, not from route attributes

FastAPI's internal route objects (`_IncludedRouter`) don't expose methods
directly. The reliable way to enumerate all mounted routes:

```python
from fastapi.testclient import TestClient
app = create_app()
c = TestClient(app)
schema = c.get("/openapi.json").json()
write_methods = {"post", "patch", "delete", "put"}
write_routes = []
for path, methods in schema["paths"].items():
    for method in methods:
        if method.lower() in write_methods and path not in EXEMPT_PATHS:
            write_routes.append((method.upper(), path))
```

### 2. Path parameter replacement for test requests

Use a regex to replace all `{param}` patterns with "1" (numeric) or "TEST"
(string). Don't hand-list every param name — new routes will add new params
and the test will silently miss them:

```python
import re
test_path = path.replace("{code}", "TEST")  # string params
test_path = re.sub(r"\{[^}]+\}", "1", test_path)  # all remaining → numeric
```

### 3. Fixture must set DATA_DIR BEFORE creating users

The master.db lives at `$DATA_DIR/master.db`. If the fixture creates
the user via `_open_master()` without setting the env var first, the user
lands in a different master.db than the one the test app reads:

```python
@pytest.fixture(scope="class")
@classmethod
def viewer_setup(cls, tmp_path_factory):
    data_dir = str(tmp_path_factory.mktemp("role_test"))
    os.environ["DATA_DIR"] = data_dir  # MUST set before _open_master()
    _init_test_entity(data_dir, entity="role_test")
    viewer_key, _ = _create_viewer_user(data_dir, "role_test")
    yield {"data_dir": data_dir, "entity": "role_test", "viewer_key": viewer_key}
    shutil.rmtree(data_dir, ignore_errors=True)
```

### 4. Create user-linked API keys via DB, not CLI

The CLI's `api-key create` only creates standalone (admin-level) keys.
To create a viewer-role key linked to a user, insert directly:

```python
from core_toolset.api.auth import generate_key, hash_key

key = generate_key()
key_hash = hash_key(key)

# 1. Create user in master.db
conn = _open_master()
conn.execute("INSERT INTO users (username, password_hash, role, active) VALUES (?, ?, 'viewer', 1)", ...)
user_id = conn.execute("SELECT id FROM users WHERE username = ?", ...).fetchone()["id"]
conn.execute("INSERT OR IGNORE INTO user_entity_access ...", (user_id, entity))
conn.commit(); conn.close()

# 2. Insert key in entity DB linked to user
conn = sqlite3.connect(str(Path(data_dir) / f"{entity}.db"))
conn.execute("INSERT INTO api_keys (name, key_hash, active, user_id) VALUES (?, ?, 1, ?)", ...)
conn.commit(); conn.close()
```

### 5. Use unique usernames (uuid) to avoid collision across test runs

```python
import uuid
username = f"viewer_{uuid.uuid4().hex[:8]}"
```

### 6. Class-scoped fixtures need @classmethod decorator

Pytest warns about class-scoped fixtures defined as instance methods. The
fixture runs once per class but each test gets a new instance — instance
attributes set in the fixture are NOT visible to test methods. Use:

```python
@pytest.fixture(scope="class")
@classmethod
def my_fixture(cls, tmp_path_factory):
    ...
```

### 7. Scope property test — snapshot technique

For the "read commands don't mutate" test, snapshot all table contents as
JSON strings before and after each command execution:

```python
def snapshot(conn):
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]
    state = {}
    for table in tables:
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY rowid").fetchall()
        state[table] = json.dumps([dict(r) for r in rows], sort_keys=True, default=str)
    return state
```

Then compare before/after snapshots for each read command. Skip commands
that need external services (Salt Edge, agent, extract/pdfplumber).

### 8. Exempt paths for role property test

Routes that should NOT be role-gated (auth flow, not business operations):

```python
EXEMPT_PATHS = {
    "/auth/login", "/auth/logout",
    "/oauth/authorize", "/oauth/register", "/oauth/token", "/oauth/revoke",
    "/ui/entries/{entry_id}/action",  # GUI uses session, tested separately
    "/ui/verify-books",               # read-only
}
```

## Critical Pitfalls (from 5th-pass review)

### P1: Subprocess-based scope test was inert — 0/87 commands ran

The first version of the scope test shelled out to the CLI using a name
transform (`cmd_account_list` → `account-list`) that produced no valid CLI
command — the CLI uses subcommand groups (`account list`, not
`account-list`). All 87 read commands were rejected by argparse before
running. The test compared snapshots that were never going to differ and
reported success. **A passing test that checks nothing is worse than a
missing one: the missing test leaves a known gap, the passing test closes
it on paper and stops anyone looking.**

**Fix:** Call `COMMAND_REGISTRY.execute(cmd.name, {"entity": "prop_test"})`
directly in-process. The registry holds the handler callables — no name
transform, no subprocess, no CLI grammar to get wrong.

### P2: Catch SystemExit separately from Exception

Some CLI handlers call `sys.exit(0)` after printing output. `SystemExit`
inherits from `BaseException`, not `Exception`, so `except Exception` won't
catch it. The handler ran, but the test saw an uncaught exception and
skipped the command — silently reducing coverage. Always catch `SystemExit`
separately and count it as executed.

### P3: Assert a minimum execution count

Without a floor assertion, a silent skip (wrong name transform, uncaught
exception type, missing env var) makes the test pass vacuously. Always
assert that enough commands actually executed (e.g., `assert executed >= 30`).

### P4: Exempt paths must have a real separate test

The role property test exempted `/ui/entries/{entry_id}/action` with the
comment "GUI uses session, tested separately." But the separate tests all
used an admin session — no viewer test existed anywhere. The exemption
comment lied, and the role gate on the GUI route was untested. Either
remove the path from EXEMPT_PATHS or write an explicit viewer test.

### P5: Split argument-dispatching handlers for honest scope classification

A single handler that dispatches on a runtime argument (e.g.,
`cmd_report_template` with `template_cmd=list|create|update|delete|...`)
cannot be classified statically — `list` and `show` are read, but `create`
and `delete` are write. Moving the whole dispatcher to write closes the
mutation hole but also blocks read-only users from listing templates.

**Fix:** Split into separate handlers, each with its own scope. The
original dispatcher remains as a write-classified convenience wrapper.
The registry auto-discovers all `cmd_*` functions, so the new handlers
appear automatically. Audit for other handlers that dispatch on a runtime
argument the same way.

### P6: Cross-company polymorphic link validation

When a polymorphic link table supports `target_type='company'`, the
validation must check `target_id == company_id`. Without this, company A
can link to company B's company record — a cross-tenant isolation breach.

The 5.16 Batch 2 Codex review found `_validate_target` used
`WHERE id = ?` for company targets without the company_id match. Company
A could create a link to company B's `company.id`.

**Fix:** For company targets, assert `int(target_id) == company_id` before
the existence check. Raise `ValueError` if they differ.

### P7: Rich default namespace for in-process scope tests

When calling `COMMAND_REGISTRY.execute` in-process with a minimal namespace
(`{"entity": "prop_test"}`), many handlers raise `AttributeError` on
missing optional args (`args.status`, `args.type`, `args.from_date`, etc.)
before reaching their DB logic. With a bare entity-only namespace, only 15
of 89 non-skipped read commands meaningfully execute. The `ran_ok >= 30`
assertion fails.

**Fix:** Build a rich default namespace with `None` for all common optional
args:

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

This gets 45/89 commands meaningfully executing — well above the threshold.

### P8: Snapshot comparison must run after exceptions (not just success)

A handler can mutate the database and then raise `SystemExit` or another
exception. If the snapshot comparison only runs on the success path (after
the `try/except` block), the mutation goes undetected. The 5.16 Codex
review caught this: the scope test's `except` paths had `continue` before
the snapshot check.

**Fix:** Move the snapshot comparison OUTSIDE the try/except block so it
runs after every handler invocation — success, `SystemExit`, `AttributeError`,
and `Exception`. The handler may have mutated before raising.

```python
try:
    COMMAND_REGISTRY.execute(cmd.name, default_args)
    ran_ok += 1
except SystemExit:
    ran_ok += 1
except (AttributeError, TypeError, KeyError):
    ran_with_error += 1
    # NO continue here — fall through to snapshot check
except Exception:
    ran_ok += 1

# ALWAYS check if DB changed — even if the handler raised
conn = sqlite3.connect(...)
after = snapshot(conn)
if after != snapshot_db["before"]:
    mutated.append(...)
```

### P9: Distinguish meaningful execution from missing-arg failures

Counting `AttributeError` as "executed" inflates the number — the handler
started but never reached its DB logic. The `ran_ok >= 30` assertion becomes
meaningless because the registry size guarantees >30 handlers will raise
`AttributeError` on some missing arg.

**Fix:** Split into two counters:
- `ran_ok`: handler returned data, called `sys.exit(0)`, or hit business
  logic (ValidationError, ValueError from a real validation)
- `ran_with_error`: handler raised `AttributeError`/`TypeError`/`KeyError`
  because required args are missing — NOT a meaningful execution

Only assert `ran_ok >= 30`. Report both counts in the assertion message.

### P10: Account targets use TEXT codes, not INTEGER rowid

When a polymorphic link supports `target_type='account'`, the `target_id`
must be the account's `code` (TEXT, e.g. "1000"), not its SQLite `rowid`.
`rowid` is SQLite-only and has no PostgreSQL equivalent. The migration
column must be `TEXT`, not `INTEGER`. The CLI must not force `int()` for
account targets — check `target_type` and use `str()` for accounts.

## When to Write These Tests

Write property tests BEFORE adding a new surface (e.g., a new vertical
module like manufacturing). The tests then automatically cover the new
routes/commands without manual list updates. If written after, the first
run validates the existing surface — any failures reveal pre-existing gaps.

## File Location

An example implementation lives at:
`tests/test_property_security.py` in the project repo.

## Relationship to build-review-loop

These tests were written by Hermes directly, NOT through Cursor CLI. This
is correct: property tests encode security invariants that the orchestrator
must define — the builder should not write its own security tests (same
principle as contract tests: Hermes writes the test, Cursor writes the code).

## In-loop security rules moved from SKILL.md pitfalls (2026-10-16 refactor)

1. **setdefault on security-critical parameters is a bypass** — when a dispatcher validates a parameter (e.g., `entity`) and then merges it into handler args with `dict.setdefault`, a caller who also passes that key inside `args` wins. The validated value never lands. One security review found this exact bug: `_dispatch_domain` validated `entity`, then did `call_args.setdefault("entity", entity)` — a caller who included `entity` inside `args` ran against an entity that was never checked, defeating tenant isolation entirely. The fix is one word: `call_args["entity"] = entity` (force, never default). This applies to ANY security-critical parameter merged into untrusted input — force the validated value, never let untrusted input override it. See `references/rest-api-review-checklist.md` pattern #8.
2. **Per-surface authorization drifts without property tests** — when CLI, REST, MCP, and GUI each implement authorization independently, they drift apart. A security property asserted as "this function gets called" is weaker than "no handler on any surface ever runs against an entity outside the principal's access set." The 4th-pass review found all three authorization defects (entity bypass, scope misclassification, missing role gates) were in code written that phase or widened by it, and none were caught by 1171 passing tests. Three cross-surface property tests — isolation, scope, role — each a loop over the command registry or route table, each running against every surface — hold the line. Write these BEFORE adding a new surface (e.g., a new vertical module). See `references/rest-api-review-checklist.md` patterns #8–10 and `references/security-property-tests.md` for implementation patterns.
