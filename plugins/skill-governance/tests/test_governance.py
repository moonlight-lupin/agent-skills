"""Isolated regression tests for non-destructive consolidation.

No real Hermes profile, user config, cron job or probe ledger is touched.
"""
import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _plugin():
    name = "skill_governance_test_package"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class Store:
    def __init__(self):
        self.values = {}
        self.writes = []

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.writes.append(key)
        self.values[key] = value


class Host:
    def __init__(self, home, config=None):
        self.hermes_home = str(home)
        self.state = Store()
        self.settings = config or {}
        self.hooks = {}
        self.skills = {}
        self.commands = {}

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def register_hook(self, name, callback):
        assert name not in self.hooks
        self.hooks[name] = callback

    def register_skill(self, name, path):
        assert Path(path).is_file()
        self.skills[name] = Path(path)

    def register_cli_command(self, name, *args):
        self.commands[name] = args

    def register_command(self, name, *args, **kw):
        self.commands[name] = args


def test_namespaced_state_and_config_are_independent(tmp_path):
    core = _plugin().core
    host = Host(tmp_path, {"manifest.track_changes": False, "advisor.enabled": True})
    m = core.ComponentContext(host, "manifest")
    a = core.ComponentContext(host, "advisor")
    m.state.set("v1", {"one": 1})
    a.state.set("v1", {"two": 2})
    assert m.state.get("v1") == {"one": 1}
    assert a.state.get("v1") == {"two": 2}
    assert host.state.values["manifest.v1"] != host.state.values["advisor.v1"]
    assert m.get_config("track_changes") is False
    assert a.get_config("enabled") is True
    assert m.get_config("auto_resolve", True) is False
    assert a.get_config("sweeper", True) is False
    with pytest.raises(ValueError):
        m.state.set("../other", {})


def test_legacy_state_migration_copies_and_is_idempotent(tmp_path):
    core = _plugin().core
    host = Host(tmp_path)
    origins = {}
    for name, plugin_id in core.LEGACY_IDS.items():
        path = core._legacy_state_path(tmp_path, plugin_id)
        path.parent.mkdir(parents=True)
        value = {"pending": [name], "fingerprints": {"x": "y"}}
        path.write_text(json.dumps({"v1": value}), encoding="utf-8")
        origins[name] = (path, path.read_bytes())
    assert set(core.migrate_legacy_state(host)) == {"manifest", "advisor"}
    for name, (path, before) in origins.items():
        assert path.read_bytes() == before
        assert host.state.values[core.STATE_KEYS[name]]["pending"] == [name]
    assert core.migrate_legacy_state(host) == []
    assert len(host.state.writes) == 2


def test_destination_not_overwritten_by_legacy(tmp_path):
    core = _plugin().core
    host = Host(tmp_path)
    host.state.set("manifest.v1", {"new": "current"})
    path = core._legacy_state_path(tmp_path, "skill-manifest")
    path.parent.mkdir(parents=True)
    path.write_text('{"v1": {"new": "old"}}')
    core.migrate_legacy_state(host)
    assert host.state.get("manifest.v1") == {"new": "current"}


@pytest.mark.parametrize("content", ['{garbage', '{"v1": []}', '{"v1": "x"}'])
def test_corrupt_legacy_fails_closed_before_registration(tmp_path, content):
    core = _plugin().core
    host = Host(tmp_path, {"manifest.disabled": True})
    path = core._legacy_state_path(tmp_path, "skill-manifest")
    path.parent.mkdir(parents=True)
    path.write_text(content)
    _plugin().register(host)
    # v0.1.1: registration never touches state; the corrupt store fails the
    # lazy bootstrap on the FIRST hook call (session start first), leaving ALL
    # hooks inert — the engines must not run on empty namespaces.
    assert set(host.hooks) == {
        "on_skill_lifecycle", "on_session_start", "pre_tool_call", "pre_llm_call"
    }
    assert host.state.values == {}
    assert host.hooks["on_session_start"](session_id="x") is None
    assert host.state.values == {}
    assert host.hooks["pre_llm_call"](session_id="x", user_message="hi") is None
    assert path.read_text() == content


