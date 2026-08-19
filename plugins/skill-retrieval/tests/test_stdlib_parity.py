"""Parity, dependency, and performance tests for the stdlib BM25 index.

These tests guard against silent regressions:

- ``test_parity_*`` — proves the stdlib inverted index ranks identically to a
  reference BM25 implementation using the same formulas (within tolerance).
  Two corpora: synthetic (seeded, hermetic) and real (repo SKILL.md files).
- ``test_no_numeric_dependencies`` — asserts numpy/scipy are NOT imported by
  ``bm25_retriever``, preventing the dependency from creeping back.
- ``test_perf_*`` — coarse bounds to catch accidental O(n·vocab) regressions.
"""

import math
import random
import sys
import time
from pathlib import Path

import pytest

import bm25_retriever as br

TOL = 1e-4

# ─── Reference BM25 (plain Python, same formulas) ─────────────────────────────


def _reference_bm25(
    corpus_ids: list[str],
    corpus_texts: list[str],
    queries: list[str],
    k1: float = 1.5,
    b: float = 0.75,
    top_k: int = 6,
) -> dict[str, list[tuple[str, float]]]:
    """Independent BM25 Okapi implementation for parity checking.

    Uses the same formulas: Okapi TF saturation, Lucene-style clipped IDF
    (max(0, log((N-df+0.5)/(df+0.5)))), query-token de-duplication, descending
    sort with score > 0 filter.
    """

    def tok(text: str) -> list[str]:
        import re
        text = text.lower()
        text = re.sub(r"[^\w\s]", " ", text)
        return text.split()

    tokenized = [tok(t) for t in corpus_texts]
    doc_lens = [len(toks) for toks in tokenized]
    n_docs = len(corpus_texts)
    avgdl = sum(doc_lens) / n_docs if n_docs else 1.0

    # Vocabulary and document frequency.
    df: dict[str, int] = {}
    for toks in tokenized:
        for t in set(toks):
            df[t] = df.get(t, 0) + 1

    # Clipped IDF.
    idf: dict[str, float] = {}
    for term, d in df.items():
        val = math.log((n_docs - d + 0.5) / (d + 0.5))
        idf[term] = max(0.0, val)

    # Precompute per-doc term weights.
    doc_weights: list[dict[str, float]] = []
    for i, toks in enumerate(tokenized):
        counts: dict[str, int] = {}
        for t in toks:
            counts[t] = counts.get(t, 0) + 1
        dl = doc_lens[i]
        denom = k1 * (1.0 - b + b * dl / avgdl)
        weights = {}
        for term, tf in counts.items():
            sat = (tf * (k1 + 1.0)) / (tf + denom)
            weights[term] = sat * idf[term]
        doc_weights.append(weights)

    results: dict[str, list[tuple[str, float]]] = {}
    for query in queries:
        q_tokens = tok(query)
        seen: set[str] = set()
        scores: dict[int, float] = {}
        for t in q_tokens:
            if t in seen:
                continue
            seen.add(t)
            for i, weights in enumerate(doc_weights):
                w = weights.get(t)
                if w is not None:
                    scores[i] = scores.get(i, 0.0) + w
        if not scores:
            results[query] = []
            continue
        ranked = sorted(scores.items(), key=lambda x: (-x[1], x[0]))
        results[query] = [
            (corpus_ids[idx], score)
            for idx, score in ranked[:top_k]
            if score > 0
        ]
    return results


def _assert_parity(
    ref_results: dict[str, list[tuple[str, float]]],
    act_results: dict[str, list[tuple[str, float]]],
    queries: list[str],
) -> None:
    """Assert set-equality of returned ids and score tolerance.

    Ordering is checked between every pair of positions whose score
    difference exceeds TOL. Ties (within TOL) may reorder — this is the
    float32→float64 behaviour delta. Using pairwise comparison avoids a
    cascade failure where a permitted near-tie swap at one position
    shifts a later comparison against a large gap.
    """
    for query in queries:
        ref = ref_results[query]
        act = act_results[query]
        ref_ids = [sid for sid, _ in ref]
        act_ids = [sid for sid, _ in act]

        # Set of returned ids must be identical.
        assert set(ref_ids) == set(act_ids), (
            f"Query {query!r}: id set mismatch. "
            f"ref={ref_ids}, act={act_ids}, "
            f"missing={set(ref_ids) - set(act_ids)}, "
            f"extra={set(act_ids) - set(ref_ids)}"
        )

        # Score tolerance.
        ref_scores = dict(ref)
        act_scores = dict(act)
        for sid in ref_ids:
            assert abs(ref_scores[sid] - act_scores[sid]) <= TOL, (
                f"Query {query!r}: score mismatch for {sid}: "
                f"ref={ref_scores[sid]}, act={act_scores[sid]}, "
                f"diff={abs(ref_scores[sid] - act_scores[sid])}"
            )

        # Ordering: for every pair (i, j) where i < j, if the score gap
        # between ref[i] and ref[j] exceeds TOL, then act must place
        # ref[i]'s id before ref[j]'s id. This catches real ranking
        # inversions without being fooled by tie reorderings.
        n = min(len(ref), len(act))
        for i in range(n):
            for j in range(i + 1, n):
                gap = abs(ref[i][1] - ref[j][1])
                if gap > TOL:
                    ref_id_i = ref[i][0]
                    ref_id_j = ref[j][0]
                    act_pos_i = act_ids.index(ref_id_i)
                    act_pos_j = act_ids.index(ref_id_j)
                    assert act_pos_i < act_pos_j, (
                        f"Query {query!r}: ordering inversion for pair "
                        f"({ref_id_i}, {ref_id_j}) with gap={gap:.2e}: "
                        f"ref ranks {ref_id_i} before {ref_id_j} "
                        f"but act ranks them {act_pos_i} vs {act_pos_j}"
                    )


