# Changelog

## Unreleased — CLI arm runner

- New tool `tools/run_arm.py`: wraps exactly one bounded CLI arm dispatch
  (claude / codex / muse) and writes a machine-readable run record (JSON) plus
  a combined stdout+stderr log, each at its own absolute path. Refuses
  `--dangerously-skip-permissions`, applies role-scoped `--allowedTools`
  whitelists, route-isolates gate claude reviews through a clean config dir
  (settings `env` block removed), auto-adds codex `--skip-git-repo-check`
  outside git repos, and aborts pre-dispatch on a muse meter/quota block
  (zero burn). Exit-code contract: 0 success, 2 bad args/paths, 3 missing
  reviewer `VERDICT:` line, 4 underlying CLI failed, 5 meter/quota abort.
- New unit tests `tests/test_arm_runner.py`: verdict extraction, run-record
  building from a fake log/blob, gate config-dir copy logic, codex flag
  building, and the muse quota-abort path (monkeypatched usage call — no
  live CLI, no network).
- Dispatch guards added to the `build` and `review-commit` SKILL.md
  pitfalls: arm jobs run as Hermes background jobs with notify enabled
  (never `&` in a foreground call), one absolute log path per concurrent
  dispatch, and route isolation for gate claude reviews.

## v0.3.0 — risk-first routing

- Separate **complexity S0–S3** (planning/decomposition) from **risk R0–R3**
  (review depth). `skills/orchestrator/references/risk-routing.md` is the
  authoritative classification and stage-routing reference.
- Preserve T0–T3 as compatibility review-tier names for existing downstream
  stages; the same reviewer lanes, budgets and live-deploy gate remain.
- Untrusted input and filesystem boundaries escalate independent of diff size;
  ordinary large refactors no longer automatically trigger T2/T3 reviews.
- Fix verification guidance: rerun full acceptance tests after every fix and
  never equate an exhausted budget with SHIP.
- Add regression checks for routing, version and safety invariants.
- Align planning-stage gates (spec turns, Goldfish offer, converge loop) with
  complexity bands; review budgets stay risk-derived.
- Plugin version 0.3.0. No hook implementation changes.
- Skill metadata versions stay in their own series: orchestrator 2.1.0,
  spec/build/review-commit 2.1.0, grill 1.1.0 (the routing contract is a
  minor release for each stage; the plugin release is 0.3.0).

## v0.2.3 — coding principles woven in

Adapted from [andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills)
(MIT): think before coding, simplicity first, surgical changes, goal-driven
execution. Woven in, not installed alongside: one home, pointers everywhere else.

- **New single home:** `skills/orchestrator/references/coding-principles.md`.
  It holds the four principles in pipeline terms, the T0/T1 plan format, the
  definition of an unreachable scenario, and the **builder block**.
- **Builder block in every brief.** The builder lane reads only its brief,
  so the implementer template (`build/references/per-task-workflow.md`), the
  fix-brief template, `workflow-steps.md` Step 1, the feature-build brief and
  the batched TDD spec all paste it verbatim. Reports now list assumptions
  made and any unrelated dead code noticed (not deleted). Fix briefs add
  "every changed line traces to one finding ID".
- **Step A Standards axis:** two new baseline checks, **Overbuilt** and
  **Drive-by Change**. The per-task quality verdict (T2/T3) uses them too.
- **Severity rule:** reachability sets the ceiling. A finding about an
  unreachable scenario is a NIT (recorded, never looped on, usually no code
  to add). Reachable but can't trigger on the live surface is MINOR. Input
  from outside the process is always reachable, so validation, auth and
  error handling there are never discounted.
- **T0/T1 plan format:** the tier line plus an assumptions line and a
  `step → verify: check` plan. This is how small work pins its intent, since
  it skips grill and the spec.
- **REFACTOR scoped** to code the current TDD cycle or task wrote or changed
  (test-evals, the TDD reference, build doctrine, the implementer template).
- Plugin version 0.2.3. No hook changes.

## v0.2.2 — hygiene after v0.2.1

- **Goldfish model pin moved into `lanes.md`.** v0.2.1 pinned the Goldfish
  children (`glm-5.3` on `ollama-cloud`) inside `goldfish-spec-review.md`,
  outside the pin single home. The pin now sits in a new `lanes.md` § Delegate
  pins table: not a reviewer lane, never counted toward a tier's reviewer set.
  The Goldfish reference points there. (This also makes the v0.2.1 line
  "model selection defers to lanes.md" true.)
- **`FIXES.md` taken out of the package.** It's a review artifact (reviewer
  IDs, a do-not-re-report list), which the release-hygiene rule keeps out of
  what ships. Its F16 line is corrected: no test was added; the existing
  `test_prefixed_plugin_skill_names_pass_without_flag` already covers
  `dev-pipeline:review-lessons`.
- **No cache folders in the zip** (`__pycache__`, `.pytest_cache`).
- Plugin version 0.2.2. No skill-behavior or hook changes.

## v0.2.1 — three-reviewer gate fix round (pre-install)

