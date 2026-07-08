#!/usr/bin/env python3
"""
Blind multi-model comparison — send one prompt to 2-4 models via OpenRouter,
NVIDIA, or Ollama Cloud, and return responses with anonymous labels.

Modes:
  simple   — one prompt → one response (default)
  tools    — multi-turn tool calling with real web_search/web_extract
  coding   — coding test bank prompts (one-shot)
  review   — code review test bank prompts with planted bugs (one-shot)

Usage:
  python3 compare.py --prompt "What is 2+2?" --models "ollama-cloud:glm-5.2" "nvidia:meta/llama-3.3-70b-instruct"
  python3 compare.py --mode tools --prompt "What's the latest Python version?" --models "ollama-cloud:glm-5.2" "ollama-cloud:kimi-k2.5"
  python3 compare.py --mode tools --test A --models "ollama-cloud:glm-5.2" "ollama-cloud:kimi-k2.5"
  python3 compare.py --mode coding --test J --models "ollama-cloud:glm-5.2" "ollama-cloud:qwen3-coder:480b"
  python3 compare.py --mode review --test O --models "ollama-cloud:glm-5.2" "ollama-cloud:kimi-k2.5" --judge "ollama-cloud:glm-5.2"
  python3 compare.py --list-providers
  python3 compare.py --list-tests
  python3 compare.py --list-models ollama-cloud

No external dependencies beyond stdlib + urllib (no pip installs needed).
"""

import argparse
import concurrent.futures
import json
import os
import random
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ─── Provider config ─────────────────────────────────────────────────────────

PROVIDERS = {
    "ollama-cloud": {
        "base_url": "https://ollama.com/v1/chat/completions",
        "key_env": "OLLAMA_API_KEY",
        "auth_header": "Authorization",
        "auth_scheme": "Bearer",
        "paid": False,
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "key_env": "NVIDIA_API_KEY",
        "auth_header": "Authorization",
        "auth_scheme": "Bearer",
        "paid": False,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "auth_header": "Authorization",
        "auth_scheme": "Bearer",
        "paid": True,
    },
}

# ─── Tool definitions for tool-calling mode ─────────────────────────────────

TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for information. Returns titles, URLs, and snippets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results to return (default 5)", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_extract",
            "description": "Fetch full page content from one or more URLs. Returns markdown text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to fetch"},
                },
                "required": ["urls"],
            },
        },
    },
]

MAX_TOOL_TURNS = 5

# ─── Test bank ───────────────────────────────────────────────────────────────

