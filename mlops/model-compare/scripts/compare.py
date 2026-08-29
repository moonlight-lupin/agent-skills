#!/usr/bin/env python3
"""
Blind multi-model comparison — send one prompt to 2-4 models via OpenRouter,
NVIDIA, or Ollama Cloud, and return responses with anonymous labels.

Modes:
  simple   — one prompt → one response (default)
  tools    — multi-turn tool calling with real web_search/web_extract
             + sandboxed run_python/read_file/write_file
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
import re
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
        # Reasoning models (GLM 5.3, 2026-08-29): reasoning tokens count
        # against max_tokens; 8192 got fully consumed by reasoning on coding
        # H3 / review H5, yielding tok_out=8192 + empty content.
        "max_tokens": 32768,
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
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "auth_header": "Authorization",
        "auth_scheme": "Bearer",
        "paid": True,
        # Reasoning model: counts reasoning tokens against max_tokens, so 8192
        # gets consumed by long reasoning chains before any content is emitted.
        # (Observed 2026-08-03: H3/H4/H5 returned tok_out=8192, content empty.)
        "max_tokens": 32768,
        # Default reasoning effort enters a RUN-AWAY LOOP on hard prompts
        # (e.g. H3 thread-safe cache: 32768 reasoning tokens, 0 content, 316s).
        # reasoning_effort=low converges: 1425 reasoning tok, 5155ch content, 22s.
        "payload_extra": {"reasoning_effort": "low"},
    },
}

# ─── Per-model reasoning_effort overrides (@effort suffix) ──────────────────
#
# Model specs (and --judge) accept an optional ":@effort" suffix:
#   ollama-cloud:@medium:glm-5.3-flash
#   ollama-cloud:@high:glm-5.3
# This lets you A/B the SAME model at two reasoning levels in one run. It is
# implemented by registering a virtual provider derived from the base
# provider, with payload_extra={"reasoning_effort": effort}. The virtual
# provider inherits max_tokens (including reasoning-model-sized overrides
# like Ollama Cloud's 32768) and reuses the same env key, so nothing is
# duplicated. Verified against Ollama Cloud /v1/chat/completions on
# 2026-08-29: top-level "reasoning_effort" is accepted and changes behavior.
def register_effort_provider(base_provider: str, effort: str) -> str:
    """Return a virtual provider name for (base_provider, effort), registering it on first use.

    Raises ValueError for unknown base providers.
    """
    if base_provider not in PROVIDERS:
        raise ValueError(f"unknown provider '{base_provider}'")
    name = f"{base_provider}@{effort}"
    if name in PROVIDERS:
        return name
    base = dict(PROVIDERS[base_provider])
    extra = dict(base.get("payload_extra") or {})
    extra["reasoning_effort"] = effort
    base["payload_extra"] = extra
    base["paid"] = base.get("paid", False)
    PROVIDERS[name] = base
    return name


def parse_model_spec(spec: str) -> tuple[str, str, str | None]:
    """Parse 'provider:model_id' or 'provider:@effort:model_id'.

    Returns (provider, model_id, effort_or_None). Raises ValueError on
    malformed specs. Effort syntax uses the literal ':@' marker so multi-colon
    model IDs (e.g. qwen3-coder:480b) stay unambiguous.
    """
    if not isinstance(spec, str) or ":" not in spec:
        raise ValueError(f"model spec '{spec}' must be 'provider:model_id' or 'provider:@effort:model_id'")
    # Find an effort marker: provider:@effort:<rest>
    m = re.match(r"^([^:@\s]+):@([A-Za-z0-9_\-]+):(.+)$", spec)
    if m:
        return m.group(1), m.group(3), m.group(2)
    provider, model_id = spec.split(":", 1)
    if "@" in spec or provider == "" or model_id == "":
        raise ValueError(f"model spec '{spec}' must be 'provider:model_id' or 'provider:@effort:model_id'")
    return provider, model_id, None


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
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute Python code in a sandbox. The code runs as a subprocess with a 10-second timeout. Working directory is the sandbox folder. Returns stdout, stderr, and exit code. Output is truncated to 2000 chars.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python code to execute"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file from the sandbox directory. Returns the file content as text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File name (relative to sandbox, no absolute paths)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file in the sandbox directory. Creates or overwrites the file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File name (relative to sandbox, no absolute paths)"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
]

MAX_TOOL_TURNS = 10

# ─── Sandbox management ─────────────────────────────────────────────────────

import subprocess
import tempfile
import shutil

SANDBOX_TIMEOUT = 10  # seconds for Python execution
SANDBOX_OUTPUT_LIMIT = 2000  # chars of stdout/stderr to return


def create_sandbox(prefix: str = "compare_sandbox_") -> str:
    """Create a per-model temp directory for sandboxed file operations."""
    return tempfile.mkdtemp(prefix=prefix)


def cleanup_sandbox(sandbox_dir: str):
    """Remove a sandbox directory."""
    if sandbox_dir and os.path.isdir(sandbox_dir):
        shutil.rmtree(sandbox_dir, ignore_errors=True)


def _safe_path(sandbox_dir: str, filename: str) -> str | None:
    """Resolve a filename against the sandbox dir, rejecting path traversal."""
    if not sandbox_dir:
        return None
    # Strip leading slashes and ./ prefixes
    filename = filename.lstrip("/").lstrip("./")
    # Reject absolute paths and ..
    if os.path.isabs(filename) or ".." in filename.split("/"):
        return None
    resolved = os.path.normpath(os.path.join(sandbox_dir, filename))
    # Ensure the resolved path is inside the sandbox
    if not resolved.startswith(os.path.abspath(sandbox_dir)):
        return None
    return resolved


def execute_run_python(code: str, sandbox_dir: str) -> str:
    """Execute Python code in a sandboxed subprocess."""
    if not sandbox_dir:
        return json.dumps({"error": "No sandbox directory available"})
    # Write code to a temp file in the sandbox, then execute
    script_path = os.path.join(sandbox_dir, "_run.py")
    try:
        with open(script_path, "w") as f:
            f.write(code)
    except Exception as e:
        return json.dumps({"error": f"Failed to write script: {e}"})
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            capture_output=True, text=True,
            timeout=SANDBOX_TIMEOUT,
            cwd=sandbox_dir,
        )
        stdout = result.stdout[:SANDBOX_OUTPUT_LIMIT]
        stderr = result.stderr[:SANDBOX_OUTPUT_LIMIT]
        return json.dumps({
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.returncode,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Execution timed out after {SANDBOX_TIMEOUT}s", "exit_code": -1})
    except Exception as e:
        return json.dumps({"error": str(e), "exit_code": -1})


def execute_read_file(path: str, sandbox_dir: str) -> str:
    """Read a file from the sandbox directory."""
    safe = _safe_path(sandbox_dir, path)
    if not safe:
        return json.dumps({"error": f"Invalid path: {path}"})
    if not os.path.isfile(safe):
        return json.dumps({"error": f"File not found: {path}"})
    try:
        with open(safe, "r") as f:
            content = f.read()
        return json.dumps({"content": content[:SANDBOX_OUTPUT_LIMIT], "path": path})
    except Exception as e:
        return json.dumps({"error": str(e)})


def execute_write_file(path: str, content: str, sandbox_dir: str) -> str:
    """Write a file to the sandbox directory."""
    safe = _safe_path(sandbox_dir, path)
    if not safe:
        return json.dumps({"error": f"Invalid path: {path}"})
    try:
        os.makedirs(os.path.dirname(safe), exist_ok=True) if os.path.dirname(safe) != sandbox_dir else None
        with open(safe, "w") as f:
            f.write(content)
        return json.dumps({"success": True, "path": path, "bytes": len(content)})
    except Exception as e:
        return json.dumps({"error": str(e)})

# ─── Test bank ───────────────────────────────────────────────────────────────

TEST_BANK = {
    # ── Tool calling tests ──
    "A": {
        "domain": "tool_calling",
        "prompt": "What's the latest version of Python and what are the top 2 new features in it?",
        "tools": True,
        "max_turns": 10,
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
        "max_turns": 10,
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
        "max_turns": 10,
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
        "max_turns": 10,
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
    # ── Hard mode tests (2026-08-03) ──
    "H1": {
        "domain": "tool_calling",
        "prompt": "There is conflicting information about whether Python 3.14's free-threaded (no-GIL) build is production-ready. Find at least 3 sources that discuss this, identify which source is most authoritative, and state the current official status per the Python documentation (e.g. experimental vs officially supported, and in which version). Be explicit about which source you trust and why.",
        "tools": True,
        "max_turns": 12,
        "evaluation": [
            "Searched multiple queries to find 3+ distinct sources",
            "Identified python.org / CPython docs as authoritative over blogs",
            "Correctly determined official status of free-threading (experimental vs supported, which version)",
            "Did not hallucinate PEP numbers or status",
            "Synthesized conflicting info into a clear verdict with source attribution",
        ],
    },
    "H2": {
        "domain": "tool_calling",
        "prompt": "Find the current stable version of Node.js, its End-of-Life (EOL) date, and recommend which major version a new production application should pin in August 2026. Verify each claim against an official source (nodejs.org or the official Node.js release schedule).",
        "tools": True,
        "max_turns": 12,
        "evaluation": [
            "Found the current Node.js version from an official source",
            "Stated the EOL date accurately from the official release schedule",
            "Recommended the correct major version to pin (current LTS)",
            "Did not hallucinate version numbers or dates",
            "Cross-verified at least two official pages (nodejs.org, release schedule)",
        ],
    },
    "H3": {
        "domain": "coding",
        "prompt": "Implement a thread-safe cache in Python with TTL expiration and LRU eviction. Requirements: (1) get(key) returns value or None; (2) put(key, value, ttl_seconds) stores with expiration; (3) evicts least recently used when over capacity; (4) safe for concurrent use by multiple threads (no lost updates, no races); (5) O(1) amortized for get/put. Include type hints, a docstring, and a short usage example with threads.",
        "tools": False,
        "evaluation": [
            "Uses a lock (threading.Lock/RLock) around shared state",
            "TTL checked on get — expired entries return None and are removed",
            "LRU eviction when over capacity",
            "No data races — all mutations under lock",
            "Correct under concurrency (no lost updates)",
            "Type hints + docstring + usage example with threads",
        ],
    },
    "H4": {
        "domain": "coding",
        "prompt": "Implement a token bucket rate limiter in Python. Requirements: (1) allow(requests) returns True if enough tokens are available; (2) the bucket refills continuously at rate tokens_per_second (based on elapsed time, not a tick loop); (3) supports a burst capacity larger than the steady-state rate; (4) thread-safe; (5) an injectable clock (time source) for testability. Include type hints, a docstring, and a short usage example.",
        "tools": False,
        "evaluation": [
            "Implements token bucket (not fixed-window or sliding-log)",
            "Continuous refill via elapsed-time arithmetic, no tick loop",
            "Burst capacity correctly modeled (never exceeds capacity)",
            "Thread-safe — lock around token updates",
            "Injectable clock (callable or time parameter)",
            "Type hints + docstring + usage example",
        ],
    },
    "H5": {
        "domain": "code_review",
        "prompt": "Review this asyncio Python code for a production service. List each issue with severity, explanation, and fix:\n\nimport asyncio\n\nclass ConnectionPool:\n    def __init__(self, max_size=3):\n        self._idle = []\n        self._inflight = 0\n        self._max_size = max_size\n        self._lock = asyncio.Lock()\n\n    async def acquire(self):\n        async with self._lock:\n            if self._idle:\n                return self._idle.pop()\n            if self._inflight >= self._max_size:\n                raise RuntimeError(\"pool exhausted\")\n            self._inflight += 1\n        # Connection created outside the lock, but _inflight already incremented\n        conn = await self._create_connection()\n        return conn\n\n    async def release(self, conn):\n        # No lock around mutation, and _inflight is never decremented\n        self._idle.append(conn)\n\n    async def _create_connection(self):\n        await asyncio.sleep(0.1)\n        return object()",
        "tools": False,
        "planted_issues": [
            {"type": "logic", "severity": "High", "description": "_inflight never decremented on release or on _create failure — pool permanently exhausts after max_size failures"},
            {"type": "concurrency", "severity": "High", "description": "release() mutates _idle without the lock; at await boundaries this races with acquire()'s pop, corrupting pool accounting"},
            {"type": "robustness", "severity": "Medium", "description": "No timeout on acquire — callers can hang forever waiting for a connection"},
            {"type": "resource", "severity": "Medium", "description": "If _create_connection raises, the acquired slot is leaked (inflight never decremented) and the exception propagates without cleanup"},
        ],
        "evaluation": [
            "Finds the inflight-counter leak (never decremented on failure or release)",
            "Identifies release() not taking the lock as a concurrency bug",
            "Notes the missing acquire timeout",
            "Explains why the double-counting leads to permanent pool exhaustion",
            "Does not hallucinate issues (e.g. doesn't claim create-under-lock is a deadlock when it's a perf issue)",
        ],
    },
    "H6": {
        "domain": "code_review",
        "prompt": "Review this authentication service code for a production web app. List each issue with severity, explanation, and fix:\n\nimport hashlib, time\n\nUSERS = {\n    \"alice\": \"5f4dcc3b5aa765d61d8327deb882cf99\",  # md5(\"password\")\n}\n\ndef check_password(username, password):\n    stored_hash = USERS.get(username)\n    if not stored_hash:\n        return False\n    # Compares hashes directly\n    return hashlib.md5(password.encode()).hexdigest() == stored_hash\n\ndef issue_session(username, role=\"user\"):\n    # Session token derived only from username and role\n    token = hashlib.md5(f\"{username}:{role}\".encode()).hexdigest()\n    return {\"token\": token, \"username\": username, \"role\": role,\n            \"issued_at\": time.time(), \"expires_at\": time.time() + 3600}\n\ndef authorize(session, required_roles):\n    if session is None:\n        return False\n    # Expiry is never checked\n    return session[\"role\"] in required_roles",
        "tools": False,
        "planted_issues": [
            {"type": "security", "severity": "Critical", "description": "Passwords hashed with MD5 (fast, brute-forceable) and stored with no salt"},
            {"type": "security", "severity": "High", "description": "Timing-unsafe comparison — == on hash strings leaks via timing side channel"},
            {"type": "security", "severity": "High", "description": "Session token is deterministic (md5 of username:role) — forgeable, no server secret"},
            {"type": "security", "severity": "High", "description": "authorize() never checks expires_at — expired sessions remain valid forever"},
            {"type": "logic", "severity": "Medium", "description": "Empty required_roles list passes any session (or: role check bypass when list is empty)"},
        ],
        "evaluation": [
            "Catches MD5 for password storage (Critical)",
            "Identifies the timing-unsafe comparison",
            "Flags the forgeable/deterministic session token",
            "Finds the missing expiry check in authorize()",
            "Notes the empty-roles authorization bypass",
            "Suggests proper fixes (bcrypt/argon2, hmac.compare_digest, secrets.token_hex, expiry check)",
        ],
    },
    "H7": {
        "domain": "code_review",
        "prompt": "Review this function for a production logging service. List each issue with severity, explanation, and fix:\n\ndef get_last_logs(conn):\n    cursor = conn.cursor()\n    cursor.execute(\"SELECT message FROM logs ORDER BY id DESC LIMIT 10\")\n    rows = []\n    while cursor.fetchone():\n        rows.append(cursor.fetchone())\n    return rows",
        "tools": False,
        "planted_issues": [
            {"type": "logic", "severity": "High", "description": "fetchone() called twice per iteration — every other row skipped; also returns only the non-None rows, silently dropping messages"},
            {"type": "resource", "severity": "Low", "description": "Cursor never closed"},
        ],
        "evaluation": [
            "Traces the loop: fetchone() in the condition AND the body skips every other row",
            "Explains the consequence (half the logs missing, silently)",
            "Suggests fetchall() or a single fetchone() assignment as the fix",
            "Does not hallucinate issues that aren't present",
        ],
    },
    # ── Sandbox tests (code execution + file ops) ──
    "S1": {
        "domain": "tool_calling",
        "prompt": "Write a Python function that checks if a string is a valid IPv4 address (four octets 0-255, no leading zeros except for 0 itself). Write the code to a file, run it with test cases, and report which tests pass or fail. You have tools: write_file, run_python, read_file.",
        "tools": True,
        "max_turns": 10,
        "evaluation": [
            "Used write_file to save the Python code to a file",
            "Used run_python to execute the code with test cases",
            "Test cases cover: valid IPs (192.168.1.1, 0.0.0.0, 255.255.255.255), invalid IPs (256.1.1.1, 01.1.1.1, 1.2.3, 1.2.3.4.5)",
            "Correctly identifies which tests pass and which fail",
            "If initial code has bugs, iterates: reads output, fixes code, re-runs",
            "Final answer includes the working code and test results",
        ],
    },
    "S2": {
        "domain": "tool_calling",
        "prompt": "You have a CSV file with this content:\n\nname,age,score\nAlice,30,85\nBob,25,92\nCharlie,35,78\nAlice,30,90\nBob,25,88\n\nWrite this CSV to a file, then write a Python script that reads it and calculates: (1) the average score per person, (2) the person with the highest average, (3) the total number of entries. Run the script and report the results. You have tools: write_file, run_python, read_file.",
        "tools": True,
        "max_turns": 10,
        "evaluation": [
            "Used write_file to save the CSV data",
            "Used write_file to save the Python script (or used run_python directly)",
            "Used run_python to execute the analysis script",
            "Correctly calculates average score per person (Alice: 87.5, Bob: 90.0, Charlie: 78.0)",
            "Correctly identifies Bob as the highest average",
            "Correctly reports 5 total entries",
            "If errors occur, iterates and fixes",
        ],
    },
    "S3": {
        "domain": "tool_calling",
        "prompt": "Write a Python script that generates the first 20 Fibonacci numbers, saves them to a file as JSON, then reads the file back and verifies the sequence is correct. Execute the script and report the results. You have tools: write_file, run_python, read_file.",
        "tools": True,
        "max_turns": 10,
        "evaluation": [
            "Used write_file or run_python to create and execute the script",
            "Script generates correct Fibonacci sequence (0,1,1,2,3,5,8,13,21,34,55,89,144,233,377,610,987,1597,2584,4181)",
            "Script saves output as JSON to a file",
            "Script reads the file back and verifies correctness",
            "Reports the results accurately",
            "If errors occur, iterates and fixes",
        ],
    },
    "S4": {
        "domain": "tool_calling",
        "prompt": "Write a Python function that reverses a linked list. Create a test that builds a list 1->2->3->4->5, reverses it, and prints the result. Write the code to a file, run it, and verify the output is 5->4->3->2->1. If the output is wrong, debug and fix it. You have tools: write_file, run_python, read_file.",
        "tools": True,
        "max_turns": 10,
        "evaluation": [
            "Defines a ListNode or Node class for the linked list",
            "Implements reverse_linked_list with correct pointer manipulation",
            "Used run_python to execute and verify output",
            "Output correctly shows 5->4->3->2->1 after reversal",
            "If initial code has bugs, iterates: reads stderr/stdout, fixes, re-runs",
            "Final answer includes the working code and confirmation of correct output",
        ],
    },
    "S5": {
        "domain": "tool_calling",
        "prompt": "Write a Python script that implements a simple Caesar cipher (shift by 3). The script should: (1) define an encrypt function, (2) define a decrypt function, (3) encrypt 'Hello World', (4) decrypt the result, (5) verify the decrypted text matches the original. Write the code to a file, run it, and report the results. You have tools: write_file, run_python, read_file.",
        "tools": True,
        "max_turns": 10,
        "evaluation": [
            "Implements encrypt and decrypt functions with shift of 3",
            "Handles uppercase and lowercase letters correctly",
            "Handles non-alphabetic characters (spaces, punctuation) by leaving them unchanged",
            "Used run_python to execute the script",
            "Encryption produces 'Khoor Zruog' for 'Hello World'",
            "Decryption correctly recovers the original text",
            "Script verifies encrypt(decrypt(text)) == text",
            "If errors occur, iterates and fixes",
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
        "max_tokens": cfg.get("max_tokens", 8192),
    }
    payload.update(cfg.get("payload_extra", {}))
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
        "max_tokens": cfg.get("max_tokens", 8192),
    }
    payload.update(cfg.get("payload_extra", {}))
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
        url = f"{searxng_url}/search?q={urllib.parse.quote(query)}&format=json&limit={limit}&engines=bing,yandex,duckduckgo,google"
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

    # Fallback: DDGS via CLI (new syntax: ddgs text -q ... -m ... -o <file>)
    try:
        import subprocess, tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tmp_path = tf.name
        result = subprocess.run(
            ["ddgs", "text", "-q", query, "-m", str(limit), "-o", tmp_path],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            with open(tmp_path) as f:
                items = json.load(f)
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


def execute_tool(tool_name: str, arguments: dict, sandbox_dir: str = None) -> str:
    """Execute a tool call and return the result as a string."""
    if tool_name == "web_search":
        return execute_web_search(arguments.get("query", ""), arguments.get("limit", 5))
    elif tool_name == "web_extract":
        return execute_web_extract(arguments.get("urls", []))
    elif tool_name == "run_python":
        return execute_run_python(arguments.get("code", ""), sandbox_dir)
    elif tool_name == "read_file":
        return execute_read_file(arguments.get("path", ""), sandbox_dir)
    elif tool_name == "write_file":
        return execute_write_file(arguments.get("path", ""), arguments.get("content", ""), sandbox_dir)
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

    # Create a per-model sandbox for file ops + code execution
    sandbox_dir = create_sandbox()

    try:
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

                    tool_result = execute_tool(name, args, sandbox_dir)
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
    finally:
        cleanup_sandbox(sandbox_dir)

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
                        help='Models in "provider:model_id" or "provider:@effort:model_id" format (e.g. ollama-cloud:@medium:glm-5.3-flash)')
    parser.add_argument("--test", "-t", help="Use a test from the test bank (e.g. A, J, O)")
    parser.add_argument("--reveal", action="store_true", help="Reveal model identities immediately")
    parser.add_argument("--judge", help="Judge model in provider:model format")
    parser.add_argument("--efficiency", action="store_true", help="Show token efficiency table")
    parser.add_argument("--list-providers", action="store_true", help="List available providers")
    parser.add_argument("--list-models", help="List models for a provider")
    parser.add_argument("--list-tests", action="store_true", help="List available test bank prompts")
    parser.add_argument("--timeout", type=int, default=120, help="Per-model timeout in seconds (simple mode)")
    parser.add_argument("--max-turns", type=int, default=None, help="Override test bank max_turns at runtime (tools mode only)")
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
        # Use test-specific max_turns if defined, otherwise fall back to constant
        effective_max_turns = test.get("max_turns", MAX_TOOL_TURNS)
        # CLI --max-turns override takes precedence over test bank default
        if args.max_turns is not None:
            effective_max_turns = args.max_turns
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

    # Parse model specs (supports provider:@effort:model_id for reasoning-effort A/B)
    model_specs = []
    for spec in args.models:
        try:
            provider, model_id, effort = parse_model_spec(spec)
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
        if effort is not None:
            try:
                provider = register_effort_provider(provider, effort)
            except ValueError as e:
                print(f"Error: {e}")
                sys.exit(1)
            print(f"[arm] {spec} -> virtual provider '{provider}' (reasoning_effort={effort})", file=sys.stderr)
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
        max_turns = effective_max_turns if 'effective_max_turns' in dir() else MAX_TOOL_TURNS
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = {}
            for i, (provider, model_id) in enumerate(model_specs):
                future = executor.submit(run_tool_loop, provider, model_id, prompt, max_turns, 60)
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
        try:
            j_provider, j_model, j_effort = parse_model_spec(args.judge)
        except ValueError as e:
            print(f"Error: --judge {e}")
            sys.exit(1)
        if j_effort is not None:
            try:
                j_provider = register_effort_provider(j_provider, j_effort)
            except ValueError as e:
                print(f"Error: --judge {e}")
                sys.exit(1)
        print(f"\n{'='*60}")
        judge_display = f"{j_provider}:{j_model}" + (f" (reasoning_effort={j_effort})" if j_effort else "")
        print(f"⚖️  Judge: {judge_display}")
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