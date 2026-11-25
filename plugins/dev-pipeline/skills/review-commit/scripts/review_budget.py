#!/usr/bin/env python3
"""Review-loop budget ledger: counts rounds and findings, and refuses rounds
the confirm-round protocol does not allow.

Every reviewer dispatch belongs to a round, and every round after R1 is a
confirm round, whatever the brief calls it (fix review, re-close, re-gate,
verification pass). The orchestrator runs this script BEFORE every reviewer
dispatch; it is the loop's budget gate without a hook (same idea as
loop_plan_check.py --gate). Rules enforced (references/confirm-round-protocol.md):

- budget: T0 = 0, T1 = 1, T2 = 2, T3 = 3 confirm rounds after R1; a gate loop
  gets exactly one re-gate. Past the budget, `round` refuses until the user's
  decision is recorded with `extend`.
- severity caps: a test-only finding is at most MINOR unless the test is the
  sole coverage of a BLOCKING/MAJOR behavior; an unreachable scenario is NIT.
- same-class stop: the 2nd BLOCKING/MAJOR finding of one class means REDESIGN
  (one class-level brief); the 3rd means ASK-USER.
- no-progress stop: open BLOCKING+MAJOR did not fall from the previous round.
- ship: nothing BLOCKING/MAJOR open or awaiting confirmation after a closed
  round -> no more rounds.

Finding lifecycle: `finding` (open) -> `resolve --status fixed` after the fix
round -> the next confirm round's verdict: `resolve` (RESOLVED) or
`resolve --status reopened` (NOT-RESOLVED).

Ledger: <dir>/budget.json (one per loop; a gate gets its own dir).
Exit codes: 0 ok/SHIP, 2 refused: budget spent, 3 refused: user decision
needed, 4 refused: nothing open (ship), 5 usage/state error.
`status` exits 0 SHIP, 10 CONTINUE, 11 REDESIGN, 20 ASK-USER.
"""
import argparse
import datetime as _dt
import json
import os
import sys

SCHEMA = "review-budget.v1"
TIER_BUDGET = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
GATE_BUDGET = 1
SEVERITIES = ["NIT", "MINOR", "MAJOR", "BLOCKING"]
LOOP_OPEN = ("BLOCKING", "MAJOR")


def _now():
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _path(d):
    return os.path.join(d, "budget.json")


def load(d):
    p = _path(d)
    if not os.path.exists(p):
        raise SystemExit(f"no ledger at {p} - run `init` first")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def save(d, led):
    os.makedirs(d, exist_ok=True)
    tmp = _path(d) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(led, fh, indent=2)
    os.replace(tmp, _path(d))


def allowed_rounds(led):
    return 1 + led["budget"] + sum(e["by"] for e in led["extensions"])


def ack_round(led):
    return max([e["at_round"] for e in led["extensions"]], default=0)


def open_bm(led):
    """BLOCKING/MAJOR not yet confirmed closed: `open`, or `fixed` (claimed by a
    fix round, awaiting the next confirm round's verdict)."""
    return [f for f in led["findings"].values()
            if f["status"] in ("open", "fixed") and f["severity"] in LOOP_OPEN]


def class_counts(led):
    counts = {}
    for f in led["findings"].values():
        if f["severity"] in LOOP_OPEN:
            c = counts.setdefault(f["class"], {"n": 0, "last_round": 0})
            c["n"] += 1
            c["last_round"] = max(c["last_round"], f["round"])
    return counts


