#!/usr/bin/env python3
"""dev-pipeline repo-context inventory engine (deterministic; read-only).

survey <repo> [--stamp-date YYYY-MM-DD]
    Emit the repo inventory + doc skeleton as JSON on stdout (exit 0).
    Identical repo state -> identical output. Never writes to the target repo.

check <repo> [--doc PATH]
    Read the survey stamp from the context doc and verdict staleness:
    exit 0 fresh | 1 stale | 2 bootstrap-needed | 3 doc-edited.

Determinism contract (plan Task 1): fixed key order, sorted lists, caps with
`<name>_truncated` sibling flags, churn window anchored to --stamp-date,
never the wall clock (the survey date defaults to today only in live runs;
tests always pass --stamp-date).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

CAPS = {
    "tree": 300,
    "languages": 12,
    "entry_points": 20,
    "test_commands": 20,
    "standards_sources": 30,
    "churn": 10,
    "frameworks": 12,
}
FRAMEWORK_RULES = [
    ("next.config.js", "next"), ("next.config.mjs", "next"), ("next.config.ts", "next"),
    ("nuxt.config.js", "nuxt"), ("nuxt.config.ts", "nuxt"),
    ("vite.config.js", "vite"), ("vite.config.ts", "vite"),
    ("tailwind.config.js", "tailwind"), ("tailwind.config.ts", "tailwind"),
    ("angular.json", "angular"),
    ("svelte.config.js", "svelte"), ("vue.config.js", "vue"),
    ("astro.config.js", "astro"), ("astro.config.mjs", "astro"),
    ("manage.py", "django"),
    ("ember-cli-build.js", "ember"),
]
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".pytest_cache", "dist", "build"}
KEY_ORDER = ["tree", "languages", "frameworks", "entry_points", "test_commands", "standards_sources", "churn"]

LANGUAGE_RULES = [
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("setup.cfg", "python"),
    ("requirements", "python"),  # requirements*.txt
    ("package.json", "javascript"),
    ("tsconfig.json", "typescript"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("Gemfile", "ruby"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
]
STANDARDS_CANDIDATES = [
    "CLAUDE.md",
    "AGENTS.md",
    "CODING_STANDARDS.md",
    "CONTRIBUTING.md",
    ".github/CONTRIBUTING.md",
    "docs/repo-context.md",
]
STAMP_MARK = "dev-pipeline repo-context survey stamp:"
CI_TEST_PATTERNS = [
    r"\bpytest\b",
    r"\bnpm test\b",
    r"\bnpm run test[-a-z]*\b",
    r"\bpnpm test\b",
    r"\bpnpm run test[-a-z]*\b",
    r"\byarn test\b",
    r"\bgo test\b",
    r"\bcargo test\b",
    r"\bmake test[-a-z]*\b",
    r"\btox\b",
]
DET_TITLES = {
    "languages": "Languages",
    "entry_points": "Entry points",
    "frameworks": "Frameworks",
    "test_commands": "Test commands",
    "standards_sources": "Standards sources",
    "churn": "Recent churn",
}
DET_SENTINELS = {  # python manifest markers, section -> label used in the det line
    "languages": "languages",
    "frameworks": "frameworks",
    "entry_points": "entry points",
    "test_commands": "test commands",
    "standards_sources": "standards sources",
    "churn": "recent churn (90d window)",
}


class _EngineError(Exception):
    pass


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60
    )
    if out.returncode != 0:
        raise _EngineError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
    return out.stdout.strip()


def _head(repo: Path) -> str | None:
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True, timeout=60,
    )
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else None


def _capped(items: list[str], key: str) -> tuple[list[str], bool]:
    cap = CAPS[key]
    return items[:cap], len(items) > cap


def _tree(root: Path) -> tuple[list[str], bool]:
    entries: set[str] = set()
    for p in sorted(root.iterdir(), key=lambda q: q.name):
        if p.name in SKIP_DIRS:
            continue
        entries.add(p.name + ("/" if p.is_dir() else ""))
        if p.is_dir():
            for q in sorted(p.iterdir(), key=lambda r: r.name):
                rel = f"{p.name}/{q.name}"
                if q.name in SKIP_DIRS or len(rel) > 40:
                    continue
                entries.add(rel + ("/" if q.is_dir() else ""))
    return _capped(sorted(entries), "tree")


def _languages(root: Path) -> tuple[list[str], bool]:
    found: list[str] = []
    for manifest, language in LANGUAGE_RULES:
        if language in found:
            continue
        if manifest == "requirements":
            hit = any(root.glob("requirements*.txt"))
        else:
            hit = (root / manifest).is_file()
        if hit:
            found.append(language)
    return _capped(found, "languages")


def _packages_json(root: Path) -> dict:
    package = root / "package.json"
    if not package.is_file():
        return {}
    try:
        return json.loads(package.read_text(encoding="utf-8"))
    except ValueError:
        return {}


def _frameworks(root: Path) -> tuple[list[str], bool]:
    found: list[str] = []
    for marker, framework in FRAMEWORK_RULES:
        if framework in found:
            continue
        if (root / marker).is_file():
            found.append(framework)
    return _capped(found, "frameworks")


def _entry_points(root: Path) -> list[str]:
    points: list[str] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        in_scripts = False
        for line in pyproject.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                in_scripts = stripped == "[project.scripts]"
                continue
            if in_scripts and "=" in stripped:
                name = stripped.split("=", 1)[0].strip()
                if name:
                    points.append(name)
    data = _packages_json(root)
    for section in ("bin", "scripts"):
        block = data.get(section)
        if isinstance(block, dict):
            points.extend(str(k) for k in block)
    return _capped(sorted(set(points)), "entry_points")


def _test_commands(root: Path) -> tuple[list[str], bool]:
    """Full runnable lines from CI `run:` statements (keeps targets and flags),
    deduplicated in first-appearance order."""
    found: list[str] = []
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        for p in sorted(workflows.glob("*")):
            if p.suffix not in (".yml", ".yaml"):
                continue
            for raw in p.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if line.startswith("- "):
                    line = line[2:]
                line = re.sub(r'^(?:run\s*:\s*|run\s*:[^"\']*["\'])', "", line).strip().rstrip("\'\"")
                if not line:
                    continue
                for pattern in CI_TEST_PATTERNS:
                    match = re.search(pattern, line)
                    if match and line not in found:
                        found.append(line)
                    if match:
                        break
    scripts = _packages_json(root).get("scripts")
    if isinstance(scripts, dict):
        for name in sorted(scripts):
            if name == "test" or name.startswith("test-"):
                cmd = f"npm run {name}"
                if cmd not in found:
                    found.append(cmd)
    return _capped(found, "test_commands")


def _standards_sources(root: Path) -> tuple[list[str], bool]:
    return _capped([c for c in STANDARDS_CANDIDATES if (root / c).is_file()], "standards_sources")


def _churn(root: Path, stamp_date: str) -> tuple[list[str], bool]:
    since = (date.fromisoformat(stamp_date) - timedelta(days=90)).isoformat()
    try:
        raw = _git(root, "log", "--name-only", "--pretty=format:", "--since", since, "-n", "1000")
    except _EngineError:
        return []
    counts: dict[str, int] = {}
    for line in raw.splitlines():  # --pretty=format: leaves file paths only
        line = line.strip()
        if not line:
            continue
        counts[line] = counts.get(line, 0) + 1
    ranked = sorted(counts, key=lambda p: (-counts[p], p))
    return _capped(ranked, "churn")


def _payload(repo: Path, stamp_date: str) -> tuple[dict, dict]:
    """Producer results as (key -> capped list) plus (key -> truncated flag),
    flags taken from each producer so re-capping can never flatten them."""
    tree, tree_trunc = _tree(repo)
    produced = {
        "languages": _languages(repo),
        "frameworks": _frameworks(repo),
        "entry_points": _entry_points(repo),
        "test_commands": _test_commands(repo),
        "standards_sources": _standards_sources(repo),
        "churn": _churn(repo, stamp_date),
    }
    payload = {"tree": tree}
    flags = {"tree": tree_trunc}
    for key, (items, truncated) in produced.items():
        payload[key] = items
        flags[key] = truncated
    return payload, flags


def _payload_keyed(repo: Path, stamp_date: str) -> dict:
    """Survey payload in the test-contract key order:
    value keys (KEY_ORDER), stamp, doc_skeleton, then every *_truncated flag."""
    payload, flags = _payload(repo, stamp_date)
    _head_sha = _head(repo)
    det_text = _det_block_text(payload)
    head_field = _head_sha if _head_sha else "none"
    keyed = {key: payload[key] for key in KEY_ORDER}
    body = [
        f"<!-- {STAMP_MARK} survey_date={stamp_date} head_sha={head_field} det_hash=PLACEHOLDER -->",
        "",
        "<!-- det:begin -->",
        det_text,
        "<!-- det:end -->",
        "",
        "Judgment sections (the repo-context skill fills these; never hand-edit the det block):",
        "<!-- fill: seams -->",
        "<!-- fill: invariants -->",
        "<!-- fill: why-notes -->",
    ]
    skeleton = "\n".join(body) + "\n"
    # single source of truth: the stamp hashes exactly what check re-hashes — the extracted det block
    det_hash = hashlib.sha256(_extract_det_block(skeleton).encode("utf-8")).hexdigest()
    skeleton = skeleton.replace("det_hash=PLACEHOLDER", f"det_hash={det_hash}", 1)
    keyed["stamp"] = {"survey_date": stamp_date, "head_sha": _head_sha, "det_hash": det_hash}
    keyed["doc_skeleton"] = skeleton
    for key in KEY_ORDER:
        keyed[f"{key}_truncated"] = flags[key]
    return keyed



def _det_block_text(payload: dict) -> str:
    body = []
    body.append("## Layout\n")
    tree = payload.get("tree") or []
    top = [e for e in tree if e.endswith("/")]
    body.append(f"- layout: {len(tree)} entries at depth <= 2; top level: {', '.join(top[:8]) or '(none)'}\n")
    for key in ("languages", "frameworks", "entry_points", "test_commands", "standards_sources", "churn"):
        body.append(f"## {DET_TITLES[key]}\n")
        label = DET_SENTINELS.get(key, key.replace("_", " "))
        body.append(f"- {label}: {', '.join(payload[key]) if payload[key] else '(none detected)'}\n")
    return "\n".join(body)


def cmd_survey(repo: Path, stamp_date: str) -> dict:
    return _payload_keyed(repo, stamp_date)


def _find_doc(repo: Path, doc: Path | None) -> Path | None:
    candidates = [doc] if doc is not None else [repo / c for c in STANDARDS_CANDIDATES]
    for candidate in candidates:
        if candidate and candidate.is_file():
            if STAMP_MARK in candidate.read_text(encoding="utf-8", errors="replace"):
                return candidate
    return None


def _stamp_fields(text: str) -> dict[str, str] | None:
    for line in text.splitlines():
        if STAMP_MARK in line and "survey_date=" in line and "det_hash=" in line:
            rest = line.split("survey_date=", 1)[1]
            fields = dict(
                part.split("=", 1) for part in ("survey_date=" + rest).split() if "=" in part
            )
            return fields
    return None


def cmd_check(repo: Path, doc: Path | None) -> dict:
    found = _find_doc(repo, doc)
    if found is None:
        return {"verdict": "bootstrap-needed"}
    text = found.read_text(encoding="utf-8", errors="replace")
    stamp = _stamp_fields(text)
    if not stamp or not stamp.get("det_hash"):
        return {"verdict": "doc-edited", "cause": "stamp-malformed"}
    current_hash = hashlib.sha256(_extract_det_block(text).encode("utf-8")).hexdigest()
    if current_hash != stamp["det_hash"]:
        return {"verdict": "doc-edited", "cause": "deterministic-section-hash-mismatch"}
    stamp_head = stamp.get("head_sha", "none")
    if not stamp_head or stamp_head == "none":
        return {"verdict": "stale", "cause": "stamp-head-missing"}
    resolved = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", f"{stamp_head}^{{commit}}"],
        capture_output=True, text=True, timeout=60,
    )
    if resolved.returncode != 0:
        return {"verdict": "stale", "cause": "stamp-head-unresolvable"}
    if _head(repo) == stamp_head:
        return {"verdict": "fresh"}
    return {"verdict": "stale"}


def _extract_det_block(text: str) -> str:
    inside = False
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        if "<!-- det:begin -->" in line:
            inside = True
            continue
        if "<!-- det:end -->" in line:
            inside = False
            continue
        if inside:
            kept.append(line)
    return "".join(kept)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="repo-context deterministic inventory engine")
    subs = parser.add_subparsers(dest="mode", required=True)

    p_survey = subs.add_parser("survey")
    p_survey.add_argument("repo")
    p_survey.add_argument("--stamp-date")

    p_check = subs.add_parser("check")
    p_check.add_argument("repo")
    p_check.add_argument("--doc")

    args = parser.parse_args(argv)
    repo = Path(args.repo)
    try:
        if args.mode == "survey":
            if not repo.is_dir() or not (repo / ".git").exists():
                raise _EngineError(f"not-a-repo: {repo} is not a git repository")
            stamp_date = args.stamp_date or date.today().isoformat()
            payload = cmd_survey(repo, stamp_date)
        else:
            if not repo.is_dir() or not (repo / ".git").exists():
                raise _EngineError(f"not-a-repo: {repo}")
            payload = cmd_check(repo, Path(args.doc) if args.doc else None)
    except _EngineError as exc:
        sys.stdout.write(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2) + "\n")
        return 2
    if args.mode == "survey":
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        return 0
    verdict = str(payload.get("verdict"))
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return {"fresh": 0, "stale": 1, "bootstrap-needed": 2, "doc-edited": 3}[verdict]


if __name__ == "__main__":
    sys.exit(main())
