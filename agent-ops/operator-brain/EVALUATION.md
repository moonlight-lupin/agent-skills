# Operator Brain — Evaluation

Evidence base for the behavioral claim behind this skill. The skill transfers
habits, not capability — these batteries measure whether the habits appear in
real tool-using runs, and on which model tier they show. Conclusions below are
observations from these runs (one run per cell), not proven general laws.

## Method

Each battery holds the subject model, the tasks, and the harness constant and
varies ONLY the injected system text:

| Arm | Injected text |
|-----|---------------|
| none | a one-line neutral operator role |
| v1.1 | installed `operator-brain` v1.1.0, copied byte-for-byte — retrievable at `git show f1156ba:agent-ops/operator-brain/SKILL.md` |
| v1.2.1 | installed `operator-brain` v1.2.1 (10 modules + Two Walls) — this commit |

Every arm receives the same one-line neutral role followed by its injected
text; the none arm receives the role alone.

Judging is blind: final outputs are shuffled into P-labels by an unseeded
shuffle, the arm→label map is sealed (chmod 600) before any scorer prompt
exists, and the judge is a model family different from the subject. The
orchestrator verifies the judge's decisive claims against the raw traces
before accepting any verdict. **Raw traces, rubric texts, judge prompts, and
sealed maps are not published with this repo** — the results below are
historical observations from the operator's runs, not artifacts you can
re-score from this commit. `evals/harness.py` and `evals/tasks/` are included
so the battery-3 setup can be replicated end to end.

The harness runs one OpenRouter chat-completions agent with tools —
web_search, web_fetch, list_dir, read_file, write_file, run_shell — with
file tools restricted to the workspace and the shell environment scrubbed
(but NOT sandboxed — the child runs as the harness user and can read host
files and the parent's original environment via /proc; containerize for
untrusted subjects). It logs full turn-level traces (JSON). Per-turn
tool-call counts are the objective batching metric. Keyless web search
endpoints anomaly-gate by IP, so the harness search pool is Wikipedia +
Hacker News; the pool is disclosed to the subject in the tool description.
`web_fetch` reports the full page length plus a `truncated` flag but feeds
the subject a 4k-char window; any read-depth labels you see in outputs are
the subject's own claims about that window.

## Battery 1 — strong subject (Claude Opus 5, run through `claude -p`)

Tests: narration/recap briefing, partial-evidence deployment report
(3 of 6 checks exist), surgical config edit. These predate this harness and
their tasks are not published here. Blind judge: GLM-5.3-flash.
Every rubric line scored 4/4 on ALL arms — 3 ties, zero regressions. A strong
baseline already sits at rubric ceiling.

## Battery 2 — mid-tier subject (GLM-5.3-flash)

Same 3 test shapes, run through the operator's subagent dispatch (not this
harness). T1 granted web tools with named-tool provenance required. Arms:
none, v1.1 (f1156ba text), and the v1.2.0 candidate text (a round-1 draft,
not the shipped 1.2.1). Blind judge: Opus. In these runs the v1.2.0
candidate won 2, tied 1, lost 0. Separating behaviors: tool provenance (the
candidate arm named tools and marked read-depth per source; the v1.1 arm
claimed "cites only what I actually read" while citing a snippet-only
source) and finding completeness on the surgical edit.

## Battery 3 — weak/cheap subject (thinkingmachines/inkling-small, this harness)

3 arms × 4 tests, one run per cell: research briefing, batchable file
inspection, missing-file honesty, surgical edit. The `:free` OpenRouter slug
was gated in our runs (raw API rejected, "only available on agentic
harnesses"), so the paid sibling of the same family was used.

- **Research deliverable (judged blind, Opus): v1.2.1 16/20 > no-skill 15/20 > v1.1 0/20.**
  The no-skill arm delivered a usable briefing but opened the finished
  message with in-progress narration ("Stage 1: Search"). The v1.2.1 arm led
  with the completed state, tracked 5 stages, marked read-depth per source,
  and ran an explicit self-check.
- **Turn closure (largest margin in these runs): the v1.1 arm produced no
  final message within budget at two different caps (10 and 12 turns of
  one-call-per-turn searching) while both other arms closed in 7 turns.** At
  the same budget, only v1.1 failed to conclude.
- **Missing-file honesty:** all arms refused to fabricate the absent
  `notes_final.md`. Separation was efficiency: v1.2.1 finished in 4 turns /
  5.1s vs 22.9s for no-skill; v1.1 again produced no deliverable in budget.
- **Batching:** in these runs no arm issued parallel tool calls — the v1.2.1
  batching rule did not change behavior on this subject. Recorded as a clean
  negative.
- **Surgical edit:** all arms produced a byte-identical minimal diff
  (rename only; hardcoded key, TODOs, unused import untouched). Tie at ceiling.

## Caveats

One run per cell per battery — direction, not proof. The search-pool
narrowing applies to all arms equally. Judge verdicts were verified: every
decisive claim was reproduced against raw traces.

## Reproducing battery 3

```bash
export OPENROUTER_API_KEY=...
HARNESS_MODEL=thinkingmachines/inkling-small python3 evals/harness.py \
    SKILL.md evals/tasks/T1_research.txt ws1 trace1.json
```

Run from `agent-ops/operator-brain/`; `SKILL.md` is the v1.2.1 arm, the
one-line neutral role is the built-in baseline. `evals/fixtures.py::seed`
builds the workspace described in tasks T2–T4 (refuses to wipe a non-empty
directory unless `FIXTURES_ALLOW_OVERWRITE=1`). `HARNESS_MAX_TURNS` sets the
turn cap (default 12). Deterministic checks (batching counts,
fabricated-content patterns, edit diff) read the JSON traces; subjective
tests go through a blind judge from a different model family — the judging
procedure is not bundled in this repo.
