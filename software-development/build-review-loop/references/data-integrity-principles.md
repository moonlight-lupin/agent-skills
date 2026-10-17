# Data Integrity and Migration Principles

Distilled from past build-review-loop projects. Data-layer rules that stay true
across codebases. Reached from SKILL.md ## Pitfalls.

## Contents

- Invariants and transactions (items 1, 5, 15)
- Schema and migration safety (items 3, 4, 11)
- Idempotency and API contract (items 8, 9, 10)
- Numeric storage (items 2, 6)
- Fixtures for data migrations (items 12, 13, 14)
- Module design residue (items 16, 17)

## Invariants and transactions

1. **Enforce invariants at the DB level** — application-level read-then-insert checks are TOCTOU-vulnerable under concurrent transactions. Two transactions can both observe an acceptable state and insert rows that jointly violate the total. Fix with database triggers that enforce the invariant atomically; keep the application-level check as a faster-path for error messages. The trigger is the authoritative guard.

5. **Bulk operations must be atomic** — pre-validate ALL items, then insert in one transaction. Per-item commits turn a mid-batch failure into committed partial data.

15. **Audit every mutation — and thread commit ownership explicitly** — an audit/logging helper that commits internally breaks the outer function's atomicity. Separate mutation logs from transactional writes; pass a commit-ownership flag through helpers that write.

## Schema and migration safety

3. **Foreign-key enforcement and table rebuilds** — `PRAGMA foreign_keys=OFF` is a no-op inside a transaction. A DROP-rebuild of a parent table cascates through child foreign keys referencing the parent BY NAME — renaming the child aside does NOT protect populated data when the child's FK definition still points at the parent. Run migrations outside foreign-key enforcement (a runner directive, not an in-file pragma), then verify with a foreign-key check before commit.

4. **Upgrade-path testing** — migrations that pass on a fresh empty schema hide data loss on populated databases: there is nothing to cascade-delete. Write upgrade-path tests against a populated legacy fixture, and re-audit any drop-and-rebuild migration that could ever re-run on real data.

11. **Migration attestation coverage** — for any rewrite over hash-chained or otherwise attested rows, determine (a) which fields the attestation payload covers, (b) what values the historical digests were computed FROM, and (c) whether every consumer of skipped rows still has a decode path. A skip rule that outlives its decoder is a silent data-corruption path. A rewrite converging with attested values can keep verification green; a skip rule cannot. Check migration ORDERING: a backfill that stamps version columns must not run before a repair that branches on those versions unless the interaction is intended.

## Numeric storage

2. **Polymorphic link tables** — the target key must be TEXT: some targets key on string codes, and numeric rowids are backend-specific and unstable. Scope validation must include the scope column (e.g. assert the target belongs to the requesting scope), not just existence — otherwise cross-scope links pass.

6. **Money and quantity columns** — store TEXT decimal strings and aggregate in application code over Decimal. SQL `SUM()` over TEXT columns coerces to REAL and launders binary rounding error into the result; `CAST(x AS NUMERIC)` still yields REAL. Guard the choke point: one coercion helper used everywhere, rejecting float outright with TypeError, so every remaining REAL leak becomes a loud test failure.

## Idempotency and API contract

8. **Idempotent inserts — suppress duplicates in SQL, never by catching IntegrityError** — on PostgreSQL the unique violation has already aborted the transaction; the catch cannot restore it, so the follow-up commit/select runs against a failed transaction. Use `INSERT ... ON CONFLICT (<col>) DO NOTHING` on both backends. A fix verified only on one backend can hide the other's defect even with a green full suite — keep a gated live-backend test for the duplicate-call path. Guard with a grep-style test: every insert branch carries the conflict clause (exclude the docstring — it names the clause too).

9. **Extend existing registration functions by delegation, not by copying their INSERT SQL** — the duplicated copy is where the unsafe suppression pattern reappears.

10. **Two-step writes and the exists-path contract** — (a) write related fields in ONE insert/transaction; a failure between steps leaves partial state the idempotent re-run never repairs (it returns "exists" before reaching the second write). Make the exists path self-heal missing pieces. (b) An "exists" fast path must verify the request matches what exists — returning success for a mismatched request silently provisions nothing while still performing side effects, and makes a collision indistinguishable from a legitimate re-run; a mismatch is an error naming the occupied resource. (c) Refusal errors must name the remedy — the flag or command that supplies the missing value — not just restate the cause.

## Fixtures for data migrations

12. **Contract tests for data migrations must reconstruct the LEGACY era** — the fixture rebuilds the state the OLD code produced: mutate current-era rows into the old storage format AND derive integrity artifacts (hash, version column) exactly as the old code would have computed them. When two contract tests cannot both pass, the tests are wrong, not the rule — the test author owns the fixture fix.

13. **Seed legacy-era rows through the entry point that matches the era** — the validating API rejects the legacy shape you are trying to create, and the legacy-tolerant entry point creates a different era's row. Probe which entry point accepts the legacy shape; when the data predates validation entirely, bypass both and INSERT the raw row, exactly as the pre-validation era would have. Check sibling test files for the canonical seeding pattern before inventing one.

14. **Probe the CLI's real output contract before writing subprocess red tests** — run the exact command once and observe: exit code, stdout vs stderr split (error JSON may go to stderr on non-zero exit), and argparse pre-exit behavior for the flags under test. A red test that parses only stdout reads an empty error dict and asserts against nothing — it fails for the wrong reason. Also: check shared test helpers' real return shapes before assuming a parsed dict.

14b. **Ambient-credential tests must never exercise the production key path** — a test asserting a no-credential refusal branch passes THROUGH the configured machine's real key on any environment where the credential is legitimately set. Fix: run the subprocess with a copied env with the credential variables removed, point the config at a guaranteed-unset variable name AND pop that name from the copied env, and assert the strict refusal message — never a weak disjunction.

## Module design residue

16. **Two module customization types only** — data-and-logic-for-a-jurisdiction modules, and industry-vertical modules; everything else is core. Do not invent a third type. Jurisdiction-specific subclasses live inside the data modules, registered through their own mechanism.

17. **Modules self-register; enums by name, not magic codes** — routes register themselves through the module manifest rather than a central registry constant that every module must edit. Use account/enum TYPE names (not hardcoded codes) so templates compose with any chart of accounts.
