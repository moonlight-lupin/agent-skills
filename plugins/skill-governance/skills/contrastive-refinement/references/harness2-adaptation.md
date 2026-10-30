# Harness² Adaptation Notes

Source: https://github.com/google-research/harness2
Paper: arXiv:2610.14224 (Xu et al., 2026). License: Apache-2.0.
Trial commit: `1cfe254` (main, 2026-10-14). Bounded trial run 2026-10-19:
`harness2-demo` passed (2 tasks, 0 failed) on managed Python 3.12.

## What was ported (concepts, not code)

| # | Concept | Upstream form | Ported form |
|---|---------|---------------|-------------|
| 1 | Propose–Probe–Compose | improver model edits a harness tree; probe rollouts on the same task; composition from behavioral contrasts | candidate patches to a skill dir; probe runs via parallel subagents on one fixed task; compose from blind-deliverable contrasts |
| 2 | No-verifier contrast | selection works without ground-truth scores by comparing deliverables from identical inputs | deliverable comparison plus a `<why>` line naming the contrast; baseline preferred when nothing differs |
| 3 | Blinded selection | labels sorted, seeded shuffle from `sha1(task|k|mode)[:12]`, anon ids A..Z, AA.. (`core/selection.py`) | `scripts/contrast.py ids` — same algorithm, same id alphabet |
| 4 | Evidence-required lessons | `EXPERIENCE.md` refuses entries without a cue/lesson/evidence/confidence block (`core/library.py`) | `scripts/contrast.py lesson-check` — exit 1 without a real (non-placeholder, non-template) value for every field; Step 7 requires it |
| 5 | Anti-contamination prompt rule | `BenchPrompts` rejects grader/evaluation/rubric vocabulary ('must describe the WORK') | Step 1 anti-contamination note: probe prompts describe the work only |
| 6 | Fallback on invalid stage | STAGE_ATTEMPTS=2, then inherit the current harness (`core/recursion.py`) | Step 5 fallback rule: one retry, then keep the baseline |

## What was NOT adopted (deliberate)

- **The OpenCode / Codex substrate layer** — targets OpenCode agent trees
  (c1..c8 surface); our surface is Hermes skills/memory/subagents/hooks.
- **The judge and report CLIs** — Vertex-centric grading; we judge by
  deliverable contrast instead.
- **The benchmark runners** (JobBench, LAB, WorkBuddy-Bench) — require
  Google Cloud / Vertex credentials, Docker, Pandoc/Poppler; our probe tasks
  are our own.
- **The per-domain experience library directory** — Mnemosyne and skill
  lesson sections already carry lessons; we add the evidence gate instead of
  a parallel store.
- **Parallel/sequential recursion scaling sweeps** — one standard cycle
  (baseline + INV/DOM candidates + composition probe + selection) is the
  practical budget in this environment; larger budgets wait for demand.

## Syncing with upstream

Concept port — no verbatim files. Re-review the core loop (Propose–Probe–Compose)
when these upstream issues close: #5 (`--bench local` task folders), #4
(`--max-usd` spend limit), plus the first tagged release and bug-fix batch
(#44 judge keeps old grade, #65 resume cache reuse).

## Trial evidence

- Install: `uv venv --python 3.12 .venv && uv pip install -e '.[render]'` —
  core package has zero hard dependencies.
- `harness2-demo` (credential-free, deterministic editors): 2 tasks, 0
  failed, 28 executions, 32 editor calls, both recursion modes ran.
- Source read: `demo.py`, `core/{spec,recursion,library,selection,tree}.py`,
  `substrate/opencode.py`. Leakage guards and blinded-seed selection verified
  in source, not just in the README.
