---
name: skill-quality-review
description: "Use when auditing or reviewing skill quality — batch checks across a library, deep per-skill grep methodology, usage stats, efficacy testing, or fix planning. Single consolidated home for the writing-for-agents review framework and the 3-surface review methodology."
license: MIT
metadata:
  version: 1.2.0
  author: moonlight-lupin
  hermes:
    tags: [skills, review, audit, quality, batch]
    related_skills: [hermes-agent-skill-authoring, skill-curation, plan]
---

# Skill Quality Review

Audit SKILL.md quality across a set of skills. Identifies the most-used skills, classifies them as self-developed vs builtin, then runs batch writing-for-agents checks and fixes.

The review framework blends Matt Pocock's `writing-for-agents` (context pointers, two loads, information hierarchy, completion criteria, leading words, pruning) with `hermes-agent-skill-authoring` peer-matched structure and cross-reference parity. See `references/writing-for-agents-framework.md` for the full lever set.

`references/skill-review-methodology.md` lives HERE in this skill — it covers per-skill grep-based review (3-sources-of-truth drift, pricing registry, guardrail asymmetry). This skill covers **batch automated checks**, the **deep per-skill methodology**, and **usage-based prioritisation** across all skills in a repo or local library. Authoring-time mechanical sweeps (TOC coverage, nesting, orphans) run via `scripts/check_references.py` in this skill — format-agnostic, works on any repo (this skill vendors it so plugin repos do not depend on a Hermes-side script). For Hermes in-repo skills, `hermes-agent-skill-authoring/scripts/audit_references.py` remains the canonical checker; see `references/hermes-library-review.md`. Deep methodology below.

## Know the skill format first

Before running any checks, identify the skill format — the frontmatter fields, structural sections, and validation rules differ:

| Aspect | Hermes in-repo | Claude Code plugin |
|---|---|---|
| Required frontmatter | `name`, `description`, `version`, `author`, `license`, `metadata.hermes.{tags, related_skills}` | `name` + `description` only |
| Description trigger convention | Starts with "Use when ..." | Often carries `Triggers: "phrase1", "phrase2"` inline |
| Structural sections | `## Overview` → `## When to Use` → `## Common Pitfalls` → `## Verification Checklist` | `## What this skill is for` → `## Workflow` → skill-specific sections |
| Validator source | `tools/skill_manager_tool.py` in hermes-agent repo | `.claude-plugin/plugin.json` + `tools/build_plugin.py` in the plugin repo |
| License field | In frontmatter | In `.claude-plugin/plugin.json`, not per-skill |

**Check for `.claude-plugin/plugin.json`** at the repo root to detect a Claude plugin. If present, adapt Checks 1, 5, and 8 to the Claude format (see `references/claude-plugin-review.md`). The script-quality checks (py_compile, grep checklist, network audit, secret scan, cross-sibling consistency) apply universally — those are format-agnostic.

## When to Use

- User says "review my skills" or "which skills do we use the most"
- User says "audit the skill quality in this repo" or "review my plugin"
- User asks to identify self-developed skills and review them
- Before a release tag on a skill-bearing plugin repo
- After bulk-creating or migrating skills
- User asks "test efficacy" / "did this change actually help" after a skill refactor

## Workflow

### A. Local-library steps (Hermes profile only)

The two sub-steps below apply only when reviewing the local Hermes skill library. Skip them entirely for remote repos and Claude plugin repos. For the full local-library procedure (state.db query, builtin-tree comparison, author-field heuristics), see `references/hermes-library-review.md`.

0. Identify most-used skills (usage frequency): query the platform's session state for actual `skill_view`/equivalent load counts when available; fall back to a `.usage.json`-style usage file when the state store does not exist or is stale.

0a. Classify self-developed vs builtin: compare the user skills directory against the runtime's bundled installation tree, and confirm with the frontmatter author field.

### B. Batch review (all formats)

#### 1. Clone (if remote) and discover skills

```python
import pathlib
repo = pathlib.Path("<repo-root>")
skills = sorted(repo.rglob("SKILL.md"))
print(f"Total: {len(skills)} skills")
```

#### 2. Run all checks

Run all automated checks from `references/batch-checks.md` (Checks 1-16 plus the reference-hygiene sweep and efficacy coverage — the check-summary table lists them). Each produces a structured report. Collect findings into MAJOR / MINOR / NIT severity buckets.

