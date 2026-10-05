---
name: skill-quality-review
description: "Use when auditing or reviewing skill quality — batch checks across a library, deep per-skill grep methodology, usage stats, efficacy testing, or fix planning. Single consolidated home for the writing-for-agents review framework and the 3-surface review methodology."
license: MIT
metadata:
  version: 1.0.0
  author: moonlight-lupin
  hermes:
    tags: [skills, review, audit, quality, batch]
    related_skills: [hermes-agent-skill-authoring, skill-curation, plan]
---

# Skill Quality Review

Audit SKILL.md quality across a set of skills. Identifies the most-used skills, classifies them as self-developed vs builtin, then runs batch writing-for-agents checks and fixes.

The review framework blends Matt Pocock's `writing-for-agents` (context pointers, two loads, information hierarchy, completion criteria, leading words, pruning) with `hermes-agent-skill-authoring` peer-matched structure and cross-reference parity. See `references/writing-for-agents-framework.md` for the full lever set.

`references/skill-review-methodology.md` lives HERE in this skill — it covers per-skill grep-based review (3-sources-of-truth drift, pricing registry, guardrail asymmetry). This skill covers **batch automated checks**, the **deep per-skill methodology**, and **usage-based prioritisation** across all skills in a repo or local library. Authoring-time mechanical sweeps (TOC, nesting, orphans) run via `hermes-agent-skill-authoring/scripts/audit_references.py`; deep methodology below.

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

### 0. Identify most-used skills (usage frequency)

When reviewing a local Hermes skill library (not a remote repo), query `state.db` for actual `skill_view` load counts. This is more reliable than `.usage.json` (which may be missing or stale).

```python
import sqlite3, json
from collections import Counter
from pathlib import Path

db = str(Path.home() / ".hermes" / "state.db")
conn = sqlite3.connect(db)
cursor = conn.cursor()
cursor.execute("SELECT tool_calls FROM messages WHERE tool_calls LIKE '%skill_view%'")
skill_counter = Counter()
for row in cursor.fetchall():
    calls = json.loads(row[0]) if row[0] else []
    if not isinstance(calls, list): calls = [calls]
    for call in calls:
        func = call.get("function", call)
        if func.get("name") != "skill_view": continue
        args = json.loads(func.get("arguments", "{}"))
        name = args.get("name", "")
        if name: skill_counter[name] += 1
# Top N
for i, (skill, count) in enumerate(skill_counter.most_common(15), 1):
    print(f"{i:2d}. {skill:45s} {count:3d} loads")
```

### 0a. Classify self-developed vs builtin

Compare the user skills directory against the Hermes installation's bundled skills:

```python
from pathlib import Path
builtin_root = Path("/usr/local/lib/hermes-agent/skills")
builtin_names = {p.parent.name for p in builtin_root.rglob("SKILL.md")}
user_root = Path.home() / ".hermes" / "skills"
for skill in top_skills:
    is_builtin = skill in builtin_names
    # Check frontmatter author field for confirmation
    ...
```

Skills with `author: Hermes Agent` or `author: Hermes Agent + Teknium` in frontmatter but NOT in the builtin tree are user-created overrides (still self-developed). Skills in the builtin tree are bundled. Everything else is self-developed.

### 1. Clone (if remote) and discover skills

```python
import pathlib
repo = pathlib.Path("<repo-root>")
skills = sorted(repo.rglob("SKILL.md"))
print(f"Total: {len(skills)} skills")
```

### 2. Run all checks via execute_code

Run the 9 automated checks from `references/batch-checks.md`. Each produces a structured report. Collect findings into MAJOR / MINOR / NIT severity buckets.

### 3. Present findings

Format as a table: finding, severity, skills affected. Include the key metrics (description char counts, trigger ratios, identity phrases leaked).

### 4. Plan fixes

Use the `plan` skill to write an actionable plan to `.hermes/plans/`. One task per finding. Include exact patch old/new strings for each fix. For bulk fixes (34+ files), include a script-based approach.

### 5. Execute

- Task 1 first (touches all files — e.g. frontmatter standardisation)
- Then remaining tasks in parallel (different files/sections)
- Verify after each task: re-run the relevant check + repo tests
- Commit after each task

### 6. Final verification

