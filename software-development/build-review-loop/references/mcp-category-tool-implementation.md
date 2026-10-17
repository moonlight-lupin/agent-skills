# MCP Category-Based Tool Implementation — Phase 5.14

Reference implementation for a 12-domain MCP tool surface with JIT discovery,
built on top of an existing CLI with 212 `cmd_*` handlers.

## Contents

- Architecture
- Key Design Decisions
- Test Coverage
- Pitfalls Encountered

## Architecture

```
CLI (212 cmd_* handlers)
  → _output/_error return (data, exit_code) tuples  [T2 refactor]
  → _run() wrapper in main() prints + exits for CLI

CommandRegistry (command_registry.py)
  → CommandMeta(name, domain, scope, description, handler)
  → Explicit scope per command (read/write/admin), default-deny
  → 12 domains: gl, ar_ap, company, crm, inventory, payroll,
    reports, recon_fx, budget, consolidation, documents, admin

MCP Server (mcp_server.py)
  → 12 @mcp.tool() functions (ledger_gl, ledger_ar_ap, ...)
  → _dispatch_domain() shared helper
  → Dynamic scope check inside execute (not just decorator)
  → Old 22 tools remain as backward-compat aliases
```

## Key Design Decisions

### 1. Return tuples instead of sys.exit (T2)

Handlers return `(data, exit_code)`. A thin `_run()` wrapper in `main()` prints
and exits for CLI. The registry's `execute()` method returns only `data`.

```python
def _output(data, exit_code=0):
    return (_serialize(data), exit_code)

def _error(msg: str):
    return ({"error": msg}, 1)

def _run(handler, args):
    result = handler(args)
    if isinstance(result, int):
        sys.exit(result)      # cmd_onboard returns int
    if isinstance(result, tuple):
        _print_and_exit(result)
    sys.exit(0)
```

### 2. Default-deny scope classification (T3)

Every `cmd_*` gets an EXPLICIT scope. Two allowlists (READ_COMMANDS,
ADMIN_COMMANDS), everything else defaults to `write`.

```python
READ_COMMANDS = frozenset({
    "cmd_entity_list", "cmd_user_list", "cmd_company_list", ...
})
ADMIN_COMMANDS = frozenset({
    "cmd_backup", "cmd_restore", "cmd_vacuum", "cmd_l10n_install", ...
})

def _scope_for(name: str) -> str:
    if name in ADMIN_COMMANDS:
        return "admin"
    if name in READ_COMMANDS:
        return "read"
    return "write"  # default-deny
```

### 3. Domain mapping with exact overrides (T3)

Some commands need exact-name overrides (checked before prefix matching):

```python
_DOMAIN_EXACT = {
    "cmd_report_ageing": "ar_ap",   # ageing report, not reports
    "cmd_init": "company",
    "cmd_backup": "admin",
    "cmd_export_trial_balance": "reports",
}
```

### 4. Dynamic scope check inside _dispatch_domain (T4)

The `@_require_scope("ledger:read")` decorator is the MINIMUM. The actual
write/admin check happens inside `_dispatch_domain` based on the command's
scope:

```python
def _dispatch_domain(domain, entity, action, args=None):
    _check_entity_access(entity, _get_principal())

    if action == "list":
        return [{"name": c.name, "scope": c.scope, ...}
                for c in COMMAND_REGISTRY.list_commands(domain)]

    if action == "execute":
        cmd_name = args.get("command")
        meta = COMMAND_REGISTRY.get(cmd_name)
        if meta.domain != domain:
            raise ValueError("wrong domain")
        # Dynamic scope check
        principal = _get_principal()
        if meta.scope == "write":
            _require_write_scope(principal)
        elif meta.scope == "admin":
            _require_admin_scope(principal)
        return COMMAND_REGISTRY.execute(cmd_name, call_args)
```

This lets a viewer call `ledger_admin(entity, action="list")` to SEE admin
commands (read scope is enough for discovery), but blocks execution of
admin-scoped commands (requires `ledger:admin`).

### 5. Three OAuth scopes (T1+T6)

```python
SCOPE_READ = "ledger:read"
SCOPE_WRITE = "ledger:write"
SCOPE_ADMIN = "ledger:admin"

def scopes_for_role(role):
    if role == "admin":
        return {SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN}
    if role == "accountant":
        return {SCOPE_READ, SCOPE_WRITE}
    return {SCOPE_READ}  # viewer
```

### 6. Nil principal = local stdio (no auth)

All scope helpers check `if principal is None: return` — local stdio MCP
(used by Claude Desktop) has no OAuth principal, so all operations are allowed.
The scope checks only fire when an HTTP transport provides a Bearer token.

## Test Coverage

| Test file | Tests | What it covers |
|---|---|---|
| test_command_registry.py | 13 | All 212 commands classified, scope/domain correctness |
| test_mcp_category_tools.py | 27 | list/execute dispatch, scope enforcement, entity isolation, all 12 domains |
| test_mcp_security.py | 40 (existing) | Old 22 tools backward compat — must pass unchanged |

## Pitfalls Encountered

1. **`cmd_onboard` returns `int`, not a tuple** — the `_run()` wrapper handles
   this with `isinstance(result, int)` check. Do not refactor `cmd_onboard`
   to return tuples; it's documented as "Never calls sys.exit" and returns
   0/1/2.

2. **`cmd_report_ageing` domain** — it's an ageing report but belongs to
   `ar_ap`, not `reports`. The `_DOMAIN_EXACT` dict handles this.

3. **213 dispatch sites, not 212** — there are 212 `cmd_*` handlers but 213
   `sys.exit(cmd_X(args))` calls in `main()` (one command has a subcommand
   alias). The regex replacement handles both.

4. **`_print_and_exit` sends errors to stderr** — the brief said stdout, but
   Cursor correctly sent errors to stderr as compact JSON so CLI output stays
   clean for piped consumers. This was a Cursor improvement over the brief.
