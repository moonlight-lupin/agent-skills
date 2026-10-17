#!/usr/bin/env python3
"""Check a loop plan file (build-review-loop port of the planning-with-files
phase-status + completion-gate concept).

The orchestrator's working memory for a multi-batch loop lives in
loop-plan.md (see references/persistent-loop-plan.md). This script reads it
and reports, deterministically:

- phase list with statuses
- resume pointer: the first non-complete phase and its unchecked items
- gate: exit code 1 while any phase is in_progress or pending-checked work
  remains and --gate is passed; exit 0 when every phase is complete

It is the loop's completion gate WITHOUT a hook: the orchestrator runs it at
loop start (resume) and before declaring the loop done. An agent cannot
quietly skip it, because the delivery checklist requires the gate output.

Status grammar (same tokens as planning-with-files, matched as plain text):
  **Status:** pending | in_progress | complete
under each '### Phase N - <name>' heading; tasks are '- [ ]' / '- [x]'.
"""
import argparse
import json
import re
import sys

PHASE_RE = re.compile(r"^###\s+Phase\s+(\d+)\s*[-\u2014:]\s*(.+?)\s*$")
STATUS_RE = re.compile(r"\*\*Status:\*\*\s*(pending|in_progress|complete)", re.I)
TASK_RE = re.compile(r"^\s*-\s+\[([ xX])\]\s*(.*)$")


def parse(path):
    phases = []
    current = None
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            m = PHASE_RE.match(line)
            if m:
                current = {"n": int(m.group(1)), "name": m.group(2),
                           "status": "pending", "tasks": [],
                           "tasks_done": 0}
                phases.append(current)
                continue
            if current is None:
                continue
            s = STATUS_RE.search(line)
            if s:
                current["status"] = s.group(1).lower()
                continue
            t = TASK_RE.match(line)
            if t:
                current["tasks"].append(t.group(2))
                if t.group(1).strip():
                    current["tasks_done"] += 1
    return phases


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("plan", help="path to loop-plan.md")
    ap.add_argument("--gate", action="store_true",
                    help="exit 1 while work remains; exit 0 only when complete")
    args = ap.parse_args()

    phases = parse(args.plan)
    if not phases:
        print(f"NO PHASES: {args.plan} has no '### Phase N - name' headings",
              file=sys.stderr)
        return 2

    open_phases = [p for p in phases
                   if p["status"] == "in_progress"
                   or (p["status"] == "pending" and p["tasks"])
                   or (p["status"] == "complete" and p["tasks"]
                       and p["tasks_done"] < len(p["tasks"]))]
    resume = open_phases[0] if open_phases else None

    summary = {
        "plan": args.plan,
        "phases": [{"n": p["n"], "name": p["name"], "status": p["status"],
                    "tasks": f"{p['tasks_done']}/{len(p['tasks'])}"}
                   for p in phases],
        "openPhases": [p["n"] for p in open_phases],
        "resume": (None if resume is None else
                   {"n": resume["n"], "name": resume["name"],
                    "status": resume["status"],
                    "unchecked": [t for t in resume["tasks"]
                                  ] if resume["status"] != "complete" else []}),
    }
    print(json.dumps(summary, indent=2))

    if args.gate:
        if resume is not None:
            print(f"GATE BLOCKED: phase {resume['n']} ({resume['name']}) "
                  f"is {resume['status']} with unchecked work", file=sys.stderr)
            return 1
        print("GATE OPEN: all phases complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
