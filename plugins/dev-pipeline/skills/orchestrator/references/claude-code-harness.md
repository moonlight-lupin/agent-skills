# Claude Code as the coding harness

Applies when `harness.coding = "claude-code"` (or `auto` with `claude` on
PATH). The controller stops writing code, briefs and tests. The architect,
the test-writer and the coder are blind `claude -p` dispatches. The controller
keeps dispatch, verification, research and commits. Lanes, providers and
models come from the lanes config (`orchestrator/config/lanes.default.toml` + a machine override). This file gives the rules for using them.

## Who does what

| Controller (Hermes, or the Claude Code main session) | Blind role dispatches (`lanes.py run`) |
|---|---|
| classifies S/R, opens rounds in `review_budget.py` (the single writer of `budget.json`) | `architect`: writes the brief, then the controller stamps it |
| web research and every non-coding tool | `test_writer`: writes the RED tests named in the brief |
| runs `lanes.py resolve` before each round and owns the ledger | `coder`: implements the brief and turns the tests GREEN |
| runs the gate suite itself, and reproduces every finding before a fix round | `reviewer` lanes with `dispatch = runner`: run inside the round |
| runs the `dispatch = controller` reviewers during verification | |
| commits. No role ever commits | |

There is no LLM "round runner" between the two columns. The controller runs
the sequence below with one `lanes.py run` per step. That keeps the same
split with one less token-burning layer, and nothing between the controller
and the roles that can fail on its own.

## Round sequence

```
resolve  →  [research, when an external fact is open]  →  architect  →  stamp brief
        →  test_writer  →  controller checks the tests are RED  →  coder
        →  runner reviewers  →  controller verification (gate suite, controller reviewers)
        →  review_budget finding/close  →  commit or the next round
```

1. `lanes.py --repo <repo> resolve --tier <T> [--gate] --ledger <run>/lanes.jsonl --round <id>`.
   - Add `--usage`, `--failed` and `--rate-limited` from what the controller knows.
   - ASK-USER stops here and goes to the user. NO-LANE means fix the machine config.
2. **External facts are the controller's job.** If the work needs a fact from
   outside the workspace (an API shape, a register map, a vendor doc), the
   controller researches it and writes it into the brief inputs before the
   round. A round with an open external-fact dependency is **NOT-STARTED**,
   never started on a guess. Roles have no web tools.
3. Architect: `lanes.py run --role architect --prompt-file <run>/architect-input.md --cwd <repo> --add-dir <run>/briefs`.
   - It writes the brief to `<run>/briefs/`, outside the repo.
   - The controller stamps it (`briefs/scripts/stamp_brief.py`) before anyone acts on it.
4. Test-writer: `--role test_writer --prompt-file <stamped test brief>`. It
   writes the tests in the repo. The controller runs them and confirms they're
   RED for the right reason (`test-evals`).
5. Coder: `--role coder --prompt-file <stamped build brief>`. It gets the
   brief on stdin and the repo as its cwd, and nothing else.
6. Runner reviewers: one `--role reviewer` run per panel seat with `dispatched_by: runner`.
   - Each reads the stamped review brief (`briefs/references/review-briefs.md`).
   - Seats run in parallel. Hold the fix round until every verdict lands.
7. Verification by the controller:
   - Rerun the gate suite independently.
   - Run the `dispatched_by: controller` seats, e.g. Hermes's Opus lane.
   - Reproduce every finding before any fix round.
   - Record verdicts with `review_budget.py`.
8. If a lane errors mid-round, read `rate_limited` in its `lane-run.v1` result.
   Re-resolve with `--failed`/`--rate-limited`, then re-dispatch, or use
   `--reuse-last` for an interrupted round.

The **round report** names, for each role, the lane and model that ran. It
cites any ledger switch rows (reason, new lane, resulting panel), the panel
and who dispatched each seat, and the test results. It never quotes
`total_cost_usd`. That field uses Anthropic list prices and is wrong for any
env-routed provider. Burn comes from the installation's own tracker, if it has one.

## Blinding (hard requirements)

- **One role per dispatch, with no shared session.** Every dispatch passes
  `--no-session-persistence`. With `blinding = "config-dir"`, each role gets
  its own `CLAUDE_CONFIG_DIR` (`<role_root>/<role>`), so auto-memory and
  history can't cross roles. With `no-memory`, auto-memory is off.
- **What each role sees.**
  - The architect's working files stay in `<run>/`, outside the repo.
  - The coder runs with the repo as cwd and no `--add-dir` to `<run>`, and it
    receives only its stamped brief.
  - Nothing the architect read reaches the coder except through the brief.
