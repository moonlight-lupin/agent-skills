# Web Search Backend Fallback

## How Hermes Web Search Dispatch Works

The `web_search` tool dispatches through a provider registry. Backend selection priority:

1. `web.search_backend` in `config.yaml` (per-capability override)
2. `web.backend` in `config.yaml` (shared fallback)
3. Auto-detect from env vars (falls through to whichever API key is found)

## Current Configuration

```yaml
web:
  backend: firecrawl
  search_backend: searxng
  extract_backend: firecrawl
```

- **Search**: SearXNG at `$SEARXNG_URL` (self-hosted, free, multi-engine)
- **Extract**: Firecrawl cloud (1,000 free credits/month)
- **Search fallback**: DDGS (auto, runtime fallback patched in `web_tools.py`)

## Runtime Fallback Patch

The stock Hermes dispatcher does NOT retry on runtime failures — if the primary provider returns `{"success": false}`, the error is passed through to the caller. A patch was added to `tools/web_tools.py` (in the `web_search_tool` function) that retries with the next available provider:

```python
# After primary provider returns failure:
if not response_data.get("success"):
    for _name, _prov in _all_providers.items():
        if _name in tried or not _prov.supports_search():
            continue
        if not _prov.is_available():
            continue
        response_data = _prov.search(query, limit)
        tried.add(_name)
        if response_data.get("success"):
            break
```

This means: if SearXNG (NAS) is down → DDGS picks up automatically → Firecrawl as last resort. No error surfaces to the user or cron job.

## Verifying the Fallback

```python
# Test: point SearXNG at a dead port to trigger fallback
import os
os.environ['SEARXNG_URL'] = 'http://127.0.0.1:9999/'  # dead port
from tools.web_tools import web_search_tool
result = web_search_tool('test query', limit=2)
# Should succeed via DDGS fallback
```

## Available Backends

| Backend | Type | Env Var | Search | Extract |
|---------|------|---------|--------|---------|
| SearXNG | Self-hosted metasearch | `SEARXNG_URL` | ✅ | ❌ |
| DDGS | Free, no key | `ddgs` package | ✅ | ❌ |
| Firecrawl | Freemium cloud | `FIRECRAWL_API_KEY` | ✅ | ✅ |
| Tavily | Paid | `TAVILY_API_KEY` | ✅ | ✅ |
| Exa | Paid | `EXA_API_KEY` | ✅ | ✅ |
| Parallel | Paid | `PARALLEL_API_KEY` | ✅ | ✅ |
| Brave Free | Free API | `BRAVE_SEARCH_API_KEY` | ✅ | ❌ |
| xAI | Grok | — | ✅ | ❌ |

## Why This Configuration

- **SearXNG for search**: free, unlimited, aggregates Google+Bing+DDG+Yahoo in one query, no rate limits (self-hosted)
- **Firecrawl for extract only**: scraping/JS rendering/markdown conversion is Firecrawl's strength; 1k credits/mo is plenty when only used for extract (not search)
- **DDGS as fallback**: free, no key, already installed — automatic retry if SearXNG container/NAS is down

## Pitfall: Masked .env Secrets

Some agent runtimes mask secret values (display them as `***`) in terminal
output. If a key looks empty when you echo it, that may just be the masking —
the value is usually still present in the process environment. Confirm a key is
set without printing it, e.g.:
```bash
test -n "$FIRECRAWL_API_KEY" && echo "FIRECRAWL_API_KEY is set" || echo "not set"
```