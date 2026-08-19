"""Tests for log-analyzer's state.db failure-rate monitor (state_failures.py).

Hazard being defended: naive regex-over-content failure detection flags
successful tool output that merely MENTIONS error words (spike on the real
MH profile state.db: Dojo's regex claimed read_file at 70% failure, but
structured exit_code parsing shows the true rate is 0%). The monitor must
use structured signals (exit_code) for JSON-mode tools and a narrow fatal
marker list for text-mode tools.
"""

import importlib.util
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "state_failures.py"
spec = importlib.util.spec_from_file_location("state_failures", SCRIPT)
assert spec is not None and spec.loader is not None
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)


def make_db(tmp_path, rows):
    """Build a minimal state.db with only the columns the monitor reads."""
    db = tmp_path / "state.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, started_at REAL)"
    )
    con.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, "
        "role TEXT, content TEXT, tool_name TEXT, timestamp REAL)"
    )
    for row in rows:
        con.execute(
            "INSERT INTO messages (session_id, role, content, tool_name, timestamp) "
            "VALUES (?,?,?,?,?)",
            row,
        )
    con.commit()
    con.close()
    return str(db)


def t_row(tool, content, ts=None, role="tool", session="s1"):
    return (session, role, content, tool, ts if ts is not None else time.time())


# --- classify_result: structured JSON mode -----------------------------

def test_json_exit_code_nonzero_is_failure():
    mode, is_fail, _ = sf.classify_result('{"output": "boom", "exit_code": 1}')
    assert mode == "json"
    assert is_fail is True


def test_json_exit_code_zero_is_success():
    mode, is_fail, _ = sf.classify_result('{"output": "ok", "exit_code": 0}')
    assert mode == "json"
    assert is_fail is False


def test_json_no_exit_code_field_is_success():
    # Structured results without an exit_code carry no failure signal.
    mode, is_fail, _ = sf.classify_result('{"output": "ok"}')
    assert mode == "json"
    assert is_fail is False


def test_json_nested_exit_code_detected():
    content = '{"output": {"output": "x", "exit_code": 2}}'
    mode, is_fail, _ = sf.classify_result(content)
    assert mode == "json"
    assert is_fail is True


# --- classify_result: text mode with narrow fatal markers --------------

def test_text_fatal_marker_is_failure():
    mode, is_fail, _ = sf.classify_result("sh: 1: python3: command not found")
    assert mode == "text"
    assert is_fail is True


def test_text_mention_of_error_word_is_NOT_failure():
    # THE spike regression: content that merely discusses error handling
    # must not count as a failure.
    mode, is_fail, _ = sf.classify_result(
        "Error paths? Tests cover the change? Readability: another engineer"
    )
    assert mode == "text"
    assert is_fail is False


def test_text_academic_mention_is_NOT_failure():
    mode, is_fail, _ = sf.classify_result(
        "the Scaled Error (Hyndman & Koehler 2006, with scored-window fallback)"
    )
    assert mode == "text"
    assert is_fail is False


def test_malformed_json_falls_back_to_text():
    mode, is_fail, _ = sf.classify_result('{"output": "unterminated')
    assert mode == "text"
    assert is_fail is False


def test_empty_content_is_success():
    mode, is_fail, _ = sf.classify_result("")
    assert mode == "empty"
    assert is_fail is False


# --- categorize failure ------------------------------------------------

def test_categorize_timeout():
    assert sf.categorize_failure("the command timed out after 600s") == "timeout"


def test_categorize_network():
    assert sf.categorize_failure("Connection refused to 192.168.50.188:3000") == "network"


def test_categorize_command_not_found():
    assert sf.categorize_failure("bash: rg: command not found") == "command_not_found"


def test_categorize_not_found():
    assert sf.categorize_failure("Error: no such file or directory: /tmp/x") == "not_found"


def test_categorize_permission():
    assert sf.categorize_failure("Permission denied (publickey)") == "permission"


def test_categorize_traceback():
    assert sf.categorize_failure("Traceback (most recent call last):\nTypeError") == "explicit_error"


def test_categorize_other():
    assert sf.categorize_failure("") == "other"


# --- analyze_state_db --------------------------------------------------

def test_analyze_totals_and_rates(tmp_path):
    now = time.time()
    rows = [
        # terminal: 4 calls, 1 failure (exit_code 1)
        t_row("terminal", '{"output": "ok", "exit_code": 0}', now),
        t_row("terminal", '{"output": "ok", "exit_code": 0}', now),
        t_row("terminal", '{"output": "ok", "exit_code": 0}', now),
        t_row("terminal", '{"output": "boom", "exit_code": 1}', now),
        # read_file: mentions error words but is a success (no exit_code)
        t_row("read_file", '{"content": "error handling is hard"}', now),
        # web_extract: text mode, benign
        t_row("web_extract", "page about exceptions and errors", now),
        # process: 2 calls, 1 failure
        t_row("process", '{"output": "ok", "exit_code": 0}', now),
        t_row("process", '{"output": "timed out", "exit_code": 124}', now),
    ]
    db = make_db(tmp_path, rows)
    res = sf.analyze_state_db(db, days=7, min_calls=2)

    assert res["tool_calls"] == 8
    assert res["failures"] == 2
    tools = {t["tool"]: t for t in res["tools"]}
    assert tools["terminal"]["total"] == 4
    assert tools["terminal"]["failures"] == 1
    assert tools["terminal"]["success_rate"] == 75.0
    # read_file and web_extract must NOT count as failing
    assert tools["read_file"]["failures"] == 0
    assert tools["web_extract"]["failures"] == 0
    # failure categories aggregated (list of {category, count, tools})
    cats = {c["category"]: c for c in res["categories"]}
    assert cats["timeout"]["count"] == 1
    assert cats["timeout"]["tools"].get("process") == 1
    # top tools ranked by failure rate, only ≥ min_calls
    top = [t["tool"] for t in res["top_tools"]]
    assert top == ["process", "terminal"]

def test_window_excludes_old_rows(tmp_path):
    old = time.time() - 10 * 86400
    rows = [
        t_row("terminal", '{"output": "old fail", "exit_code": 1}', old),
        t_row("terminal", '{"output": "ok", "exit_code": 0}', time.time()),
    ]
    db = make_db(tmp_path, rows)
    res = sf.analyze_state_db(db, days=7)
    assert res["tool_calls"] == 1
    assert res["failures"] == 0


def test_low_sample_tools_excluded_from_ranking(tmp_path):
    rows = [
        t_row("terminal", '{"output": "ok", "exit_code": 0}', time.time()),
        # browser_navigate: a real failure but only 1 call total
        t_row("browser_navigate", '{"output": "x", "exit_code": 1}', time.time()),
    ]
    db = make_db(tmp_path, rows)
    res = sf.analyze_state_db(db, days=7, min_calls=5)
    tools = {t["tool"]: t for t in res["tools"]}
    assert tools["browser_navigate"]["failures"] == 1
    assert all(t["tool"] != "browser_navigate" for t in res["top_tools"])


def test_sessions_count_best_effort(tmp_path):
    db = make_db(tmp_path, [t_row("terminal", '{"output": "ok", "exit_code": 0}')])
    con = sqlite3.connect(db)
    con.execute("INSERT INTO sessions (id, started_at) VALUES ('s1', ?)", (time.time(),))
    con.commit()
    con.close()
    res = sf.analyze_state_db(db, days=7)
    assert res["sessions_analyzed"] == 1


def test_missing_db_returns_error(tmp_path):
    res = sf.analyze_state_db(str(tmp_path / "nope.db"), days=7)
    assert "error" in res


# --- CLI / cron quiet mode ---------------------------------------------

def _run_cli(tmp_path, *args):
    db = make_db(tmp_path, [])
    cmd = [sys.executable, str(SCRIPT), "--db", db, *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def test_quiet_mode_silent_when_no_failures(tmp_path):
    r = _run_cli(tmp_path, "--quiet")
    assert r.returncode == 0
    assert r.stdout.strip() == ""


def test_quiet_mode_reports_when_failures(tmp_path):
    now = time.time()
    rows = [t_row("terminal", '{"output": "boom", "exit_code": 1}', now)]
    db = make_db(tmp_path, rows)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", db, "--quiet"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "terminal" in r.stdout
    assert "8.0" not in r.stdout  # sanity: real numbers, not placeholder


def test_json_output_shape(tmp_path):
    now = time.time()
    rows = [t_row("terminal", '{"output": "boom", "exit_code": 1}', now)]
    db = make_db(tmp_path, rows)
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--db", db, "--json"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert d["failures"] == 1
    assert d["tools"][0]["tool"] == "terminal"
