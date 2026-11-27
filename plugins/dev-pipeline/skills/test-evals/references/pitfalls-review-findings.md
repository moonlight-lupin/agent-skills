# Review-finding patterns

Read when a review finding touches warnings, payload shape, provenance, injection, concurrency, timestamps, or test-only flags.

## Contents

- Pitfall rules
- Semantic inversion in user-facing warnings
- Suppress warnings where the advice isn't actionable on that surface
- Check ALL payload builders when adding a response field
- Provenance fields must reflect what actually ran, not the server default
- When adding a test-only flag, update existing tests that use incomplete data
- Concurrency test thread count must not exceed the retry budget
- Audit hash chain: distinguish "empty log" from "corrupt tail"
- Stuck-action reconciliation must share the retry budget
- Timestamp normalization must cover ALL timestamp parse sites, not just new code
- String fields that interpolate into agent-loaded artifacts are an injection surface — validate content, not just type, at the schema boundary.
- Helpers that join untrusted strings to filesystem paths must re-validate the string themselves.
- A concurrency test that flakes ~30% is evidence of a race in SHARED infrastructure, not your new code — reproduce the flake before blaming the test.
- Default implied booleans toward the safe direction, derived from context.

## Pitfall rules

### Semantic inversion in user-facing warnings

15. **Semantic inversion in user-facing warnings** — Opus 5 caught that the
    seasonal_period warning said "MASE may be **inflated**" — but scoring at
    lag 1 on seasonal data makes MASE *smaller* (the lag-1 naive denominator
    is inflated by the seasonal swing, so the model looks *better*). The word
    "inflated" drops "skill" and inverts the meaning: a reader who acts on it
    concludes their score is too harsh and stops worrying — the exact opposite
    of the intent. Codex missed this; Opus 5's extended thinking caught it.
    Lesson: the wording of warnings/advice is a real review category — not a
    correctness bug (code runs fine) but a *meaning* bug where the text
    inverts the advice. When writing warnings that tell users what to do,
    have the reviewer check that the action the warning recommends actually
    addresses the problem it describes. Fix: "MASE is scaled against a
    lag-1 baseline, which on seasonal data usually **OVERSTATES skill**."

### Suppress warnings where the advice isn't actionable on that surface

16. **Suppress warnings where the advice isn't actionable on that surface**
    — if a warning says "set parameter X" but the surface (REST endpoint, GUI
    panel, MCP tool) doesn't expose parameter X, the warning is noise that
    trains callers to ignore the `warnings` array. Either add the parameter
    to the surface, or suppress the warning there and document the limitation
    in the description. In the v0.2.9 session, `compare_backends` had the
    seasonal_period warning but no `seasonal_period` parameter — and the
    MASE denominator is constant across backends within a run, so ranking is
    unaffected. Fix: suppressed the warning on `compare_backends`, updated
    the description to explain "MASE is lag-1-scaled, comparable across
    backends within one run, but NOT comparable against `backtest_timeseries`
    unless both use the same `seasonal_period`."

### Check ALL payload builders when adding a response field