TEST_BANK = {
    # ── Tool calling tests ──
    "A": {
        "domain": "tool_calling",
        "prompt": "What's the latest version of Python and what are the top 2 new features in it?",
        "tools": True,
        "max_turns": 5,
        "evaluation": [
            "Called web_search with a good query (e.g. 'latest Python version 2026')",
            "Picked an authoritative URL from search results (python.org > random blog)",
            "Extracted relevant content using web_extract",
            "Final answer states the correct version and real features",
            "Did not hallucinate version numbers or features",
        ],
    },
    "B": {
        "domain": "tool_calling",
        "prompt": "Find the GitHub repository for PewDiePie's Odysseus project and tell me how many stars it has.",
        "tools": True,
        "max_turns": 5,
        "evaluation": [
            "Searched for 'PewDiePie Odysseus GitHub' or similar",
            "Picked the correct GitHub URL from results",
            "Extracted the repo page and found the star count",
            "Reported the correct star count (approximately 78k as of June 2026)",
            "Did not hallucinate the star count",
        ],
    },
    "C": {
        "domain": "tool_calling",
        "prompt": "Search for the best reverse proxy for a homelab in 2026, then pick the top recommendation and find out what its key feature is.",
        "tools": True,
        "max_turns": 5,
        "evaluation": [
            "Searched for reverse proxy recommendations",
            "Extracted content from a relevant article or comparison",
            "Identified a specific reverse proxy (e.g. Caddy, Traefik, Nginx Proxy Manager)",
            "Named a key feature of the chosen proxy",
            "Did not just list search results — synthesized an answer",
        ],
    },
    "E": {
        "domain": "tool_calling",
        "prompt": "Search for Python LRU cache implementations, look at the top result, then write one that's better than what you found.",
        "tools": True,
        "max_turns": 5,
        "evaluation": [
            "Searched for LRU cache implementations",
            "Extracted and read at least one result",
            "Wrote a working LRU cache based on what was found",
            "Improved on the found implementation (better edge cases, cleaner code, etc.)",
            "Code is syntactically correct and would run",
        ],
    },
    # ── Coding tests ──
    "J": {
        "domain": "coding",
        "prompt": "Implement an LRU cache in Python with get(key) and put(key, value) methods. Both operations must be O(1). Include type hints and a docstring.",
        "tools": False,
        "evaluation": [
            "Uses OrderedDict or doubly-linked list + dict for O(1)",
            "get() returns value or None, updates recency",
            "put() evicts least recently used when at capacity",
            "Handles edge cases: empty cache, capacity 1, re-put existing key",
            "Includes type hints and docstring as requested",
        ],
    },
    "K": {
        "domain": "coding",
        "prompt": "Write a Python function that takes a list of URLs and fetches them concurrently with a timeout of 5 seconds per URL. Return results in the same order as input. Include error handling for individual URL failures.",
        "tools": False,
        "evaluation": [
            "Uses asyncio + aiohttp or concurrent.futures (not sequential requests)",
            "Timeout of 5 seconds per URL (not global)",
            "Results in same order as input (uses enumerate or index tracking)",
            "Handles individual URL failures gracefully (doesn't crash on one error)",
            "Includes type hints",
        ],
    },
    "L": {
        "domain": "coding",
        "prompt": "Fix the bug in this merge sort implementation:\n\ndef merge_sort(arr):\n    if len(arr) <= 1:\n        return arr\n    mid = len(arr) // 2\n    left = merge_sort(arr[:mid])\n    right = merge_sort(arr[mid:])\n    return merge(left, right)\n\ndef merge(left, right):\n    result = []\n    i = j = 0\n    while i < len(left) and j < len(right):\n        if left[i] <= right[j]:\n            result.append(left[i])\n            i += 1\n        else:\n            result.append(right[j])\n            j += 1\n    result.extend(left[i:])\n    result.extend(right[j+1:])\n    return result\n\nExplain what the bug was and provide the fixed code.",
        "tools": False,
        "evaluation": [
            "Identifies the off-by-one bug: right[j+1:] should be right[j:]",
            "Explains why it's wrong (skips the last element of right when loop exits)",
            "Fixed code is correct merge sort",
            "Doesn't rewrite unnecessarily — minimal fix",
            "Explanation is clear and concise",
        ],
    },
    "M": {
        "domain": "coding",
        "prompt": "Write a Python decorator that retries a function up to 3 times on exception, with 1 second delay between retries. Include type hints, a docstring, and preserve the wrapped function's metadata.",
        "tools": False,
        "evaluation": [
            "Correct retry logic: try/except in a loop, max 3 attempts",
            "1 second delay between retries (time.sleep(1))",
            "Uses functools.wraps to preserve metadata",
            "Type hints on the decorator and wrapper",
            "Re-raises the exception after all retries exhausted",
        ],
    },
    # ── Code review tests ──
    "O": {
        "domain": "code_review",
        "prompt": "Review this Python function for bugs, security issues, and improvements. List each issue with severity (Critical/High/Medium/Low), explanation, and suggested fix:\n\ndef get_user_by_name(conn, username):\n    cursor = conn.cursor()\n    query = f\"SELECT * FROM users WHERE name = '{username}'\"\n    cursor.execute(query)\n    results = []\n    for i in range(cursor.rowcount):\n        results.append(cursor.fetchone())\n    return results",
        "tools": False,
        "planted_issues": [
            {"type": "security", "severity": "Critical", "description": "SQL injection via f-string interpolation"},
            {"type": "logic", "severity": "Medium", "description": "fetchone() in a rowcount loop is unreliable — should use fetchall()"},
        ],
        "evaluation": [
            "Finds the SQL injection vulnerability (Critical)",
            "Identifies the fetchone/rowcount pattern as unreliable",
            "Prioritizes security over logic issues",
            "Suggests parameterized queries as the fix for SQL injection",
            "Does not hallucinate issues that aren't there",
        ],
    },
    "P": {
        "domain": "code_review",
        "prompt": "Review this Python code for bugs, security issues, and improvements. List each issue with severity:\n\ndef calculate_total(items):\n    total = 0\n    for item in items:\n        total += item['price'] * item['quantity']\n    return total\n\ndef format_receipt(items):\n    total = calculate_total(items)\n    lines = []\n    for item in items:\n        lines.append(f\"{item['name']}: ${item['price'] * item['quantity']:.2f}\")\n    lines.append(f\"Total: ${total:.2f}\")\n    return '\\n'.join(lines)",
        "tools": False,
        "planted_issues": [],
        "evaluation": [
            "Correctly identifies this as clean, working code",
            "Does not hallucinate bugs that don't exist",
            "May suggest minor style improvements (type hints, edge case for empty list) but doesn't flag them as bugs",
            "Low false-positive rate",
        ],
    },
    "Q": {
        "domain": "code_review",
        "prompt": "Review this code for a production service. List each issue with severity:\n\nclass Cache:\n    def __init__(self):\n        self._data = {}\n    \n    def get(self, key):\n        return self._data.get(key)\n    \n    def set(self, key, value):\n        self._data[key] = value\n\nclass UserService:\n    def __init__(self):\n        self.cache = Cache()\n    \n    def get_user(self, user_id):\n        cached = self.cache.get(user_id)\n        if cached:\n            return cached\n        user = self._fetch_from_db(user_id)\n        self.cache.set(user_id, user)\n        return user\n    \n    def _fetch_from_db(self, user_id):\n        return {'id': user_id, 'name': 'User ' + str(user_id)}",
        "tools": False,
        "planted_issues": [
            {"type": "concurrency", "severity": "High", "description": "Cache is not thread-safe — concurrent get/set can cause race conditions in production"},
        ],
        "evaluation": [
            "Identifies the thread-safety / race condition issue",
            "Explains why it's a problem in production (concurrent requests)",
            "Suggests a fix (threading.Lock, or concurrent.futures, or a thread-safe cache)",
            "Doesn't hallucinate issues — the cache is simple but functional for single-threaded use",
        ],
    },
    "R": {
        "domain": "code_review",
        "prompt": "Review this code for a banking service. List each issue with severity:\n\ndef transfer_balance(from_account, to_account, amount):\n    from_account['balance'] -= amount\n    to_account['balance'] += amount\n    return from_account, to_account\n\ndef calculate_interest(principal, rate, years):\n    return principal * (1 + rate) ** years\n\ndef format_currency(amount):\n    return f\"${amount:.2f}\"",
        "tools": False,
        "planted_issues": [
            {"type": "domain", "severity": "High", "description": "Floating-point for monetary calculations — will cause rounding errors"},
            {"type": "logic", "severity": "Medium", "description": "transfer_balance has no validation — negative amounts, insufficient funds, same account"},
        ],
        "evaluation": [
            "Catches the float-for-money issue (should use Decimal)",
            "Identifies missing validation in transfer_balance (negative amounts, insufficient funds)",
            "Prioritizes the money handling issue appropriately for a banking context",
            "Suggests decimal.Decimal as the fix",
            "Doesn't miss the domain-specific issue (float precision)",
        ],
    },
}


