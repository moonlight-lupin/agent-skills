#!/usr/bin/env python3
"""Capture a delegate-result.v1 result file after a builder/reviewer dispatch.

Part of the build-review-loop skill. Run once per dispatch, after the
implementer process exits and before orchestrator verification. The result
file — not a log tail — is the dispatch's accountable record: status, exit
code, the model that actually ran, and the touched-files boundary the review
starts from.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys

SCHEMA = "delegate-result.v1"


def git_porcelain(repo):
    """git status --porcelain lines for repo; None when git can't report."""
    try:
        out = subprocess.run(
            ["git", "-C", repo, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if out.returncode != 0:
            return None
        return [line for line in out.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return None


def status_from_exit(code):
    if code == 0:
        return "completed"
    if code == 124:
        return "timeout"
    if code == 127:
        return "unavailable"
    return "failed"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True,
                    help="project working tree the implementer ran in")
    ap.add_argument("--task", required=True,
                    help='short label, e.g. "build R1: batch A"')
    ap.add_argument("--implementer", required=True,
                    choices=["cursor", "codex", "claude-code", "hermes"])
    ap.add_argument("--model", default=None,
                    help="model that actually ran (after any tier fallback)")
    ap.add_argument("--report", default=None,
                    help="path to the implementer's full output/report file")
    ap.add_argument("--stderr", default=None,
                    help="path to captured stderr, if kept")
    ap.add_argument("--exit-code", type=int, required=True)
    ap.add_argument("--started-at", default=None,
                    help="ISO timestamp the dispatch started, if known")
    ap.add_argument("--out", required=True,
                    help="output JSON path (keep it outside the repo)")
    ap.add_argument("--notes", default=None,
                    help="free text, e.g. 'medium-tier fallback' or 'delta round for R1'")
    args = ap.parse_args()

    result = {
        "schema": SCHEMA,
        "task": args.task,
        "implementer": args.implementer,
        "model": args.model,
        "status": status_from_exit(args.exit_code),
        "exitCode": args.exit_code,
        "reportPath": os.path.abspath(args.report) if args.report else None,
        "stderrPath": os.path.abspath(args.stderr) if args.stderr else None,
        "touchedFiles": git_porcelain(args.repo),
        "startedAt": args.started_at,
        "finishedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"),
        "notes": args.notes,
    }

    if args.report and not os.path.isfile(result["reportPath"]):
        print(f"WARN: report file not found: {result['reportPath']}", file=sys.stderr)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
        fh.write("\n")

    touched = result["touchedFiles"]
    touched_n = "unknown" if touched is None else len(touched)
    print(f"captured {args.out}: status={result['status']} "
          f"exit={args.exit_code} touched={touched_n}")


if __name__ == "__main__":
    main()
