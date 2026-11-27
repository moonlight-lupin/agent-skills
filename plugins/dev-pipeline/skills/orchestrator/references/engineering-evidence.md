# Engineering capability management

Native plugin tools are available in supported Hermes runtimes. All command
execution uses the existing terminal dispatch API; the plugin never runs host
subprocesses, overrides terminal or changes backend policy.

## Operator setup (outside the agent)

Configure settings under plugins.entries.dev-pipeline.settings:

- install_allowlist: approved IDs from discovery, default [].
- allow_project_checks: true only in trusted/approved isolated environments.
- allow_network_checks: true only if dependency metadata may be transmitted.
- allow_auth_probes: true for vendor status probes.
- required_checks: project-appropriate IDs from the engineering planner/catalog;
  diff is always required. Set before work begins; do not relax to pass a gate.

Global npm and uv installs run only with the operator allowlist; OS packages,
vendor shell installers, project dependencies and account logins stay manual.
Prefer pinned versions and project lockfiles in production. Installation is
verified by a subsequent version probe; no automatic credential setup.

Bubblewrap on Linux: operator installs bwrap and prlimit, runs
hermes plugins install bubblewrap --enable (or allowlist bubblewrap_plugin
and use dev_pipeline_setup where the active terminal can reach the intended
Hermes profile), sets terminal.backend
to bubblewrap, terminal.degraded_mode to fail and selects an appropriate
workspace/network profile. Run hermes doctor on the host. A config read or
binary discovery does not attest actual isolation. Do not run untrusted
projects if the isolation has not been established. Never silently fall back
to local execution. Git worktrees are not security sandboxes.

## Workflow

1. Use canonical absolute Git root in the active POSIX terminal backend.
   Discover project root markers and installed binaries. Explicitly probe
   versions of up to three tools at a time; use doctor auth only if permitted.
   Presence and version response do not prove authentication, quota, model
   availability, or compatibility. Doctor supports auth probes for Claude,
   Codex and gh only; other vendors remain unknown until a real dispatch.
2. Run existing lanes.py detect/doctor/resolve in the actual coding environment.
   Doctor invokes bundled lanes.py detect in the active backend when
   allow_project_checks is enabled; if the script is hidden, run the existing
   resolver in the coding environment. Lane detect labels prerequisite
   readiness separately from authentication.
   Advanced Delegation plugin presence/installation is managed as a capability;
   it does not silently select specialist profiles or replace lane policy.
   Discovery supplies candidate CLIs but does not select lanes, infer model
   families or modify routing config. Add new CLI lanes only with verified
   invocation and independent family identity. Native controller remains
   the existing fallback; do not count it as an independent model family.
   Version probes require allow_project_checks. A repository-provided
   .dev-pipeline/lanes.toml is untrusted: it cannot define new lanes,
   providers or executable commands; lane execution config comes only from
   bundled, machine or explicitly named config.
3. Inspect repository CI and plan checks; prefer configured CI/lockfiles.
   Use native LSP status/install and write_file/patch diagnostics. CLI status
   may describe a different process from the active gateway; no diagnostics
   does not mean no errors. Use ast search for targeted structural navigation;
   ast-grep may load project sgconfig.yml custom parsers.
4. Run one check at a time through engineering_run. Record PASS, FINDINGS,
   ERROR or UNAVAILABLE, not a model's claim. Dirty-tree runs are useful during
   build but cannot satisfy final gates. Rerun on final clean commit. The
   mandatory diff check covers the HEAD commit and uncommitted changes only;
   multi-commit branches need repository CI or an explicit range check.
5. Before push, tag, release or live deploy, require ENGINEERING_PASS from
   dev_pipeline_gate on that exact clean commit. Missing, failed or stale
   mandatory records are NOT_SHIP. Then apply all existing acceptance, review,
   deployment and CI gates. This is a workflow gate, not an interception of
   arbitrary terminal commands or a tamper-proof security boundary.
6. Full acceptance suite remains required even when not represented by a
   built-in check. Coverage and mutation thresholds belong to the repository.
   Nonstandard projects/monorepos require manual profile selection and CI
   verification; root marker detection is advisory.

## Evidence limitations

State lives in the active Hermes profile; one latest record per root/check.
Evidence binds the canonical root, HEAD and clean tracked/untracked status
before/after, command and exit code. Ignored files, external dependencies,
concurrent edits reverted during execution and backend changes are not
cryptographically attested. Re-run after any dependency or environment
change. A check that leaves un-tracked artifacts on disk (for example a
pytest cache not covered by .gitignore) makes its own run ineligible;
keep project cache paths ignored so clean-commit reruns classify as
eligible. The gate does not authorize release by itself. Avoid concurrent
mutations while checking. The plugin does not enforce organization-wide
deployment policy; enforce that in protected CI/branch rules.
