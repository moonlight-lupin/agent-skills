"""stamp_brief.py: briefs get their facts from commands (v0.3.1)."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "skills/briefs/scripts/stamp_brief.py"
spec = importlib.util.spec_from_file_location("dev_pipeline_stamp_brief", PATH)
sb = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = sb
spec.loader.exec_module(sb)

ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env=ENV).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    shas = []
    for i in range(3):
        (r / "app.py").write_text("x = %d\n" * (i + 1) % tuple(range(i + 1)), encoding="utf-8")
        git(r, "add", "app.py")
        git(r, "commit", "-q", "-m", f"c{i}")
        shas.append(git(r, "rev-parse", "HEAD"))
    return r, shas


def stamp(tmp_path, body, *args):
    t = tmp_path / "brief.tmpl.md"
    t.write_text(body, encoding="utf-8")
    out = tmp_path / "brief.md"
    code = sb.main([str(t), "--out", str(out), *[str(a) for a in args]])
    return code, (out.read_text(encoding="utf-8") if out.exists() else None)


def test_fills_facts_from_git_and_the_test_command(tmp_path, repo):
    r, shas = repo
    code, out = stamp(tmp_path, "{{BASE}} -> {{HEAD}}: {{DIFF}} {{DIFF_LINES}} lines, {{DIFF_FILES}} file\n"
                      "`{{TEST_CMD}}` exit {{TEST_EXIT}}: {{TEST_TAIL}}\n",
                      "--repo", r, "--base", shas[0], "--diff-out", tmp_path / "r.diff",
                      "--test-cmd", f'"{sys.executable}" -c "print(\'5 passed\')"')
    assert code == 0
    assert shas[0][:12] in out and shas[2][:12] in out
    assert "1 file" in out and "exit 0: 5 passed" in out
    assert (tmp_path / "r.diff").read_text(encoding="utf-8").startswith("diff --git")


def test_refuses_unfilled_placeholders(tmp_path, repo):
    r, shas = repo
    code, out = stamp(tmp_path, "{{ROUND_LINE}}\n", "--repo", r)
    assert code == 2 and out is None


def test_refuses_a_stale_sha(tmp_path, repo):
    r, shas = repo
    body = "base {{BASE}}, fixes landed at " + shas[1][:7] + "\n"
    code, out = stamp(tmp_path, body, "--repo", r, "--base", shas[0])
    assert code == 3 and out is None
    code, out = stamp(tmp_path, body, "--repo", r, "--base", shas[0], "--allow-sha", shas[1][:7])
    assert code == 0


def test_needs_an_open_budget_round(tmp_path, repo):
    r, _ = repo
    rb = sys.modules.get("dev_pipeline_review_budget") or sb.load_budget_module()
    ledger = tmp_path / "loop"
    rb.main(["init", str(ledger), "--tier", "T2"])
    assert stamp(tmp_path, "{{ROUND_LINE}}\n", "--repo", r, "--budget", ledger)[0] == 4
    rb.main(["round", str(ledger)])
    code, out = stamp(tmp_path, "{{ROUND_LINE}}\n", "--repo", r, "--budget", ledger)
    assert code == 0 and "round 1 of 3" in out


def test_refuses_a_diff_over_the_milestone_limit(tmp_path, repo):
    r, shas = repo
    args = ("--repo", r, "--base", shas[0], "--diff-out", tmp_path / "r.diff", "--max-diff-lines", "3")
    assert stamp(tmp_path, "{{DIFF_LINES}}\n", *args)[0] == 6
    assert stamp(tmp_path, "{{DIFF_LINES}}\n", *args, "--allow-large", "single file")[0] == 0


def test_stamps_the_shared_blocks(tmp_path, repo):
    r, _ = repo
    code, out = stamp(tmp_path, "{{SEVERITY_BLOCK}}\n{{BUILDER_BLOCK}}\n", "--repo", r)
    assert code == 0
    assert "SEVERITY (dev-pipeline" in out and "CODING PRINCIPLES (dev-pipeline)" in out


def test_every_template_placeholder_is_one_the_script_fills():
    known = {"BASE", "HEAD", "DIFF", "DIFF_LINES", "DIFF_FILES", "TEST_CMD", "TEST_EXIT",
             "TEST_TAIL", "ROUND_LINE", "SEVERITY_BLOCK", "BUILDER_BLOCK", "DATE"}
    for f in [*(ROOT / "skills/briefs/references").glob("*.md"),
              ROOT / "skills/build/references/per-task-workflow.md"]:
        for name in sb.PLACEHOLDER.findall(f.read_text(encoding="utf-8")):
            assert name in known, (f.name, name)