#### 3. Present findings

Format as a table: finding, severity, skills affected. Include the key metrics (description char counts, trigger ratios, identity phrases leaked).

#### 4. Plan fixes

Write an actionable plan to the repo's plans folder (create one if none exists, e.g. `plans/`), one task per finding. Include exact patch old/new strings for each fix. For bulk fixes (34+ files), include a script-based approach.

#### 5. Execute

- Task 1 first (touches all files — e.g. frontmatter standardisation)
- Then remaining tasks in parallel (different files/sections)
- Verify after each task: re-run the relevant check + repo tests
- Commit after each task

#### 6. Final verification

Re-run all checks. Confirm all findings resolved. Run repo tests.

### 7. Single-skill sprawl refactor (deep pass on ONE oversized skill)

When one SKILL.md fails the sprawl test — a single section over ~50% of the file, or a flat list of 60+ items — refactor that skill alone. The batch workflow does not apply.

1. **Map section sizes.** Regex every heading, compute the char span of each section. The dominant section is the refactor target. A `skill_view` result over ~100KB persists to a spillover cache file whose content is ONE JSON line — parse it with `json.load` and navigate by character offsets; line-based reads see a single giant line.
2. **Cluster the flat list.** Classify every item: keep (fires every run) / tool-mechanics (CLI flags, polling, env quirks) / domain sediment (finished-project specifics). Classify by list POSITION, never the printed number — hand-maintained numbered lists drift (duplicate and skipped numbers), so the ordinal is not a stable identifier and a position-keyed bucketing with a coverage assert catches drift.
3. **Split by branch, not by date.** Write each displaced cluster to `references/<topic>.md` named by its TOPIC (tool mechanics, past-project findings), renumber the kept items, and give each disclosed file a pointer line stating WHEN to read it. SKILL.md keeps only what every run needs.
4. **Dedupe symptom lists.** Red Flags / Rationalizations / Remember sections usually restate workflow rules. Keep the checklist as a symptom index that points at each rule's governing section; a rule lives once, in the section that uses it.
5. **Archive before deleting.** The skills tree is not a git repo — write removed content verbatim to `references/retired-<topic>-archive.md` BEFORE the destructive edit, never after. If a destructive edit lands without a prior archive, recover the original from the session's earlier `skill_view` spillover cache (see step 1) — it holds the verbatim pre-edit text.
6. **Verify structurally.** Even ``` fence count, heading inventory intact, no stale references to removed sections, every new reference file exists with the expected item count. Expect count-based checks to over-flag: an in-body mention of a section name or reference path is a valid second occurrence — inspect the context instead of trusting the count.
7. **Bump the skill's version** (minor) and preserve any user-mandated content rules — nothing leaves the skill without approval and an archive.

### 8. Efficacy A/B test (does the refactor change behavior?)

After a quality refactor, structural checks prove the file is better-shaped; they do not prove the agent behaves better. When the user asks for efficacy evidence, run a controlled A/B with parallel agent dispatch: reconstruct the before-arm byte-exactly, probe both arms with identical scenarios on fresh subagents, score against a fixed rubric. Full procedure, controlled-variable rules, dispatch pitfalls, and evaluation-coverage rules (scenarios per skill, model scope): see `references/efficacy-ab-test.md` (rubric starter: `templates/efficacy-rubric-template.md`). When the question is "was the skill worth having at all" rather than "did v2 beat v1", use the Quick used-vs-no-skill variant at the end of that reference — it drops the byte-exact before-arm and scores quality, time, and tokens.

### 9. Reference-hygiene sweep (mechanical, whole-tree)

Single source of truth: `scripts/check_references.py` in this skill (format-agnostic; no dependency on any platform-side script). The bulk TOC fixer `add_toc.py` lives in this skill's `scripts/` — dry-run by default, `--apply` to write; generates Contents lists from the file's own structure (## first, then ###, then bold-label bullets; code-fence aware), capped at 60 entries so label-dump files are skipped rather than doubled; writes exactly one trailing newline.

For Hermes in-repo libraries, `hermes-agent-skill-authoring/scripts/audit_references.py` remains the canonical cross-check.

Sequence: audit (check_references.py) → dry-run review → `add_toc.py --apply` → re-audit. Expect `no-contents-list` to drop to deliberate exceptions only. Fix any `nested`/`orphan-reference` findings by editing SKILL.md pointers, preserving frontmatter.
### hermes-agent repo profile (bundled v2.0.0 standards)

Applies when reviewing a skill for publication into the hermes-agent repo (`skills/` or `optional-skills/`). Sources of truth: the built-in `hermes-agent-skill-authoring` v2.0.0 walkthrough and the repo AGENTS.md "Skill authoring standards (HARDLINE)" section. Checks beyond the batch set:

- **Tier decision**: bundled requires a 5+ sessions/month bar; niche/vertical/heavy goes to `optional-skills/`. Review rejects a bundled-tier violation.
- **Description hardline ≤ 60 chars** — the validator allows 1024, but review REJECTS over 60. One sentence, ends with a period, no marketing words, capability self-contained in the 57-char system-prompt window.
- **Author credit**: human first — `Real Name (handle), Hermes Agent`. Never `author: Hermes Agent` alone on a contributed skill.
- **Platforms gating**: audited from actual prose/scripts (fcntl/termios → not windows), never copied from a sibling.
- **No machine-local paths** (`/home/<you>/...`) and **Hermes-tool framing** (`search_files` not grep, `read_file` not cat, invocations framed as `terminal(command=...)`).
- **Tests**: `tests/skills/test_<skill>_skill.py` (stdlib + pytest + unittest.mock, no live network) via `scripts/run_tests.sh`. **Docs regen** with scope discipline: only the skill's own page, catalog row, and one `sidebars.ts` insertion.
- **No router/index skills**; every `related_skills` entry resolves in-repo.

### personal library profile (this library)

Applies to the local personal skill library — the batch checks in this skill's workflow remain authoritative here. Key differences from the repo profile:

- **Descriptions up to 1024 chars and MUST be trigger-style ("Use when ...")** — the platform's BM25 retrieval has no stemming ("onboard" does not match "onboarding"), so capability nouns AND trigger words as literal surface forms are load-bearing. The repo's skills-ref CI enforces the 1024 ceiling on publish.
- **Size**: 8-15k chars target, >20k split to references/.
- **Structure**: When to Use + actionable body + Common Pitfalls + Verification Checklist minimum.
- **Audit mode**: authoring-time mechanical sweeps (TOC coverage, one-level-deep linkage, orphans) run via `scripts/check_references.py` in this skill; the deep per-skill methodology is this skill's `references/skill-review-methodology.md`.
- **Local-library classification (usage stats, builtin-vs-self-developed, curator adoption)**: see `references/hermes-library-review.md`.

## Check summary

| # | Check | Severity if found |
|---|---|---|
| 1 | Frontmatter validation (adapt fields to format — see `references/claude-plugin-review.md`) | MAJOR (format-dependent — frontmatter "gaps" are false positives on Claude plugins, where only name + description are required) |
| 2 | Description identity leakage (intent-first, deterministic, local engine, etc.) | MAJOR |
| 3 | Trigger ratio (< 25% = low, < 30% = borderline) | MINOR |
| 4 | Completion criteria (steps without "Done when") | MINOR |
| 5 | Structure gaps (adapt expected sections to format — Hermes vs Claude plugin) | MINOR |
| 6 | Name mismatch (dir name != frontmatter name) | MINOR |
| 7 | Boilerplate duplication (identical sections across many skills) | NIT; score by total duplicated lines across the library, not per file — escalate to MINOR when large in aggregate (identical house-style text is loaded context on every invocation) |
| 8 | Cross-sibling consistency (British English, date format, license type, domain terminology — read license from plugin.json for Claude plugins) | NIT; MINOR for terminology drift (see Check 8b) |
| 9 | No-op prose ("be careful", "be thorough", "best practices") | NIT |
| 10 | "Use when" description prefix missing | MAJOR |
| 11 | `metadata.hermes` nesting wrong or missing (Hermes format only) | MINOR |
| 12 | Literal duplicate lines | MINOR |
| 13 | Two-loads mismatch | MAJOR |
| 14 | Contradictory DEFAULT labels; options with no default; loose tolerances; hidden engine defaults; voodoo constants (see §Check 14) | MAJOR (contradictory defaults) / MINOR (missing default, loose tolerance) |
| 15 | Callability — cited scripts runnable as written (see §Check 15) | MAJOR |
| 16 | Unworkable or non-independent instructions (see §Check 16) | MAJOR |
| 17 | Reference hygiene — TOC on long references, one level deep, orphans (see §Check 17) | MINOR |
| 18 | Workflow scaffolding — progress checklist for 7+-step workflows; named feedback loop (see §Check 18) | MINOR |
| 19 | Evaluation coverage — evals per skill; skills with none flagged; model scope recorded (see §Check 19) | MINOR |

Full check code and fix patterns: see `references/batch-checks.md`.
Claude plugin format adaptations: see `references/claude-plugin-review.md`.
Writing-for-agents review framework (context pointers, two loads, hierarchy, leading words, pruning): see `references/writing-for-agents-framework.md`.
Recurring failure patterns from real reviews (with grep checks and fix patterns): see `references/recurring-failure-patterns.md`.
Domain-specific passive-voice false positives (accounting, legal, medical): see `references/domain-passive-voice.md`.
Building product skills alongside an existing reference toolkit: see `references/independent-skills.md`.
Deep per-skill grep review methodology (3-sources-of-truth drift, pricing registry, guardrail asymmetry): see `references/skill-review-methodology.md`.
Hermes local-library classification (state.db usage stats, builtin-vs-self-developed, curator adoption): see `references/hermes-library-review.md`.
Fix-phase orchestration (batch ordering, parallel agents, no-loss proof): see `references/fix-phase-pitfalls.md`.

## Fix priority

For the Claude plugin profile, order fixes by how much each would have caught on a real review (pere-toolkit). Costly defects first, mechanical last, conciseness last of all:

1. **Callability (Check 15)** — uncallable or wrong call lines (MAJOR)
2. **Unworkable / non-independent instructions (Check 16)** — instructions the agent cannot follow, or a sign-off gate where the signer reviews its own output (MAJOR)
3. **Defaults / tolerances (Check 14)** — options with no default, loose tolerances on exact steps, hidden engine defaults, voodoo constants
4. **Docs ↔ code drift that changes numbers**
5. **Mechanical** — TOC on long references, unnamed packages, frontmatter (mechanical fixes are cheap and safe)
6. **Terminology (Check 8b)** — inventory, glossary, first-use alignment
7. **Boilerplate / conciseness — LAST.** Fixing callability ADDS lines; a conciseness pass over unsettled text deletes the new call lines. Run conciseness only on settled text, and prove nothing load-bearing was lost (see Pitfall 19).

For the Hermes-library profile, the frontmatter-first order below remains valid because frontmatter there carries load-bearing trigger surface:

1. **Frontmatter** — version/author/license/metadata missing (MAJOR, all files)
2. **Description identity leakage** — cut identity, keep triggers (MAJOR, per-skill)
3. **Callability (Check 15)** — uncallable or wrong call lines (MAJOR, per-skill)
4. **## Files missing** — add section (MINOR, per-skill)
5. **Completion criteria** — add "Done when" to steps (MINOR, per-skill)
6. **Name mismatch** — align frontmatter name with directory (MINOR, per-skill)
7. **## Common Pitfalls** — add section (optional, per-skill)

## Bulk fix technique

For fixes that touch all skills (frontmatter, name fixes), use a batch script (`execute_code` in Hermes) that patches all files in one pass. For targeted fixes (description trimming, ## Files addition), use a file-patching tool per file.

See `references/batch-checks.md` for the script template. For fix-phase dispatch discipline (batch ordering, parallel agents, proving nothing was lost), see `references/fix-phase-pitfalls.md`.

## Common Pitfalls

1. **Protected skills block writes.** Bundled skills (shipped with the runtime) cannot be patched in place. If the skill you want to update is bundled, say so and recommend the platform's adoption flow (in Hermes: `hermes curator adopt <name>`).

2. **Hermes vs Claude plugin format false-positives.** Running Hermes-format checks (expecting `version`/`author`/`license`/`metadata` in frontmatter, `## Overview`/`## Common Pitfalls` in structure) against a Claude Code plugin will flag every skill as broken. Always detect the format first (check for `.claude-plugin/plugin.json`) and adapt checks 1, 5, and 8. See `references/claude-plugin-review.md` for the adaptation table.

