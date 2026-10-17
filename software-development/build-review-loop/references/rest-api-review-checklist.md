# REST API Review Checklist

Patterns discovered during a Codex review of a REST API build (Aug 2026).
These are the 5 MAJOR + 2 MINOR findings that recurred when adding new REST
routers and PATCH endpoints over an existing engine layer. Use this as a
pre-dispatch checklist and a Codex review prompt supplement.

## Contents

- MAJOR Patterns
- MINOR Patterns
- Authorization Patterns (from 4th-pass security review)
- Pre-Dispatch Checklist for New REST Routers
- Codex Review Prompt Supplement

## MAJOR Patterns

### 1. NotFound exceptions mapped to 400, not 404

**Problem:** A single `except LedgerError` (or equivalent base exception)
handler maps ALL domain errors — including `*NotFound` subclasses — to HTTP
400. A missing resource returns 400 instead of 404. This violates REST
conventions and confuses API clients.

**Fix:** Maintain a tuple of all `*NotFound` exception classes. Catch them
before the base exception and map to 404:

```python
from core_toolset.core.exceptions import (
    AccountNotFound, InvoiceNotFound, BillNotFound, ...
)

NotFoundError = (AccountNotFound, InvoiceNotFound, BillNotFound, ...)

def run(fn, *args, **kwargs):
    try:
        return ok(fn(*args, **kwargs))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except LedgerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Missing required field: {exc}") from exc
```

**Key:** Every time a new `*NotFound` exception is added to the codebase, it
must be added to the tuple. A test should assert the tuple covers all
`*NotFound` classes in the exceptions module.

### 2. Missing required fields → KeyError 500

**Problem:** Router handlers access required payload fields with `dict[...]`
on a generic `Payload` dict. If the field is missing, Python raises `KeyError`
which escapes as an unhandled 500 error instead of a proper 422/400.

**Fix:** Either:
- Use Pydantic request models (preferred for new routers) — FastAPI auto-
  validates and returns 422 for missing/invalid fields.
- OR catch `KeyError` in the `run()` helper and map to 422 (shown above).

The `run()` helper approach is a safety net; typed Pydantic models are the
proper fix. But the safety net prevents 500s even when a developer forgets
the model.

### 3. Cross-company data leak in multi-tenant endpoints

**Problem:** An endpoint that takes a resource ID (e.g., `run_id`) from the
URL path does NOT verify the resource belongs to the authenticated company.
A caller from company A can retrieve company B's payslips by guessing the
run ID.

**Example:** `GET /pay-runs/{run_id}/payslips` called `list_pay_slips(conn,
run_id)` without checking that the pay run belongs to `db.company_id`.

**Fix:** Always verify ownership before returning scoped data:

```python
@router.get("/pay-runs/{run_id}/payslips")
def pay_slips_list(run_id: int, db: Annotated[DBContext, Depends(get_db)]):
    get_pay_run(db.conn, db.company_id, run_id)  # raises PayRunNotFound if wrong company
    return run(list_pay_slips, db.conn, run_id)
```

**Check every endpoint that takes an ID in the path** — does the engine
function filter by `company_id`? If not, add a guard call.

### 4. period_id not reset when entry date changes

**Problem:** When `update_entry` changes the entry date, `period_id` is
initialized to the old value (`entry.period_id`). If the new date falls
outside ALL fiscal periods, the period_id remains the old period — the entry
is now associated with a period that doesn't cover its date.

**Fix:** Initialize `period_id = None`. Only assign it when a covering OPEN
period is found:

```python
period_id = None  # reset
if covering:
    if covering["status"] != "open":
        raise FiscalPeriodClosed(...)
    period_id = covering["id"]
conn.execute("UPDATE journal_entries SET date = ?, period_id = ?, ...", ...)
```

### 5. Replacement lines skip validation that create_entry performs

**Problem:** `update_entry` replaces journal lines but skips the
`counter_party_id` existence + active-status validation that `create_entry`
performs. A nonexistent or cross-company counterparty reaches the foreign-key
constraint → unhandled database error → 500.

