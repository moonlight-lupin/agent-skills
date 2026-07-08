#!/usr/bin/env python3
"""
Shared helpers for the Library RAG scripts.

Centralizes the bits that were previously copy-pasted across rag_index.py,
rag_query.py, and mcp_server.py: API-key loading, the OpenRouter embeddings
call (with retry/back-off), L2 normalization, float32 blob packing, and the
sqlite-vec connection.

Normalization policy: embeddings are returned RAW from the API helpers;
`float_to_blob()` is the single place that L2-normalizes before packing. This
guarantees both stored and query vectors are unit-norm, which makes the
`1 - distance**2 / 2` cosine approximation exact.
"""

import os, sys, struct, sqlite3, math, time
from pathlib import Path

import requests

# ─── Config ───────────────────────────────────────────────────────────────────
EMBEDDING_MODEL = 'baai/bge-m3'
EMBEDDING_DIMS = 1024
API_URL = 'https://openrouter.ai/api/v1/embeddings'


def default_env_path():
    """Path to the .env file holding the API key (overridable via HERMES_ENV)."""
    return os.environ.get('HERMES_ENV', os.path.expanduser('~/.hermes/.env'))


# ─── API key ──────────────────────────────────────────────────────────────────

def load_api_key(required=True):
    """Load the OpenRouter API key from the environment or the .env file.

    Returns the key string. If not found: raises ValueError when ``required``,
    otherwise returns ''.
    """
    key = os.environ.get('OPENROUTER_API_KEY')
    if key:
        return key
    env_path = Path(default_env_path())
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if 'OPENROUTER' in line.upper() and 'API_KEY' in line.upper() and not line.startswith('#'):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
    if required:
        raise ValueError(f"No OPENROUTER_API_KEY found in env or {env_path}")
    return ''


# ─── Vectors ──────────────────────────────────────────────────────────────────

def normalize_vec(vec):
    """L2-normalize a vector. Returns a new list."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def float_to_blob(emb):
    """Pack a float list into a float32 little-endian blob, L2-normalized.

    This is the single normalization point for the pipeline — see module docstring.
    """
    emb = normalize_vec(emb)
    return struct.pack(f'{len(emb)}f', *emb)


# ─── Embeddings ───────────────────────────────────────────────────────────────

def get_embeddings(texts, api_key, retries=3):
    """Get embeddings for a batch of texts from OpenRouter.

    Returns ``(embeddings, usage)`` where ``embeddings`` is a list of raw
    (un-normalized) float vectors and ``usage`` is the API usage dict.
    Retries with exponential back-off on rate limits / transient errors.
    """
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.post(
                API_URL,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': EMBEDDING_MODEL,
                    'input': texts,
                    'encoding_format': 'float',
                },
                timeout=120,
            )
            if resp.status_code == 200:
                data = resp.json()
                embeddings = [item['embedding'] for item in data['data']]
                usage = data.get('usage', {})
                return embeddings, usage
            elif resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                last_err = f"rate limited (429)"
                print(f"  ⏳ Rate limited, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
            else:
                last_err = f"API error {resp.status_code}: {resp.text[:200]}"
                print(f"  ❌ {last_err}", file=sys.stderr)
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
        except Exception as e:
            last_err = f"request error: {e}"
            print(f"  ⚠️  {last_err}", file=sys.stderr)
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"Failed after {retries} retries: {last_err}")


def get_embedding(text, api_key, retries=3):
    """Get a single raw (un-normalized) embedding. Thin wrapper over get_embeddings."""
    embeddings, _ = get_embeddings([text], api_key, retries=retries)
    return embeddings[0]


# ─── DB ───────────────────────────────────────────────────────────────────────

def connect_db(db_path):
    """Open a sqlite3 connection with the sqlite-vec extension loaded."""
    conn = sqlite3.connect(str(db_path))
    import sqlite_vec
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn
