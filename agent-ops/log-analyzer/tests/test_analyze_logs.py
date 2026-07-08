import importlib.util
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "analyze_logs.py"
spec = importlib.util.spec_from_file_location("analyze_logs", SCRIPT)
assert spec is not None and spec.loader is not None
analyze_logs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze_logs)


def write_log(tmp_path, text):
    path = tmp_path / "agent.log"
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def test_parse_log_line_iso():
    entry = analyze_logs.parse_log_line("2026-07-06T12:30:45Z ERROR gateway: Connection refused")
    assert entry["timestamp"].isoformat() == "2026-07-06T12:30:45+00:00"
    assert entry["level"] == "ERROR"
    assert entry["component"] == "gateway"
    assert entry["message"] == "Connection refused"


def test_parse_log_line_space():
    entry = analyze_logs.parse_log_line("2026-07-06 12:30:45 WARN [cron] job ran long")
    assert entry["timestamp"].isoformat() == "2026-07-06T12:30:45+00:00"
    assert entry["level"] == "WARN"
    assert entry["component"] == "cron"
    assert entry["message"] == "job ran long"


def test_parse_log_line_time_only():
    entry = analyze_logs.parse_log_line("12:30:45 ERROR Connection refused", default_date=date(2026, 7, 6))
    assert entry["timestamp"].isoformat() == "2026-07-06T12:30:45+00:00"
    assert entry["level"] == "ERROR"
    assert entry["component"] == "unknown"
    assert entry["message"] == "Connection refused"


def test_error_clusters(tmp_path):
    log = write_log(
        tmp_path,
        """
2026-07-06 08:00:00 ERROR [gateway] Connection refused to 192.0.2.10:3000
2026-07-06 08:01:00 ERROR [gateway] Connection refused to 192.0.2.11:3001
2026-07-06 08:02:00 ERROR [gateway] Connection refused to 192.0.2.12:3002
""",
    )
    scan = analyze_logs.scan_log_file(str(log))
    clusters = scan["anomalies"]["error_clusters"]
    assert len(clusters) == 1
    assert clusters[0]["count"] == 3
    assert clusters[0]["message"] == "Connection refused to [IP]:[NUM]"


def test_rate_limits(tmp_path):
    log = write_log(
        tmp_path,
        """
2026-07-06T10:00:00Z ERROR agent: provider=openrouter HTTP 429 too many requests
2026-07-06T10:05:00Z WARN agent: openrouter rate limit retrying
2026-07-06T10:15:00Z ERROR agent: quota exceeded for provider openrouter
""",
    )
    scan = analyze_logs.scan_log_file(str(log))
    hits = scan["anomalies"]["rate_limits"]
    assert len(hits) == 1
    assert hits[0]["provider"] == "openrouter"
    assert hits[0]["count"] == 3


def test_timeouts(tmp_path):
    log = write_log(
        tmp_path,
        """
2026-07-06 11:00:00 ERROR [agent] tool_call: web_extract deadline exceeded for https://example.com/a
2026-07-06 11:01:00 WARN [agent] tool_call: web_extract timed out fetching https://example.com/b
2026-07-06 11:02:00 ERROR [agent] tool: web_extract connection timeout
""",
    )
    scan = analyze_logs.scan_log_file(str(log))
    timeouts = scan["anomalies"]["timeouts"]
    assert len(timeouts) == 1
    assert timeouts[0]["tool"] == "web_extract"
    assert timeouts[0]["count"] == 3
    assert "https://example.com/a" in timeouts[0]["urls"]


def test_tool_failures(tmp_path):
    log = write_log(
        tmp_path,
        """
2026-07-06 12:00:00 ERROR [tools] terminal: command not found: xyz
2026-07-06 12:01:00 ERROR [agent] tool: terminal timeout waiting for process
2026-07-06 12:02:00 ERROR [agent] tool_call: web_search HTTP 500 upstream
""",
    )
    scan = analyze_logs.scan_log_file(str(log))
    failures = {item["tool"]: item for item in scan["anomalies"]["tool_failures"]}
    assert failures["terminal"]["count"] == 2
    assert failures["web_search"]["count"] == 1


