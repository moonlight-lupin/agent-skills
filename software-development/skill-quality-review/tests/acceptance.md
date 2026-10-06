# Acceptance test — manual full-tree runs (6 Oct review, second round)

The synthetic fixtures in `test_harness_acceptance.py` lock in the defect shapes
without the real repo. If the pere-toolkit repo is available locally, these two
documented full-tree runs are the acceptance gates the 6 Oct review specified:

## d4e0a2c (pre-fix tree) — expect findings

```
git worktree add /tmp/pd4 d4e0a2c   # from the pere-toolkit clone
python3 scripts/check_calls.py /tmp/pd4
python3 scripts/check_references.py /tmp/pd4
```

Expected (measured 6 Oct 2026, second-round harness):

- `no-recipe` ≥ 30 (measured 36)
- `bid_level(...)` binding failure (missing required: offers, valuation_date)
- exactly 3 `demo-dispatch` (capital_stack.py, fund_fees.py, density_calc.py)
- at least 1 `repo-relative-path` (review-jv-terms inline waterfall.py spans; measured 2)
- check_references: 27 `no-contents-list`, plus 6 orphan + 4 nested

## 8e61771 (v0.11.0, the fixed tree) — expect clean check_calls

```
git worktree add /tmp/pv011 8e61771
python3 scripts/check_calls.py /tmp/pv011    # exit 0
python3 scripts/check_references.py /tmp/pv011
```

Expected: check_calls exit 0 (measured exit 0). check_references still reports the
10 pre-existing pere findings (6 orphan + 4 nested) — those are the real tree, not
harness false positives; the 14 template `no-contents-list` false positives are gone.

Clean up worktrees after the run: `git worktree remove /tmp/pd4 /tmp/pv011 && git
worktree prune`.