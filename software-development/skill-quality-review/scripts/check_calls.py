#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check 15 — Callability harness.

Extracts call-like spans and command lines from every SKILL.md in a repo,
then verifies each against the repo's code WITHOUT executing engine logic:

- command lines (`python ... path.py ...`): the cited path must resolve;
  safe `--help` probes run with sys.executable (never a bare "python3",
  which is absent on Windows).
- inline call spans (`name(...)`, `module.name(...)`): parsed with ast,
  then bound against the resolved function's inspect.signature with
  placeholder objects. A call that cannot bind — missing required keyword,
  unknown keyword, too many positional arguments — is a MAJOR finding
  (Check 15, wrong call line). Function bodies are never called.
- module-prefixed spans must resolve to a module file matching the prefix
  (`scenario_kit._apply_many` must live in a module named scenario_kit);
  alias imports (`import model_kit as mk`) are honoured.
- private names (leading `_`) are flagged: skills must not cite them.
- bare function-name spans cited directly after a script path
  (``scripts/x.py`` `name`) must be top-level names of that module —
  return-dict keys cited as functions fail this (`plates`, `code`).
- NO-RECIPE: a skill citing a library script with no import-recipe line
  ("Calling the engines / sys.path recipe") is flagged. This rule
  reproduced the 6 Oct reviewer's hand-count exactly: 39 of 52 pere
  skills at d4e0a2c. CLI citations do not need a recipe.
- a `def main()` whose `__main__` block ignores arguments (prints a demo
  whatever you pass) is flagged; the demo-dispatch scan runs for EVERY
  skill — even one with no call snippets (density_calc.py was missed
  when the scan was skipped for snippet-less skills).