def evaluate(led):
    """Return (verdict, reasons). Verdicts: SHIP, CONTINUE, REDESIGN, ASK-USER."""
    rounds = led["rounds"]
    closed = [r for r in rounds if r.get("closed_at")]
    ack = ack_round(led)
    reasons = []
    if closed and not open_bm(led) and len(closed) == len(rounds):
        return "SHIP", ["no BLOCKING/MAJOR open after the last closed round"]
    for cls, c in class_counts(led).items():
        if c["n"] >= 3 and c["last_round"] > ack:
            reasons.append(f"same-class stop: class '{cls}' has {c['n']} BLOCKING/MAJOR findings - ask the user")
    if len(closed) >= 2 and closed[-1]["n"] > ack:
        prev, last = closed[-2]["open_bm_at_close"], closed[-1]["open_bm_at_close"]
        if last >= prev and last > 0:
            reasons.append(f"no-progress stop: open BLOCKING+MAJOR {prev} -> {last}")
    if len(rounds) >= allowed_rounds(led) and open_bm(led):
        reasons.append(f"budget spent: {len(rounds)} of {allowed_rounds(led)} rounds used with "
                       f"{len(open_bm(led))} BLOCKING/MAJOR open - NOT SHIP; ask the user")
    if reasons:
        return "ASK-USER", reasons
    redesign = [cls for cls, c in class_counts(led).items() if c["n"] == 2 and c["last_round"] > ack]
    if redesign:
        return "REDESIGN", [f"same-class: class '{cls}' has 2 BLOCKING/MAJOR findings - next brief is ONE "
                            f"class-level redesign, not another instance patch" for cls in redesign]
    return "CONTINUE", [f"{len(open_bm(led))} BLOCKING/MAJOR open; "
                        f"{allowed_rounds(led) - len(rounds)} round(s) left"]


def round_line(led):
    n = len(led["rounds"])
    label = "R1" if n <= 1 else f"confirm round {n - 1}"
    return (f"{led['kind']} {led['tier']}: this is round {n} of {allowed_rounds(led)} "
            f"({label}; R1 + {allowed_rounds(led) - 1} allowed)")


def cmd_init(a):
    p = _path(a.dir)
    if os.path.exists(p) and not a.force:
        print(f"ledger exists at {p} (use --force to replace)")
        return 5
    led = {"schema": SCHEMA, "tier": a.tier, "kind": a.kind,
           "budget": GATE_BUDGET if a.kind == "gate" else TIER_BUDGET[a.tier],
           "created_at": _now(), "rounds": [], "findings": {}, "extensions": []}
    save(a.dir, led)
    print(f"initialised {a.kind} ledger, {a.tier}: R1 + {led['budget']} round(s)")
    return 0


def cmd_round(a):
    led = load(a.dir)
    if led["rounds"] and not led["rounds"][-1].get("closed_at"):
        print(f"round {led['rounds'][-1]['n']} is still open - close it first")
        return 5
    if led["rounds"]:
        verdict, reasons = evaluate(led)
        if verdict == "SHIP":
            print("REFUSED: nothing BLOCKING/MAJOR is open - SHIP; don't run another round")
            return 4
        if verdict == "ASK-USER":
            print("REFUSED: " + "; ".join(reasons))
            print("Record the user's decision with `extend` before another round.")
            return 2 if any(r.startswith("budget spent") for r in reasons) else 3
        if verdict == "REDESIGN":
            print("NOTE: " + "; ".join(reasons))
    n = len(led["rounds"]) + 1
    led["rounds"].append({"n": n, "label": a.label or ("R1" if n == 1 else f"R{n}"),
                          "opened_at": _now(), "reviewers": [], "scope": a.scope})
    save(a.dir, led)
    print(round_line(led))
    return 0


def cmd_dispatch(a):
    led = load(a.dir)
    if not led["rounds"] or led["rounds"][-1].get("closed_at"):
        print("REFUSED: no open round - every reviewer dispatch needs `round` first "
              "(a fix review or re-close IS a confirm round)")
        return 5
    r = led["rounds"][-1]
    if a.reviewer not in r["reviewers"]:
        r["reviewers"].append(a.reviewer)
    save(a.dir, led)
    print(f"round {r['n']}: dispatched {a.reviewer}")
    return 0


def cmd_close(a):
    led = load(a.dir)
    if not led["rounds"] or led["rounds"][-1].get("closed_at"):
        print("no open round to close")
        return 5
    r = led["rounds"][-1]
    if not r["reviewers"]:
        print("REFUSED: round has no dispatched reviewer")
        return 5
    r["closed_at"] = _now()
    r["open_bm_at_close"] = len(open_bm(led))
    save(a.dir, led)
    verdict, reasons = evaluate(led)
    print(f"round {r['n']} closed: {verdict} - " + "; ".join(reasons))
    return 0


