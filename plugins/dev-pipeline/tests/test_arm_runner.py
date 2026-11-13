"""Unit tests for the CLI arm runner tool (plugins/dev-pipeline/tools/run_arm.py).

Covers ONLY: verdict extraction (claude JSON-blob result + plain-log
fallback), run-record building from a fake log + fake claude JSON blob,
the clean-config-dir copy logic (tmp dirs), codex flag building with and
without a git repo, the muse quota/meter abort path (monkeypatched usage
call — no live CLI calls, no network), extra-arg safety validation,
reviewer provider-env stripping, and the exit-code contract for failed
preconditions (no live CLIs are spawned: subprocess is monkeypatched).
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

# Codex/muse-style log: the verdict must be the LAST non-blank line.
def test_verdict_found_as_final_line():
    log = "finding A ...\nfinding B ...\nVERDICT: APPROVE\n"
    assert run_arm.extract_verdict(log) == "APPROVE"


def test_verdict_must_be_last_nonblank_line():
    # An earlier VERDICT line followed by any later text does not count.
    log = "VERDICT: REJECT\nfinal answer follows\n"
    assert run_arm.extract_verdict(log) is None


def test_verdict_inline_match_in_longer_line_rejected():
    log = "final answer: VERDICT: SHIP\n"
    assert run_arm.extract_verdict(log) is None
    # Quoted matches inside a longer line never count either.
    assert run_arm.extract_verdict('note "VERDICT: SHIP" was said\n') is None


def test_verdict_reject_and_ship_forms():
    assert run_arm.extract_verdict("VERDICT: REJECT\n") == "REJECT"
    assert run_arm.extract_verdict("VERDICT: SHIP\n") == "SHIP"


def test_verdict_superseded_by_trailing_text_is_missing():
    # The verdict sits before a later filler line, so the last non-blank
    # line is not a verdict line.
    log = "VERDICT: APPROVE\n" + "x" * 250 + "\n"
    assert run_arm.extract_verdict(log) is None


def test_verdict_missing_empty_and_lowercase_keyword():
    assert run_arm.extract_verdict("all good, no verdict line\n") is None
    assert run_arm.extract_verdict("") is None
    # The keyword is case-insensitive, but still anchored to the whole line.
    assert run_arm.extract_verdict("verdict: approve\n") == "APPROVE"


# Claude arms run with --output-format json: the log ends with the JSON
# blob, and the verdict lives in the blob's "result" string.
def fake_claude_log(verdict_line="VERDICT: SHIP"):
    result = "summary of the review\n" + verdict_line
    blob = json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "result": result,
            "num_turns": 4,
            "total_cost_usd": 0.0123,
            "usage": {"input_tokens": 210, "output_tokens": 55},
        }
    )
    # Real shape: warning lines, then the blob LAST (no bare VERDICT line
    # after it).
    return (
        "warning: low disk\n"
        "warning: something else\n"
        + blob
        + "\n"
    )


def test_claude_verdict_taken_from_result_blob():
    # The combined log ends with the JSON blob, so a verdict can only be
    # extracted from the blob's "result" string.
    assert run_arm.extract_verdict(fake_claude_log(), arm="claude") == "SHIP"
    assert (
        run_arm.extract_verdict(fake_claude_log("VERDICT: REJECT"), arm="claude")
        == "REJECT"
    )


def test_claude_verdict_outside_blob_is_ignored_when_blob_parses():
    # A blob parses, but its "result" carries no verdict: a VERDICT line
    # elsewhere in the log does not rescue it.
    blob = json.dumps({"result": "no verdict here", "num_turns": 1})
    log = "VERDICT: APPROVE\n" + blob + "\n"
    assert run_arm.extract_verdict(log, arm="claude") is None


def test_claude_nonjson_log_falls_back_to_last_log_line():
    # A non-json claude run: no blob parses, so the whole log's last
    # non-blank line is anchor-matched.
    log = "thinking...\nVERDICT: APPROVE\n"
    assert run_arm.extract_verdict(log, arm="claude") == "APPROVE"


def test_claude_inline_verdict_in_result_rejected():
    blob = json.dumps(
        {"result": "final answer: VERDICT: APPROVE", "num_turns": 2}
    )
    assert run_arm.extract_verdict(blob + "\n", arm="claude") is None


# --------------------------------------------------------------------------
# run-record building (fake log + fake claude JSON blob)
# --------------------------------------------------------------------------

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
    # The nested usage object inside the LAST top-level blob starts later
    # than that blob's opening brace, but only top-level spans compete: the
    # record must read the last TOP-LEVEL blob, not the innermost object.
    log = (
        "noise\n"
        + json.dumps(
            {
                "result": "partial review",
                "usage": {"output_tokens": 9},
            }
        )
        + "\n"
        + json.dumps(
            {
                "result": "second pass\nVERDICT: APPROVE",
                "num_turns": 7,
                "total_cost_usd": 0.5,
                "usage": {"output_tokens": 120},
            }
        )
        + "\n"
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
    assert record["verdict"] == "APPROVE"


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


def test_muse_usage_bare_429_text_is_blocked(monkeypatch):
    monkeypatch.setattr(
        run_arm,
        "_muse_usage_output",
        lambda env: "429 Too Many Requests",
    )
    with pytest.raises(run_arm.QuotaAbortError):
        run_arm.muse_quota_gate(env={})


class _FakeProc:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_muse_usage_query_nonzero_exit_aborts(monkeypatch):
    # A failed usage query is a meter failure, not a clean bill of health.
    monkeypatch.setattr(
        run_arm.subprocess,
        "run",
        lambda *a, **k: _FakeProc(2, stdout="meter backend error"),
    )
    with pytest.raises(run_arm.QuotaAbortError):
        run_arm.muse_quota_gate(env={})


def test_muse_usage_query_spawn_failure_aborts(monkeypatch):
    def boom(*a, **k):
        raise OSError("no such program")

    monkeypatch.setattr(run_arm.subprocess, "run", boom)
    with pytest.raises(run_arm.QuotaAbortError):
        run_arm.muse_quota_gate(env={})


def test_muse_usage_query_nonzero_exit_with_benign_marker_allowed(monkeypatch):
    # server_sent_no_usage is benign even on a nonzero exit: it can happen
    # before the first use in a new window — must NOT abort.
    monkeypatch.setattr(
        run_arm.subprocess,
        "run",
        lambda *a, **k: _FakeProc(
            1, stderr="server_sent_no_usage: no usage data yet"
        ),
    )
    info = run_arm.muse_quota_gate(env={})
    assert info["status"] == "no_data"


def test_muse_usage_query_nonzero_exit_generic_no_usage_data_aborts(monkeypatch):
    # On a FAILED query only server_sent_no_usage is a benign marker; a
    # generic "no usage data" does not prove the meter is healthy — abort.
    monkeypatch.setattr(
        run_arm.subprocess,
        "run",
        lambda *a, **k: _FakeProc(
            1, stderr="warning: no usage data in response"
        ),
    )
    with pytest.raises(run_arm.QuotaAbortError):
        run_arm.muse_quota_gate(env={})


# --------------------------------------------------------------------------
# extra-arg safety validation (whitelist injection)
# --------------------------------------------------------------------------

def test_extra_arg_allowedtools_is_rejected():
    # Extra args are appended AFTER the role's --allowedTools, so a second
    # one would override the role's tool whitelist — refuse it.
    for extra in (["--allowedTools", "Bash"], ["--allowedTools=Write"]):
        with pytest.raises(run_arm.UsageError):
            run_arm.build_claude_args("glm-5.3", "p", "coder", extra)
    with pytest.raises(run_arm.UsageError):
        run_arm.validate_extra_args(["--allowedToolsBash"])


def test_extra_arg_dangerously_skip_permissions_any_spelling():
    for arg in (
        "--dangerously-skip-permissions",
        "--DANGEROUSLY-SKIP-PERMISSIONS",
        "--dangerously_skip_permissions",
        "--dangerouslySkipPermissions=true",
    ):
        with pytest.raises(run_arm.UsageError):
            run_arm.validate_extra_args([arg])


def test_extra_arg_normal_values_pass():
    run_arm.validate_extra_args(["--verbose", "a plain value"])
    args = run_arm.build_claude_args("glm-5.3", "prompt", "reviewer", ["--verbose"])
    assert args[0] == "-p"
    assert args[-1] == "--verbose"


# --------------------------------------------------------------------------
# reviewer env isolation (provider routing keys)
# --------------------------------------------------------------------------

def test_strip_provider_env_removes_routing_keys_only():
    env = {
        "PATH": "/usr/bin",
        "ANTHROPIC_BASE_URL": "https://example.invalid",
        "ANTHROPIC_AUTH_TOKEN": "token",
        "ANTHROPIC_API_KEY": "key",
        "ANTHROPIC_MODEL": "model",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "haiku",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "sonnet",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "opus",
        "ANTHROPIC_SMALL_FAST_MODEL": "fast",
        "ANTHROPIC_MODEL_ERROR_HINT": "hint",
        "SOME_UNRELATED_VAR": "kept",
    }
    out = run_arm.strip_provider_env(dict(env))
    for key in run_arm.ANTHROPIC_PROVIDER_ENV_KEYS:
        assert key not in out
    assert out["PATH"] == "/usr/bin"
    assert out["SOME_UNRELATED_VAR"] == "kept"


# --------------------------------------------------------------------------
# exit-code contract via main() (preconditions → clean exit 2)
# --------------------------------------------------------------------------

def _base_argv(tmp_path, **overrides):
    options = {
        "--arm": "claude",
        "--role": "coder",
        "--workdir": str(tmp_path),
        "--prompt-file": str(tmp_path / "prompt.txt"),
        "--log-path": str(tmp_path / "run.log"),
        "--record-path": str(tmp_path / "run.json"),
    }
    options.update(overrides)
    (tmp_path / "prompt.txt").write_text("do the thing\n")
    argv = []
    for flag, value in options.items():
        argv += [flag, value]
    return argv


def test_missing_env_file_exits_2_clean_stderr(tmp_path, capsys):
    rc = run_arm.main(
        _base_argv(tmp_path) + ["--env-file", str(tmp_path / "missing.env")]
    )
    assert rc == 2
    err = capsys.readouterr().err
    assert "error:" in err
    assert "Traceback" not in err
    assert not (tmp_path / "run.log").exists()


def test_existing_log_path_exits_2(tmp_path):
    (tmp_path / "run.log").write_text("leftover\n")
    rc = run_arm.main(_base_argv(tmp_path))
    assert rc == 2


def test_spawn_failure_record_carries_exit_4(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise OSError("no such program")

    monkeypatch.setattr(run_arm.subprocess, "run", boom)
    rc = run_arm.main(_base_argv(tmp_path, **{"--arm": "codex"}))
    assert rc == 4
    record = json.loads((tmp_path / "run.json").read_text())
    assert record["exit_code"] == 4
    assert "dispatch error" in (tmp_path / "run.log").read_text()


def test_unwritable_record_path_raises_usage_error(tmp_path):
    with pytest.raises(run_arm.UsageError):
        run_arm._write_record(tmp_path / "no" / "dir" / "run.json", {"x": 1})