Usage: python3 check_calls.py <repo-root>
Prints one finding per line: [CLAUDE][CHECK15] skill | kind | detail
Exit 1 if any finding, 0 clean, 2 usage error.
"""

import ast
import importlib.util
import inspect
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile

CODE_SPAN = re.compile(r"`([^`\n]+)`")
CALLLIKE = re.compile(r"^[a-zA-Z_][\w.]*\(.*\)$")
PY_CMDLINE = re.compile(r"^\s*(?:python3?|uv run)\s+(.+\.py)([^\n]*)$")
REPO_REL = re.compile(
    r"(?:^\s*|(?:python3?\s+|uv\s+run\s+))?(?:skills|src|\.\.)/[\w\-./]+\.py\b")
MOD_KEY_ADJ = re.compile(r"`([a-z_][\w]*)`\s*\(?`(\w[\w]*)`\)?")
NO_RECIPE_RE = re.compile(r"Calling the engines|sys\.path|import recipe", re.I)
ENGINE_CALL_RE = re.compile(r"`[a-z_][\w]*\.[a-zA-Z_]\w*\(")

SKIP_DIR_PARTS = {"_workings", "node_modules", ".git", "__pycache__", ".venv"}
ROUTER_SKILLS = {"getting-started", "workflow-recipes"}

PLACEHOLDERS = {"fn", "f", "func", "x", "y", "arg", "args", "callback", "callable",
                "value", "values", "name", "key", "item", "obj", "input", "data",
                "deal", "over", "overrides", "result", "res", "out"}
TOOL_NAMES = {"terminal", "search_files", "read_file", "write_file", "patch",
              "execute_code", "web_search", "web_extract", "skill_view",
              "delegate_task", "todo_list", "browser_exec", "cronjob"}
VALUE_SINGLETONS = {"none", "null", "nil", "true", "false", "standard",
                    "regulatory", "cash", "committed", "subject"}
BUILTIN_NAMES = set(dir(__import__("builtins")))
STDLIB_MODULES = {
    "os", "sys", "json", "re", "math", "subprocess", "pathlib", "shutil", "glob",
    "collections", "itertools", "functools", "datetime", "dataclasses", "typing",
    "statistics", "csv", "tempfile", "copy", "abc", "enum", "secrets",
    "hashlib", "base64", "uuid", "random", "time", "calendar", "decimal",
    "fractions", "unittest", "logging", "warnings", "pickle", "io", "string",
    "inspect", "operator", "heapq", "bisect", "array", "struct",
    "zipfile", "tarfile", "xml", "html", "urllib", "http", "socket", "ssl",
    "asyncio", "concurrent", "multiprocessing", "threading", "queue", "sched",
    "contextlib", "traceback", "gc", "platform", "argparse", "configparser",
    "sqlite3", "zlib", "gzip", "bz2", "lzma", "stat", "filecmp", "fnmatch",
    "tomllib",
}


def fenced_code_blocks(text: str):
    for m in re.finditer(r"```[^\n]*\n(.*?)```", text, re.DOTALL):
        yield m.group(1)


def extract_calls(text: str):
    """Yield (kind, snippet, offset) triples that look like engine citations."""
    for block_m in re.finditer(r"```[^\n]*\n(.*?)```", text, re.DOTALL):
        block_start = block_m.start(1)
        for line in block_m.group(1).splitlines():
            if PY_CMDLINE.match(line) or REPO_REL.search(line):
                yield ("cmd", line.strip(), block_start)
    for m in CODE_SPAN.finditer(text):
        span = m.group(1).strip()
        if REPO_REL.search(span) and ".py" in span:
            yield ("cmd-inline", span, m.start(1))
            continue
        if CALLLIKE.match(span):
            yield ("call", span, m.start(1))
            continue
        # call fragments inside spans: `cf = mk.xirr(scenario_kit._apply_many(
        # base, overrides))` — assignments and nested calls. Extract each
        # `name(` whose parens close inside the span.
        for cm in re.finditer(r"[a-zA-Z_][\w.]*(?:\.)?[a-zA-Z_]\w*\(", span):
            start = cm.start()
            depth = 0
            for i in range(start, len(span)):
                if span[i] == "(":
                    depth += 1
                elif span[i] == ")":
                    depth -= 1
                    if depth == 0:
                        frag = span[start:i + 1]
                        if CALLLIKE.match(frag) and frag != span:
                            # notation chains ("NOI = NRA(sqft) × rate(£/sqft)")
                            # and non-ASCII unit glosses (£) are prose, not calls
                            if "×" in span or "→" in span or any(
                                    ord(ch) > 127 for ch in frag):
                                break
                            yield ("call-frag", frag, m.start(1))
                        break


def script_kind(path: pathlib.Path):
    """CLI vs library, and the demo-dispatch bug: __main__ block that never
    calls main() when a def main exists."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError, ValueError):
        return {"cls": "unparseable", "demo_dispatch": False}
    has_main_def = any(
        isinstance(n, ast.FunctionDef) and n.name == "main" for n in ast.walk(tree))
    demo_dispatch = False
    main_called = False
    exit_dispatch = False
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and ast.unparse(node.test).startswith(
                "__name__ =="):
            calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
            called = any(getattr(n.func, "id", "") == "main" for n in calls)
            if has_main_def and not called:
                demo_dispatch = True
            if called:
                main_called = True
            # sys.exit(<call>()) is a CLI dispatch even without def main
            # (comps_evidence pattern). print-then-sys.exit(0) demos are not.
            exit_dispatch = any(
                isinstance(n.func, ast.Attribute) and n.func.attr == "exit"
                and bool(n.args) and isinstance(n.args[0], ast.Call)
                for n in calls)
    cls = "CLI" if (main_called or exit_dispatch) else "library"
    return {"cls": cls, "demo_dispatch": demo_dispatch}


def build_repo_index(repo: pathlib.Path):
    """Parse each .py once: leaf name -> {stem: path} top-level names,
    module stem -> paths."""
    top_names = {}
    module_files = {}
    for dp, dns, fns in os.walk(repo):
        dns[:] = [d for d in dns if d not in SKIP_DIR_PARTS
                  and not d.startswith(".")]
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            path = pathlib.Path(dp) / fn
            if any(part in SKIP_DIR_PARTS or part == "tests"
                   for part in path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8",
                                                errors="replace"))
            except (SyntaxError, OSError, ValueError):
                continue
            stem = path.stem
            module_files.setdefault(stem, []).append(path)
            for n in tree.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                    top_names.setdefault(n.name, {})[stem] = path
    return top_names, module_files