All fixes are mechanical wording edits applied by the orchestrator after the
v0.2.0 three-reviewer gate (Codex REVISE, Opus APPROVE WITH FIXES, Muse
APPROVE WITH FIXES); every finding was reproduced first. The findings→fixes
map (`FIXES.md`) is kept with the dev notes, outside the package (v0.2.2).

- Gate round and its re-gate sit OUTSIDE the tier confirm budget; T0 live
  deploys run the gate as their only round; gate OUT-OF-SCOPE = outside the
  net diff; worked T2+deploy budget example added.
- Per-task workflow tier-branch (T2 ONE combined reviewer, T3 two), per-task
  fix budget points at the tier table, requesting-code-review legacy "max 2
  cycles" and "two-stage" wording updated to the tier rules.
- HOLD-until-all-verdicts is restated as the default; the fix-brief supersede
  is a recovery path; Step 8's builder command reads the fix brief, not the
  raw review log.
- Step 9 stop handling aligned with the protocol (no auto user-escalation);
  Step 10 rewritten to lane names, tier reviewer counts and the trivial-fix
  rule; review pass required "from lane A or better".
- Dead-lane (Reviewer C) substitution rule added to reviewer-dispatch.md;
  Bot Mode row names lanes A/B/C; grill covers ambiguous T1; flow-map shows
  the Goldfish step; capture example records the model that ran.
- Goldfish review scope settled per user decision: offered at T2/T3 after the
  approved plan; T0/T1/research exempt; spec-range pass T2/T3; model selection
  defers to lanes.md (single home).
- Path B declared a T2 greenfield exception in size-tiers rule 7; Path B
  keeps both spec turns; implementer report drops "commits"; T0 push
  exception (no behavior change) stated in review-commit Step C.
- Bare lesson pointers now qualified with `review-lessons/references/...`;
  review-lessons "Old names" note covers numbered pitfall references.
- All CRLF files converted to LF (__init__.py, 5 references); plugin version
  0.2.1.
- Qualified `dev-pipeline:review-lessons` create-passing is already asserted
  by test_prefixed_plugin_skill_names_pass_without_flag (RESOLVED WITHOUT
  CHANGE, Opus-17b).

## v0.2.0 — slimmed pipeline, bounded review loops

**Why:** review loops were running to R10+. Several v0.1.x rules stacked to
keep them open (details at the end of
`skills/review-commit/references/confirm-round-protocol.md`).

### Review loops (the R10+ fix)
- Confirm rounds now review the **fix diff only**, not a fresh full-state diff
  each round. Issues in untouched code are `OUT-OF-SCOPE-N`: deferred, not looped
  on (a reproduced BLOCKING is the exception).
- **Severity floor:** only BLOCKING/MAJOR keep a loop open. MINOR/NIT go to a
  deferred list and never trigger a round. The orchestrator re-rates severity
  after reproducing.
- Confirm rounds go **only to reviewers with open findings**. A reviewer that
  returns SHIP drops out.
- **Three-reviewer gate runs once**, on the net diff, after the loop converges.
  It no longer runs on every round. It is still required before any live deploy.
  This changes a standing instruction; confirmed by the user on 2026-10-26.
- **Hard round budget per tier:** T1 = 1, T2 = 2, T3 = 3 confirm rounds. When
  the budget is spent, the loop stops and asks: ship / one more round /
  redesign. "Review loop N times" = N reviews in total.
- **Stop conditions:** ship when nothing BLOCKING/MAJOR is open;
  **same-class stop** (on the second same-class finding, redesign the class);
  **no-progress stop**; **fix-quality stop** (most findings come from the fixes).
- Removed the "deep sweep" exception, "never end on a single reviewer's
  confirm", and "a 30-45 min round is cheap insurance".
- Trivial fixes (≤ ~10 lines, mechanical, no design choice) may be made by the
  orchestrator directly, and it has to say so. The old "never hand-code, not
  even one line" rule is gone.

### Size tiers (new)
- `skills/orchestrator/references/size-tiers.md`: T0 Trivial / T1 Small /
  T2 Standard / T3 High-stakes. Each tier sets which stages run, how many
  reviewers, the per-task review depth (none / one combined reviewer / two
  separate reviewers), the converge cap and the confirm-round budget. The tier
  is stated up front and can only go up silently, never down.

### Contradictions fixed
- **Model pins:** a single home in `skills/orchestrator/references/lanes.md`.
  Stage files name lanes, not models. The old files disagreed (cursor-grok
  4.5 / 4.6 / 4.7, GPT-5.6 vs gpt-6-sol). The outside `model-routing` skill is
  older still and should be reconciled with lanes.md.
- **Loop caps:** 3 cycles, 5 rounds, "> 5 means churn" and "max 2 cycles" are
  replaced by the tier budget in `confirm-round-protocol.md`.
- **Test ownership:** the plan names the test cases (behavior, seam, expected
  value and its source). `test-evals` writes the tests and runs them RED. The
  `build` implementer makes them GREEN and doesn't edit them.
