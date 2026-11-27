"""Capability registry and terminal-backed evidence. No host subprocesses."""
import hashlib
import json
import posixpath
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path

# id: (category, binary aliases, version arguments, approved installation recipe)
# Project-local dependencies and vendor-specific installers are intentionally
# manual: never modify a lockfile, elevate privileges or download shell scripts.
CATALOG = {
    "git": ("core", ("git",), "--version", None),
    "gh": ("core", ("gh",), "--version", None),
    "hermes": ("agent", ("hermes",), "--version", None),
    "claude": ("agent", ("claude",), "--version", "npm install -g @anthropic-ai/claude-code"),
    "codex": ("agent", ("codex",), "--version", "npm install -g @openai/codex"),
    "cursor": ("agent", ("cursor-agent", "agent"), "--version", None),
    "muse": ("agent", ("muse",), "--version", None),
    "gemini": ("agent", ("gemini",), "--version", "npm install -g @google/gemini-cli"),
    "opencode": ("agent", ("opencode",), "--version", "npm install -g opencode-ai"),
    "aider": ("agent", ("aider",), "--version", "uv tool install aider-chat"),
    "ast_grep": ("navigation", ("ast-grep", "sg"), "--version", "npm install -g @ast-grep/cli"),
    "ripgrep": ("navigation", ("rg",), "--version", None),
    "tree_sitter": ("navigation", ("tree-sitter",), "--version", "npm install -g tree-sitter-cli"),
    "ruff": ("python", ("ruff",), "--version", "uv tool install ruff"),
    "mypy": ("python", ("mypy",), "--version", "uv tool install mypy"),
    "pyright": ("lsp", ("pyright", "pyright-langserver"), "--version", "hermes lsp install pyright"),
    "pytest": ("python", ("pytest",), "--version", None),
    "coverage": ("python", ("coverage",), "--version", None),
    "mutmut": ("python", ("mutmut",), "--version", None),
    "eslint": ("javascript", ("./node_modules/.bin/eslint", "eslint"), "--version", None),
    "tsc": ("javascript", ("./node_modules/.bin/tsc", "tsc"), "--version", None),
    "biome": ("javascript", ("./node_modules/.bin/biome", "biome"), "--version", None),
    "vitest": ("javascript", ("./node_modules/.bin/vitest", "vitest"), "--version", None),
    "jest": ("javascript", ("./node_modules/.bin/jest", "jest"), "--version", None),
    "playwright": ("javascript", ("./node_modules/.bin/playwright", "playwright"), "--version", None),
    "typescript_lsp": ("lsp", ("typescript-language-server",), "--version", "hermes lsp install typescript"),
    "go": ("go", ("go",), "version", None),
    "gopls": ("lsp", ("gopls",), "version", "hermes lsp install gopls"),
    "golangci_lint": ("go", ("golangci-lint",), "version", None),
    "cargo": ("rust", ("cargo",), "--version", None),
    "clippy": ("rust", ("cargo-clippy",), "--version", "rustup component add clippy"),
    "rust_analyzer": ("lsp", ("rust-analyzer",), "--version", "hermes lsp install rust-analyzer"),
    "cargo_audit": ("security", ("cargo-audit",), "--version", "cargo install cargo-audit --locked"),
    "bandit": ("security", ("bandit",), "--version", "uv tool install bandit"),
    "pip_audit": ("security", ("pip-audit",), "--version", "uv tool install pip-audit"),
    "semgrep": ("security", ("semgrep",), "--version", "uv tool install semgrep"),
    "gitleaks": ("security", ("gitleaks",), "version", None),
    "trivy": ("security", ("trivy",), "--version", None),
    "snyk": ("security", ("snyk",), "--version", "npm install -g snyk"),
    "bubblewrap": ("isolation", ("bwrap",), "--version", None),
    "bubblewrap_plugin": ("isolation", (), "", "hermes plugins install bubblewrap --enable"),
    "advanced_delegation": ("agent", (), "", "hermes plugins install advanced-delegation --enable"),
    "prlimit": ("isolation", ("prlimit",), "--version", None),
    "docker": ("isolation", ("docker",), "--version", None),
    "uv": ("package", ("uv",), "--version", None),
    "pipx": ("package", ("pipx",), "--version", None),
    "npm": ("package", ("npm",), "--version", None),
    "pnpm": ("package", ("pnpm",), "--version", None),
    "rustup": ("package", ("rustup",), "--version", None),
}
# check: command, prerequisite capability, findings exit codes, network required
CHECKS = {
    "diff": ("git show --format= --check --first-parent HEAD && git diff --check HEAD --", "git", (2,), False),
    "python_lint": ("ruff check .", "ruff", (1,), False),
    "python_types": ("mypy .", "mypy", (1,), False),
    "python_security": ("bandit -r . -x ./.git,./.venv,./venv,./node_modules", "bandit", (1,), False),
    "python_dependencies": ("pip-audit", "pip_audit", (1,), True),
    "python_tests": ("pytest", "pytest", (1,), False),
    # findings exit codes probed live 2026-11-27: go vet findings -> 1,
    # go test failures -> 1, clippy -D warnings -> 101, cargo test failures
    # -> 101; npm audit/npm test and cargo audit report findings exit 1.
    "python_coverage": ("coverage run -m pytest && coverage report", "coverage", (1,), False),
    "js_lint": ("if [ -x ./node_modules/.bin/eslint ]; then ./node_modules/.bin/eslint .; else eslint .; fi", "eslint", (1,), False),
    "js_types": ("if [ -x ./node_modules/.bin/tsc ]; then ./node_modules/.bin/tsc --noEmit; else tsc --noEmit; fi", "tsc", (1, 2), False),
    "js_dependencies": ("npm audit --json", "npm", (1,), True),
    "js_tests": ("npm test", "npm", (1,), False),
    "go_static": ("GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local go vet ./...", "go", (1,), False),
    "go_tests": ("GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local go test ./...", "go", (1,), False),
    "rust_static": ("cargo clippy --offline --locked --all-targets -- -D warnings", "clippy", (101,), False),
    "rust_tests": ("cargo test --offline --locked", "cargo", (101,), False),
    "rust_dependencies": ("cargo audit", "cargo_audit", (1,), True),
    "secrets": ("gitleaks git --redact --no-banner --log-opts=-1", "gitleaks", (1,), False),
    "semgrep": ("semgrep scan --config auto --error --metrics=off", "semgrep", (1,), True),
    "trivy": ("trivy fs --scanners vuln,misconfig,secret --exit-code 1 .", "trivy", (1,), True),
    "snyk": ("snyk test", "snyk", (1,), True),
    "ast_search_help": ("ast-grep run --help", "ast_grep", (), False),
}
PROFILES = {
    "python": ("diff", "python_lint", "python_types", "python_security"),
    "javascript": ("diff", "js_lint", "js_types"),
    "go": ("diff", "go_static"),
    "rust": ("diff", "rust_static"),
    "generic": ("diff",),
}
NETWORK_CHECKS = {"python": "python_dependencies", "javascript": "js_dependencies", "rust": "rust_dependencies"}
LSP_IDS = {"pyright": "pyright", "typescript_lsp": "typescript", "gopls": "gopls", "rust_analyzer": "rust-analyzer"}
AUTH = {"claude": "claude auth status", "codex": "codex login status", "gh": "gh auth status"}
MARKERS = {
    "python": ("pyproject.toml", "setup.py", "requirements.txt", "uv.lock", "setup.cfg"),
    "javascript": ("package.json", "tsconfig.json"),
    "go": ("go.mod", "go.work"),
    "rust": ("Cargo.toml",),
}
SHA = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SAFE_PATH = re.compile(r"^/[^\x00-\x1f\x7f]*$")
EVIDENCE_SCHEMA = "dev-pipeline-engineering.v1"

