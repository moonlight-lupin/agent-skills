"""RED tests for the lanes setup subcommand (dev-pipeline 0.7.0, Task 1).

Seam: the lanes script's CLI (skills/orchestrator/scripts/lanes.py), driven as
a subprocess against a tmp HOME and a fixture defaults file -- the only public
seam of the writer engine (plan Task 1). Written by test-evals; the build
implementer does not edit this file (attested).

Pinned output contract for `setup` (single JSON object on stdout for
successful runs): {"wrote": <abs path|null>, "backup": <abs path|null>,
"warnings": [str], "doctor": <doctor report>, "roundtrip": <resolve T2
report>}; for --check: {"wrote": null, "proposed": <diff str>, ...}.
Refusals print {"refused": <msg>, ...} (plus "diff" in the force-required
case) to stderr with the contract's exit code. The override file contains
ONLY the changed tables; a header comment and the schema line, no absolute
paths, so identical inputs write identical bytes anywhere.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
LANES = REPO_ROOT / "skills" / "orchestrator" / "scripts" / "lanes.py"
_FX_STATE: dict = {}  # the module fixture posts its defaults path here

FIXTURE_DEFAULTS = """\
schema = "dev-pipeline-lanes.v1"

[harness]
controller = "auto"
coding = "auto"

[claude_code]
binary = "claude"
binary_args = []
version_pin = ""
blinding = "no-memory"
role_root = "~/.config/dev-pipeline/roles"
max_turns = 80
permission_mode = "acceptEdits"
allowed_tools = ["Bash", "Read"]
disallowed_tools = []
reviewer_disallowed_tools = ["Edit", "Write"]
extra_args = []

[providers.anthropic]
kind = "anthropic-login"

[providers.stub]
kind = "anthropic-compatible"
base_url = "https://stub.invalid"
auth_env = "STUB_COMPAT_KEY"

[lanes.claude]
via = "claude-code"
provider = "anthropic"
model = ""
family = "anthropic"

[lanes.codex]
via = "cli"
binary = ["definitely-missing-codex-bin"]
model = ""
effort = "high"
family = "openai"
model_args = ["-m", "{model}"]
effort_args = ["-c", "model_reasoning_effort={effort}"]
review_argv = ["{binary}", "exec", "--sandbox", "read-only", "{model_args}", "{effort_args}", "{prompt_pointer}"]
code_argv = ["{binary}", "exec", "--sandbox", "workspace-write", "{model_args}", "{effort_args}", "{prompt_pointer}"]

[lanes.controller]
via = "controller"
family = "controller"

[roles]
architect = ["claude", "controller"]
test_writer = ["claude", "controller"]
coder = ["claude", "controller"]
reviewers = ["codex", "claude", "controller"]
goldfish = ["controller"]

[ladder]
threshold_pct = 80
max_rate_limits = 2
approval_lanes = []

[review]
same_family_seats = "ask"
dispatch = {}

[review.seats]
T0 = 0
T1 = 1
T2 = 2
T3 = 3
gate = 3

