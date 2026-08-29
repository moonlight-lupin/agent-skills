---
name: model-compare
description: "Use when the user says \"compare models\", \"test these models\", \"which model is better for\", \"A/B test\", \"blind comparison\", or wants to see how different AI models handle the same prompt. Blind side-by-side multi-model comparison with anonymous presentation, vote, reveal, and optional synthesis."
version: 1.2.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [model, comparison, evaluation, a/b-testing, blind, synthesis, openrouter]
    related_skills: [deep-research]
---

# Model Compare — Blind Side-by-Side Multi-Model Testing

Send one prompt to multiple models simultaneously, present responses
anonymously, let the user pick a winner, then reveal which model is which.

Inspired by the Compare feature in PewDiePie's Odysseus project, adapted for
Hermes's multi-provider architecture (OpenRouter, NVIDIA, Ollama Cloud, any
OpenAI-compatible endpoint).

## When to use

- "Compare these models on..."
- "Which model is better for [task]?"
- "A/B test [model1] vs [model2]"
- "Blind comparison of..."
- "Test how different models handle this prompt"
- User wants to evaluate models before committing to one for a workflow
- Prompt engineering — seeing how different models interpret instructions

## When NOT to use

- **Benchmarking** (MMLU, GSM8K, etc.) → use `evaluating-llms-harness` skill
- **Cost analysis** → just check provider pricing pages
- **Single model test** → just switch model and ask directly
- **Multi-source research synthesis** → use `deep-research` skill (iterative research loop, not model comparison)

## Architecture

Four comparison modes, all driven by `scripts/compare.py`:

| Mode | Flag | What it does | API feature |
|---|---|---|---|
| **simple** | `--mode simple` (default) | One prompt → one response | Basic chat completion |
| **tools** | `--mode tools` | Multi-turn tool calling with real web_search/web_extract + sandboxed run_python/read_file/write_file. 10-turn max (configurable per-test via `max_turns` in TEST_BANK). Tracks full trace. | `tools` array in request, multi-turn messages |
| **coding** | `--mode coding` | Test bank coding prompts (LRU cache, concurrent fetch, debug merge sort, retry decorator) | Basic chat completion |
| **review** | `--mode review` | Code review prompts with planted bugs (SQL injection, clean code, race condition, float-for-money) | Basic chat completion |

```
User prompt + model list
  → Step 1: Resolve models to provider endpoints (free providers first)
  → Step 2: Send prompt to all models in parallel
     ├─ simple/coding/review: one-shot chat completion
     └─ tools: multi-turn loop (Think→Search→Extract→Execute→Synthesize→Stop, max 10 turns by default, per-test configurable)
  → Step 3: Quality check responses (handle errors/empty)
  → Step 4: Present anonymously (shuffle + label A/B/C/D)
  → Step 5: Efficiency table (tokens in/out, turns, tool calls — auto for tools mode)
  → Step 6: User votes OR judge model evaluates
  → Step 7: Reveal identities + show mapping
  → Step 8 (optional): Save to JSON file
```

### Script: `scripts/compare.py`

The primary interface — a standalone CLI tool (no pip dependencies, pure stdlib + urllib). See `references/provider-tool-support.md` for which models support tool calling. For empirical model behavior findings from 16 head-to-head tests (GLM 5.2, MiniMax M3, HY3, Laguna), see `references/model-behavior.md`. (Running the test suite under `tests/` needs `pytest` — see `requirements-dev.txt`; the skill itself needs nothing installed.)

