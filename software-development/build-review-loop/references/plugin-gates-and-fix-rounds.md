# Plugin Gates and Fix Rounds

Standing rules for the build→review→fix→live cycle on Hermes plugins. A companion to `build-review-loop` (round mechanics) and `hermes-plugin-development` (packaging). This file carries the gate policy and the fix-round contracts proven against real adversarial reviewers.

## Ship gates (all required, in order)

1. Orchestrator verifies independently: full suite green in a writable environment, contract files byte-unchanged (`git diff` against the baseline commit), `py_compile` + YAML parse sweep, and a hand-run of every reproduced finding.
2. Codex confirm review (`codex exec -m gpt-6-sol -c model_reasoning_effort="high" --sandbox workspace-write`): scoped to the fix diff, every original finding itemized RESOLVED/NOT-RESOLVED with file:line evidence, plus a differential hunt with reviewer-constructed inputs.
3. Full-plugin gate BEFORE live install: Claude Code Opus 5.5 via `claude -p --model opus` AND Muse review (`muse exec --trust-workspace --model muse-spark-1.3 --reasoning-effort high --disable-web-tools`, judge from a pre-generated diff, timeout 1500) alongside Codex. All verdicts required at APPROVE before the local install.
4. No catalog submission until a live trial (~1 week, trial period noted in the design spec) passes review. The catalog PR is the LAST step, never the first.

## Fix-round contracts

- Reproduce a reviewer finding with the reviewer's EXACT input construction before accepting or rejecting it. An approximate analog that runs fast does not exonerate the finding — superlinear behavior hides behind a different token layout of the same idea (one long string vs many short lines both scale, but only one reproduces the quadratic).
- Order performance fixes with the ALGORITHM pinned, not the goal. State the data-flow invariant ('single forward cursor; consumed regions never re-scanned'), add a bounded look-ahead constant when full generality is unneeded (document it as a named CONSTANT), and pin a wall-clock linearity test: 2x input must not exceed 3x time, printed as a table. An instruction like 'make it linear' does not converge — the builder makes each tested shape fast and the next shape stays quadratic.
- Pair every perf fix with a ratio assertion (never a solo absolute-time bound) and generous CI margins to avoid flaky timing failures.
- Verify the premise of your own verification test before calling the code wrong. Compute fixtures (calendar dates, regex groupings) against a tool, not from memory — a wrong premise in the orchestrator's probe reads as a builder regression and can dispatch a pointless fix round.
- When reviewers report 'the pinned contract file was modified', check git history for WHO changed it before blaming the builder: the orchestrator's own between-rounds patch commits alongside the builder's work and looks identical to a violation in a commit-range diff. Record an inline waiver comment in the contract file at the moment you exercise that right.
- Confirm-review prompt shape: scope to the exact fix diff, list every original finding with its expected RESOLVED status, require named regression tests per finding, ask explicitly for reviewer-constructed pathological shapes, and end with a single SHIP | DO-NOT-SHIP line.
- Convergence criterion: each confirm round must surface strictly fewer or narrower findings. A same-count round means the fix round treated symptoms — re-pin the invariant in the brief instead of looping another fix.
- Reviewer sandbox failures (read-only workspace, no writable temp dir) are environmental: the exoneration criterion is 'zero assertion failures', not 'suite green'. Never weaken tests to pass a sandbox.
- Build tests use `tempfile.TemporaryDirectory(dir="/root")` where writable; when read-only, redirect to /tmp in-test via env fallback. Report both failure modes distinctly in round results.

## Lifecycle-gate summary (decision table)

| Event | Gate |
|---|---|
| Parser/module fix round | Orchestrator repro + Codex confirm |
| New hook/plugin surface | + loader-fidelity package-exec test must pass |
| Live install | Full three-model gate + `hermes plugins validate` |
| Catalog PR | Live trial (~1 week) verdict + validate green |
| Catalog PR scope | Capabilities mirror manifest exactly; release tag + Release object; public surfaces only |
