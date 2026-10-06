# Recurring Failure Patterns — Self-Developed Skill Reviews

Patterns that appeared across multiple independent skills during a review of 6 self-developed Hermes Agent skills (Aug 2026). These are batch-check candidates, not per-skill findings — if one skill has the issue, siblings probably do too.

## Contents

- 1. "Use when" description prefix missing (6/6 skills)
- 2. `metadata.hermes` nesting wrong or missing (3/6 skills)
- 3. Stale version references in prose after upgrades (high-impact)
- 4. Environment-state in descriptions (stale-on-arrival)
- 5. Two-loads mismatch: model-invoked skill that says "don't load per-session"
- 6. Literal duplicate content from copy-paste
- 7. Cross-reference parity: feature defaults inconsistent across 4 sources
- 8. Contradictory "default" labels within a single file
- 9. Build history / changelog sediment (4/12 skills)
- 10. Project README masquerading as skill (2/12 skills)
- 11. Broken pitfall numbering (1/12 skills)
- 12. Description retrieval regression — trading capability nouns for trigger phrasing (3/3 skills, Aug 2026)
- 13. Degrees-of-freedom defects — options with no default, loose tolerances, hidden engine defaults, voodoo constants (Oct 2026)

## 1. "Use when" description prefix missing (6/6 skills)

**Observed:** Every model-invoked description led with identity ("Delegate coding to Cursor CLI", "Manage Docker on the Unraid NAS", "Parse agent log files to identify...") instead of trigger branches.

**Why it matters:** The description is where invocation work happens. Leading with identity means the model reads *what the skill is* before *when to fire it*. The "Use when" convention front-loads the trigger.

**Check:**
```python
desc = fm.get("description", "")
if not desc.strip().startswith("Use when"):
    print(f"  FAIL: description does not start with 'Use when'")
```

**Fix pattern:** Rewrite to `Use when <trigger>. <one-line behavior>.` Push identity into the body.

## 2. `metadata.hermes` nesting wrong or missing (3/6 skills)

**Observed:** Skills either omit `metadata` entirely, put `tags` at the top level (`tags: [...]` instead of `metadata: hermes: tags: [...]`), or nest correctly but omit `related_skills`.

**Check:**
```python
fm = yaml.safe_load(frontmatter)
assert "metadata" in fm, "missing metadata"
assert "hermes" in fm["metadata"], "missing metadata.hermes"
assert "tags" in fm["metadata"]["hermes"], "missing tags"
assert "related_skills" in fm["metadata"]["hermes"], "missing related_skills"
```

**Fix pattern:** Restructure to `metadata:\n  hermes:\n    tags: [...]\n    related_skills: [...]`.

## 3. Stale version references in prose after upgrades (high-impact)

**Observed:** After a model version upgrade (Grok 4.5 → 4.6), the Orchestrate-and-Review section still said "Grok 4.5 High" in prose while the actual commands used `cursor-grok-4.6-high` and the model table listed 4.6.

**Why it matters:** An agent reading the prose may use the old model ID, or become confused about which is current. This is a cross-reference parity failure *within* SKILL.md, not just across files.

**Check:**
```python
# After any version upgrade, grep the old version string:
import subprocess
old_version = "4.5"  # the version being replaced
result = subprocess.run(["grep", "-n", old_version, "SKILL.md"], capture_output=True, text=True)
if result.stdout:
    print(f"  STALE: {old_version} still referenced in SKILL.md")
```

**Fix pattern:** After any version upgrade, `grep` the old version string across the entire SKILL.md and all linked references — not just the section you edited.

## 4. Environment-state in descriptions (stale-on-arrival)

**Observed:** Description included "36+ containers, 35 stacks" — live counts that drift as the environment changes. Another description included a Docker version number.

**Why it matters:** These counts are body content, not invocation triggers. They don't help the model decide *when* to fire the skill, and they become wrong over time.

**Check:**
```python
desc = fm.get("description", "")
# Flag numbers + unit words that suggest live state
import re
state_patterns = re.findall(r'\d+\+?\s+(?:containers|stacks|services|nodes|servers|models|endpoints)', desc)
if state_patterns:
    print(f"  STALE-RISK: environment state in description: {state_patterns}")
```

**Fix pattern:** Remove environment state from descriptions. If needed in the body, date it and mark it as a snapshot.

## 5. Two-loads mismatch: model-invoked skill that says "don't load per-session"

**Observed:** A skill's Adoption Patterns section recommended baking content into SOUL.md and NOT loading the skill per-session, and noted the system prompt already injects the content — but the skill had no `disable-model-invocation: true` flag. The model-invoked description was paying context load for a skill meant to be user-invoked.

**Why it matters:** The skill's own guidance contradicts its invocation mode. Every turn, the description spends tokens for a skill that shouldn't be loaded.