def cmd_finding(a):
    led = load(a.dir)
    if not led["rounds"]:
        print("no round yet - findings belong to a round")
        return 5
    sev, note = a.severity, []
    if a.unreachable:
        sev, note = "NIT", ["unreachable scenario -> NIT"]
    elif a.test_only and not a.sole_coverage and SEVERITIES.index(sev) > SEVERITIES.index("MINOR"):
        sev, note = "MINOR", ["test-only -> capped at MINOR"]
    led["findings"][a.id] = {"severity": sev, "reviewer_severity": a.severity, "class": a.cls,
                             "round": led["rounds"][-1]["n"], "status": "open",
                             "test_only": a.test_only, "unreachable": a.unreachable}
    save(a.dir, led)
    count = class_counts(led).get(a.cls, {"n": 0})["n"]
    loops = "keeps the loop open" if sev in LOOP_OPEN else "deferred list - does not keep the loop open"
    print(f"{a.id}: {sev} ({loops}); class '{a.cls}' now has {count} BLOCKING/MAJOR"
          + (f" [{'; '.join(note)}]" if note else ""))
    return 0


def cmd_resolve(a):
    led = load(a.dir)
    if a.id not in led["findings"]:
        print(f"unknown finding {a.id}")
        return 5
    led["findings"][a.id]["status"] = "open" if a.status == "reopened" else a.status
    save(a.dir, led)
    print(f"{a.id}: {a.status}")
    return 0


def cmd_extend(a):
    led = load(a.dir)
    led["extensions"].append({"by": a.by, "reason": a.reason, "approved_by": a.approved_by,
                              "at_round": len(led["rounds"]), "at": _now()})
    save(a.dir, led)
    print(f"extended by {a.by} round(s), approved by {a.approved_by}: {a.reason}")
    return 0


def cmd_status(a):
    led = load(a.dir)
    verdict, reasons = evaluate(led)
    if a.line:
        print(round_line(led))
        return 0
    if a.json:
        print(json.dumps({"verdict": verdict, "reasons": reasons, "rounds": len(led["rounds"]),
                          "allowed_rounds": allowed_rounds(led),
                          "open_blocking_major": [k for k, f in led["findings"].items()
                                                  if f["status"] in ("open", "fixed")
                                                  and f["severity"] in LOOP_OPEN],
                          "classes": class_counts(led)}, indent=2))
    else:
        print(round_line(led))
        print(f"verdict: {verdict}")
        for r in reasons:
            print(f"  - {r}")
    return {"SHIP": 0, "CONTINUE": 10, "REDESIGN": 11, "ASK-USER": 20}[verdict]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init"); p.add_argument("dir")
    p.add_argument("--tier", choices=sorted(TIER_BUDGET), required=True)
    p.add_argument("--kind", choices=["loop", "gate"], default="loop")
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("round"); p.add_argument("dir"); p.add_argument("--label")
    p.add_argument("--scope", help="the diff this round reviews"); p.set_defaults(fn=cmd_round)
    p = sub.add_parser("dispatch"); p.add_argument("dir"); p.add_argument("--reviewer", required=True)
    p.set_defaults(fn=cmd_dispatch)
    p = sub.add_parser("close"); p.add_argument("dir"); p.set_defaults(fn=cmd_close)
    p = sub.add_parser("finding"); p.add_argument("dir"); p.add_argument("--id", required=True)
    p.add_argument("--severity", choices=SEVERITIES, required=True)
    p.add_argument("--class", dest="cls", required=True, help="mechanism / input family / invariant")
    p.add_argument("--test-only", action="store_true")
    p.add_argument("--sole-coverage", action="store_true",
                   help="the test is the only coverage of a BLOCKING/MAJOR behavior")
    p.add_argument("--unreachable", action="store_true"); p.set_defaults(fn=cmd_finding)
    p = sub.add_parser("resolve"); p.add_argument("dir"); p.add_argument("--id", required=True)
    p.add_argument("--status", choices=["fixed", "resolved", "reopened", "deferred", "accepted"],
                   default="resolved",
                   help="fixed = fix landed, awaiting confirmation; resolved = a confirm round "
                        "verdict says RESOLVED; reopened = NOT-RESOLVED; accepted = user accepted the risk")
    p.set_defaults(fn=cmd_resolve)
    p = sub.add_parser("extend"); p.add_argument("dir"); p.add_argument("--by", type=int, default=1)
    p.add_argument("--reason", required=True); p.add_argument("--approved-by", required=True)
    p.set_defaults(fn=cmd_extend)
    p = sub.add_parser("status"); p.add_argument("dir"); p.add_argument("--json", action="store_true")
    p.add_argument("--line", action="store_true", help="print only the round line for briefs")
    p.set_defaults(fn=cmd_status)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
