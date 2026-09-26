"""Contract tests for the Lumen memory-source adapter layer.

Authored by the orchestrator (Hermes), NOT the builder. The builder must
make these pass WITHOUT modifying this file. If a test contradicts the
brief, the builder must STOP and report — never weaken a test.

Encodes the contract from DESIGN.md §4b:
- MemorySourceAdapter interface: name / is_available() / load_items(cutoff, now)
- SourceItem field compatibility with wiki_curator.py
- json-file adapter: CoS-compatible memory.json reading, missing file -> []
- mnemosyne adapter: envelope v1.3 shape parsing, superseded skip,
  cutoff filtering, subprocess failure -> [] (never raise)
- none adapter: always empty
- selection: auto (mnemosyne preferred, json-file fallback), unknown -> auto
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Resolve PLUGIN_DIR = the directory containing the `lumen` plugin tree.
# Three supported layouts:
#   A) tests inside plugin:      <root>/lumen/tests/          -> plugin = parents[1]
#   B) tests at plugin root:     <root>/lumen/tests/test_*.py where cwd
#      already resolved to repo root and plugin = parents[1]  (same as A)
#   C) repo-root tests dir:      <root>/tests/ with plugin at <root>/lumen/
# Contract file lives at <root>/lumen/tests/ in the dev tree (brief §layout),
# so layout A is primary; C supports the agent-skills installed layout.
_here = Path(__file__).resolve()
if (_here.parents[1] / "skills" / "curator").exists():
    PLUGIN_DIR = _here.parents[1]                       # layout A
elif (_here.parents[1].name == "lumen-dev" or _here.parents[1].name == "lumen"):
    PLUGIN_DIR = _here.parents[1]                       # plugin tree exists yet; scripts pending
elif (_here.parents[2] / "lumen" / "skills" / "curator").exists():
    PLUGIN_DIR = _here.parents[2] / "lumen"             # layout C
else:
    PLUGIN_DIR = _here.parents[1]
SCRIPTS_DIR = PLUGIN_DIR / "skills" / "curator" / "scripts"
FIXTURES = Path(__file__).parent / "fixtures"


def _import(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def adapters_mod():
    """The adapters module, importable independent of wiki_curator paths."""
    wiki_curator = importlib.util.spec_from_file_location(
        "wc_contract", SCRIPTS_DIR / "wiki_curator.py")
    wc = importlib.util.module_from_spec(wiki_curator)
    sys.modules["wc_contract"] = wc
    wiki_curator.loader.exec_module(wc)
    adapters = importlib.util.spec_from_file_location(
        "adapters_contract", SCRIPTS_DIR / "adapters.py")
    ad = importlib.util.module_from_spec(adapters)
    sys.modules["adapters_contract"] = ad
    adapters.loader.exec_module(ad)
    return ad


def _cutoff(days: int = 30) -> tuple[datetime, datetime]:
    now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
    return now - timedelta(days=days), now


# ─── Interface contract ─────────────────────────────────────────────


class TestAdapterInterface:
    def test_adapter_registry_exposes_three_names(self, adapters_mod):
        """auto/json-file/mnemosyne/none must all resolve; these three
        adapters must exist."""
        names = {a.name for a in adapters_mod.ADAPTERS}
        assert {"json-file", "mnemosyne", "none"} <= names

    def test_sourceitem_fields_match_cos_shape(self, adapters_mod):
        """SourceItem must keep the exact CoS field set — curation logic
        downstream (curate_items, report_changes) depends on it."""
        wc = sys.modules["wc_contract"]
        item = wc.SourceItem(
            source_id="x", source_kind="memory", title="t", text="b",
            timestamp=datetime.now(timezone.utc), raw={})
        for f in ("source_id", "source_kind", "title", "text", "timestamp",
                  "tags", "people", "entities", "projects", "raw"):
            assert hasattr(item, f)


# ─── json-file adapter ──────────────────────────────────────────────


class TestJsonFileAdapter:
    def test_loads_fixture_records(self, adapters_mod, tmp_path):
        """The adapter parses the CoS-shape memory.json fixture into
        SourceItems with people/entities extracted."""
        fixture = json.loads((FIXTURES / "memory.json").read_text())
        assert fixture, "fixture must exist and be non-empty"
        import shutil
        proj = tmp_path / "wiki" / ".knowledge"
        proj.mkdir(parents=True)
        shutil.copy(FIXTURES / "memory.json", proj / "memory.json")
        ad = adapters_mod.get_adapter(
            {"curator": {"memory_source": "json-file"}},
            wiki_path=tmp_path / "wiki")
        cutoff, now = _cutoff()
        items = ad.load_items(cutoff, now)
        assert len(items) >= 2
        assert all(i.source_kind == "memory" for i in items)

    def test_missing_file_returns_empty_list(self, adapters_mod, tmp_path):
        """Missing memory.json -> [] — CoS behavior preserved (never raise)."""
        (tmp_path / "wiki" / ".knowledge").mkdir(parents=True)
        ad = adapters_mod.get_adapter(
            {"curator": {"memory_source": "json-file"}},
            wiki_path=tmp_path / "wiki")
        cutoff, now = _cutoff()
        assert ad.load_items(cutoff, now) == []

    def test_old_records_filtered_by_cutoff(self, adapters_mod, tmp_path):
        """Records older than the cutoff are excluded — fixture carries one."""
        import shutil
        proj = tmp_path / "wiki" / ".knowledge"
        proj.mkdir(parents=True)
        shutil.copy(FIXTURES / "memory.json", proj / "memory.json")
        ad = adapters_mod.get_adapter(
            {"curator": {"memory_source": "json-file"}},
            wiki_path=tmp_path / "wiki")
        # Cutoff 10 years back: everything in.
        now = datetime.now(timezone.utc)
        old_cutoff = now - timedelta(days=3650)
        wide = ad.load_items(old_cutoff, now)
        tight = ad.load_items(now - timedelta(days=1), now)
        assert len(wide) > len(tight), "cutoff must filter old records"


# ─── mnemosyne adapter ──────────────────────────────────────────────


class TestMnemosyneAdapter:
    def test_fixture_is_valid_envelope(self):
        """Fixture must carry the mnemosyne_export marker + working_memory."""
        env = json.loads((FIXTURES / "mnemosyne_export.json").read_text())
        assert "mnemosyne_export" in env
        assert isinstance(env.get("working_memory"), list)
        assert len(env["working_memory"]) >= 3

    def test_parse_envelope_records_to_sourceitems(self, adapters_mod):
        """Parsing the export envelope maps records to SourceItems:
        id->source_id, content->text, timestamp->timestamp, source->tag."""
        env = json.loads((FIXTURES / "mnemosyne_export.json").read_text())
        parser = adapters_mod.parse_mnemosyne_envelope
        assert callable(parser), (
            "adapters.py must expose parse_mnemosyne_envelope(envelope_dict) "
            "-> list[SourceItem]")
        cutoff, now = _cutoff()
        items = parser(env, cutoff, now)
        assert len(items) >= 2
        rec_ids = {i.source_id for i in items}
        assert any(r["id"] in rec_ids for r in env["working_memory"])
        first = items[0]
        assert first.source_kind == "memory"
        assert first.text == first.raw.get("content", first.text)

    def test_superseded_records_skipped(self, adapters_mod):
        """Records with superseded_by set are excluded."""
        env = json.loads((FIXTURES / "mnemosyne_export.json").read_text())
        superseded = [
            r["id"] for r in env["working_memory"] if r.get("superseded_by")]
        assert superseded, "fixture must include a superseded record"
        cutoff, now = _cutoff(days=3650)
        items = adapters_mod.parse_mnemosyne_envelope(env, cutoff, now)
        got_ids = {i.source_id for i in items}
        assert not (set(superseded) & got_ids), (
            "superseded records must not appear in adapter output")

    def test_subprocess_failure_returns_empty_never_raises(
            self, adapters_mod, monkeypatch):
        """A failing `hermes` subprocess must degrade to [], never raise."""
        ad_class = None
        for a in getattr(adapters_mod, "ADAPTERS", []):
            if a.name == "mnemosyne":
                ad_class = a
        assert ad_class is not None
        ad = ad_class()
        monkeypatch.setattr(
            ad, "_run_export", lambda: None, raising=False)
        # If the adapter uses a helper, make it blow up instead:
        def boom():
            raise RuntimeError("hermes not found")
        # Patch at module level too, whichever seam the implementation chose:
        for seam in ("_run_export", "_run_cli", "_export", "run_export"):
            if hasattr(ad, seam):
                monkeypatch.setattr(ad, seam, boom, raising=True)
        monkeypatch.setattr(adapters_mod, "run_mnemosyne_export", boom,
                            raising=False)
        cutoff, now = _cutoff()
        try:
            items = ad.load_items(cutoff, now)
        except RuntimeError:
            pytest.fail("adapter must not raise on subprocess failure")
        assert items == []


# ─── Selection logic ────────────────────────────────────────────────


class TestAdapterSelection:
    def test_none_adapter_returns_empty(self, adapters_mod):
        ad = adapters_mod.get_adapter(
            {"curator": {"memory_source": "none"}}, wiki_path=None)
        cutoff, now = _cutoff()
        assert ad.load_items(cutoff, now) == []

    def test_unknown_value_falls_back_to_auto(self, adapters_mod):
        ad = adapters_mod.get_adapter(
            {"curator": {"memory_source": "telepathy"}}, wiki_path=None)
        assert ad is not None and hasattr(ad, "load_items")

    def test_auto_returns_something(self, adapters_mod, tmp_path, monkeypatch):
        """auto resolves to a working adapter. With mnemosyne unavailable it
        must fall back to json-file (empty here, no raise). Availability is
        monkeypatched so the test is deterministic on hosts where the
        `hermes` CLI exists."""
        class _NoMnemo:
            name = "mnemosyne"

            def is_available(self):
                return False

            def load_items(self, cutoff, now):
                return []
        monkeypatch.setattr(
            adapters_mod.MnemosyneAdapter, "is_available", lambda self: False)
        ad = adapters_mod.get_adapter(
            {"curator": {"memory_source": "auto"}},
            wiki_path=tmp_path / "nowhere")
        assert ad.name == "json-file"
        cutoff, now = _cutoff()
        assert ad.load_items(cutoff, now) == []

    def test_auto_prefers_mnemosyne_when_available(
            self, adapters_mod, monkeypatch):
        """auto picks the mnemosyne adapter when its CLI is present."""
        monkeypatch.setattr(
            adapters_mod.MnemosyneAdapter, "is_available", lambda self: True)
        ad = adapters_mod.get_adapter(
            {"curator": {"memory_source": "auto"}}, wiki_path=None)
        assert ad.name == "mnemosyne"