# ─── Env loading ─────────────────────────────────────────────────────────────

def load_env():
    """Load env vars from ~/.hermes/.env if not already in environment."""
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_api_key(provider: str) -> str:
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}")
    key = os.environ.get(cfg["key_env"], "")
    if not key:
        raise ValueError(f"No API key found for {provider} (env: {cfg['key_env']})")
    return key


# ─── API call helpers ────────────────────────────────────────────────────────

def _build_headers(provider: str, api_key: str) -> dict:
    cfg = PROVIDERS[provider]
    headers = {
        "Content-Type": "application/json",
        f"{cfg['auth_header']}": f"{cfg['auth_scheme']} {api_key}",
    }
    if provider == "openrouter":
        headers["X-Title"] = "Hermes Model Compare"
        headers["HTTP-Referer"] = "https://github.com/moonlight-lupin/agent_skills"
    return headers


def call_model_simple(provider: str, model: str, prompt: str, timeout: int = 120) -> dict:
    """Send a simple chat completion (no tools) and return the response."""
    # Provider health check — skip if in cooldown
    if provider_health and not provider_health.is_alive(provider):
        cooldown = provider_health.cooldown_remaining(provider)
        return {
            "success": False,
            "content": f"[Provider {provider} in cooldown ({cooldown:.0f}s remaining) — skipping]",
            "elapsed": 0, "tokens_in": 0, "tokens_out": 0,
            "error": f"cooldown ({cooldown:.0f}s)",
        }

    cfg = PROVIDERS[provider]
    api_key = get_api_key(provider)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(cfg["base_url"], data=data, headers=_build_headers(provider, api_key), method="POST")
    try:
        start = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - start
        content = ""
        if "choices" in body and body["choices"]:
            msg = body["choices"][0].get("message", {})
            content = msg.get("content", "")
        elif "error" in body:
            content = f"[API Error: {body['error']}]"
        usage = body.get("usage", {})
        if provider_health:
            provider_health.record_success(provider)
        return {
            "success": True,
            "content": content,
            "elapsed": round(elapsed, 1),
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "error": None,
        }
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        if provider_health:
            provider_health.record_failure(provider, f"HTTP {e.code}: {err_body[:100]}")
        return {"success": False, "content": f"[HTTP {e.code}: {err_body}]", "elapsed": 0,
                "tokens_in": 0, "tokens_out": 0, "error": f"HTTP {e.code}"}
    except Exception as e:
        if provider_health:
            provider_health.record_failure(provider, str(e)[:200])
        return {"success": False, "content": f"[Error: {str(e)}]", "elapsed": 0,
                "tokens_in": 0, "tokens_out": 0, "error": str(e)}


