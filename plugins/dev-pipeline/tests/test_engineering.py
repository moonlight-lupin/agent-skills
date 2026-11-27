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
        if cmd in self.responses:
            return self.responses[cmd]
        if cmd == "git rev-parse --show-toplevel":
            return {"exit_code": 0, "output": ROOT}
        if cmd == "git rev-parse HEAD":
            return {"exit_code": 0, "output": self.head}
        if cmd.startswith("git status"):
            return {"exit_code": 0, "output": self.dirty}
        if cmd.startswith("if test"):
            return {"exit_code": 0, "output": "python"}
        if cmd.startswith("command -v "):
            name = cmd.split()[2]
            return {"exit_code": 1, "output": ""} if name in self.missing else {"exit_code": 0, "output": "/usr/bin/" + name}
        return {"exit_code": 0, "output": ""}

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
