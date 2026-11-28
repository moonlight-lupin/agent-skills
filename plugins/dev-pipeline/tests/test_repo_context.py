"""RED tests for the repo-context inventory engine (dev-pipeline 0.6.1, Task 1).

Seam: the inventory script's CLI (skills/repo-context/scripts/inventory.py),
drive as a subprocess against fixture git repos — the only public seam of the
engine (plan Task 1). Written by test-evals; the build implementer does not
edit this file (attested).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY = REPO_ROOT / "skills" / "repo-context" / "scripts" / "inventory.py"
STAMP_DATE = "2026-11-28"
STAMP_MARK = "dev-pipeline repo-context survey stamp:"
SKIPPED_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".pytest_cache", "dist", "build"}
TREE_CAP = 300

GITENV = {
    **dict(__import__("os").environ),
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def run_inventory(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    assert not INVENTORY.exists() or INVENTORY.is_file()
    return subprocess.run(
        [sys.executable, str(INVENTORY), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={
            **__import__("os").environ,
            "HERMES_HOME": "",  # suite isolation: no profile leakage into the engine
            "TMPDIR": str(__import__("tempfile").gettempdir()),
        },
    )


def make_repo(tmp_path: Path, *, name: str = "repo", ci: bool = True) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n\n[project.scripts]\ndemo-cli = "demo.cli:main"\n'
    )
    (repo / "CLAUDE.md").write_text("# Convention\n\n- Use pytest for tests.\n- Keep modules deep.\n")
    (repo / "tailwind.config.js").write_text("export default {}\n")
    (repo / "README.md").write_text("# demo\n")
    pkg = repo / "packages" / "demo"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cli.py").write_text("def main() -> int:\n    return 0\n")
    if ci:
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "ci.yml").write_text(
            "jobs:\n  test:\n    steps:\n      - run: pytest tests/ -q\n      - run: cargo test --locked\n"
        )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env=GITENV)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def head_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def write_stamped_doc(repo: Path, survey_stdout: str) -> Path:
    """Simulate the skill's bootstrap: transcribe the skeleton into the repo verbatim."""
    payload = json.loads(survey_stdout)
    doc = repo / "docs" / "repo-context.md"
    doc.parent.mkdir(exist_ok=True)
    doc.write_text(payload["doc_skeleton"])
    return doc


def det_section(doc_text: str) -> str:
    lines = doc_text.splitlines(keepends=True)
    inside = False
    kept: list[str] = []
    for line in lines:
        if "<!-- det:begin -->" in line:
            inside = True
            continue
        if "<!-- det:end -->" in line:
            inside = False
            continue
        if inside:
            kept.append(line)
    return "".join(kept)


# ── survey mode ──────────────────────────────────────────────────────────


def test_survey_deterministic(tmp_path):
    repo = make_repo(tmp_path)
    first = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE)
    second = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout, "identical repo state must emit byte-identical output"


def test_survey_content(tmp_path):
    repo = make_repo(tmp_path)
    out = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE)
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    expected_keys = ["tree", "languages", "frameworks", "entry_points", "test_commands", "standards_sources", "churn", "stamp", "doc_skeleton"]
    assert list(payload.keys()) == expected_keys + [k for k in payload if k.endswith("_truncated")]
    assert "python" in payload["languages"]
    assert "tailwind" in payload["frameworks"]
    assert "Layout" in payload["doc_skeleton"]
    assert any(p.endswith("CLAUDE.md") for p in payload["standards_sources"])
    assert any(c.startswith("pytest") for c in payload["test_commands"])
    assert payload["stamp"]["survey_date"] == STAMP_DATE
    assert payload["stamp"]["head_sha"] == head_sha(repo)
    assert "det_hash" in payload["stamp"] and len(payload["stamp"]["det_hash"]) == 64
    skeleton = payload["doc_skeleton"]
    assert STAMP_MARK in skeleton
    for marker in ("<!-- det:begin -->", "<!-- det:end -->", "<!-- fill: seams -->"):
        assert marker in skeleton, f"skeleton must carry {marker}"
    assert demo_entry_present(payload["entry_points"], "demo-cli")


def demo_entry_present(entry_points: list, name: str) -> bool:
    return any(name in (str(e) if not isinstance(e, dict) else " ".join(str(v) for v in e)) for e in entry_points)


def test_survey_caps(tmp_path):
    repo = make_repo(tmp_path, name="caps", ci=False)
    mods = repo / "alpha"
    mods.mkdir()
    for i in range(TREE_CAP + 30):
        (mods / f"f{i:03d}.txt").write_text("x")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fill")
    out = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE)
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert len(payload["tree"]) == TREE_CAP
    assert payload["tree_truncated"] is True
    # churn is honestly truncated here: the fill commit touches 320 files (cap 10)
    assert payload["churn_truncated"] is True
    for key in ("languages", "entry_points", "test_commands", "standards_sources", "frameworks"):
        assert payload[f"{key}_truncated"] is False


