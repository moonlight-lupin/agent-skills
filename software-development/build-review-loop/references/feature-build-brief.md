# Feature Build Brief (new capability, not a fix)

Companion to fix-brief-template.md. Use when dispatching the builder to ADD a
capability against contract tests the orchestrator already wrote and committed
(SKILL.md Step 2b pattern). Field-validated shape for two-builder parallel
dispatch on one repo.

## Structure

```markdown
# BRIEF-N: <capability title>

## Repo / working rules
- Repo path, branch (already checked out).
- Do NOT `git commit` — the orchestrator commits after verification.
- Do NOT modify (exact file list): the orchestrator-written contract test files,
  fixtures, cached schemas. "If the tests contradict this brief, STOP and report
  the contradiction — do not warp production code or weaken tests."
- For parallel dispatch: name the OTHER builder's tree and forbid touching it.

## Task (what to build)
<The target artifact layout, exact CLI surface, field-by-field mapping rules,
validation requirements. Quote the governing spec's section numbers where they
bite. Specify fallback behavior for missing dependencies.>

### Acceptance criteria (numbered, each runnable)
1. `python -m pytest <contract-test-file> -q` — ALL N tests pass.
2. `python -m pytest <existing-suite> -q` — existing tests still pass.
3. (combined run command)
4. `--help` shows the new flag/surface.
5. No-regression check spelled out concretely (what must be byte-equivalent).
6. Dependency policy ("no new pip dependencies" unless approved).

### Verification you must run and report
- The pytest commands with output.
- A manual end-to-end run: exact commands, then show the artifacts
  (`find <out> -type f | sort`, `cat` the key files).

## Integration boundaries changed
| Boundary | Old shape | New shape | Test |
```

## What makes it work
- **Contract tests committed BEFORE the brief is sent** — the brief names the
  test file that encodes the expected behavior and repeats the do-not-modify rule.
- **Acceptance criteria are exact commands, not descriptions** — the builder
  runs them and pastes output; the orchestrator re-runs them independently.
- **Forbidden files are listed by path**, not by description.
- **Parallel dispatch needs three things per brief:** its own directory scope,
  the sibling scope forbidden, and its own log file + terminal session
  (pitfall (parallel dispatches)). Commit in completion order after verifying each independently.
- **A builder that stops to report a contradiction is a success signal**
  (see `review-findings-adjudication.md` — own the fixture fix) — the brief must license that stop explicitly.
- **Map rules field-by-field when the contract is a spec** — name every
  permitted field, its source in the input format, and its transformation
  (string → object, placeholder rewrites, slug constraints). A builder given
  "convert the manifest" guesses; one given the table converts correctly.
