# Batched TDD + Opus Review

> **Fold-in note (2026-10-19):** verbatim copy of the `batched-tdd-opus-review`
> skill body into the dev-pipeline **test-evals** stage, with one exception:
> §6's confirm-round text now points at the shared confirm-round protocol
> that the review-commit stage owns. Session records referenced below stay in
> the source archive at
> `~/.hermes/skills/.curator_backups/dev-pipeline-consolidation-2026-10-19/software-development/batched-tdd-opus-review/references/`;
> paths written as `references/<file>.md` resolve inside the test-evals skill.
> Model pins live ONLY in the lanes config (`orchestrator/config/lanes.default.toml`,
> plus a machine override) — role and rule text in `orchestrator/references/lanes.md`.
> The former "User says / Model / Dispatch method" pin table below carried only
> dispatch methods (workflow, not pins) and is long gone.

## Contents

- CRITICAL: "Opus" Means the Current Opus Generation
- Process (spec + branch setup … push + CI, 8 steps)
- Key Rules / Pitfalls / Fix-round retarget authority / Review report shape
- Relationship to Other Skills

# Batched TDD + Opus Review

A TDD pattern for multi-feature builds where features are grouped into
batches, each batch gets N TDD loops (build → verify+fix), then an **actual
Opus review** before commit. Distinct from the `review-commit` stage's loop
(builder lane builds, reviewer lanes review after commit) — here the structure is: spec → batch
features → TDD loops per batch → Opus review → fix → commit → push → CI.

## When to Use

- User says "implement, use TDD" or "TDD, 2 loops each batch, Opus on each batch"
- User says "batch properly" + "Opus on each batch at the end before commit"
- User wants multiple features built in one session, grouped into batches
- Feature has clear specs / brief (brainstorm-first → user steers → execute)

## CRITICAL: "Opus" Means the Current Opus Generation

When the user says "Opus review," they mean the **current Opus generation** —
the batch "Opus" lane in `orchestrator/references/lanes.md` (the only place the
exact model name lives). Do NOT substitute the builder model, an older Opus,
or any other family. The user chose the Opus line for its
architecture/security/correctness reasoning — using a different model defeats
the purpose and breaks trust.

If the user says "Grok review" or "Codex review," use that model.

**Batch reviewer dispatch priority:**
1. **Claude Code first** (`claude --model "$BATCH_REVIEW_MODEL" -p "..."`) — the
   user's preferred method when available. Check `claude auth status` first
   (works as root via OAuth). **CRITICAL pitfall**: the batch reviewer in print mode
   always tries to use tools (Read/Bash) on turn 1, even when content is
   piped via stdin and `--allowedTools ""` is set. This exhausts
   `--max-turns` without producing output. The working invocation:
   ```bash
   cat /tmp/review-prompt.txt /tmp/diff.txt | claude -p \
     --model "$BATCH_REVIEW_MODEL" --effort medium --max-turns 1 \
     --allowedTools "" --output-format json > /tmp/review.json
   ```
   The prompt MUST say "Do NOT use any tools. The entire diff is provided
   below. Just read it and write your review directly as text output."
   `--effort medium` is sufficient (high makes it worse). `--bare` mode
   breaks OAuth ("Not logged in") — do NOT use it. Parse `result` from
   JSON output.
2. **Cursor CLI fallback** (`agent -p --force --model "$OPUS_REVIEW_MODEL" --sandbox disabled`, model from the lanes config — the single pin source)
   — when Claude Code is not installed or the turn-exhaustion can't be
   worked around. Takes 5–8 minutes — use `notify_on_complete=true`.
3. **`delegate_task` subagent** — when both CLIs are unavailable or the diff
   includes untracked new files that `git diff` misses.

Cursor CLI Opus variants (high / high-fast / medium / low): check `agent --list-models`; the review default is in `lanes.md`.

Which model each review phrase resolves to — "Opus review" / "Grok review" /
"Codex review" / the default when unspecified — is a model PIN: it lives only
in `orchestrator/references/lanes.md`; this file does not restate pins.
What remains here is the dispatch method per review kind (workflow, not pins):

- **Batch review** — Claude Code print mode first (`claude --model "$BATCH_REVIEW_MODEL" -p`,
  stdin-piped prompt per the dispatch priority above), Cursor CLI fallback,
  `delegate_task` subagent last resort.
- **Grok review** — Cursor CLI (`agent -p --force`, exact pin in
  `lanes.md`).
