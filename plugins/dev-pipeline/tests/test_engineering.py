"""Contract tests for the pure planner; no external binaries or network."""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "engineering", Path(__file__).resolve().parents[1] / "engineering.py")
engineering = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engineering)

def test_profiles_are_fixed_and_not_executed():
    for language in engineering.PROFILES:
        result = json.loads(engineering.plan({"language": language}))
        assert result["status"] == "planned_not_run"
        assert result["checks"][0]["id"] == "diff"
        assert all(c["command"] == engineering.CHECKS[c["id"]][0] for c in result["checks"])
        assert not any(c["id"].endswith("dependencies") for c in result["checks"])

def test_dependency_audits_are_opt_in():
    for language in ("python", "javascript"):
        result = json.loads(engineering.plan({"language": language, "network": True}))
        assert result["checks"][-1]["id"] == engineering.NETWORK_CHECKS[language]

def test_reject_bad_input():
    for args in (None, [], {"language": []}, {"language": "python; touch /tmp/x"},
                 {"language": "python", "network": "false"}):
        assert "error" in json.loads(engineering.plan(args))

def test_registration():
    class Context:
        def register_tool(self, **kwargs):
            self.tool = kwargs
    ctx = Context()
    engineering.register_engineering(ctx)
    assert ctx.tool["name"] == "dev_pipeline_engineering_plan"
    assert ctx.tool["handler"] is engineering.plan
    assert ctx.tool["schema"]["parameters"]["additionalProperties"] is False
