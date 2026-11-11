#!/usr/bin/env python3
"""Aggregate a model-compare battery: judge scores from compare.py logs + metrics from result JSONs.

Usage:
  python3 aggregate_battery.py OUTDIR \
      --seq log_tools.txt=tools:A,B,C,E,H1,H2,S1,S2,S3,S4,S5 \
      --seq log_coding.txt=coding:J,K,L,M,H3,H4 \
      --seq log_review.txt=review:O,P,Q,R,H5,H6,H7 \
      --seq log_rerun.txt=coding:H3,review:P,Q,H5,H6,H7 \
      [--seq log_rerun2.txt=review:H5,H6,H7]

Each --seq entry lists one compare.py loop's logfile and the tests it ran, IN
LOOP ORDER. Selection rule: for each (mode, test) take the LATEST COMPLETE
judge block (exactly 3 Score lines) across the logs in CLI order - rerun logs
supersede originals only where the judge actually ran; blocks whose judge died
in a cooldown have no Score lines and fall through to the older complete block.
Arm metrics come from OUTDIR/<mode>_<test>.json (the last run's file). Reads
OUTDIR logs + JSONs only; writes OUTDIR/aggregated.json (override with --output).
"""
import argparse, json, os, re, sys

HDR = re.compile(r"(?m)^(?P<mark>[✅❌]) Model (?P<label>[A-D]) \((?P<model>[^):]+:[^):]+)\)")
JUDGE = re.compile(r"⚖️\s*Judge:")
SCORE = re.compile(r"#(\d) Model ([A-D]) — Score: ([\d.]+)/10")
BEST = re.compile(r"Best: Model ([A-D])")


def parse_seq(spec):
    logfile, rest = spec.split("=", 1)
    mode, tests = rest.split(":", 1)
    return logfile, [(mode.strip(), t.strip()) for t in tests.split(",")]