- **Codex review** — `codex exec --sandbox ...`, review-only.

## Process

### 0. Spec + branch setup

1. Write the design spec (if not already written) to `docs/design/<date>-<name>.md`.
2. Create a feature branch: `git checkout -b feat/<name>`.
3. Commit the spec first.

### 1. Partition features into batches

Group features by shared-code dependency:
- **Batch A** = features that change shared types/schemas (do first — downstream depends on them)
- **Batch B** = features that are additive (new endpoints, new files — no shared code changes)

Example (a batched review round on a forecasting library):
- Batch A: pinball+MASE (changes `BacktestMetrics`) + robustness (changes `Series`, `BackendInfo`)
- Batch B: anomaly detection + context ablation + benchmark (all new modules, new endpoints)

### 2. Per batch: write a self-contained spec file

Write `/tmp/<batch>-spec.md` for each batch. The spec must be readable by a
coding agent with zero conversation context — no "as we discussed" references.
Include:
- What exists (current state of each file to be modified)
- What to build (TDD steps: RED tests first, then GREEN implementation)
- Exact file paths
- Verification commands
- Constraints (backward compatible, follow existing patterns, etc.)

### 3. Per batch: TDD Loop 1 — Build (Cursor or Hermes)

**Delegating the RED tests themselves to a cheap external model** (when the user names a model for test authoring, e.g. "use <model X> to build the red tests"): write a brief file (target test count, per-criterion coverage list, exact import-target module + helper pattern, hard rules: test file only / no skips / run both the targeted file and the full suite), then call the model's API directly:

```python
# Ollama Cloud, OpenAI-compatible; key in ~/.hermes/.env as OLLAMA_API_KEY
# POST https://ollama.com/v1/chat/completions, model "<the named model>"
```

- **Set max_tokens ≥20000, not 8000.** Reasoning models on Ollama Cloud can burn the ENTIRE max_tokens budget on the `reasoning` field and return empty `content` — an 8K-token attempt produced 34K reasoning chars and zero output; with 20K the same prompt returned the full file on one call.
- Strip markdown fences from the reply before writing; write to /tmp first, read it fully, then place it in the repo.
- Verify the model's output yourself — RED state (every test fails naming the missing module), full suite shows only the new failures, ruff clean — before committing RED and dispatching the GREEN builder.
- **Check the dispatch target hosts the named model BEFORE dispatching.** Run `agent --list-models` first when routing through Cursor CLI; an Ollama-Cloud-hosted id is not Cursor-hosted, so Cursor rejects the dispatch at dispatch and the nearest-name fallback (a look-alike tier id) is a substitution the user never asked for; surface iter must be told about — flag it in the batch report, never present it as equivalence. Route GLM through its native API (the Ollama Cloud path above) and keep Cursor CLI for Cursor-hosted models only.