def call_model_with_tools(provider: str, model: str, messages: list, timeout: int = 60) -> dict:
    """Send a chat completion with tool definitions. Returns message + tool_calls."""
    # Provider health check — skip if in cooldown
    if provider_health and not provider_health.is_alive(provider):
        cooldown = provider_health.cooldown_remaining(provider)
        return {"success": False, "error": f"cooldown ({cooldown:.0f}s)", "content": "",
                "tool_calls": None, "elapsed": 0, "tokens_in": 0, "tokens_out": 0, "finish_reason": "error"}

    cfg = PROVIDERS[provider]
    api_key = get_api_key(provider)
    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOL_DEFS,
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(cfg["base_url"], data=data, headers=_build_headers(provider, api_key), method="POST")
    try:
        start = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        elapsed = time.time() - start
        if "error" in body:
            if provider_health:
                provider_health.record_failure(provider, str(body["error"])[:200])
            return {"success": False, "error": str(body["error"]), "content": "", "tool_calls": None,
                    "elapsed": 0, "tokens_in": 0, "tokens_out": 0, "finish_reason": "error"}
        msg = body["choices"][0].get("message", {})
        usage = body.get("usage", {})
        if provider_health:
            provider_health.record_success(provider)
        return {
            "success": True,
            "content": msg.get("content", "") or "",
            "tool_calls": msg.get("tool_calls"),
            "elapsed": round(elapsed, 1),
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "finish_reason": body["choices"][0].get("finish_reason", "stop"),
            "error": None,
        }
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        if provider_health:
            provider_health.record_failure(provider, f"HTTP {e.code}: {err_body[:100]}")
        return {"success": False, "error": f"HTTP {e.code}: {err_body}", "content": "",
                "tool_calls": None, "elapsed": 0, "tokens_in": 0, "tokens_out": 0, "finish_reason": "error"}
    except Exception as e:
        if provider_health:
            provider_health.record_failure(provider, str(e)[:200])
        return {"success": False, "error": str(e), "content": "", "tool_calls": None,
                "elapsed": 0, "tokens_in": 0, "tokens_out": 0, "finish_reason": "error"}


# ─── Real tool execution ────────────────────────────────────────────────────

def execute_web_search(query: str, limit: int = 5) -> str:
    """Execute a real web search via SearXNG (if configured) with DDGS fallback."""
    # Try SearXNG first, only if a self-hosted instance is configured via env.
    searxng_url = os.environ.get("SEARXNG_URL", "").rstrip("/")
    try:
        if not searxng_url:
            raise RuntimeError("SEARXNG_URL not set; using DDGS fallback")
        url = f"{searxng_url}/search?q={urllib.parse.quote(query)}&format=json&limit={limit}"
        req = urllib.request.Request(url, headers={"User-Agent": "Hermes-Model-Compare/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results", [])[:limit]
        if not results:
            return json.dumps({"results": [], "note": "No results found"})
        formatted = []
        for i, r in enumerate(results):
            formatted.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:300],
            })
        return json.dumps({"results": formatted})
    except Exception:
        pass

    # Fallback: DDGS via CLI
    try:
        import subprocess
        result = subprocess.run(
            ["ddgs", "--json", "-q", query, "-m", str(limit)],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout:
            items = json.loads(result.stdout)
            formatted = []
            for item in items[:limit]:
                formatted.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", item.get("url", "")),
                    "snippet": item.get("body", item.get("snippet", ""))[:300],
                })
            return json.dumps({"results": formatted})
    except Exception:
        pass

    return json.dumps({"results": [], "error": "Search failed — both SearXNG and DDGS unavailable"})


def execute_web_extract(urls: list) -> str:
    """Fetch real page content from URLs. Returns truncated markdown text."""
    results = []
    for url in urls[:3]:  # Max 3 URLs per call
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            # crude HTML to text — strip tags
            import re
            text = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            # Truncate to 3000 chars per page
            results.append({"url": url, "content": text[:3000]})
        except Exception as e:
            results.append({"url": url, "error": str(e)[:100]})
    return json.dumps({"results": results})


def execute_tool(tool_name: str, arguments: dict) -> str:
    """Execute a tool call and return the result as a string."""
    if tool_name == "web_search":
        return execute_web_search(arguments.get("query", ""), arguments.get("limit", 5))
    elif tool_name == "web_extract":
        return execute_web_extract(arguments.get("urls", []))
    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})


# ─── Multi-turn tool calling loop ────────────────────────────────────────────

