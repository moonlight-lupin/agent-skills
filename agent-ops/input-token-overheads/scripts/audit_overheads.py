#!/usr/bin/env python3
"""Overhead audit for a Hermes instance (input-token-overheads v1.5).

Measures every per-turn input token source (SKILL.md ## Procedure step 1),
plus two checks ported from jzOcb/context-doctor (MIT):

1. Truncation/missing detection — every always-injected file (mandatory
   skills, memory blocks) is compared against its injection cap. A file
   over cap is flagged TRUNCATED: its instructions are silently cut every
   turn. A mandatory skill that does not exist is flagged MISSING.
2. --chart — a horizontal-bar PNG of overhead sources for chat sharing
   (Telegram). Requires matplotlib; degrades to text without it.

Usage:
  python3 audit_overheads.py                  # full text audit
  python3 audit_overheads.py --chart out.png  # + PNG chart
"""
import glob
import json
import os
import re
import sys

import yaml

HERMES = os.path.expanduser("~/.hermes")
DEFAULT_TOP_K = 6
DEFAULT_CTX = 200000
# Injection caps. The memory tool enforces these budgets; mandatory-skill
# full-body loads are capped by the retrieval plugin's per-skill limit.
CAPS = {
    "memory.md": 2200,
    "user profile": 3000,
    "mandatory skill body": 10000,
}


def load_config():
    p = os.path.join(HERMES, "config.yaml")
    if not os.path.isfile(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def audit_skill_descriptions():
    files = glob.glob(os.path.join(HERMES, "skills", "**", "SKILL.md"),
                      recursive=True)
    total = 0
    count = 0
    by_cat = {}
    for f in files:
        try:
            text = open(f, encoding="utf-8").read()
            m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
            if not m:
                continue
            fm = yaml.safe_load(m.group(1)) or {}
            desc = fm.get("description", "") or ""
            if not desc:
                continue
            cat = f.split("/skills/")[1].split("/")[0]
            by_cat.setdefault(cat, [0, 0])
            by_cat[cat][0] += len(desc)
            by_cat[cat][1] += 1
            total += len(desc)
            count += 1
        except Exception:
            pass
    return {"count": count, "total_chars": total, "by_category": by_cat}


def check_file(path, cap, label):
    """context-doctor-style status for one injected file."""
    if not os.path.isfile(path):
        return {"file": label, "status": "MISSING", "chars": None, "cap": cap}
    size = os.path.getsize(path)
    status = "TRUNCATED" if size > cap else "OK"
    return {"file": label, "status": status, "chars": size, "cap": cap}


def audit_injected_files():
    """Truncation/missing check on always-injected files."""
    out = []
    for mem in glob.glob(os.path.join(HERMES, "memories", "MEMORY.md")):
        out.append(check_file(mem, CAPS["memory.md"], "memory.md"))
    out.append(check_file(os.path.join(HERMES, "memories", "USER.md"),
                          CAPS["user profile"], "user profile"))
    # Mandatory skills (config: skills.mandatory or behavioral rules list)
    cfg = load_config()
    mandatory = ((cfg.get("skills") or {}).get("mandatory") or [])
    for name in mandatory:
        hits = glob.glob(os.path.join(HERMES, "skills", "**", name,
                                      "SKILL.md"), recursive=True)
        if not hits:
            out.append({"file": f"mandatory:{name}", "status": "MISSING",
                        "chars": None, "cap": CAPS["mandatory skill body"]})
        else:
            out.append(check_file(hits[0], CAPS["mandatory skill body"],
                                  f"mandatory:{name}"))
    return out


def estimate_sources(desc_stats, cfg):
    top_k = int(os.environ.get("SKILL_RETRIEVAL_TOP_K", str(DEFAULT_TOP_K)))
    avg = desc_stats["total_chars"] // max(desc_stats["count"], 1)
    disabled = (cfg.get("skills") or {}).get("disabled", []) or []
    comp = cfg.get("compression") or {}
    sources = [
        ("skill descriptions (top-K)", top_k * avg // 4),
        ("memory.md", (os.path.getsize(os.path.join(HERMES, "memories", "MEMORY.md")) // 4) if os.path.isfile(os.path.join(HERMES, "memories", "MEMORY.md")) else 0),
        ("user profile", (os.path.getsize(os.path.join(HERMES, "memories", "USER.md")) // 4) if os.path.isfile(os.path.join(HERMES, "memories", "USER.md")) else 0),
    ]
    return sources, {"top_k": top_k, "avg_desc_chars": avg,
                     "disabled": len(disabled), "compression": comp}


def health_ratio(overhead_tokens, ctx=DEFAULT_CTX):
    pct = overhead_tokens / ctx * 100
    if pct < 5:
        return pct, "excellent"
    if pct < 15:
        return pct, "healthy"
    if pct < 25:
        return pct, "acceptable"
    return pct, "unhealthy"


def make_chart(sources, path, ctx=DEFAULT_CTX):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("chart skipped: matplotlib not available", file=sys.stderr)
        return None
    labels = [s[0] for s in sources]
    vals = [s[1] for s in sources]
    fig, ax = plt.subplots(figsize=(8, 1.2 + 0.5 * len(labels)))
    ax.barh(labels[::-1], vals[::-1], color="#4a7c59")
    ax.set_xlabel("tokens per turn (est.)")
    ax.set_title(f"Hermes input overhead per turn (window {ctx:,} tok)")
    for i, v in enumerate(vals[::-1]):
        ax.text(v, i, f" {v:,}", va="center", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chart", metavar="PNG", default=None,
                    help="also write a PNG chart to this path")
    ap.add_argument("--ctx", type=int, default=DEFAULT_CTX,
                    help="context window size in tokens")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()

    cfg = load_config()
    desc = audit_skill_descriptions()
    injected = audit_injected_files()
    sources, meta = estimate_sources(desc, cfg)
    overhead = sum(v for _, v in sources)
    pct, rating = health_ratio(overhead, args.ctx)

    result = {
        "sources": [{"source": s, "tokens_est": v} for s, v in sources],
        "overhead_tokens_est": overhead,
        "overhead_pct_of_window": round(pct, 1),
        "health": rating,
        "injected_files": injected,
        "meta": meta,
    }
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Overhead estimate: ~{overhead:,} tokens/turn "
              f"({pct:.1f}% of {args.ctx:,}) -> {rating}")
        for s, v in sources:
            print(f"  {v:>7,} tok  {s}")
        print(f"Skills: {desc['count']} total, "
              f"{desc['total_chars']:,} chars in descriptions, "
              f"{meta['disabled']} disabled")
        print("Injected-file check (context-doctor port):")
        for f in injected:
            marker = {"OK": "OK ", "TRUNCATED": "!!", "MISSING": "??"}[f["status"]]
            detail = ("-" if f["chars"] is None else
                      f"{f['chars']:,} chars (cap {f['cap']:,})")
            print(f"  [{marker}] {f['status']:<9} {f['file']}: {detail}")

    if args.chart:
        out = make_chart(sources, args.chart, args.ctx)
        if out:
            print(f"chart written: {out}")
    truncated = [f for f in injected if f["status"] != "OK"]
    if truncated:
        print(f"\nACTION: {len(truncated)} injected file(s) need attention "
              "(TRUNCATED = silently cut every turn; MISSING = broken "
              "reference)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
