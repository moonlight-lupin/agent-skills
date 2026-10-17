# External Field Briefing → Skill Updates (Aug 2026)

Pattern for when an external party (a deployment operator, a field agent,
another assistant) sends a briefing/report describing findings and suggested
upstream fixes for a repo we maintain.

## What a field briefing looks like

Markdown document, sender runs the software in production, structure:
- **Symptom** — what failed live, with the exact error string
- **Root cause** — their diagnosis, usually verified by live repro
- **Repro** — a concrete failing case AND a succeeding case
- **Suggested upstream fix** — code diff sketch + test-contract list
- **Files touched locally** — so you can diff against their deployment

Treat it as an EXTERNAL REVIEW: valuable findings, but unverified claims.
Both findings this session were accurate, but verify each against current
source anyway (it may be fixed, or misdescribed).

## Workflow (validated Aug 2026, a connector field briefing)

1. **Verify repo state before anything**: `git status --short` (uncommitted
   work present?), recent log, `git fetch origin`, and — for a plugin with a
   local installation — `diff -q` the dev repo's key files against
   `~/.hermes/plugins/<name>/` so you know the sync baseline.
2. **Verify each finding in current source** — read the actual function
   before writing anything. Check the existing tests that touch it: the
   briefing will often name tests to extend (its "test contract").
3. **Write the red contract tests first** (orchestrator-authored, per
   build-review-loop Step 2b). Extend the EXISTING test functions the
   briefing names rather than creating a parallel new test file — the
   briefing's suggested fix becomes the tightened assertion.
4. **Run and confirm honest RED** — assertions fail on the missing change,
   not harness errors.
5. **Commit the red tests alone** — clean diff boundary for the reviewer.
6. **Brief the builder** with the field briefing's fix sketches, the
   do-not-touch test list, and the real suite baseline.
7. Normal build-review-loop: Cursor build → independent verify → commit →
   Codex review → fix round → re-review → push → CI → update local install.

## Pitfalls specific to this pattern

- **Scope gaps are the norm, not the exception.** A briefing written on
  ANOTHER deployment references artifacts that do not exist in your repo.
  This session: `skills.local/` overlay and a deployment-side
  `executive-briefing` skill — neither exists here. Verify each referenced
  path; scope the missing ones out in the delivery message rather than
  asking the user (operator-brain module 4: no permission stop for trivia).
- **Suggested fixes can be dead code even when the diagnosis is right.**
  The briefing's hardening suggestion (a `data_preview` check inside the
  strict-response validator) was implemented by the builder and passed its
  unit test — but Codex caught that the production call path discards
  `data_preview` BEFORE the validator runs, so the error was unreachable.
  The unit test called the validator directly with a shape production never
  produces. Lesson: a fix at the wrong LAYER tests green and does nothing.
  When a fix guards a payload shape, trace the shape from the transport
  boundary to the validator — add an end-to-end test that mocks the FULL
  transport envelope, not a direct validator call.
- **Subprocess tests that assert a missing-credential branch are
  hermeticity hazards.** The CLI auto-loads a plugin-root `.env`; on any
  machine where the real key is set (the normal production state), the test
  silently exercises the WITH-key branch and passes for the wrong reason.
  Fix pattern: copy the config pointing `key_env` at a guaranteed-unset
  name (e.g. `COMPOSIO_TEST_KEY_NOT_SET`), AND scrub the variable from the
  subprocess env (pass a copied `env=` to `subprocess.run`) — enforce
  "unset" rather than assume it. Replace weak assertions like
  `"KEY" in out or "OTHER" not in out` (true for nearly any failure output)
  with the strict refusal-message check.
- **Tighten existing tests rather than adding parallel twins.** First pass
  added `_hermetic` duplicate tests next to the originals; the reviewer
  correctly flagged that the originals kept their live-call risk. Correct
  shape: convert the originals in place, merge the twins.
- **Briefs written by you can drop context the docs had.** This session's
  builder rewrite of `workspace-access.md` dropped a slug-examples
  parenthetical because the brief text omitted it (deliberately shortened,
  but the parenthetical was live information). Re-read the full diff of
  docs changes against the original — restore dropped content that wasn't
  part of the change.

## Session record (for reference)

Field briefing 2026-08-29 (Composio MCP, Google family):
1. `GMAIL_FETCH_EMAILS` data offload → lean `mail_search` args
   (`include_payload=False, verbose=False`), Google branch only.
2. Agent-side read ladder reordered: direct
   `COMPOSIO_MULTI_EXECUTE_TOOL` with `tools_allowlist` slugs first,
   `COMPOSIO_SEARCH_TOOLS` discovery as fallback only.
Commits `fbb0eed` (red tests) → `893a2fe` (fixes) → `0d0de3a` (Codex R1:
reachable offload error + hermetic no-key tests). Suite 2104 → 2107 passed.