**Check:**
```python
body = content[content.index("---", 3):]  # after frontmatter
anti_load_signals = ["SOUL.md", "don't load", "bake into", "not loading", "already injects"]
has_anti_load = any(s.lower() in body.lower() for s in anti_load_signals)
has_disable = "disable-model-invocation: true" in frontmatter
if has_anti_load and not has_disable:
    print("  TWO-LOADS MISMATCH: body says don't load per-session, but no disable-model-invocation flag")
```

**Fix pattern:** Either set `disable-model-invocation: true` and strip the description to one line, or rewrite the description with real trigger branches so per-session loading is justified.

## 6. Literal duplicate content from copy-paste

**Observed:** Two types — (a) duplicate table rows (a stack list with two identical lines), (b) a pitfall bullet copied verbatim to a second location later in the file.

**Check:**
```python
lines = content.split('\n')
from collections import Counter
dupes = [line for line, count in Counter(lines).items() if count > 1 and line.strip()]
if dupes:
    print(f"  DUPLICATE LINES: {dupes[:5]}")
```

**Fix pattern:** Delete the duplicate occurrence. Keep the first instance.

## 7. Cross-reference parity: feature defaults inconsistent across 4 sources

**Observed:** SKILL.md said "FLUX 3 generates audio by default" (implying the script sends audio=True), but the script's `--audio` was `store_true` (default False) for ALL models including FLUX 3, and the reference file said "generate_audio — default OFF", and the prompting guide said "In falvid.py, audio is off by default". Four sources, three different claims.

**Why it matters:** An agent following SKILL.md would expect FLUX 3 drafts to have audio without passing `--audio`, but they won't. The user gets silent video when they expected sound.

**Check:**
```python
# Grep for "by default" / "default off" / "store_true" across all surfaces:
import subprocess
surfaces = ["SKILL.md", "references/*.md", "scripts/*.py"]
for surface in surfaces:
    result = subprocess.run(["grep", "-n", "-i", "audio.*default\\|default.*audio\\|store_true.*audio\\|audio.*store_true", surface], capture_output=True, text=True)
    if result.stdout:
        print(f"  {surface}: {result.stdout.strip()}")
# Compare: do all surfaces agree?
```