def test_crashes(tmp_path):
    log = write_log(
        tmp_path,
        """
2026-07-06 15:29:59 INFO [agent] starting session
2026-07-06 15:30:00 ERROR [agent] Traceback (most recent call last):
  File "runner.py", line 12, in <module>
    run()
KeyError: 'session_id'
2026-07-06 15:30:01 INFO [agent] cleanup
""",
    )
    scan = analyze_logs.scan_log_file(str(log))
    crashes = scan["anomalies"]["crashes"]
    assert len(crashes) == 1
    assert crashes[0]["type"] == "stack_trace"
    assert crashes[0]["message"] == "KeyError: 'session_id'"
    assert any("cleanup" in line for line in crashes[0]["context"])


def test_component_breakdown(tmp_path):
    log = write_log(
        tmp_path,
        """
2026-07-06 12:00:00 ERROR [gateway] Connection refused
2026-07-06 12:01:00 WARN [gateway] retrying
2026-07-06 12:02:00 ERROR [agent] failed task
2026-07-06 12:03:00 WARNING cron: skipped stale job
""",
    )
    scan = analyze_logs.scan_log_file(str(log))
    assert scan["component_breakdown"]["gateway"] == {"errors": 1, "warnings": 1}
    assert scan["component_breakdown"]["agent"] == {"errors": 1, "warnings": 0}
    assert scan["component_breakdown"]["cron"] == {"errors": 0, "warnings": 1}


def test_error_timeline(tmp_path):
    log = write_log(
        tmp_path,
        """
2026-07-06 08:00:00 ERROR [gateway] one
2026-07-06 08:30:00 ERROR [gateway] two
2026-07-06 10:00:00 ERROR [gateway] three
""",
    )
    scan = analyze_logs.scan_log_file(str(log))
    assert scan["error_timeline"] == {"08:00": 2, "10:00": 1}


def test_time_window_filter(tmp_path):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    old = now - timedelta(hours=48)
    recent = now - timedelta(hours=1)
    log = write_log(
        tmp_path,
        f"""
{old.strftime('%Y-%m-%d %H:%M:%S')} ERROR [gateway] old failure
{recent.strftime('%Y-%m-%d %H:%M:%S')} ERROR [gateway] recent failure
""",
    )
    scan = analyze_logs.scan_log_file(str(log), since="24h")
    assert scan["lines_analyzed"] == 1
    assert scan["total_errors"] == 1
    assert scan["error_timeline"] == {recent.strftime("%H:00"): 1}


def test_multiline_stack_trace(tmp_path):
    log = write_log(
        tmp_path,
        """
2026-07-06 15:30:00 ERROR [agent] Traceback (most recent call last):
  File "runner.py", line 12, in <module>
    run()
ValueError: bad input
""",
    )
    entries, _lines = analyze_logs.read_entries(str(log))
    assert len(entries) == 1
    assert entries[0]["line_count"] == 4
    scan = analyze_logs.scan_log_file(str(log))
    assert len(scan["anomalies"]["crashes"]) == 1


def test_quiet_mode(tmp_path):
    log = write_log(
        tmp_path,
        """
2026-07-06 12:00:00 INFO [agent] ok
2026-07-06 12:01:00 WARN [agent] expected retry
""",
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "scan", "--log-file", str(log), "--quiet"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_report_generation(tmp_path):
    scan = {
        "log_file": "agent.log",
        "lines_analyzed": 3,
        "time_window": "24h",
        "total_errors": 3,
        "total_warnings": 1,
        "has_anomalies": True,
        "anomalies": {
            "error_clusters": [
                {"message": "Connection refused to [IP]:[NUM]", "count": 3, "first_seen": "2026-07-06T08:00:00Z", "last_seen": "2026-07-06T08:02:00Z"}
            ],
            "rate_limits": [],
            "timeouts": [{"tool": "web_extract", "count": 2, "urls": []}],
            "tool_failures": [{"tool": "terminal", "count": 1, "top_error_counts": [{"message": "timeout", "count": 1}]}],
            "crashes": [],
        },
        "component_breakdown": {"gateway": {"errors": 3, "warnings": 1}},
        "error_timeline": {"08:00": 3},
    }
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(json.dumps(scan), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "report", "--scan", str(scan_path)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "# Log Analysis Report" in result.stdout
    assert "## Error Clusters (1)" in result.stdout
    assert "Connection refused to [IP]:[NUM]" in result.stdout
    assert "## Component Breakdown" in result.stdout
    assert "08:00 ███ 3" in result.stdout
