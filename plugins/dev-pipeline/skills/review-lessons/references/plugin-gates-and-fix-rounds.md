# Plugin Gates and Fix Rounds

Standing rules for the build→review→fix→live cycle on Hermes plugins. A companion to `build-review-loop` (round mechanics) and `hermes-plugin-development` (packaging). This file carries the gate policy and the fix-round contracts proven against real adversarial reviewers.

## Ship gates (all required, in order)

1. Orchestrator verifies independently: full suite green in a writable environment, contract files byte-unchanged (`git diff` against the baseline commit), `py_compile` + YAML parse sweep, and a hand-run of every reproduced finding.
2. Reviewer A confirm review (Codex, model and effort flag from the lanes config (`orchestrator/config/lanes.default.toml` + a machine override), `--sandbox workspace-write`): scoped to the fix diff, every original finding itemized RESOLVED/NOT-RESOLVED with file:line evidence, plus a differential hunt with reviewer-constructed inputs.
3. Full-plugin gate BEFORE live install: the three-reviewer gate (reviewer lanes A + B + C per the roles in the lanes config; Muse judges from a pre-generated diff, timeout 1500), run once on the net diff after the fix loop converges (`review-commit/references/confirm-round-protocol.md`). All verdicts required at SHIP before the local install.
4. No catalog submission until a live trial (~1 week, trial period noted in the design spec) passes review. The catalog PR is the LAST step, never the first.

## Fix-round contracts

- Reproduce a reviewer finding with the reviewer's EXACT input construction before accepting or rejecting it. An approximate analog that runs fast does not exonerate the finding — superlinear behavior hides behind a different token layout of the same idea (one long string vs many short lines both scale, but only one reproduces the quadratic).
- Order performance fixes with the ALGORITHM pinned, not the goal. State the data-flow invariant ('single forward cursor; consumed regions never re-scanned'), add a bounded look-ahead constant when full generality is unneeded (document it as a named CONSTANT), and pin a wall-clock linearity test: 2x input must not exceed 3x time, printed as a table. An instruction like 'make it linear' does not converge — the builder makes each tested shape fast and the next shape stays quadratic.
- Pair every perf fix with a ratio assertion (never a solo absolute-time bound) and generous CI margins to avoid flaky timing failures.
- Verify the premise of your own verification test before calling the code wrong. Compute fixtures (calendar dates, regex groupings) against a tool, not from memory — a wrong premise in the orchestrator's probe reads as a builder regression and can dispatch a pointless fix round.
- When reviewers report 'the pinned contract file was modified', check git history for WHO changed it before blaming the builder: the orchestrator's own between-rounds patch commits alongside the builder's work and looks identical to a violation in a commit-range diff. Record an inline waiver comment in the contract file at the moment you exercise that right.
- Confirm-review prompt shape: scope to the exact fix diff, list every original finding with its expected RESOLVED status, require named regression tests per finding, ask explicitly for reviewer-constructed pathological shapes, and end with a single SHIP | DO-NOT-SHIP line.
- Give reviewers READ access to the Hermes-written contract tests, not just the diff (read-only file access is usually available even when code execution is not): reviewers without test access burn a third of their report on 'cannot assess test quality' and demand tests that already exist; with access they adjudicate the tests directly.
- Park review inputs INSIDE the repo working directory and gitignore them (`*.diff`, `review-*.md`) before referencing: every reviewer's sandbox must be able to read the diff from its cwd (muse cannot read /tmp; opus read-only needs in-cwd files), with reviewer cwd = repo root.
- A reviewer verdict is not evidence — verify before fixing. When a 3-model round splits (DO-NOT-SHIP on broad claims + SHIP), reproduce each MAJOR with the reviewer's exact premise first, dismiss false positives with specific written evidence (file:line of why not), and make the round-2 prompt restate every verdict + dismissal rationale and invite contest only with specific evidence. One such cycle converts a discordant round 1 into a converged round 2 (R1: DO-NOT-SHIP/SHIP-conditional/SHIP → R2: SHIP ×3).
- Convergence criterion: each confirm round must surface strictly fewer or narrower findings. A same-count round means the fix round treated symptoms — re-pin the invariant in the brief instead of looping another fix.
- Reviewer sandbox failures (read-only workspace, no writable temp dir) are environmental: the exoneration criterion is 'zero assertion failures', not 'suite green'. Never weaken tests to pass a sandbox.
- Verify contract-file integrity by CONTENT hash, not the `.attest` git diff: re-running attest rewrites marker metadata, so a committed `.attest` shows `M` after a legitimate re-attest while the sha256 field inside stays identical. `M` on the marker is benign; a changed hash is the violation. Orchestrator test additions to Hermes-owned contract-test files are legitimate mid-loop (extend them RED with the reviewers' named test asks, re-attest, re-commit) — never hand-edit the builder's code in the same pass.
- Build tests use `tempfile.TemporaryDirectory(dir="/root")` where writable; when read-only, redirect to /tmp in-test via env fallback. Report both failure modes distinctly in round results.

## Live install on the gateway host

Install = rsync the repo tree to `~/.hermes/plugins/<name>/` (exclude `.git`, `BRIEF*`, `*.attest`, `__pycache__`, `.pytest_cache`, review artifacts), then activate:
- Never attempt a gateway restart/stop from inside the gateway process — every in-tree path is blocked (systemctl, `hermes gateway restart`, self-SSH command text, even a heredoc containing the restart string): the gate pattern-matches the command, and a real restart's SIGTERM kills this agent's process tree. The sanctioned in-process action is the plugins disable/enable cycle (`hermes plugins disable <name> && hermes plugins enable <name>`), which reports 'Gateway reloaded plugins — active in the running gateway now: hooks'.
- The disable/enable reload re-arms hooks but does not provably re-import the plugin's Python modules (stale `sys.modules` risk). A plugin that changed module-level code needs a real restart from a shell outside the gateway — ask the user to run it. Verify the new code, not a log line: check for a behavioral canary (a log record the old code cannot emit); state pending-restart status explicitly instead of declaring the new code live.
- After activation, run the test suite from the LIVE directory too: the live tree is what the gateway loads, so it, not the repo, must be green.

- Register the install with the CLI, not the file tools: `patch`/`write_file` refuse `~/.hermes/config.yaml` (security guard). `hermes config set plugins.enabled '[a, b, <name>]'` REPLACES the whole enabled list — read the current list first (`hermes config get plugins.enabled` or parse `jobs.json`-style YAML) and never retype it from memory. Add a `plugins.entries.<name>.settings` block at the same time; verify both with `hermes config get` read-back.
- The config schema in `plugin.yaml` (or the gateway's own schema) must declare EVERY setting the code reads: an undeclared key can be silently dropped by strict validation/unknown-key trimming, and a too-narrow type silently rejects valid values (a `ttl_minutes: {type: integer}` schema rejects a float the code guards for; a missing `markers` array property makes that setting dead). After touching any settings key in code, grep the schema file for every key the loader reads — one review round caught BOTH a missing property and a too-narrow type in the same plugin.

## Lifecycle-gate summary (decision table)

| Event | Gate |
|---|---|
| Parser/module fix round | Orchestrator repro + Codex confirm |
| New hook/plugin surface | + loader-fidelity package-exec test must pass |
| Live install | Full three-model gate + `hermes plugins validate` |
| Catalog PR | Live trial (~1 week) verdict + validate green |
| Catalog PR scope | Capabilities mirror manifest exactly; release tag + Release object; public surfaces only |