def test_survey_overflow_flags(tmp_path):
    """Codex R1 reproduction pinned: a capped list short of tree must carry a
    TRUE truncation flag — entry_points and test_commands at 25 entries."""
    repo = make_repo(tmp_path, name="overflow", ci=False)
    scripts = "\n".join(f'demo-{i} = "demo.cli:main"' for i in range(25))
    (repo / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n\n[project.scripts]\n' + scripts + "\n"
    )
    package = repo / "package.json"
    tests = ",\n".join(f'"test-{i}": "node t{i}.js"' for i in range(25))
    package.write_text('{\n  "scripts": {\n    ' + tests + "\n  }\n}\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "overflow")
    out = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE)
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    assert len(payload["entry_points"]) == 20 and payload["entry_points_truncated"] is True
    assert len(payload["test_commands"]) == 20 and payload["test_commands_truncated"] is True


def test_survey_fast(tmp_path):
    repo = make_repo(tmp_path, name="fastrepo2", ci=False)
    mods = repo / "alpha"
    mods.mkdir()
    for i in range(TREE_CAP + 30):
        (mods / f"f{i:03d}.txt").write_text("x")
    start = time.monotonic()
    out = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE, timeout=30)
    assert out.returncode == 0, out.stderr
    assert time.monotonic() - start < 10, "survey must stay bounded on a capped repo"


def test_survey_non_repo(tmp_path):
    plain = tmp_path / "notarepo"
    plain.mkdir()
    (plain / "hello.txt").write_text("hi")
    out = run_inventory("survey", str(plain))
    assert out.returncode != 0
    payload = json.loads(out.stdout)
    assert "error" in {str(k) for k in payload}
    assert "tree" not in payload


def test_survey_read_only(tmp_path):
    repo = make_repo(tmp_path, name="ro")
    snapshot_before = _snapshot(repo)
    out = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE)
    assert out.returncode == 0
    assert _snapshot(repo) == snapshot_before, "the engine must never write to the target repo"


def _snapshot(repo: Path) -> dict:
    snap = {}
    for p in sorted(repo.rglob("*")):
        rel = str(p.relative_to(repo))
        if ".git" in rel.split("/"):
            continue
        snap[rel] = (p.stat().st_mtime_ns, p.stat().st_size) if p.is_file() else "dir"
    return snap


# ── check mode: the five staleness cases ────────────────────────────────


def test_check_fresh(tmp_path):
    repo = make_repo(tmp_path, name="fresh")
    survey = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE)
    assert survey.returncode == 0, survey.stderr
    write_stamped_doc(repo, survey.stdout)
    out = run_inventory("check", str(repo))
    assert out.returncode == 0, out.stdout + out.stderr
    assert json.loads(out.stdout)["verdict"] == "fresh"


def test_check_advanced(tmp_path):
    repo = make_repo(tmp_path, name="advanced")
    survey = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE)
    write_stamped_doc(repo, survey.stdout)
    (repo / "README.md").write_text("# demo\n\ngrew\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "second commit")
    out = run_inventory("check", str(repo))
    assert out.returncode == 1, out.stdout
    assert json.loads(out.stdout)["verdict"] == "stale"


def test_check_stamp_unresolvable(tmp_path):
    repo = make_repo(tmp_path, name="foreign")
    survey = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE)
    doc = write_stamped_doc(repo, survey.stdout)
    foreign = "f" * 64
    stamp_line = next(ln for ln in doc.read_text().splitlines() if STAMP_MARK in ln)
    rewritten = re.sub(r"(?<=head_sha=)[0-9a-f]+", foreign, stamp_line)
    doc.write_text(doc.read_text().replace(stamp_line, rewritten))
    out = run_inventory("check", str(repo))
    assert out.returncode == 1, out.stdout
    payload = json.loads(out.stdout)
    assert payload["verdict"] == "stale"
    assert payload["cause"] == "stamp-head-unresolvable"


def test_check_no_doc(tmp_path):
    repo = make_repo(tmp_path, name="nodoc")
    out = run_inventory("check", str(repo))
    assert out.returncode == 2, out.stdout
    assert json.loads(out.stdout)["verdict"] == "bootstrap-needed"


def test_check_hand_edited(tmp_path):
    repo = make_repo(tmp_path, name="handedit")
    survey = run_inventory("survey", str(repo), "--stamp-date", STAMP_DATE)
    doc = write_stamped_doc(repo, survey.stdout)
    text = doc.read_text()
    det = det_section(text)
    assert det, "deterministic section expected in the skeleton"
    doc.write_text(text.replace(det, det.replace("pytest", "pytest (edited by a human)", 1)))
    out = run_inventory("check", str(repo))
    assert out.returncode == 3, out.stdout
    assert json.loads(out.stdout)["verdict"] == "doc-edited"