def test_first_hook_is_session_start_and_migration_still_wins(tmp_path, monkeypatch):
    """The engines must never write before migration: bootstrap-first ordering.

    Regression for the fix-round finding: an engine state write creating the
    destination would make destination-wins skip the legacy import forever.
    Advisor is enabled and pre_tool_call is forced as the FIRST hook so a real
    engine write races the bootstrap; the legacy advisor payload must come
    through intact."""
    core = _plugin().core
    host = Host(tmp_path, {"manifest.disabled": True, "advisor.enabled": True})
    legacy_advisor = {"pending": [{"skill": "legacy-uncharted", "created_at": "t0"}],
                      "sweeper_job_id": ""}
    path = core._legacy_state_path(tmp_path, "contrastive-advisor")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"v1": legacy_advisor}))
    _plugin().register(host)
    # A behavioral edit arrives BEFORE the first session start: the advisor
    # engine wants to write advisor.v1; bootstrap must migrate first anyway.
    host.hooks["pre_tool_call"](tool_name="skill_manage",
                                args={"action": "patch", "name": "probe-me",
                                      "old_string": "## Procedure",
                                      "new_string": "## Procedure\\nConfirm"},
                                session_id="s1")
    migrated = host.state.get("advisor.v1")
    # The migrated legacy pending payload survived (destination-wins was not
    # triggered by an engine write that preceded migration). The engine's
    # fresh observation may join it; the legacy row must still be present.
    pendings = [p.get("skill") for p in migrated["pending"]]
    assert "legacy-uncharted" in pendings


def test_empty_legacy_envelope_reads_as_nothing_to_migrate(tmp_path):
    core = _plugin().core
    host = Host(tmp_path, {"manifest.disabled": True})
    path = core._legacy_state_path(tmp_path, "skill-manifest")
    path.parent.mkdir(parents=True)
    path.write_text('{"other": 1, "v1": null}')
    _plugin().register(host)
    assert host.state.get("manifest.v1") is None
    # The hook must run normally over the empty store.
    assert host.hooks["pre_llm_call"](session_id="x", user_message="hi") is None
    assert "governance.records" in host.state.values


def test_registered_hooks_are_composed_once(tmp_path):
    host = Host(tmp_path, {"manifest.disabled": True, "advisor.enabled": False})
    _plugin().register(host)
    assert set(host.hooks) == {
        "on_skill_lifecycle", "on_session_start", "pre_tool_call", "pre_llm_call"
    }
    assert "contrastive-refinement" in host.skills
    assert "skill-manifest" in host.commands
    assert "skill-manifest-ack" in host.commands
    assert host.hooks["pre_llm_call"](session_id="x", user_message="hello") is None
    assert host.state.get("governance.records") == {}


def test_concurrent_advisories_combine_without_losing_content():
    fn = _plugin().core.compose_advisories
    assert fn(None, None) is None
    assert fn({"context": "manifest"}, {"context": "probe"}) == {
        "context": "manifest\n\nprobe"
    }


def test_acknowledgement_and_probe_remain_separate_decisions():
    core = _plugin().core
    digest = "a" * 64
    state = {"fingerprints": {
        "key1": {"digest": digest, "ack": digest},
        "key2": {"digest": digest, "ack": "b" * 64},
    }, "findings": {"key2": {
        "name": "edited", "reason": "changed", "digest": digest,
    }}}
    records = core.build_records(state, {"pending": [
        {"skill": "edited", "probe_dir": "/tmp/evidence"}
    ]})
    assert records["manifest:key1"]["manifest_status"] == "fingerprint_current"
    assert records["manifest:key1"]["validation_status"] == "not_evaluated"
    assert records["skill:edited"]["manifest_status"] == "review_required"
    assert records["skill:edited"]["validation_status"] == "probe_advised"


