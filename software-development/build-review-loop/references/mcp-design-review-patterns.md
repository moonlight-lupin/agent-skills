# MCP Design Review Patterns

Patterns discovered during an MCP architecture review (Aug 2026).
These apply to any project building a Composio-style category-based MCP tool
surface over an existing CLI.

## Contents

- Pattern 1: Design Stoppers vs Code Fixes
- Pattern 2: Fail-Open Scope Classification
- Pattern 3: Missing Privilege Tier
- Pattern 4: JIT Discovery Response Size
- Pattern 5: Review-and-Audit GUI Before CRUD
- Pattern 6: Expose Tamper-Evidence Everywhere

## Pattern 1: Design Stoppers vs Code Fixes

A review finding can be a "design stopper" — a prerequisite refactor that cannot
be fixed in the current build cycle and changes phase sequencing — rather than
a code fix to dispatch to the builder.

### Example: sys.exit in CLI handlers

**Finding:** All `cmd_*` CLI handlers call `_output()` or `_error()`, both of
which end in `sys.exit()`. `SystemExit` inherits `BaseException`, not `Exception`,
so Starlette's exception middleware does not catch it. This means:

- The MCP command registry (Phase 5.14) cannot call `cmd_*` handlers directly.
- The GUI write routes (Phase 5.15) cannot call `cmd_*` handlers directly.

**Resolution:** This is not a bug to fix — it is a prerequisite refactor:
`cmd_*` handlers return a value; a thin CLI wrapper does the printing and
exiting. This refactor unblocks both phases and must be sequenced before either.

**How to handle:**
1. Document the prerequisite in the roadmap/spec.
2. Update phase sequencing to include the refactor first.
3. Do NOT attempt to fix it in the current build cycle unless it is in scope.
4. Note that the refactor serves two phases — one piece of work, two unblocks.

## Pattern 2: Fail-Open Scope Classification

When building a command registry that classifies commands as read or write,
never use name-pattern matching with a read default.

### Example: 13+ mutating commands missed by pattern

**Finding:** The MCP architecture doc proposed classifying write commands by
matching ~23 name patterns (`*_create`, `*_post`, `*_approve`, etc.). Anything
unmatched defaulted to `read`. The reviewer ran the pattern against all 212
handlers and found 13+ mutating commands that were missed:

- `user_update` → `update_user()` (changes user role)
- `user_assign_entity` → `assign_entity()` (grants entity access)
- `saltedge_config` → `set_se_config()` (writes bank credentials)
- `fx_rate` → `fx_set_rate()` (sets rates used in revaluation)
- `recon_match` → `recon_create_match()` (settles subledger items)
- `budget_set_lines`, `inv_adjust`, `consol_member_add`, etc.

The first two are security-critical: a `ledger:read` token that can reach
`user_update` can change its own role, and one that can reach
`user_assign_entity` can grant itself another company's books — unwinding both
halves of the entity isolation.

**Fix:**
1. **Default deny.** Unknown commands classify as `write` (more restrictive).
2. **Explicit classification.** Every `cmd_*` gets an explicit scope in the
   registry, assigned by a human during the build.
3. **Test enforcement.** A test asserts every `cmd_*` carries a classification.
   A new command without a classification fails CI.

## Pattern 3: Missing Privilege Tier

When a domain tool bundles admin operations (backup, restore, vacuum, module
install), the OAuth scope model must have a tier for it before the tool ships.

### Example: ledger:admin scope

**Finding:** The OAuth model had two scopes: `ledger:read` and `ledger:write`.
`scopes_for_role` gives any accountant `ledger:write`. The `ledger_admin`
domain tool bundles `restore` (overwrites a ledger from a file), `backup`,
`vacuum`, `l10n_install`, `module_*`, and `agent_*`.

On the design as written, an ordinary accountant token can restore over the
company's books, install a localisation module, or drive the agent.

**Fix:** Add `ledger:admin` scope (admin only) before `ledger_admin` ships:

```python
def scopes_for_role(role: str) -> set[str]:
    if role == "admin":
        return {SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN}
    if role == "accountant":
        return {SCOPE_READ, SCOPE_WRITE}
    return {SCOPE_READ}  # viewer
```

## Pattern 4: JIT Discovery Response Size

When a domain tool's `list` action returns all commands in a domain, returning
full arg schemas for every command moves the context cost from tool definitions
(per-turn) to tool results (transient). This still wins — but only if `list`
returns terse summaries (name + one-line description), not full schemas.

A second call with `args={"command": "<name>", "schema": True}` fetches one
command's full arg schema. This keeps the discovery response small.

## Pattern 5: Review-and-Audit GUI Before CRUD

When the product positioning is "agent-driven, human review and audit," the
GUI's primary job is to surface audit artifacts — not to provide booking
interfaces. Full CRUD is the secondary job.

The cheap half of the GUI:
1. Audit log page with `source` column (cli/api/agent provenance)
2. Pending approval filter on entries
3. Entry detail route with lines (debits, credits, accounts)
4. "Verify books" button calling `verify_hash_chain()`
5. One write action: approve/reject on submitted entries

This is a fraction of the effort of full CRUD but delivers the product's
primary value proposition. Sequence it before the CRUD build.

## Pattern 6: Expose Tamper-Evidence Everywhere

`verify_hash_chain()` was internal to `close_period` only. An auditor cannot
ask the system to verify the books — they can only close a period and infer it
passed. Tamper-evidence you cannot invoke on demand is a feature an auditor
must take on trust — the opposite of its purpose.

Expose it on every surface:
- CLI: `ledger audit verify`
- REST: `GET /audit/verify`
- MCP: via command registry
- GUI: a "Verify books" button