3. **Tests may reference SKILL.md content.** Before patching, check if any test files read SKILL.md (grep for `SKILL.md` in test directories). The `test_recipes.py` pattern in fpa-toolkit reads the body but not frontmatter — safe to edit frontmatter.

4. **Name change may break code references.** Before changing a frontmatter `name:` field, grep for the old name in all `.py`, `.md`, `.json` files. If code references the old name, update those too.

5. **Description trimming changes invocation behaviour.** Preserve all quoted trigger phrases and NOT-for disambiguators. Only cut identity/behavioral content. Verify trigger ratio >= 30% after trimming.

6. **Parallel subagent write conflicts.** When dispatching `delegate_task` subagents to fix skills in parallel, and you are also patching skills directly, both writers may target the same file. The `patch` tool will warn: "modified by sibling subagent but this agent never read it." Always re-read a file before patching if a subagent may have touched it. Alternatively, partition work so subagents and the orchestrator never touch the same files.

7. **Router skills skew consistency ratios.** Skills like `workflow-recipes` or `getting-started` are pure routers — they don't produce deliverables, carry trigger phrases, or reference house-style. Exclude them from trigger-coverage and house-style-consistency denominators. See `references/claude-plugin-review.md` § "Router/reference skills are exempt".

8. **Namespace-prefixed frontmatter names.** Claude plugins with multiple skill families (e.g. fpa-toolkit with `fpa-balance-sheet` in dir `balance-sheet/`) use a prefix to prevent cross-plugin collisions. This is intentional — do not flag as a name mismatch. Only flag when neither name is a prefix of the other.

