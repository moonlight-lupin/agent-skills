# Reviewing Claude Code Plugin Skills

Claude Code plugins (standalone repos with `.claude-plugin/plugin.json`) use a different skill format from Hermes in-repo skills. When the pre-flight check detects `.claude-plugin/plugin.json` at the repo root, adapt the batch checks as follows.

## Contents

- Frontmatter — Check 1 adaptation
- Structure — Check 5 adaptation
- Cross-sibling — Check 8 adaptation
- Cross-sibling consistency — what to check
- Script-quality checks (format-agnostic)
- Test suite
- Repo-level metadata checks
- Hooks quality (if present)
- Frontmatter parsing — correct approach
- Size refactoring — progressive disclosure for oversized skills

## Frontmatter — Check 1 adaptation

Claude plugin frontmatter requires only `name` + `description`. Do **not** flag missing `version`, `author`, `license`, or `metadata.hermes` — those are Hermes conventions, not Claude's.

```python
# Detect format
is_claude_plugin = (repo / ".claude-plugin" / "plugin.json").exists()

# Required fields by format
required = ['name', 'description'] if is_claude_plugin else \
          ['name', 'description', 'version', 'author', 'license', 'metadata']
```

Validate:
- `name` — may carry a namespace prefix (e.g. `fpa-balance-sheet` in dir `balance-sheet/`) that differs from the directory name. This is **intentional namespacing** to prevent collisions when multiple plugins are installed — do NOT flag it as a mismatch. Only flag a real mismatch when neither is a prefix of the other.
- `description` is a single-line string ≤ 1024 chars (enforced by Claude's build tool)
- `description` carries trigger phrases — look for `Triggers:` or `Use when` (Claude skills often use `Triggers:` inline)

**Router/reference skills are exempt from trigger and house-style checks.** Skills like `workflow-recipes`, `getting-started`, or any router that only routes to other skills (no deliverable output) don't carry `Triggers:` phrases or house-style references. Count them out of the denominator when computing trigger coverage and house-style consistency ratios.

## Structure — Check 5 adaptation

Claude plugin skills use `## What this skill is for` instead of `## Overview`, and `## Workflow` or `## How to use` instead of `## When to Use`. Do not flag these as missing.

```python
if is_claude_plugin:
    expected_sections = ['## What this skill is for']  # minimum
    # ## Workflow / ## How to use — most skills have one, but router/reference skills may not
else:
    expected_sections = ['## Overview', '## When to Use', '## Common Pitfalls', '## Verification Checklist']
```

## Cross-sibling — Check 8 adaptation

Claude plugins carry license in `.claude-plugin/plugin.json`, not per-skill frontmatter. Read the plugin manifest for license type instead of grepping skill text.

## Cross-sibling consistency — what to check

Claude plugin skills in the same repo share conventions. Grep across all `skills/*/SKILL.md`:
- House-style reference (e.g. `house-style.md`) — should be consistent across skills that produce deliverables (router/reference skills are exempt)
- Trigger phrase convention (`Triggers:` vs `Use when`) — should be consistent
- Evidence/labelling system — if the repo enforces labels (VERIFIED/SOURCED/REASONED/ESTIMATED), check all deliverable-producing skills reference it

## Script-quality checks (format-agnostic)

These apply regardless of skill format:
- `python3 -m py_compile` on all `skills/*/scripts/*.py`
- `grep -rln 'import requests\|import urllib\|import httpx' skills/*/scripts/*.py` — network call audit
- `grep -rn 'except:' skills/*/scripts/*.py` — bare except check
- `grep -rln 'sk-|api_key.*=.*"[a-zA-Z0-9]\{20,\}' skills/*/scripts/*.py` — hardcoded secrets
- `grep -rn 'reconfigure.*utf-8' skills/*/scripts/*.py` — encoding fix presence
- `grep -rn 'sys.exit\|SystemExit' skills/*/scripts/*.py` — CLI dispatch pattern

## Test suite

Run `python -m pytest tests -q --tb=line` from the repo root. Note:
- Environment-specific failures (missing Chromium, missing LibreOffice, missing optional deps) are not code defects — the test is designed correctly, the environment just lacks the dependency
- Skipped tests for optional packages (Pillow, cairosvg, pywin32) are expected and indicate graceful degradation working as designed
- Compare the actual test count against any claims in README/TRUST.md

## Repo-level metadata checks

- `plugin.json` version vs README vs TRUST.md — all should agree
- README skill count vs `ls -d skills/*/ | wc -l` — should match
- README test count vs `python -m pytest --collect-only -q` — should match
- Agent references in recipes/agents → all should resolve to real files
- Cross-referenced skill names in SKILL.md bodies → all should resolve to real `skills/` directories

## Hooks quality (if present)

Claude plugin Stop hooks should be:
- Non-blocking (always exit 0)
- Bounded (cap files scanned per stop, time window)
- Graceful (honest SKIPPED when dependencies absent, never false pass)
- Opt-out via env vars
- Self-locating (try multiple paths for portability)

## Frontmatter parsing — correct approach

When validating frontmatter programmatically, parse line-by-line for the closing `---` rather than using a regex on `content[3:]` — the regex approach can misfire on frontmatter that contains `---` in a description string:

```python
lines = content.split('\n')
closing_line = None
for i, line in enumerate(lines[1:], 1):
    if line.strip() == '---':
        closing_line = i
        break
if closing_line is None:
    # malformed — no closing delimiter
fm_text = '\n'.join(lines[1:closing_line])
fm = yaml.safe_load(fm_text)
```

## Size refactoring — progressive disclosure for oversized skills

When a SKILL.md exceeds the 15k target (but is under the 100k hard limit), refactor by progressive disclosure rather than cutting content:

1. **Identify extractable blocks** — sections that are feature catalogues, mode encyclopedias, or deal-type-specific sub-procedures. These are loaded on-demand, not needed on every run.
2. **Move to `references/<topic>.md`** — create a new reference file with the full detail, organised under `##` headings that the SKILL.md pointers can target by section.
3. **Replace with a compact dispatch** — in SKILL.md, replace the block with either:
   - A **dispatch table** (for mode/option selections): `| Mode | When | Reference |` — one row per option, each pointing to the reference file or section.
   - A **one-line pointer** (for sub-procedures): "Read `references/specialised-builds.md` § Commercial for the full procedure."
4. **Update the Reference files list** — add the new reference file to the `## Reference files` section at the bottom of SKILL.md so future agents know it exists.
5. **Verify** — run the test suite after refactoring. Tests should be unaffected (they test scripts, not SKILL.md prose), but recipe-resolution tests may catch broken cross-references.

**Concrete examples from pere-toolkit (v0.9.9):**
- `underwrite-build` 18k → 11k: extracted engine feature catalogue to existing `references/monthly-model-architecture.md`; extracted sub-steps 3a/3b/4a to new `references/specialised-builds.md`.
- `valuation-report-review` 20k → 15k: extracted 6-mode dispatch to new `references/mode-dispatch.md`; trimmed Phase 2/3 commentary in-place (kept procedure, tightened "why this matters" prose).