**Fix:** Apply the same validation loop in `update_entry` as `create_entry`:
account exists + active, counter_party exists + active, debit XOR credit,
non-negative, balanced. Copy the validation block; do not skip it.

## MINOR Patterns

### 6. Empty PATCH (no recognized fields) succeeds silently

**Problem:** A PATCH request with no recognized fields (e.g., `{"unknown":
"value"}`) still commits, creates an audit event, and returns 200. The
`update_item` and `update_employee` functions correctly reject this with
`ValidationError("No updatable fields supplied.")`, but `update_entry`,
`update_invoice`, `update_bill`, `update_payment` did not.

**Fix:** Whitelist recognized fields at the top of each update function:

```python
recognized = {k: v for k, v in fields.items() if k in ("description", "date", "lines")}
if not recognized:
    raise ValidationError("No updatable fields supplied.")
```

### 7. Delete operations silently succeed on missing targets

**Problem:** `remove_member` and `delete_elimination` execute DELETE SQL
without checking if the target exists. If nothing matches, the DELETE
succeeds silently (0 rows affected) and returns success.

**Fix:** Verify the target exists before deleting:

```python
def delete_elimination(conn, elimination_id):
    get_elimination(conn, elimination_id)  # raises if not found
    conn.execute("DELETE FROM ...")

def remove_member(conn, group_id, company_id):
    get_group(conn, group_id)
    cur = conn.execute("DELETE FROM ... WHERE ...", ...)
    if cur.rowcount == 0:
        raise GroupNotFound(f"Member ... not found in group {group_id}.")
```

## Authorization Patterns (from 4th-pass security review)

### 8. Entity override via setdefault — cross-tenant write bypass

**Problem:** A MCP dispatcher validates the `entity` parameter, then merges it
into handler args with `setdefault`. If the caller also passes `entity` inside
`args`, the caller's value wins and the handler runs against an entity that
was never validated. This defeats tenant isolation entirely.

**Root cause:** `setdefault` only sets if the key is absent. A caller who
includes `entity` in `args` pre-fills the key, so the validated value never
lands.

**Fix:** Force, never default:
```python
# WRONG — caller's args["entity"] survives:
call_args.setdefault("entity", entity)

# RIGHT — validated entity always wins:
call_args["entity"] = entity
```

**Test:** A regression test must pass a foreign entity inside `args` and
assert the handler does NOT run against it.

### 9. Mutating commands classified as read-scope

**Problem:** When scope is defined by explicit command sets (READ_COMMANDS,
ADMIN_COMMANDS), a hand-built list can include commands that actually write.
A read-scoped token can then mutate state.

**Examples found:**
- `cmd_report_template` — a CRUD dispatcher (create/update/delete) classified as read
- `cmd_report_load_defaults` — writes template records, classified as read
- `cmd_consol_fetch_rates` — fetches and persists exchange rates, classified as read

**Root cause:** A command whose scope depends on a runtime sub-argument (e.g.,
`template_cmd="create"`) cannot be statically classified. The classification
becomes a lie for mutating sub-actions.

**Fix:** Move any command that writes to the database out of READ_COMMANDS.
For dispatchers that mix read and write sub-actions, split them into separate
commands so each can be classified independently, or classify the whole
command as write.

**Splitting pattern (from 5th-pass review):** A handler like
`cmd_report_template` that dispatches on `args.template_cmd` (list|show|
create|update|delete|set-default) should be split into:
- `cmd_report_template_list` (read) — list templates
- `cmd_report_template_show` (read) — show single template
- `cmd_report_template_create` (write) — create template
- `cmd_report_template_update` (write) — update template
- `cmd_report_template_delete` (write) — delete template
- `cmd_report_template_set_default` (write) — set default template

The original dispatcher remains as a write-classified convenience wrapper
that delegates to the split handlers. The registry auto-discovers all
`cmd_*` functions, so the new handlers appear automatically. Add the
read-only split handlers to READ_COMMANDS.