def dump(obj):
    return json.dumps(obj, ensure_ascii=False)

def error(message):
    return {"error": message}

def plan(args, **kwargs):
    if not isinstance(args, dict):
        return dump(error("Expected an object"))
    language = args.get("language", "generic")
    network = args.get("network", False)
    if not isinstance(language, str) or language not in PROFILES or type(network) is not bool:
        return dump(error("Invalid language or network"))
    ids = list(PROFILES[language])
    if network and language in NETWORK_CHECKS:
        ids.append(NETWORK_CHECKS[language])
    return dump({"status": "planned_not_run", "language": language,
                 "checks": [{"id": k, "command": CHECKS[k][0], "requires": CHECKS[k][1],
                             "network": CHECKS[k][3]} for k in ids],
                 "cautions": ["Prefer repo CI and project-local tools; planner output is not evidence.",
                              "No automatic install or network without operator policy.",
                              "Run acceptance tests and retain independent review."]})

def degraded(raw):
    """True for any terminal envelope that must never yield a determination."""
    if not isinstance(raw, dict):
        return True
    return bool(raw.get("error") or raw.get("status") in ("degraded", "blocked", "running", "pending", "timeout")
                or any(raw.get(k) for k in ("cwd_fallback", "environment_recreated", "promoted_from_foreground", "session_id")))

