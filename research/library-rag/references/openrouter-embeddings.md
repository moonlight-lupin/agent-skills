# Embeddings API — Reference

> **Current default:** NVIDIA NIM / `nvidia/nemotron-3-embed-1b` (2048-dim).
> See [Current default: NVIDIA NIM](#current-default-nvidia-nim) below.
>
> The rest of this document describes the **legacy OpenRouter / bge-m3 path**,
> kept for users who still configure OpenRouter as a fallback.

## Current default: NVIDIA NIM

```
POST https://integrate.api.nvidia.com/v1/embeddings
Authorization: Bearer $NVIDIA_API_KEY
Content-Type: application/json
```

```json
{
  "model": "nvidia/nemotron-3-embed-1b",
  "input": ["text one", "text two"],
  "encoding_format": "float",
  "input_type": "query"
}
```

| Property | Value |
|---|---|
| Model | `nvidia/nemotron-3-embed-1b` |
| Dimensions | 2048 |
| Auth env var | `NVIDIA_API_KEY` |
| Optional `input_type` | `"query"` or `"passage"` (improves retrieval; omit for provider default) |
| Cost | Free on NVIDIA NIM free-trial tier |

Virtual table: `CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[2048])`

To use the legacy OpenRouter path instead, set `OPENROUTER_API_KEY` and
omit `NVIDIA_API_KEY` — `load_api_key()` in `rag_common.py` auto-switches
`API_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIMS` to the bge-m3 values below.

---

# Legacy: OpenRouter Embeddings API

## Endpoint

```
POST https://openrouter.ai/api/v1/embeddings
Authorization: Bearer $OPENROUTER_API_KEY
Content-Type: application/json
```

## Request Format

```json
{
  "model": "baai/bge-m3",
  "input": ["text one", "text two", ...],
  "encoding_format": "float"
}
```

Supports batch input (array of strings). Returns one embedding per input string.

## Response Format

```json
{
  "data": [
    {"embedding": [0.01, -0.03, ...], "index": 0},
    {"embedding": [0.02, -0.01, ...], "index": 1}
  ],
  "model": "BAAI/bge-m3",
  "usage": {"prompt_tokens": 34, "cost": 3.4e-07}
}
```

## Model: bge-m3 (legacy)

| Property | Value |
|---|---|
| OpenRouter slug | `baai/bge-m3` |
| Dimensions | 1024 |
| Context | 8K tokens |
| Languages | 100+ (multilingual) |
| Price | $0.01/M input tokens |
| Rate limit | Standard (no special free-tier limit) |

**Why bge-m3 was chosen historically**: Top MTEB multilingual ranking. Handles English, Chinese, and other languages with equal quality. Superseded as the default by Nemotron-3-Embed-1B (better retrieval in our benchmarks, free via NIM, 2048-dim).

## Free Alternative (historical note — not the current default)

`nvidia/llama-nemotron-embed-vl-1b-v2:free` — truly $0 but:
- Llama-based, English-centric → Chinese quality unknown
- 200 req/day rate limit (full library needs ~2400 calls)
- "All prompts logged" by NVIDIA for model improvement
- Not worth the risk for a $0.05 total cost saving on the old OpenRouter path

The current default (`nvidia/nemotron-3-embed-1b` via NIM) is the recommended free path.

## Cost Estimates (June 2026, OpenRouter / bge-m3)

| Scope | Chunks | Tokens | Cost |
|---|---|---|---|
| Single book (300 pages) | ~300 | ~100K | ~$0.001 |
| Full library (all 7 sources) | ~78K | ~5M | ~$0.05–0.12 |
| Single query | 1 | ~10 | ~$0.0000001 |

## sqlite-vec Storage

Vectors stored as float32 little-endian blobs:

```python
import struct
def float_to_blob(emb):
    return struct.pack(f'{len(emb)}f', *emb)
```

Virtual table (legacy bge-m3): `CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[1024])`
Virtual table (current Nemotron): `CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[2048])`

Query with: `SELECT rowid, distance FROM vec_chunks WHERE embedding MATCH ? AND k = ?`

**Similarity**: sqlite-vec returns L2 distance. Convert to approximate cosine similarity:
```python
sim = max(0, 1 - distance ** 2 / 2)
```

## API Key

Current default key in `~/.hermes/.env`:

```
NVIDIA_API_KEY=nvapi-...
```

Legacy OpenRouter key (still accepted as fallback by `load_api_key`):

```
OPENROUTER_API_KEY=sk-or-v1-...
```