9. **Rebase needed if remote has advanced.** Always `git fetch` + check for new commits before pushing. Rebase local commits on top.

10. **Usage frequency from local state, not .usage.json.** When identifying most-used skills in a local library, query the platform's session state (`state.db` `messages.tool_calls` in Hermes) for `skill_view` call counts — see `references/hermes-library-review.md`. The `.usage.json` file may not exist or may be stale. See Workflow §A step 0.

11. **Self-developed vs builtin classification.** Platform specifics (bundled tree paths, author-field heuristics, curator adoption) are in `references/hermes-library-review.md`. The test: compare the user skills directory against the runtime installation's bundled tree, and confirm with the frontmatter author field. See Workflow §A step 0a.

12. **Parallel review for 12+ skills.** Dispatch 2 `delegate_task` subagents (6 skills each) rather than reviewing serially. Each reads the full SKILL.md + linked files, applies the writing-for-agents levers, and returns structured findings. See `references/writing-for-agents-framework.md` for the lever set and dispatch pattern.

13. **Recurring failure patterns across self-developed skills (Aug 2026 review of 12 skills).** The same issues appeared across multiple independent skills — encode them as batch checks, not per-skill findings. See `references/recurring-failure-patterns.md` for the full list (11 patterns with grep checks and fix patterns). The most impactful:
    - **"Use when" description prefix missing (12/12 skills).** Every model-invoked description led with identity instead of trigger branches. This is the single most common frontmatter miss — 100% hit rate across 12 skills.
    - **Build history / changelog sediment (4/12 skills).** tablina, orion, hermes-post-update, development-workflow all carried project history (commit hashes, per-phase review findings, batch logs) that belongs in `references/build-history.md` or deleted. The skill describes current state, not project evolution.
    - **Project README masquerading as skill (2/12 skills).** tablina (100K chars) and orion (57K chars) were project wikis with no Overview, no When to Use, no workflow steps. Fix: structural rebuild — extract 85%+ into reference files, rewrite as ~15K operational guide.
    - **`metadata.hermes` nesting wrong or missing (6/12 skills).** Tags at top level instead of under `metadata.hermes`, or metadata block omitted entirely.
    - **Cross-reference parity: audio/feature defaults inconsistent across 4 sources (1/12 skills, high-impact).** SKILL.md says "audio by default" but script sends `generate_audio=False` for all models. The fix may require changing the script, not just the docs.
    - **Literal duplicate content from copy-paste (3/12 skills).** Duplicate table rows, verbatim-copied pitfall bullets, broken pitfall numbering (duplicate "8", missing "10").
    - **Description retrieval regression (3/3 skills, second-pass review).** Rewriting descriptions to add "Use when" trigger prefixes dropped capability nouns. The BM25 tokenizer has no stemming — "onboard" does not match "onboarding". Descriptions must carry both trigger words AND capability words as literal surface forms. Test against the repo's BM25 index before shipping. See `references/recurring-failure-patterns.md` pattern 12.

