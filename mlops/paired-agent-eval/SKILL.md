---
name: paired-agent-eval
description: "Use when running paired agent A/B quality pilots."
license: MIT
metadata:
  version: 1.4.0
  author: moonlight-lupin
  platforms: [linux, macos, windows]
  hermes:
    tags: [evaluation, benchmark, dev-pipeline, ab-testing]
    related_skills: [agent-skills-repo-maintenance, model-compare]
---

# Paired Agent Evaluation

## Overview

Answers "does tiered pipeline processing justify its cost" with matched task
pairs: a single-agent baseline arm versus a pipeline arm (tier flow per the
dev-pipeline size-tiers), on identical pinned trees with identical up-front
acceptance suites. Cost side (elapsed, tokens, review rounds) is measured
directly; quality side comes from the acceptance suite plus a blinded,
severity-weighted defect scorer. Analyzer:
`plugins/dev-pipeline/benchmarks/compare_runs.py` in the agent-skills mirror
(schema: task_id, variant baseline/pipeline, tier T0-T3, elapsed_s, tokens,
success, regressions, review_rounds).

## When to Use

Load this skill when the user asks whether the dev-pipeline (or any staged
agent workflow) is worth its cost — "run an A/B pilot", "empirically test
whether T2/T3 justify their overhead", "evaluate the pipeline against a
baseline" — or when asked to analyze results produced by
`plugins/dev-pipeline/benchmarks/compare_runs.py`. Do not use for single-side
PR review (see agent-skills-repo-maintenance).

## Procedure

1. **Package the pair before any arm runs.** Starter repo, full-contract
   TASK.md (exit codes, JSON shapes, every rule an arm can violate), and
   `acceptance/test_acceptance.py` — one file, copied identically into both
   arm repos. `git init` + one pinned start commit per arm; cross-check the
   pin shas are equal.
2. **Audit the acceptance suite against the stub tree before pinning.** Run
   the tests' logic against the starter and confirm each expectation is
   actually implementable per the TASK.md wording (slug rules, search terms,
   JSON shapes). A flawed acceptance rule forces a wrong implementation and
   voids the pair; this check has caught instrument bugs twice (a
   `#guide-` slug that no GitHub-slugging impl could satisfy; a test writing
   `r.md` while asserting `report.md`). Two structural rules from those hits:
   - Tests that chdir the CLI into a tmp dir MUST resolve the script by
     absolute `REPO` path — a relative `python3 shelf.py` cannot resolve from
     tmp cwd and forces every arm to shim the environment.
   - Never let a convoluted conditional assertion ("A and B if C else True")
     through an audit — rewrite it plainly.
   Also diff both arm repos against the starter file set BEFORE trusting any
   suite result: one implementer added an undisclosed `conftest.py` that
   symlinked the CLI into every tmp dir and even alias-fixed a broken
   assertion per test name instead of disclosing the harness bug. If a
   genuine instrument bug surfaces mid-run: fix the suite, push it as an
   explicit harness-owned commit (`instrument: ...`) into BOTH repos, archive
   the shim, re-verify both arms, and log the deviation in PROTOCOL.
3. **Fix one coder model for BOTH arms.** The experiment measures PROCESS, not
   model. Baseline = a single codex exec given TASK.md + suite, work
   autonomously, commit, print FINAL_STATUS. Pipeline arm = the tier's flow.
4. **Tier flow menu (from the dev-pipeline size-tiers doc):**
   - T1: no grill/spec turn (acceptance criteria inline in the plan), one
     implementer batch, NO per-task review, Step A by the orchestrator, Step B
     one lane, confirm budget 1.
   - T2: grill decisions recorded + spec, ~3 implementer batches, ONE combined
     reviewer per batch (spec verdict then quality verdict), converge cap 2,
     Step B two cross-model lanes, confirm budget 2.
   - T3: grill mandatory, two SEPARATE per-task reviewers (spec compliance,
     then quality only after spec PASS), converge cap 3, Step B three lanes,
     confirm budget 3.
   Fold each review's findings into the NEXT implementer dispatch rather than
   a separate fix round when budget is tight; say so in the dispatch.
5. **Confirm reviews reproduce, never read.** Instruct confirm reviewers to
   build probe trees in a temp dir and reproduce every claimed fix; then the
   orchestrator reproduces the decisive ones itself anyway (scaling probes for
   performance findings: double the input twice and expect ~4x/~2x to detect
   quadratic vs linear). "fixed (static-only, not reproduced)" is an
   UNVERIFIED state, not a pass.
