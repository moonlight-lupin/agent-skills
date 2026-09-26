#!/usr/bin/env python3
"""Hardening tests for adapter source IDs and mnemosyne failure reporting."""

from __future__ import annotations

import sys
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "skills" / "curator" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import adapters  # noqa: E402
import wiki_curator  # noqa: E402  # SourceItem owner, required by parse_mnemosyne_envelope


def test_normalise_source_id_is_deterministic():
    record = {"title": "Pricing review", "text": "Dana asked about timeline."}
    first = adapters._normalise_source_id("memory", record)
    second = adapters._normalise_source_id("memory", record)
    assert first == second
    assert re.fullmatch(r"memory_[0-9a-f]{12}", first)


def test_normalise_source_id_sanitizes_unsafe_characters():
    record = {"id": "evil id!with spaces/x"}
    source_id = adapters._normalise_source_id("memory", record)
    assert "!" not in source_id
    assert "/" not in source_id
    assert " " not in source_id
    assert source_id == "evil_id_with_spaces_x"


def test_mnemosyne_passthrough_ids_are_sanitized():
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    items = adapters.parse_mnemosyne_envelope(
        {
            "working_memory": [
                {
                    "id": "evil id!with spaces/x",
                    "content": "Dana asked about pricing.",
                    "timestamp": now.isoformat(),
                }
            ]
        },
        cutoff=now - timedelta(days=1),
        now=now,
    )
    assert len(items) == 1
    source_id = items[0].source_id
    assert "!" not in source_id
    assert "/" not in source_id
    assert " " not in source_id
    assert source_id == "evil_id_with_spaces_x"


def test_mnemosyne_export_nonzero_exit_warns(capsys):
    with patch("adapters.shutil.which", return_value="/usr/bin/hermes"):
        with patch("adapters.subprocess.run") as run:
            run.return_value.returncode = 1
            result = adapters.run_mnemosyne_export()
    assert result is None
    err = capsys.readouterr().err
    assert err.count("warning: mnemosyne export failed") == 1
    assert "considering 0 records" in err


def test_mnemosyne_export_timeout_warns(capsys):
    with patch("adapters.shutil.which", return_value="/usr/bin/hermes"):
        with patch("adapters.subprocess.run", side_effect=adapters.subprocess.TimeoutExpired(cmd="hermes", timeout=120)):
            result = adapters.run_mnemosyne_export()
    assert result is None
    err = capsys.readouterr().err
    assert "warning: mnemosyne export failed (timeout); considering 0 records" in err


def test_empty_sanitized_id_matches_prefix_digest():
    record = {"id": "!!!"}
    source_id = adapters._normalise_source_id("memory", record)
    assert re.fullmatch(r"memory_[0-9a-f]{12}", source_id)

    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    items = adapters.parse_mnemosyne_envelope(
        {
            "working_memory": [
                {
                    "id": "@@@",
                    "content": "Dana asked about pricing.",
                    "timestamp": now.isoformat(),
                }
            ]
        },
        cutoff=now - timedelta(days=1),
        now=now,
    )
    assert len(items) == 1
    assert re.fullmatch(r"memory_[0-9a-f]{12}", items[0].source_id)


def test_mnemosyne_export_bad_json_warns(tmp_path, capsys):
    fd, tmp_name = tempfile.mkstemp(prefix="lumen-mnemosyne-test-", suffix=".json")
    export_path = Path(tmp_name)
    export_path.write_text("not-json", encoding="utf-8")
    try:
        with patch("adapters.shutil.which", return_value="/usr/bin/hermes"):
            with patch("adapters.tempfile.mkstemp", return_value=(fd, tmp_name)):
                with patch("adapters.subprocess.run") as run:
                    run.return_value.returncode = 0
                    result = adapters.run_mnemosyne_export()
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    assert result is None
    err = capsys.readouterr().err
    assert err.count("warning: mnemosyne export failed") == 1
    assert "considering 0 records" in err
    assert "Dana" not in err


def test_mnemosyne_export_exception_leaks_type_only(capsys):
    secret = "SYNTHETIC_PRIVATE_VALUE"
    with patch("adapters.shutil.which", return_value="/usr/bin/hermes"):
        with patch("adapters.subprocess.run", side_effect=OSError(secret)):
            result = adapters.run_mnemosyne_export()
    assert result is None
    err = capsys.readouterr().err
    assert "warning: mnemosyne export failed" in err
    assert "OSError" in err
    assert secret not in err
    assert err.count("\n") == 1


def test_mnemosyne_load_items_exception_leaks_type_only(capsys):
    secret = "SYNTHETIC_PRIVATE_VALUE"
    adapter = adapters.MnemosyneAdapter()
    now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    with patch.object(adapter, "_run_export", side_effect=RuntimeError(secret)):
        items = adapter.load_items(now - timedelta(days=1), now)
    assert items == []
    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert secret not in err
    assert err.count("\n") == 1


def test_mnemosyne_export_argv_uses_script_path_without_shell():
    hermes = "/usr/bin/hermes"
    with patch("adapters.shutil.which", return_value=hermes):
        with patch("adapters.subprocess.run") as run:
            run.return_value.returncode = 1
            adapters.run_mnemosyne_export()
    assert run.call_count == 1
    args, kwargs = run.call_args
    argv = args[0]
    assert argv[0] == hermes
    assert argv[1:3] == ["mnemosyne", "export"]
    assert "--output" in argv
    assert kwargs.get("shell") in (None, False)


def test_mnemosyne_tempfile_cleaned_up_on_failure():
    created: list[str] = []
    real_mkstemp = tempfile.mkstemp

    def spy_mkstemp(*args, **kwargs):
        fd, name = real_mkstemp(*args, **kwargs)
        created.append(name)
        return fd, name

    with patch("adapters.shutil.which", return_value="/usr/bin/hermes"):
        with patch("adapters.tempfile.mkstemp", side_effect=spy_mkstemp):
            with patch("adapters.subprocess.run", side_effect=OSError("synthetic export failure")):
                result = adapters.run_mnemosyne_export()
    assert result is None
    assert created
    for name in created:
        assert not Path(name).exists()
