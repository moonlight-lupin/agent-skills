"""Unit tests for the CLI arm runner tool (plugins/dev-pipeline/tools/run_arm.py).

Covers ONLY: verdict extraction, run-record building from a fake log + fake
claude JSON blob, the clean-config-dir copy logic (tmp dirs), codex flag
building with and without a git repo, and the muse quota-abort path
(monkeypatched usage call — no live CLI calls, no network).
"""
import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

TOOL_PATH = Path(__file__).resolve().parents[1] / "tools" / "run_arm.py"
_spec = importlib.util.spec_from_file_location("dev_pipeline_run_arm", TOOL_PATH)
run_arm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = run_arm
_spec.loader.exec_module(run_arm)


# --------------------------------------------------------------------------
# verdict extraction
# --------------------------------------------------------------------------

def test_verdict_found_at_tail():
    log = "finding A ...\nfinding B ...\nVERDICT: APPROVE\n"
    assert run_arm.extract_verdict(log) == "APPROVE"


def test_verdict_last_match_in_tail_wins():
    log = "VERDICT: REJECT\nfinal answer: VERDICT: SHIP\n"
    assert run_arm.extract_verdict(log) == "SHIP"


def test_verdict_reject_and_ship_forms():
    assert run_arm.extract_verdict("VERDICT: REJECT\n") == "REJECT"
    assert run_arm.extract_verdict("VERDICT: SHIP\n") == "SHIP"


def test_verdict_beyond_final_200_chars_is_missing():
    filler = "x" * 250
    log = "VERDICT: APPROVE\n" + filler
    assert run_arm.extract_verdict(log) is None


def test_verdict_missing_or_lowercase():
    assert run_arm.extract_verdict("all good, no verdict line\n") is None
    assert run_arm.extract_verdict("") is None
    assert run_arm.extract_verdict("verdict: approve\n") == "APPROVE"


# --------------------------------------------------------------------------
# run-record building (fake log + fake claude JSON blob)
# --------------------------------------------------------------------------

def fake_claude_log(verdict_line="VERDICT: SHIP\n"):
    blob = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "num_turns": 4,
            "total_cost_usd": 0.0123,
            "usage": {"input_tokens": 210, "output_tokens": 55},
        }
    )
    return (
        "warning: low disk\n"
        "warning: something else\n"
        + blob
        + "\n"
        + verdict_line
    )


def started_and_ended():
    started = datetime.now().astimezone()
    return started, started + timedelta(seconds=90)


def test_claude_reviewer_record_from_fake_log():
    started, ended = started_and_ended()
    record = run_arm.build_run_record(
        arm="claude",
        role="reviewer",
        model="glm-5.3",
        workdir="/tmp/w",
        prompt_file="/tmp/p.txt",
        log_path="/tmp/l.log",
        started=started,
        ended=ended,
        exit_code=0,
        log_text=fake_claude_log(),
    )
    assert record["arm"] == "claude"
    assert record["model"] == "glm-5.3"
    assert record["turns"] == 4
    assert record["cost_usd"] == 0.0123
    assert record["tokens_out"] == 55
    assert record["verdict"] == "SHIP"
    assert record["elapsed_s"] == 90.0
    assert record["exit_code"] == 0
    # ISO with local zone: both timestamps carry an offset
    assert record["started_local"] == started.isoformat()
    assert "+" in record["ended_local"] or "-" in record["ended_local"]


def test_claude_coder_record_has_null_verdict():
    started, ended = started_and_ended()
    record = run_arm.build_run_record(
        arm="claude",
        role="coder",
        model="glm-5.3",
        workdir="/tmp/w",
        prompt_file="/tmp/p.txt",
        log_path="/tmp/l.log",
        started=started,
        ended=ended,
        exit_code=0,
        log_text=fake_claude_log(),
    )
    assert record["verdict"] is None
    assert record["turns"] == 4


def test_nested_json_object_does_not_shadow_outer_blob():
    # The inner usage object starts LAST; the record must still read the
    # outer blob (the "last complete" object means top-level, not innermost).
    log = (
        "noise\n"
        '{"result":"partial","usage":{"output_tokens":9}}\n'
        + json.dumps(
            {
                "num_turns": 7,
                "total_cost_usd": 0.5,
                "usage": {"output_tokens": 120},
            }
        )
        + "\nVERDICT: APPROVE\n"
    )
    started, ended = started_and_ended()
    record = run_arm.build_run_record(
        arm="claude",
        role="reviewer",
        model="glm-5.3",
        workdir="/tmp/w",
        prompt_file="/tmp/p.txt",
        log_path="/tmp/l.log",
        started=started,
        ended=ended,
        exit_code=0,
        log_text=log,
    )
    assert record["turns"] == 7
    assert record["cost_usd"] == 0.5
    assert record["tokens_out"] == 120


def test_codex_record_parses_tokens_used_line():
    log = (
        "codex exec start\n"
        "work done\n"
        "tokens used: 12,345\n"
    )
    started, ended = started_and_ended()
    record = run_arm.build_run_record(
        arm="codex",
        role="coder",
        model="gpt-6-sol",
        workdir="/tmp/w",
        prompt_file="/tmp/p.txt",
        log_path="/tmp/l.log",
        started=started,
        ended=ended,
        exit_code=0,
        log_text=log,
    )
    assert record["tokens_used"] == 12345
    assert record["turns"] is None
    assert record["cost_usd"] is None
    assert record["tokens_out"] is None
    assert record["verdict"] is None


