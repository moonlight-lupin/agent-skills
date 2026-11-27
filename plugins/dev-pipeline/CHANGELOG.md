## 0.6.0 — coding-capability upgrades

Always-loaded text shrink (rules moved, none dropped):
- `build` SKILL.md 19.6 KB → 7.9 KB: implementation doctrine, adjacent-work pointers, model pins, the full Red Flags compliance checklist, fix-loop + RED-test contract, and continuous-execution wording now live in `references/build-doctrine.md`; ledger curation + usage rules in `references/ledger-orchestration-adaptation.md`.
- `spec` SKILL.md 18.5 KB → 7.7 KB: WHAT/WHY boundary table, seam-sketching rules, case-table rules, clarify phase, self-review checklist, Goldfish review, spec consumption, constitution gates, cross-artifact analyze, no-placeholders, and both handoff paths now live in `references/spec-doctrine.md`.
- `test-evals` SKILL.md 15.0 KB → 6.2 KB: full TDD methodology, seam/mock discipline, batched TDD + Opus loop, pre-commit review, pattern integration, and the full Red Flags list now live in `references/test-doctrine.md`.
- Hard cap 8 KB per always-loaded SKILL.md asserted by `tests/test_skill_sizes.py`.

New `debug` skill (ninth bundled skill):
- Bug-shaped work ("fix this", "this is broken", failing test, stack trace) routes to `debug` instead of the feature chain: reproduce → failing test at the highest public seam (or name why not) → minimal fix → named test + full suite → `review-commit` at the risk-derived tier.
- Register in `_BUNDLED_SKILLS` ( eight → nine, pinned in `tests/test_create_gate.py`); orchestrator stage table + `risk-routing.md` route bug-shaped asks; the router hint's verb list ("fix, debug") now has its route.

review-commit: CI watch-and-fix loop + PR hygiene:
- New single home `ci-loop-and-pr-hygiene.md` (linked from the stage SKILL and `workflow-steps.md`): watch CI to completion, classify failures, reproduce locally, fix within the tier's confirm budget with capped CI fix rounds; pre-existing failures stay named, never ignored; PR rules: draft PR, ~3,000-line split guide, body = intent/test evidence/risk tier, no force-push to shared branches.

Verification: `pytest plugins/dev-pipeline/tests/ -q` green; secrets grep clean; forbidden-identity scan clean.

# Changelog

## 0.5.0 — discoverability and unattended execution

- **Behavior change, in plain words:** the pipeline no longer stops at stage handoffs to ask "shall I proceed?". After a spec or plan is saved, the session states the saved path and continues. Optional extras run (or stay skipped) without a prompt: the S2/S3 Goldfish spec review now runs after the approved plan; ticket slicing runs only when the user already asked for tickets. The session stops **only at an important fork** — a public-contract change, a trust/auth/money/privacy/irreversible-data boundary, an expensive-to-reverse architecture choice, a relaxed constraint, or a ship-gate choice with residual risk (spent budget with open blockers, merge to the default branch, tag, live deploy). The authoritative definition, including what is explicitly *not* a fork, lives in `skills/orchestrator/references/unattended.md`; every stage skill points there. Pushing the feature branch and opening a draft PR after a SHIP review is not a fork and proceeds without asking; merging, tagging and live deploy stay forks. A new fork that surfaces mid-pipeline stops the session with one numbered question and a recommended answer, then continues.
- **Discoverability:** registered plugin skills are not listed in Hermes' available-skills index, so a plain "build X" never reached the orchestrator. When the host exposes `ctx.register_system_prompt_section`, `register()` now adds a short system-prompt hint (well under the API's `max_chars`, ~300 characters, no pipeline detail, no risk table, no model names) telling Hermes to load `skill_view("dev-pipeline:orchestrator")` for build/implement/add/fix/debug/review asks that do not name a phase. The registration is guarded on `callable(ctx.register_system_prompt_section)` — exactly like the existing `register_tool` guard — so older Hermes without the API still loads the plugin. New fake-`ctx` tests cover registration, absence tolerance, an error not breaking plugin load, and the no-model-pins/no-pipeline-detail contract (`tests/test_system_prompt_section.py`).
- `grill` remains the place that collects foreseeable important forks; its when-to-use now states S2/S3 fuzzy plans and ambiguous S1 asks, and that the session does not proceed to spec while known important forks are open. Spec, test-evals, build and review-commit drop their handoff questions and point at the fork rule.
- Skill metadata bumps (always-loaded contract text changed): orchestrator 2.2.0, grill 1.2.0, spec 2.2.0, test-evals 2.1.0, build 2.2.0, review-commit 2.3.0. Create-gate behavior, review budgets, risk routing and the three-reviewer live-deploy gate are unchanged.

