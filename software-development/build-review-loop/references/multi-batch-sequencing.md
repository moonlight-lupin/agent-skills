# Multi-Batch Sequencing + Codex Review Gate

Learned from three build phases (Aug 2026). 7 tasks in 5 batches, 6 tasks in 2 batches, then 7 tasks in 2 batches — all with Codex review before push.

## Multi-Batch Sequencing

When a phase has many tasks, batch them by dependency and risk:

- **Batch by independence** — tasks that don't depend on each other can run in parallel. Tasks that depend on prior output must wait.
- **Batch by risk** — highest-risk tasks first (e.g. 213 dispatch-site refactor before the registry that uses it). If the high-risk batch fails, you haven't wasted time on low-risk work.
- **Verify independently between batches** — after each batch: `git diff --stat`, grep for expected patterns, run targeted tests, then full suite. Do NOT trust Cursor's self-report.
- **Commit between batches** — each batch gets its own commit. This gives Codex a clean diff boundary for review.
- **Write the next brief while the current batch builds** — the build takes 5-8 min. Use that time to write the next batch's brief, update docs, or plan. Do NOT tight-poll.

Typical batch sizes: 2-3 tasks per batch. A single batch should produce 10-30 new tests and complete in 5-10 minutes.

### Phase 5.14 batching example

| Batch | Tasks | Build time | Tests added |
|---|---|---|---|
| 1 | T1 (SCOPE_ADMIN) + T2 (cmd_* return tuples) | ~8.5 min | +1 |
| 2 | T3 (CommandRegistry, 212 commands) | ~7 min | +13 |
| 3 | T4 (12 domain tools) + T6 (scope helpers) | ~6 min | +27 |
| 4 | T5 (21 old tools delegate to registry) | ~6 min | — |
| 5 | T7 (full verification) | — | — |

Total: 1113 → 1154 tests across 4 builds.

### Phase 5.15 batching example

| Batch | Tasks | Build time | Tests added |
|---|---|---|---|
| 1 | T1 (audit page) + T2 (entry filter) + T3 (entry detail) | ~6 min | +8 |
| 2 | T4 (verify button) + T5 (approve/reject) + T6 (verify everywhere) | ~6 min | +12 |

Total: 1154 → 1174 tests across 2 builds.

### Third batching example

| Batch | Tasks | Build time | Tests added |
|---|---|---|---|
| 1 | T1-T4 (PATCH endpoints for draft records) | ~6 min | +7 |
| 2 | T1-T3 (new REST routers for 3 modules) | ~6 min | (pending) |

Total: 1174 → 1181 tests after Batch 1.

**Key learning from one gap analysis:** Before implementing "full CRUD" from a roadmap, audit what already exists. The REST API already had GET/POST/action endpoints for all priority entities. The actual gap was only PATCH (update) for draft records + missing routers for 3 modules. The router registry controls which router files mount — modules not listed there have no API surface despite having engine functions. Always grep the existing routers before assuming CRUD is missing.

## Codex Review Gate Before Push

The user's workflow requires a Codex review pass BEFORE any push to GitHub:

1. Build (Cursor) → 2. Hermes verifies independently → 3. Commit locally → 4. Codex review → 5. Fix findings (if any) → 6. Push

**NEVER commit-and-push in one step.** Always commit locally first, then dispatch Codex, then push after the review passes.

The user corrected this explicitly: "Codex review first before push please." A prior push (M5 in Phase 5.13) went out without a separate Codex review. The user noticed and required the gate going forward.

### Codex NIT/MINOR fixes: Hermes may apply directly

When Codex returns only NIT or MINOR findings (stale comments, docstring additions, test assertion tightening), Hermes MAY apply those fixes directly without dispatching Cursor. These are documentation/test-quality tweaks, not logic changes.

The "orchestrator never hand-codes" rule ('Cursor CLI is the BUILDER, Codex is the REVIEWER — never swap roles') applies to **code logic**, not to Codex review NITs. Use judgment:
- If the fix changes behavior → dispatch Cursor
- If it's a comment, docstring, or test assertion → apply directly

### Phase 5.14 Codex review example

Codex found: NIT (stale comment about `cmd_pv_*` prefix table) + MINOR (document exit-code discard in `execute()` docstring). Both were docstring/comment fixes. Hermes applied them directly, committed, and pushed. No need to dispatch Cursor for a one-line comment fix.

### Phase 5.15 Codex review example

Codex found: 3 MINOR (test assertions too loose — missing-entry test accepted both 303 and 404; auth tests didn't check redirect location; filter tests only checked HTTP 200). Hermes tightened the assertions directly:
- Changed `assert r.status_code in (303, 404)` to `assert r.status_code == 404`
- Added `assert "/ui/login" in r.headers.get("location", "")` to auth tests
- Kept `in (302, 303)` for redirects (FastAPI uses 302 for GET redirects, 303 for POST-redirect-GET)

### Codex review command pattern

```bash
codex exec --sandbox workspace-write \
  "Read /tmp/review-phase-N.md and review the changes. Run: git diff <base>..HEAD --stat. Then review each file. Output your review as text. Do NOT make any file changes." \
  2>&1 | tail -800
```

Run with `background=true, pty=true, notify_on_complete=true`.

**Note:** Codex cannot run the full test suite in its sandbox (`fastapi` / `fastmcp` not installed — `ModuleNotFoundError`). It falls back to targeted tests or static analysis. This is fine — Hermes already verified the full suite independently. Codex's value is code review, not test execution.

## Tight-Polling Anti-Pattern (reinforced)

Despite pitfall #17 already existing in the SKILL.md, this session still tight-polled `proc_f4464e325dd5` for T5 — burning 40+ tool iterations over ~6 minutes. The completion notification arrived automatically via `notify_on_complete=true`.

**The lesson bears repeating:** dispatch with `notify_on_complete=true`, then STOP polling. Do other work. The notification WILL arrive. Every poll wastes a tool iteration that could be used for verification, brief writing, or planning.
