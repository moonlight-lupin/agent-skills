# Review-lane outages + generated-frontmatter findings

Session evidence: a plugin repo with a 2112-test suite (2026-08-29).

## 1. Reviewer-lane outage — substitute across families, never single-reviewer

Failure: `claude -p` (Opus lane) failed twice with `Failed to authenticate:
OAuth session expired and could not be refreshed`. Headless CLI cannot
re-auth; recovery needs a foreground `claude login` — unavailable mid-run.

Working substitute: Cursor lane for review:

```bash
agent -p --trust --model "cursor-grok-4.6-medium" \
  "Review the diff at /tmp/<x>.diff. Also read <untracked files> directly \
from the repo (untracked files are NOT in a git diff). Print findings with \
severity BLOCKING/MAJOR/MINOR/NIT as your final message. Read-only." \
  background=true
```

Rules:
- Substitute from a DIFFERENT model family (Codex+Cursor stayed the lanes;
  do not run two models from the same family and call it diversity).
- Mark in the report which lanes actually ran. "Two-lane review" claimed
  with a dead lane is a false claim.
- Reviewer-down is not a reason to skip review or self-approve.

## 2. New review-finding class: f-string-generated YAML frontmatter

Any code that writes YAML frontmatter by f-string interpolation of user
data has TWO independent failure modes (both reproduced live):

(a) **Unquoted special characters.** Company/user values containing
`:`, `#`, quotes, or newlines produce invalid YAML:
`title: O'Brien & Co: "Trading" #2` → `mapping values are not allowed here`.

(b) **safe_dump default width wrapping.** Routing through
`yaml.safe_dump(...)` fixes (a) but the default `width=80` wraps long
values across lines and appends a `...` document-end marker — the result
is again invalid frontmatter:

```
title: Acme Advisory Pte Ltd Wiki Purpose
...
type: reference        # <- now outside the frontmatter block
```

Correct pattern:

```python
title = yaml.safe_dump(
    f"{name} Wiki Purpose", default_flow_style=False, width=4096, allow_unicode=True
).strip()
```

Review checklist when the diff touches generated-frontmatter code:
- Grep for `return f"""---` / `title: {` interpolation of external values.
- Test matrix: name with `:`, `#`, `"`, `'`, em-dash/unicode — assert
  `split_frontmatter()` returns valid=True for every case, not just that
  the string "looks right".
- For overwrite semantics: test force=False keeps operator-edited seed
  files byte-identical.

## 3. Untracked-reviewable trap

`git diff` does not include untracked files. A reviewer reading only the
diff will report the new entrypoint as "BLOCKING: untracked, would not
ship" (Codex did exactly this — a false finding with a root cause in the
review harness, not the change). Always pass the diff PLUS explicit paths
to new untracked files when commissioning a review.

## 4. CLI contract tests: assert the stable surface

When a command prints "OK: ..." on success and "ERROR: N" only in summary
mode, asserting the mode-specific string breaks; assert exit code + absence
of `[ERROR]` lines instead. Prefer `--summary` in CLI tests when that is
the variant schedulers actually call.