Re-run all 9 checks. Confirm all findings resolved. Run repo tests.

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

After a quality refactor, structural checks prove the file is better-shaped; they do not prove the agent behaves better. When the user asks for efficacy evidence, run a controlled A/B: reconstruct the before-arm byte-exactly, probe both arms with identical scenarios on fresh subagents, score against a fixed rubric. Full procedure, controlled-variable rules, and dispatch pitfalls: see `references/efficacy-ab-test.md` (rubric starter: `templates/efficacy-rubric-template.md`). When the question is "was the skill worth having at all" rather than "did v2 beat v1", use the Quick used-vs-no-skill variant at the end of that reference — it drops the byte-exact before-arm and scores quality, time, and tokens.

### 9. Reference-hygiene sweep (mechanical, whole-tree)

Single source of truth: `hermes-agent-skill-authoring/scripts/audit_references.py` (canonical checker; this skill holds no fork). The bulk TOC fixer `add_toc.py` lives in this skill's `scripts/` — dry-run by default, `--apply` to write; generates Contents lists from the file's own structure (## first, then ###, then bold-label bullets; code-fence aware), capped at 60 entries so label-dump files are skipped rather than doubled; writes exactly one trailing newline.

Sequence: audit (authoring's checker) → dry-run review → `add_toc.py --apply` → re-audit. Expect `no-contents-list` to drop to deliberate exceptions only. Fix any `nested`/`orphan-reference` findings by editing SKILL.md pointers, preserving frontmatter.
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

Applies to `~/.hermes/skills/` — the batch checks in this skill's workflow remain authoritative here. Key differences from the repo profile:

- **Descriptions up to 1024 chars and MUST be trigger-style ("Use when ...")** — Hermes BM25 retrieval has no stemming ("onboard" does not match "onboarding"), so capability nouns AND trigger words as literal surface forms are load-bearing. The repo's skills-ref CI enforces the 1024 ceiling on publish.
- **Size**: 8-15k chars target, >20k split to references/.
- **Structure**: When to Use + actionable body + Common Pitfalls + Verification Checklist minimum.
- **Audit mode**: authoring-time mechanical sweeps (TOC coverage, one-level-deep linkage, orphans) run via `hermes-agent-skill-authoring/scripts/audit_references.py`; the deep per-skill methodology is this skill's `references/skill-review-methodology.md`.

## Check summary

| # | Check | Severity if found |
|---|---|---|
| 1 | Frontmatter validation (adapt fields to format — see `references/claude-plugin-review.md`) | MAJOR |
| 2 | Description identity leakage (intent-first, deterministic, local engine, etc.) | MAJOR |
| 3 | Trigger ratio (< 25% = low, < 30% = borderline) | MINOR |
| 4 | Completion criteria (steps without "Done when") | MINOR |
| 5 | Structure gaps (adapt expected sections to format — Hermes vs Claude plugin) | MINOR |
| 6 | Name mismatch (dir name != frontmatter name) | MINOR |
| 7 | Boilerplate duplication (identical sections across many skills) | NIT |
| 8 | Cross-sibling consistency (British English, date format, license type — read license from plugin.json for Claude plugins) | NIT |
| 9 | No-op prose ("be careful", "be thorough", "best practices") | NIT |

Full check code and fix patterns: see `references/batch-checks.md`.
Claude plugin format adaptations: see `references/claude-plugin-review.md`.
Writing-for-agents review framework (context pointers, two loads, hierarchy, leading words, pruning): see `references/writing-for-agents-framework.md`.
Recurring failure patterns from real reviews (with grep checks and fix patterns): see `references/recurring-failure-patterns.md`.
Domain-specific passive-voice false positives (accounting, legal, medical): see `references/domain-passive-voice.md`.
Building product skills alongside an existing reference toolkit: see `references/independent-skills.md`.
Deep per-skill grep review methodology (3-sources-of-truth drift, pricing registry, guardrail asymmetry): see `references/skill-review-methodology.md`.

## Fix priority

1. **Frontmatter** — version/author/license/metadata missing (MAJOR, all files)
2. **Description identity leakage** — cut identity, keep triggers (MAJOR, per-skill)
3. **## Files missing** — add section (MINOR, per-skill)
4. **Completion criteria** — add "Done when" to steps (MINOR, per-skill)
5. **Name mismatch** — align frontmatter name with directory (MINOR, per-skill)
6. **## Common Pitfalls** — add section (optional, per-skill)

## Bulk fix technique

For fixes that touch all skills (frontmatter, name fixes), use `execute_code` with a Python script that patches all files in one pass. For targeted fixes (description trimming, ## Files addition), use the `patch` tool per file.

See `references/batch-checks.md` for the script template.

## Common Pitfalls

1. **Protected skills block writes.** Bundled skills (shipped with Hermes) cannot be patched via `skill_manage`. If the skill you want to update is bundled, say so and recommend `hermes curator adopt <name>`.

2. **Hermes vs Claude plugin format false-positives.** Running Hermes-format checks (expecting `version`/`author`/`license`/`metadata` in frontmatter, `## Overview`/`## Common Pitfalls` in structure) against a Claude Code plugin will flag every skill as broken. Always detect the format first (check for `.claude-plugin/plugin.json`) and adapt checks 1, 5, and 8. See `references/claude-plugin-review.md` for the adaptation table.

3. **Tests may reference SKILL.md content.** Before patching, check if any test files read SKILL.md (grep for `SKILL.md` in test directories). The `test_recipes.py` pattern in fpa-toolkit reads the body but not frontmatter — safe to edit frontmatter.

4. **Name change may break code references.** Before changing a frontmatter `name:` field, grep for the old name in all `.py`, `.md`, `.json` files. If code references the old name, update those too.

5. **Description trimming changes invocation behaviour.** Preserve all quoted trigger phrases and NOT-for disambiguators. Only cut identity/behavioral content. Verify trigger ratio >= 30% after trimming.

6. **Parallel subagent write conflicts.** When dispatching `delegate_task` subagents to fix skills in parallel, and you are also patching skills directly, both writers may target the same file. The `patch` tool will warn: "modified by sibling subagent but this agent never read it." Always re-read a file before patching if a subagent may have touched it. Alternatively, partition work so subagents and the orchestrator never touch the same files.

7. **Router skills skew consistency ratios.** Skills like `workflow-recipes` or `getting-started` are pure routers — they don't produce deliverables, carry trigger phrases, or reference house-style. Exclude them from trigger-coverage and house-style-consistency denominators. See `references/claude-plugin-review.md` § "Router/reference skills are exempt".

8. **Namespace-prefixed frontmatter names.** Claude plugins with multiple skill families (e.g. fpa-toolkit with `fpa-balance-sheet` in dir `balance-sheet/`) use a prefix to prevent cross-plugin collisions. This is intentional — do not flag as a name mismatch. Only flag when neither name is a prefix of the other.

9. **Rebase needed if remote has advanced.** Always `git fetch` + check for new commits before pushing. Rebase local commits on top.

10. **Usage frequency from state.db, not .usage.json.** When identifying most-used skills, query `state.db` `messages.tool_calls` for `skill_view` call counts. The `.usage.json` file may not exist or may be stale. The state.db query gives actual load counts across all sessions. See Step 0 in the Workflow section.

11. **Self-developed vs builtin classification.** Compare `~/.hermes/skills/` against `/usr/local/lib/hermes-agent/skills/` (the Hermes installation path). Skills in the builtin tree are bundled. Skills with `author: Hermes Agent` in frontmatter but NOT in the builtin tree are user-created overrides — still self-developed. Everything else with `author: MH` or `author: moonlight-lupin` is self-developed. See Step 0a in the Workflow section.

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

17. **Bulk text writers must end files with exactly one trailing newline.** A missing final newline makes git report the last line as deleted plus re-added: the commit diff reads as content loss and costs a false investigation before push. Write `"\n".join(lines) + "\n"`.

## Verification Checklist

- [ ] All SKILL.md files discovered (count matches expected)
- [ ] Usage frequency queried from state.db (if local library review)
- [ ] Skills classified as self-developed vs builtin (if local library review)
- [ ] All 9 checks run and findings collected
- [ ] Findings classified MAJOR / MINOR / NIT
- [ ] Plan written to `.hermes/plans/` with exact patch strings
- [ ] Each task verified: relevant check re-run + repo tests pass
- [ ] Each task committed with descriptive message
- [ ] Final verification: all 9 checks pass
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