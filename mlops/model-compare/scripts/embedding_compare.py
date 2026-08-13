#!/usr/bin/env python3
"""
Embedding model benchmark — compare embedding models on pairwise similarity
and retrieval accuracy.

Part of the model-compare skill. Run this before switching embedding models
to verify the new model is better for your use case.

Compares models on:
  - Pairwise similarity (8 test pairs, similar + dissimilar)
  - Retrieval ranking (3 queries against 6 docs, top-1 accuracy)
  - Latency

Usage:
  python3 embedding_compare.py
  python3 embedding_compare.py --models "nvidia:nvidia/nemotron-3-embed-1b" "openrouter:BAAI/bge-m3"
  python3 embedding_compare.py --quiet
  python3 embedding_compare.py --env-file /path/to/.env

Requires NVIDIA_API_KEY and/or OPENROUTER_API_KEY in the environment or
an env file (default via --env-file).

No external dependencies beyond stdlib + urllib (no pip installs needed).
"""

import argparse
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ─── Provider config ─────────────────────────────────────────────────────────

PROVIDERS = {
    "nvidia": {
        "url": "https://integrate.api.nvidia.com/v1/embeddings",
        "key_env": "NVIDIA_API_KEY",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/embeddings",
        "key_env": "OPENROUTER_API_KEY",
    },
}

DEFAULT_MODELS = [
    "openrouter:BAAI/bge-m3",
    "nvidia:nvidia/nemotron-3-embed-1b",
]

DEFAULT_ENV_FILE = os.environ.get("SKILL_ENV_FILE", str(Path.home() / ".hermes" / ".env"))

# ─── Test data ───────────────────────────────────────────────────────────────

# Test pairs: (text_a, text_b, expected_similarity)
TEST_PAIRS = [
    ("The quick brown fox jumps over the lazy dog", "A fast fox leaps above a sleeping canine", "similar"),
    ("How to bake sourdough bread", "What is the recipe for sourdough bread?", "similar"),
    ("Python list comprehension syntax", "How to use list comprehensions in Python", "similar"),
    ("The quick brown fox jumps over the lazy dog", "Machine learning models require large datasets", "dissimilar"),
    ("Invoice for five thousand dollars due Friday", "Bill for $5000 payable this week", "similar"),
    ("Kubernetes pod crash loop backoff", "How to fix a car engine that won't start", "dissimilar"),
    ("The weather is sunny today", "Today's climate is bright and clear", "similar"),
    ("SQL JOIN vs NoSQL lookup performance", "Database query optimization techniques", "similar"),
]

RETRIEVAL_DOCS = [
    "Python is a high-level programming language with dynamic typing",
    "Rust provides memory safety without garbage collection",
    "The Eiffel Tower is located in Paris, France",
    "Machine learning models can suffer from overfitting on small datasets",
    "Kubernetes orchestrates containerized applications across clusters",
    "Sourdough bread requires a starter culture and long fermentation",
]

RETRIEVAL_QUERIES = [
    "How do I train a model without overfitting?",
    "What language is best for systems programming with memory safety?",
    "How to bake fermented bread?",
]

EXPECTED_MATCHES = [3, 1, 5]  # 0-indexed doc indices


# ─── Env loading ─────────────────────────────────────────────────────────────

def load_env(env_file=None):
    """Load env vars from an env file if not already in the environment.

    Prefers existing process env; only fills missing keys from the file.
    """
    if env_file is None:
        env_file = DEFAULT_ENV_FILE
    env_path = Path(os.path.expanduser(env_file))
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
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        if key and key not in os.environ:
            os.environ[key] = value


def get_api_key(provider):
    cfg = PROVIDERS.get(provider)
    if not cfg:
        raise ValueError(f"Unknown provider: {provider}")
    key = os.environ.get(cfg["key_env"], "")
    if not key:
        raise ValueError(f"No API key found for {provider} (env: {cfg['key_env']})")
    return key


# ─── Embedding helpers ───────────────────────────────────────────────────────

def cosine(a, b):
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na * nb > 0 else 0.0


