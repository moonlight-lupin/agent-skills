# Production-reachability review — the dead-feature cluster

The most expensive review finding class in a multi-batch feature build: every
module's tests green, suite 2400+ passing, and the feature **unreachable in
production** because the public functions a spec AC depends on have zero
non-test callers.

## The rule

After a batch's tests go green, grep for PRODUCTION callers of every public
function the spec's acceptance criteria depend on:

```bash
grep -rn "<function_name>" --include="*.py" shared/ skills/ \
  | grep -v test | grep -v "def <function_name>"
```

Every hit must be a real dispatch site — a CLI verb handler, a hook
registration tuple, a scheduler prompt, or another live caller. A hit inside
another dead function does not count (dead calling dead is still dead). A
function whose callers are only its own test file certifies nothing about
production.

## The four shapes this cluster takes (all observed in one review round)

1. **Zero-caller functions.** `bind_action` / `skip_step` / `fire_occurrence`
   existed with full test coverage and no CLI verb, no hook invocation, no
   scheduler wiring. Entire user stories (approval binding, skip marking,
   occurrence firing) were unreachable outside tests. Fix shape: wire the
   caller (add the CLI verb, register the hook, name the function in the
   scheduler prompt) — or cut the AC from the spec explicitly.

2. **Test-only enrichment kwargs.** A hook whose documented production
   signature is `(tool_name, args, result, context)` but whose implementation
   requires `exit_code=` / `config=` kwargs that the runtime never passes.
   Tests hand-pass both, so 36 tests certify a path production never reaches
   (`exit_code=None` → signal never fires). The tell: **a test passes by
   hand-passing a kwarg the documented signature does not contain.** Fix:
   derive the value from what the runtime actually passes (`result` carries
   the exit status), and drive at least one test per signal through the
   documented four-argument signature with no enrichment kwargs.

3. **Gate key with no runtime precedent.** The whole injection gate hung on
   `context["session_id"]` — a key no other hook in the repo reads. If the
   runtime never populates it, the feature returns None always and is inert
   on a live install while every test passes. Rule: before merging a gate on
   a runtime context key, grep the repo for precedent of that key being
   supplied; no precedent → the spec's manual smoke run on a live install is
   a MERGE BLOCKER, not a nice-to-have.

4. **Missing producer.** A verdict computation reads a store nothing writes
   (`workflow_facts`) — so the happy verdict (GO) is unreachable and the
   function degrades unconditionally. The missing PRODUCER is its own
   finding; do not fold it into the consumer's degradation behavior.

## Why tests cannot catch this

RED→GREEN tests import the module and call the functions directly. That is the
contract style working as designed — it pins behavior, not wiring. Wiring is a
separate batch, and the wiring batch's own tests can repeat the mistake (call
the handler directly instead of through the documented dispatch). The only
checks that close this are (a) the grep pass above, run by the orchestrator
per batch, and (b) the spec's manual smoke run on a live install.

## Where to put the check

- Per-batch verification (orchestrator, after tests pass): one grep pass over
  the batch's public functions, results in the batch report.
- Reviewer brief: add "reachability" as a named review priority AFTER
  guardrail invariants — reviewers find this class reliably when told to look;
  they do not stumble into it.
- Pre-merge gate: the smoke run exercises the LIVE entry point (CLI verb or
  hook dispatch), not the function directly.

Observed cost of skipping it: five user stories across four batches passed
their tests and could not execute in production; the review returned BLOCK on
two files and ~15 MUST-FIX items, most in the reachability cluster.

## Moved from SKILL.md pitfalls (2026-10-16 refactor)

45. **A feature wired into the documented path can be dead in production — trace the LIVE scheduler's actual entry point** — before reporting a feature as shipped, verify the production invocation chain actually reaches the code path the feature hooks. Read the live scheduler definition (cron jobs.json `prompt` field or external-worker config): the real daily briefing may invoke a skill whose prompt drives the agent to compose output via ad-hoc runner scripts and its own tool calls, never calling the programmatic CLI command the feature hooks. Tests pass because tests call the path directly; production never does. When the live path differs from the documented one, the fix is updating the skill prompt/runner — not more code — and the brief must name which path is live. Cross-check by reading the scheduler session's message history in the Hermes session DB (its tool calls show exactly what ran). Validated Sep 2026 on a trends feature (reviewer finding + cron session trace).