def resolve(fn: str, leaf: str, skill_dir: pathlib.Path, repo: pathlib.Path,
            top_names, module_files):
    """Resolve a cited call target, honouring the module prefix. A prefixed
    span must resolve to a module file matching the prefix — leaf-only
    matching resolved monthly_model.run into the wrong file on the pere run.
    Returns (module_path | None, prefix)."""
    prefix = fn.split(".")[0] if "." in fn else None
    if prefix:
        cands = module_files.get(prefix, [])
        if not cands:
            return None, prefix
        for cand in cands:
            try:
                tree = ast.parse(cand.read_text(encoding="utf-8",
                                                errors="replace"))
            except (SyntaxError, OSError, ValueError):
                continue
            top = {n.name for n in tree.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef))}
            if leaf in top:
                return cand, prefix
        return None, prefix
    by_leaf = top_names.get(leaf, {})
    near = [p for p in by_leaf.values() if skill_dir in p.parents]
    if near:
        return sorted(near, key=lambda p: str(p))[0], None
    if by_leaf:
        return sorted(by_leaf.values(), key=lambda p: str(p))[0], None
    return None, None


def resolve_all(fn: str, leaf: str, skill_dir: pathlib.Path, repo: pathlib.Path,
                top_names):
    """ALL module paths defining the leaf, skill-local first (pere has
    `noi_of` in three modules and `run` in five; an unprefixed prose span
    may reference any of them)."""
    by_leaf = top_names.get(leaf, {})
    near = [p for p in by_leaf.values() if skill_dir in p.parents]
    far = [p for p in by_leaf.values() if skill_dir not in p.parents]
    return (sorted(near, key=lambda p: str(p))
            + sorted(far, key=lambda p: str(p)))


class _Placeholder:
    def __repr__(self):
        return "<made-up>"


def _has_concrete_call(text: str, leaf: str):
    """Does the text carry a non-ellipsis call for this leaf anywhere?"""
    for m in CODE_SPAN.finditer(text):
        s = m.group(1).strip()
        if not CALLLIKE.match(s):
            continue
        if s.split("(", 1)[0].split(".")[-1] != leaf:
            continue
        body = s[s.find("("):]
        if body.strip() not in ("()", "(...)") and "…" not in body \
                and "..." not in body:
            return True
    return False


def _ellipsis_only(args, kwargs):
    if not args and not kwargs:
        return True
    return (len(args) == 1 and isinstance(args[0], ast.Constant)
            and args[0].value is Ellipsis)


def _has_bare_name_args(call):
    """Illustrative fragments in prose cite constructors with undefined bare
    names (`Deal(exit_noi_forward=True, exit_noi_growth=g)` — `g` is a
    prose variable, not an argument list). Any ast.Name argument marks the
    span as a fragment; **spreads and *args too."""
    def _scan(nodes):
        for node in nodes:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name) or isinstance(sub, ast.Starred):
                    return True
        return False
    if _scan(call.args):
        return True
    kw_values = [kw.value for kw in call.keywords if kw.arg is not None
                 and not isinstance(kw.value, ast.Constant)]
    if _scan(kw_values):
        return True
    if any(kw.arg is None for kw in call.keywords):
        return True  # **spread
    return False