[pin]
plugin_version = ""
master_path = ""
"""


def make_home(tmp_path: Path, name: str = "home") -> Path:
    home = tmp_path / name
    home.mkdir()
    (home / ".hermes" / "dev-pipeline").mkdir(parents=True)
    return home


def default_path(home: Path) -> Path:
    return home / ".hermes" / "dev-pipeline" / "lanes.toml"


def write_defaults(tmp_path: Path, name: str = "defaults") -> Path:
    p = tmp_path / f"{name}.tmp" / "lanes.default.toml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(FIXTURE_DEFAULTS)
    return p


def run_lanes(*args: str, home: Path | None = None, timeout: float = 120, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {
        **__import__("os").environ.copy(),
        "TMPDIR": tempfile.gettempdir(),          # suite isolation
        "PATH": __import__("os").environ.get("PATH", "/usr/bin:/bin"),
    }
    env.pop("HERMES_HOME", None)                  # no profile leakage into the engine
    env.pop("DEV_PIPELINE_LANES", None)           # no machine config leakage either
    if home is not None:
        env["HOME"] = str(home)
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(LANES), *args],
        capture_output=True, text=True, timeout=timeout, env=env,
    )


def run_setup(*args: str, home: Path) -> subprocess.CompletedProcess:
    path = _FX_STATE.get("defaults", Path())
    assert path.is_file(), "module fixture _FIXTURES must have run first"
    return run_lanes("--defaults", str(path), "setup", *args, home=home)


def out_json(proc: subprocess.CompletedProcess) -> dict:
    return json.loads(proc.stdout)


def err_json(proc: subprocess.CompletedProcess) -> dict:
    return json.loads(proc.stderr)


def _register_guard() -> None:
    """The engine must exist at the script's top level (not argparse's usage
    error, which also exits 2 and would make the refusal tests pass red)."""
    proc = run_lanes("--help")
    assert proc.returncode == 0, proc.stderr
    assert "setup" in proc.stdout, "lanes.py --help must list the setup subcommand (RED: missing)"


@pytest.fixture(scope="module", autouse=True)
def _engine_registered():
    _register_guard()


@pytest.fixture(scope="module")
def _FIXTURES(tmp_path_factory):
    base = tmp_path_factory.mktemp("lanes08_setup")
    defaults = write_defaults(base, "defaults")
    _FX_STATE["defaults"] = defaults
    return {"defaults": defaults, "base": base}


# ── machine scope writes ──────────────────────────────────────────────────


def test_quick_fresh_write(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--quick", "roles.coder=codex,controller", "roles.reviewers=codex,claude", "lanes.codex.model=gpt-6-sol", home=home)
    assert proc.returncode == 0, proc.stderr
    body = out_json(proc)
    written = Path(body["wrote"])
    assert written == default_path(home)
    text = written.read_text()
    assert 'schema = "dev-pipeline-lanes.v1"' in text
    merged = tomllib.loads(text)
    assert merged["roles"]["coder"] == ["codex", "controller"]
    assert merged["roles"]["reviewers"] == ["codex", "claude"]
    assert merged["lanes"]["codex"]["model"] == "gpt-6-sol"
    assert "harness" not in merged and "ladder" not in merged  # minimal override
    assert body["roundtrip"]["roles"]["coder"]  # a coder lane was picked (env-dependent choice)
    assert body["doctor"]["schema"] == "dev-pipeline-lanes.v1"


def test_check_writes_nothing(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--check", "--set", "roles.coder=codex", home=home)
    assert proc.returncode == 0, proc.stderr
    body = out_json(proc)
    assert body["wrote"] is None
    assert "proposed" in body and body["proposed"].strip()
    assert not default_path(home).exists()


def test_deep_set_preserves_siblings(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--set", "review.seats.T2=3", home=home)
    assert proc.returncode == 0, proc.stderr
    text = default_path(home).read_text()
    merged = tomllib.loads(text)
    assert merged["review"]["seats"]["T2"] == 3
    assert "T1" not in text and "T3" not in text  # only the deepest key ships
    proc2 = run_setup("--check", home=home)
    assert proc2.returncode == 0, proc2.stderr


def test_unknown_key_refused(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--set", "harness.wrong=1", home=home)
    assert proc.returncode == 2
    assert "refused" in err_json(proc)
    assert not default_path(home).exists()


def test_unknown_lane_refused(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--set", "roles.coder=nope", home=home)
    assert proc.returncode == 2
    msg = err_json(proc)["refused"]
    assert "claude" in msg and "codex" in msg
    assert not default_path(home).exists()


def test_list_value_replaces(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--set", "roles.coder=claude,controller", home=home)
    assert proc.returncode == 0, proc.stderr
    merged = tomllib.loads(default_path(home).read_text())
    assert merged["roles"]["coder"] == ["claude", "controller"]


def test_refuse_without_force_shows_diff(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    p = default_path(home)
    p.write_text('[lanes.codex]\nmodel = "old"\n')
    before = p.read_bytes()
    proc = run_setup("--set", "lanes.codex.model=new", home=home)
    assert proc.returncode == 4
    body = err_json(proc)
    assert "refused" in body
    assert "diff" in body and "--- " in body["diff"] and "+++ " in body["diff"]
    assert p.read_bytes() == before


def test_force_backs_up(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    p = default_path(home)
    p.write_text('[lanes.codex]\nmodel = "v1"\n')
    proc = run_setup("--force", "--set", "lanes.codex.model=v2", home=home)
    assert proc.returncode == 0, proc.stderr
    backups = sorted(p.parent.glob("lanes.toml.bak-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == b'[lanes.codex]\nmodel = "v1"\n'
    # three forced rounds total -> exactly the two most recent backups remain
    run_setup("--force", "--set", "lanes.codex.model=v3", home=home)
    run_setup("--force", "--set", "lanes.codex.model=v4", home=home)
    backups = sorted(p.parent.glob("lanes.toml.bak-*"))
    assert len(backups) == 2


def test_unparseable_existing_refused(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    default_path(home).write_text("[lanes.codex\nbroken ===")
    proc = run_setup("--set", "roles.coder=claude", home=home)
    assert proc.returncode == 5
    assert "refused" in err_json(proc) or "error" in err_json(proc)


def test_empty_override_is_fresh(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    default_path(home).write_bytes(b"")
    proc = run_setup("--set", "roles.coder=claude", home=home)
    assert proc.returncode == 0, proc.stderr
    assert default_path(home).read_text().strip()


def test_unset_removes_key(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    first = run_setup("--set", "lanes.codex.model=m1", "--force", home=home)
    assert first.returncode == 0, first.stderr
    proc = run_setup("--unset", "lanes.codex.model", "--force", home=home)
    assert proc.returncode == 0, proc.stderr
    merged = tomllib.loads(default_path(home).read_text())
    assert "model" not in merged.get("lanes", {}).get("codex", {})


def test_unset_unknown_path(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--unset", "harness.wrong", home=home)
    assert proc.returncode == 2
    assert "refused" in err_json(proc)


# ── project scope and the trust boundary ──────────────────────────────────


def test_project_scope_model_effort_ok(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    repo = tmp_path / "proj"
    (repo / ".dev-pipeline").mkdir(parents=True)
    proc = run_setup("--project", "--repo", str(repo), "--set", "lanes.codex.model=gpt-6-sol", home=home)
    assert proc.returncode == 0, proc.stderr
    text = (repo / ".dev-pipeline" / "lanes.toml").read_text()
    assert tomllib.loads(text)["lanes"]["codex"]["model"] == "gpt-6-sol"
    assert not default_path(home).exists()  # project scope never writes the machine file


def test_project_scope_refuses_trusted_keys(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    repo = tmp_path / "proj"
    repo.mkdir(parents=True)
    proc = run_setup("--project", "--repo", str(repo), "--set", "lanes.codex.model=gpt-6-sol", "--set", "harness.controller=claude-code", home=home)
    assert proc.returncode == 3
    assert "untrusted" in err_json(proc)["refused"]
    assert not (repo / ".dev-pipeline" / "lanes.toml").exists()  # whole-write refusal


def test_project_scope_refuses_unknown_lane(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    repo = tmp_path / "proj"
    repo.mkdir(parents=True)
    proc = run_setup("--project", "--repo", str(repo), "--set", "lanes.newlane.model=x", home=home)
    assert proc.returncode == 3
    assert "untrusted" in err_json(proc)["refused"]


# ── warnings and the verify roundtrip ─────────────────────────────────────


def test_unavailable_lane_warns(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    # US-4 acceptance (adjudicated over the edge-case prose): a coder list
    # with no resolvable lane still writes, warns, and exits NONZERO
    proc = run_setup("--quick", "roles.coder=codex", home=home)
    assert proc.returncode == 2, proc.stderr
    body = out_json(proc)
    assert body["wrote"]  # the write stands; the problem is reported, not hidden
    assert any("codex" in w for w in body.get("warnings", []))
    assert "no coder lane resolves" in body.get("verification", "")


def test_provider_env_warns(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    # the bundled validator requires a model on an anthropic-compatible lane
    proc = run_setup("--set", "lanes.claude.model=stub-model", "--set", "lanes.claude.provider=stub", home=home)
    assert proc.returncode == 0, proc.stderr
    body = out_json(proc)
    assert any("STUB_COMPAT_KEY" in w for w in body.get("warnings", []))


def test_verify_roundtrip_prints_roles(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--quick", "roles.coder=claude", "roles.reviewers=codex,claude", home=home)
    assert proc.returncode == 0, proc.stderr
    body = out_json(proc)
    assert body["doctor"]["ok"] is not None
    assert body["roundtrip"]["roles"]["coder"]  # a coder lane was picked (env-dependent choice)
    assert body["roundtrip"]["verdict"]


# ── determinism and read-only defaults ────────────────────────────────────


def test_setup_deterministic_quick(_FIXTURES, tmp_path):
    home_a, home_b = make_home(tmp_path, "home-a"), make_home(tmp_path, "home-b")
    # roles.coder=codex resolves to NO-LANE on the fixture (adjudicated rc 2);
    # determinism is still the claim: identical inputs -> identical bytes
    first = run_setup("--quick", "roles.coder=codex", "roles.reviewers=codex,claude", "lanes.codex.model=gpt-6-sol", home=home_a)
    second = run_setup("--quick", "roles.coder=codex", "roles.reviewers=codex,claude", "lanes.codex.model=gpt-6-sol", home=home_b)
    assert first.returncode == second.returncode == 2, (first.stderr, second.stderr)
    assert default_path(home_a).read_bytes() == default_path(home_b).read_bytes()


def test_setup_deterministic_deep(_FIXTURES, tmp_path):
    args = ("--set", "roles.reviewers=codex,claude,controller", "--unset", "lanes.codex.model")
    home_a, home_b = make_home(tmp_path, "home-a"), make_home(tmp_path, "home-b")
    first = run_setup(*args, "--force", home=home_a)
    second = run_setup(*args, "--force", home=home_b)
    assert first.returncode == second.returncode == 0, (first.stderr, second.stderr)
    assert default_path(home_a).read_bytes() == default_path(home_b).read_bytes()


def test_setup_defaults_untouched(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    defaults = _FIXTURES["defaults"]
    before = (defaults.read_bytes(), defaults.stat().st_mtime_ns)
    proc = run_setup("--quick", "roles.coder=codex", home=home)
    assert proc.returncode == 2, proc.stderr  # adjudicated NO-LANE exit; file write stands
    after = (defaults.read_bytes(), defaults.stat().st_mtime_ns)
    assert after == before


# ── R3 regression rows: mechanisms fixed in review rounds, pinned here ────


def test_r3_string_list_scalar_shorthand_refused(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--set", "lanes.codex.binary=42", home=home)
    assert proc.returncode == 2
    assert "string list" in err_json(proc)["refused"]


def test_r3_quoted_keys_survive_rewrite(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    p = default_path(home)
    p.write_text('schema = "dev-pipeline-lanes.v1"\n[providers."z.ai"]\nkind = "anthropic-login"\n')
    proc = run_setup("--force", "--set", "roles.coder=claude", home=home)
    assert proc.returncode == 0, proc.stderr
    text = p.read_text()
    assert 'providers."z.ai"' in text  # one provider, not a restructured nesting
    assert '[providers.z.ai]' not in text


def test_r3_dynamic_surfaces_reachable(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    run_setup("--force", "--set", "review.dispatch.claude=controller", home=home)
    run_setup("--force", "--set", "lanes.claude.blinding=config-dir", home=home)
    p = run_setup("--force", "--set", "providers.compat.kind=anthropic-login", home=home)
    assert p.returncode == 0, p.stderr
    merged = tomllib.loads(default_path(home).read_text())
    assert merged["review"]["dispatch"]["claude"] == "controller"
    assert merged["lanes"]["claude"]["blinding"] == "config-dir"
    assert merged["providers"]["compat"]["kind"] == "anthropic-login"


def test_r3_dynamic_unknown_leaf_refused(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--set", "lanes.codex.nonsense=hello", home=home)
    assert proc.returncode == 2
    assert "unknown key" in err_json(proc)["refused"]


def test_r3_machine_active_config_target_wins(_FIXTURES, tmp_path):
    # the loader uses ~/.config when ~/.hermes is absent: setup must write it,
    # not create a shadowing ~/.hermes file (codex R1-on-fixed-tree finding 5)
    home = make_home(tmp_path)
    home.chmod(0o777)
    cfg_dir = home / ".config" / "dev-pipeline"
    cfg_dir.mkdir(parents=True)
    cfg = cfg_dir / "lanes.toml"
    cfg.write_text('[lanes.codex]\nmodel = "old"\n')
    proc = run_setup("--force", "--set", "lanes.codex.model=new", home=home)
    assert proc.returncode == 0, proc.stderr
    assert 'model = "new"' in cfg.read_text()
    assert not (home / ".hermes" / "dev-pipeline" / "lanes.toml").exists()


def test_r3_env_var_new_file_first_time_setup(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    env_file = tmp_path / "brand-new" / "lanes.toml"
    proc = run_lanes("--defaults", str(_FX_STATE["defaults"]), "setup",
                     "--set", "roles.coder=claude", home=home,
                     env_extra={"DEV_PIPELINE_LANES": str(env_file)})
    assert proc.returncode == 0, proc.stderr
    assert env_file.exists()


def test_r3_unparseable_machine_file_refused_upfront(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    default_path(home).write_text("[lanes\nbroken ===")
    proc = run_setup("--project", "--repo", str(tmp_path),
                     "--set", "lanes.claude.model=probe", home=home)
    assert proc.returncode == 5
    assert "does not parse" in err_json(proc)["refused"]


def test_r3_project_write_refuses_hostile_content(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    repo = tmp_path / "proj"
    (repo / ".dev-pipeline").mkdir(parents=True)
    (repo / ".dev-pipeline" / "lanes.toml").write_text(
        'schema = "dev-pipeline-lanes.v1"\n[harness]\ncoding = "controller"\n'
        '[lanes.codex]\nmodel = "old"\n')
    proc = run_setup("--project", "--repo", str(repo), "--force",
                     "--set", "lanes.codex.model=new", home=home)
    assert proc.returncode == 3  # whole-write refusal: nothing silently dropped
    assert "outside the untrusted surface" in err_json(proc)["refused"]


def test_r3_project_symlink_escape_refused(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    home.chmod(0o777)
    repo = tmp_path / "proj"
    repo.mkdir(parents=True)
    (repo / ".dev-pipeline").symlink_to(home / ".hermes" / "dev-pipeline")
    proc = run_setup("--project", "--repo", str(repo), "--force",
                     "--set", "lanes.claude.model=x", home=home)
    assert proc.returncode == 3
    assert not default_path(home).exists()  # the machine file was never touched


def test_r3_check_reports_requested_values(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    body = out_json(run_setup("--check", "--set", "roles.coder=codex", home=home))
    req = body.get("requested", {})
    assert req["roles.coder"]["proposed"] == ["codex"]
    assert req["roles.coder"]["current"] == ["claude", "controller"]
    assert body.get("state") == "current-on-disk"


# ── gate-round regression rows (codex panel findings, verified) ────────────


def test_gate_seats_reject_negative_and_fractional(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--set", "review.seats.T2=-1", home=home)
    assert proc.returncode == 2, proc.stderr
    assert "nonnegative integer" in err_json(proc)["refused"]
    proc = run_setup("--set", "review.seats.T2=2.9", home=home)
    assert proc.returncode == 2
    assert "an integer is expected" in err_json(proc)["refused"]


def test_gate_check_roundtrip_on_missing_env_target(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_lanes("--defaults", str(_FX_STATE["defaults"]), "setup", "--check",
                     "--set", "roles.coder=controller", home=home,
                     env_extra={"DEV_PIPELINE_LANES": str(tmp_path / "not-yet" / "lanes.toml")})
    assert proc.returncode == 0, proc.stderr  # spec: a no-override check is a report, exit 0
    body = out_json(proc)
    assert body["doctor"]["schema"] == "dev-pipeline-lanes.v1"


def test_gate_empty_list_encoding(_FIXTURES, tmp_path):
    home = make_home(tmp_path)
    proc = run_setup("--set", "roles.reviewers=", home=home)
    assert proc.returncode == 0, proc.stderr
    text = default_path(home).read_text()
    assert "reviewers = []" in text
    merged = tomllib.loads(text)
    assert merged["roles"]["reviewers"] == []