def run_tool_loop(provider: str, model: str, prompt: str, max_turns: int = 5, timeout: int = 60) -> dict:
    """
    Run a multi-turn tool calling loop:
    1. Send prompt + tool defs
    2. If model returns tool_calls, execute them and feed results back
    3. Repeat until final answer or max_turns
    Returns full trace + stats.
    """
    messages = [{"role": "user", "content": prompt}]
    trace = []
    total_tokens_in = 0
    total_tokens_out = 0
    total_tool_calls = 0
    total_elapsed = 0
    turn = 0
    converged = False
    final_content = ""

    for turn in range(1, max_turns + 1):
        result = call_model_with_tools(provider, model, messages, timeout=timeout)
        total_elapsed += result["elapsed"]
        total_tokens_in += result["tokens_in"]
        total_tokens_out += result["tokens_out"]

        if not result["success"]:
            trace.append({
                "turn": turn,
                "type": "error",
                "error": result["error"],
                "tokens_in": result["tokens_in"],
                "tokens_out": result["tokens_out"],
                "elapsed": result["elapsed"],
            })
            final_content = f"[Error on turn {turn}: {result['error']}]"
            break

        tool_calls = result.get("tool_calls")
        content = result.get("content", "")

        if tool_calls:
            # Record the assistant message with tool calls
            tc_summary = []
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "?")
                args_str = fn.get("arguments", "{}")
                try:
                    args = json.loads(args_str)
                except Exception:
                    args = {"raw": args_str}
                tc_summary.append({"tool": name, "args": args})
                total_tool_calls += 1

            trace.append({
                "turn": turn,
                "type": "tool_call",
                "tool_calls": tc_summary,
                "content": content[:200] if content else "",
                "tokens_in": result["tokens_in"],
                "tokens_out": result["tokens_out"],
                "elapsed": result["elapsed"],
            })

            # Add assistant message to conversation
            messages.append(result.get("raw_message") or {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            })

            # Execute each tool call and feed results back
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "?")
                args_str = fn.get("arguments", "{}")
                tool_call_id = tc.get("id", f"call_{turn}")
                try:
                    args = json.loads(args_str)
                except Exception:
                    args = {}

                tool_result = execute_tool(name, args)
                truncated_result = tool_result[:2000]  # Keep context manageable

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": truncated_result,
                })

                trace.append({
                    "turn": turn,
                    "type": "tool_result",
                    "tool": name,
                    "result_preview": truncated_result[:300],
                    "result_length": len(tool_result),
                })

        else:
            # No tool calls — this is the final answer
            final_content = content
            converged = True
            trace.append({
                "turn": turn,
                "type": "final",
                "content": content[:200],
                "tokens_in": result["tokens_in"],
                "tokens_out": result["tokens_out"],
                "elapsed": result["elapsed"],
            })
            break

    if not converged and turn == max_turns:
        final_content = final_content or "[Did not converge — hit max turns]"
        trace.append({"turn": max_turns, "type": "max_turns_reached"})

    return {
        "success": True,
        "content": final_content,
        "trace": trace,
        "turns": turn,
        "tool_calls": total_tool_calls,
        "tokens_in": total_tokens_in,
        "tokens_out": total_tokens_out,
        "elapsed": round(total_elapsed, 1),
        "converged": converged,
    }


# ─── Judge ───────────────────────────────────────────────────────────────────

def judge_responses(prompt: str, responses: list, judge_model: str, judge_provider: str,
                    mode: str = "simple", test_eval: list = None) -> dict:
    """Ask a judge model to rank the blind responses."""

    # Build evaluation criteria
    if test_eval:
        criteria_text = "\n".join(f"- {c}" for c in test_eval)
    elif mode == "tools":
        criteria_text = """- Tool selection strategy: did it search smart? pick authoritative sources?
- Answer accuracy: is the final answer correct and non-hallucinated?
- Token efficiency: fewer tokens for same quality = better
- Convergence: did it reach an answer, or get stuck?"""
    else:
        criteria_text = """1. Accuracy — is the information correct?
2. Completeness — does it fully address the prompt?
3. Clarity — is it well-structured and easy to understand?
4. Helpfulness — does it provide actionable, useful information?"""

    rubric = f"""You are an impartial judge evaluating AI model responses. Rank them by quality.

Original prompt:
{prompt}

Evaluation criteria:
{criteria_text}
"""

    for i, r in enumerate(responses):
        label = chr(65 + i)
        rubric += f"\n--- Response {label} ---\n{r['content']}\n"

    # For tool calling mode, include the trace
    if mode == "tools":
        rubric += "\n--- Tool Call Traces ---\n"
        for i, r in enumerate(responses):
            label = chr(65 + i)
            rubric += f"\n[Model {label} trace]\n"
            if "trace" in r:
                for step in r["trace"]:
                    if step["type"] == "tool_call":
                        for tc in step.get("tool_calls", []):
                            rubric += f"  Turn {step['turn']}: Called {tc['tool']}({json.dumps(tc['args'])[:100]})\n"
                    elif step["type"] == "tool_result":
                        rubric += f"  Turn {step['turn']}: Result from {step['tool']} ({step['result_length']} chars)\n"
                    elif step["type"] == "final":
                        rubric += f"  Turn {step['turn']}: Final answer given\n"
                    elif step["type"] == "error":
                        rubric += f"  Turn {step['turn']}: ERROR: {step['error']}\n"
                    elif step["type"] == "max_turns_reached":
                        rubric += f"  Turn {step['turn']}: MAX TURNS reached without final answer\n"
                rubric += f"  Stats: {r.get('turns',0)} turns, {r.get('tool_calls',0)} tool calls, {r.get('tokens_in',0)} tokens in, {r.get('tokens_out',0)} tokens out\n"

    rubric += f"""

Evaluate each response on the criteria above.

Output your evaluation as JSON:
{{
  "rankings": [
    {{"label": "A", "rank": 1, "score": 8.5, "strengths": "...", "weaknesses": "..."}},
    {{"label": "B", "rank": 2, "score": 7.0, "strengths": "...", "weaknesses": "..."}}
  ],
  "best_overall": "A",
  "summary": "One paragraph comparing the responses"
}}

Score each on a 0-10 scale. Rank 1 = best."""

    result = call_model_simple(judge_provider, judge_model, rubric, timeout=180)
    if result["success"]:
        content = result["content"]
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start != -1 and json_end > json_start:
            try:
                parsed = json.loads(content[json_start:json_end])
                result["parsed_judgment"] = parsed
            except json.JSONDecodeError:
                result["parsed_judgment"] = None
                result["raw_judgment"] = content
        else:
            result["parsed_judgment"] = None
            result["raw_judgment"] = content
    return result


