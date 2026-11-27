# CLI and environment mechanics

Read before dispatching a build or review, opening a PR, or diagnosing a CI miss. Timing, turn caps, gh failures, and pre-existing CI pins live here.

## Contents

- Pitfall rules
- gh PR creation failing
- Pre-existing CI failures in multiple locations
- `delegate_task` subagent review is a viable Opus alternative
- Opus 5.5 high takes 5–8 minutes
- Claude Code print-mode turn exhaustion
- Opus multi-file review: name exactly which files to read, demand immediate write, use --max-turns 25
- Parallel dispatch: Codex review + Cursor build for different files

## Pitfall rules

### gh PR creation failing

4. **gh PR creation failing** — fine-grained PATs may lack
   `repository.defaultBranchRef` scope. Don't retry endlessly — tell the user
   to create the PR from GitHub UI.

### Pre-existing CI failures in multiple locations

6. **Pre-existing CI failures in multiple locations** — a version-pin test
   can fail in both the test file (`tests/test_api.py`) AND the CI workflow
   YAML (`.github/workflows/ci.yml`) with hardcoded regex patterns. When
   fixing a pre-existing CI failure, `grep -rn "<old-version>" tests/
   .github/` to find ALL hardcoded references. A single fix in the test
   file won't make CI green if the workflow YAML has its own inline Python
   check with the same hardcoded pattern. A fastmcp version-pin incident is
   the canonical example.

### `delegate_task` subagent review is a viable Opus alternative

10. **`delegate_task` subagent review is a viable Opus alternative** — when
    the Cursor CLI is unavailable or the diff includes untracked new files
    that `git diff` misses, use `delegate_task` with an `output_schema` to
    dispatch a subagent review. The subagent can read the actual codebase on
    disk (not just the diff), cross-check the diff against the working tree,
    and find issues the diff alone misses. In one semantic-cache subagent
    review session, the subagent noticed the on-disk code had already diverged from
    the diff (a pre-emptive ACL fix) and correctly flagged the diff version
    as BLOCKING while confirming the working tree was safe. Pass enough
    context in the `goal` field — architecture facts, security boundaries,
    the specific review focus areas — because the subagent starts with zero
    conversation context. Write findings to a file AND return them via
    `output_schema` so you get structured results even if the file write fails.

### Opus 5.5 high takes 5–8 minutes

13. **Opus 5.5 high takes 5–8 minutes** — the `claude-opus-5-5-high`
    model is thorough but slow. Don't panic at the wait or kill the process
    prematurely. Set `notify_on_complete=true` and continue other work (e.g.
    fixing findings from the Codex review that already completed) while
    waiting. If the user asks for a specific model and you dispatch the wrong
    one (e.g. `claude-opus-5-medium` instead of `claude-opus-5-5-high`),
    kill the process and relaunch with the correct model — the user will
    notice the model name in the output.

### Claude Code print-mode turn exhaustion

14. **Claude Code print-mode turn exhaustion** — Opus 5 in `claude -p` mode
    always tries to use tools (Read, Bash) on turn 1, even when the diff is
    piped via stdin and `--allowedTools ""` is set. With `--max-turns N`,
    it exhausts N turns reading files and exits with "Reached max turns"
    without producing any review text. Symptom: exit code 1, output file
    contains only "Error: Reached max turns (N)". This happens because
    Opus 5's default behavior is to explore the codebase before answering —
    it doesn't realize the content is already in its context via stdin.
    **Fix**: (a) set `--max-turns 1` so it can't loop, (b) set
    `--allowedTools ""` to block tool access, (c) include in the prompt:
    "Do NOT use any tools. The entire diff is provided below in this prompt.
    Just read it and write your review directly as text output.", (d) use
    `--effort medium` not `high` (high makes the exploration instinct
    stronger). With `--max-turns 1` and `--allowedTools ""`, the model has
    no choice but to answer from context. Cost: ~$0.63 for a 1671-line
    diff (5 commits). Do NOT use `--bare` mode — it breaks OAuth auth
    ("Not logged in · Please run /login"). Claude Code CAN run as root;
    OAuth auth works fine via `claude auth status`.

### Opus multi-file review: name exactly which files to read, demand immediate write, use --max-turns 25

20. **Opus multi-file review: name exactly which files to read, demand immediate write, use --max-turns 25** — when reviewing a multi-file diff with Claude Code (`claude -p --model opus`), Opus tries to explore the entire codebase and exhausts `--max-turns` without writing output. The working pattern for multi-file reviews:
    ```bash
    claude -p "$(cat /tmp/opus-review-prompt.md)" \
      --model opus --allowedTools "Read,Write,Bash" --max-turns 25
    ```
    The prompt MUST:
    - Name exactly which files to read (e.g. "Read ONLY these 4 files: state_store.py, webhook_security.py, ...")
    - Demand immediate write: "Write your review IMMEDIATELY to /tmp/opus-review-phaseN.md"
    - Specify the output format (Verdict, BLOCKING, MAJOR, MINOR, Summary)
    - Cap files to read (e.g. "Do NOT read more than 5 files")
    **Use `--max-turns 25`, not 10.** Opus reads 1 file per turn (each Read call = 1 turn). With 4 files to review, that's 4 turns for reading + 1 for git diff + 1 for pytest = 6 turns before it can write. `--max-turns 10` was too low for any multi-file review — Opus hit the limit every time without writing output. 25 is the minimum for multi-file reviews. This was proven across a multi-phase build (2026-08-14/15): with max-turns 10, Opus failed 3/5 reviews (exhausted turns, no output file written). With max-turns 25, Opus succeeded 100% and produced detailed reviews (10-19K chars each).

### Parallel dispatch: Codex review + Cursor build for different files

21. **Parallel dispatch: Codex review + Cursor build for different files** — when Loop 1 review (Codex) and Loop 2 build (Cursor) touch different source files, dispatch both simultaneously. Codex reviews the Loop 1 diff (already committed) while Cursor builds Loop 2 (new files). This saves 3-5 minutes per phase. Verify file non-overlap before dispatching — if both touch the same file, serialize instead.