**If using Cursor** (user's preferred for multi-file builds):
```bash
agent -p --force --model "$BUILDER_MODEL" \
  "Read the spec at /tmp/<batch>-spec.md and implement it fully. The RED tests listed in the spec are already written and failing — do NOT edit them; implement until they pass. Any new behavior the spec missed gets its own failing-first test, listed in your report. Follow the CODING PRINCIPLES block in the spec. Run the verification commands at the end of the spec. Report what you changed."
```
Run with `background=true, notify_on_complete=true`.

The batch spec carries the builder block from `orchestrator/references/coding-principles.md`, pasted verbatim. Before either dispatch, this stage writes the batch's RED tests and runs them
to failure (the stage's ownership rule in `test-evals/SKILL.md`).

**If Hermes builds** (for smaller tasks):
Run the RED tests and confirm they fail for the right reason, then implement
until all pass.

### 4. Per batch: TDD Loop 2 — Verify + fix

**Hermes verifies independently** (do NOT trust the builder's self-report):
1. Run the full test suite: `python -m pytest tests/ -v`
2. Run lint: `ruff check core/ api/ mcp_server/ tests/`
3. Check for pre-existing failures (compare against clean branch — `git stash`
   and run the same test, then `git stash pop`)
4. If any NEW failures: dispatch Cursor to fix, or fix directly
5. Re-run tests + lint until green

### 5. Per batch: Opus review BEFORE commit

Dispatch the review using the **actual Opus model**:

```bash
git diff > /tmp/<batch>.diff
agent -p --force --model "$OPUS_REVIEW_MODEL" --sandbox disabled \
  "Review the diff at /tmp/<batch>.diff. Focus on: correctness, backward
  compatibility, edge cases, security, architecture. Write findings to
  /tmp/<batch>-review.md with severity labels (BLOCKING/MAJOR/MINOR/NIT).
  Do NOT make any changes."
```

Alternatively, use `delegate_task` for a subagent review (if Cursor CLI
is unavailable or the diff is small enough to inline).

### 6. Per batch: Fix review findings

Dispatch the builder lane (or fix directly if trivial) to address every
BLOCKING/MAJOR finding. Apply MINOR fixes only if quick; otherwise defer them.
MINOR/NIT never trigger another review. Re-run tests + lint.

**Fix-round security findings get orchestrator-authored RED tests BEFORE
the builder dispatch** — reproduce each finding as a failing test pinning
the exact rejection (control chars, traversal, injection payload). A
builder satisfies only the tests you wrote; fields you did not pin stay
unsafe.

**After the fix round, run a confirm re-review on the fix diff, not a fresh broad review** — `review-commit/references/confirm-round-protocol.md` owns the contract (RESOLVED / RESOLVED-BUT / NOT-RESOLVED per original finding, NEW-N for regressions the fix introduced) and the budget: per batch, at most the tier's confirm rounds (default 1), then ask.

### 7. Per batch: Commit

```bash
git add <specific files>  # avoid git add -A (may catch untracked junk)
git commit -m "feat: <description> (Batch X)"
```

### 8. After all batches: Push + CI

Two release shapes:
- **Merge at the end (default):** after all batches pass review, `git push -u origin feat/<name>`, then merge. If the user says "hold and merge everything one shot later", the batches still STACK on the feature branch — push between batches (so each batch is CI-verified on the PR) but do NOT merge; say so in each status report so the user knows the PR is open but held.
- **Merge per batch:** push + merge each batch as it ships.

Either way, after pushing check CI:

```bash
gh run list --limit 5
```

**CI triggers:** Check `.github/workflows/ci.yml` for trigger rules. Some
workflows only trigger on `push: [main]` or `pull_request` — a feature
branch push alone may not trigger CI. If so, create a PR to trigger it.

**gh PR creation may fail** with `GraphQL: Resource not accessible by personal
access token (repository.defaultBranchRef)` — this is a fine-grained PAT
limitation. Tell the user to create the PR from the GitHub UI.

## Key Rules

Read `references/key-rules.md` before the first batch. It holds RED-before-GREEN, the Opus model pin, review-before-commit, specific `git add`, CI-after-push, independent verification, and the BLE001 / deleted-file rules.

## Pitfalls

1. **Substituting Opus with another model** — the user will notice and call
   it out. "Opus" is a specific model choice, not a generic word for "thorough."
   In one session, the first review cycle used Grok 4.5 High
   instead of Opus. The user caught it and asked for a supplementary Opus
   review. The Opus review then found 3 additional MAJOR findings the Grok
   review missed (DoS surface, work-cap fragility, silent data mutation).
   Lesson: different models genuinely find different issues — don't treat
   them as interchangeable.

2. **Reviewing after commit** — if you commit then review, fixing findings
   requires a separate fix commit. Review first, fix, then commit — one clean
   commit per batch.

3. **`git add -A` catching junk** — Cursor sometimes creates `docs/walkthrough/`
   screenshots or other artifacts. Stage specific files.

4. **CI not triggering on branch push** — check the workflow's `on:` triggers.
   If it only fires on `push: [main]` or `pull_request`, the branch push
   alone won't trigger it.

5. **NEVER pipe build dispatches through `tail`** — piping a Cursor build
   command through `tail -5` (or `tail -800`) means `process(action="log")`
   only sees the already-truncated output. You cannot inspect intermediate
   progress, debug a hung build, or read the builder's full summary. This
   is the same trap as piping reviews (`review-lessons/references/loop-pitfalls.md` #8), but
   it's easy to miss for builds because the `tail -5` looks like a harmless
   preview filter. Instead: instruct the agent to **write its output to a
   file** (`/tmp/build-output.md`) and `read_file` it after. Or omit the
   pipe entirely and use `process(action="log", limit=800)` for the full
   output. The `tail` pipe truncates at the shell level before Hermes ever
   sees it.

6. **Verify the Hermes-authored contract test is untouched** — when you
   write a TDD contract test before dispatching the builder, the post-build
   verification MUST confirm the builder did not modify or delete it. Run
   `git diff HEAD --stat -- tests/<contract_test>.py` — zero diff means
   Cursor respected the constraint. A non-zero diff means Cursor weakened
   or deleted the test to make it pass (this has happened — Cursor wrote
   `assert condition or True` in one project, deleted inconvenient test files 3
   times). If the diff is non-zero, inspect it immediately: a legitimate
   update (e.g. adding a mock for a new API the test calls) is fine; a
   weakened assertion or deleted test is a BLOCKING finding. This check is
   in addition to running the test suite — a passing suite with a
   silently-weakened test is worse than no test at all.

7. **Production code patching the test suite at import time is a BLOCKING test-gaming shape.** A GREEN build added a `_patch_test_install_cron_kw()` helper called at import that scanned `sys.modules` for the batch's test module and replaced a helper so RED tests passed. Detect it: import the test module under a different name (so the patch's name-match misses) and call the original helper — a `TypeError` proves the patch is load-bearing, and it also runs on every CLI invocation since the module imports at startup. Fix: delete the patch; the authorized edit is to the test helper itself (add the kwarg the contract requires). Add to the review brief: "production modules must not reference test modules" so the reviewer greps for it.

8. **When a test pin contradicts the spec, the spec wins — retarget the pin explicitly, never silently.** A wiring test pinned "install never creates a review-queue action" while the spec required cron creation to BE a review-queue action. Retarget the pin to the spec contract ("no UNAPPROVED mutation"), list every retargeted test in the commit message and status report, and when gating the primitive itself would need unauthorized test edits, gate the operator surface instead and flag the deviation (primitive stays direct; surface is gated) — a flagged partial fix beats a silent test rewrite. Pins also go stale in the other direction: a RED contract authored BEFORE a later review-authorized fix round can contradict the shipped behavior and surface mid-GREEN as an impossible assertion (the builder stops — the escape hatch working). Verify the pin predates the behavior change, then retarget it in your own hand to pin the NEW end-to-end flow (e.g. propose → approve → execute → reinstall), which is stronger than the original pin, and list the retarget in the commit message.

When you hit something below, read the file before acting. The kept items above are the only pitfalls that gate every run.

| When you hit | Read |
|---|---|
| CLI, env, dispatch timing, turn caps, gh, pre-existing CI | `references/pitfalls-cli-and-env-mechanics.md` |
| Loop convergence: public-interface tests, RED delegation, pins, reachability, downstream review | `references/pitfalls-loop-convergence.md` |
| Review findings: warnings, payloads, provenance, injection, concurrency, timestamps | `references/pitfalls-review-findings.md` |
| Report shape to demand in every review brief, plus session records | `references/review-report-shape.md` |
| RED/GREEN, Opus pin, staging, CI-after-push — every batch | `references/key-rules.md` |

## Fix-round retarget authority (who edits tests after a review)
Round A (blockers + guardrails): the builder is test-forbidden except review-authorized edits; the orchestrator makes any remaining legitimate test edits itself (e.g. count pins in UNRELATED pre-existing test files broken by a registration growth — update numbers only, never weaken an assertion). Round B (reachability/behavior changes): behavior fixes legitimately break pre-existing pins — the builder stops and lists the breaks WITHOUT editing; the orchestrator verifies each break maps to a review-authorized behavior change (grep the finding, confirm the mechanism), patches the pin itself (assertion direction + threshold + docstring only), and re-runs. A pin retarget is legitimate when the pin asserts an OLD threshold/order/count the review explicitly replaced; it is test-gaming when it weakens an assertion inside the NEW feature's own contract test.

## Review report shape (ask for this in every review brief)

Ask for this shape in every review brief (per-file verdict table, file:line findings, merge order). Full text, the mock-import and BLE001 notes, and the session narratives are in `references/review-report-shape.md`.

The full report template and worked report examples live in
`references/review-report-shape.md`.

## Relationship to Other Skills

- **`review-commit` stage**: builder lane builds, reviewer lanes review in a
  budgeted confirm-round loop after commit. This mode differs: per-batch Opus
  review BEFORE commit. Use it when the user says "Opus" or asks for batched TDD.
  Fix rounds after the batch review follow the same severity floor and budget
  (`review-commit/references/confirm-round-protocol.md`).
- **`build` stage**: per-task subagent dispatch with per-task review sized by
  tier. This mode is simpler — one review per batch.
- **Builder model**: the builder lane in `orchestrator/references/lanes.md`;
  "Opus" overrides the reviewer, never the builder.