def load_module(path: pathlib.Path, cwd_tmp: str = None):
    """exec_module with the module's own directory on sys.path (sibling
    imports like `import osm_map` need it) and cwd in the scratch dir."""
    spec = importlib.util.spec_from_file_location("probe_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["probe_mod"] = mod
    mod_dir = str(path.parent)
    added = mod_dir not in sys.path
    if added:
        sys.path.insert(0, mod_dir)
    cwd0 = os.getcwd()
    if cwd_tmp:
        os.chdir(cwd_tmp)
    try:
        spec.loader.exec_module(mod)
    finally:
        if cwd_tmp:
            os.chdir(cwd0)
        if added:
            sys.path.remove(mod_dir)
    return mod


def bind_check(fn: str, snippet: str, fn_obj, skill_has_recipe: bool):
    """Bind the snippet's arguments against the real signature without
    calling. Returns an error string or None."""
    if fn_obj is None:
        return None
    try:
        call = ast.parse(snippet if not snippet.startswith("`") else snippet[1:-1])
    except SyntaxError:
        return None  # not an arg-list; the name-resolution checks already ran
    found = None
    for node in ast.walk(call):
        if isinstance(node, ast.Call) and node is not call:
            found = node
            break
    if found is None:
        if isinstance(call, ast.Call):
            found = call
        else:
            return None
    call = found
    try:
        sig = inspect.signature(fn_obj)
    except (TypeError, ValueError):
        return None
    if _has_bare_name_args(call):
        return None  # illustrative fragment, not an argument list
    if _ellipsis_only(call.args, call.keywords):
        # generic signature: acceptable when the skill carries the import
        # recipe naming where the verified call lines live (v0.11 shape);
        # binds-fail is the finding when there is no recipe (d4 shape:
        # bid_level(...) with valuation_date nowhere)
        if skill_has_recipe:
            return None
        required = [p.name for p in sig.parameters.values()
                    if p.default is inspect.Parameter.empty
                    and p.kind is not inspect.Parameter.VAR_KEYWORD
                    and p.kind is not inspect.Parameter.VAR_POSITIONAL]
        if required:
            return f"missing required argument(s): {', '.join(required)}"
        return None
    args, kwargs = [], {}
    try:
        for a in call.args:
            if isinstance(a, ast.Starred):
                return None
            args.append(_Placeholder())
        for k in call.keywords:
            if k.arg is None:
                return None
            kwargs[k.arg] = _Placeholder()
        sig.bind(*args, **kwargs)
    except TypeError as e:
        return f"bind fails: {e}"
    return None


def try_verify(skill_dir: pathlib.Path, snippets, repo: pathlib.Path,
               top_names, module_files, text_full: str):
    """Verify call snippets without executing engine logic.
    Returns list of failures: (snippet, error)."""
    failures = []
    has_recipe = bool(NO_RECIPE_RE.search(text_full))
    with tempfile.TemporaryDirectory() as tmp:
        for kind, snip, offset in snippets:
            if kind in ("cmd", "cmd-inline"):
                m = re.search(REPO_REL, snip)
                if m:
                    rel = m.group(0).strip()
                    target = repo / rel
                    if not target.exists() and not list(
                            repo.rglob(pathlib.Path(rel).name)):
                        failures.append(
                            (snip, "script not found at cited repo-relative path"))
                        continue
                m2 = re.match(
                    r"^(?:python3?\s+|uv\s+run\s+)?(\S+)\s*(.*)$",
                    snip.split(None, 1)[-1]
                    if snip.startswith(("python", "uv")) else snip)
                target2, args = ((m2.group(1), m2.group(2)) if m2
                                 else (None, snip))
                t_path = pathlib.Path(target2)
                if t_path.is_absolute():
                    candidates = [t_path] if t_path.exists() else []
                else:
                    candidates = ([repo / target2]
                                  if (repo / target2).exists() else [])
                    if not candidates:
                        candidates = list(repo.rglob(t_path.name))[:1]
                if not candidates:
                    continue
                probe_cmd = [sys.executable, str(candidates[0])]
                if any(a in args for a in ("-h", "--help")):
                    probe_cmd += shlex.split(args) if args else []
                else:
                    probe_cmd += ["--help"]
                try:
                    r = subprocess.run(probe_cmd, capture_output=True,
                                       text=True, timeout=30, cwd=tmp)
                    if r.returncode not in (0, 2):
                        out = (r.stderr or r.stdout).strip()
                        last = out.splitlines()[-1] if out else \
                            f"exit {r.returncode}"
                        failures.append((snip, last[:200]))
                except Exception as e:  # noqa: BLE001
                    failures.append((snip, f"probe: {e}"))
                continue
            # inline call span
            fn = snip.split("(", 1)[0]
            prefix0 = fn.split(".")[0]
            alias_m = (re.search(
                r"import\s+(\w+)\s+as\s+" + re.escape(prefix0) + r"\b",
                text_full)
                or re.search(  # prose alias: "`mk` = `model_kit`"
                    r"`" + re.escape(prefix0) + r"`\s*=\s*`(\w+)`",
                    text_full))
            if alias_m and "." in fn and alias_m.group(1) not in (prefix0,):
                fn = alias_m.group(1) + "." + fn.split(".", 1)[1]
            leaf = fn.split(".")[-1]
            if leaf in PLACEHOLDERS or leaf in BUILTIN_NAMES \
                    or leaf in TOOL_NAMES or fn.split(".")[0] in STDLIB_MODULES:
                continue
            module_path, prefix = resolve(fn, leaf, skill_dir, repo,
                                          top_names, module_files)
            if module_path is None:
                if prefix:
                    failures.append(
                        (snip, f"prefix '{prefix}' matches no module file in "
                               f"the repo (dict key cited as a function?)"))
                elif kind != "call-frag":
                    # undefined-target on frags is prose noise (recipe-local
                    # names like date, domain abbreviations); whole spans only
                    failures.append(
                        (snip, f"undefined target '{fn}' — no module anywhere "
                               f"in the repo defines '{leaf}'"))
                continue
            if leaf.startswith("_"):
                failures.append(
                    (snip, f"private name: '{fn}' starts with '_' — skills "
                           f"must cite public API"))
                continue
            try:
                mod = load_module(module_path, tmp)
            except Exception as e:  # noqa: BLE001
                s = str(e).strip()
                failures.append((snip, f"import fails: "
                                       f"{s.splitlines()[-1][:200] if s else 'error'}"))
                continue
            # pointer spans ("feeds ... through `x.to_leases(...)`") are
            # descriptive cross-references, not run instructions
            before = text_full[max(0, offset - 161):offset].rstrip("`")
            if re.search(r"\b(?:through|via)\s*$", before) and \
                    re.search(
                        r"^[\w\-./]*\w\.[\w.]+\((?:\.{3}|…|\s*)?\)$",
                        snip):
                continue
            fn_obj = getattr(mod, leaf, None)
            if fn_obj is None and kind == "call-frag":
                continue  # frag member-mismatch is triage context, not a finding
            if fn_obj is None:
                failures.append(
                    (snip, f"'{leaf}' is not a top-level member of "
                           f"{module_path.name} — return-dict key cited as a "
                           f"function?"))
                continue
            err = bind_check(fn, snip, fn_obj, has_recipe)
            if err and prefix is None:
                # duplicate leaf names across modules: acceptable when ANY
                # module defining the leaf accepts the cited arguments
                for cand in resolve_all(fn, leaf, skill_dir, repo, top_names):
                    try:
                        cmod = load_module(cand, tmp)
                        if bind_check(fn, snip, getattr(cmod, leaf, None),
                                      has_recipe) is None:
                            err = None
                            break
                    except Exception:  # noqa: BLE001
                        continue
            if err:
                failures.append((snip, err))
    return failures


def check_no_recipe(skill_md: pathlib.Path, text: str, repo: pathlib.Path,
                    kind_cache, findings):
    """A skill citing a library script with no import-recipe line is a
    finding. Reproduced the reviewer's 39/52 hand-count at d4e0a2c."""
    if NO_RECIPE_RE.search(text):
        return
    if skill_md.parent.name in ROUTER_SKILLS:
        return
    if (skill_md.parent / "scripts" / "check_calls.py").exists():
        return  # the harness skill itself carries and documents the recipe
    libs = []
    for m in re.finditer(r"`([\w\-./]+\.py)`", text):
        sp = m.group(1)
        parts = pathlib.PurePosixPath(sp).parts
        if "tests" in parts or "assets" in parts:
            continue  # test files and sample assets are not engine citations
        if sp in kind_cache:
            kind = kind_cache[sp]
        else:
            if (repo / sp).exists():
                cands = [repo / sp]
            else:
                cands = list(repo.rglob(pathlib.Path(sp).name))
            kind = script_kind(cands[0]) if cands else None
            kind_cache[sp] = kind
        if kind is None or kind.get("cls") == "library":
            libs.append(sp)
    if libs:
        uniq = sorted(set(libs))
        head = ", ".join(uniq[:3]) + ("…" if len(uniq) > 3 else "")
        findings.append(
            (skill_md.parent.name, "no-recipe",
             f"cites {len(libs)} library script(s) ({head}) with no import "
             f"recipe line (Calling the engines / sys.path recipe)"))


def check_mod_key_adjacency(skill_md: pathlib.Path, text: str, findings,
                            module_files):
    """`design_kit` (`plates` — a module span directly followed by a bare
    key span reads as a function citation. If the key is not a top-level
    member of that module, flag. Value enumerations (`approvals` `none`,
    `png` (`None`)) are skipped: the module span there does not name a
    real module file, and singleton values are not callable anyway."""
    for m in MOD_KEY_ADJ.finditer(text):
        mod_name, key = m.group(1), m.group(2)
        if mod_name in STDLIB_MODULES or key in PLACEHOLDERS \
                or key.lower() in VALUE_SINGLETONS:
            continue
        if mod_name not in module_files:
            continue  # not a module file stem — not an engine citation
        hits = []
        for p in module_files.get(mod_name, []):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8",
                                             errors="replace"))
            except (SyntaxError, OSError, ValueError):
                continue
            top = {n.name for n in tree.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef))}
            if key in top:
                hits.append(p)
        if not hits:
            findings.append(
                (skill_md.parent.name, "key-as-call",
                 f"`{mod_name}` (`{key}`) — '{key}' is not a top-level member "
                 f"of {mod_name}; config/return-dict keys must not be cited "
                 f"as functions"))