> **Tool-mode environment dependency:** `--mode tools` runs real `web_search`. That needs **either** `SEARXNG_URL` set to a SearXNG instance **or** the [`ddgs`](https://pypi.org/project/ddgs/) CLI available on `PATH` (the fallback). Neither is a Python import dependency, but one of them must be present for live search; without both, `web_search` returns an error result. The other three modes (`simple`, `coding`, `review`) need neither.

```bash
# Simple 2-model blind comparison
python3 scripts/compare.py --prompt "Explain X" --models "ollama-cloud:glm-5.2" "ollama-cloud:kimi-k2.5"

# Reasoning-effort A/B: SAME model, two effort levels (native syntax)
# Registers a virtual provider per arm; judge can also take an effort suffix.
python3 scripts/compare.py --mode review --test H7 \
  --models "ollama-cloud:@medium:glm-5.3-flash" "ollama-cloud:@high:glm-5.3-flash" \
  --judge "ollama-cloud:@medium:glm-5.3" --reveal

# Tool calling with test bank prompt A + judge + reveal
python3 scripts/compare.py --mode tools --test A --models "ollama-cloud:glm-5.2" "ollama-cloud:kimi-k2.5" --judge "ollama-cloud:glm-5.2" --reveal

# Coding test J with efficiency table
python3 scripts/compare.py --mode coding --test J --models "ollama-cloud:glm-5.2" "ollama-cloud:qwen3-coder:480b" --efficiency

# Code review test O with judge
python3 scripts/compare.py --mode review --test O --models "ollama-cloud:glm-5.2" "ollama-cloud:kimi-k2.5" --judge "ollama-cloud:glm-5.2"

# List available tests
python3 scripts/compare.py --list-tests

# List providers
python3 scripts/compare.py --list-providers
```

Key flags: `--prompt`, `--models`, `--mode`, `--test` (test bank ID), `--judge`, `--efficiency`, `--reveal`, `--output`, `--timeout`, `--list-providers`, `--list-models`.

### Reasoning-effort A/B (`:@effort` suffix, added 2026-08-29)

Model specs and `--judge` accept an optional effort marker `provider:@effort:model_id`, e.g.
`ollama-cloud:@medium:glm-5.3-flash`. Each unique (provider, effort) pair registers a
virtual provider (`ollama-cloud@medium`) that clones the base provider's config — same
endpoint, same env key, inherited `max_tokens` — and injects `reasoning_effort` into the
payload. This enables comparing the SAME model at two reasoning levels in one blind run;
the reveal labels the arms `provider@effort`. Findings from the 2026-08-29
glm-5.3-flash A/B (Codex-judged, 8 tests): effort→thinking-token count is non-monotonic;
high was ~3x faster median but non-converged on a 12-turn tool-chain test that medium
completed; medium won on judged quality overall (8.6 vs 7.8 avg). See
`~/.hermes/data/glm53flash_effort_ab/ab_results.jsonl` for full traces.

> **`--max-turns` CLI override (added 2026-07-17):** Pass `--max-turns N` to override the test bank's `max_turns` field at runtime without editing source. If not passed, the test bank default is used. This was added because killing a background run to patch `TEST_BANK["A"]["max_turns"]` in source code is fragile and disrupts parallel execution.

## Available Providers

Three providers are wired in (the canonical config is `PROVIDERS` in
`scripts/compare.py`):

| Provider | Env Var | Cost | Model families | Endpoint |
|---|---|---|---|---|
| **Ollama Cloud** | `OLLAMA_API_KEY` | **Free** | GLM, Qwen, Kimi, Gemini, Gemma | `https://ollama.com/v1/chat/completions` |
| **NVIDIA** | `NVIDIA_API_KEY` | **Free** | Yi, Llama, Nemotron, … | `https://integrate.api.nvidia.com/v1/chat/completions` |
| **OpenRouter** | `OPENROUTER_API_KEY` | **Paid** (per-token) | Claude, GPT, Gemini, DeepSeek, Llama, Qwen, Mistral | `https://openrouter.ai/api/v1/chat/completions` |

> **Model inventories live elsewhere, on purpose.** Exact model counts and IDs
> drift constantly, so they are deliberately kept out of this doc. For the live
> list run `python3 scripts/compare.py --list-models <provider>` (needs that
> provider's key); `references/providers.json` holds a curated, count-free
> snapshot with representative model IDs per provider.

### Cost-aware provider routing (mandatory)

When the user does **not** specify a provider, route to **free providers first**:

1. **Ollama Cloud** — free (GLM, Qwen, Kimi, Gemini, Gemma)
2. **NVIDIA** — free (Yi, Llama, Nemotron)
3. **OpenRouter** — paid (per-token cost). **Only use when:**
   - The user explicitly requests an OpenRouter-only model (e.g. Claude, GPT-4o)
   - The user explicitly says to use OpenRouter
   - The free providers don't have a suitable model for the task

**Before any OpenRouter call**, confirm with the user:
> "This comparison will use OpenRouter which has per-token costs. Estimated cost: ~$0.01–0.05 per model per call (varies by model). Proceed?"

Only proceed after explicit confirmation. When in doubt, default to free providers.

To call a model, POST to the provider's `/v1/chat/completions` endpoint with:
```json
{
  "model": "<model_id>",
  "messages": [{"role": "user", "content": "<prompt>"}],
  "max_tokens": 8192,
  "temperature": 0.7
}
```
Header: `Authorization: Bearer <API_KEY>`

> **max_tokens** is set to 8192 in both `call_model_simple` and
> `call_model_with_tools`. The previous default of 4096 caused truncated
> code output on coding test J (LRU cache) — the model generated so much
> code it hit the 4096 limit before finishing the decorator section.
> If a model still truncates, increase the value in the payload dict.

## Step 1 — Resolve Models

Determine which models to compare. The user may specify:
- **Explicit model names**: "compare claude-sonnet-4.6 vs gpt-4o vs gemini-2.5-flash"
- **Provider + model**: "compare OpenRouter claude-sonnet-4.6 vs Ollama glm-5.2"
- **Task-based**: "which model is best for coding?" → suggest 2-4 candidates
- **All from a provider**: "test 3 OpenRouter models" → pick diverse ones

### Model resolution

Map the user's model names to a `provider:model_id` spec. **Free providers
(Ollama Cloud, NVIDIA) are preferred.** OpenRouter is only used for models not
on a free provider (e.g. Claude, GPT) or when the user explicitly asks for it.

The rules, not a hardcoded catalogue (which would rot):

- **Free, leave the prefix off or name an Ollama/NVIDIA model** → resolve on a
  free provider, e.g. `ollama-cloud:glm-5.2`, `ollama-cloud:qwen3-coder:480b`,
  `nvidia:meta/llama-3.3-70b-instruct`.
- **A proprietary model (Claude, GPT, Gemini-Pro, DeepSeek-R1, …)** → only
  OpenRouter carries it, e.g. `openrouter:anthropic/claude-sonnet-4.6`,
  `openrouter:openai/gpt-4o` — **paid, confirm first** (see routing rule above).
- **Unsure of the exact ID?** Run `python3 scripts/compare.py --list-models
  <provider>` for the live list, or see `references/providers.json` for a
  curated set of representative IDs per provider. Don't hand-maintain a model
  table here.

**When user doesn't specify models:**
1. Check if the task type maps to free models (e.g. coding → qwen3-coder, glm-5.2; general → glm-5.2, kimi-k2.5)
2. Suggest 2-4 free models from Ollama Cloud and NVIDIA
3. Only suggest OpenRouter models if the user asks for premium models (Claude, GPT-4o) or the free providers lack suitable options
4. If suggesting any paid models, flag the cost before running

If unsure which provider has a model, check with:
```bash
curl -s https://openrouter.ai/api/v1/models -H "Authorization: Bearer $OPENROUTER_API_KEY" | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data'] if 'KEYWORD' in m['id'].lower()]"
```

**Rules:**
- 2-4 models per comparison (more = unwieldy in chat)
- If user doesn't specify, suggest a diverse set (different providers/sizes)
- Always confirm the model list with the user before running

## Step 2 — Send Prompt to All Models

Send the prompt to all models **in parallel**. The script handles this
automatically via `concurrent.futures.ThreadPoolExecutor` — no need for
delegate_task or manual parallelism.

### Simple / coding / review modes

One-shot chat completion per model. All calls fired concurrently by the script.

### Tool calling mode

Multi-turn loop per model (also concurrent across models):

```
Turn 1: Send prompt + tool definitions → Model returns tool_call(s)
Turn 2: Execute real tool → inject result → Model returns tool_call(s) or answer
Turn 3: ... until final answer or max turns (10 by default, configurable per-test via `max_turns` field in TEST_BANK)
```

**Real tool execution** — the script executes `web_search` and `web_extract`
for real:
- `web_search` → SearXNG (self-hosted, via `SEARXNG_URL`) with DDGS fallback
- `web_extract` → direct HTTP fetch with HTML-to-text conversion (3000 chars/page)

No mock tools, no fake results. Models must formulate good queries, pick the
right URLs, and synthesize from real content. A model that generates a bad
search query gets bad results and must recover.

**Tool definitions** passed via the OpenAI `tools` parameter:
- `web_search(query, limit)` — returns titles, URLs, snippets
- `web_extract(urls)` — returns page content as text

**No terminal tool** — we don't have a sandbox. Terminal is not exposed to
comparison models for safety reasons.

## Step 3 — Quality Check

For each response:
- **Empty/error**: if a model returns an error or empty response, note it and
  exclude from the comparison. Tell the user which model failed.
- **Truncated**: if response hit max_tokens, note it was truncated
- **Refusal**: if a model refused to answer, include it as-is (refusals are
  valid comparison data)

## Step 4 — Present Anonymously

**Shuffle the responses** and assign neutral labels. Do NOT reveal which model
is which.

**Shuffle rule:** Use a random permutation. Do not always put the same model
first. If the user is comparing 3 models, randomly assign A/B/C.

Present as:

```
🧪 Blind Model Comparison
Prompt: "[truncated to 100 chars...]"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 Model A:
[full response]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 Model B:
[full response]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 Model C:
[full response]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Vote: Reply with the letter of the best response (A, B, or C), or "tie".
```

**Formatting rules:**
- Full responses, not summaries — the user needs to judge quality
- Clear visual separation between responses
- Truncate at ~3000 chars per response for chat readability (note if truncated)
- If responses are very long (>3000 chars), save full versions to files and
  present truncated versions in chat with a note

## Step 5 — User Votes

Wait for the user to vote. Accept:
- Letter: "A", "B", "C", "D"
- "tie" or "tie between A and B"
- "all bad" (valid — none won)
- Specific feedback: "A is better but B's code is cleaner"

## Step 6 — Reveal Identities

After the vote, reveal the mapping:

```
🎭 Reveal:

Model A → <actual_model_name> (<provider>)
Model B → <actual_model_name> (<provider>)
Model C → <actual_model_name> (<provider>)

🏆 Your winner: Model <letter> = <actual_model_name>
```

## Step 7 — Synthesis (optional)

If the user wants the best possible answer, synthesize across all responses:

```
"Want me to synthesize the best parts of all responses into one?"
```

If yes, take the strongest elements from each response and produce a unified
answer. Note which model contributed each part:

```
## Synthesized Answer
[merged response]

## Contributions
- Section X: primarily from <model_name>
- Section Y: primarily from <model_name>
```

## Step 8 — Vote History (optional)

For recurring comparisons, log results to a file:

```
~/.hermes/data/model_compare_history.jsonl
```

Format:
```json
{"timestamp": "2026-06-27T12:00:00", "prompt": "...", "models": ["model_a", "model_b"], "winner": "model_a", "is_blind": true, "feedback": "..."}
```

This builds up a picture of which models win for which task types over time.

## Test Bank (24 tests)

Use `--test <ID>` to run a pre-built test prompt. The mode is auto-set based on the test domain.

| ID | Domain | Prompt summary | Tools? |
|---|---|---|---|
| A | tool_calling | Latest Python version + top 2 features | 🔧 |
| B | tool_calling | Find Odysseus GitHub repo star count | 🔧 |
| C | tool_calling | Best reverse proxy for homelab, then find key feature | 🔧 |
| E | tool_calling | Search LRU cache implementations, then write a better one | 🔧 |
| H1 | tool_calling | Python 3.14 free-threaded status — find 3 sources, identify authoritative | 🔧 |
| H2 | tool_calling | Node.js stable version + EOL date, verify against official source | 🔧 |
| S1 | tool_calling | Write IPv4 validator, run with test cases, report pass/fail | 🔧 📦 |
| S2 | tool_calling | Write CSV to file, analyze averages, run script, report results | 🔧 📦 |
| S3 | tool_calling | Generate Fibonacci, save as JSON, read back and verify | 🔧 📦 |
| S4 | tool_calling | Reverse a linked list, run test, verify output, debug if wrong | 🔧 📦 |
| S5 | tool_calling | Caesar cipher encrypt/decrypt, run and verify round-trip | 🔧 📦 |
| J | coding | Implement LRU cache, O(1), type hints + docstring | |
| K | coding | Concurrent URL fetch with per-URL timeout, preserve order | |
| L | coding | Fix buggy merge sort (off-by-one in merge step) | |
| M | coding | Retry decorator, 3x, 1s delay, preserve metadata | |
| H3 | coding | Thread-safe cache with TTL + LRU eviction | |
| H4 | coding | Token bucket rate limiter, thread-safe, injectable clock | |
| O | code_review | SQL injection + unreliable rowcount loop | |
| P | code_review | Clean code (no bugs) — test false positive rate | |
| Q | code_review | Thread-unsafe cache in production service | |
| R | code_review | Float for money + missing transfer validation | |
| H5 | code_review | Asyncio connection pool — inflight leak, missing lock, no timeout | |
| H6 | code_review | Auth service — MD5, timing-unsafe, forgeable token, no expiry check | |
| H7 | code_review | Logging service — fetchone() called twice per loop iteration | |

🔧 = uses web_search/web_extract tools. 📦 = uses sandbox tools (run_python/read_file/write_file).

Each test includes evaluation criteria used by the judge. Tool-calling tests also include a `max_turns` field (default 10) that controls the turn cap for that specific test — edit the TEST_BANK entry in `scripts/compare.py` to change it for an individual test. Code review tests include planted issues for objective scoring.

## Tool Calling Mode — How It Works

The `--mode tools` flag enables multi-turn tool calling with **real tools** (not mocks):

1. Script defines 5 tools as OpenAI function tools: `web_search`, `web_extract`, `run_python`, `read_file`, `write_file`
2. Sends prompt + tool defs to each model in parallel
3. When a model returns `tool_calls`, the script **executes the real call**:
   - `web_search` → SearXNG (self-hosted, via `SEARXNG_URL`) with DDGS fallback
   - `web_extract` → direct HTTP fetch, HTML stripped to text, truncated to 3000 chars/page
   - `run_python` → executes Python code in a per-model sandbox (temp dir, 10s timeout, no network)
   - `read_file` → reads a file from the sandbox directory (path traversal blocked)
   - `write_file` → writes a file to the sandbox directory (path traversal blocked)
4. Feeds the real result back as a `tool` role message
5. Repeats until final answer or max turns (10 default, configurable per-test via `max_turns` in TEST_BANK)
6. Tracks all turns, tool calls, tokens per turn, convergence status

**Sandbox security:** Each model gets its own temp directory (`tempfile.mkdtemp`). Path traversal (`../`) and absolute paths are rejected. Python execution has a 10-second timeout. No network access from within the sandbox subprocess. Sandbox is cleaned up after each model's run (in a `finally` block).

**Tools exposed:** `web_search`, `web_extract`, `run_python`, `read_file`, `write_file`. See `references/provider-tool-support.md` for which models support tool calling.

**Judge sees the full tool call trace** — what was searched, what was extracted, what code was run and its output, how many turns, whether it converged. This lets the judge evaluate *tool selection strategy*, not just the final answer.

## Efficiency Analysis

The `--efficiency` flag (auto-enabled for tools mode) prints a token comparison table:

```
📊 Efficiency Comparison
                      Turns  Tools   Tok In  Tok Out  Ratio   Time
✅ ollama-cloud:glm-5.2      5      5     7806      777   0.10  15.3s
✅ ollama-cloud:kimi-k2.5    5      4     5434     1051   0.19  14.8s
✅ ollama-cloud:gemma4:31b   2      1      949      248   0.26   6.5s
```

Key metrics: turns, tool calls, tokens in (context consumed), tokens out (generated), efficiency ratio (out/in), time. **Efficiency without accuracy is waste** — a model that uses few tokens but gets the wrong answer is not efficient, it's just wrong fast.

## Use Cases

### Model selection for a workflow
> "I need a model for summarizing legal documents. Compare claude-sonnet-4.6, gpt-4o, and gemini-2.5-flash on this prompt: [legal text]"

### Cost vs quality tradeoff
> "Compare glm-5.2 (free) vs claude-sonnet-4.6 (paid) on this coding prompt. Is the paid one worth it?"

### Prompt robustness testing
> "Test this prompt on 3 models — I want to see which ones follow my formatting instructions"

### Provider comparison
> "Compare the same model (llama-4-maverick) on OpenRouter vs NVIDIA — is there a difference?"

## Provider Health Tracking

The `scripts/provider_health.py` module tracks provider endpoint health and
implements dead-host cooldown — when a provider fails consecutively, it's
marked dead for a cooldown period and subsequent calls skip it automatically.

### How it works

- **2 consecutive failures** → provider marked dead
- **Cooldown**: 15s (Ollama Cloud), 30s (NVIDIA), 20s (OpenRouter)
- **Any success** → resets failure counter immediately
- **Cooldown expiry** → provider gets another chance
- State persists to `~/.hermes/data/provider_health.json` across runs

### CLI

```bash
# Check provider health
python3 scripts/provider_health.py --status

# Reset all providers
python3 scripts/provider_health.py --reset all

# Reset a specific provider
python3 scripts/provider_health.py --reset ollama-cloud
```

### Integration in compare.py

Both `call_model_simple` and `call_model_with_tools` check provider health
before making API calls. If a provider is in cooldown, the call is skipped
with a `[Provider X in cooldown (Ns remaining) — skipping]` message instead
of waiting for a timeout. Successes and failures are recorded automatically.

### When it matters

- Running comparisons across multiple providers — one flaky provider won't
  slow down the whole comparison
- Tool calling mode (10 turns per model) — a dead provider is skipped in
  seconds instead of waiting 60s × 10 turns = 10 minutes of timeouts
- Back-to-back comparisons — if a provider went down in a previous run, the
  next run knows to skip it

## Hybrid Mode — CLI Models Alongside API Models

The compare script only supports API-based providers (OpenRouter, Ollama
Cloud, NVIDIA). When the user wants to include models only accessible via
CLI tools (Codex CLI, Cursor CLI), use this hybrid pattern:

### When to use hybrid mode

- **Cost savings** — user says "use codex cli for gpt5.6" to avoid OpenRouter
  per-token costs. Codex ($20/mo) and Cursor Pro+ ($60/mo) include model
  access without per-token charges.
- **Model availability** — some models (e.g. `cursor-grok-4.5-high`) are
  only available through Cursor CLI, not on any API provider.

### How to run hybrid comparisons

1. **API models** → run through `scripts/compare.py` as normal (background)
2. **CLI models** → run each separately via terminal in parallel:\n   - **Codex CLI** (GPT-5.6): `codex exec --skip-git-repo-check -m gpt-5.5 "<prompt>" > /tmp/codex_result.json 2>&1`\n   - **Cursor CLI** (Grok 4.5): `export PATH="$HOME/.local/bin:$PATH" && export $(grep 'CURSOR_API_KEY=' ~/.hermes/.env | xargs) && agent -p --force --model "cursor-grok-4.5-high" --sandbox disabled "<prompt>" > /tmp/cursor_result.json 2>&1`
3. **Merge results** — collect API script output + CLI outputs, present all
   responses anonymously (shuffle together), let user vote, then reveal.

### CLI model specifics

| CLI | Binary | Model flag | Auth | Cost |
|-----|--------|-----------|------|------|
| Codex | `codex` | `-m gpt-5.6-sol` | OAuth (hermes auth) | $20/mo included |
| Cursor | `agent` | `--model "cursor-grok-4.5-high"` | `CURSOR_API_KEY` in .env | $60/mo included |

> **Always run CLI models in background** (`background=true` +
> `notify_on_complete=true`) — they can take 1-5 minutes. Run them in the
> same tool batch as the API script launch for true parallelism.

> **Cursor Grok 4.5 High** is the heaviest internal tier. For lighter
> tasks use `cursor-grok-4.5-medium`. See the `cursor-cli` skill for full
> model selection guidance.

## Pitfalls

- **Revealing identities too early** — never let model names leak into the anonymous presentation. Double-check before sending.
- **Always same order** — shuffle every time. If model A is always first, the user may develop position bias.
- **Not parallel** — send all API calls in the same tool block. Sequential calls waste time.
- **Ignoring failures** — if a model errors, tell the user. Don't silently exclude it.
- **Truncating too aggressively** — the user needs enough text to judge quality. 3000 chars minimum, full if shorter.
- **Forgetting to reveal** — always reveal after the vote. The whole point is knowing which model won.
- **Not confirming model list** — always confirm which models before spending API calls. Models cost money.
- **Spending paid API calls without confirmation** — OpenRouter is per-token paid. Always confirm with the user before calling OpenRouter models. Default to free providers (Ollama Cloud, NVIDIA) when no provider is specified. Only escalate to OpenRouter when the user explicitly requests a premium model or confirms cost.
- **Using max_tokens too low** — 8192 is the current default in compare.py. The previous 4096 caused truncated code on test J (LRU cache decorator cut off mid-function). If a model still truncates, raise the value in the payload dict.
- **Temperature mismatch** — use the same temperature (0.7 default) for all models. Different temperatures = unfair comparison.
- **API key leakage** — never print API keys in output. Always use env var references in curl commands.
- **Rate limits** — OpenRouter and NVIDIA have rate limits. If comparing 4+ models, add a small delay between calls if needed. OpenRouter free-tier models (with `:free` suffix) are especially prone to HTTP 429 rate-limiting after just 1-2 calls.
- **OpenRouter free-tier models (`:free` suffix) and the cost gate** — the script conservatively treats ALL OpenRouter models as paid, even `:free` suffix models that cost $0. Set `COMPARE_CONFIRM_PAID=1` env var to bypass the cost confirmation gate. Example: `COMPARE_CONFIRM_PAID=1 python3 scripts/compare.py --models "openrouter:tencent/hy3:free" ...`. No additional cost confirmation needed since the user has already chosen free-tier models.
- **NVIDIA NIM model IDs include the `nvidia/` prefix** — when using NIM via compare.py, pass the full model ID including the org prefix: `nvidia:nvidia/nemotron-3.5-lightning-30b-a3b` (provider colon, then full model ID). Passing `nvidia:nemotron-3.5-lightning-30b-a3b` (without the `nvidia/` prefix) returns HTTP 404 "page not found" — NIM requires the full `nvidia/...` model ID in the API payload.
- **Nemotron 3.5 Lightning free tier tool calling** — only the OpenRouter `:free` suffix and NIM direct support `tools`. The OpenRouter paid tier (`nvidia/nemotron-3.5-lightning` without `:free`, CoreWeave-hosted) returns HTTP 404 on `tools`. Use `nvidia:nvidia/nemotron-3.5-lightning-30b-a3b` (NIM, free, stable) or `openrouter:nvidia/nemotron-3.5-lightning:free` (free, but prone to 502s).
- **NVIDIA model list is stale** — the `/v1/models` endpoint lists many models but most return 404/410 when called. Only `meta/llama-3.1-70b-instruct`, `meta/llama-3.3-70b-instruct`, and `mistralai/mixtral-8x7b-instruct-v0.1` were alive as of June 2026. Always verify a model is alive with a simple chat completion before using it in a comparison. See `references/provider-tool-support.md` for the current alive list.
- **Assuming tool calling support** — not all models support the `tools` API parameter. Test with a simple tool-call request first. Models that mention "search" in text but don't emit `tool_calls` do NOT support tool calling. See `references/provider-tool-support.md` for the tested matrix.
- **Not all models support tool calling** — `deepseek-v3.2` (Ollama Cloud) mentions "search" in text but does NOT emit `tool_calls`. `mistralai/mixtral-8x7b-instruct-v0.1` (NVIDIA) returns HTTP 400 on the `tools` parameter. Test tool support per model before running `--mode tools`. See `references/provider-tool-support.md`.
- **Efficiency without accuracy is waste** — a model that uses few tokens but gets the wrong answer is not efficient. Always cross-reference efficiency stats with the judge score. gemma4:31b used 949 tokens and 2 turns but said Python 3.13 (wrong); kimi-k2.5 used 5434 tokens and 5 turns but got the correct answer with authoritative sources.
- **Tool calling loop can hit max turns** — some models keep searching without synthesizing. The 10-turn default cap (configurable per-test via `max_turns` in TEST_BANK) prevents infinite loops, but the result is marked "did not converge." Check the `converged` field in the trace. Increasing `max_turns` can help models that need more turns to synthesize, but watch for models that loop on the same URLs without converging — more turns won't fix a model that can't synthesize.
- **No `--max-turns` CLI override (fixed 2026-07-17)** — the script used to only support per-test `max_turns` in the TEST_BANK dict, requiring source edits to change the turn cap. This forced killing background runs to patch source. Now `--max-turns N` overrides at runtime. If the flag doesn't work, check that `compare.py` has the `--max-turns` argument parser entry.
- **User prefers CLI models to cut costs** — when the user says "use codex cli for gpt5.6" or "use cursor-grok-4.5-high", they want to avoid OpenRouter per-token charges. Route GPT-5.6 through Codex CLI and Grok 4.5 through Cursor CLI instead of OpenRouter. See the Hybrid Mode section above. This is a cost preference, not just a one-off request.\n- **Codex CLI model version limits** — `codex exec -m gpt-5.6-sol` fails with "requires a newer version of Codex" on v0.135. Test with a trivial prompt first (`codex exec --skip-git-repo-check -m <model> "say hello"`). Fall back to `gpt-5.5` if the newer model is unsupported.\n- **Codex CLI needs `--skip-git-repo-check`** — without it, Codex refuses to run outside a git repo. Always include this flag.\n- **Cursor CLI `--force` required for web access** — `--trust --sandbox disabled` alone does NOT enable web search in headless mode. Web requests are still blocked. Use `--force` (which implies `--trust`) to enable web access. Confirmed across 3 attempts: `--trust` → blocked, `--trust --sandbox disabled` → blocked, `--force` → works.\n- **OpenRouter geofenced models** — some models (e.g. `meta/muse-spark-1.1`) return HTTP 403 "This model is only available in the United States" when called from outside the US. No workaround without a US proxy. Exclude from comparisons run from non-US locations.
- **SearXNG default engines may return 0 results** — Google, DuckDuckGo, Brave, Startpage, and Mojeek engines frequently fail on self-hosted SearXNG (rate limits, CAPTCHAs). Only Bing and Yandex reliably return results. The script's `execute_web_search` now passes `&engines=bing,yandex,duckduckgo,google` explicitly. If search returns 43-char `{"results": [], "note": "No results found"}` on every query, check SearXNG engine health with `curl -s "http://$SEARXNG_URL/search?q=test&format=json&engines=bing"` and update the engines list in `scripts/compare.py`.
- **DDGS CLI syntax changed** — the old `ddgs --json -q ... -m ...` syntax no longer works. The new CLI uses `ddgs text -q ... -m ... -o <file>` (outputs to file, not stdout). The script's DDGS fallback has been updated to use the new syntax. Verify with `ddgs text --help` if fallback fails.
- **SEARXNG_URL not exported to background processes** — the env var is loaded from `~/.hermes/.env` by the script's `load_env()` function, but if you pass `--mode tools` to a background process (e.g. via `terminal(background=true)`), make sure to `export SEARXNG_URL=http://...` explicitly in the command. The `load_env()` function only sets vars that are NOT already in `os.environ`, but background shells start with a minimal environment.
- **compare.py requires 2+ models** — the script exits with "Error: need at least 2 models to compare" if you pass only one. To retry a single model after rate limiting, use a direct curl API call instead of the script.
- **Comparing reasoning-effort levels is now native (v1.2.0)** — use the `provider:@effort:model_id` syntax on `--models` and `--judge` (see the "Reasoning-effort A/B" section above). The old wrapper-harness pattern (`/root/.hermes/cache/ab_effort_run.py`, virtual providers registered in a loader script) still works for multi-test batteries with per-test ground-truth judging; the native syntax covers single-run comparisons. For CLI judges (e.g. Codex gpt-5.6-sol): write the rubric + anonymized responses to a temp file, run `codex exec --skip-git-repo-check -m gpt-5.6-sol "Read the file <path> and follow the instructions inside"`, parse JSON from stdout+stderr, shuffle the Response 1/2 order per test. Ground truth for code_review tests comes from TEST_BANK `evaluation` + `planted_issues` keys (NOT `evaluation_criteria`). Known findings (glm-5.3-flash, 2026-08-29): effort→reasoning-token count is NON-monotonic (high ≠ more thinking); high effort hit a 12-turn non-convergence on long tool chains while medium converged; medium won 4-2-2 on quality (8.6 vs 7.8 avg), high was ~3x faster median.
- **Kimi K3 rate limiting on OpenRouter** — `moonshotai/kimi-k3` hits HTTP 429 on the shared OpenRouter pool, especially when running multiple tests in parallel. Wait 15-30s and retry, or add a Moonshot API key to OpenRouter (BYOK) for dedicated rate limits.
- **Sandbox tests (S1-S5) need models that support 5 tools** — the sandbox tests pass all 5 tool definitions (web_search, web_extract, run_python, read_file, write_file) to the model. Some models may not support tool calling with 5 tools, or may only support 1-2 tools at a time. If a model fails on sandbox tests but passes research tests (A/B/C), it may be overwhelmed by the number of tool definitions. Test with a simpler sandbox prompt first.
- **Sandbox Python execution is not network-isolated** — the `run_python` tool runs `subprocess.run([sys.executable, script])` which can make network calls if the code imports `urllib` or `socket`. The 10-second timeout limits damage but is not a true sandbox. For production hardening, consider running in a container or seccomp filter. For model comparison purposes, the timeout is sufficient.
- **Sandbox temp files are cleaned up after each model** — the `run_tool_loop` function creates a temp dir per model and cleans it up in a `finally` block. If a model writes a file and then needs to read it back in a later turn, that works (same sandbox dir persists across turns). But if the script crashes mid-run, the `finally` block still cleans up.
- **Sandbox output truncated to 2000 chars** — `run_python` returns stdout and stderr truncated to 2000 chars each. If a model generates a lot of output (e.g. printing a large list), the truncated output may confuse it. Models that format output concisely will perform better on sandbox tests.

## Related Work

[Odysseus](https://github.com/pewdiepie-archdaemon/odysseus) — PewDiePie's self-hosted AI workspace — includes a "Compare" feature for blind side-by-side model testing with conceptually similar goals (anonymous presentation, evaluation, reveal). This skill takes a different approach: pure-prompt + stdlib scripts with no UI, designed to run inside any agent's tool loop rather than as a standalone web app. Odysseus also reported a fine-tuned Qwen 32B model scoring 39% on the Aider Polyglot benchmark — a useful data point for model comparison calibration.