- **CLI coders are blind by construction.** The brief goes by prompt file and
  no transcript is shared. The architect stays a Claude Code lane even when a
  CLI writes the code.
- **An env-routed lane never falls back to the user's login.**
  - Its dispatch sets the base URL and token from the provider's `auth_env`,
    blanks `ANTHROPIC_API_KEY`, and pins every model alias (main, opus,
    sonnet, haiku, subagent) to the lane's model.
  - When the key is empty it refuses (exit 4).
  - A lane on the Anthropic login (e.g. the controller's Opus reviewer) uses
    `blinding = "no-memory"`, so it keeps the normal login.

## Tool partition

- Every dispatch denies `WebSearch`, `WebFetch`, `curl`, `wget`,
  `git commit`, `git push` and `git reset`. Reviewers also lose `Edit`,
  `Write` and `NotebookEdit`. The lists are `claude_code.disallowed_tools`
  and `reviewer_disallowed_tools` in config.
- CLI lanes carry their own equivalent in their `argv` template (Muse
  `--disable-web-tools`, Codex `--sandbox read-only` for review).
- **A deny list is not a network sandbox.** Bash can still reach the network
  through other programs, such as a Python one-liner. Where the strip must be
  airtight, run the roles inside an OS or network sandbox (Claude Code's
  sandbox with a network allow-list, a container, or a firewall namespace),
  and prove it with probe 3 below.
- A reviewer that needs a vendor doc asks the controller. The controller
  passes the fact back as a review-input line, never as a live web tool in the gate.

## Review gate

- The coder-exclusion rule applies to the actual coder lane of the round,
  after any escalation. `resolve` computes the panel after the ladder.
- The full panel runs once per milestone on the final pre-deploy diff (`--gate`).
- Fix rounds use one strong reviewer on the fix diff only.
- The confirm-round protocol, the budget script and the stop conditions are
  unchanged (`review-commit`).

## Version pin and the single master

- Set `claude_code.version_pin`. Dispatches then set `DISABLE_AUTOUPDATER=1`,
  and `lanes.py doctor` fails when the installed CLI differs.
- One master copy of the plugin: the Hermes plugin directory, or the
  `agent_skills` repo. A Claude Code copy sets `[pin] master_path` (and/or
  `plugin_version`), and `doctor` fails when they drift.
- The plugin also loads in Claude Code directly through
  `.claude-plugin/plugin.json`. The Hermes create-gate hook (`__init__.py`)
  is Hermes-only and does not run there.

## Term map for older references

| Older references say | Under the Claude Code harness |
|---|---|
| `delegate_task` an implementer | `lanes.py run --role coder` with a stamped brief |
| the builder lane | the `coder` role (`resolve` picks the lane) |
| reviewer lane A / B / C | the panel seats from `resolve` |
| Hermes bot profiles (`coder`, `code_reviewer`) | per-role `CLAUDE_CONFIG_DIR` |
| `.hermes/specs`, `.hermes/plans` | unchanged |

## Phase 0 probes (run them before adopting on a real project)

Run them on a contained project and record the results in the trial ledger.

1. **Smoke.** `lanes.py run --role coder` makes a one-file edit with a tool
   loop. Check the file on disk and `exit_code` 0.
2. **Sustained burn.** One contained mini-feature through the full round
   sequence. Record each provider's usage after every round. This decides
   whether to adopt. Set the pass threshold before running.
3. **Translation and partition.**
   - Tool calling survives a multi-turn task.
   - A `WebSearch` attempt fails on permissions, with no silent degradation.
   - A `curl` attempt is denied.
   - A non-curl network attempt (`python -c "import urllib.request; …"`) is
     blocked when an airtight strip is claimed.
4. **Blinding.**
   - Put a unique marker in the architect's input, NOT in the brief.
   - Run architect → coder.
   - Pass: the marker is absent from the coder's output and from its config
     dir, and the coder made no read under `<run>/`.
5. **CLI driving.** A runner reviewer lane (e.g. Codex) reviews a diff with a
   planted bug. The verdict comes back parseable and names the bug.
6. **Version pin.** `doctor` passes with the pin set, and no auto-update occurs during the trial.

## Known caveats on env-routed providers

- Hosted web search and some advanced tool controls degrade through
  Anthropic-compatible endpoints. They are stripped anyway.
- `/effort` and interleaved-thinking display may do nothing. That is cosmetic.
- `total_cost_usd` is wrong for these backends.
- `--fallback-model` can't cross providers, so retries stay on one provider.
  A retry storm during a provider outage is the failure to watch. Escalate
  with `--failed` instead of retrying.
