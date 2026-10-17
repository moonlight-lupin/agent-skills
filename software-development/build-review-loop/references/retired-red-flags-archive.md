# Retired Red Flags (archive from the 2026-09-12 refactor)

Restatements removed from SKILL.md ## Red Flags during the writing-for-agents dedupe.
Each rule's single source of truth lives in ## Pitfalls, ## Workflow, or the Verification
Checklist of SKILL.md — these lines are preserved verbatim for the no-trim record only.

- Findings INCREASE between rounds — fixes introduced regressions; stop and investigate

- Builder and reviewer are the same model — defeats the cross-model diversity principle

- No commit between review rounds — reviewer can't diff what changed

- Reviewer prompt is inlined instead of written to a file — long inline prompts get parsed poorly

- Trusting `tail -5` output as the full builder output — use `process(action="log")` for complete output

- Piping review/agent output through `tail` — the pipe truncates at the shell level; `process(action="log")` only sees the already-truncated result. Write review output to a file and `read_file` it instead

- Skipping Hermes independent verification (Step 4) — the builder's "all checks passed" is a claim

- No convergence check — each round should produce strictly fewer findings

- Stale mock payload in tests — test passes against a hand-rolled shape that doesn't match the real function's return; verify mock shapes at each integration boundary

- Orchestrator hand-coding fixes instead of dispatching through Cursor — even one-line patches must go through the builder when build-review-loop is active

- Tight-polling background builds — loop-polling `process(action="poll")` every few seconds burns the iteration budget. Dispatch with `notify_on_complete=true` and move on to other work.

- Pushing without Codex review — the user requires a Codex review pass before ANY push. Never commit and push in one step. Commit locally, review, then push.

- Reporting shipped before CI is green — always check `gh run list` for `conclusion: "success"` before telling the user the work is done.

- `setdefault` on security-critical parameters — a validated parameter merged via `setdefault` into untrusted input can be overridden by the caller. Force the validated value (`call_args["entity"] = entity`), never default it.

- No cross-surface property tests — when CLI, REST, MCP, and GUI each implement authorization independently, per-surface tests miss cross-surface regressions. Three property tests (isolation, scope, role) catch what per-surface tests cannot. See `references/security-property-tests.md` for implementation patterns.

- A passing test that checks nothing — a scope test that shells to the CLI with a wrong name transform runs 0 commands, compares identical snapshots, and reports success. Assert minimum execution count. Use `COMMAND_REGISTRY.execute` in-process, not subprocess.

- Exempting a route from a property test without a real separate test — the exemption comment becomes a lie, and the property goes untested on that route.

- Argument-dispatching handlers classified as a single scope — a handler whose scope depends on `args.subcommand` can't be classified statically. Split it into separate handlers per subcommand.

- Application-level invariant checks without DB enforcement — read-then-insert is TOCTOU-vulnerable under concurrent transactions. Add DB triggers as the authoritative guard.

- Polymorphic link tables using INTEGER target_id — some models use string codes (accounts). Use TEXT to support both integer IDs and string codes. SQLite rowid has no PostgreSQL equivalent.

- Cross-company polymorphic links without target_id == company_id check — company A can link to company B's records.

- PRAGMA foreign_keys=OFF in migration files is a no-op inside a transaction — DROP TABLE cascades to dependent rows. Rename dependent tables aside before rebuilding parent.

- SQL SUM() over TEXT money columns returns float — aggregate in Python over Decimal; make the money coercion helper reject float.

- Grep-guard tests that cover only one file class (.sql but not .py) leave the same defect live in the sibling class — extend the grep to all runtime files.

- Contract tests for external audit findings committed before verifying failure reasons — harness errors (TypeError, IntegrityError, AttributeError) are not honest RED.

- A full-suite verification run overlapping a builder dispatch on the same working tree — false failures that look like regressions. One repo-touching job at a time; write the next brief outside the tree while waiting.

- Contract tests that decorate current-era records with legacy shapes (new rows on v2-hashed parents, internally inconsistent test pairs) — rebuild the legacy era faithfully: mutate existing rows, recompute historical digests, set version columns as the old code would have. When two contract tests cannot both pass, the tests are wrong.

- Real companies, clients, or the user's employer used as test fixtures or example names — always neutral fictional names; scan fixtures before committing (pitfall #63).

- Subprocess-based red tests written without probing the CLI's real output contract first (stdout vs stderr, exit codes, argparse rejection) — they fail for the wrong reason or read empty error dicts (pitfall #64).

- INSERT + `except IntegrityError: pass` as an idempotency mechanism — works on SQLite, aborts the transaction on PostgreSQL. Use `ON CONFLICT ... DO NOTHING` and pin it with a grep-guard test (pitfall #66).

- An "exists"/idempotent fast path that returns success without checking the existing object matches the request — a collision with a different company becomes a silent no-op (pitfall #67).

- Green contract tests achieved through unsanctioned production changes — read the builder's diff for helpers, markers, or storage-format changes the brief never asked for; verify HOW tests pass, not just THAT they pass.

- Bulk operations calling single-item functions that commit individually — partial failures leave committed data. Pre-validate all, then single-transaction insert.

- Non-unit exchange rates accepted in base-currency paths — produces contradictory currency data (reporting_rate != 1 but debit/credit = amount).

- Dispatching Cursor as reviewer when it was the builder — same-model review shares blind spots. Cursor builds, Codex + Opus review. The user corrected this explicitly.

- Dispatching multiple Cursor builds for independent modules in parallel without using named sessions — when three vertical modules each create their own directory with no shared files, three Cursor CLI processes can run simultaneously. Use `session=` parameter on `terminal(background=true)` to give each build an isolated browser/terminal session so they don't clobber each other. Verify each build independently before committing. Commit in dependency order (leaf modules first). This is the multi-vertical parallel build pattern.
