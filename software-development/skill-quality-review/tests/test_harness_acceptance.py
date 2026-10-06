#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Acceptance fixtures for the Check 15/17 harnesses (second 6 Oct review).

Two shapes are cut from the pere-toolkit states and reduced to minimal
synthetic repos here — the full-tree runs over the real repo stay a
documented manual step (tests/acceptance.md), because the repo is
Hermes-local and may not exist where the plugin is installed.

Fixtures reproduce, in miniature:
- d4e0a2c shape: skill cites a library engine with no import recipe, cites
  a call span missing a required keyword, and carries a demo-dispatch
  __main__ block, and one repo-relative CLI path.
- v0.11.0 shape: same engine WITH the "Calling the engines" recipe and
  verified call lines — both harnesses come back clean."""

import pathlib
import subprocess
import sys
import textwrap

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
CHECK_CALLS = SKILL_DIR / "scripts" / "check_calls.py"
CHECK_REFERENCES = SKILL_DIR / "scripts" / "check_references.py"

D4_SKILL = textwrap.dedent("""\
    ---
    name: sample-skill
    description: "Use when underwriting a sample deal in scratch tests."
    ---

    # Sample

    ## Workflow

    - Cite the engine: `scripts/engine.py` `bid_level(...)`.
    - Run: `python skills/sample-skill/scripts/report.py`.
    """)

D4_CALLS = textwrap.dedent('''\
    """Engine and CLI for the sample fixture."""
    def bid_level(offers, *, valuation_date):
        return offers, valuation_date


    def main(argv=None):
        print("main would run", argv)


    if __name__ == "__main__":
        print("demo output")
''')

D4_REPORT = textwrap.dedent('''\
    """A repo-relative CLI fixture."""
    if __name__ == "__main__":
        print("report")
''')

V011_SKILL = textwrap.dedent("""\
    ---
    name: sample-skill
    description: "Use when underwriting a sample deal in scratch tests."
    ---

    # Sample

    Calling the engines: put `scripts/` on `sys.path`, then `import engine`
    and call with the verified signature below.

    ## Workflow

    - Verified call: `engine.bid_level([{'price': 1.0}], valuation_date='2031-01-01')`.
    """)

V011_CALLS = textwrap.dedent('''\
    """Engine and CLI for the sample fixture."""
    def bid_level(offers, *, valuation_date):
        return offers, valuation_date


    def main(argv=None):
        print("bid_level ready")


    if __name__ == "__main__":
        main()
''')


def build_repo(root: pathlib.Path, skill_text: str, calls_text: str):
    scripts = root / "skills" / "sample-skill" / "scripts"
    scripts.mkdir(parents=True)
    (root / "skills" / "sample-skill" / "SKILL.md").write_text(skill_text)
    (scripts / "engine.py").write_text(calls_text)
    (scripts / "report.py").write_text(D4_REPORT)
    return root


def run(script: pathlib.Path, root: pathlib.Path):
    return subprocess.run(
        [sys.executable, str(script), str(root)],
        capture_output=True, text=True, timeout=120)


def test_d4_shape_is_caught(tmp_path):
    root = build_repo(tmp_path, D4_SKILL, D4_CALLS)
    r = run(CHECK_CALLS, root)
    assert r.returncode == 1, r.stdout + r.stderr
    out = r.stdout
    assert "no-recipe" in out, out
    assert "demo-dispatch" in out, out
    assert "bid_level" in out and "missing required" in out, out
    assert "repo-relative-path" in out, out


def test_v011_shape_is_clean(tmp_path):
    root = build_repo(tmp_path, V011_SKILL, V011_CALLS)
    r = run(CHECK_CALLS, root)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "OK" in r.stdout


def test_templates_exempt_from_toc_check(tmp_path):
    root = tmp_path
    template = root / "skills" / "sample-skill" / "assets"
    template.mkdir(parents=True)
    lines = "\n".join(f"line {i}" for i in range(120)) + "\n"
    (template / "memo-template.md").write_text(lines)
    # no SKILL.md at all -> file not claimed by any skill -> skipped cleanly
    r = run(CHECK_REFERENCES, root)
    assert r.returncode == 0, r.stdout + r.stderr
    # now WITH a SKILL.md that cites the template: still no no-contents finding
    build_repo(root, V011_SKILL, V011_CALLS)
    r = run(CHECK_REFERENCES, root)
    assert "no-contents-list" not in r.stdout, r.stdout
    # and a LONG reference file WITHOUT a Contents list IS flagged
    ref = root / "skills" / "sample-skill" / "references"
    ref.mkdir(parents=True, exist_ok=True)
    (ref / "method.md").write_text(lines)
    (root / "skills" / "sample-skill" / "SKILL.md").write_text(
        V011_SKILL + "\nSee `references/method.md`.\n")
    r = run(CHECK_REFERENCES, root)
    assert "no-contents-list" in r.stdout, r.stdout


if __name__ == "__main__":
    sys.exit(subprocess.run([sys.executable, "-m", "pytest", __file__,
                             "-q"]).returncode)