## 0.4.3 — lane source of truth and safe git

- The lanes TOML is the single source for model names, CLI binaries, and invocation flags. `references/lanes.md` now carries lane roles, rules, and the degrade policy only — the dated model-pin table is gone (it had drifted from the shipped default).
- New `tests/test_lane_pins.py`: the default config must declare all four CLI families (Claude Code, Cursor, Codex, Muse); lane Markdown must be free of dated pin tables, literal `--model <id>` commands, and versioned pin ids; no command block under the plugin may run `git add -A` (stage explicit paths; `git status --short` and a secrets scan before every commit — the antipattern warnings stay, the instructional blocks are gone).
- Lesson dispatch examples now use env vars for model ids; pin-drift lessons point at the config instead of remembered tier labels.
- Version-pointer prose updated wherever it claimed `lanes.md` held the pins.

## 0.4.2 — public hygiene, link integrity, create-gate doc trim

- Scrubbed private project identities and operator initials from all prose: case-study citations genericised or dropped; those sessions are described without project names (the identity term list is a local denylist outside the public tree; the test skips identity screening where the denylist is absent).
- Fixed or removed every dangling in-plugin citation; Goldfish persona/standard paths now point at the bundled files (`goldfish/personas/…`, `goldfish/standards/…`).
- New `tests/test_reference_paths.py`: fails when any plugin-context file citation fails to resolve, and fails when a private project identity is reintroduced.
- Trimmed the create-gate module docstring (~9.4 KB → ~3.3 KB): gated scope, one-flag-one-create, existence-check contract, batch rules, fail-closed behavior and the two accepted risks remain; walker history already lives in CHANGELOG. Hook logic unchanged.
- README and repo tree labels now say eight bundled skills (six stage skills plus briefs and review-lessons). Removed `plugins/lumen/tests/test_adapters_contract.py.attest`.

## 0.4.1 — gate hardening from the full-plugin review (r2)

- Untrusted lane config: a repository-provided `.dev-pipeline/lanes.toml` can no longer define routes, providers or executable commands, nor touch the claude_code harness table (binary, binary_args, permission_mode, tool lists) or per-lane argv template keys (model_args, effort_args); its only surface is per-lane model and effort labels on trusted lanes (family is trusted-only: it feeds the family-independence check for review seats). `validate_extra_args` denies permission/sandbox bypass flag variants (`--permission-mode bypassPermissions`, `--sandbox danger-full-access`).
- Engineering evidence: degraded terminal envelopes never classify a capability as missing (no installs inside degraded backends); the gate refuses to run when the operator config is unreachable instead of falling back to diff-only; FINDINGS exit codes corrected against probed behavior (go vet/test 1, clippy/cargo-test 101, npm 1); non-string terminal `output` fails closed; JS checks fall back from the project-local binary to PATH; discover reports language-detection failure instead of a silent None; doctor fully covered by tests.

## 0.4.0 — engineering capability management

