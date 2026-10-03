#!/usr/bin/env python3
"""Jev rerank A/B analysis — reads the per-turn JSONL log.

Usage:
  python3 rerank_ab_report.py [LOG_PATH]

LOG_PATH defaults to $HERMES_HOME/data/jev-trial/rerank_ab_log.jsonl (else ~/.hermes/data/...)
(one JSON line per turn, written by jev_rerank.py).

Outputs A/B metrics for operator review:
  - rank1 flip rate (Jev #1 vs BM25 #1)
  - positional displacement (mean |rank change|, max)
  - band distribution (decisive-high / band / decisive-low shares)
  - fallback rate with reason breakdown
  - latency p50/p95 and cost estimate
Controlled English output. No data leaves the machine.
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

_base = os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")
DEFAULT_LOG = Path(_base) / "data" / "jev-trial" / "rerank_ab_log.jsonl"
BAND_LOW, BAND_HIGH = 0.35, 0.65


def load_records(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"WARN: unparseable line skipped: {line[:80]}")
    return records


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(int(len(ordered) * pct / 100.0), len(ordered) - 1)
    return ordered[idx]


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    records = load_records(path)
    if not records:
        print(f"No records in {path}")
        print("The log fills as turns run with SKILL_RETRIEVAL_RERANK=jev.")
        return

    applied = [r for r in records if r.get("jev_order")]
    skipped = [r for r in records if not r.get("jev_order")]
    n_applied = len(applied)

    print(f"Log: {path}")
    print(f"Turns recorded: {len(records)} (applied {n_applied}, skipped {len(skipped)})")

    if skipped:
        reasons = Counter(r.get("fallback_reason") or "unknown" for r in skipped)
        print("\nFallback rate:")
        print(f"  {len(skipped)}/{len(records)} = {len(skipped)/len(records):.0%}")
        for reason, count in reasons.most_common():
            print(f"  {reason}: {count}")

    if not n_applied:
        print("\nNo applied reranks yet — insufficient evidence.")
        return

    flips = sum(1 for r in applied if r.get("rank1_flip"))
    print("\nRank-1 flip rate (Jev #1 differs from BM25 #1):")
    print(f"  {sum(1 for r in applied if r.get('rank1_flip'))}/{n_applied}"
          f" = {sum(1 for r in applied if r.get('rank1_flip'))/n_applied:.0%}")

    displacements: list[float] = []
    band_counts: Counter = Counter()
    for r in applied:
        probs = r.get("jev_probs") or {}
        bm25 = r.get("bm25_order") or []
        jev = r.get("jev_order") or []
        bm25_rank = {sid: i for i, sid in enumerate(bm25)}
        for sid in jev:
            if sid in bm25_rank:
                disp = abs(bm25_rank[sid] - jev.index(sid))
                displacements.append(float(disp))
            p = probs.get(sid)
            if p is not None:
                if p >= BAND_HIGH:
                    band_counts["decisive_high"] += 1
                elif p > BAND_LOW:
                    band_counts["band_kept_bm25_position"] += 1
                else:
                    band_counts["decisive_low"] += 1

    print("\nPositional displacement (|BM25 rank - Jev rank|):")
    if displacements:
        mean_d = sum(displacements) / len(displacements)
        print(f"  mean {mean_d:.2f}  max {max(displacements):.0f}  n {len(displacements)}")
    else:
        print("  no data")

    total_band = sum(band_counts.values()) or 1
    print("\nBand distribution of Jev probabilities:")
    for band in ("decisive_high", "band_kept_bm25_position", "decisive_low"):
        count = band_counts.get(band, 0)
        print(f"  {band}: {count} ({count / total_band:.0%})")

    latencies = [r["latency_ms"] for r in applied if isinstance(r.get("latency_ms"), (int, float))]
    tokens = [r["input_tokens"] for r in applied if isinstance(r.get("input_tokens"), (int, float))]
    if latencies:
        print("\nJev overhead per turn:")
        print(f"  latency p50 {percentile(latencies, 50):.0f} ms"
              f"  p95 {percentile(latencies, 95):.0f} ms")
        if tokens:
            print(f"  input tokens: mean {sum(tokens)/len(tokens):.0f}"
                  f"  est cost/turn ${sum(tokens)/len(tokens)*0.042/1e6:.6f}")


if __name__ == "__main__":
    main()