**Fix pattern:** Pick one truth (the script's behavior is authoritative) and align all docs to it. If the script overrides a model's API default, say so explicitly: "FLUX 3 includes native audio at the API level, but `falvid.py` sends `generate_audio=False` by default for all models. Pass `--audio` to enable."

## 8. Contradictory "default" labels within a single file

**Observed:** A model table had `composer-2.5` labeled "General coding (DEFAULT)" and `cursor-grok-4.6-high` labeled "General coding (DEFAULT — user pref)" — two things both claiming to be the default. The routing guide later clarified only Grok 4.6 High was the user's default, making the composer-2.5 label stale sediment.

**Check:**
```python
import re
defaults = re.findall(r'\(DEFAULT[^)]*\)', content)
if len(defaults) > 1:
    # Check if they're for the same task/category
    print(f"  MULTIPLE DEFAULTS: {defaults}")
```

**Fix pattern:** Only one model/option can be the default per task. If the default changed, update the old label to "Fallback" or remove the DEFAULT tag.

## 9. Build history / changelog sediment (4/12 skills)

**Observed (Aug 2026, 12-skill review):** tablina (60 lines of batch history with commit hashes), orion (full bug fix history + per-phase Codex review findings), hermes-post-update (per-patch diagnostic essays), development-workflow (cross-project patterns from Argus/Pythia/Tablina). All carried project history that belongs in reference files or should be deleted.

**Why it matters:** The skill should describe current state, not project evolution. Build history adds dead weight and goes stale immediately. One skill (tablina) even had a pitfall warning against trusting its own build-history section — the skill contradicted itself.

**Check:**
```python
import re
history_patterns = re.findall(r'(?:batch|shipped|commit [0-9a-f]|phase [0-9]|codex review|opus review|PR #)\b', content, re.I)
if len(history_patterns) > 5:
    print(f"  SEDIMENT: {len(history_patterns)} history references — move to references/build-history.md")
```

**Fix pattern:** Move build history, per-phase review findings, and bug fix logs to `references/build-history.md` or delete. Keep only current state: strategy params, CLI commands, architecture, pitfalls. The skill describes what IS, not what happened.

## 10. Project README masquerading as skill (2/12 skills)

**Observed (Aug 2026):** tablina (99,873 chars) and orion (56,759 chars) were project wikis stuffed into SKILL.md — full backtest results, SQL schemas, API endpoint specs, 490-line pitfalls sections. Both had no `## Overview`, no `## When to Use`, no workflow steps. They were structured as project READMEs, not skills.

**Why it matters:** A 100K SKILL.md is 127 chars from the hard limit and 6-12x the recommended range. The agent cannot effectively parse or follow a document that large. The skill provides no operational guidance — just encyclopedic reference.

**Check:**
```python
size = len(content)
has_overview = "## Overview" in content
has_when_to_use = "## When to Use" in content
has_steps = bool(re.search(r'^\d+\.\s', content, re.M))
if size > 20000 and not (has_overview and has_when_to_use):
    print(f"  PROJECT-README-AS-SKILL: {size:,} chars, missing Overview/When-to-Use — needs structural rebuild")
```

**Fix pattern:** Structural rebuild — extract 85%+ into reference files (build-history.md, pitfalls.md, api-and-data-model.md, bug-fix-history.md). Rewrite SKILL.md as a ~15K operational guide with: trigger-focused description, Overview, When to Use, compact quick-reference tables, top-10 pitfalls (pointer to full list), verification checklist. Target: SKILL.md as index + quick reference, not encyclopedia.

## 11. Broken pitfall numbering (1/12 skills)

**Observed:** build-review-loop had two items numbered "8" (duplicate) and skipped from "9" to "11" (missing "10"). Caused by incremental edits without renumbering.

**Check:**
```python
import re
numbers = [int(m) for m in re.findall(r'^(\d+)\.\s+\*\*', content, re.M)]
# Find duplicates and gaps
from collections import Counter
dupes = {n: c for n, c in Counter(numbers).items() if c > 1}
gaps = [n for n in range(1, max(numbers) + 1) if n not in numbers]
if dupes: print(f"  DUPLICATE NUMBERS: {dupes}")
if gaps: print(f"  MISSING NUMBERS: {gaps}")
```

**Fix pattern:** Renumber sequentially. Duplicates and gaps confuse cross-references within the skill.

## 12. Description retrieval regression — trading capability nouns for trigger phrasing (3/3 skills, Aug 2026)

**Observed:** When rewriting descriptions to add "Use when" trigger prefixes, the capability nouns were dropped. Example: "Reclaim disk space on a Linux VM. Surveys every space consumer..." became "Use when disk usage is above 80%...". The BM25 skill-retrieval plugin tokenizer lowercases and splits on non-word characters with no stemming — so "onboard" does not match "onboarding" and "92" does not match "80". A description must carry the literal surface forms of both trigger words (what the user says) AND capability words (what the skill does).

**Measured impact:** 9/14 realistic queries hit after rewrite vs 13/14 with dual-surface-form descriptions. The one remaining miss was zero lexical overlap — adding the literal token "df" to the description closed it.

**Check:**
```python
# Test descriptions against the repo's own BM25 index before shipping:
# 1. Build index over all name:description pairs
# 2. Run realistic user queries
# 3. Verify expected skill ranks in top-K
# The skill-retrieval plugin's tokenize() splits on \W+ with no stemming.
# Descriptions must contain literal surface forms: "df", "80%", "onboarding",
# "context window", "gateway", "dashboard" — not synonyms or stems.
```

**Fix pattern:** Descriptions should carry both halves. Example: "Use when df says disk is above 80% full or the user wants to reclaim storage space on a VM." carries trigger words ("df", "80%", "full") AND capability words ("reclaim", "storage", "space"). The 200-char truncation budget is enough for both — most descriptions are under 120 chars.

**Generalization:** any description rewrite that changes the vocabulary (not just the structure) must be tested against the retrieval index. Structural reformatting (adding "Use when") is safe. Vocabulary changes (replacing "reclaim storage" with "disk usage") are not — they break BM25 matching.

## 13. Degrees-of-freedom defects (5 Oct 2026 pere-toolkit review; 8 findings on 52 skills)

Batch-check Check 14 extension (`references/batch-checks.md` § "Check 14 extension"). Skills whose text offered a choice where the engine required one, or hid a judgement inside a default:

- **Options with no default.** "Same period last year or last quarter" (8 occurrences). Anthropic's rule: one default plus an escape hatch — never a bare "A or B" inside a step.
- **Loose wording on exact steps.** "Aim for a few basis points" where the validator has a 5 bp tolerance; legal-notice dates "inferred"; a provision placed "by hand". If the script enforces a number, the prose must state the same number.
- **Judgement hidden in engine defaults.** `discount_rate=0.08` on a keyword argument the SKILL.md never mentions. For every cited function, inspect its signature; a judgement default must either appear in the skill text or the step must say "pass X and state it".
- **Voodoo constants.** Module-level numeric thresholds with no rationale (`TIERS = 75 / 50`). Fix pattern: a provenance register — a test file that fails until every default number cites its source (pere-toolkit: `tests/test_provenance.py`).

**Check:** for each skill, extract choice-pair phrasing, validator tolerances, and cited-function defaults; compare with the prose. Full check code: `references/batch-checks.md` § Check 14 extension.

**Fix pattern:** state the default in the step, state the tolerance in the step, document judgement defaults, and give every module threshold a rationale or provenance entry.