**Audit:** Check for other handlers that dispatch on a runtime argument
(`args.subcommand`, `args.template_cmd`, etc.) — any such handler has the
same problem. Search: `grep -n "getattr(args," core_toolset/cli.py |
grep "_cmd\|subcommand"`

**Test:** A property test that runs every READ_COMMANDS entry against a
snapshot database and asserts no row changed would catch this class.

### 10. No role gate on REST/GUI write endpoints

**Problem:** `require_auth` authenticates and checks entity access, but no
write endpoint checks the user's role. A viewer can post to the general
ledger, approve entries, create invoices — anything that requires
authentication but not a specific role.

**Root cause:** `require_role("admin", "accountant")` exists but is only
applied to user-management routes. Write routes on all other routers rely on
`require_auth` alone. The GUI's write actions (`entry_action`,
`verify_books`) check the session but never read `user["role"]`.

**Fix:**
- REST: add a `require_write_role` dependency to every POST/PATCH/DELETE route
  (or to the router if it has no GET routes). Import from a shared location
  (e.g., `common.py`) so it chains through `require_auth`.
- GUI: add a `_require_write_role(user)` helper that checks
  `user.get("role") in ("admin", "accountant")` and raises 403 otherwise.
  Call it in every write route after `_check_session`.

**Three-surface authorization model (the real issue):** When CLI, REST, MCP,
and GUI each implement authorization independently, they drift apart. The
property to assert is not "this function gets called" but "no handler on any
surface ever runs against an entity outside the principal's access set, and
no write-scoped call mutates state, and no viewer can write." Three property
tests — isolation, scope, role — each a loop over the command registry or
route table, each running against every surface — hold the line. New surfaces
inherit the invariants instead of re-deriving them.

## Pre-Dispatch Checklist for New REST Routers

Before dispatching Cursor to build a new router, verify the brief covers:

- [ ] Every `*NotFound` exception is in the 404 mapping tuple
- [ ] Required payload fields accessed via `.get()` or typed Pydantic models
- [ ] Every path-parameterized endpoint verifies company/tenant ownership
- [ ] Update functions reset derived fields (period_id, totals) from scratch
- [ ] Update functions validate replacement data with the same checks as create
- [ ] Empty PATCH (no recognized fields) raises ValidationError
- [ ] Delete operations verify the target exists before deleting
- [ ] Router-level `dependencies=[Depends(require_auth)]` on every new router
- [ ] New modules registered in the router registry (or equivalent)
- [ ] `enabled_api_routers()` returns the new router names for ALL enabled modules
- [ ] Every POST/PATCH/DELETE route has `require_write_role` (or equivalent role gate)
- [ ] GUI write actions check `user["role"]` after session validation
- [ ] Entity parameters are FORCED into handler args, never setdefault
- [ ] No mutating command is in a read-scope set
- [ ] Argument-dispatching handlers split into per-subcommand handlers with honest scope — no handler whose scope depends on a runtime argument

## Codex Review Prompt Supplement

When reviewing new REST API routers, add this to the review prompt:

```
Additionally check for these common API design issues:
1. Are *NotFound exceptions mapped to 404, or do they return 400?
2. Do required payload fields raise KeyError→500, or are they validated?
3. Does every path-parameterized endpoint verify company/tenant ownership?
4. Do update functions reset derived fields (period_id, totals) from scratch?
5. Do update functions validate replacement data with the same checks as create?
6. Does an empty PATCH (no recognized fields) raise an error?
7. Do delete operations verify the target exists before deleting?
8. Are entity parameters forced (not setdefault) into handler args?
9. Are any mutating commands classified as read-scope?
10. Do all write endpoints check role (not just authentication)?
11. Do GUI write actions check user["role"] after session validation?
12. Are argument-dispatching handlers (e.g., cmd_report_template with template_cmd) split into per-subcommand handlers with honest scope classification?
13. Are accounting invariants (factor sums, balance constraints) enforced at the DB level (triggers), not just application-level checks?
14. Do polymorphic link tables use TEXT for target_id (not INTEGER) to support string codes like account codes?
15. Do polymorphic link validators block cross-company targets (target_id == company_id for company targets)?
```
