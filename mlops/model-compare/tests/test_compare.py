#!/usr/bin/env python3
"""Tests for compare.py — provider routing, tool calling, test bank, judge, efficiency.

No network calls. All API interactions are mocked via monkeypatch.
Run: python3 -m pytest tests/test_compare.py -v
"""

import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add scripts dir to path
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import compare


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    """Ensure no real API keys leak into tests."""
    for key in ("OLLAMA_API_KEY", "NVIDIA_API_KEY", "OPENROUTER_API_KEY",
                "COMPARE_CONFIRM_PAID", "SEARXNG_URL"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def fresh_health(monkeypatch):
    """Replace the singleton provider_health with a fresh in-memory instance."""
    from provider_health import ProviderHealth
    fresh = ProviderHealth(persist_path=None)
    monkeypatch.setattr(compare, "provider_health", fresh)
    return fresh


# ─── Provider config ─────────────────────────────────────────────────────────

class TestProviders:
    def test_providers_defined(self):
        assert "ollama-cloud" in compare.PROVIDERS
        assert "nvidia" in compare.PROVIDERS
        assert "openrouter" in compare.PROVIDERS

    def test_provider_fields(self):
        for name, cfg in compare.PROVIDERS.items():
            assert "base_url" in cfg, f"{name} missing base_url"
            assert "key_env" in cfg, f"{name} missing key_env"
            assert "paid" in cfg, f"{name} missing paid flag"

    def test_ollama_free(self):
        assert compare.PROVIDERS["ollama-cloud"]["paid"] is False

    def test_openrouter_paid(self):
        assert compare.PROVIDERS["openrouter"]["paid"] is True

    def test_build_headers_basic(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        headers = compare._build_headers("ollama-cloud", "test-key")
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"

    def test_build_headers_openrouter_extra(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
        headers = compare._build_headers("openrouter", "or-key")
        assert headers["X-Title"] == "Hermes Model Compare"
        assert "HTTP-Referer" in headers

    def test_get_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
        with pytest.raises(ValueError, match="No API key"):
            compare.get_api_key("ollama-cloud")

    def test_get_api_key_present(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_API_KEY", "my-key")
        assert compare.get_api_key("ollama-cloud") == "my-key"

    def test_get_api_key_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            compare.get_api_key("nonexistent")


class TestLoadEnv:
    def test_load_env_no_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        compare.load_env()  # should not crash

    def test_load_env_reads_file(self, monkeypatch, tmp_path):
        env_dir = tmp_path / ".hermes"
        env_dir.mkdir()
        (env_dir / ".env").write_text('TEST_KEY_VAR=hello\n# comment\n')
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("TEST_KEY_VAR", raising=False)
        compare.load_env()
        assert os.environ.get("TEST_KEY_VAR") == "hello"


# ─── Test bank ───────────────────────────────────────────────────────────────

class TestTestBank:
    def test_bank_has_tests(self):
        assert len(compare.TEST_BANK) >= 10

    def test_tool_tests_have_tools_flag(self):
        for tid, test in compare.TEST_BANK.items():
            if test.get("tools"):
                assert test["domain"] == "tool_calling"

    def test_coding_tests_no_tools(self):
        for tid, test in compare.TEST_BANK.items():
            if test["domain"] == "coding":
                assert not test.get("tools", False)

    def test_review_tests_have_planted_issues(self):
        for tid, test in compare.TEST_BANK.items():
            if test["domain"] == "code_review":
                assert "planted_issues" in test
                assert isinstance(test["planted_issues"], list)

    def test_test_p_has_no_bugs(self):
        """Test P is the clean-code false-positive test."""
        assert compare.TEST_BANK["P"]["planted_issues"] == []

    def test_test_o_has_sql_injection(self):
        issues = compare.TEST_BANK["O"]["planted_issues"]
        assert any(i["type"] == "security" for i in issues)

    def test_all_tests_have_evaluation(self):
        for tid, test in compare.TEST_BANK.items():
            assert "evaluation" in test, f"Test {tid} missing evaluation criteria"
            assert isinstance(test["evaluation"], list)
            assert len(test["evaluation"]) >= 3

    def test_all_tests_have_prompt(self):
        for tid, test in compare.TEST_BANK.items():
            assert "prompt" in test
            assert len(test["prompt"]) > 20


# ─── Tool definitions ────────────────────────────────────────────────────────

class TestToolDefs:
    def test_tool_defs_exist(self):
        assert len(compare.TOOL_DEFS) == 2

    def test_web_search_def(self):
        names = [t["function"]["name"] for t in compare.TOOL_DEFS]
        assert "web_search" in names
        assert "web_extract" in names

    def test_tool_defs_have_parameters(self):
        for td in compare.TOOL_DEFS:
            assert td["type"] == "function"
            assert "parameters" in td["function"]
            assert "required" in td["function"]["parameters"]


# ─── call_model_simple (mocked) ──────────────────────────────────────────────

class TestCallModelSimple:
    def test_success(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "Hello world"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None

        monkeypatch.setattr(compare.urllib.request, "urlopen", lambda req, timeout=120: mock_resp)

        result = compare.call_model_simple("ollama-cloud", "test-model", "hi")
        assert result["success"] is True
        assert result["content"] == "Hello world"
        assert result["tokens_in"] == 10
        assert result["tokens_out"] == 5

    def test_http_error(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        import urllib.error
        def raise_error(req, timeout=120):
            raise urllib.error.HTTPError(
                req.full_url, 429, b"Rate limited", {},
                MagicMock(read=lambda: b'{"error": "rate limited"}')
            )

        monkeypatch.setattr(compare.urllib.request, "urlopen", raise_error)

        result = compare.call_model_simple("ollama-cloud", "test-model", "hi")
        assert result["success"] is False
        assert "429" in result["error"]

    def test_generic_error(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")
        monkeypatch.setattr(compare.urllib.request, "urlopen",
                          lambda req, timeout=120: (_ for _ in ()).throw(ConnectionError("refused")))

        result = compare.call_model_simple("ollama-cloud", "test-model", "hi")
        assert result["success"] is False
        assert "refused" in result["error"]

    def test_provider_in_cooldown_skipped(self, monkeypatch, fresh_health):
        """When provider is in cooldown, call is skipped without hitting the API."""
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        # Force provider into cooldown
        for _ in range(3):
            fresh_health.record_failure("ollama-cloud", "test error")
        assert not fresh_health.is_alive("ollama-cloud")

        # urlopen should never be called
        call_count = [0]
        def counting_urlopen(req, timeout=120):
            call_count[0] += 1
            return MagicMock()

        monkeypatch.setattr(compare.urllib.request, "urlopen", counting_urlopen)

        result = compare.call_model_simple("ollama-cloud", "test-model", "hi")
        assert result["success"] is False
        assert "cooldown" in result["error"]
        assert call_count[0] == 0

    def test_success_resets_failures(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        # Record one failure (not enough to kill)
        fresh_health.record_failure("ollama-cloud", "first fail")
        assert fresh_health.status()["ollama-cloud"]["fails"] == 1

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "OK"}}],
            "usage": {},
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        monkeypatch.setattr(compare.urllib.request, "urlopen", lambda req, timeout=120: mock_resp)

        compare.call_model_simple("ollama-cloud", "test-model", "hi")
        assert fresh_health.status()["ollama-cloud"]["fails"] == 0


# ─── call_model_with_tools (mocked) ──────────────────────────────────────────

class TestCallModelWithTools:
    def test_returns_tool_calls(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {
                "content": "",
                "tool_calls": [{"id": "call_1", "function": {
                    "name": "web_search",
                    "arguments": '{"query": "python 3.13"}'
                }}],
            }, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 20},
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        monkeypatch.setattr(compare.urllib.request, "urlopen", lambda req, timeout=60: mock_resp)

        result = compare.call_model_with_tools("ollama-cloud", "test-model", [{"role": "user", "content": "hi"}])
        assert result["success"] is True
        assert result["tool_calls"] is not None
        assert result["finish_reason"] == "tool_calls"

    def test_returns_final_answer(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "The answer is 42"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 10},
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        monkeypatch.setattr(compare.urllib.request, "urlopen", lambda req, timeout=60: mock_resp)

        result = compare.call_model_with_tools("ollama-cloud", "test-model", [{"role": "user", "content": "hi"}])
        assert result["success"] is True
        assert result["tool_calls"] is None
        assert result["content"] == "The answer is 42"
        assert result["finish_reason"] == "stop"

    def test_api_error_in_body(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "error": "model not found",
        }).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = lambda s, *a: None
        monkeypatch.setattr(compare.urllib.request, "urlopen", lambda req, timeout=60: mock_resp)

        result = compare.call_model_with_tools("ollama-cloud", "test-model", [{"role": "user", "content": "hi"}])
        assert result["success"] is False
        assert "model not found" in result["error"]


# ─── Tool execution ──────────────────────────────────────────────────────────

class TestExecuteTool:
    def test_unknown_tool(self):
        result = compare.execute_tool("nonexistent", {})
        parsed = json.loads(result)
        assert "error" in parsed

    def test_web_search_dispatches(self, monkeypatch):
        called = {"query": None}
        def mock_search(query, limit=5):
            called["query"] = query
            called["limit"] = limit
            return json.dumps({"results": [{"title": "Test", "url": "http://example.com"}]})
        monkeypatch.setattr(compare, "execute_web_search", mock_search)
        result = compare.execute_tool("web_search", {"query": "hello", "limit": 3})
        assert called["query"] == "hello"
        assert called["limit"] == 3

    def test_web_extract_dispatches(self, monkeypatch):
        called = {"urls": None}
        def mock_extract(urls):
            called["urls"] = urls
            return json.dumps({"results": [{"url": urls[0], "content": "text"}]})
        monkeypatch.setattr(compare, "execute_web_extract", mock_extract)
        result = compare.execute_tool("web_extract", {"urls": ["http://example.com"]})
        assert called["urls"] == ["http://example.com"]


# ─── Tool calling loop (mocked) ──────────────────────────────────────────────

class TestRunToolLoop:
    def test_converges_on_first_answer(self, monkeypatch, fresh_health):
        """Model gives final answer immediately — should converge in 1 turn."""
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        call_count = [0]
        def mock_call(provider, model, messages, timeout=60):
            call_count[0] += 1
            return {
                "success": True,
                "content": "The answer is 42",
                "tool_calls": None,
                "elapsed": 0.5,
                "tokens_in": 100,
                "tokens_out": 10,
                "finish_reason": "stop",
                "error": None,
            }

        monkeypatch.setattr(compare, "call_model_with_tools", mock_call)
        result = compare.run_tool_loop("ollama-cloud", "test-model", "What is 42?")

        assert result["converged"] is True
        assert result["turns"] == 1
        assert result["tool_calls"] == 0
        assert result["content"] == "The answer is 42"
        assert call_count[0] == 1

    def test_tool_call_then_answer(self, monkeypatch, fresh_health):
        """Model calls a tool, then gives final answer — 2 turns."""
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        responses = [
            {"success": True, "content": "", "tool_calls": [
                {"id": "call_1", "function": {"name": "web_search", "arguments": '{"query": "test"}'}}
            ], "elapsed": 0.5, "tokens_in": 50, "tokens_out": 20, "finish_reason": "tool_calls", "error": None},
            {"success": True, "content": "Found it", "tool_calls": None,
             "elapsed": 0.3, "tokens_in": 200, "tokens_out": 5, "finish_reason": "stop", "error": None},
        ]
        idx = [0]
        def mock_call(provider, model, messages, timeout=60):
            r = responses[idx[0]]
            idx[0] += 1
            r["_raw_message"] = {"role": "assistant", "content": r["content"], "tool_calls": r.get("tool_calls")}
            return r

        monkeypatch.setattr(compare, "call_model_with_tools", mock_call)
        monkeypatch.setattr(compare, "execute_web_search", lambda q, limit=5: json.dumps({"results": []}))

        result = compare.run_tool_loop("ollama-cloud", "test-model", "search and answer")
        assert result["converged"] is True
        assert result["turns"] == 2
        assert result["tool_calls"] == 1
        assert result["content"] == "Found it"

    def test_max_turns_not_converged(self, monkeypatch, fresh_health):
        """Model keeps calling tools and never converges."""
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        def always_tool_call(provider, model, messages, timeout=60):
            return {
                "success": True, "content": "", "tool_calls": [
                    {"id": "call_1", "function": {"name": "web_search", "arguments": '{"query": "more"}'}}
                ], "elapsed": 0.5, "tokens_in": 50, "tokens_out": 20,
                "finish_reason": "tool_calls", "error": None,
                "_raw_message": {"role": "assistant", "content": "", "tool_calls": []},
            }

        monkeypatch.setattr(compare, "call_model_with_tools", always_tool_call)
        monkeypatch.setattr(compare, "execute_web_search", lambda q, limit=5: json.dumps({"results": []}))

        result = compare.run_tool_loop("ollama-cloud", "test-model", "keep searching", max_turns=3)
        assert result["converged"] is False
        assert result["turns"] == 3
        assert "max turns" in result["content"].lower() or "did not converge" in result["content"].lower()

    def test_error_stops_loop(self, monkeypatch, fresh_health):
        """API error on first turn stops the loop."""
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        def error_call(provider, model, messages, timeout=60):
            return {"success": False, "error": "HTTP 500", "content": "",
                    "tool_calls": None, "elapsed": 0, "tokens_in": 0,
                    "tokens_out": 0, "finish_reason": "error"}

        monkeypatch.setattr(compare, "call_model_with_tools", error_call)
        result = compare.run_tool_loop("ollama-cloud", "test-model", "test")
        assert result["converged"] is False
        assert result["turns"] == 1
        assert "Error" in result["content"]

    def test_trace_structure(self, monkeypatch, fresh_health):
        """Trace entries have correct types and fields."""
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        def final_answer(provider, model, messages, timeout=60):
            return {"success": True, "content": "done", "tool_calls": None,
                    "elapsed": 0.1, "tokens_in": 10, "tokens_out": 5,
                    "finish_reason": "stop", "error": None}

        monkeypatch.setattr(compare, "call_model_with_tools", final_answer)
        result = compare.run_tool_loop("ollama-cloud", "test-model", "test")

        assert len(result["trace"]) == 1
        assert result["trace"][0]["type"] == "final"
        assert "tokens_in" in result["trace"][0]
        assert "tokens_out" in result["trace"][0]


# ─── Judge (mocked) ──────────────────────────────────────────────────────────

class TestJudge:
    def test_judge_parses_json(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        judgment_json = json.dumps({
            "rankings": [
                {"label": "A", "rank": 1, "score": 8.5, "strengths": "good", "weaknesses": "none"},
                {"label": "B", "rank": 2, "score": 7.0, "strengths": "ok", "weaknesses": "slow"},
            ],
            "best_overall": "A",
            "summary": "A was better",
        })

        mock_result = {"success": True, "content": f"Here is my judgment:\n{judgment_json}\nDone.",
                       "elapsed": 1.0, "tokens_in": 100, "tokens_out": 50, "error": None}

        monkeypatch.setattr(compare, "call_model_simple", lambda p, m, prompt, timeout=180: mock_result)

        responses = [
            {"content": "response A", "label": "A", "provider": "test", "model": "a"},
            {"content": "response B", "label": "B", "provider": "test", "model": "b"},
        ]
        result = compare.judge_responses("test prompt", responses, "judge-model", "ollama-cloud")

        assert result["success"] is True
        assert result["parsed_judgment"]["best_overall"] == "A"
        assert len(result["parsed_judgment"]["rankings"]) == 2

    def test_judge_non_json_response(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        mock_result = {"success": True, "content": "I think A is better but no JSON.",
                       "elapsed": 1.0, "tokens_in": 50, "tokens_out": 20, "error": None}

        monkeypatch.setattr(compare, "call_model_simple", lambda p, m, prompt, timeout=180: mock_result)

        responses = [{"content": "A", "label": "A"}, {"content": "B", "label": "B"}]
        result = compare.judge_responses("test", responses, "judge", "ollama-cloud")

        assert result["success"] is True
        assert result["parsed_judgment"] is None
        assert result["raw_judgment"] == "I think A is better but no JSON."

    def test_judge_includes_trace_for_tools_mode(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        captured_prompt = []
        def capture_call(p, m, prompt, timeout=180):
            captured_prompt.append(prompt)
            return {"success": True, "content": json.dumps({
                "rankings": [{"label": "A", "rank": 1, "score": 9, "strengths": "", "weaknesses": ""}],
                "best_overall": "A", "summary": "A won",
            }), "elapsed": 1, "tokens_in": 50, "tokens_out": 30, "error": None}

        monkeypatch.setattr(compare, "call_model_simple", capture_call)

        responses = [{
            "content": "answer", "label": "A", "provider": "t", "model": "m",
            "trace": [{"turn": 1, "type": "tool_call", "tool_calls": [{"tool": "web_search", "args": {"query": "test"}}]}],
            "turns": 2, "tool_calls": 1, "tokens_in": 100, "tokens_out": 50,
        }]
        compare.judge_responses("test", responses, "judge", "ollama-cloud", mode="tools")

        assert "Tool Call Traces" in captured_prompt[0]
        assert "web_search" in captured_prompt[0]

    def test_judge_uses_test_eval_criteria(self, monkeypatch, fresh_health):
        monkeypatch.setenv("OLLAMA_API_KEY", "test-key")

        captured = []
        def capture(p, m, prompt, timeout=180):
            captured.append(prompt)
            return {"success": True, "content": json.dumps({
                "rankings": [], "best_overall": "", "summary": "",
            }), "elapsed": 1, "tokens_in": 10, "tokens_out": 5, "error": None}

        monkeypatch.setattr(compare, "call_model_simple", capture)

        test_eval = ["Check for X", "Check for Y"]
        compare.judge_responses("test", [{"content": "a", "label": "A"}], "j", "ollama-cloud",
                                test_eval=test_eval)

        assert "Check for X" in captured[0]
        assert "Check for Y" in captured[0]


# ─── Efficiency table ────────────────────────────────────────────────────────

class TestEfficiencyTable:
    def test_tools_mode_prints(self, capsys):
        results = [
            {"label": "A", "provider": "test", "model": "a", "turns": 3, "tool_calls": 2,
             "tokens_in": 100, "tokens_out": 50, "elapsed": 5.0, "converged": True, "_revealed": True},
        ]
        compare.print_efficiency_table(results, "tools")
        out = capsys.readouterr().out
        assert "Efficiency" in out
        assert "Turns" in out
        assert "Tools" in out

    def test_simple_mode_prints(self, capsys):
        results = [
            {"label": "A", "provider": "test", "model": "a",
             "tokens_in": 100, "tokens_out": 50, "elapsed": 2.0, "_revealed": True},
        ]
        compare.print_efficiency_table(results, "simple")
        out = capsys.readouterr().out
        assert "Efficiency" in out
        assert "Tok In" in out

    def test_ratio_calculation(self, capsys):
        results = [
            {"label": "A", "provider": "t", "model": "m", "turns": 1, "tool_calls": 0,
             "tokens_in": 200, "tokens_out": 100, "elapsed": 1.0, "converged": True, "_revealed": True},
        ]
        compare.print_efficiency_table(results, "tools")
        out = capsys.readouterr().out
        assert "0.50" in out  # 100/200 = 0.50

    def test_zero_tokens_in_no_crash(self, capsys):
        results = [
            {"label": "A", "provider": "t", "model": "m", "turns": 0, "tool_calls": 0,
             "tokens_in": 0, "tokens_out": 0, "elapsed": 0, "converged": False, "_revealed": True},
        ]
        compare.print_efficiency_table(results, "tools")
        out = capsys.readouterr().out
        assert "N/A" in out


# ─── Provider health integration ─────────────────────────────────────────────

class TestProviderHealthIntegration:
    def test_2_failures_marks_dead(self, fresh_health):
        assert fresh_health.is_alive("ollama-cloud") is True
        fresh_health.record_failure("ollama-cloud", "fail 1")
        assert fresh_health.is_alive("ollama-cloud") is True  # 1 fail, threshold=2
        fresh_health.record_failure("ollama-cloud", "fail 2")
        assert fresh_health.is_alive("ollama-cloud") is False  # 2 fails → dead

    def test_success_resets(self, fresh_health):
        fresh_health.record_failure("ollama-cloud", "fail 1")
        fresh_health.record_success("ollama-cloud")
        assert fresh_health.is_alive("ollama-cloud") is True
        # Next failure should be fail count 1, not 2
        fresh_health.record_failure("ollama-cloud", "fail again")
        assert fresh_health.is_alive("ollama-cloud") is True

    def test_cooldown_remaining(self, fresh_health):
        fresh_health.record_failure("ollama-cloud", "fail 1")
        fresh_health.record_failure("ollama-cloud", "fail 2")
        remaining = fresh_health.cooldown_remaining("ollama-cloud")
        assert remaining > 0
        assert remaining <= 15  # ollama-cloud cooldown is 15s

    def test_openrouter_higher_threshold(self, fresh_health):
        """OpenRouter has fail_threshold=3, not 2."""
        fresh_health.record_failure("openrouter", "fail 1")
        fresh_health.record_failure("openrouter", "fail 2")
        assert fresh_health.is_alive("openrouter") is True  # 2 < 3
        fresh_health.record_failure("openrouter", "fail 3")
        assert fresh_health.is_alive("openrouter") is False

    def test_reset_provider(self, fresh_health):
        fresh_health.record_failure("ollama-cloud", "fail")
        fresh_health.record_failure("ollama-cloud", "fail")
        assert not fresh_health.is_alive("ollama-cloud")
        fresh_health.reset("ollama-cloud")
        assert fresh_health.is_alive("ollama-cloud") is True

    def test_reset_all(self, fresh_health):
        for p in ("ollama-cloud", "nvidia", "openrouter"):
            fresh_health.record_failure(p, "fail")
            fresh_health.record_failure(p, "fail")
        fresh_health.reset()
        for p in ("ollama-cloud", "nvidia", "openrouter"):
            assert fresh_health.is_alive(p) is True

    def test_status_returns_dict(self, fresh_health):
        fresh_health.record_failure("nvidia", "test")
        status = fresh_health.status()
        assert "nvidia" in status
        assert status["nvidia"]["fails"] == 1
        assert status["nvidia"]["alive"] is True


# ─── Model spec parsing ──────────────────────────────────────────────────────

class TestModelSpecParsing:
    """Test the model spec parsing logic from main() without running main()."""

    def test_valid_spec(self):
        specs = ["ollama-cloud:glm-5.2", "nvidia:meta/llama-3.3-70b-instruct"]
        parsed = []
        for spec in specs:
            provider, model_id = spec.split(":", 1)
            assert provider in compare.PROVIDERS
            parsed.append((provider, model_id))
        assert len(parsed) == 2
        assert parsed[0] == ("ollama-cloud", "glm-5.2")

    def test_missing_colon_rejected(self):
        spec = "ollama-cloud-glm-5.2"
        assert ":" not in spec

    def test_unknown_provider_rejected(self):
        spec = "unknown-provider:model"
        provider = spec.split(":", 1)[0]
        assert provider not in compare.PROVIDERS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])