def test_ledger_answer_never_counts_as_fingerprint_bound_validation():
    core = _plugin().core
    rows = [{"skill": "alpha", "answered_at": "today",
             "answered_with": "probe-cycle/selection.md"}]
    records = core.build_records({}, {}, rows)
    assert records["skill:alpha"]["validation_status"] == "answered_unbound"
    assert records["skill:alpha"]["manifest_status"] == "unknown"


def test_legacy_jobs_prevent_new_governance_cron(monkeypatch, tmp_path):
    core = _plugin().core
    host = Host(tmp_path, {"cron.enabled": True})
    cron = types.ModuleType("cron")
    jobs = types.ModuleType("cron.jobs")
    jobs.load_jobs = lambda: [{"name": core.LEGACY_CRON_NAMES[0], "id": "old"}]
    tools = types.ModuleType("tools")
    cronjob_tools = types.ModuleType("tools.cronjob_tools")
    called = []
    cronjob_tools.cronjob = lambda **kw: called.append(kw)
    for name, mod in (("cron", cron), ("cron.jobs", jobs), ("tools", tools),
                      ("tools.cronjob_tools", cronjob_tools)):
        monkeypatch.setitem(sys.modules, name, mod)
    core.ensure_single_cron(host)
    assert called == []


def test_cron_default_off_even_with_cron_modules_present(monkeypatch, tmp_path):
    """The cron.enabled gate must be the thing that stops creation."""
    core = _plugin().core
    host = Host(tmp_path)  # cron.enabled unset (default False)
    created = []
    cron = types.ModuleType("cron")
    jobs = types.ModuleType("cron.jobs")
    jobs.load_jobs = lambda: []
    tools = types.ModuleType("tools")
    cronjob_tools = types.ModuleType("tools.cronjob_tools")
    cronjob_tools.cronjob = lambda **kw: created.append(kw)
    for name, mod in (("cron", cron), ("cron.jobs", jobs), ("tools", tools),
                      ("tools.cronjob_tools", cronjob_tools)):
        monkeypatch.setitem(sys.modules, name, mod)
    core.ensure_single_cron(host)
    assert created == []
    assert host.state.values == {}


def test_cron_opt_back_in_via_recreated_named_job(monkeypatch, tmp_path):
    core = _plugin().core
    host = Host(tmp_path, {"cron.enabled": True})
    host.state.set("governance.cron", {"job_id": "gone", "user_removed": True})
    jobs = types.ModuleType("cron.jobs")
    job_list = [{"name": core.CRON_NAME, "id": "re-created"}]
    jobs.load_jobs = lambda: list(job_list)
    cronjob_tools = types.ModuleType("tools.cronjob_tools")
    calls = []
    cronjob_tools.cronjob = lambda **kw: calls.append(kw)
    for name, mod in (("cron", types.ModuleType("cron")), ("cron.jobs", jobs),
                      ("tools", types.ModuleType("tools")),
                      ("tools.cronjob_tools", cronjob_tools)):
        monkeypatch.setitem(sys.modules, name, mod)
    core.ensure_single_cron(host)
    assert calls == []  # adoption, not creation
    assert host.state.get("governance.cron") == {"job_id": "re-created",
                                                 "user_removed": False}


def test_both_engines_advice_is_delivered_in_one_gateway_hook(tmp_path, monkeypatch):
    plugin = _plugin()
    host = Host(tmp_path, {"manifest.disabled": True, "advisor.enabled": False})
    plugin.register(host)
    invoked = []
    def manifest_note(**kw):
        invoked.append(("manifest", kw["session_id"]))
        return {"context": "manifest drift"}
    def probe_note(ctx, **kw):
        invoked.append(("advisor", kw["session_id"]))
        assert ctx.state is not host.state
        return {"context": "probe suggestion"}
    monkeypatch.setattr(plugin.manifest_hooks, "on_pre_llm_call", manifest_note)
    monkeypatch.setattr(plugin.advisor, "on_pre_llm_call", probe_note)
    result = host.hooks["pre_llm_call"](session_id="session-1", user_message="go")
    assert result == {"context": "manifest drift\n\nprobe suggestion"}
    assert invoked == [("manifest", "session-1"), ("advisor", "session-1")]