def get_embeddings(provider, model, texts, input_type=None, api_key=None):
    """Fetch embeddings from a provider. Returns (embeddings, usage, latency).

    For NVIDIA, passes input_type ("query" or "passage"). OpenRouter ignores it.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    cfg = PROVIDERS[provider]
    if api_key is None:
        api_key = get_api_key(provider)

    body = {"model": model, "input": texts}
    if provider == "nvidia":
        body["input_type"] = input_type or "passage"
        body["encoding_format"] = "float"

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        cfg["url"],
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            resp = json.loads(r.read())
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code} from {provider}: {err_body}") from e
    latency = time.time() - start
    return [d["embedding"] for d in resp["data"]], resp.get("usage", {}), latency


def parse_model_spec(spec):
    """Parse 'provider:model_id' into (provider, model_id)."""
    if ":" not in spec:
        raise ValueError(f"model spec '{spec}' must be 'provider:model_id'")
    provider, model_id = spec.split(":", 1)
    if provider not in PROVIDERS:
        raise ValueError(
            f"unknown provider '{provider}'. Available: {', '.join(PROVIDERS.keys())}"
        )
    return provider, model_id


def short_label(provider, model):
    """Human-readable short name for table columns."""
    mid = model.lower()
    if "bge-m3" in mid:
        return "bge-m3"
    if "nemotron" in mid:
        return "Nemotron"
    return model.rsplit("/", 1)[-1][:12]


# ─── Main ────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Benchmark embedding models on similarity and retrieval accuracy",
    )
    parser.add_argument(
        "--env-file",
        default=DEFAULT_ENV_FILE,
        help="Path to dotenv file (default: %(default)s)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=True,
        help="Show per-test details (default: on)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only print summary",
    )
    parser.add_argument(
        "--models", "-m",
        nargs="+",
        default=DEFAULT_MODELS,
        help='Models as "provider:model_id" (default: bge-m3 + Nemotron)',
    )
    args = parser.parse_args(argv)

    verbose = not args.quiet
    load_env(args.env_file)

    models = []
    for spec in args.models:
        try:
            models.append(parse_model_spec(spec))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    if len(models) < 1:
        print("Error: need at least 1 model", file=sys.stderr)
        sys.exit(1)

    for provider, _ in models:
        try:
            get_api_key(provider)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    labels = [short_label(p, m) for p, m in models]
    title = " vs ".join(labels)

    print("=" * 70)
    print(f"  Embedding Model Comparison: {title}")
    print("=" * 70)

    # ── Pairwise ──
    wins = {label: 0 for label in labels}
    if verbose:
        print("\n--- Pairwise Similarity ---")
        header = f"{'#':<4} {'Expected':<12}"
        for label in labels:
            header += f" {label:>10}"
        header += f" {'Winner':>10}"
        print(header)
        print("-" * (30 + 11 * len(labels)))

    for i, (a, b, expected) in enumerate(TEST_PAIRS):
        sims = []
        for provider, model in models:
            embs, _, _ = get_embeddings(provider, model, [a, b], input_type="passage")
            sims.append(cosine(embs[0], embs[1]))

        if expected == "similar":
            best_idx = max(range(len(sims)), key=lambda j: sims[j])
        else:
            best_idx = min(range(len(sims)), key=lambda j: sims[j])
        winner = labels[best_idx]
        wins[winner] += 1

        if verbose:
            row = f"  {i + 1:<3} {expected:<12}"
            for sim in sims:
                row += f" {sim:>10.4f}"
            row += f" {winner:>10}"
            print(row)

    # ── Retrieval ──
    correct = {label: 0 for label in labels}
    if verbose:
        print("\n--- Retrieval Ranking (top-1 accuracy) ---")
        print("-" * 70)

    for qi, (query, expected_idx) in enumerate(zip(RETRIEVAL_QUERIES, EXPECTED_MATCHES)):
        tops = []
        for provider, model in models:
            q_emb, _, _ = get_embeddings(provider, model, [query], input_type="query")
            d_emb, _, _ = get_embeddings(
                provider, model, RETRIEVAL_DOCS, input_type="passage"
            )
            top = max(range(len(d_emb)), key=lambda idx: cosine(q_emb[0], d_emb[idx]))
            tops.append(top)

        for j, top in enumerate(tops):
            if top == expected_idx:
                correct[labels[j]] += 1

        if verbose:
            print(f"  Q{qi + 1}: \"{query[:45]}\" -> expect doc {expected_idx}")
            for j, top in enumerate(tops):
                hit = "YES" if top == expected_idx else f"NO({top})"
                print(f"      {labels[j]:<12} {hit}")

    # ── Latency ──
    latencies = {}
    if verbose:
        print("\n--- Latency ---")
    for (provider, model), label in zip(models, labels):
        _, _, latency = get_embeddings(
            provider, model, ["test sentence"], input_type="query"
        )
        latencies[label] = latency
        if verbose:
            print(f"  {label} ({provider}): {latency:.3f}s")

    # ── Summary ──
    n_q = len(RETRIEVAL_QUERIES)
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    for (provider, model), label in zip(models, labels):
        print(f"  {label}: {provider}/{model}")
    pairwise_str = " | ".join(
        f"{label} {wins[label]}/{len(TEST_PAIRS)}" for label in labels
    )
    retrieval_str = " | ".join(f"{label} {correct[label]}/{n_q}" for label in labels)
    latency_str = " | ".join(f"{label} {latencies[label]:.3f}s" for label in labels)
    print(f"  Pairwise:   {pairwise_str}")
    print(f"  Retrieval:  {retrieval_str}")
    print(f"  Latency:    {latency_str}")


if __name__ == "__main__":
    main()
