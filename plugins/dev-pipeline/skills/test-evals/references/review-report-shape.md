# Review report shape (ask for this in every review brief)

Read before writing every review brief. Demand this shape, then open the session record that matches the surface under review.

## Contents

- Review report shape (ask for this in every review brief)
- Mock at ALL import sites, not just the source module
- BLE001 (blind except) is often intentional for graceful degradation

## Review report shape (ask for this in every review brief)
A per-file verdict table (SHIP / FIX-FIRST / BLOCK) at the top, findings after, each with file:line + the minimal fix. This is the shape the operator reads first and the fix-round brief cites by path. Ask for a merge-order section too (blockers → guardrails → fail-soft → NICE post-merge); fix rounds then implement all reproduced BLOCKING/MAJOR findings in ONE brief, sequenced in that order — one brief per round with the order carried inside it (the confirm-round protocol's ONE-deduped-list rule), never split into one dispatch per group. For reviews of wiring/live-seam code, add to the brief: production modules must not reference test modules (the reviewer greps for it), and "reachability" is a named priority — every new public function checked for ≥1 production caller.

A concrete session (a dogfooding round 2): Codex + Opus 5 parallel review, the semantic inversion catch
("inflated" vs "overstates skill"), the actionable-advice suppression pattern,
and the multi-surface payload builder sync issue.

A concrete session — backup-restore + health-diagnostics review (2026-08-11 Opus 5 session: spec-vs-test pin conflicts, TDD discipline finding).

A concrete case — the model_id provenance fix:
pattern: when an audit field is always set from the server default rather
than the backend that actually ran, every audit record lies about what
produced the forecast. The fix: add a `model_id` property to every backend
class and use `backend.model_id` at every audit-record call site.

A concrete catch — a MASE baseline bug: the function's `train=None` fallback used the holdout
window's own volatility as the MASE denominator instead of the training
history's naive error, sign-flipping "worse than random walk" into "beats
random walk." The fix pattern: always check whether callers actually pass
the non-fallback argument — the fallback is a correctness hazard, not a
convenience.

A CI pre-existing-failure incident shows the version-pin hardcoded
regex pattern — when CI fails on a pre-existing dependency version test,
grep both `tests/` AND `.github/workflows/` for hardcoded version strings.

A concrete case — a 3-phase production readiness build: deferred review
findings carried forward as next-phase contract tests, Opus multi-file
review with file naming pattern (4 successes), parallel Codex+Cursor
dispatch, the _fill_defaults backward compat technique, flaky race test
fix (thread count ≤ retry budget), audit hash chain corrupt-tail
detection, the _parse_ts helper for all timestamp sites, stuck-action
reconciliation sharing MAX_RETRIES budget, and Claude Desktop
compatibility investigation. 1802→1895 tests across 3 phases with 0
regressions.

A concrete case — a phased upgrade build (2026-08-15): note-capture hook,
writing-for-agents review fixes (workspace-access extraction, routing
tail removal, completion criteria, negation→positive), wiki search
subcommand + context injection hook. Dual-reviewer (Codex+Opus) findings
including the stop-word substring matching bug, dangling shared reference
path, constraint deletion in negation rewrites, and Opus max-turns 25
requirement. 1910→1947 tests across 3 sub-phases with 0 regressions.

A concrete case — a 4-batch surface-hardening build (2026-08-22): 981→1095 tests, Grok high
review found 1 BLOCKING (HTTP MCP authz never wired — BearerGate stashed
principal on ASGI scope but tools read from env var) + 8 MAJOR (encryption
fail-open, hash chain NULL bypass, migration partial-apply, restore
non-atomic, busy_timeout on only 1 of 5 connection paths, MCP auto-creates
unregistered entity DBs). All fixed in one TDD fix cycle. Key lesson: when
the user does not repeat "Opus" in a session, do NOT silently default to
Grok — check canonical memory for their preferred review model.

A concrete case — a `delegate_task` subagent review session: 13 findings (1 BLOCKING tenant-ACL cache leak, 2
MAJOR query-flow design decisions, 5 MINOR, 4 NIT), the pre-emptive fix
pattern, and the test helper pattern for mocking `get_embedding` at multiple
import sites.

### Mock at ALL import sites, not just the source module

When a function is imported at module level in multiple files (e.g.
`get_embedding` imported in both `search.py` and `search_stages.py`),
patching only `app.embeddings.get_embedding` leaves the other import
site calling the real function. Tests will fail with network/credential
errors that look unrelated to your mock. Patch at every
`app.<module>.<function>` site where the name is bound. A
contextmanager helper that patches all known sites is cleaner than
scattered `with patch(...)` blocks:

```python
@contextmanager
def _patch_embedding(embedding=None):
    emb = embedding if embedding is not None else _make_embedding()
    with patch("app.search.get_embedding", return_value=emb), \
         patch("app.search_stages.get_embedding", return_value=emb):
        yield
```

### BLE001 (blind except) is often intentional for graceful degradation

Ruff flags `except Exception` as a code smell, but for features that MUST
fall back silently (HyDE, cache, CRAG timeout, provider retry), a broad
catch is the correct pattern. Narrowing the catch risks leaking an
unexpected exception type that breaks the degradation contract. When a
module's design contract is "never break the caller on failure," leave
the BLE001 and add a comment. Don't let ruff auto-fix it.
