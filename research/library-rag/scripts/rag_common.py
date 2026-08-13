#!/usr/bin/env python3
"""
Shared helpers for the Library RAG scripts.

Centralizes the bits that were previously copy-pasted across rag_index.py,
rag_query.py, and mcp_server.py: API-key loading, the embeddings call (with
retry/back-off), L2 normalization, float32 blob packing, and the sqlite-vec
connection.

Default provider: NVIDIA NIM (`nvidia/nemotron-3-embed-1b`, 2048-dim).
OpenRouter remains a supported fallback — when only ``OPENROUTER_API_KEY``
is present, ``load_api_key()`` automatically switches ``API_URL`` /
``EMBEDDING_MODEL`` / ``EMBEDDING_DIMS`` to the legacy bge-m3 path so the
key is never sent to the NVIDIA endpoint by accident.

Normalization policy: embeddings are returned RAW from the API helpers;
`float_to_blob()` is the single place that L2-normalizes before packing. This
guarantees both stored and query vectors are unit-norm, which makes the
`1 - distance**2 / 2` cosine approximation exact.
"""

import os, sys, struct, sqlite3, math, time
from pathlib import Path

import requests

# ─── Config ───────────────────────────────────────────────────────────────────
_NVIDIA_API_URL = 'https://integrate.api.nvidia.com/v1/embeddings'
_NVIDIA_EMBEDDING_MODEL = 'nvidia/nemotron-3-embed-1b'
_NVIDIA_EMBEDDING_DIMS = 2048

_OPENROUTER_API_URL = 'https://openrouter.ai/api/v1/embeddings'
_OPENROUTER_EMBEDDING_MODEL = 'baai/bge-m3'
_OPENROUTER_EMBEDDING_DIMS = 1024

EMBEDDING_MODEL = _NVIDIA_EMBEDDING_MODEL
EMBEDDING_DIMS = _NVIDIA_EMBEDDING_DIMS
API_URL = _NVIDIA_API_URL
API_KEY_ENV = 'NVIDIA_API_KEY'
# Legacy OpenRouter key — still accepted by load_api_key as a fallback
_FALLBACK_API_KEY_ENV = 'OPENROUTER_API_KEY'


def default_env_path():
    """Path to the .env file holding the API key (overridable via HERMES_ENV)."""
    return os.environ.get('HERMES_ENV', os.path.expanduser('~/.hermes/.env'))


def _apply_openrouter_fallback_config():
    """Point module config at legacy OpenRouter / bge-m3 when that key is used.

    Only switches values still at the NVIDIA defaults so an explicit manual
    override of ``API_URL`` / ``EMBEDDING_MODEL`` / ``EMBEDDING_DIMS`` is kept.
    """
    global API_URL, EMBEDDING_MODEL, EMBEDDING_DIMS, API_KEY_ENV
    if API_URL == _NVIDIA_API_URL:
        API_URL = _OPENROUTER_API_URL
    if EMBEDDING_MODEL == _NVIDIA_EMBEDDING_MODEL:
        EMBEDDING_MODEL = _OPENROUTER_EMBEDDING_MODEL
    if EMBEDDING_DIMS == _NVIDIA_EMBEDDING_DIMS:
        EMBEDDING_DIMS = _OPENROUTER_EMBEDDING_DIMS
    API_KEY_ENV = _FALLBACK_API_KEY_ENV


def _restore_nvidia_config_if_openrouter_fallback():
    """Undo an earlier OpenRouter auto-fallback when an NVIDIA key is present."""
    global API_URL, EMBEDDING_MODEL, EMBEDDING_DIMS, API_KEY_ENV
    if API_URL == _OPENROUTER_API_URL:
        API_URL = _NVIDIA_API_URL
    if EMBEDDING_MODEL == _OPENROUTER_EMBEDDING_MODEL:
        EMBEDDING_MODEL = _NVIDIA_EMBEDDING_MODEL
    if EMBEDDING_DIMS == _OPENROUTER_EMBEDDING_DIMS:
        EMBEDDING_DIMS = _NVIDIA_EMBEDDING_DIMS
    API_KEY_ENV = 'NVIDIA_API_KEY'


# ─── API key ──────────────────────────────────────────────────────────────────

def _read_key_from_env_file(env_path, env_var):
    """Return the value of ``env_var`` from a dotenv-style file, or None."""
    if not env_path.exists():
        return None
    for line in env_path.read_text().splitlines():
        if line.startswith('#') or '=' not in line:
            continue
        name, _, value = line.partition('=')
        if name.strip() == env_var:
            return value.strip().strip('"').strip("'")
    return None


def _lookup_key(env_var, env_path):
    """Return key for ``env_var`` from process env or dotenv file, or None."""
    key = os.environ.get(env_var)
    if key:
        return key
    return _read_key_from_env_file(env_path, env_var)


def load_api_key(required=True):
    """Load the embedding API key from the environment or the .env file.

    Prefers ``NVIDIA_API_KEY``. If only ``OPENROUTER_API_KEY`` is present,
    switches the module to the legacy OpenRouter / bge-m3 endpoint so the
    OpenRouter key is never sent to NVIDIA NIM.

    Returns the key string. If not found: raises ValueError when ``required``,
    otherwise returns ''.
    """
    env_path = Path(default_env_path())
    nvidia_key = _lookup_key('NVIDIA_API_KEY', env_path)
    if nvidia_key:
        _restore_nvidia_config_if_openrouter_fallback()
        return nvidia_key

    openrouter_key = _lookup_key(_FALLBACK_API_KEY_ENV, env_path)
    if openrouter_key:
        _apply_openrouter_fallback_config()
        return openrouter_key

    if required:
        raise ValueError(
            f"No NVIDIA_API_KEY (or {_FALLBACK_API_KEY_ENV}) found in env or {env_path}"
        )
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

def get_embeddings(texts, api_key, retries=3, input_type=None):
    """Get embeddings for a batch of texts from the configured provider.

    Returns ``(embeddings, usage)`` where ``embeddings`` is a list of raw
    (un-normalized) float vectors and ``usage`` is the API usage dict.
    Retries with exponential back-off on rate limits / transient errors.

    ``input_type`` is optional NIM-specific guidance (``"query"`` or
    ``"passage"``). When provided it is included in the request payload;
    when omitted, the provider default applies. OpenRouter ignores unknown
    fields, so this stays safe on the fallback path.
    """
    last_err = None
    payload = {
        'model': EMBEDDING_MODEL,
        'input': texts,
        'encoding_format': 'float',
    }
    if input_type is not None:
        payload['input_type'] = input_type

    for attempt in range(retries):
        try:
            resp = requests.post(
                API_URL,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json=payload,
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


def get_embedding(text, api_key, retries=3, input_type=None):
    """Get a single raw (un-normalized) embedding. Thin wrapper over get_embeddings."""
    embeddings, _ = get_embeddings(
        [text], api_key, retries=retries, input_type=input_type
    )
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
