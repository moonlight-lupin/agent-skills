# Dispatch Result Contract (`delegate-result.v1`)

Ported concept (Sep 2026) from amElnagdy/delegate-skills (MIT): every
implementer dispatch produces one machine-readable result file. Our loop does
not run their relay (it wraps other orchestrators' CLIs); it keeps the same
contract shape. Hermes stays the orchestrator: same model, same CLIs, same
review gates.

## The contract

One JSON file per dispatch, written with
`scripts/capture_dispatch_result.py`, kept OUTSIDE the repo (e.g. the
workspace or `/tmp`), never committed:

```json
{
  "schema": "delegate-result.v1",
  "task": "build R1: batch A",
  "implementer": "cursor",
  "model": "cursor-grok-4.6-high",
  "status": "completed",
  "exitCode": 0,
  "reportPath": "/tmp/proj-build-r1-report.md",
  "stderrPath": null,
  "touchedFiles": [" M core_toolset/modules/x/engine.py", "?? tests/test_x.py"],
  "startedAt": null,
  "finishedAt": "2026-09-12T04:11:32+00:00",
  "notes": "delta round for R1"
}
```

- `status` derives from the exit code: 0 → `completed`, 124 → `timeout`,
  127 → `unavailable` (binary missing), anything else → `failed`.
- `touchedFiles` is `git status --porcelain` at capture time — the review
  boundary. `null` means git could not report (non-repo, git error);
  `[]` means the tree is clean. Untracked files are implementer output:
  no `git diff` shows them — open them directly.
- `model` records the model that ACTUALLY ran, after any tier fallback
  (`cursor-grok-4.6-medium` when high tier hit resource_exhausted) —
  same discipline as delegate-skills' `codexVersion`.
- `notes` records dispatch deltas: fallback reasons, round lineage.

## Capture commands per implementer

```bash
# After the implementer process exits and BEFORE verification/commit:
python3 <skill-dir>/scripts/capture_dispatch_result.py \
  --repo <project-dir> --task "build R1" --implementer cursor \
  --model cursor-grok-4.6-high --exit-code <N> \
  --report /tmp/proj-build-r1-report.md --out /tmp/proj-dispatch-r1.json
```

For Claude Code print mode (`claude -p ... > review.txt 2>&1`), pass
`--report review.txt` and `--implementer claude-code`. For Hermes-built
fallbacks, use `--implementer hermes` so the result file shows the loop's
cross-model property was degraded.

## What the result file changes in the loop

- Review starts from `touchedFiles`, not from reading the whole diff.
- Review prompts get the touched-file list pre-computed.
- The commit boundary check is mechanical: the commit content must match
  the captured `touchedFiles` — any file present at commit time but absent
  from the capture (or vice versa) is a scope deviation to adjudicate.
- Failed dispatches (`failed`/`timeout`) leave a record the fix round
  resumes from; the fix brief cites the capture, not memory.

## Attestation scope at dispatch time

Attest (`scripts/attest_file.py attest`) every file the builder is
forbidden to modify — the contract-test file, fixture files it must not
generate differently, and BRIEF.md itself — BEFORE dispatching, and add
`*.attest` to `.gitignore` first so the opaque hash sidecars never ride a
`git add -A` into a commit. After the build exits, re-run the attestation
check; a TAMPERED contract file is a BLOCKING finding. Also verify the
red baseline before dispatch: run the orchestrator-authored contract suite
once, confirm every failure is a module-not-found naming the thing the
build introduces (not a harness bug), and commit that baseline — the red
baseline is what makes "it passes after the build" mean anything.
