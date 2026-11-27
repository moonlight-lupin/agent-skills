"""Mock terminal contracts. No vendor credentials, binaries or network."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("engineering", Path(__file__).resolve().parents[1] / "engineering.py")
engineering = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engineering)
ROOT = "/repo"
HEAD = "a" * 40

class State:
    def __init__(self):
        self.rows = {}
    def set(self, key, value):
        self.rows[key] = value
    def get(self, key, default=None):
        return self.rows.get(key, default)

class Context:
    def __init__(self):
        self.tools = {}
        self.state = State()
        self.config = {}
        self.calls = []
        self.head = HEAD
        self.dirty = ""
        self.missing = set()
        self.responses = {}
    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs
    def get_config(self, key, default=None):
        return self.config.get(key, default)
    def dispatch_tool(self, name, args, **kwargs):
        assert name == "terminal"
        assert args["workdir"] == ROOT
        cmd = args["command"]
        self.calls.append((cmd, kwargs))
        # Real dispatch_tool returns a JSON string; mirror that contract.
        def as_json(raw):
            return json.dumps(raw, ensure_ascii=False)
        if cmd in self.responses:
            return as_json(self.responses[cmd])
        if cmd == "git rev-parse --show-toplevel":
            return as_json({"exit_code": 0, "output": ROOT})
        if cmd == "git rev-parse HEAD":
            return as_json({"exit_code": 0, "output": self.head})
        if cmd.startswith("git status"):
            return as_json({"exit_code": 0, "output": self.dirty})
        if cmd.startswith("if test"):
            return as_json({"exit_code": 0, "output": "python"})
        if cmd.startswith("command -v "):
            name = cmd.split()[2]
            return as_json({"exit_code": 1, "output": ""} if name in self.missing else {"exit_code": 0, "output": "/usr/bin/" + name})
        return as_json({"exit_code": 0, "output": ""})

def test_plan_and_registration():
    ctx = Context()
    engineering.register_engineering(ctx)
    assert len(ctx.tools) == 8
    assert not ctx.calls
    for language in engineering.PROFILES:
        result = json.loads(engineering.plan({"language": language}))
        assert result["status"] == "planned_not_run"
        assert result["checks"][0]["id"] == "diff"
        assert all(c["command"] == engineering.CHECKS[c["id"]][0] for c in result["checks"])
    for args in (None, [], {"language": []}, {"language": "python; touch /tmp/x"}, {"network": "false"}):
        assert "error" in json.loads(engineering.plan(args))

def test_discovery_separates_binary_and_version():
    ctx = Context()
    tool = engineering.Engineering(ctx)
    ctx.missing.add("codex")
    ctx.config["allow_project_checks"] = True
    rows = tool.discover({"root": ROOT, "ids": ["claude", "codex"], "versions": True})["capabilities"]
    assert rows[0]["operational"] == "version_ok"
    assert rows[0]["authentication"] == "unknown"
    assert rows[1]["installed"] == "missing"
    assert "error" in tool.discover({"root": ROOT, "versions": True})

def test_install_default_deny_and_reprobe():
    ctx = Context()
    tool = engineering.Engineering(ctx)
    ctx.missing.add("ruff")
    assert tool.setup({"root": ROOT, "id": "ruff"})["status"] == "approval_required"
    assert not any("tool install" in cmd for cmd, _ in ctx.calls)
    ctx.config["install_allowlist"] = ["ruff"]
    ctx.config["allow_project_checks"] = True
    assert tool.setup({"root": ROOT, "id": "ruff"})["status"] == "not_verified"
    assert any(cmd == "uv tool install ruff" for cmd, _ in ctx.calls)

def test_network_and_project_policy():
    ctx = Context()
    tool = engineering.Engineering(ctx)
    assert "error" in tool.run({"root": ROOT, "check": "python_dependencies"})
    assert "error" in tool.run({"root": ROOT, "check": "python_lint"})
    assert not ctx.calls

def test_gate_missing_pass_stale_dirty_failed():
    ctx = Context()
    tool = engineering.Engineering(ctx)
    assert tool.gate({"root": ROOT})["verdict"] == "NOT_SHIP"
    assert tool.run({"root": ROOT, "check": "diff"}, task_id="t")["eligible"]
    assert all(k.get("task_id") == "t" for _, k in ctx.calls[-5:])
    assert tool.gate({"root": ROOT})["verdict"] == "ENGINEERING_PASS"
    ctx.head = "b" * 40
    assert tool.gate({"root": ROOT})["verdict"] == "NOT_SHIP"
    ctx.dirty = "?? file"
    assert not tool.run({"root": ROOT, "check": "diff"})["eligible"]
    assert tool.gate({"root": ROOT})["verdict"] == "NOT_SHIP"
    ctx.dirty = ""
    ctx.responses[engineering.CHECKS["diff"][0]] = {"exit_code": 2, "output": "bad"}
    assert tool.run({"root": ROOT, "check": "diff"})["status"] == "FINDINGS"
    assert tool.gate({"root": ROOT})["verdict"] == "NOT_SHIP"

def test_gate_requires_operator_checks():
    ctx = Context()
    tool = engineering.Engineering(ctx)
    ctx.config.update(required_checks=["python_lint"], allow_project_checks=True)
    tool.run({"root": ROOT, "check": "diff"})
    assert tool.gate({"root": ROOT})["verdict"] == "NOT_SHIP"
    tool.run({"root": ROOT, "check": "python_lint"})
    assert tool.gate({"root": ROOT})["verdict"] == "ENGINEERING_PASS"

def test_bad_terminal_envelopes_never_pass():
    for raw in ({}, {"exit_code": True}, {"exit_code": 0, "error": "blocked"},
                {"exit_code": 0, "cwd_fallback": "elsewhere"}, {"exit_code": 0, "session_id": "job"},
                {"exit_code": 0, "environment_recreated": True}, {"exit_code": 0, "status": "degraded"}):
        assert engineering.classify(raw) == "ERROR"

def test_non_json_terminal_response_fails_closed():
    ctx = Context()
    tool = engineering.Engineering(ctx)
    for raw in ("not-json", "", "[]", "null", "3"):
        ctx.responses["git rev-parse --show-toplevel"] = raw
        result = tool.snapshot(ROOT, {})
        assert "error" in result

def test_invalid_input_and_ast_quoting():
    ctx = Context()
    tool = engineering.Engineering(ctx)
    assert "error" in tool.run({"root": "/repo/../else", "check": "diff"})
    assert "error" in tool.run({"root": ROOT, "check": "git push"})
    ctx.config["allow_project_checks"] = True
    pattern = "'; echo PWN; #"
    tool.ast({"root": ROOT, "language": "python", "pattern": pattern})
    import shlex
    assert shlex.split(ctx.calls[-1][0]) == ["ast-grep", "run", "--lang", "python", "--pattern=" + pattern, "--json=compact", "."]

def test_lsp_and_auth_fail_closed():
    ctx = Context()
    tool = engineering.Engineering(ctx)
    assert tool.lsp({"root": ROOT})["status"] == "unavailable"
    assert "error" in tool.doctor({"root": ROOT, "auth": "claude"})
    ctx.responses["hermes lsp status --json"] = {"exit_code": 0, "output": json.dumps({"service": {"enabled": True}, "registry": [{"server_id": "pyright", "binary_status": "installed"}]})}
    assert tool.lsp({"root": ROOT})["servers"][0]["binary_status"] == "installed"


def test_inventory_rejects_incomplete_results():
    ctx = Context()
    tool = engineering.Engineering(ctx)
    assert "error" in tool.discover({"root": ROOT})

def test_bubblewrap_plugin_install_respects_allowlist():
    ctx = Context()
    ctx.responses["hermes plugins list --json"] = {"exit_code": 0, "output": "[]"}
    tool = engineering.Engineering(ctx)
    assert tool.setup({"root": ROOT, "id": "bubblewrap_plugin"})["status"] == "approval_required"
    ctx.config.update(allow_project_checks=True, install_allowlist=["bubblewrap_plugin"])
    assert tool.setup({"root": ROOT, "id": "bubblewrap_plugin"})["status"] == "not_verified"
    assert any(cmd == "hermes plugins install bubblewrap --enable" for cmd, _ in ctx.calls)

def test_hermes_managed_lsp_does_not_require_path():
    ctx = Context()
    ctx.responses["hermes lsp status --json"] = {
        "exit_code": 0, "output": json.dumps({"service": {"enabled": True},
        "registry": [{"server_id": "pyright", "binary_status": "installed"}]})}
    tool = engineering.Engineering(ctx)
    assert tool.probe("pyright", ROOT, {})["operational"] == "hermes_registry_installed"

def test_real_git_round_trip(tmp_path):
    import subprocess
    root = str(tmp_path.resolve())
    def git(*args):
        subprocess.run(["git", "-C", root, *args], check=True, capture_output=True)
    git("init")
    git("-c", "user.email=test@example.invalid", "-c", "user.name=Test", "commit", "--allow-empty", "-m", "init")
    class RealGit(Context):
        def dispatch_tool(self, name, args, **kwargs):
            assert name == "terminal" and args["workdir"] == root
            result = subprocess.run(args["command"], shell=True, cwd=root, capture_output=True, text=True, timeout=15)
            return json.dumps({"exit_code": result.returncode, "output": result.stdout + result.stderr}, ensure_ascii=False)
    tool = engineering.Engineering(RealGit())
    assert tool.run({"root": root, "check": "diff"})["status"] == "PASS"
    assert tool.gate({"root": root})["verdict"] == "ENGINEERING_PASS"
    (tmp_path / "new.txt").write_text("dirty\n")
    assert tool.gate({"root": root})["verdict"] == "NOT_SHIP"
    git("add", "new.txt")
    git("-c", "user.email=test@example.invalid", "-c", "user.name=Test", "commit", "-m", "change")
    assert tool.gate({"root": root})["verdict"] == "NOT_SHIP"
    assert tool.run({"root": root, "check": "diff"})["status"] == "PASS"
    assert tool.gate({"root": root})["verdict"] == "ENGINEERING_PASS"


def test_doctor_calls_existing_resolver_only_when_allowed():
    import shlex
    ctx = Context()
    tool = engineering.Engineering(ctx)
    assert tool.configured_lanes(ROOT, {})["status"] == "not_probed"
    assert not ctx.calls
    ctx.config["allow_project_checks"] = True
    script = Path(str(engineering.__file__)).resolve().parent / "skills/orchestrator/scripts/lanes.py"
    command = "python3 " + shlex.quote(str(script)) + " --repo " + shlex.quote(ROOT) + " detect"
    ctx.responses[command] = {"exit_code": 0, "output": json.dumps({"lanes": [{"lane": "controller"}]})}
    assert tool.configured_lanes(ROOT, {})["lanes"] == [{"lane": "controller"}]

def test_delegation_plugin_install_default_deny():
    ctx = Context()
    ctx.responses["hermes plugins list --json"] = {"exit_code": 0, "output": "[]"}
    tool = engineering.Engineering(ctx)
    assert tool.setup({"root": ROOT, "id": "advanced_delegation"})["status"] == "approval_required"

def test_degraded_envelope_is_never_missing():
    # Gate r2-C1: a degraded terminal envelope must never prove absence —
    # an approved install would otherwise run inside a degraded backend.
    ctx = Context()
    tool = engineering.Engineering(ctx)
    ctx.responses["command -v ruff"] = {"exit_code": 1, "environment_recreated": True}
    assert tool.probe("ruff", ROOT, {})["installed"] == "unknown"
    assert "error" in tool.setup({"root": ROOT, "id": "ruff"})

def test_gate_fail_closed_without_get_config():
    # Gate r2-O1: with no reachable config getter the operator's
    # required_checks policy is unknowable — the gate must refuse, not
    # silently fall back to diff-only.
    class NoConfigContext:
        """Minimal ctx with a terminal stub but NO get_config (gate r2-O1)."""

        def __init__(self):
            self.state = State()
            self.head = HEAD
            self.dirty = ""
            self.responses = {}
            self.calls = []

        def _as_json(self, raw):
            return json.dumps(raw, ensure_ascii=False)

        def dispatch_tool(self, name, args, **kwargs):
            cmd = args["command"]
            self.calls.append((cmd, kwargs))
            if cmd in self.responses:
                return self._as_json(self.responses[cmd])
            if cmd == "git rev-parse --show-toplevel":
                return self._as_json({"exit_code": 0, "output": ROOT})
            if cmd == "git rev-parse HEAD":
                return self._as_json({"exit_code": 0, "output": self.head})
            if cmd.startswith("git status"):
                return self._as_json({"exit_code": 0, "output": self.dirty})
            return self._as_json({"exit_code": 0, "output": ""})

    tool = engineering.Engineering(NoConfigContext())
    assert tool.has_config is False
    assert "error" in tool.required(ROOT, {}, ["python"])
    assert "error" in tool.gate({"root": ROOT})

def test_non_string_output_fails_closed():
    ctx = Context()
    tool = engineering.Engineering(ctx)
    for bad in (None, 5, {"nested": 1}):
        ctx.responses["git rev-parse --show-toplevel"] = {"exit_code": 0, "output": bad}
        assert "error" in tool.snapshot(ROOT, {})

def test_probed_findings_exit_codes():
    # Gate r2-O5: real findings must be recorded as FINDINGS, not ERROR.
    assert engineering.classify({"exit_code": 1}, engineering.CHECKS["go_static"][2]) == "FINDINGS"
    assert engineering.classify({"exit_code": 1}, engineering.CHECKS["go_tests"][2]) == "FINDINGS"
    assert engineering.classify({"exit_code": 101}, engineering.CHECKS["rust_static"][2]) == "FINDINGS"
    assert engineering.classify({"exit_code": 101}, engineering.CHECKS["rust_tests"][2]) == "FINDINGS"
    assert engineering.classify({"exit_code": 1}, engineering.CHECKS["js_dependencies"][2]) == "FINDINGS"
    # An exit code outside the findings set stays ERROR.
    assert engineering.classify({"exit_code": 101}, engineering.CHECKS["go_tests"][2]) == "ERROR"

def test_discover_language_detection_failure_contract():
    import shlex
    ctx = Context()
    tool = engineering.Engineering(ctx)
    cmds = []
    for lang, ms in engineering.MARKERS.items():
        cond = " || ".join("test -f " + shlex.quote(p) for p in ms)
        cmds.append("if " + cond + "; then printf '%s\\n' " + lang + "; fi")
    ctx.responses["; ".join(cmds)] = {"exit_code": 0, "output": "python\nnotalang"}
    out = tool.discover({"root": ROOT, "ids": ["git"]})
    assert out["languages"] is None
    assert out.get("languages_note") == "Project language detection failed"
    # The full inventory path requires language detection and fails closed.
    assert "error" in tool.discover({"root": ROOT})

class InventoryContext(Context):
    def dispatch_tool(self, name, args, **kwargs):
        cmd = args["command"]
        if "__DEV_PIPELINE_INVENTORY_END__" in cmd:
            rows = "\n".join(cid + "\t/usr/bin/" + cid for cid, data in engineering.CATALOG.items()
                             if data[1] and cid not in self.missing)
            return json.dumps({"exit_code": 0, "output": rows + "\n" + "__DEV_PIPELINE_INVENTORY_END__"})
        return super().dispatch_tool(name, args, **kwargs)

def test_doctor_full_path():
    # Gate r2-O8: the default doctor path (inventory, required, sandbox,
    # configured lanes) had no test coverage.
    import shlex
    ctx = InventoryContext()
    ctx.config.update(allow_project_checks=True, required_checks=["python_lint"])
    ctx.missing.add("ruff")
    tool = engineering.Engineering(ctx)
    script = Path(str(engineering.__file__)).resolve().parent / "skills/orchestrator/scripts/lanes.py"
    command = "python3 " + shlex.quote(str(script)) + " --repo " + shlex.quote(ROOT) + " detect"
    ctx.responses[command] = {"exit_code": 0, "output": json.dumps({"lanes": [{"lane": "claude"}]})}
    out = tool.doctor({"root": ROOT})
    assert out["required_checks"] == ["diff", "python_lint"]
    assert out["missing_requirements"] == ["ruff"]
    assert out["configured_lanes"]["status"] == "observed"
    assert out["sandbox"]["isolation_verified"] is False
