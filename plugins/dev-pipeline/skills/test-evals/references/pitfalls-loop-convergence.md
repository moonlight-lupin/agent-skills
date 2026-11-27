# Loop convergence pitfalls

Read before every batch and every fix round. These rules gate RED authoring, review carry-forward, pin retargets, and reachability.

## Contents

- Pitfall rules
- Opus finds what Grok misses
- Fix security issues pre-emptively while the review runs
- TDD tests must exercise the PUBLIC interface, not just internals
- Multi-phase builds: carry deferred review findings into the next phase's contract tests
- Review each batch's artifact against its DOWNSTREAM consumer, not just its RED contract.
- Delegate RED-test authoring as brief → author → report, then GREEN as a separate brief that cites the report.
- Wiring batch: pin the LIVE entry-point contracts with RED tests BEFORE editing the live files.
- Count pins in OTHER pre-existing test files break when a wiring batch extends a shared registry — update them yourself in the same commit, only when the builder is test-forbidden.
- GREEN briefs that name an exact file allowlist must include the stop-and-report escape hatch.
- Reachability: every new public function needs ≥1 production caller — contract tests passing proves nothing about wiring.
- Pin ordering/docstring contracts with exact-sequence assertions, not membership checks.

## Pitfall rules

### Opus finds what Grok misses

7. **Opus finds what Grok misses** — in one batched round, the Grok
   4.5 High review of Batch A found 4 MAJOR findings (MASE denominator,
   score_actuals pinball, seasonal_period wiring, TimesFM determinism).
   The subsequent Opus review found 3 additional MAJOR findings the Grok
   review missed: (a) `/v1/anomaly` holdout=0 DoS surface — route never
   passed `max_periods` to core despite supporting it, (b) work-cap
   fragility — duplicated `_ANOMALY_MIN_HISTORY=8` literal could desync
   from core, and MCP had no cap at all, (c) `positive_only` silent
   history mutation in Pydantic validator with no warning. The pattern:
   Grok catches correctness and wiring gaps; Opus catches security, DoS,
   and data-integrity concerns. Both are needed for a thorough review.

### Fix security issues pre-emptively while the review runs

11. **Fix security issues pre-emptively while the review runs** — when you
    spot a BLOCKING issue (e.g. tenant ACL missing from a cache key) while
    the Opus review is still running, fix it immediately in the working tree
    and add a regression test. Then when the review confirms the same issue,
    you already have the fix + test and can note "already fixed" in your
    response. This saves a full review-fix-rerun cycle. The key insight: the
    review reads a frozen diff, but you can keep working on the live tree.
    Generate a fresh diff for the commit that includes both the original
    features AND the pre-emptive fix.

### TDD tests must exercise the PUBLIC interface, not just internals

12. **TDD tests must exercise the PUBLIC interface, not just internals** —
    when writing TDD tests for a change that affects an API endpoint or MCP
    tool return shape, a test that calls the internal function (e.g.
    `Forecaster.forecast()`) and asserts on `record.warnings` will pass even
    if the API adapter (REST `result.json`, MCP tool return dict) never
    surfaces the field. The test proves the data exists, not that the caller
    can see it. Always add a test that goes through the actual public surface:
    submit a job via `TestClient`, poll for completion, fetch `result.json`,
    and assert the new field is present. For MCP, use the `_call(server, tool,
    args)` helper pattern (see `test_mcp_ownership.py`). Without this, a
    regression that drops the field from the adapter is invisible to the
    suite. In one dogfooding session, Codex caught this: the initial
    `test_forecast_returns_warnings_array` only called `Forecaster.forecast()`
    directly — it would have passed even if both the REST and MCP changes were
    reverted. The fix was to add `test_result_json_includes_warnings` that
    goes through the full `TestClient` → POST `/v1/jobs` → poll → GET
    `result.json` path.

### Multi-phase builds: carry deferred review findings into the next phase's contract tests

19. **Multi-phase builds: carry deferred review findings into the next phase's contract tests** — when a reviewer (Opus or Codex) finds MAJOR/MINOR issues that are not blocking but should be fixed, do NOT just fix them silently. Add them to the next phase's contract test file as TDD red tests. This ensures: (a) the fix is verified by a Hermes-written test, (b) the deferred item is not forgotten, (c) the test encodes the expected behavior for future regressions. Pattern:
    - Phase N review finds Major X → deferred to Phase N+1
    - Phase N+1 contract test file includes `TestXFromPhaseN` class
    - TDD red → Cursor builds → test passes → item closed
    This was proven in a multi-phase production roadmap build: Phase 1 Opus review deferred 5 majors to Phase 2, all 5 became Phase 2 contract tests, all fixed and verified.

### Review each batch's artifact against its DOWNSTREAM consumer, not just its RED contract.

27. **Review each batch's artifact against its DOWNSTREAM consumer, not just its RED contract.** The contract tests cannot see ahead: a generator emitted a SKILL.md without YAML frontmatter — every bundled skill carries frontmatter and the NEXT batch's registry discovery keys off it — yet all contract tests passed because no test pinned frontmatter. When writing the batch brief, name what the next batch does with this artifact and add a RED test for that requirement; a one-line generator change now beats a breaking regeneration after user YAML exists.