6. **Blinded scoring** (codex gpt-6-sol high): stage anonymized copies under
   neutral paths (`arm_one/`, `arm_two/`) each with TASK.md + tests copies;
   the scorer brief must forbid reading anything else on the machine (git
   history, logs, metadata) and apply one rubric (Critical=3, Important=2,
   Minor=1). Write the `BLINDING.txt` map (arm -> origin), chmod 600, and open
   it only after the score lands.
7. **Metrics without invented values.** Elapsed = mtime(brief) − mtime(log)
   (agent CLI logs carry no timestamps). Tokens: ONLY codex exec reports a
   `tokens used` line; claude -p and muse exec do not — pipeline token totals
   are coder-only undercounts, always say so. Where a schema field is
   unmeasured, log the convention in PROTOCOL notes (e.g. combined total in
   input_tokens, output_tokens 0 = not separately measured) — never present a
   placeholder as a measurement.
8. **Report with the standing caveat:** one pair gives direction, not proof;
   state deviations from protocol (run order, blinding order, unmeasured
   spend) in the same breath as the result.

## Behavioral / skill-text variant A/B

When the deliverable under test is TEXT that steers behavior (a SKILL.md
revision, a system-prompt change), keep the paired logic but inject text
instead of switching workflows:

1. **Build variants by copying the installed skill file, then VERIFY the copy by whole-file diff.** Arms must differ
   only in the injected text. A hand-typed baseline silently drops sections
   and the A/B then grades text nobody will ship — check the version-bump diff-stat before running: an
   unexplained large deletion (e.g. −40 lines on a +10/−5 bump) is dropped content, not edit churn.
2. **Injection surfaces:** CLI subject — `claude -p --model <subject>
   --append-system-prompt "$(cat variant.txt)" "$(cat task.txt)"`, one
   terminal call per arm, outputs to files. Subagent subject (weak/cheap
   tier) — inline the full variant text in task context with "follow this as
   operating behavior; never mention it in the reply". Grant real tools when
   the skill governs tool use, and require named-tool provenance (which
   tools, read-depth per source); a subject that narrates a search it never
   made is a finding, not noise.
3. **Rubric per test: 3-5 lines, 0-4 each.** Every line targets either a NEW
   rule (so the delta can score) or a regression risk (so harm is visible).
   If no line can distinguish the variants, redesign the test before running.
4. **Blind judging:** unseeded-shuffle all arms into P-labels; the judge sees
   only label + group + text, and must be a DIFFERENT model family from the
   subject. Before accepting, verify the judge's decisive claims (counts,
   quotes, labels) against the raw texts — judges misread like any reader.
5. **Subject-tier rule:** ties on a strong subject do NOT mean the variant
   adds nothing. Strong baselines already score at rubric ceiling; behavioral
   deltas surface on the weaker runner tier the skill is meant for. Re-run
   the battery there before concluding — a 3-tie strong-subject result plus
   wins on the weak tier is the normal shipping pattern.
6. **Multi-arm batteries.** When the question is whether a skill earns its
   keep at all, run three arms: a no-skill baseline (plain system line only,
   same neutral text for every arm), the old version, and the candidate —
   identical harness, fixtures, and task text; the arms differ ONLY in the
   injected text. Two skill arms score the delta; the baseline arm scores
   whether any version beats nothing.
7. **Real tool-harness subjects and trace metrics.** For skills that govern
   tool use, drive the subject through a real tool loop (API tool-calling
   with jailed workspace tools) and log the full transcript per run. Score
   deterministic tests from the trace: per-turn tool-call counts (the
   parallelism metric), missing-file honesty, exact diffs of requested
   edits, deliverable-within-budget. Verify the subject's provenance claims
   against the MODEL-VISIBLE payload — a model labels read-depth against the
   truncated tool output it received, so a "snippet-only" label of a page
   the tool internally fetched at 40k chars can be honest; compare claims to
   what the model saw, not the tool's internal size, before calling it a
   mislabel. Reserve blind judging for the subjective deliverables.
8. **Turn budget is part of the instrument.** Set a max-turn cap per run and
   log deliverable-within-budget as a first-class metric: a subject that
   emits tool calls every turn and never closes with final text scores
   0/20-style on the deliverable rubric. Cheap models with autonomy-adjacent
   prompts are the main runaway-loop risk.

## Pitfalls