- Native capability inventory across coding CLIs, language toolchains, LSP, scanners and isolation. Explicit allowlist for fixed install recipes, version and auth status probes, read-only AST search, bounded terminal-backed checks, profile-scoped commit-specific evidence and engineering gate. Existing lane resolver remains authoritative. Operator controls network, project execution and required checks.
- Integrate evidence collection with orchestration, build and review; preserve existing reviewer gates. Doctor invokes the existing lane resolver in the active backend. Detect and install official Bubblewrap and Advanced Delegation plugins when allowlisted. No unapproved installs or host-side execution.

## 0.3.2

Reconcile the two dev-pipeline lines: land the briefs/lanes/review-budget
work (stamped briefs, case tables, orchestrator lanes config, review budget)
together with the CLI arm runner and its verdict/dispatch gating, and carry the
live-only confirm-round rule (freeze the tracked tree between dispatch and read
verdicts). Published plugin version is 0.3.2.

## v0.3.1 — counted rounds, stamped briefs, case tables

**Why:** on one project (Nov 2026) a v0.3.0 three-reviewer gate ran 15 fix
rounds (D through P) and 8 re-close rounds in an evening. The protocol allows
one fix round and one re-gate. The rules were there; nothing counted the rounds.

- **Every reviewer dispatch after R1 is a confirm round**, whatever the brief
  calls it (fix review, re-close, re-gate, verification pass). Single-reviewer
  "fix reviews" no longer sit outside the budget.
- **New `review-commit/scripts/review_budget.py`** is the loop's ledger and
  budget gate, run before every reviewer dispatch. It counts rounds per tier
  (a gate gets one re-gate) and caps severities. It reports SHIP / CONTINUE /
  REDESIGN / ASK-USER, and refuses a round when:
  - the budget is spent with BLOCKING/MAJOR open;
  - a class has its third BLOCKING/MAJOR finding;
  - open BLOCKING+MAJOR didn't fall from the previous round;
  - nothing is open.

  Only `extend`, which records the user's decision, gets past a refusal.
  Findings move open → fixed → resolved, so a claimed fix isn't a confirmed one.
- **Test-only findings are capped at MINOR** unless the test is the only
  coverage of a BLOCKING/MAJOR behavior.
- **Every finding gets a class**; the same-class stop counts by class.
- **One fix brief and one review per round**, never one per finding.
- **Milestones:** R1 and the gate review one milestone (a build phase or
  feature, as a guide ≤ ~3,000 changed lines), never a whole product as its
  first full review. Re-gates review the fix diff, not the net diff again.
- **New `briefs` skill** (bundled; the hook registers it):
  - The single home for brief templates: implementer (pointer), fix and
    feature builder briefs (moved from review-commit), and new R1, confirm
    and gate review briefs with a shared severity block.
  - **Case tables** (`briefs/references/case-tables.md`): the spec sheet for
    any rule with state (corrections, retries, idempotence, rolling windows,
    caches, sync, lifecycles, permission matrices, time boundaries). One row
    per case, reviewed once before the build, and every row becomes a RED
    test. A missing row found in review is a design change: update the table
    first. Wired into the spec plan turn, the plan template's Test-First
    Gate, test-evals and the same-class stop.
  - **`briefs/scripts/stamp_brief.py`** fills SHAs, the diff (written to a
    file, with line and file counts), test-command results, the round line
    from the budget ledger, and the severity and builder blocks. It refuses
    to write a brief when:
    - a placeholder is unfilled;
    - the brief cites a commit that is neither base nor head;
    - no review round is open;
    - the diff passes 5,000 lines without `--allow-large`.
- Tests: `test_review_budget.py` (9) and `test_stamp_brief.py` (7). The
  create-gate tests pin eight bundled skill names, and the routing contract
  test pins 0.3.1.
- Plugin version 0.3.1. Skill metadata: review-commit 2.2.0, briefs 1.0.0.
  No hook logic changes beyond the bundled-skill list.
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
