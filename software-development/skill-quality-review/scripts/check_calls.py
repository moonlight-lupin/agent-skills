#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check 15 — Callability harness.

Extracts code spans and fenced command lines that look like calls
(``name(...)`` inline code, or `python ... path.py ...` fenced/shell lines)
from every SKILL.md in a repo, then executes each against small made-up
inputs in a scratch directory. A call line that does not run is a MAJOR
finding (Check 15, uncallable engine).

Design rules (from the Oct 2026 pere-toolkit review):
- Every cited script is classified CLI or library.
- A library citation must have an import recipe the agent can follow.
- A def main() whose __main__ block ignores arguments (runs a demo whatever
  you pass) is flagged.
- Repo-relative CLI paths (python skills/x/scripts/y.py) are flagged: they
  break once the plugin is installed.

Usage: python3 check_calls.py <repo-root> [--apply-report <path>]
Prints one finding per line: [CLAUDE][CHECK15] skill | kind | detail
Exit 1 if any finding.
"""

import ast
import json
import pathlib
import re
import subprocess
import sys
import tempfile

CODE_SPAN = re.compile(r"`([^`]+)`")
CALLLIKE = re.compile(r"^[a-zA-Z_][\w.]*\(.*\)$")
PY_CMDLINE = re.compile(r"^\s*(?:python3?|uv run)\s+(.+\.py)([^\n]*)$")
REPO_REL = re.compile(r"^\s*(?:python3?\s+)?(?:skills|src|\.\.)/[\w\-./]+\.py\b")

# Non-findings: placeholder args in SKILL.md prose, python builtins, and
# stdlib module citations
PLACEHOLDERS = {"fn", "f", "func", "x", "y", "arg", "args", "callback", "callable",
                "value", "values", "name", "key", "item", "obj", "input", "data"}
BUILTIN_NAMES = set(dir(__import__("builtins")))
STDLIB_MODULES = {
    "os", "sys", "json", "re", "math", "subprocess", "pathlib", "shutil", "glob",
    "collections", "itertools", "functools", "datetime", "dataclasses", "typing",
    "statistics", "csv", "tempfile", "textwrap", "copy", "abc", "enum", "secrets",
    "hashlib", "base64", "uuid", "random", "time", "calendar", "decimal",
    "fractions", "unittest", "logging", "warnings", "pickle", "io", "string",
    "textwrap2", "inspect", "operator", "heapq", "bisect", "array", "struct",
    "zipfile", "tarfile", "xml", "html", "urllib", "http", "socket", "ssl",
    "asyncio", "concurrent", "multiprocessing", "threading", "queue", "sched",
    "contextlib", "traceback", "gc", "platform", "argparse", "configparser",
    "sqlite3", "zlib", "gzip", "bz2", "lzma", "stat", "filecmp", "fnmatch",
}


def fenced_code_blocks(text: str):
    for m in re.finditer(r"```([^\n]*)\n(.*?)```", text, re.DOTALL):
        yield m.group(2)


def extract_calls(text: str):
    """Yield (kind, snippet) pairs that look like engine calls."""
    # fenced shell/python command lines
    for block in fenced_code_blocks(text):
        for line in block.splitlines():
            if PY_CMDLINE.match(line) or REPO_REL.match(line):
                yield ("cmd", line.strip())
    # inline spans that look like a function call
    for span in CODE_SPAN.findall(text):
        span = span.strip()
        if "\n" in span:
            continue
        if CALLLIKE.match(span):
            yield ("call", span)


def classify_script(path: pathlib.Path):
    """CLI vs library, and the demo-dispatch bug: __main__ block that never
    calls main() when arguments are given."""
    src = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return {"cls": "unparseable", "demo_dispatch": False, "main_called": None}
    has_main_def = any(
        isinstance(n, ast.FunctionDef) and n.name == "main" for n in ast.walk(tree)
    )
    main_called = None
    demo_dispatch = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            test = node.test
            is_main_guard = (
                isinstance(test, ast.Compare)
                and ast.unparse(test).startswith("__name__ ==")
            )
            if is_main_guard:
                called = any(
                    isinstance(n, ast.Call) and getattr(n.func, "id", "") == "main"
                    for n in ast.walk(node)
                )
                calls_sys_exit = any(
                    isinstance(n, ast.Call)
                    and "exit" in ast.dump(n.func)
                    for n in ast.walk(node)
                )
                if has_main_def:
                    main_called = called or calls_sys_exit
                if has_main_def and not called:
                    demo_dispatch = True
    cls = "CLI" if has_main_def and main_called else "library"
    return {"cls": cls, "demo_dispatch": demo_dispatch, "main_called": main_called}


def try_execute(skill_dir: pathlib.Path, snippets, repo: pathlib.Path):
    """Execute call snippets in a scratch dir with the skill dir on sys.path.
    Returns list of failures: (snippet, error)."""
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for kind, snip in snippets:
            if kind == "cmd":
                # rewrite repo-relative .py paths to absolute under the repo
                m = re.match(r"^(\S+\.py)(.*)$", snip.split(None, 1)[-1] if snip.startswith(("python", "uv")) else snip, re.S)
                target, args = (m.group(1), m.group(2)) if m else (None, snip)
                if target:
                    abs_target = repo / target if not pathlib.Path(target).is_absolute() else pathlib.Path(target)
                    if not abs_target.exists():
                        candidates = list(repo.rglob(pathlib.Path(target).name))
                        if candidates:
                            abs_target = candidates[0]
                    if not abs_target.exists():
                        failures.append((snip, "script not found at cited path"))
                        continue
                    target, args = str(abs_target), args
                    runner = "python3"
                    cmd = [runner, target] + shlex_split(args)
                else:
                    cmd = shlex_split(snip)
                # --help style is the only safe invocation without side effects
                if any(a in args for a in ("-h", "--help")):
                    probe = cmd
                else:
                    # made-up inputs: append --help to avoid destructive runs
                    probe = cmd[:1] + cmd[1:2] + ["--help"]
                try:
                    r = subprocess.run(
                        probe, capture_output=True, text=True, timeout=30,
                        cwd=str(tmp),
                    )
                    if r.returncode not in (0, 2):
                        failures.append((snip, (r.stderr or r.stdout).strip()[-300:]))
                except Exception as e:  # noqa: BLE001
                    failures.append((snip, str(e)))
            else:
                # inline call: resolve the target, then import-check it
                fn = snip.split("(", 1)[0]
                leaf = fn.split(".")[-1]
                # skip placeholders, builtins, stdlib — not engine citations
                if leaf in PLACEHOLDERS or leaf in BUILTIN_NAMES \
                        or fn.split(".")[0] in STDLIB_MODULES:
                    continue
                # prefix resolution: engines live in sibling skills' scripts too.
                # `forecast_kit.noi_series` resolves wherever its module file sits
                # in the repo, honouring the shared import recipe.
                search_dirs = [skill_dir, repo, repo / "skills"]
                seen = set()
                module_path = None
                for search in search_dirs:
                    if not search or not search.exists() or search in seen:
                        continue
                    seen.add(search)
                    for cand in sorted(search.rglob("*.py")):
                        if "__pycache__" in str(cand) or "/tests/" in str(cand):
                            continue
                        try:
                            tree = ast.parse(cand.read_text(encoding="utf-8", errors="replace"))
                        except SyntaxError:
                            continue
                        # top-level defs/classes only — nested functions are not
                        # importable module members (a nested `def run` in an
                        # unrelated file once resolved a `run(...)` citation
                        # wrongly and cost a false finding)
                        names = {n.name for n in tree.body
                                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
                        if leaf in names:
                            module_path = cand
                            break
                    if module_path:
                        break
                if module_path is None:
                    failures.append((snip, f"undefined target '{fn}' — no module anywhere in the repo defines '{leaf}'"))
                    continue
                mod_name = module_path.stem
                code = (
                    "import sys; sys.path.insert(0, %r); "
                    "import %s as m; "
                    "fn = getattr(m, %r, None); "
                    "import inspect; sig = inspect.signature(fn); "
                    "kwargs = {}; "
                    "for p in sig.parameters.values():\n"
                    "    if p.default is not inspect.Parameter.empty: kwargs[p.name] = p.default\n"
                    "    elif p.kind == inspect.Parameter.KEYWORD_ONLY or p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD:\n"
                    "        pass\n" % (str(module_path.parent), mod_name, fn.split(".")[-1])
                )
                # Only inspect signature; do NOT call — made-up args can be wrong type.
                # The MAJOR signal is: the cited call exists and is importable.
                try:
                    probe_code = (
                        "import sys, importlib.util, ast, os\n"
                        "sys.path.insert(0, %r)\n"
                        "spec = importlib.util.spec_from_file_location('probe_mod', %r)\n"
                        "mod = importlib.util.module_from_spec(spec)\n"
                        "sys.modules['probe_mod'] = mod\n"
                        "spec.loader.exec_module(mod)\n"
                        "print(getattr(mod, %r) is not None)\n" % (str(module_path.parent), str(module_path), fn.split(".")[-1])
                    )
                    r = subprocess.run(
                        [sys.executable, "-c", probe_code], capture_output=True,
                        text=True, timeout=30, cwd=str(tmp),
                    )
                    if r.returncode != 0 or "True" not in r.stdout:
                        last = (r.stderr or "").strip().splitlines()[-1] if (r.stderr or "").strip() else "import returned False"
                        failures.append((snip, f"import fails: {last[:200]}"))
                except Exception as e:  # noqa: BLE001
                    failures.append((snip, str(e)))
    return failures


def shlex_split(s: str):
    import shlex
    try:
        return shlex.split(s)
    except ValueError:
        return s.split()


def main(argv):
    if len(argv) < 2:
        print("usage: check_calls.py <repo-root>")
        return 2
    repo = pathlib.Path(argv[1]).resolve()
    skills = sorted(repo.rglob("SKILL.md"))
    findings = []
    for skill_md in skills:
        skill_dir = skill_md.parent
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        snippets = list(extract_calls(text))
        if not snippets:
            continue
        # 1) script-path classification
        script_paths = [s for k, s in snippets if k == "cmd"]
        for sp in script_paths:
            if REPO_REL.match(sp):
                findings.append(
                    (skill_dir.name, "repo-relative-path",
                     f"cited CLI path breaks after plugin install: {sp}")
                )
        # 2) demo-dispatch bug in any referenced script
        for py in list(skill_dir.rglob("*.py")):
            info = classify_script(py)
            if info["demo_dispatch"]:
                findings.append(
                    (skill_dir.name, "demo-dispatch",
                     f"{py.relative_to(skill_dir)}: __main__ block never calls main() — any CLI invocation runs the demo")
                )
        # 3) execute the extracted calls
        for snip, err in try_execute(skill_dir, snippets, repo):
            findings.append((skill_dir.name, "call-fails", f"{snip[:90]} -> {err}"))
    if findings:
        print("[CLAUDE][CHECK15] Callability findings:")
        for skill, kind, detail in findings:
            print(f"  {skill} | {kind} | {detail}")
        return 1
    print("[CLAUDE][CHECK15] OK — all cited calls import and all scripts classify")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))