- **Test pyramid removed:** 80/15/5 contradicted the seam-first rule. Replaced
  by "seam first, then size".
- **Task size:** "each task = 2-5 minutes" contradicted "a task is the unit
  worth a reviewer gate". Now 2-5 minutes is a step; a task is one test cycle.
- **Stale pointers** to superseded skills (`build-review-loop`,
  `codex-confirm-loop`, `two-axis-code-review`, `subagent-driven-development`,
  the `plan` skill) now point to the plugin's own stages.
- Dead links in `build/references/per-task-workflow.md` removed.
- `workflow-steps.md` Step 6 told reviewers to read the whole codebase. It now
  uses the diff, like the rest of the loop.

### review-commit split
- `review-commit` keeps the process: `SKILL.md`, `confirm-round-protocol.md`,
  `two-axis-single-pass.md`, `workflow-steps.md`, `spec-convergence.md`, and
  the new `reviewer-dispatch.md` (CLI mechanics) and `release-hygiene.md`.
  It also keeps the brief/contract/loop-plan files and the scripts.
- The new **`review-lessons`** skill holds 34 lesson files (SQLite, MCP, REST,
  sync, mobile, test-quality traps, CLI quirks…). They are loaded on demand,
  one file per case.
- Deleted: the verbatim copies `build-review-loop.md` and
  `codex-confirm-loop.md`. Their pitfalls became
  `review-lessons/references/loop-pitfalls.md` and `confirm-loop-lessons.md`.
  Also deleted: `retired-red-flags-archive.md` and
  `retired-skill-md-2026-10-archive/`.

### Packaging
- `plugin.yaml` description cut from ~460 words to one sentence. The old text
  is under v0.1.8 below.
- The hook registers `review-lessons` as a bundled skill. Tests are updated
  (six → seven pinned names). The hook logic is unchanged.
- No `__pycache__` / `.pytest_cache` in the package.

## v0.1.8 and earlier

Original `plugin.yaml` description, kept verbatim:

> Development pipeline plugin: six stage skills (spec, build, review-commit, test-evals, grill, orchestrator) plus a pre_tool_call create-gate policy hook that vets every skill_manage create target (flat args and the atomic operations batch shape — including operations as a JSON string or dict, falsy-operations flat fallback, and unknown shapes, every entry examined, dict-structured operations never dropping the call's own flat create) with ONE existence walker mirroring the runtime _find_skill exactly: the ACTIVE profile's skill roots only (get_all_skills_dirs — skills dir, create_dir, skills.external_dirs), each configured root pre-checked against the component-wise exclusion rule over ITS OWN path (a root like /configured/node_modules/skills is skipped entirely), a filtered recursive SKILL.md walk that prunes excluded/dependency and support dirs and does NOT follow symlinked dirs, TWO-PASS sequence (every root's directory-name scan first; the frontmatter pass only when the whole directory scan failed), and frontmatter claimants deduped by the RESOLVED SKILL.md file (two dirs symlinking one SKILL.md = one holder; a unique SKILL.md display-name holder counts as existing; an ambiguous holder stays gated; a batch mixing mutating ops with creates disarms frontmatter-only matches). The create-dedup check is category-independent. Genuinely new skills are blocked unless the gate decides them: BLOCKS apply ONLY to creates whose category is software-development (the gate reserves NEW SOFTWARE-DEVELOPMENT skills; every other category string, non-string category, or absent/empty category passes UNGATED, consumes nothing, and never counts toward the multi-entry rule), and such a create is blocked unless the single-use allow flag at the RESOLVED active-home flag path (interpolated into the block message) is consumed first (one flag = one create; flag left intact on malformed gated names or multi-gated-create batches); sibling profiles are NOT existence roots; the flag's consent is not enforceable across terminal/write_file skill creation — that cross-tool boundary is the documented accepted risk. Errors on a create decision fail closed; all other tool calls pass through. v0.1.3: round-4 walker-only parity, frontmatter-name parity, falsy/unknown-operations gating, resolved flag path in the message. v0.1.4: round-5 root-component exclusion, frontmatter dedupe by resolved SKILL.md, two-pass lookup sequence, mutating-batch frontmatter disarm, dict-operations flat-create preservation, live-probe flag safety. v0.1.5: round-6 — every DISCOVERED SKILL.md path is re-checked at FILE level by the runtime exclusion predicate before counting as a claimant (a root whose own SKILL.md is a directory/symlink escaped the walker's dir-name pruning), multi-entry batches skip the existence lookup entirely (every well-formed create gated; runtime already-exists rejection accepted as over-gating), single-op calls keep full runtime parity, parallel-call interleaving documented as accepted, debug log on fallback-rule switches. v0.1.7: create-gate SCOPED to the software-development category — only creates whose category normalizes to 'software-development' are gated; every other category (and a create with no category) passes ungated, consumes nothing, and never counts toward the multi-entry rule (a mixed batch gates only its gated creates; gate behavior for gated creates is unchanged).
