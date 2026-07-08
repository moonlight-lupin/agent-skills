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

| Model | Provider | `tools` support |
|---|---|---|
| `deepseek-v3.2` | Ollama Cloud | ❌ mentions "search" in text but does not emit `tool_calls` |
| `mistralai/mixtral-8x7b-instruct-v0.1` | NVIDIA | ❌ returns HTTP 400 on the `tools` parameter |

### Quick self-test

```bash
# Does this model emit tool_calls? Run a 1-turn tools comparison and check the trace.
python3 scripts/compare.py --mode tools --test A \
  --models "ollama-cloud:<model-id>" --efficiency
```

If the trace shows 0 tool calls and the model "answered from memory," it likely
does not support the `tools` parameter on that provider.