# ─── Parity: synthetic corpus ────────────────────────────────────────────────


@pytest.fixture
def synthetic_corpus():
    """Seeded random corpus: ~300 docs, ~1200-term vocab."""
    rng = random.Random(42)
    vocab_terms = [f"term{i}" for i in range(1200)]
    n_docs = 300
    ids = [f"doc{i}" for i in range(n_docs)]
    texts = []
    for _ in range(n_docs):
        n_tokens = rng.randint(5, 40)
        tokens = rng.choices(vocab_terms, k=n_tokens)
        texts.append(" ".join(tokens))
    return ids, texts


@pytest.fixture
def synthetic_queries():
    """100 random queries + a few realistic ones."""
    rng = random.Random(99)
    vocab_terms = [f"term{i}" for i in range(1200)]
    queries = []
    for _ in range(100):
        n = rng.randint(1, 5)
        queries.append(" ".join(rng.choices(vocab_terms, k=n)))
    queries += [
        "generate an image",
        "scrape a website",
        "plan a trip",
        "search papers on arxiv",
        "deploy docker container",
    ]
    return queries


def test_parity_synthetic(synthetic_corpus, synthetic_queries):
    """Stdlib index matches reference BM25 on synthetic corpus."""
    ids, texts = synthetic_corpus
    queries = synthetic_queries

    ref = _reference_bm25(ids, texts, queries, top_k=6)

    index = br.BM25Index()
    index.build(ids, texts)
    act = {q: index.retrieve(q, top_k=6) for q in queries}

    _assert_parity(ref, act, queries)


# ─── Parity: real corpus (repo SKILL.md files) ───────────────────────────────


def _load_real_corpus():
    """Load real SKILL.md descriptions from the repo root."""
    # tests/ → skill-retrieval/ → plugins/ → repo root
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    skills = []
    for skill_md in sorted(repo_root.rglob("SKILL.md")):
        parsed = br._parse_skill_md(skill_md)
        if parsed is None:
            continue
        name, desc = parsed
        if not name or not desc:
            continue
        rel = str(skill_md.parent.relative_to(repo_root))
        skills.append((rel, f"{name}: {desc}"))
    return skills


def test_parity_real_corpus():
    """Stdlib index matches reference BM25 on the repo's own skills."""
    skills = _load_real_corpus()
    if len(skills) < 3:
        pytest.skip("Not enough real skills for parity test")

    ids = [s[0] for s in skills]
    texts = [s[1] for s in skills]
    queries = [
        "generate an image",
        "scrape a website",
        "plan a trip",
        "search papers on arxiv",
        "deploy docker container",
        "review code for bugs",
        "send an email",
        "create a spreadsheet",
        "monitor news and alerts",
        "build a nextjs app",
        "research a topic thoroughly",
        "manage home assistant devices",
    ]

    ref = _reference_bm25(ids, texts, queries, top_k=6)

    index = br.BM25Index()
    index.build(ids, texts)
    act = {q: index.retrieve(q, top_k=6) for q in queries}

    _assert_parity(ref, act, queries)


# ─── No numeric dependencies guard ───────────────────────────────────────────


def test_no_numeric_dependencies():
    """bm25_retriever must not import numpy or scipy.

    This stops the dependency from silently creeping back in. We import the
    module in a fresh subprocess to get a clean sys.modules.
    """
    import subprocess
    result = subprocess.run(
        [
            sys.executable, "-c",
            "import sys; import bm25_retriever; "
            "assert 'numpy' not in sys.modules, 'numpy leaked into sys.modules'; "
            "assert 'scipy' not in sys.modules, 'scipy leaked into sys.modules'; "
            "print('OK: no numpy/scipy in sys.modules')",
        ],
        capture_output=True, text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(
            Path(__file__).resolve().parent.parent / "scripts"
        )},
    )
    assert result.returncode == 0, (
        f"Numeric dependency guard failed:\n{result.stdout}\n{result.stderr}"
    )


# ─── Performance bounds ──────────────────────────────────────────────────────


def test_perf_build_under_one_second():
    """Building 300 documents completes in well under a second."""
    rng = random.Random(42)
    vocab = [f"term{i}" for i in range(1200)]
    ids = [f"doc{i}" for i in range(300)]
    texts = [" ".join(rng.choices(vocab, k=rng.randint(5, 40))) for _ in range(300)]

    # Take the minimum of 3 builds to reduce wall-clock noise.
    best = float("inf")
    for _ in range(3):
        t0 = time.perf_counter()
        index = br.BM25Index()
        index.build(ids, texts)
        elapsed = time.perf_counter() - t0
        best = min(best, elapsed)

    assert best < 1.0, f"Build too slow: {best:.3f}s (expected < 1s)"


def test_perf_query_under_50ms():
    """A query returns in well under 50 ms."""
    rng = random.Random(42)
    vocab = [f"term{i}" for i in range(1200)]
    ids = [f"doc{i}" for i in range(300)]
    texts = [" ".join(rng.choices(vocab, k=rng.randint(5, 40))) for _ in range(300)]

    index = br.BM25Index()
    index.build(ids, texts)

    # Warm up.
    index.retrieve("term5 term10 term20", top_k=6)

    # Take the minimum of 10 queries to reduce wall-clock noise.
    best = float("inf")
    results = []
    for _ in range(10):
        t0 = time.perf_counter()
        results = index.retrieve("term5 term10 term20", top_k=6)
        elapsed = time.perf_counter() - t0
        best = min(best, elapsed)

    assert best < 0.050, f"Query too slow: {best * 1000:.3f}ms (expected < 50ms)"
    assert len(results) > 0
