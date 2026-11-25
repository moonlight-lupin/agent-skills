#!/usr/bin/env python3
"""Stamp a brief template with facts taken from commands, not from memory.

Fills, when the template uses them:
  {{BASE}} {{HEAD}}             short SHAs resolved by git
  {{DIFF}} {{DIFF_LINES}} {{DIFF_FILES}}
                                the base..head diff, written to --diff-out
  {{TEST_CMD}} {{TEST_EXIT}} {{TEST_TAIL}}
                                --test-cmd run in the repo; exit code and last output line
  {{ROUND_LINE}}                from the review budget ledger (--budget)
  {{SEVERITY_BLOCK}}            from ../references/review-briefs.md
  {{BUILDER_BLOCK}}             from orchestrator/references/coding-principles.md
  {{DATE}}                      today, ISO

Refuses (non-zero exit, nothing written) when:
  2  a {{PLACEHOLDER}} is left unfilled
  3  the brief cites a commit SHA that is neither BASE nor HEAD (pass --allow-sha
     for one cited on purpose)
  4  --budget is given but no review round is open (run review_budget.py round)
  6  the diff is longer than --max-diff-lines without --allow-large
  5  usage / git errors
"""
import argparse
import datetime as _dt
import importlib.util
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(os.path.dirname(HERE))
REVIEW_BRIEFS = os.path.join(SKILLS, "briefs", "references", "review-briefs.md")
CODING_PRINCIPLES = os.path.join(SKILLS, "orchestrator", "references", "coding-principles.md")
BUDGET_SCRIPT = os.path.join(SKILLS, "review-commit", "scripts", "review_budget.py")
PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
SHA_TOKEN = re.compile(r"\b[0-9a-f]{7,40}\b")


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def is_commit(repo, token):
    r = subprocess.run(["git", "-C", repo, "rev-parse", "--verify", "-q", f"{token}^{{commit}}"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def fenced_block_after(path, heading):
    """The first ``` fenced block after the heading line that starts with `heading`."""
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(heading))
    opened = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("```"))
    closed = next(i for i in range(opened + 1, len(lines)) if lines[i].startswith("```"))
    return "\n".join(lines[opened + 1:closed])


def load_budget_module():
    spec = importlib.util.spec_from_file_location("dev_pipeline_review_budget_stamp", BUDGET_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("template")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--base")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--diff-out", help="where to write the base..head diff")
    ap.add_argument("--exclude", action="append", default=[],
                    help="pathspec to leave out of the diff (e.g. package-lock.json); repeatable")
    ap.add_argument("--test-cmd")
    ap.add_argument("--budget", help="review budget ledger dir (review_budget.py)")
    ap.add_argument("--allow-sha", action="append", default=[])
    ap.add_argument("--max-diff-lines", type=int, default=5000)
    ap.add_argument("--allow-large", metavar="REASON")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    with open(a.template, encoding="utf-8") as fh:
        text = fh.read()
    used = set(PLACEHOLDER.findall(text))
    values = {"DATE": _dt.date.today().isoformat()}

    base_full = head_full = None
    if a.base:
        base_full = git(a.repo, "rev-parse", "--verify", f"{a.base}^{{commit}}").strip()
        values["BASE"] = base_full[:12]
    head_full = git(a.repo, "rev-parse", "--verify", f"{a.head}^{{commit}}").strip()
    values["HEAD"] = head_full[:12]

    if used & {"DIFF", "DIFF_LINES", "DIFF_FILES"}:
        if not (a.base and a.diff_out):
            print("the template uses {{DIFF*}}: pass --base and --diff-out")
            return 5
        spec = ["--", "."] + [f":(exclude){p}" for p in a.exclude]
        diff = git(a.repo, "diff", f"{base_full}..{head_full}", *spec)
        files = git(a.repo, "diff", "--name-only", f"{base_full}..{head_full}", *spec).split()
        n_lines = diff.count("\n")
        if n_lines > a.max_diff_lines and not a.allow_large:
            print(f"REFUSED: diff is {n_lines} lines (> {a.max_diff_lines}). Review per milestone "
                  "(confirm-round-protocol.md § Milestones), or pass --allow-large with a reason.")
            return 6
        os.makedirs(os.path.dirname(os.path.abspath(a.diff_out)), exist_ok=True)
        with open(a.diff_out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(diff)
        values.update(DIFF=a.diff_out, DIFF_LINES=str(n_lines), DIFF_FILES=str(len(files)))
        if a.exclude:
            values["DIFF"] += f" (excluding {', '.join(a.exclude)})"

    if a.test_cmd:
        r = subprocess.run(a.test_cmd, shell=True, cwd=a.repo, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        tail = [l.strip() for l in (r.stdout + r.stderr).splitlines() if l.strip()]
        values.update(TEST_CMD=a.test_cmd, TEST_EXIT=str(r.returncode),
                      TEST_TAIL=(tail[-1][:200] if tail else "(no output)"))

    if a.budget:
        rb = load_budget_module()
        led = rb.load(a.budget)
        if not led["rounds"] or led["rounds"][-1].get("closed_at"):
            print("REFUSED: no review round is open - run review_budget.py round first")
            return 4
        values["ROUND_LINE"] = rb.round_line(led)

    if "SEVERITY_BLOCK" in used:
        values["SEVERITY_BLOCK"] = "```\n" + fenced_block_after(REVIEW_BRIEFS, "## Severity block") + "\n```"
    if "BUILDER_BLOCK" in used:
        values["BUILDER_BLOCK"] = fenced_block_after(CODING_PRINCIPLES, "## Builder block")

    out = PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)
    left = sorted(set(PLACEHOLDER.findall(out)))
    if left:
        print("REFUSED: unfilled placeholders: " + ", ".join("{{%s}}" % k for k in left))
        return 2

    known = {s for s in (base_full, head_full) if s}
    stale = []
    for tok in set(SHA_TOKEN.findall(out)):
        if not (re.search(r"\d", tok) and re.search(r"[a-f]", tok)):
            continue
        if any(full.startswith(tok) for full in known) or tok in a.allow_sha:
            continue
        if is_commit(a.repo, tok):
            stale.append(tok)
    if stale:
        print("REFUSED: the brief cites commits that are neither BASE nor HEAD: " + ", ".join(sorted(stale))
              + " (stale? pass --allow-sha for one cited on purpose)")
        return 3

    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(out)
        print(f"stamped {a.out}" + (f" (large diff allowed: {a.allow_large})" if a.allow_large else ""))
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