- **Scorer noise is real — repro every headline finding before accepting a
  blinded verdict.** Round-2 examples: the scorer counted a behavior
  IMPROVEMENT over the starter as a defect (header-only CSV exit matched the
  pinned starter's old behavior), while its short-row-crash finding was
  genuine. One repro each settles it.
- **Blind-order discipline**: randomize the arm→slot mapping with an unseeded
  shuffle (round 1 used a fixed order and only noticed when the map was
  written); write the sealed map BEFORE any scorer prompt exists, chmod 600.
- **A fix that closes one hole can open another — new findings stay in the
  measurement.** A malformed-quote guard that re-parses per line broke valid
  RFC 4180 multi-line fields. When the tier's confirm budget is spent, do NOT
  polish past it: leave the regression in the artifact, record it as an
  adjudication line, and let the blind scorer weigh it — honest loss beats
  post-hoc polish. Escalate/split only the load-bearing case.
- **Never gate a later shell step on a piped check.** In
  `pytest -q | tail -2 && git commit`, `$?` is `tail`'s and a RED suite commits
  cleanly. Write the deciding command's output to a file or run it unpiped;
  same for `git pull --ff-only` piped through `tail -1` (silently failing
  state changes).
- **Confirm the clone's branch label before interpreting any tree state.** The
  working clone may still sit on a leftover PR branch from earlier work; `git
  log` and `ls` then describe a tree that is not what you think you are
  reviewing. `git branch --show-current` + `git rev-parse HEAD origin/main`
  before comparisons.
- **Finiteness validation needs type discipline.** `math.isfinite(huge_int)`
  raises OverflowError, so float-only guards (`isinstance(val, float) and not
  math.isfinite(val)`) plus an explicit magnitude cap below 2**53, and gate
  the report at the serialization boundary (`json.dumps(..., allow_nan=False)`).
- **A Step-B APPROVE does not mean the artifact is clean.** In the T1 round the single lightweight lane APPROVED with 0 Important while the blind scorer found a short-row crash (exit 1 traceback) in the same file. Lightweight review adds confidence, not coverage; weight tier verdicts accordingly.
- **Background implementers race their own notification.** A fixer may print its log tail before the git commit lands; a `git log` check taken immediately can miss the commit (and `git status` can show phantom modified files mid-close). Re-run `git log --oneline -1` and `git status --short` immediately before probing the tree or committing anything yourself.
- **Untrack stray bytecode before scoring.** Implementers and harness commits have added `tests/__pycache__/*.pyc` to diffs; `git rm --cached` + `.gitignore` (harness-owned hygiene commit) so the scored diff shows only real work.
- **Codex-authored branches may open as draft PRs** — `gh pr ready N` before
  `gh pr merge`, which otherwise fails with "still a draft".
- **Self-test the harness's retrieval tools before the battery.** Run one
  real query through every tool the subjects will see; a broken scraper
  returns a tiny error payload that reads as success in the transcript, and
  every research arm then flails on junk (or fabricates around it) for the
  whole run.
- **Eval-report claims about the harness must match harness code
  byte-for-byte** — trace format (JSON vs JSONL), turn caps,
  isolation/restriction claims, and environment variables. Reviewers check
  doc claims against the code, and any drift costs a fix round; update the
  docstring and the report in the same edit so they cannot drift.
- **Keyless search from a datacenter host is a minefield — pick the pool,
  then disclose it.** Popular HTML endpoints bot-gate or anomaly-gate server
  IPs, and legacy RSS endpoints can serve location-poisoned results for the
  local IP. Working keyless set: Wikipedia API + Hacker News Algolia. Put
  the source pool in the tool description so the subject knows its universe
  — pool bias hits every arm equally and stays comparable.
- **When a turn cap truncates an arm, re-run ALL arms at the raised cap.**
  Granting only the failed arm more budget breaks cost symmetry. Truncation
  that persists across two raised caps is a real behavioral finding (failure
  to close a turn), not instrument failure — record it, never re-budget
  cherry-arm.
- **Probe the model slug with one real call before building the harness.**
  Free-tier slugs can refuse raw API calls entirely (agentic-app-only
  gating); the same family's paid sibling usually accepts them. Confirm the
  fallback with the user before spending their key — and never spoof the
  gating headers to get past a provider restriction.
- **Run arm-orchestration steps as tracked background processes with logs at
  absolute paths**, drive the sequence from completion notifications, and keep
  live state in the scratchpad — a 6+ step pipeline spans many turns.
- **Shared helpers must live in the script that the background process
  runs.** A helper defined in a foreground kernel session does not exist in
  a later background interpreter — the first reference dies with
  AttributeError mid-battery.

## Honest limits

One pair per tier measures the cost side precisely and the quality side only
anecdotally. Say so every time. Scale to 3-5 pairs per tier before drawing a
tier-level conclusion, and re-audit the instrument when tasks change class
(security-surface tasks need a security-focused scorer brief, not the general
rubric).