def main(argv):
    if len(argv) < 2:
        print("usage: check_calls.py <repo-root>")
        return 2
    repo = pathlib.Path(argv[1]).resolve()
    if not repo.is_dir():
        print(f"not a directory: {repo}")
        return 2
    top_names, module_files = build_repo_index(repo)
    findings = []
    kind_cache = {}
    for skill_md in sorted(repo.rglob("SKILL.md")):
        rel_parts = skill_md.relative_to(repo).parts
        if any(part in SKIP_DIR_PARTS or part.startswith(".")
               for part in rel_parts):
            continue
        skill_dir = skill_md.parent
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        snippets = list(extract_calls(text))
        check_no_recipe(skill_md, text, repo, kind_cache, findings)
        check_mod_key_adjacency(skill_md, text, findings, module_files)
        for kind, sp, _ in snippets:
            if kind in ("cmd", "cmd-inline") and re.match(
                    r"^(?:python3?\s+)?(?:skills|src)/", sp):
                findings.append(
                    (skill_dir.name, "repo-relative-path",
                     f"cited CLI path breaks after plugin install: {sp[:90]}"))
        # demo-dispatch scan runs for EVERY skill — even with no snippets
        for py in sorted(skill_dir.rglob("*.py")):
            if any(p in SKIP_DIR_PARTS for p in py.parts):
                continue
            info = script_kind(py)
            if info["demo_dispatch"]:
                findings.append(
                    (skill_dir.name, "demo-dispatch",
                     f"{py.relative_to(skill_dir)}: __main__ block never calls "
                     f"main() — any CLI invocation runs the demo"))
        for snip, err in try_verify(skill_dir, snippets, repo, top_names,
                                    module_files, text):
            findings.append(
                (skill_dir.name, "call-defect", f"{snip[:90]} -> {err}"))
    if findings:
        print("[CLAUDE][CHECK15] Callability findings:")
        for skill, kind, detail in findings:
            print(f"  {skill} | {kind} | {detail}")
        return 1
    print("[CLAUDE][CHECK15] OK — all cited calls bind and all scripts classify")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))