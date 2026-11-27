# Engineering evidence (optional tooling layer)

The native `dev_pipeline_engineering_plan` tool provides fixed, language-specific
check suggestions. It does not execute commands, read repositories, install
packages or bypass the terminal backend. Use it after identifying the project
language; for mixed repositories request each relevant language.

## Workflow

1. Inspect project CI and documented commands. Prefer those over generic defaults.
2. Use the planner to identify gaps: diff hygiene, lint, type checking, static
   security analysis and optional dependency audits. Run relevant checks through
   the existing terminal backend from the approved repository root.
3. For navigation use installed ast-grep with a targeted pattern and language;
   use native Hermes LSP diagnostics where configured. Neither replaces tests.
4. Capture command, working directory, exit code, relevant output and commit
   SHA (and note dirty/untracked state) in the existing progress ledger or
   review report. Mark each check PASS, FINDINGS, ERROR, UNAVAILABLE or NOT RUN.
   Do not present planner output as executed evidence.
5. Run required acceptance tests and rerun affected checks after fixes.
   A required project check that fails or cannot run is not a pass; report
   the blocker under the existing review policy. Do not silently waive it.
6. Dependency audits are opt-in because they can contact external registries.
   Go/Rust tools may also fetch dependencies; use the terminal's network
   controls for offline work. Never auto-install packages or run untrusted
   repository configurations outside approved isolation.

## Prerequisites

Install only the tools relevant to a project, under operator control:
ruff, mypy, bandit, pip-audit, project-local ESLint/TypeScript,
Go, Cargo/Clippy, and ast-grep. The plugin does not bundle their binaries
or configure LSP servers or Bubblewrap. Use Hermes' configured terminal
isolation; Git worktrees alone are not sandboxes.

Coverage and mutation testing are project-specific: use existing CI commands
and thresholds, not invented generic thresholds. Keep risk routing, review
budgets and independent reviewer gates unchanged.
