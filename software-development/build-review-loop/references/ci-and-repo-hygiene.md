# CI and Repository Hygiene Pitfalls

Learned from a sixth-pass review (Aug 2026). Three findings, all reproduced.

## R3: CI Only Runs on Master — Feature Branches Are Blind

### The Problem

The CI workflow only triggers on `push: branches: [master]`. All development happens on feature branches. Sixteen phases of work landed on a branch that CI never evaluated. Two shipped defects (migration 055 data loss, missing l10n file) would have been caught by the existing test suite if CI had run on the branch.

### The Fix

One line of YAML:

```yaml
on:
  push:
    branches: ['**']    # was: branches: [master]
  pull_request:
    branches: [master]
```

This runs CI on every push to every branch. The cost is negligible (a few minutes of CI per push). The benefit is that defects are caught at push time, not at merge time — and not in a customer's books.

### General Rule

CI should run on every branch where work happens. If development happens on feature branches, CI must trigger on `branches: ['**']`, not just `master`. A CI pipeline that only watches the merge target is a post-hoc validator, not a guardrail.

## R2: Unanchored .gitignore Rules Eat Source Assets

### The Problem

A `.gitignore` rule like `data/` (unanchored) matches any directory named `data` at any depth in the tree. The rule was intended to keep runtime entity databases (`data/` as the default runtime data directory) out of the repo. But it also swallowed `core_toolset/data/l10n_registry.json` — a source asset one directory up from the whitelisted path.

The negation `!core_toolset/modules/**/data/` only covered the modules path. The source asset at `core_toolset/data/` was never tracked.

### The Fix

Anchor the rule to the repo root, and add a matching negation:

```gitignore
/data/           # was: data/ (unanchored)
/data_*/
!core_toolset/modules/**/data/
!core_toolset/modules/**/data/**
!core_toolset/data/       # NEW: whitelist source assets
!core_toolset/data/**     # NEW: whitelist contents
```

### Detection

```bash
git ls-files core_toolset/data/    # empty → file not tracked
git log --all -- core_toolset/data/  # empty → never committed
```

If a test file fails with `FileNotFoundError` on a data file that exists locally but is missing on CI or fresh clone, check `.gitignore` first.

### General Rule

Always anchor `.gitignore` rules that are meant to exclude top-level runtime directories. Use `/data/` not `data/`. After adding any new source asset under a path that shares a name with an ignored directory, verify it's tracked with `git ls-files`. Sweep for other swallowed assets after fixing the rule.

## R1: Migration Data Loss — See sqlite-migration-pitfalls.md

The full migration 055 data-loss story is in `references/sqlite-migration-pitfalls.md`. The key lesson for CI: fresh-DB tests cannot catch upgrade-path data loss. Write upgrade-path tests that seed real data before migration and verify row counts after. See `references/upgrade-path-test-pattern.md`.

## Git/CI principles distilled from past projects (2026-10-16)

- **Anchor .gitignore patterns.** An unanchored directory pattern (e.g. a bare `data/`) swallows package data directories anywhere in the tree: the file exists locally, is never committed, and everything fails on a fresh clone. Anchor directory patterns to the intended level, add negations for package data, and verify with a clean-clone run.
- **CI must trigger on the branches where development happens.** A push trigger limited to the default branch means CI never runs on the feature branch where the work lands — both repo-hygiene and behavior bugs ship untested. Set the push trigger to all branches (or at least the development pattern in use); default-branch-only triggers are for release tags only.
