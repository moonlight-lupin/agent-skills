# OpenRouter Embeddings API — Reference

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

## Model: bge-m3

| Property | Value |
|---|---|
| OpenRouter slug | `baai/bge-m3` |
| Dimensions | 1024 |
| Context | 8K tokens |
| Languages | 100+ (multilingual) |
| Price | $0.01/M input tokens |
| Rate limit | Standard (no special free-tier limit) |

**Why bge-m3**: Top MTEB multilingual ranking. Handles English, Chinese, and other languages with equal quality.

## Free Alternative (not recommended)

`nvidia/llama-nemotron-embed-vl-1b-v2:free` — truly $0 but:
- Llama-based, English-centric → Chinese quality unknown
- 200 req/day rate limit (full library needs ~2400 calls)
- "All prompts logged" by NVIDIA for model improvement
- Not worth the risk for a $0.05 total cost saving

## Cost Estimates (June 2026)

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

Virtual table: `CREATE VIRTUAL TABLE vec_chunks USING vec0(embedding float[1024])`

Query with: `SELECT rowid, distance FROM vec_chunks WHERE embedding MATCH ? AND k = ?`

**Similarity**: sqlite-vec returns L2 distance. Convert to approximate cosine similarity:
```python
sim = max(0, 1 - distance ** 2 / 2)
```

## API Key

Stored in `~/.hermes/.env` as `OPENROUTER_API_KEY=sk-or-v1-...`. Loaded by both scripts:

```python
def load_api_key():
    env = Path(os.environ.get('HERMES_ENV', os.path.expanduser('~/.hermes/.env'))).read_text()
    for line in env.splitlines():
        if 'OPENROUTER' in line.upper() and 'API_KEY' in line.upper() and not line.startswith('#'):
            return line.split('=', 1)[1].strip().strip('"').strip("'")
```