def classify(raw, findings=()):
    if degraded(raw):
        return "ERROR"
    rc = raw.get("exit_code")
    if type(rc) is not int:
        return "ERROR"
    if rc in (126, 127):
        return "UNAVAILABLE"
    if rc == 0:
        return "PASS"
    if rc in findings:
        return "FINDINGS"
    return "ERROR"

def valid_path(path):
    return isinstance(path, str) and bool(SAFE_PATH.fullmatch(path)) and path == posixpath.normpath(path) and not path.startswith("//")

class Engineering:
    def __init__(self, ctx):
        self.ctx = ctx
        self.has_config = callable(getattr(ctx, "get_config", None))

    def config(self, key, default):
        getter = getattr(self.ctx, "get_config", None)
        return getter(key, default) if callable(getter) else default

    def dispatch(self, cmd, root, kw, timeout=60):
        if not valid_path(root):
            return error("Explicit absolute normalized POSIX repository path required")
        dispatcher = getattr(self.ctx, "dispatch_tool", None)
        if not callable(dispatcher):
            return error("Hermes terminal dispatch unavailable; update Hermes")
        context = {k: kw[k] for k in ("task_id", "session_id") if isinstance(kw.get(k), str)}
        try:
            raw = dispatcher("terminal", {"command": cmd, "workdir": root, "timeout": timeout}, **context)
            raw = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(raw, dict) and not isinstance(raw.get("output", ""), str):
                return error("Malformed terminal response: output not a string")
            return raw if isinstance(raw, dict) else error("Malformed terminal response")
        except Exception as exc:
            return error("Terminal dispatch failed: " + type(exc).__name__)

    def snapshot(self, root, kw):
        result = self.dispatch("git rev-parse --show-toplevel", root, kw)
        if classify(result) != "PASS" or result.get("output", "").strip() != root:
            return error("Cannot verify requested repository root (use canonical root; no cwd fallback)")
        head = self.dispatch("git rev-parse HEAD", root, kw)
        status = self.dispatch("git status --porcelain=v1 --untracked-files=all", root, kw)
        if classify(head) != "PASS" or classify(status) != "PASS":
            return error("Cannot establish repository snapshot")
        sha = head.get("output", "").strip()
        if not SHA.fullmatch(sha):
            return error("Invalid commit SHA")
        return {"root": root, "head": sha, "clean": not status.get("output", "").strip()}

    def plugin_status(self, name, root, kw):
        raw = self.dispatch("hermes plugins list --json", root, kw, 30)
        try:
            rows = json.loads(raw.get("output", "")) if classify(raw) == "PASS" else None
        except (ValueError, TypeError):
            rows = None
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            return {"installed": "unknown"}
        matches = [r for r in rows if r.get("name") == name]
        if len(matches) > 1:
            return {"installed": "unknown"}
        if not matches:
            return {"installed": "missing"}
        row = matches[0]
        return {"installed": "present", "version": str(row.get("version", ""))[:100],
                "configured": row.get("status"), "operational": "not_probed"}

    def probe(self, cid, root, kw, version=False):
        category, aliases, flag, recipe = CATALOG[cid]
        if cid in ("bubblewrap_plugin", "advanced_delegation"):
            plugin = {"bubblewrap_plugin": "bubblewrap", "advanced_delegation": "advanced-delegation"}[cid]
            return {"id": cid, "category": category, "installable": True,
                    **self.plugin_status(plugin, root, kw)}
        if cid in LSP_IDS:
            # Hermes-managed servers may live outside PATH. Prefer its own
            # registry over a shell lookup, but do not equate this to gateway readiness.
            observed = self.lsp({"root": root}, **kw)
            matches = [r for r in observed.get("servers", []) if r.get("id") == LSP_IDS[cid]]
            if len(matches) == 1 and matches[0].get("binary_status") == "installed":
                return {"id": cid, "category": category, "installed": "present", "installable": bool(recipe),
                        "operational": "hermes_registry_installed", "authentication": "not_applicable"}
        # No user-controlled strings in the command. Use explicit local paths,
        # otherwise PATH resolution. sg is also a system group tool, so never
        # accept that alias as ast-grep without a positive version signature.
        if cid == "ast_grep":
            aliases = ("ast-grep",)
        command = " || ".join("command -v " + shlex.quote(a) for a in aliases)
        raw = self.dispatch(command, root, kw)
        if classify(raw) != "PASS":
            # A degraded envelope is never proof of absence: it must never
            # become "missing" or an approved install runs in a degraded
            # terminal (gate finding r2-C1).
            state = "missing" if raw.get("exit_code") == 1 and not degraded(raw) else "unknown"
            return {"id": cid, "category": category, "installed": state, "installable": bool(recipe)}
        path = raw.get("output", "").strip()
        if not path or "\n" in path or "\r" in path:
            return {"id": cid, "category": category, "installed": "unknown", "installable": bool(recipe)}
        result = {"id": cid, "category": category, "installed": "present", "path": path,
                  "installable": bool(recipe), "operational": "not_probed", "authentication": "unknown"}
        if version:
            # Resolve the same alias again in terminal; quote output rather
            # than executing it as shell source. Only absolute or catalog-local paths.
            if valid_path(path) or (path in aliases and path.startswith("./")):
                r = self.dispatch(shlex.quote(path) + " " + flag, root, kw, 20)
                result["operational"] = "version_ok" if classify(r) == "PASS" else "version_failed"
                if classify(r) == "PASS":
                    result["version"] = str(r.get("output", ""))[:300]
            else:
                result["operational"] = "unrecognized_path"
        return result

    def languages(self, root, kw):
        # Fixed test expressions; print only known language labels.
        cmds = []
        for lang, markers in MARKERS.items():
            condition = " || ".join("test -f " + shlex.quote(p) for p in markers)
            cmds.append("if " + condition + "; then printf '%s\\n' " + lang + "; fi")
        raw = self.dispatch("; ".join(cmds), root, kw)
        if classify(raw) != "PASS":
            return None
        lines = raw.get("output", "").splitlines()
        if any(line not in MARKERS for line in lines):
            return None
        return list(dict.fromkeys(lines)) or ["generic"]

    def discover(self, args, **kw):
        root = args.get("root")
        ids = args.get("ids", [])
        version = args.get("versions", False)
        if not valid_path(root) or not isinstance(ids, list) or any(not isinstance(k, str) or k not in CATALOG for k in ids) or type(version) is not bool:
            return error("Invalid root, capability ids or versions")
        if version and (not ids or len(ids) > 3):
            return error("Version probing is bounded to 1–3 explicitly selected capabilities")
        if version and self.config("allow_project_checks", False) is not True:
            return error("Operator must enable allow_project_checks before executing version probes")
        langs = self.languages(root, kw)
        if not ids:
            if langs is None:
                return error("Project language detection failed (gate finding r2-M1)")
            # One shell dispatch for the default inventory; version and auth
            # probes are deliberately separate to avoid slow/networking CLIs.
            lines = []
            for cid, (cat, aliases, flag, recipe) in CATALOG.items():
                if not aliases:
                    continue
                if cid == "ast_grep":
                    aliases = ("ast-grep",)
                lookup = " || ".join("command -v " + shlex.quote(a) for a in aliases)
                lines.append("if p=$(" + lookup + "); then printf '%s\\t%s\\n' " + cid + ' "$p"; fi')
            raw = self.dispatch("; ".join(lines) + "; printf '%s\\n' __DEV_PIPELINE_INVENTORY_END__", root, kw)
            if classify(raw) != "PASS":
                return error("Inventory probe failed; no absence inferred")
            present = {}
            output = raw.get("output", "").splitlines()
            if not output or output[-1] != "__DEV_PIPELINE_INVENTORY_END__":
                return error("Incomplete inventory")
            for line in output[:-1]:
                cid, sep, path = line.partition("\t")
                if not sep or cid not in CATALOG or not path or cid in present:
                    return error("Malformed or truncated inventory")
                present[cid] = path
            # A terminal spill/truncation is not a reliable negative result.
            if raw.get("full_output_path") or raw.get("output_total_chars"):
                return error("Inventory output spilled; probe selected ids")
            rows = [{"id": cid, "category": data[0], "installed": "present" if cid in present else "missing",
                     "path": present.get(cid), "installable": bool(data[3]),
                     "operational": "not_probed", "authentication": "unknown"} for cid, data in CATALOG.items() if data[1]]
            rows.extend(self.probe(cid, root, kw) for cid in ("bubblewrap_plugin", "advanced_delegation"))
            lsp = self.lsp({"root": root}, **kw)
            installed_servers = {r["id"] for r in lsp.get("servers", []) if r.get("binary_status") == "installed"}
            for row in rows:
                if LSP_IDS.get(row["id"]) in installed_servers:
                    row.update(installed="present", operational="hermes_registry_installed")
        else:
            rows = [self.probe(cid, root, kw, version) for cid in dict.fromkeys(ids)]
        return {"languages": langs,
                **({"languages_note": "Project language detection failed"} if langs is None and ids else {}),
                "capabilities": rows,
                "lane_candidates": [r["id"] for r in rows if r["category"] == "agent" and CATALOG[r["id"]][1] and r["installed"] == "present"],
                "routing": "Use existing lanes.py detect/doctor/resolve; binary presence is not a lane approval or verified model family."}

    def doctor(self, args, **kw):
        root = args.get("root")
        if not valid_path(root):
            return error("Invalid root")
        cid = args.get("auth")
        if cid is not None:
            if not isinstance(cid, str) or cid not in AUTH:
                return error("No supported auth probe for this capability")
            if self.config("allow_auth_probes", False) is not True:
                return error("Operator must enable allow_auth_probes; probes may contact vendor services")
            raw = self.dispatch(AUTH[cid], root, kw, 30)
            # Do not return raw account/credential output.
            return {"id": cid, "authentication": "probe_passed" if classify(raw) == "PASS" else "not_verified",
                    "operational": "model_dispatch_not_tested"}
        inv = self.discover({"root": root}, **kw)
        if "error" in inv:
            return inv
        required = self.required(root, kw, inv["languages"])
        if isinstance(required, dict):
            return required
        by = {r["id"]: r for r in inv["capabilities"]}
        inv["required_checks"] = required
        inv["missing_requirements"] = sorted({CHECKS[k][1] for k in required if by[CHECKS[k][1]]["installed"] != "present"})
        inv["sandbox"] = self.sandbox(root, kw)
        inv["configured_lanes"] = self.configured_lanes(root, kw)
        return inv

    def configured_lanes(self, root, kw):
        if self.config("allow_project_checks", False) is not True:
            return {"status": "not_probed", "note": "Enable allow_project_checks to inspect project lane configuration"}
        script = Path(__file__).resolve().parent / "skills/orchestrator/scripts/lanes.py"
        # Execute the existing resolver in the same environment as checks.
        # It may be intentionally hidden by remote/sandbox backends. Never
        # compensate by running it on the plugin host.
        raw = self.dispatch("python3 " + shlex.quote(str(script)) + " --repo " + shlex.quote(root) + " detect", root, kw, 30)
        try:
            result = json.loads(raw.get("output", "")) if classify(raw) == "PASS" else None
        except (ValueError, TypeError):
            result = None
        if not isinstance(result, dict) or not isinstance(result.get("lanes"), list):
            return {"status": "unavailable", "note": "Run bundled lanes.py detect in the coding environment"}
        return {"status": "observed", "lanes": result["lanes"],
                "note": "Existing lane resolver is authoritative; presence is not login, quota or model entitlement."}

    def sandbox(self, root, kw):
        # A config read is advisory, not an attestation of actual containment.
        raw = self.dispatch("hermes config get terminal.backend", root, kw, 20)
        val = str(raw.get("output", "")).strip()
        known = ("local", "bubblewrap", "docker", "ssh", "modal", "daytona", "vercel_sandbox")
        backend = val if classify(raw) == "PASS" and val in known else "unknown"
        return {"configured_backend": backend, "plugin": self.plugin_status("bubblewrap", root, kw), "isolation_verified": False,
                "note": "Run hermes doctor on host and configure terminal.degraded_mode=fail. Worktrees are not sandboxes; config is not proof of effective containment."}

    def setup(self, args, **kw):
        root, cid = args.get("root"), args.get("id")
        if not valid_path(root) or not isinstance(cid, str) or cid not in CATALOG:
            return error("Invalid root or capability id")
        current = self.probe(cid, root, kw)
        recipe = CATALOG[cid][3]
        if current["installed"] == "present":
            return {"status": "already_present", "capability": current}
        if current["installed"] != "missing":
            return error("Cannot establish absence; refusing installation")
        if not recipe:
            return {"status": "manual_setup_required", "id": cid,
                    "note": "Use operator-managed vendor/OS install or repository lockfile. Bubblewrap: install OS bwrap/prlimit and official Hermes plugin; configure backend explicitly."}
        allowed = self.config("install_allowlist", [])
        if not isinstance(allowed, list) or cid not in allowed:
            return {"status": "approval_required", "id": cid, "command": recipe,
                    "note": "Operator must add capability id to install_allowlist outside the agent. No sudo, arbitrary URL, or shell installer."}
        if self.config("allow_project_checks", False) is not True:
            return error("Operator must enable allow_project_checks before installation in this environment")
        raw = self.dispatch(recipe, root, kw, 180)
        after = self.probe(cid, root, kw, version=True) if classify(raw) == "PASS" else None
        verified = after and (after.get("operational") in ("version_ok", "hermes_registry_installed")
                              or cid in ("bubblewrap_plugin", "advanced_delegation") and after.get("configured") == "enabled")
        return {"status": "installed" if verified else "not_verified",
                "id": cid, "command": recipe, "exit_code": raw.get("exit_code"), "capability": after,
                "note": "Installation does not authenticate coding agents or select their model."}

    def lsp(self, args, **kw):
        root, action = args.get("root"), args.get("action", "status")
        if not valid_path(root):
            return error("Invalid root")
        if action == "install":
            cid = args.get("id")
            if not isinstance(cid, str) or cid not in LSP_IDS:
                return error("Unknown language server")
            return self.setup({"root": root, "id": cid}, **kw)
        if action != "status":
            return error("Unknown LSP action")
        raw = self.dispatch("hermes lsp status --json", root, kw, 30)
        try:
            info = json.loads(raw.get("output", "")) if classify(raw) == "PASS" else None
        except (ValueError, TypeError):
            info = None
        if not isinstance(info, dict):
            return {"status": "unavailable", "note": "LSP CLI not accessible in this backend; use host hermes lsp status"}
        service = info.get("service")
        registry = info.get("registry")
        if not isinstance(service, dict) or not isinstance(registry, list):
            return error("Unexpected LSP status schema")
        return {"status": "observed", "enabled": service.get("enabled"),
                "servers": [{"id": r.get("server_id"), "binary_status": r.get("binary_status")} for r in registry if isinstance(r, dict)],
                "note": "This CLI reports its own service, not necessarily gateway clients. Native write_file/patch diagnostics are advisory; full-project checks still required."}

    def required(self, root, kw, langs=None):
        # Operator controls additional required checks, not model arguments.
        if not self.has_config:
            return error("Cannot read operator config (no ctx.get_config); refusing to assume required_checks empty (gate finding r2-O1)")
        if langs is None:
            langs = self.languages(root, kw)
        if langs is None:
            return error("Project language detection failed")
        additional = self.config("required_checks", [])
        if not isinstance(additional, list) or any(not isinstance(k, str) or k not in CHECKS or k == "ast_search_help" for k in additional):
            return error("Invalid operator required_checks")
        # Generic diff is mandatory; language-specific requirements are
        # operator-selected to avoid forcing mypy on projects without it.
        return list(dict.fromkeys(["diff", *additional]))

    def key(self, root, check):
        return "engineering-" + hashlib.sha256((root + "\0" + check).encode()).hexdigest()

    def run(self, args, **kw):
        root, check = args.get("root"), args.get("check")
        if not valid_path(root) or not isinstance(check, str) or check not in CHECKS:
            return error("Invalid root or check")
        command, capability, findings, network = CHECKS[check]
        if network and self.config("allow_network_checks", False) is not True:
            return error("Operator must enable allow_network_checks")
        if self.config("allow_project_checks", False) is not True and check != "diff":
            return error("Operator must enable allow_project_checks for repository code execution in an approved backend")
        before = self.snapshot(root, kw)
        if "error" in before:
            return before
        probe = self.probe(capability, root, kw)
        if probe["installed"] != "present":
            raw = error("Capability missing or unknown")
            status = "UNAVAILABLE" if probe["installed"] == "missing" else "ERROR"
        else:
            raw = self.dispatch(command, root, kw, 180)
            status = classify(raw, findings)
        after = self.snapshot(root, kw)
        eligible = before == after and before["clean"]
        evidence = {"schema": EVIDENCE_SCHEMA, "check": check, "command": command, "snapshot": before,
                    "after": after, "eligible": eligible, "status": status,
                    "exit_code": raw.get("exit_code"), "at": datetime.now(timezone.utc).isoformat(),
                    "output_tail": str(raw.get("output", ""))[-3000:]}
        try:
            self.ctx.state.set(self.key(root, check), evidence)
        except Exception:
            return {"status": "ERROR", "note": "Evidence persistence failed; cannot gate", "evidence": evidence}
        return evidence

    def gate(self, args, **kw):
        root = args.get("root")
        if not valid_path(root):
            return error("Invalid root")
        snap = self.snapshot(root, kw)
        if "error" in snap:
            return snap
        required = self.required(root, kw)
        if isinstance(required, dict):
            return required
        blocked = []
        if not snap["clean"]:
            blocked.append({"reason": "dirty_or_untracked_worktree"})
        for check in required:
            try:
                row = self.ctx.state.get(self.key(root, check), default=None)
            except Exception:
                row = None
            if not isinstance(row, dict):
                blocked.append({"check": check, "reason": "missing"})
            elif (row.get("schema") != EVIDENCE_SCHEMA or row.get("check") != check
                  or row.get("command") != CHECKS[check][0] or row.get("snapshot") != snap
                  or row.get("after") != snap or row.get("eligible") is not True):
                blocked.append({"check": check, "reason": "stale_or_unbound"})
            elif row.get("status") != "PASS" or row.get("exit_code") != 0:
                blocked.append({"check": check, "reason": row.get("status", "invalid")})
        # Not a release authorization. Existing acceptance suite and review
        # gates still apply, including the T3 live-deploy rule.
        return {"verdict": "NOT_SHIP" if blocked else "ENGINEERING_PASS",
                "snapshot": snap, "required": required, "blockers": blocked,
                "note": "Engineering gate only; not a security boundary or substitute for CI, acceptance tests or independent review."}

    def ast(self, args, **kw):
        root, lang, pattern = args.get("root"), args.get("language"), args.get("pattern")
        if not valid_path(root) or not isinstance(lang, str) or lang not in ("python", "javascript", "typescript", "tsx", "go", "rust") or not isinstance(pattern, str) or not pattern or len(pattern) > 1000 or "\0" in pattern:
            return error("Invalid AST search")
        if self.config("allow_project_checks", False) is not True:
            return error("Operator must enable allow_project_checks")
        raw = self.dispatch("ast-grep run --lang " + lang + " --pattern=" + shlex.quote(pattern) + " --json=compact .", root, kw)
        return {"status": classify(raw), "exit_code": raw.get("exit_code"), "output": str(raw.get("output", ""))[:12000],
                "note": "Read-only structural search; nonzero may mean no matches or error. Not release evidence."}

