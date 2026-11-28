---
name: setup-lanes
description: "Use when the user asks to set up or change lane configuration: which lane codes, which lanes review, model pins per lane, or any lanes.default.toml surface — coder configuration and reviewer seats written into validated override files. Triggers: 'set up my lanes', 'set the coder model', 'change my reviewers', 'configure review seats', 'lane setup', 'which lanes do I have'."
metadata:
  version: 1.0.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [setup-lanes, configuration, lanes, coder, reviewers]
    related_skills: [orchestrator, review-commit, build]
---

# Setup Lanes

Configure which model does which job on THIS machine. You carry the
interview judgment; the engine carries validation, merging, writing and
verification. Never hand-edit the override or the defaults yourself.

## The engine

`$HERMES_HOME/plugins/dev-pipeline/skills/orchestrator/scripts/lanes.py` is the
single writer (`setup` subcommand) and the single reader (`detect`,
`resolve`, `doctor`). Its path anchors on `$HERMES_HOME` (the plugin
install), never the working directory. Exit codes are subcommand-scoped:
0 ok; 2 validation refusal; 3 trust-boundary refusal; 4 force required;
5 parse/config error. A landed write is always ok (0): when no coder
lane resolves because the machine lacks the tooling, the write stands
and the JSON carries the notice — the rc never encodes machine state.

Facts first, every time:

1. `doctor` — what is configured, what resolves, which problems exist.
2. `detect` — every lane and whether it can run here (binary present,
   provider key set). A lane that cannot run stays configurable; resolve
   always skips it, so warn and proceed.

## The interview (one pass)

Ask, in one numbered pass, with the detect/doctor facts as context:

1. **Coder lane** — which lane codes. State each lane's `via`, family,
   model and availability. Give the current order from `roles.coder`
   (it is an escalation ladder: first available lane wins).
2. **Reviewer lanes, in order** — which lanes review. Reviewers are
   preference-ordered; the family-mixing rule needs independence, so
   prefer spreading across families.
3. **Model pins per lane** — optional. One model per lane, defaulting to
   the CLI's own default (empty).

Map the answers to ONE engine call. Coder = `roles.coder=<lanes>`;
reviewers = `roles.reviewers=<lanes>`; a model pin = `lanes.<id>.model=<model>`.
Lanes the user did not mention keep their defaults. Then run:

```
python3 "$HERMES_HOME/plugins/dev-pipeline/skills/orchestrator/scripts/lanes.py" \
  setup --quick "roles.coder=<lanes>" --quick "roles.reviewers=<lanes>" \
        --quick "lanes.<id>.model=<model>"
```

## Deep edits (any schema key)

`--set <dotted.key>=<value>` reaches every key the defaults define: the
harness, `claude_code` (blinding, role_root, max_turns, permission_mode,
allowed/disallowed tools), providers, lane `review_argv`/`code_argv`,
`roles`, the usage ladder, `review` seats and dispatch, and `pin`. Lists
are comma-separated (a list replaces the whole list); booleans are
true/false; numbers and strings are as typed. `--unset <key>` removes a
key a previous override added, restoring the defaults-implied value.
Unknown keys are refused with the nearest real candidates — read them,
do not guess paths. Inline tables are addressed deepest
(`--set review.seats.T2=3` ships one key, keeping sibling defaults).

## Write rules

- Machine scope writes the ACTIVE machine override: `$DEV_PIPELINE_LANES`
  if set, else the first of `$HOME/.hermes/dev-pipeline/lanes.toml` and
  `$HOME/.config/dev-pipeline/lanes.toml` that exists (else the first).
  A not-yet-created target is a legal first-time setup.
- List leaves take `KEY=` for the EMPTY list (e.g. `--set roles.goldfish=`).
- `--project --repo <root>` writes `<repo>/.dev-pipeline/lanes.toml` —
  the UNTRUSTED surface. It accepts ONLY per-lane model/effort on lanes
  defined by trusted sources; anything else is refused whole and pointed
  at the machine scope. Never try to smuggle a trusted key through a
  project file.
- An existing override is never clobbered silently: without `--force`
  you get the unified diff (exit 4) — read it to the user, then rerun
  with `--force` only after they agree. `--force` keeps a timestamped
  backup; the two most recent survive. Project backups land inside the
  repo's `.dev-pipeline/` — keep `*.bak-*` out of git there.
- `--check` reports the effective values and the would-be diff and
  writes nothing. Run it to preview, or to show the current state.

## Verification and the report

Every write ends with `doctor` + a `resolve`-tier T2 roundtrip inside one
JSON report. Read back to the user: the written path, the effective
roles table (lane, family, model), the doctor warnings, and the panel it
produces. An unavailable lane warns (it stays listed, resolve skips it);
a compatible provider whose key variable is unset warns. Neither blocks
the write; a `verdict: ASK-USER`/`NO-LANE` in the roundtrip does get
reported plainly.

## Red Flags

- Hand-editing `lanes.toml` or the defaults instead of the engine.
- Writing a machine-scope file from project-scope answers.
- Agreeing to `--force` before showing the diff.
- Setting a reviewer list to one lane from one family while other
  families are available.
- Treating the interview answers as flag values without validating lane
  names against `detect` first.
- Editing `lanes.default.toml` (it ships with the plugin; the override
  system exists exactly so it never needs edits).