def test_migration_preflight_fails_without_partial_state(tmp_path):
    core = _plugin().core
    host = Host(tmp_path)
    first = core._legacy_state_path(tmp_path, "skill-manifest")
    second = core._legacy_state_path(tmp_path, "contrastive-advisor")
    for path in (first, second):
        path.parent.mkdir(parents=True)
    first.write_text('{"v1": {"preserve": true}}')
    second.write_text("bad-json")
    with pytest.raises(json.JSONDecodeError):
        core.migrate_legacy_state(host)
    assert host.state.writes == []


def test_single_cron_respects_user_removal(monkeypatch, tmp_path):
    core = _plugin().core
    host = Host(tmp_path, {"cron.enabled": True})
    jobs = types.ModuleType("cron.jobs")
    active_jobs = []
    jobs.load_jobs = lambda: list(active_jobs)
    cronjob_tools = types.ModuleType("tools.cronjob_tools")
    calls = []
    def create(**kw):
        calls.append(kw)
        return {"job_id": "g-1"}
    cronjob_tools.cronjob = create
    for name, mod in (("cron", types.ModuleType("cron")), ("cron.jobs", jobs),
                      ("tools", types.ModuleType("tools")),
                      ("tools.cronjob_tools", cronjob_tools)):
        monkeypatch.setitem(sys.modules, name, mod)
    core.ensure_single_cron(host)
    assert len(calls) == 1
    assert host.state.get("governance.cron") == {"job_id": "g-1"}
    core.ensure_single_cron(host)  # job no longer listed -> manual removal
    assert host.state.get("governance.cron")["user_removed"] is True
    core.ensure_single_cron(host)
    assert len(calls) == 1


def test_external_ack_digest_is_current_only_for_matching_fingerprint():
    core = _plugin().core
    digest = "c" * 64
    source = {"fingerprints": {
        "hash-one": {"digest": digest, "ack": ""},
        "hash-two": {"digest": digest, "ack": ""},
    }, "findings": {}}
    external = {
        "hash-one": {"digest": digest},
        "hash-two": {"digest": "d" * 64},
    }
    records = core.build_records(source, {}, external_acks=external)
    assert records["manifest:hash-one"]["manifest_status"] == "acknowledged"
    assert records["manifest:hash-two"]["manifest_status"] == "baseline_observed"
    assert all(r["validation_status"] == "not_evaluated" for r in records.values())


def test_real_advisor_edit_to_advisory_in_composed_hook(tmp_path):
    """Exercise the vendored advisor, not a monkeypatched callback."""
    host = Host(tmp_path, {"manifest.disabled": True, "advisor.enabled": True,
                           "advisor.ledger_enabled": False})
    _plugin().register(host)
    assert host.hooks["pre_tool_call"](
        tool_name="skill_manage",
        args={"action": "patch", "name": "demo", "old_string": "## Procedure",
              "new_string": "## Procedure\\nConfirm real behavior"},
        session_id="s1",
    ) is None
    queue = host.state.get("advisor.v1", {}).get("pending", [])
    assert len(queue) == 1 and queue[0]["skill"] == "demo"
    result = host.hooks["pre_llm_call"](
        session_id="s1", user_message="continue", is_first_turn=False,
        conversation_history=[{"role": "user", "content": "hi"}],
    )
    assert result is not None and "demo" in result["context"]
    assert host.state.get("advisor.v1", {}).get("pending", []) == []


def test_last_fire_decision_wins_unless_a_live_reminder_is_queued():
    core = _plugin().core
    rows = [
        {"skill": "alpha", "fired_at": 1, "answered_at": None},
        {"skill": "alpha", "fired_at": 2, "answered_at": 3,
         "answered_with": "proof/selection.md"},
    ]
    closed = core.build_records({}, {}, rows)["skill:alpha"]
    assert closed["validation_status"] == "answered_unbound"
    queued = core.build_records({}, {"pending": [
        {"skill": "alpha", "created_at": "now"}
    ]}, rows)["skill:alpha"]
    assert queued["validation_status"] == "probe_advised"