17. **Check ALL payload builders when adding a response field** — when you
    add a field to one response shape (e.g. REST `result.json`), find every
    other builder that claims to match it (docstrings saying "Shape matching
    X" are contracts). In v0.2.9, `job_result_payload()` in
    `core/multi_forecast.py` (used by `/v1/jobs/multi`) was missing the new
    `warnings` field despite its docstring saying it matches `result.json`.
    Codex caught this — `grep -rn "Shape matching" core/ api/` finds all
    payload builders that need updating.

### Provenance fields must reflect what actually ran, not the server default

18. **Provenance fields must reflect what actually ran, not the server
    default** — `model_id` was always set to `model_manager.model_id` (the
    TimesFM checkpoint) even when ARIMA/ETS/Prophet served the forecast.
    The schema comment even confessed this (`"model_id names the TimesFM
    weights even on runs an ARIMA/ETS/Prophet backend served"`). Fix: add a
    `model_id` property to every backend class (`statsmodels-arima-0.14.6`,
    `prophet-1.3.0`, etc.) and use `backend.model_id` at every audit-record
    call site. `grep -rn 'model_id=model_manager\|model_id=self\.mm' core/`
    finds all call sites. `score_forecast_accuracy` inherits the correct
    value from the AuditRecord — no separate fix needed. The full fix pattern
    includes re-checking every test stub that pinned the old provenance value.

### When adding a test-only flag, update existing tests that use incomplete data

22. **When adding a test-only flag, update existing tests that use incomplete data** — when you add `_fill_defaults=False` to a function (making it fail on incomplete data by default), existing tests that call it with incomplete data will break. The builder (Cursor) should update those tests to pass `_fill_defaults=True` where the test data is intentionally minimal. This is NOT the builder modifying Hermes contract tests — these are pre-existing tests adapting to a new API contract. Verify the builder only added the flag to tests with incomplete data, not to tests that provide complete data. In one review session, Cursor correctly added `_fill_defaults=True` to 8 call sites in `test_phase2_loop1.py` and `test_phase2_loop2.py` — all were tests with minimal deal dicts missing `stage`/`client_name`.

### Concurrency test thread count must not exceed the retry budget

23. **Concurrency test thread count must not exceed the retry budget** — when writing a threading-based race test for a function protected by `_with_retry` (max_attempts=3), spawning 5 concurrent threads means 2 will exhaust their 3 retry attempts under contention and silently return None. The test expects all to succeed but gets N-1. This is flaky by construction, not a real bug. Fix: set thread count ≤ max_attempts (3 threads for 3 retries). Also add jittered backoff (10-50ms random sleep between retries) to `_with_retry` so concurrent retries don't all hit the lock at the same instant. This bit one phase-loop test on CI (passed locally, failed on Python 3.11 runner).

### Audit hash chain: distinguish "empty log" from "corrupt tail"

24. **Audit hash chain: distinguish "empty log" from "corrupt tail"** — when implementing a hash chain for tamper-evidence, `_last_hash()` must NOT silently return the genesis value (`""`) when the last line is unparseable or lacks a `_hash` key. That makes corruption indistinguishable from "new file" and silently restarts the chain, defeating tamper-evidence. Fix: raise on corrupt/legacy tail. The caller catches and writes a `_chain_restart: true` marker record. `verify_audit_chain()` recognizes restart markers as legal chain breaks. This makes the break visible instead of silent. Proven in a phase build (Opus batch B1).

### Stuck-action reconciliation must share the retry budget

25. **Stuck-action reconciliation must share the retry budget** — when implementing `revert_stuck_action` (re-arming a crashed worker's `executing` action), it MUST increment `retry_count` and check `MAX_RETRIES`, sharing the same budget as `mark_failed`. Without this, a crash-loop re-arms the action without bound, reopening the unbounded duplicate-send hole that `MAX_RETRIES` exists to close. The crash-loop case is precisely where ambiguity about whether the send landed is highest. Proven in a phase build (Opus batch B2).

### Timestamp normalization must cover ALL timestamp parse sites, not just new code

26. **Timestamp normalization must cover ALL timestamp parse sites, not just new code** — when fixing naive-timestamp bugs (timezone-aware vs naive comparison raising `TypeError`), apply the fix to ALL functions that parse ISO timestamps, not just the new ones you're writing. Extract a `_parse_ts(value) -> datetime | None` helper that normalizes naive to UTC, and use it everywhere. In one phase build, the fix was applied to `find_stuck_actions` and `revert_stuck_action` but NOT to `_is_expired` and `_is_approval_lapsed` — where the `TypeError` was caught and returned "not expired" (fail-open), making a lapsed approval stay executable indefinitely. Proven in a phase build (Opus milestone M1).

### String fields that interpolate into agent-loaded artifacts are an injection surface — validate content, not just type, at the schema boundary.

28. **String fields that interpolate into agent-loaded artifacts are an injection surface — validate content, not just type, at the schema boundary.** Reproduced in review: a newline-bearing `description` forged an entire fake step list ahead of the real one, and a backtick in a command `pattern` closed the code span so the remainder rendered as prose instructions. A generator's output is an instruction file an agent acts on, not a report; "the operator wrote the YAML" is not a trust boundary when the YAML was drafted from conversational material. Reject control characters and newlines in short fields, reject backticks in code-span-rendered values (or fence with a longer backtick run), keep multi-paragraph fields single-line, and reject `..`, `~`, backslashes, and drive letters in relative paths — a leading-`/` check alone admits `../` traversal.

**Input rejection alone cannot make a markdown renderer safe — render inertly by construction.** Expect the reviewer to chase the same injection class across sibling surfaces, one field per round: values gated → keys still echo verbatim; keys gated → a key starting with `##` still forges a real heading at line start; inline markdown still live in values. A gate on strings only blocks control chars and backticks — it cannot stop block-level syntax that turns hostile at line-start position. Gate every interpolated field (key AND value) AND render unknown/untrusted keys and string values inside code spans so block and inline syntax are inert in the output; a sanitizer is only correct when its own name matches what it protects (if you wrap in backticks at render, reject backticks at validation). Probe-verified across four review rounds on one generator; write the pinning test with a `## heading` payload at line start, not just a newline payload.

### Helpers that join untrusted strings to filesystem paths must re-validate the string themselves.

29. **Helpers that join untrusted strings to filesystem paths must re-validate the string themselves.** A name-conflict checker built `root / "skills" / name` without applying the schema's kebab+length validation, so `../skills/x` and `/etc` both reached the join; it only failed by luck because those paths existed. Callers will assume the helper vouched for the name (the next batch writes `skills.local/<name>/` through the same string). Re-run the schema validator at the top of the helper — one line of reuse, not a new check.

### A concurrency test that flakes ~30% is evidence of a race in SHARED infrastructure, not your new code — reproduce the flake before blaming the test.

30. **A concurrency test that flakes ~30% is evidence of a race in SHARED infrastructure, not your new code — reproduce the flake before blaming the test.** A two-thread barrier race test intermittently raised bare `OperationalError: database is locked`. Trace the exception TYPE first: `BEGIN IMMEDIATE` contention is wrapped into the codebase's own ConcurrencyError, so an UNWRAPPED sqlite OperationalError means it escaped from connection SETUP, not from the mutation path. Root cause (reproduced in isolation with a minimal two-thread sqlite script): two connections racing `PRAGMA journal_mode=WAL` on a FRESH database — busy_timeout does NOT cover the journal-mode pragma. Fix in the shared layer with a small retry loop (attempts + backoff); then loop the previously flaky test ~15x to confirm the flake is gone, and run the shared module's own suite before committing. Isolation recipe: strip the test back to the smallest script that still reproduces (two threads, barrier, connect+PRAGMA), bisect which statement raises by wrapping each in try/except.

### Default implied booleans toward the safe direction, derived from context.

31. **Default implied booleans toward the safe direction, derived from context.** A `review_queue` step with `requires_approval` omitted normalized to False — the pointer strip then rendered a connector-mutation step as a bare imperative, collapsing Observe→Approve→Execute by omission, and no test caught it because the contract shared the same default. When a flag gates a guardrail, derive the default from the sibling field (approval-style signal ⇒ approval required) — and when the flag gates a hard invariant (approval, tamper-evidence), refuse the explicit unsafe value outright instead of merely defaulting safe: an author-written opt-out is a schema-level gate bypass, and the operator will approve the stricter contract when you present it. Update the pinning test to the stricter contract in the same commit so the suite pins the decision, not the old permissiveness.