def register_engineering(ctx):
    service = Engineering(ctx)
    root = {"type": "string", "description": "Canonical absolute POSIX repository root in the active terminal backend"}
    sid = {"type": "string", "enum": list(CATALOG)}
    def reg(name, desc, props, required, handler):
        ctx.register_tool(name=name, toolset="dev-pipeline", description=desc,
                          schema={"name": name, "description": desc, "parameters": {
                              "type": "object", "properties": props, "required": required, "additionalProperties": False}},
                          handler=handler)
    def wrap(fn):
        def handle(args, **kw):
            if not isinstance(args, dict):
                return dump(error("Expected object"))
            return dump(fn(args, **kw))
        return handle
    reg("dev_pipeline_engineering_plan", "Suggest fixed checks; not execution",
        {"language": {"type": "string", "enum": list(PROFILES)}, "network": {"type": "boolean"}}, ["language"], plan)
    reg("dev_pipeline_discover", "Discover tools in active terminal; bounded version probes require allow_project_checks",
        {"root": root, "ids": {"type": "array", "items": sid}, "versions": {"type": "boolean"}}, ["root"], wrap(service.discover))
    reg("dev_pipeline_doctor", "Diagnose prerequisites, configured backend and opt-in auth probes",
        {"root": root, "auth": {"type": "string", "enum": list(AUTH)}}, ["root"], wrap(service.doctor))
    reg("dev_pipeline_setup", "Install absent allowlisted capability using fixed recipe, then verify version",
        {"root": root, "id": sid}, ["root", "id"], wrap(service.setup))
    reg("dev_pipeline_lsp", "Observe native Hermes LSP readiness or install approved server",
        {"root": root, "action": {"type": "string", "enum": ["status", "install"]}, "id": {"type": "string", "enum": list(LSP_IDS)}}, ["root"], wrap(service.lsp))
    reg("dev_pipeline_engineering_run", "Execute one fixed check and store commit-bound evidence",
        {"root": root, "check": {"type": "string", "enum": list(CHECKS)}}, ["root", "check"], wrap(service.run))
    reg("dev_pipeline_gate", "Fail closed on missing, failed or stale mandatory engineering evidence",
        {"root": root}, ["root"], wrap(service.gate))
    reg("dev_pipeline_ast_search", "Read-only ast-grep structural search; ast-grep may load project sgconfig.yml custom parsers",
        {"root": root, "language": {"type": "string", "enum": ["python", "javascript", "typescript", "tsx", "go", "rust"]},
         "pattern": {"type": "string"}}, ["root", "language", "pattern"], wrap(service.ast))