def test_cycle_closure_counts_as_answered_unbound():
    """record_fire closes rows with answered_at + cycle and NO answered_with.

    The live fire-ledger shows this is the majority closure shape (54 of 83
    answered rows). A cycle-closed row must not read as not_evaluated."""
    core = _plugin().core
    rows = [{"skill": "beta", "fired_at": "t1", "answered_at": "t2",
             "cycle": "/skill-probes/beta/cycle-1/selection.md"}]
    rec = core.build_records({}, {}, rows)["skill:beta"]
    assert rec["validation_status"] == "answered_unbound"
    assert rec["evidence"].endswith("selection.md")
    # answered_at with no closure evidence of either kind stays not_evaluated.
    bare = core.build_records({}, {}, [
        {"skill": "gamma", "answered_at": "t2"}])["skill:gamma"]
    assert bare["validation_status"] == "not_evaluated"


def test_same_basename_skills_do_not_overwrite_each_other():
    core = _plugin().core
    state = {"fingerprints": {"h1": {"digest": "a" * 64}, "h2": {"digest": "b" * 64}},
             "findings": {"h1": {"name": "twin", "reason": "changed"},
                          "h2": {"name": "twin", "reason": "changed"}}}
    records = core.build_records(state, {})
    assert "skill:twin" in records  # first occurrence keeps the plain name
    keys = {r["manifest_key"]: r for r in records.values() if r["skill_name"] == "twin"}
    assert set(keys) == {"h1", "h2"}  # both survive, neither overwrites


def test_baseline_provenance_lookup_is_case_insensitive():
    core = _plugin().core
    digest = "a" * 64
    state = {"baseline": {"mixedcase": "adapted"},
             "fingerprints": {"k1": {"digest": digest}},
             "findings": {"k1": {"name": "MixedCase", "reason": "changed"}}}
    records = core.build_records(state, {})
    assert records["skill:MixedCase"]["provenance_status"] == "adapted"


def test_evidence_cache_invalidates_on_ledger_change(tmp_path, monkeypatch):
    core = _plugin().core
    ledger = tmp_path / "skill-probes" / "fire-ledger.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text('{"skill": "a", "fired_at": "t"}\n')
    calls = {"n": 0}
    def counting_load(path):
        calls["n"] += 1
        rows = []
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    advisor_mod = types.SimpleNamespace(
        load_settings=lambda ctx: {"enabled": True, "ledger_enabled": True,
                                   "probe_root": str(tmp_path / "skill-probes")},
        _ledger_path=lambda settings: ledger,
        _load_ledger_rows=counting_load,
    )
    host = Host(tmp_path)
    core.sync_records(host, advisor_mod)
    assert calls["n"] == 1
    core.sync_records(host, advisor_mod)  # unchanged signature: no re-parse
    assert calls["n"] == 1
    records = host.state.get("governance.records", {})
    assert records["skill:a"]["validation_status"] == "probe_advised"
    # A new fire appends to the ledger: signature must change and re-parse.
    with open(ledger, "a", encoding="utf-8") as fh:
        fh.write('{"skill": "b", "fired_at": "t2"}\n')
    # mtime_ns granularity: force a distinct signature deterministically.
    os.utime(ledger, ns=(1_000_000_100, 1_000_000_200))
    core.sync_records(host, advisor_mod)
    assert calls["n"] == 2
    records = host.state.get("governance.records", {})
    assert "skill:b" in records
    # A failed parse must NOT replace the cached good rows with empties.
    def broken_load(path):
        calls["n"] += 1
        raise OSError("transient")
    advisor_mod._load_ledger_rows = broken_load
    os.utime(ledger, ns=(1_000_000_300, 1_000_000_400))
    core.sync_records(host, advisor_mod)
    records = host.state.get("governance.records", {})
    assert "skill:b" in records  # stale-but-good rows survive the failure
