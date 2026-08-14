# Provider & tool-calling support

Which providers `compare.py` knows about, and which models actually support the
`tools` API parameter used by `--mode tools`. **Provider catalogues and model
availability change constantly — treat every list here as a starting point and
verify live before relying on it.**

## Providers

| Provider | Env var | Cost | Endpoint |
|---|---|---|---|
| Ollama Cloud | `OLLAMA_API_KEY` | Free | `https://ollama.com/v1/chat/completions` |
| NVIDIA | `NVIDIA_API_KEY` | Free | `https://integrate.api.nvidia.com/v1/chat/completions` |
| OpenRouter | `OPENROUTER_API_KEY` | Paid (per-token) | `https://openrouter.ai/api/v1/chat/completions` |

Routing is cost-aware: free providers (Ollama Cloud, NVIDIA) are preferred, and
OpenRouter is only used on explicit confirmation (see SKILL.md → *Cost-aware
provider routing*).

## NVIDIA: verify a model is alive first

NVIDIA's `/v1/models` endpoint lists a large catalogue (121 at build time), but
**most entries return 404/410 when actually called.** Always confirm a model
with a simple chat completion before using it in a comparison.

Known-alive as of **June 2026** (re-verify — this drifts):

- `meta/llama-3.1-70b-instruct`
- `meta/llama-3.3-70b-instruct`
- `mistralai/mixtral-8x7b-instruct-v0.1`

## Tool-calling support

Not all models support the `tools` request parameter, even if they mention
"search" in their text output. A model that describes searching but never emits
a `tool_calls` field does **not** support tool calling and will fail `--mode
tools`. Test each model with a single tool-call request before a full run.

Observed (re-verify before relying on it):

| Model | Provider | `tools` support | Notes |
|---|---|---|---|
| `glm-5.2` | Ollama Cloud | ✅ Excellent | Converges fast, good tool selection. Can be derailed by garbled page extracts. |
| `minimax-m3` | Ollama Cloud | ✅ Good | Efficient researcher, but over-researches instead of synthesizing on some tasks. |
| `kimi-k2.5` | Ollama Cloud | ✅ Good | Tested in prior sessions. Correct answers with authoritative sources. |
| `gemma4:31b` | Ollama Cloud | ✅ Basic | Fewest turns/tokens but got wrong answer (Python 3.13 vs 3.14). |
| `deepseek-v3.2` | Ollama Cloud | ❌ | Mentions "search" in text but does not emit `tool_calls`. |
| `mistralai/mixtral-8x7b-instruct-v0.1` | NVIDIA | ❌ | Returns HTTP 400 on the `tools` parameter. |
| `tencent/hy3:free` | OpenRouter | ⚠️ Poor | Emits `tool_calls` but consistently fails to synthesize — empty output or max-turns. |
| `poolside/laguna-m.1:free` | OpenRouter | ⚠️ Rate-limited | HTTP 429 after 2 calls. Free tier too throttled for tool mode. |
| `moonshotai/kimi-k3` | OpenRouter | ✅ Excellent | 2.8T MoE, 1M ctx. Fastest convergence (3 turns), lowest token usage. $3/M in / $15/M out. |
| `meta/muse-spark-1.1` | OpenRouter | ❌ Geofenced | HTTP 403: "Only available in the United States." Fails outside US. |
| `meta/muse-glimmer-30b` | OpenRouter | ✅ Emits tool_calls, ❌ Never converges | Emits valid `tool_calls` (API works) but fails to synthesize final answers. 0/4 tool-calling tests converged (tests A/B/C/E, Aug 2026). Extracts content from URLs but keeps searching until max turns. Heavy reasoner — 50K+ tokens per test. $0.30/M in, $1.20/M out. Also failed coding test J (returned -1 instead of None, int-only types) and code review test O (over-engineered, changed API contract). Not viable for agentic workflows. |
| `nvidia/nemotron-3.5-lightning:free` | OpenRouter | ⚠️ Tools work, never converges | **Free tier only** supports `tools` (NVIDIA-hosted). **Paid tier** (`nvidia/nemotron-3.5-lightning` without `:free`) does NOT — CoreWeave-hosted, returns HTTP 404 on `tools` param. The free tier emits valid `tool_calls` and follows the Think→Search→Extract loop correctly, but fails to synthesize — 0/1 tool-calling tests converged (test A: 8 turns, 8 tool calls, 16K tokens, 61s, max turns hit). Kept searching "Python 3.14 release date" and "Python 3.14 new features t-strings" across 8 turns without producing a final answer. Same non-convergence pattern as Muse Glimmer. Strong on coding (clean OrderedDict LRU, best docstrings) and code review (caught all 6 issues in test O, uniquely found falsy-value `if cached:` bug in test Q). Free tier is slow: 108-152s on one-shot, 61s on tool calling. |

### CLI-only models (not in compare.py — run separately)

These models are accessible only through their respective CLIs, not via API
from compare.py. Run them in parallel via `terminal(background=true)` and merge
results manually. See `references/model-behavior.md` → *CLI Model Integration
Pattern* for launch commands and pitfalls.

| Model | CLI | Tool calling | Notes |
|---|---|---|---|
| `gpt-5.5` / `gpt-5.6-sol` | Codex CLI (`codex exec`) | ✅ (via Codex web search) | ⚠️ Codex v0.135 doesn't support gpt-5.6-sol — needs upgrade. Use gpt-5.5 as fallback. Very high token overhead (~37-50K per test). |
| `cursor-grok-4.5-high` | Cursor CLI (`agent -p`) | ✅ (via Cursor web search) | ⚠️ Requires `--force` flag for web access in headless mode. `--trust --sandbox disabled` alone is NOT enough — web requests still blocked. |

See `references/model-behavior.md` for detailed per-model profiles from 16+ tests.

### Quick self-test

```bash
# Does this model emit tool_calls? Run a 1-turn tools comparison and check the trace.
python3 scripts/compare.py --mode tools --test A \
  --models "ollama-cloud:<model-id>" --efficiency
```

If the trace shows 0 tool calls and the model "answered from memory," it likely
does not support the `tools` parameter on that provider.