def parse_blocks(text):
    """Return complete judge blocks [(mapping, marks, scores, best)] in log order."""
    headers = list(HDR.finditer(text))
    judges = [m.start() for m in JUDGE.finditer(text)]
    triples = [headers[i:i + 3] for i in range(0, len(headers) - 2, 3)]
    blocks = []
    for j in judges:
        grp, pos = None, -1
        for g in triples:
            p = max(x.start() for x in g)
            if p < j and p > pos:
                grp, pos = g, p
        if grp is None:
            continue
        nxt = next((j2 for j2 in judges if j2 > j), len(text))
        seg = text[j:nxt]
        scores = {m.group(2): (int(m.group(1)), float(m.group(3)))
                  for m in SCORE.finditer(seg)}
        if len(scores) != 3:
            print(f"   (incomplete judge block, {len(scores)}/3 scores — skipped)", file=sys.stderr)
            continue
        mapping = {g["label"]: g["model"].split(":", 1)[1] for g in grp}
        marks = {g["label"]: g["mark"] for g in grp}
        bm = BEST.search(seg)
        # best may be a missing label if the Best line sits after the last score group
        blocks.append((mapping, marks, scores, bm.group(1) if bm else None, j))
    return blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--seq", action="append", required=True,
                    help="logfile=mode:test[,test...] in the loop's run order")
    ap.add_argument("--output", default="aggregated.json")
    args = ap.parse_args()
    D = args.outdir.rstrip("/")

    # arms from the result JSONs (model field is the bare id; may carry a
    # date-suffix like deepseek-v4.1-flash:1017)
    arms = set()
    for f in sorted(os.listdir(D)):
        if f.endswith(".json") and re.match(r"^(tools|coding|review)_", f):
            try:
                for r in json.load(open(f"{D}/{f}")).get("results", []):
                    arms.add(r["model"])
            except Exception:
                pass
    mode_tests = []
    seen = set()
    for s in args.seq:
        for mt in parse_seq(s)[1]:
            if mt not in seen:
                seen.add(mt)
                mode_tests.append(mt)

    # collect latest complete judge block per (mode, test), logs in CLI order
    log_blocks = {}
    for s in args.seq:
        logfile, seq = parse_seq(s)
        path = f"{D}/{logfile}"
        if not os.path.exists(path):
            print(f"!! missing {logfile}", file=sys.stderr)
            continue
        blocks = parse_blocks(open(path, encoding="utf-8", errors="replace").read())
        if len(blocks) != len(seq):
            print(f"!! {logfile}: {len(blocks)} complete judge blocks vs {len(seq)} expected "
                  f"tests — zipping the first {min(len(blocks), len(seq))}", file=sys.stderr)
        for (mode, test), blk in zip(seq, blocks):
            mapping, marks, scores, best, _ = blk
            log_blocks[(mode, test)] = {
                "scores": {mapping[l]: sc for l, sc in scores.items()},
                "best": mapping[best] if best else None,
                "labels": {mapping[l]: l for l in mapping},
                "nonconverged": {mapping[l]: (marks[l] == "❌") for l in mapping},
                "source_log": logfile,
            }

    rows, per_test = [], []
    missing = []
    for mode, test in mode_tests:
        blk = log_blocks.get((mode, test))
        if blk is None:
            missing.append(f"{mode}_{test}: no complete judge block")
            continue
        row = {"mode": mode, "test": test, **blk}
        rows.append(row)
        jpath = f"{D}/{mode}_{test}.json"
        if not os.path.exists(jpath):
            missing.append(f"{mode}_{test}: result JSON missing")
            continue
        for r in json.load(open(jpath))["results"]:
            key = r["model"]
            if key not in row["scores"]:
                # header carried provider:model; JSON carries bare id
                key = next((k for k in row["scores"] if k.endswith(r["model"])), r["model"])
            sc = row["scores"].get(key)
            entry = {"test": f"{mode}_{test}", "model": key,
                     "score": sc[1] if sc else None, "rank": sc[0] if sc else None,
                     "judge_best": row["best"] == key,
                     "success": r.get("success"),
                     "tokens_in": r.get("tokens_in"), "tokens_out": r.get("tokens_out"),
                     "elapsed": r.get("elapsed"),
                     "content_chars": len(r.get("content") or ""),
                     "turns": r.get("turns"), "tool_calls": r.get("tool_calls"),
                     "converged": r.get("converged")}
            entry["delivery_fail"] = (r.get("success") is not True) or (entry["content_chars"] < 20)
            per_test.append(entry)
    for m in missing:
        print(f"!! {m}", file=sys.stderr)

    models = sorted({e["model"] for e in per_test})
    stats = {m: {"scores": [], "wins": 0, "by_mode": {}, "dfail": 0,
                 "nonconv": 0, "tok_in": 0, "tok_out": 0} for m in models}
    for e in per_test:
        st = stats[e["model"]]
        if e["score"] is not None:
            st["scores"].append(e["score"])
            st["by_mode"].setdefault(e["test"].split("_")[0], []).append(e["score"])
            if e["rank"] == 1:
                st["wins"] += 1
        if e["delivery_fail"]:
            st["dfail"] += 1
        st["tok_in"] += e["tokens_in"] or 0
        st["tok_out"] += e["tokens_out"] or 0
        if e["test"].split("_")[0] == "tools" and e["converged"] is False:
            st["nonconv"] += 1
    for row in rows:
        for m, bad in row["nonconverged"].items():
            if bad and row["mode"] != "tools":
                stats[m]["nonconv"] += 1

    json.dump({"rows": rows, "per_test": per_test},
              open(f"{D}/{args.output}", "w"), indent=1)
    print(f"{'model':26} {'avg':>5} {'wins':>4} "
          f"{'tools':>6} {'coding':>6} {'review':>6} {'dfail':>5} {'n':>3}")
    for m in models:
        st = stats[m]
        avg = sum(st["scores"]) / len(st["scores"]) if st["scores"] else 0
        bm = {mode: sum(v) / len(v) for mode, v in st["by_mode"].items()}
        print(f"{m:26} {avg:5.2f} {st['wins']:4d} {bm.get('tools', 0):6.2f} "
              f"{bm.get('coding', 0):6.2f} {bm.get('review', 0):6.2f} {st['dfail']:5d} {len(st['scores']):3d}")
    fails = [e for e in per_test if e["delivery_fail"]]
    if fails:
        print("\nDelivery failures (0-timeout shape):")
        for e in fails:
            print(f"  {e['test']:12} {e['model']:26} tok_out={e['tokens_out']} "
                  f"chars={e['content_chars']}")
    print(f"\nSaved {f'{D}/{args.output}'}")


if __name__ == "__main__":
    main()
