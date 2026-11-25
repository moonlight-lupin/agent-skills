"""review_budget.py: the review-loop budget gate (v0.3.1)."""
import importlib.util
import json
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / "skills/review-commit/scripts/review_budget.py"
spec = importlib.util.spec_from_file_location("dev_pipeline_review_budget", PATH)
rb = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rb
spec.loader.exec_module(rb)


def run(*args):
    return rb.main([str(a) for a in args])


def round_with(d, reviewer="codex", findings=(), resolve=()):
    """The fix round marks `resolve` ids fixed; the next round confirms them
    RESOLVED, records its new findings, and closes."""
    for fid in resolve:
        assert run("resolve", d, "--id", fid, "--status", "fixed") == 0
    code = run("round", d)
    if code:
        return code
    assert run("dispatch", d, "--reviewer", reviewer) == 0
    for fid in resolve:
        assert run("resolve", d, "--id", fid) == 0
    for fid, sev, cls, *flags in findings:
        assert run("finding", d, "--id", fid, "--severity", sev, "--class", cls, *flags) == 0
    assert run("close", d) == 0
    return 0


def ledger(d):
    return json.loads((Path(d) / "budget.json").read_text(encoding="utf-8"))


def test_t2_allows_r1_plus_two_then_refuses_until_user_extends(tmp_path):
    d = tmp_path / "loop"
    assert run("init", d, "--tier", "T2") == 0
    assert round_with(d, findings=[("a1", "MAJOR", "auth"), ("a2", "MAJOR", "io"),
                                   ("a3", "BLOCKING", "money")]) == 0
    assert round_with(d, findings=[("b1", "MAJOR", "paging")], resolve=["a1", "a2"]) == 0
    assert round_with(d, findings=[], resolve=["b1"]) == 0  # a3 still open: 2 -> 1
    assert run("round", d) == 2, "a 4th round at T2 must be refused while MAJORs are open"
    assert run("status", d) == 20
    assert run("extend", d, "--by", "1", "--reason", "fix c1 only", "--approved-by", "user") == 0
    assert run("round", d) == 0


def test_every_dispatch_needs_an_open_round(tmp_path):
    d = tmp_path / "loop"
    run("init", d, "--tier", "T3")
    assert run("dispatch", d, "--reviewer", "codex") == 5
    assert round_with(d, findings=[("a1", "BLOCKING", "x")]) == 0
    # A "fix review" by one reviewer after the round closed is still a round.
    assert run("dispatch", d, "--reviewer", "codex") == 5


def test_test_only_capped_at_minor_unless_sole_coverage(tmp_path):
    d = tmp_path / "loop"
    run("init", d, "--tier", "T2")
    run("round", d)
    run("finding", d, "--id", "t1", "--severity", "MAJOR", "--class", "test-month", "--test-only")
    run("finding", d, "--id", "t2", "--severity", "MAJOR", "--class", "money", "--test-only", "--sole-coverage")
    run("finding", d, "--id", "u1", "--severity", "BLOCKING", "--class", "null", "--unreachable")
    f = ledger(d)["findings"]
    assert f["t1"]["severity"] == "MINOR" and f["t1"]["reviewer_severity"] == "MAJOR"
    assert f["t2"]["severity"] == "MAJOR"
    assert f["u1"]["severity"] == "NIT"


def test_minor_only_rounds_ship_and_refuse_another_round(tmp_path):
    d = tmp_path / "loop"
    run("init", d, "--tier", "T3")
    assert round_with(d, findings=[("m1", "MINOR", "style"), ("t1", "MAJOR", "tests", "--test-only")]) == 0
    assert run("status", d) == 0
    assert run("round", d) == 4


def test_same_class_redesign_then_ask_user(tmp_path):
    d = tmp_path / "loop"
    run("init", d, "--tier", "T3")
    round_with(d, findings=[("r1", "BLOCKING", "revision-state"), ("x1", "MAJOR", "x"),
                            ("x2", "MAJOR", "y")])
    round_with(d, findings=[("r2", "MAJOR", "revision-state")], resolve=["r1", "x1", "x2"])
    assert run("status", d) == 11, "second same-class finding -> REDESIGN"
    round_with(d, findings=[("r3", "MAJOR", "revision-state")], resolve=["r2"])
    assert run("status", d) == 20
    assert run("round", d) == 3, "third same-class finding blocks the next round"
    run("extend", d, "--by", "0", "--reason", "user chose redesign", "--approved-by", "user")
    assert run("round", d) == 0


def test_fixed_awaits_confirmation_so_the_confirm_round_is_allowed(tmp_path):
    d = tmp_path / "loop"
    run("init", d, "--tier", "T1")
    round_with(d, findings=[("a", "MAJOR", "c1")])
    run("resolve", d, "--id", "a", "--status", "fixed")
    assert run("status", d) == 10, "a claimed fix is not a confirmed one"
    assert run("round", d) == 0


def test_no_progress_stops(tmp_path):
    d = tmp_path / "loop"
    run("init", d, "--tier", "T3")
    round_with(d, findings=[("a", "MAJOR", "c1")])
    round_with(d, findings=[("b", "MAJOR", "c2")], resolve=[])
    assert run("status", d) == 20
    assert run("round", d) == 3


def test_gate_gets_one_regate_regardless_of_tier(tmp_path):
    d = tmp_path / "gate"
    run("init", d, "--tier", "T3", "--kind", "gate")
    assert round_with(d, findings=[("g1", "BLOCKING", "a")]) == 0
    assert round_with(d, findings=[("g2", "MAJOR", "b")], resolve=["g1"]) == 0
    assert run("round", d) == 2


def test_status_line_for_briefs(tmp_path, capsys):
    d = tmp_path / "loop"
    run("init", d, "--tier", "T2")
    run("round", d)
    capsys.readouterr()
    run("status", d, "--line")
    assert "round 1 of 3" in capsys.readouterr().out
