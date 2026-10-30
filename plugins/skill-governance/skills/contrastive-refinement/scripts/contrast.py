#!/usr/bin/env python3
"""Deterministic helpers for contrastive skill refinement (Harness^2 port).

Two jobs, both pure stdlib and offline:

- `ids`      — assign anonymous labels (A, B, .. Z, AA, AB, ..) to candidate
               outputs with a seeded shuffle, so the selection step compares
               deliverables blind. Same (labels, task, k, mode) -> same mapping
               within one Python version; cross-interpreter stability of
               `random.Random` is not guaranteed, so never compare mappings
               across interpreters.
- `lesson-check` — the evidence gate: a lesson entry is valid only when
               cue, lesson, evidence and confidence are all present with a
               real (non-placeholder) value. Exits 0 when valid, 1 with the
               missing fields when not. No evidence -> no lesson.

Value format: single-line `field: value`; bullets and bold markers are
stripped; duplicate fields take the LAST occurrence.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import re
import sys

LESSON_FIELDS = ("cue", "lesson", "evidence", "confidence")

_PLACEHOLDERS = frozenset({"n/a", "na", "-", "none", "todo", "tbd", "?", "x", ""})

_BARE_TEMPLATE_TAG = re.compile(r"<[^<>]*>")  # ONE tag, nothing else

_WRAP_AND_TRAILING = "*`_\"'.!,::"  # markdown wraps and trailing punctuation


def _clean_value(raw: str) -> str:
    """Normalize a field value for the placeholder check. Strips markdown
    wraps (bold/italics/backticks/quotes) from both ends and trailing
    sentence punctuation, iteratively, so `**n/a**`, `N/A.` and `**  ` all
    normalize to a placeholder. Only the WHOLE value is compared — a sentence
    that merely contains a placeholder word stays valid.
    """
    value = raw.strip()
    for _ in range(3):
        before = value
        value = value.strip(_WRAP_AND_TRAILING).strip()
        if value == before:
            break
    return value.lower()


def _is_placeholder(raw: str) -> bool:
    value = _clean_value(raw)
    return value in _PLACEHOLDERS or bool(_BARE_TEMPLATE_TAG.fullmatch(value))

_FIELD_LINE = re.compile(r"^\s*[-*]?\s*\**([a-zA-Z][a-zA-Z ]*?)\**\s*:\s*(.*?)\s*$")


def assign_ids(
    labels: list[str],
    *,
    task_id: str = "",
    k: int = 1,
    mode: str = "",
) -> dict[str, str]:
    """Return anon_id -> label. Labels are sorted then seeded-shuffled, so the
    mapping is stable across reruns of the same probe cycle.

    Labels are whitespace-stripped before dedup (the CLI and API normalize
    identically). The seed binds the shuffle to (task_id, k, mode): different
    probe cycles get different orders, the same cycle never does.
    """
    cleaned = [str(label).strip() for label in labels]
    if not cleaned:
        raise ValueError("no labels given — assign_ids needs at least one candidate")
    if any(not label for label in cleaned):
        raise ValueError(f"blank labels are invalid: {labels}")
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"duplicate labels: {cleaned}")
    seed = int(hashlib.sha1(f"{task_id}|{k}|{mode}".encode()).hexdigest()[:12], 16)
    ordered = sorted(cleaned)
    random.Random(seed).shuffle(ordered)
    return {_anon_id(i): label for i, label in enumerate(ordered)}


def _anon_id(index: int) -> str:
    """A..Z, AA..AZ, BA.. — single- and double-letter ids the way Harness^2 does."""
    out = ""
    n = index + 1
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def check_lesson(text: str) -> tuple[bool, list[str]]:
    """Validate a lesson entry. Returns (ok, problems). Every field in
    LESSON_FIELDS must appear as `field: <real value>` (bullet and bold
    markers are stripped; a value that is only a placeholder such as `n/a`,
    `-`, `none` — with or without markdown wraps like `**n/a**` or trailing
    punctuation like `N/A.` — counts as empty, and a value that is ONE bare
    `<template>` tag is rejected as well; evidence that merely CONTAINS or
    assembles tag spans stays valid). The evidence field is mandatory — a
    lesson without an observed contrast is rejected. Values are single-line;
    the last duplicate field wins.
    """
    problems: list[str] = []
    if not text or not text.strip():
        return False, ["empty lesson text"]
    found: dict[str, str] = {}
    for line in text.splitlines():
        m = _FIELD_LINE.match(line)
        if not m:
            continue
        key = m.group(1).strip().lower()
        if key in LESSON_FIELDS:
            found[key] = m.group(2)
    for field in LESSON_FIELDS:
        if _is_placeholder(found.get(field, "")):
            problems.append(f"missing or empty field: {field}")
    return not problems, problems


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_ids = sub.add_parser("ids", help="assign anonymous candidate ids")
    p_ids.add_argument("--labels", required=True, help="comma-separated candidate labels")
    p_ids.add_argument("--task", default="", help="probe task id (part of the shuffle seed)")
    p_ids.add_argument("--k", type=int, default=1, help="shuffle-seed tag, not a run count")
    p_ids.add_argument("--mode", default="", help="probe mode tag (seed part)")

    p_lesson = sub.add_parser("lesson-check", help="validate a lesson entry on stdin")

    args = parser.parse_args(argv)
    if args.command == "ids":
        labels = [str(s).strip() for s in args.labels.split(",")]
        try:
            mapping = assign_ids(labels, task_id=args.task, k=args.k, mode=args.mode)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        for anon, label in mapping.items():
            print(f"{anon}\t{label}")
        return 0
    if args.command == "lesson-check":
        text = sys.stdin.read()
        ok, problems = check_lesson(text)
        if ok:
            print("ok: lesson complete (cue, lesson, evidence, confidence)")
            return 0
        for problem in problems:
            print(f"reject: {problem}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(_main())
