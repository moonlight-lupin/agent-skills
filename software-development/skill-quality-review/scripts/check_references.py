#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check 17 — reference hygiene audit (format-agnostic).

Vendored from hermes-agent-skill-authoring's audit_references.py so plugin
repos do not depend on anything outside this skill. Checks, per reference
file (*.md under each skill, excluding SKILL.md itself):

- no-contents-list : file over 100 lines with no Contents/TOC list
- nested           : reference file more than one directory deep under the
                     skill directory (references/references/x.md or refs/x/y.md)
- orphan-reference : file under references/ (or templates/, scripts/ docs)
                     that no SKILL.md text mentions by name

Exemptions (same rules as add_toc.py): files whose basename starts with
'llms', paths containing brands/, vendor/, examples/, dumps over 5000 lines,
archives (.archive/, .curator_backups/, retired-*).

Note on one-level-deep: a reference file must live at
<skill>/references/<name>.md. Files deeper than that are findings.

Usage: python3 check_references.py <repo-root> [--json]
Exit 0 clean, 1 findings, 2 usage error.
"""

import json
import os
import re
import sys

TOC_RE = re.compile(r"^(#{1,3}\s+(contents|table of contents)\b|## Contents)", re.I)
VENDORED_DIR_PARTS = {"brands", "vendor", "examples"}
ARCHIVE_PARTS = {".archive", ".curator_backups", "__pycache__", ".hub"}
MAX_ARCHIVE_BASENAMES = ("retired-",)
MENTION_MIN = 0


def is_exempt(rel: str, n_lines: int) -> bool:
    parts = rel.replace(os.sep, "/").split("/")
    base = parts[-1].lower()
    if base.startswith("llms"):
        return True
    if set(parts) & VENDORED_DIR_PARTS or set(parts) & ARCHIVE_PARTS:
        return True
    if base.startswith(MAX_ARCHIVE_BASENAMES):
        return True
    if n_lines > 5000:
        return True
    return False


def has_contents(text: str) -> bool:
    lines = text.splitlines()
    head = lines[:80]
    return any(TOC_RE.match(l) for l in head) or bool(re.search(TOC_RE, text[:400]))


def main(argv):
    if len(argv) < 2:
        print("usage: check_references.py <repo-root> [--json]")
        return 2
    do_json = "--json" in argv
    root = os.path.abspath(argv[1])
    if not os.path.isdir(root):
        print(f"not a directory: {root}")
        return 2

    findings = []  # (skill, kind, relpath)

    # ---- discover skills and their SKILL.md texts ----
    skill_texts = {}
    skill_dirs = {}
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in ARCHIVE_PARTS]
        if "SKILL.md" in fns:
            fp = os.path.join(dp, "SKILL.md")
            skill_texts[fp] = open(fp, encoding="utf-8", errors="replace").read().lower()
            skill_dirs[fp] = dp

    # ---- walk every file under each skill, audit non-SKILL.md documents ----
    checked = 0
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in ARCHIVE_PARTS]
        for fn in sorted(fns):
            if not fn.endswith(".md") or fn == "SKILL.md":
                continue
            fp = os.path.join(dp, fn)
            rel = os.path.relpath(fp, root)
            # which skill does this belong to? nearest ancestor with SKILL.md
            owning_skill_md = None
            walk = dp
            while walk.startswith(root) and walk != os.path.dirname(root):
                cand = os.path.join(walk, "SKILL.md")
                if cand in skill_texts:
                    owning_skill_md = cand
                    break
                walk = os.path.dirname(walk)
            if owning_skill_md is None:
                continue
            skill_dir = skill_dirs[owning_skill_md]
            skill_rel = os.path.relpath(fp, skill_dir)
            try:
                text = open(fp, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            n_lines = text.count("\n") + 1
            if is_exempt(rel, n_lines):
                continue
            checked += 1
            # 1) TOC on long references
            if n_lines > 100 and not has_contents(text):
                findings.append((rel, "no-contents-list",
                                 f"{n_lines} lines, no Contents list"))
            # 2) one level deep
            parts = skill_rel.replace(os.sep, "/").split("/")[:-1]
            depth_dirs = [p for p in parts if p not in (".",)]
            # a reference file directly under references/ or templates/ etc is
            # depth 1; deeper is a finding
            if len(parts) > 1 or (len(parts) == 1 and parts[0] not in (
                    "references", "templates", "scripts", "assets", "commands",
                    "agents", "hooks")):
                findings.append((rel, "nested",
                                 f"reference file deeper than one level: {skill_rel}"))
            # 3) orphan check — is this file mentioned by its SKILL.md?
            stem = fn[:-3]
            text_l = text
            mentioned = stem in skill_texts[owning_skill_md] or fn in skill_texts[owning_skill_md]
            if not mentioned:
                findings.append((rel, "orphan-reference",
                                 f"not referenced by {os.path.relpath(owning_skill_md, root)}"))

    if do_json:
        print(json.dumps({"checked": checked, "findings": findings}, indent=1))
    else:
        if findings:
            print(f"[CLAUDE][CHECK17] {len(findings)} findings ({checked} files checked):")
            for rel, kind, detail in findings:
                print(f"  {kind:<18} {rel} — {detail}")
        else:
            print(f"[CLAUDE][CHECK17] OK — {checked} reference files clean")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))