14. **Fix scripts that mutate a section must parse by position, not printed ordinal.** Hand-maintained numbered lists contain duplicate and skipped numbers; keying classification or dedupe on the printed number mis-buckets items and can silently drop content. Enumerate matches in order, assert full position coverage, and diff item counts before writing.

15. **Check for literal near-duplicate items before splitting a list.** A long accumulated list often carries the same finding written twice under one number (paraphrase, not verbatim — similarity ~0.55 still counts). Compare candidates by normalized text before distributing to reference files; keep the fuller copy and note the merge.

16. **Heading extraction without fence tracking indexes code comments.** Fenced examples carry `## ` comment lines and `- **Label**:` bullets that look like document structure. Toggle fence state on every ``` line and extract structure only outside fences — a generated Contents list built from code samples corrupts the doc silently.

17. **Bulk text writers must end files with exactly one trailing newline.** A missing final newline makes git report the last line as deleted plus re-added: the commit diff reads as content loss and costs a false investigation before push. Write `"\n".join(lines) + "\n"`. Applies to this skill's own files too — a structural sweep (trailing newline, fence parity, dead-pointer check over rglob) is part of final verification.

18. **Fix-phase orchestration (multi-agent batches).** Eight pitfalls from a real 5-agent run over 52 skills (pere-toolkit, Oct 2026). Full detail and the batch-sequencing template: `references/fix-phase-pitfalls.md`. The load-bearing ones:
    - **Conciseness LAST.** Callability fixes add lines; a trim over unsettled text deletes the call lines the fix phase just added. Run conciseness on settled text, then prove nothing load-bearing was lost: script-check that every code span and CLI command in the previous commit still exists in the new one.
    - **Regex boilerplate replacement eats neighbours** — match to paragraph end, never end-of-line; diff every replaced span against HEAD.
    - **Python writers and CRLF** — put `newline="\n"` in every open() in every agent prompt; lint for CRLF before commit.
    - **Parallel test runs on shared resources are flaky** (LibreOffice fights) — agents report such failures, the orchestrator re-runs the suite solo before each commit.
    - **Announce new lint rules before agents run tests**, or land them after the batch — a mid-batch rule breaks every agent's "suite green" gate.
    - **Partition by file; the orchestrator stays out of agents' files mid-run** — mechanical cross-cutting edits (boilerplate, TOCs) go before or after an agent batch, never during.
    - **Verify reviewer findings before fixing** — each finding needs a quoted locator and a spot-check; counts come from scripts, not reviewer estimates (two independent reviewers still produced three false findings).

## Verification Checklist

- [ ] All SKILL.md files discovered (count matches expected)
- [ ] Usage frequency queried from local state (if local library review; see `references/hermes-library-review.md`)
- [ ] Skills classified as self-developed vs builtin (if local library review)
- [ ] All checks run (Checks 1-16 + reference hygiene + scaffolding + eval coverage) and findings collected
- [ ] Findings classified MAJOR / MINOR / NIT
- [ ] Plan written to the repo's plans folder with exact patch strings
- [ ] Each task verified: relevant check re-run + repo tests pass
- [ ] Each task committed with descriptive message
- [ ] Final verification: all checks pass
- [ ] Single-skill refactors: fence balance OK, removed content archived verbatim, reference files exist (Workflow §7)
- [ ] Pushed (or user told "push" to push)

## Efficacy testing a skill refactor (validated 2026-09-12)

Before/after behavioral validation for a skill writing refactor. Pattern: (1) reconstruct the
"before" version byte-exact (from cache captures + archives; verify char count and section
parity before testing); (2) copy both arms to isolated test dirs; (3) write scenario probes
targeting exactly what changed (pointer firing, dedupe, sprawl) with a fixed 0-3 rubric
written to disk first; (4) dispatch one fresh subagent per arm with identical prompts, arm
identity unstated; (5) score blind, compare rubric scores AND tool traffic (api_calls/duration
from the completion reports). Verdict shapes: sprawl refactor should show equal-or-better
answers with fewer calls; pure dedupe should show identical behavior. n=1 per cell is
directional only — state that. Side benefit: probes surface pre-existing defects (dead
pointers, duplicate items) worth fixing in the live skill regardless of verdict.