# ─── Efficiency stats table ──────────────────────────────────────────────────

def print_efficiency_table(results: list, mode: str):
    """Print a token efficiency comparison table."""
    print(f"\n{'='*70}")
    print("📊 Efficiency Comparison")
    print(f"{'='*70}")

    if mode == "tools":
        print(f"{'':20s} {'Turns':>6s} {'Tools':>6s} {'Tok In':>8s} {'Tok Out':>8s} {'Ratio':>6s} {'Time':>6s}")
        print(f"{'-'*70}")
        for r in results:
            label = r["label"]
            identity = f"{r['provider']}:{r['model']}" if r.get("_revealed") else f"Model {label}"
            ratio = f"{r['tokens_out']/r['tokens_in']:.2f}" if r.get("tokens_in", 0) > 0 else "N/A"
            converged = "✅" if r.get("converged") else "❌"
            print(f"{converged} {identity:18s} {r.get('turns',0):>6d} {r.get('tool_calls',0):>6d} "
                  f"{r.get('tokens_in',0):>8d} {r.get('tokens_out',0):>8d} {ratio:>6s} {r.get('elapsed',0):>5.1f}s")
    else:
        print(f"{'':20s} {'Tok In':>8s} {'Tok Out':>8s} {'Total':>8s} {'Time':>6s}")
        print(f"{'-'*70}")
        for r in results:
            label = r["label"]
            identity = f"{r['provider']}:{r['model']}" if r.get("_revealed") else f"Model {label}"
            total = r.get("tokens_in", 0) + r.get("tokens_out", 0)
            print(f"  {identity:18s} {r.get('tokens_in',0):>8d} {r.get('tokens_out',0):>8d} {total:>8d} {r.get('elapsed',0):>5.1f}s")

    print(f"{'='*70}")


# ─── Output formatting ──────────────────────────────────────────────────────

def print_tool_trace(result: dict, label: str, reveal: bool):
    """Print the tool call trace for a model."""
    identity = f"{result['provider']}:{result['model']}" if reveal else "???"
    status = "✅" if result.get("converged") else "❌"
    print(f"\n{'='*60}")
    print(f"{status} Model {label} ({identity})")
    print(f"   Turns: {result.get('turns',0)} | Tool calls: {result.get('tool_calls',0)} | "
          f"Tokens: {result.get('tokens_in',0)}→{result.get('tokens_out',0)} | {result.get('elapsed',0)}s")
    print(f"{'='*60}")

    if "trace" in result:
        for step in result["trace"]:
            if step["type"] == "tool_call":
                for tc in step.get("tool_calls", []):
                    args_str = json.dumps(tc["args"])
                    if len(args_str) > 80:
                        args_str = args_str[:77] + "..."
                    print(f"\n  🔧 Turn {step['turn']}: {tc['tool']}({args_str})")
            elif step["type"] == "tool_result":
                preview = step.get("result_preview", "")[:150]
                print(f"  📄 Result ({step['result_length']} chars): {preview}...")
            elif step["type"] == "final":
                print(f"\n  💬 Final answer (turn {step['turn']}):")
                print(f"  {result['content']}")
            elif step["type"] == "error":
                print(f"\n  ❌ Turn {step['turn']}: {step['error']}")
            elif step["type"] == "max_turns_reached":
                print(f"\n  ⛔ Max turns ({step['turn']}) reached without final answer")

    if not result.get("converged"):
        print(f"\n  ⚠️ Did not converge — no final answer produced")


def print_simple_result(result: dict, label: str, reveal: bool):
    """Print a simple (non-tool) response."""
    identity = f"{result['provider']}:{result['model']}" if reveal else "???"
    status = "✅" if result["success"] else "❌"
    print(f"\n{'='*60}")
    print(f"{status} Model {label} ({identity})")
    print(f"   Time: {result['elapsed']}s | Tokens: {result['tokens_in']}→{result['tokens_out']}")
    print(f"{'='*60}")
    print(result["content"])


# ─── Main ────────────────────────────────────────────────────────────────────

import urllib.parse  # Needed for URL quoting in search

# ─── Provider health (dead-host cooldown) ────────────────────────────────────
# Import from sibling module — falls back to no-op if unavailable
try:
    from provider_health import health as provider_health
except ImportError:
    import os as _os, sys as _sys
    _script_dir = _os.path.dirname(_os.path.abspath(__file__))
    if _script_dir not in _sys.path:
        _sys.path.insert(0, _script_dir)
    try:
        from provider_health import health as provider_health
    except ImportError:
        # Graceful degradation — no health tracking
        provider_health = None