### Delegate RED-test authoring as brief → author → report, then GREEN as a separate brief that cites the report.

32. **Delegate RED-test authoring as brief → author → report, then GREEN as a separate brief that cites the report.** Write the authoring brief with the target test count, the spec sections to read, the existing test patterns to mirror, and hard rules (test file only, no implementation, no skipped tests). The author's ambiguity-resolution report — every spec ambiguity it hit, its chosen resolution, and its seam decisions (no invented kwargs, no audit assertions where no seam exists, fixture pattern to mirror) — becomes PART of the GREEN contract: cite it by path in the implementation brief so the builder inherits the seams instead of inventing different ones. Verify RED state yourself (right failure reason, full suite untouched) before dispatching GREEN. Batches structured this way land in one builder dispatch each with zero contract/builder conflicts.

A concrete session example:
10 MAJOR findings from Grok + 3 MAJOR from Opus across 2 batches, the
pattern of what each review model catches (Grok: correctness + wiring;
Opus: security + DoS + data-integrity), and what they miss.

### Wiring batch: pin the LIVE entry-point contracts with RED tests BEFORE editing the live files.

33. **Wiring batch: pin the LIVE entry-point contracts with RED tests BEFORE editing the live files.** The wiring batch (ALL_HOOKS registration, CLI subcommand dispatch, doctor check registration) is the smallest batch but the riskiest seam — it touches files other features import. Read the live entry points first (the ALL_HOOKS dict shape, the build_parser nested-subparser pattern, the doctor CHECKS list), write RED tests asserting the exact ABSENCE (workflow hooks not in ALL_HOOKS, workflows parser missing, install dir undiscovered), commit RED, then GREEN. RED-for-wiring is not "module missing" — it is per-test absence against current code; state each test's RED reason in the author report.

### Count pins in OTHER pre-existing test files break when a wiring batch extends a shared registry — update them yourself in the same commit, only when the builder is test-forbidden.

34. **Count pins in OTHER pre-existing test files break when a wiring batch extends a shared registry — update them yourself in the same commit, only when the builder is test-forbidden.** When ALL_HOOKS grows 10→12, an unrelated test pinning `total == 10` fails; that is a legitimate contract update (the new hooks ARE registered), not test-gaming. Distinguish: a pin updated to match a deliberate, verified registration is a contract update; a weakened assertion inside the NEW feature's contract test is a BLOCKING finding (pitfall 9). If the GREEN brief forbade the builder from touching tests/, the orchestrator makes the count-pin edit directly — grep the test tree for the old count first (`grep -rn "== 10\|== 3" tests/test_<module>.py`), update numbers only, and say so explicitly in the commit message and status report.

### GREEN briefs that name an exact file allowlist must include the stop-and-report escape hatch.

35. **GREEN briefs that name an exact file allowlist must include the stop-and-report escape hatch.** Name every file the builder may edit, forbid tests, then add: "If another change seems required, STOP and write why in the report." A builder hitting a real blocker (RED contract pins an entry point the named files cannot host — e.g. a line-capped god-file needing a new module) then stops with a justification instead of silently widening the diff or weakening a test to fit. The orchestrator inspects the justification before committing: a new module that the RED contract requires and that keeps delegation clean (no logic duplication) is fine; an edit to a file on the forbidden list is a finding.

### Reachability: every new public function needs ≥1 production caller — contract tests passing proves nothing about wiring.

36. **Reachability: every new public function needs ≥1 production caller — contract tests passing proves nothing about wiring.** Before declaring a feature build complete, grep each new public entry point for non-test callers (`grep -rn "func_name" shared/ --include="*.py" | grep -v test`). A full suite can be green while US acceptance criteria are unreachable in real runs: bind/skip/fire functions with zero callers mean the approval signal, GO verdicts, and scheduled firing never execute; and a hook that requires an `exit_code=`/`config=` kwarg is dead when the documented runtime signature supplies neither — tests that pass those kwargs by hand are exactly what makes dead paths look wired. Two closing gates per build: (a) drive at least one test per hook signal through the DOCUMENTED runtime signature with no extra kwargs; (b) any feature gate hanging on a runtime context field with no precedent in the repo (e.g. `context["session_id"]`) is a LIVE smoke-run-before-merge requirement — do not merge on synthetic evidence alone (procedure in `review-commit/references/release-hygiene.md` — live smoke testing before a release)n: branch the installed copy, drive modules directly, stop at the real approval gate, restore).

### Pin ordering/docstring contracts with exact-sequence assertions, not membership checks.

38. **Pin ordering/docstring contracts with exact-sequence assertions, not membership checks.** When a docstring or test comment states an output-order contract ("least relevant sinks deepest", "X sorts first by prob desc"), assert the exact expected list or exact head/tail slices (`order[-2:] == [...]`, `order == [...]`), not `in order` plus `set(order)` — a sort-direction bug still contains every element, so membership passes. A test comment that describes intended-but-unimplemented order is a silently unpinned contract: grep the test tree for the contract's wording before touching a sort key, and pin any sibling comments you find in the same commit as the fix (proven when a two-week trial audit surfaced a sort inversion whose own repo test comment had described the correct order all along).