def test_codex_record_without_tokens_line_is_null():
    started, ended = started_and_ended()
    record = run_arm.build_run_record(
        arm="codex",
        role="coder",
        model="gpt-6-sol",
        workdir="/tmp/w",
        prompt_file="/tmp/p.txt",
        log_path="/tmp/l.log",
        started=started,
        ended=ended,
        exit_code=1,
        log_text="failed early, no usage line\n",
    )
    assert record["tokens_used"] is None
    assert record["exit_code"] == 1


# --------------------------------------------------------------------------
# clean gate-config-dir copy logic (tmp dirs)
# --------------------------------------------------------------------------

def test_gate_config_dir_copies_credentials_and_strips_env(tmp_path):
    home_claude = tmp_path / "claude-home"
    home_claude.mkdir()
    (home_claude / ".credentials.json").write_text('{"token":"redacted"}')
    (home_claude / "settings.json").write_text(
        json.dumps(
            {
                "env": {"ANTHROPIC_BASE_URL": "https://example.invalid"},
                "permissions": {"allow": ["Read"]},
                "model": "glm-5.3",
            }
        )
    )
    gate_dir = tmp_path / "gate-config"

    run_arm.prepare_gate_config_dir(
        gate_dir,
        home_claude / ".credentials.json",
        home_claude / "settings.json",
    )

    creds = json.loads((gate_dir / ".credentials.json").read_text())
    assert creds == {"token": "redacted"}
    settings = json.loads((gate_dir / "settings.json").read_text())
    assert "env" not in settings
    assert settings["permissions"] == {"allow": ["Read"]}
    assert settings["model"] == "glm-5.3"


def test_gate_config_dir_reuse_and_missing_sources(tmp_path):
    gate_dir = tmp_path / "gate-config"
    # First run with no sources at all: empty settings, no credentials.
    run_arm.prepare_gate_config_dir(gate_dir, None, None)
    settings = json.loads((gate_dir / "settings.json").read_text())
    assert settings == {}
    assert not (gate_dir / ".credentials.json").exists()
    # Second run (reuse) with sources now present: copied, env still gone.
    src = tmp_path / "src"
    src.mkdir()
    (src / ".credentials.json").write_text('{"token":"fresh"}')
    (src / "settings.json").write_text('{"env": {"A": "B"}, "x": 1}')
    run_arm.prepare_gate_config_dir(gate_dir, src / ".credentials.json", src / "settings.json")
    settings = json.loads((gate_dir / "settings.json").read_text())
    assert settings == {"x": 1}
    assert json.loads((gate_dir / ".credentials.json").read_text()) == {"token": "fresh"}


def test_gate_config_dir_tolerates_invalid_settings_json(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "settings.json").write_text("{not json")
    gate_dir = tmp_path / "gate-config"
    run_arm.prepare_gate_config_dir(gate_dir, None, src / "settings.json")
    assert json.loads((gate_dir / "settings.json").read_text()) == {}


# --------------------------------------------------------------------------
# codex flag building with and without a git repo
# --------------------------------------------------------------------------

def test_codex_args_inside_git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    assert run_arm.is_inside_git_repo(repo) is True
    args = run_arm.build_codex_args("gpt-6-sol", "do the thing", True, [])
    assert args[:6] == [
        "exec",
        "-m",
        "gpt-6-sol",
        "-c",
        "model_reasoning_effort=high",
        "do the thing",
    ]
    assert "--skip-git-repo-check" not in args


def test_codex_args_outside_git_repo(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert run_arm.is_inside_git_repo(plain) is False
    args = run_arm.build_codex_args("gpt-6-sol", "prompt", False, [])
    assert args[0] == "exec"
    assert args[1] == "--skip-git-repo-check"
    assert args[2:4] == ["-m", "gpt-6-sol"]
    assert "prompt" in args


def test_git_file_worktree_marker_counts_as_repo(tmp_path):
    worktree = tmp_path / "wt"
    worktree.mkdir()
    (worktree / ".git").write_text("gitdir: /somewhere/else\n")
    assert run_arm.is_inside_git_repo(worktree) is True


# --------------------------------------------------------------------------
# muse quota-abort path (usage call monkeypatched — no live CLI, no network)
# --------------------------------------------------------------------------

def test_muse_quota_gate_aborts_on_exhausted_quota(monkeypatch):
    monkeypatch.setattr(
        run_arm,
        "_muse_usage_output",
        lambda env: "meter: quota exhausted; resets 2026-11-15",
    )
    with pytest.raises(run_arm.QuotaAbortError) as excinfo:
        run_arm.muse_quota_gate(env={})
    assert "2026-11-15" in str(excinfo.value)
    assert "zero burn" in str(excinfo.value)


def test_muse_quota_gate_aborts_on_rate_limit_text(monkeypatch):
    monkeypatch.setattr(
        run_arm,
        "_muse_usage_output",
        lambda env: "rate-limit hit: window resets on 2026-12-01, retry later",
    )
    with pytest.raises(run_arm.QuotaAbortError):
        run_arm.muse_quota_gate(env={})


def test_muse_quota_gate_passes_on_no_usage_data(monkeypatch):
    # server_sent_no_usage is benign: can happen before the first use in a
    # new window — must NOT abort.
    monkeypatch.setattr(
        run_arm,
        "_muse_usage_output",
        lambda env: "server_sent_no_usage: no usage data for this subscription",
    )
    info = run_arm.muse_quota_gate(env={})
    assert info["status"] == "no_data"


def test_muse_quota_gate_passes_on_healthy_usage(monkeypatch):
    monkeypatch.setattr(
        run_arm,
        "_muse_usage_output",
        lambda env: "used 12% of window quota, resets 2026-11-20",
    )
    info = run_arm.muse_quota_gate(env={})
    assert info["status"] == "ok"