def main():
    parser = argparse.ArgumentParser(description="Blind multi-model comparison")
    parser.add_argument("--mode", choices=["simple", "tools", "coding", "review"], default="simple",
                        help="Comparison mode (default: simple)")
    parser.add_argument("--prompt", "-p", help="Prompt text (inline)")
    parser.add_argument("--prompt-file", "-f", help="Read prompt from file")
    parser.add_argument("--models", "-m", nargs="+",
                        help='Models in "provider:model_id" format')
    parser.add_argument("--test", "-t", help="Use a test from the test bank (e.g. A, J, O)")
    parser.add_argument("--reveal", action="store_true", help="Reveal model identities immediately")
    parser.add_argument("--judge", help="Judge model in provider:model format")
    parser.add_argument("--efficiency", action="store_true", help="Show token efficiency table")
    parser.add_argument("--list-providers", action="store_true", help="List available providers")
    parser.add_argument("--list-models", help="List models for a provider")
    parser.add_argument("--list-tests", action="store_true", help="List available test bank prompts")
    parser.add_argument("--timeout", type=int, default=120, help="Per-model timeout in seconds (simple mode)")
    parser.add_argument("--output", "-o", help="Save results to JSON file")

    args = parser.parse_args()
    load_env()

    # ─── List providers ──────────────────────────────────────────────────────
    if args.list_providers:
        print("Available providers:")
        for name, cfg in PROVIDERS.items():
            key_present = "✅" if os.environ.get(cfg["key_env"]) else "❌"
            cost = "FREE" if not cfg.get("paid") else "PAID"
            print(f"  {name:15s} {key_present}  {cost:4s}  (env: {cfg['key_env']})")
        return

    # ─── List models ─────────────────────────────────────────────────────────
    if args.list_models:
        provider = args.list_models
        if provider not in PROVIDERS:
            print(f"Unknown provider: {provider}")
            sys.exit(1)
        cfg = PROVIDERS[provider]
        api_key = os.environ.get(cfg["key_env"], "")
        if not api_key:
            print(f"No API key for {provider}")
            sys.exit(1)
        base = cfg["base_url"].replace("/chat/completions", "/models")
        req = urllib.request.Request(base, headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = data.get("data", [])
            print(f"\n{provider}: {len(models)} models\n")
            for m in sorted(models, key=lambda x: x.get("id", "")):
                print(f"  {m['id']}")
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)
        return

    # ─── List tests ──────────────────────────────────────────────────────────
    if args.list_tests:
        print("Available test bank prompts:\n")
        current_domain = None
        for test_id in sorted(TEST_BANK.keys()):
            test = TEST_BANK[test_id]
            if test["domain"] != current_domain:
                current_domain = test["domain"]
                print(f"\n  [{current_domain}]")
            tools_tag = " 🔧" if test.get("tools") else ""
            print(f"    {test_id}: {test['prompt'][:80]}...{tools_tag}")
        return

    # ─── Resolve test bank prompt ────────────────────────────────────────────
    test_eval = None
    if args.test:
        if args.test not in TEST_BANK:
            print(f"Error: test '{args.test}' not found. Use --list-tests to see available tests.")
            sys.exit(1)
        test = TEST_BANK[args.test]
        args.prompt = test["prompt"]
        test_eval = test.get("evaluation")
        # Override mode based on test domain
        if test.get("tools"):
            args.mode = "tools"
        elif test["domain"] == "coding":
            args.mode = "coding"
        elif test["domain"] == "code_review":
            args.mode = "review"

    # ─── Validate inputs ─────────────────────────────────────────────────────
    if not args.prompt and not args.prompt_file:
        print("Error: --prompt, --prompt-file, or --test required")
        sys.exit(1)
    if not args.models:
        print("Error: --models required")
        sys.exit(1)

    # Get prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text().strip()
    else:
        prompt = args.prompt

    # Parse model specs
    model_specs = []
    for spec in args.models:
        if ":" not in spec:
            print(f"Error: model spec '{spec}' must be 'provider:model_id'")
            sys.exit(1)
        provider, model_id = spec.split(":", 1)
        if provider not in PROVIDERS:
            print(f"Error: unknown provider '{provider}'. Available: {', '.join(PROVIDERS.keys())}")
            sys.exit(1)
        model_specs.append((provider, model_id))

    if len(model_specs) < 2:
        print("Error: need at least 2 models to compare")
        sys.exit(1)
    if len(model_specs) > 4:
        print("Error: max 4 models per comparison")
        sys.exit(1)

    # Cost check
    paid_models = [(p, m) for p, m in model_specs if PROVIDERS[p].get("paid", False)]
    if paid_models and not os.environ.get("COMPARE_CONFIRM_PAID"):
        print("\n⚠️  Cost warning:", file=sys.stderr)
        for p, m in paid_models:
            print(f"   {p}:{m} — PAID (per-token cost)", file=sys.stderr)
        print(f"\n   This comparison will use {len(paid_models)} paid model(s).", file=sys.stderr)
        print(f"   Estimated cost: ~$0.01–0.10 per model per call.", file=sys.stderr)
        print(f"\n   To proceed: COMPARE_CONFIRM_PAID=1 ...", file=sys.stderr)
        print(f"   Or use free providers: ollama-cloud, nvidia", file=sys.stderr)
        sys.exit(1)

    # Blind mode: shuffle
    if not args.reveal:
        random.shuffle(model_specs)

    mode_label = {"simple": "Simple", "tools": "Tool Calling", "coding": "Coding", "review": "Code Review"}[args.mode]
    print(f"\n🧪 {mode_label} Comparison — {len(model_specs)} models", file=sys.stderr)
    print(f"   Prompt: \"{prompt[:80]}...\"\n", file=sys.stderr)

    # ─── Run comparisons ─────────────────────────────────────────────────────
    results = []

    if args.mode == "tools":
        # Multi-turn tool calling — run each model's loop concurrently
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for i, (provider, model_id) in enumerate(model_specs):
                future = executor.submit(run_tool_loop, provider, model_id, prompt, MAX_TOOL_TURNS, 60)
                futures[future] = (i, provider, model_id)
            for future in concurrent.futures.as_completed(futures):
                idx, provider, model_id = futures[future]
                result = future.result()
                result["provider"] = provider
                result["model"] = model_id
                result["label"] = chr(65 + idx)
                results.append(result)
    else:
        # Simple / coding / review — one-shot
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for i, (provider, model_id) in enumerate(model_specs):
                future = executor.submit(call_model_simple, provider, model_id, prompt, args.timeout)
                futures[future] = (i, provider, model_id)
            for future in concurrent.futures.as_completed(futures):
                idx, provider, model_id = futures[future]
                result = future.result()
                result["provider"] = provider
                result["model"] = model_id
                result["label"] = chr(65 + idx)
                results.append(result)

    results.sort(key=lambda r: r["label"])

    # Mark revealed for efficiency table
    if args.reveal:
        for r in results:
            r["_revealed"] = True

    # ─── Print results ───────────────────────────────────────────────────────
    for r in results:
        if args.mode == "tools":
            print_tool_trace(r, r["label"], args.reveal)
        else:
            print_simple_result(r, r["label"], args.reveal)

    # ─── Efficiency table ────────────────────────────────────────────────────
    if args.efficiency or args.mode == "tools":
        print_efficiency_table(results, args.mode)

    # ─── Judge ───────────────────────────────────────────────────────────────
    if args.judge:
        if ":" not in args.judge:
            print("Error: --judge must be 'provider:model_id'")
            sys.exit(1)
        j_provider, j_model = args.judge.split(":", 1)
        print(f"\n{'='*60}")
        print(f"⚖️  Judge: {j_provider}:{j_model}")
        print(f"{'='*60}", file=sys.stderr)

        judgment = judge_responses(prompt, results, j_model, j_provider, args.mode, test_eval)
        if judgment["success"]:
            if judgment.get("parsed_judgment"):
                j = judgment["parsed_judgment"]
                print(f"\nBest: Model {j.get('best_overall', '?')}\n")
                for ranking in sorted(j.get("rankings", []), key=lambda x: x.get("rank", 99)):
                    print(f"  #{ranking['rank']} Model {ranking['label']} — Score: {ranking['score']}/10")
                    print(f"    Strengths: {ranking.get('strengths', 'N/A')}")
                    print(f"    Weaknesses: {ranking.get('weaknesses', 'N/A')}")
                print(f"\nSummary: {j.get('summary', 'N/A')}")
            else:
                print(judgment.get("raw_judgment", judgment["content"]))
        else:
            print(f"Judge failed: {judgment['error']}")

    # ─── Reveal ──────────────────────────────────────────────────────────────
    if not args.reveal:
        print(f"\n{'='*60}")
        print("🔓 Reveal:")
        for r in results:
            print(f"  Model {r['label']} = {r['provider']}:{r['model']}")
        print(f"{'='*60}")

    # ─── Save output ─────────────────────────────────────────────────────────
    if args.output:
        output_data = {
            "prompt": prompt,
            "mode": args.mode,
            "test_id": args.test,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "models": [{"label": r["label"], "provider": r["provider"], "model": r["model"]} for r in results],
            "results": [],
        }
        for r in results:
            entry = {
                "label": r["label"], "provider": r["provider"], "model": r["model"],
                "content": r.get("content", ""), "elapsed": r.get("elapsed", 0),
                "tokens_in": r.get("tokens_in", 0), "tokens_out": r.get("tokens_out", 0),
                "success": r.get("success", False),
            }
            if args.mode == "tools":
                entry["turns"] = r.get("turns", 0)
                entry["tool_calls"] = r.get("tool_calls", 0)
                entry["converged"] = r.get("converged", False)
                entry["trace"] = r.get("trace", [])
            output_data["results"].append(entry)
        Path(args.output).write_text(json.dumps(output_data, indent=2))
        print(f"\n💾 Saved to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    import urllib.parse  # Needed for URL quoting in search
    main()