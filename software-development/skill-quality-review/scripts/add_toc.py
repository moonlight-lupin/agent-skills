#!/usr/bin/env python3
"""Bulk-add Contents lists to long markdown reference files.

Companion to audit_references.py in this skill. Finds markdown files over
100 lines that lack a Contents list and inserts one generated from the
file's own structure. Dry-run by default; pass --apply to write.

Heading extraction priority (all code-fence aware):
  1. '## ' headings
  2. '### ' headings when no '## ' exists
  3. '- **Label**:' bold-label bullets when no headings exist
Skips files whose generated list would exceed --max-entries (default 60):
for label-dump files a TOC nearly doubles the file and stops paying for
itself. Same vendored exemptions as audit_references.py (llms*, brands/,
vendor/, examples/, >5000-line dumps). Adds exactly one trailing newline —
bulk writers that leave the final newline off make git report the last
line as deleted and re-added.

Usage:
    python3 add_toc.py <dir>              # dry-run report
    python3 add_toc.py <dir> --apply      # write the TOCs
    python3 add_toc.py <dir> --json       # machine-readable report
    python3 add_toc.py <dir> --max-entries 80

Exit code 0 = nothing pending or all applied cleanly; 1 = pending changes
remain (dry-run) or some files were skipped for structure reasons.
"""
import json
import os
import re
import sys

TOC_MARK = "## Contents"
VENDORED_DIR_PARTS = {"brands", "vendor", "examples"}


def _outside_fences(lines):
    """Yield (index, line) for lines outside fenced code blocks."""
    inf = False
    for i, l in enumerate(lines):
        if l.strip().startswith("```"):
            inf = not inf
            continue
        if not inf:
            yield i, l


def clean_entry(text):
    t = re.sub(r"\*+", "", text.strip())
    return t.rstrip(":").strip()


def extract(lines):
    """Return (entries, mode) using the highest-priority structure present."""
    h2, h3, bullets = [], [], []
    for _, l in _outside_fences(lines):
        if re.match(r"^## ", l):
            h2.append(clean_entry(l[3:]))
        elif re.match(r"^### ", l):
            h3.append(clean_entry(l[4:]))
        m = re.match(r"^- \*\*(.+?)\*\*", l)
        if m:
            bullets.append(m.group(1).strip())
    if h2:
        return h2, "h2"
    if h3:
        return h3, "h3"
    if bullets:
        return bullets, "bullets"
    return [], None


def is_vendored(rel, n_lines):
    parts = set(rel.replace(os.sep, "/").split("/"))
    if os.path.basename(rel.lower()).startswith("llms"):
        return True
    if parts & VENDORED_DIR_PARTS:
        return True
    return n_lines > 5000


def add_toc(fp, rel, max_entries):
    txt = open(fp, errors="replace").read()
    lines = txt.splitlines()
    if len(lines) <= 100:
        return "short"
    head_zone = txt.splitlines()[:80]
    if TOC_MARK in txt[:400] or any(l.strip() == TOC_MARK for l in head_zone) \
            or any(re.match(r"^#{1,3}\s+(contents|table of contents)\b", l, re.I) for l in head_zone):
        return "already-toc"
    if is_vendored(rel, len(lines)):
        return "vendored"
    entries, mode = extract(lines)
    if not mode:
        return "no-structure"
    if len(entries) > max_entries:
        return "too-many-entries"
    anchor = r"^## " if mode == "h2" else (r"^### " if mode == "h3" else r"^- \*\*")
    ins = None
    for i, l in _outside_fences(lines):
        if re.match(anchor, l) and any(x.strip() for x in lines[i + 1:]):
            ins = i
            break
    if ins is None:
        return "no-insert-point"
    toc = [TOC_MARK, ""] + [f"- {e}" for e in entries] + [""]
    new = lines[:ins] + toc + lines[ins:]
    open(fp, "w").write("\n".join(new) + "\n")
    return "fixed"


def main():
    argv = sys.argv[1:]
    do_apply = "--apply" in argv
    as_json = "--json" in argv
    max_entries = 60
    if "--max-entries" in argv:
        idx = argv.index("--max-entries")
        max_entries = int(argv[idx + 1])
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    root = os.path.abspath(args[0])
    if not os.path.isdir(root):
        print(f"not a directory: {root}")
        return 2
    report = {}
    changed = 0
    for dp, _, fns in os.walk(root):
        for fn in sorted(fns):
            if not fn.endswith(".md") or fn == "SKILL.md":
                continue
            fp = os.path.join(dp, fn)
            rel = os.path.relpath(fp, root)
            status = add_toc(fp, rel, max_entries)
            report[rel] = status
            if status == "fixed":
                changed += 1
    if as_json:
        print(json.dumps({"applied": do_apply, "fixed": changed,
                          "report": report}, indent=1))
    else:
        print(f"{'APPLIED' if do_apply else 'DRY-RUN'} | fixed: {changed}")
        for rel, status in report.items():
            if status not in ("short", "already-toc", "vendored"):
                print(f"  {status:<20} {rel}")
    pending = sum(1 for s in report.values() if s == "fixed" and not do_apply)
    skipped = sum(1 for s in report.values() if s.startswith(("too-many", "no-")))
    return 1 if (pending or skipped) else 0


if __name__ == "__main__":
    sys.exit(main())