# Model Behavior Findings

## Contents

- Head-to-head: Solar Pro 4 vs GLM-5.3-flash (2026-09-02, 8-test suite)
- DeepSeek V4.1 Flash vs GLM-5.3-Flash (6-test battery)
- Upstage Solar Pro 4 (direct API)
- Models Tested
- GLM 5.2 (ollama-cloud) — Detailed Profile
- MiniMax M3 (ollama-cloud) — Detailed Profile
- tencent/hy3:free (openrouter) — Detailed Profile
- OpenRouter Free-Tier Rate Limiting
- Kimi K3 (openrouter) — Detailed Profile\n\nOverall: 9.5/10 on test A, 8.5/10 on test C. Top performer on efficiency.\n\nTested 2026-07-17. 2.8T param MoE, 1M context, $3/M input / $15/M output.\n\n### Strengths\n- Efficient tool calling: Converged in 3 turns (35.6s) on test A —\n  searched docs.python.org directly, extracted, answered. No wasted turns.\n- Correct answers: Identified Python 3.14 + PEP 750 (t-strings) + PEP 649/749\n  (deferred annotations) from official docs.\n- Token efficiency: 3,341 tokens in / 562 tokens out — 2.7× fewer tokens\n  than GLM-5.2 on the same test.\n- Test C (reverse proxy): Converged in 3 turns (38.4s), 2,600 tok in /\n  744 tok out. Recommended Caddy with automatic HTTPS as key feature.\n  Again most efficient — 4× fewer tokens than GLM-5.2.\n\n### Weaknesses\n- Answer depth: On test C, the answer was correct but thinner than\n  Cursor Grok 4.5 High (no comparison table, fewer citations). Wins on\n  efficiency, not on answer richness.\n\n### Best for\nTool-calling tasks where efficiency matters. Strong first choice for\nresearch lookups. When answer quality/structure matters more than token\n  cost, Cursor Grok 4.5 High may produce better-formatted results.
- GLM 5.2 (ollama-cloud) — Test A Update (2026-07-17)
- Meta Muse Spark 1.1 (openrouter) — Geofenced
- CLI Model Integration Pattern (2026-07-17)
- GPT-5.5 via Codex CLI — Detailed Profile\n\nOverall: 9.0/10 on test A, 8.5/10 on test C. Thorough but expensive.\n\nTested 2026-07-17 via Codex CLI v0.135.0. Note: gpt-5.6-sol not supported\nby this Codex version — used gpt-5.5 as fallback.\n\n### Strengths\n- Thorough research: On test C, cited 5+ sources with links (caddyserver.com,\n  NPM GitHub, Traefik docs, homelab comparison). Compared NPM, Traefik, Caddy\n  with clear tradeoffs.\n- Correct answers: Both tests A and C correct. Noted patch version (3.14.6)\n  that other models missed on test A. Picked free-threaded mode as #1 feature\n  on test A (valid but less commonly cited).\n\n### Weaknesses\n- Massive token overhead: 37,450 tokens on test A, 50,799 on test C.\n  This is Codex CLI overhead (verbose tool-calling format), not the model itself.\n  ~10× more tokens than Kimi K3 for similar quality.\n- Model version lag: Codex CLI v0.135 doesn't support gpt-5.6-sol.\n  Must use gpt-5.5 as fallback until Codex is upgraded.\n\n### Best for\nDeep research where token cost doesn't matter and citations are important.\nUse when you have Codex subscription and want thorough, well-sourced answers.\n\n## Cursor Grok 4.5 High via Cursor CLI — Detailed Profile\n\nOverall: 9.0/10 on test C (tool calling). Best answer structure.\n\nTested 2026-07-17 via Cursor CLI (`agent` binary). Required `--force` flag\nfor web access in headless mode.\n\n### Strengths\n- Best structured answer: On test C, produced a comparison table\n  (\"when to pick something else\"), Caddyfile code example, and clear decision\n  framework. Most useful answer for someone making a real decision.\n- Diverse sources: Cited 5 sources (selfhosting.sh, Big Iron, How-To Geek,\n  CloudHostReview, TechFuel) — more diverse than other models.\n- Good detail: Mentioned `annotationlib` VALUE/FORWARDREF/STRING formats\n  (test A), 20-40MB idle RAM for Caddy (test C). Technical depth.\n- Token efficient: ~8,500 tok in / ~1,200 tok out — between Kimi K3 and\n  GLM-5.2. Good balance of depth and efficiency.\n\n### Weaknesses\n- Web access flaky in headless: Required 3 attempts to get web working.\n  `--trust` alone → blocked, `--trust --sandbox disabled` → blocked,\n  `--force` → works. Must always use `--force` for web-dependent tasks.\n- First two attempts failed: On test A, the first run produced no answer\n  (\"web search and fetching python.org were blocked\"). Only succeeded on\n  third attempt with `--force`.\n\n### Best for\nAnswer quality / structure. When the user needs a well-formatted, actionable\nanswer with comparison tables and code examples. Best used through Cursor CLI\nwith `--force --sandbox disabled --model "cursor-grok-4.5-high"`.
- max_turns Calibration
- Judge Model Notes
- Coding & Code Review Tests (2026-07-17)
- Kimi K3 Rate Limiting (2026-07-17)
- 2026-10-14: mistral-large-4 vs glm-5.3 vs kimi-k3 (Ollama Cloud, glm-5.3-flash judge, 6 tests: J M O H6 A S1)
- 2026-10-14: + gemini-4-argon (OpenRouter, $0.12 for 6 tests) — 4-way re-judge of same responses
- compare.py Single-Model Limitation
- Vote History Location
- Muse Spark Open findings (24-test battery, 2026-10-16)
- Nemotron 3.5 Super VL findings (24-test battery, 2026-10-16)
- Battery harness + judge convention (2026-10-16)

## Head-to-head: Solar Pro 4 vs GLM-5.3-flash (2026-09-02, 8-test suite)

Same harness (DonSeTch search, 20-turn tools cap, 420s per-model timeout).
Functional verification for coding; planted-issue ground truth for review.

| Test | Solar Pro 4 | GLM-5.3-flash |
|---|---|---|
| tools H1 (open research) | ❌ no convergence, 20 turns/22 calls | ✅ 17 turns/25 calls, correct verdict |
| tools H2 (verify official) | ✅ 7 turns/7 calls, correct | ✅ 5 turns/7 calls, correct (dist/index.json) |
| tools S4 (sandbox loop) | ✅ 4 turns/3 calls | ✅ 3 turns/2 calls |
| coding H3 (TTL+LRU) | ✅ ALL functional tests pass | ❌ RuntimeError: OrderedDict.peekitem doesn't exist |
| coding H4 (token bucket) | ✅ ALL pass (burst, refill, threads) | ✅ ALL pass (burst, refill, threads) |
| review H5/H6/H7 | 11/11 planted issues | 11/11 planted issues |
| Wall time (suite) | 219s | 656s |
| Tokens | 160K in / 10K out | 145K in / 70K out |
| Est cost (list) | $0.06 | free |

- GLM-5.3-flash H3 bug: `_evict_locked` calls `self._entries.peekitem(last=False)`
  — `OrderedDict` has no `peekitem`. Unrunnable code shipped confidently.
- GLM-5.3-flash timed out at harness default 120s on H3/H5 (thinking model,
  slow on hard one-shots); completed at --timeout 420 (173s, 224s). Harness
  timeout for thinking models should be 300s+.
- Solar Pro 4 H1 non-converged this run (converged in the earlier solo run) —
  convergence on long research chains is inconsistent run-to-run.
- Solar Pro 4 is 3x faster wall-clock and 7x fewer output tokens; answers are
  denser (good) but its 24% hallucination rate (AA finding) is the tradeoff.

## DeepSeek V4.1 Flash vs GLM-5.3-Flash (6-test battery)

Run on Ollama Cloud via `model-compare`, GLM judge, scored 0-10 x 6 tests
(max 60): GLM-5.3-flash 57.5, DeepSeek V4.1 flash 57.0, DeepSeek V4.0 (0731) 50.0.

- GLM-5.3-flash wins by a hair, mainly from code-review precision.
- V4.1 is the speed and correctness upgrade over V4.0. V4.0's coding failure
  was an import bug (`Optional` used without being imported) that crashed the
  module at import; V4.1 passed all runtime checks.
- All three converged on H3 — a "failure" noted there was a harness artifact,
  not a model error. Verify against the trace before scoring a non-convergence
  against a model.
- Beta model IDs on Ollama Cloud can expire within days; a beta winner is not
  a routing candidate until it is stable.

## Upstage Solar Pro 4 (direct API)

Solo run (8 tests: H1, H2, S4 tools; H3, H4 coding; H5, H6, H7 review), no judge,
functional verification instead. Model reports `solar-pro4-260806`, cutoff Feb 2026.

- **Coding (strong)**: H3 TTL+LRU cache and H4 token bucket both passed all
  functional tests (thread safety, injectable clock, TTL expiry, LRU eviction)
  after adjusting for API-shape differences (`put(key, value, ttl_seconds)`
  required arg; `tokens_per_second=0` rejected by validation). Type hints,
  docstrings, thread-safe (RLock / atomic check-and-consume). ~4.5KB each.
- **Code review (strong)**: caught ALL 11 planted issues across H5 (4/4),
  H6 (5/5), H7 (2/2) with severity classification and concrete fixes. Well
  structured (severity-ordered). No false positives observed on quick read.
- **Tool calling — research chains (mixed; search quality is a confounder)**:
  Initial run (SearXNG backend returning off-topic junk): H1 and H2 both hit
  the turn cap with 0 synthesis. After switching the harness `web_search` to
  DonSeTch CLI (clean, reranked results): **H1 converged** — 10 turns, 12 tool
  calls, high-quality answer ranking source authority (docs.python.org >
  PEPs > blogs), correct PEP 779/Phase-II verdict. **H2 still failed at 20
  turns**: the model obtained the correct data at turn 11 (endoflife.date API
  via run_python: Node v26, EOL 2029-04-30) but kept issuing verification
  calls (curl through run_python) and never answered. Pattern: weak
  "stop condition" — it under-synthesizes when tool results are messy
  (harness web_extract returns crude HTML for JS-heavy pages like
  nodejs.org) and over-verifies when it already has enough. H2-style
  "verify against the official source" tasks are its worst case.
- **Tool calling — sandbox (S4, PASS)**: write→run→verify loop converged in
  4 turns / 3 tool calls. Correct linked-list reversal with verification.
  Will happily use run_python+curl for fetching when web_extract disappoints.
- **Harness fix shipped with these findings**: compare.py `execute_web_search`
  now tries DonSeTch CLI first (`donsetch search --json`), then SearXNG, then
  DDGS. Also fixed `dir()` → `locals()` so `--max-turns` overrides actually
  apply (dir() was always truthy at module scope, silently ignoring overrides).
- **Speed (very fast)**: whole 8-test suite in ~2 min; tool turns ~1s each;
  coding/review one-shots 8–18s.
- **Cost (very cheap)**: ~103K tokens in, 1.6K out across the suite ≈ $0.003.
  List price $0.03/M prompt tokens (OpenRouter listing, 2026-09-02).

Verdict: strong offline model (coding, review — 11/11 planted review bugs
caught, both hard coding tests pass functionally). Research chains: usable on
open research (H1) once search quality is fixed, but unreliable on
verify-heavy tasks (H2 non-convergence with correct data already in context).
Not yet dependable for agentic loops without a turn-budget guardrail.

---

# Historical (2026-07-07 head-to-heads)

Observed model behavior from 16 head-to-head comparisons run on 2026-07-07.
These are empirical findings from specific test runs, not benchmarks —
individual results may vary. Use as calibration data, not definitive rankings.

## Models Tested

| Model | Provider | Cost | Tool calling | Notes |
|---|---|---|---|---|
| `glm-5.2` | Ollama Cloud | Free | ✅ Excellent | Strong all-rounder |
| `minimax-m3` | Ollama Cloud | Free | ✅ Good | Strong researcher, weaker at code review |
| `tencent/hy3:free` | OpenRouter | Free tier | ⚠️ Poor | Searches but can't synthesize |
| `poolside/laguna-xs-2.1:free` | OpenRouter | Free tier | ❌ Invalid ID | Model not found (HTTP 400) |
| `poolside/laguna-m.1:free` | OpenRouter | Free tier | ❌ Rate-limited | HTTP 429 after 2 calls |

## GLM 5.2 (ollama-cloud) — Detailed Profile

**Overall: 8.1 avg across 12 tests. Best all-rounder on free tier.**

### Strengths
- **Coding** (avg 8.9): Clean code, modern type hints (`ParamSpec`), concise
  explanations. Won 2/4 coding tests outright, tied or close in the rest.
  Best at tasks requiring precision (merge sort fix: 9.5, retry decorator: 9.0).
- **Code review** (avg 8.5): Low false-positive rate. Stays grounded in actual
  code — doesn't hallucinate bugs that aren't there. Correctly identified
  clean code as clean (test P: 8.0 vs MiniMax's 5.5 for inflating severities).
- **Tool calling — factual lookup** (test B: 8.5): Goes straight to
  authoritative source, converges fast (4 turns, 3 tool calls).

### Weaknesses
- **Tool calling — bad data derails it**: On test A, a garbled binary response
  from python.org/downloads sent GLM into a death spiral of re-extraction
  attempts. It never recovered and scored 1.0. This happened once across 4
  tool tests — not systematic, but notable.
- **Truncation**: With max_tokens=4096, the LRU cache code (test E) was cut off
  mid-decorator. Fixed by raising to 8192, but the model generates a LOT of
  output — watch for truncation on code-heavy tasks.
- **Tool calling — research synthesis** (test A round 1: 1.0): Can over-research
  when the first extraction fails, burning turns on re-extraction instead of
  trying a different URL.

### Best for
Code generation, code review, factual lookups, tasks requiring precision and
low false-positive rates.

## MiniMax M3 (ollama-cloud) — Detailed Profile

**Overall: 7.7 avg across 12 tests. Strong researcher, weaker at code review.**

### Strengths
- **Tool calling — research synthesis** (test A: 9.5, test C: 8.0): Efficient
  tool selection, goes straight to authoritative sources. Converges in fewer
  turns than GLM on research tasks (test C: 5 turns vs GLM's 6).
- **Coding — structured output** (test J: 8.5, test K: 9.5): Produces
  well-structured code with dataclasses, complexity tables, and both sync/async
  entry points. `__slots__` for memory efficiency. Good at tasks requiring
  architectural decisions.
- **Code review — thorough** (test O: 9.0): Finds more issues, includes attack
  examples, PEP references, priority recommendations. When the code genuinely
  has many issues, MiniMax's thoroughness wins.

### Weaknesses
- **Code review — high false-positive rate** (test P: 5.5): Inflates
  severities on clean code. Labeled missing input validation as "Critical/High"
  when the code had no planted bugs. Hallucinated a "negative values are always
  wrong" logic bug (discounts/refunds exist). This is dangerous for production
  code review where false positives erode trust.
- **Code review — hallucinated runtime errors** (test Q: 7.5): Claimed
  `RuntimeError: dictionary changed size during iteration` would occur, but
  the code had no iteration. Fabricating errors that can't happen is worse
  than missing issues.
- **Code review — over-speculation** (test R: 8.0): Found 21 issues for a
  10-line snippet. Many were valid domain concerns (authentication, currency
  mismatch) but not evident from the code. Noisy and less practical than GLM's
  focused 7-issue review.
- **Tool calling — convergence failure** (test B: 4.0): Found the right repo
  and even tried the GitHub API endpoint (clever!), but kept searching for
  confirmation instead of synthesizing the answer. Hit max turns.

### Best for
Research-heavy tool calling, brainstorming code architecture, thorough (but
noisy) code review where you want every possible issue flagged.

## tencent/hy3:free (openrouter) — Detailed Profile

**Overall: 0.5 avg across 4 tool-calling tests. Not viable for tool calling.**

### Pattern across 4 rounds
| Round | Test | Turns | Converged? | Final output |
|---|---|---|---|---|
| 1 (5-cap) | E | 5 | ❌ Max turns | — |
| 2 (10-cap) | E | 8 | ✅ | **Empty** |
| 3 (10-cap) | E | 8 | ✅ | **Empty** |
| 4 (10-cap) | A | 5 | ❌ Max turns | — |

### Key finding
HY3 does the research phase well — good search queries, picks relevant URLs,
even tries `r.jina.ai` to bypass 403s. But it **consistently fails to
synthesize**: either hits the turn cap without producing a final answer, or
converges with completely empty output. This is a systematic issue, not a
one-off failure.

Likely causes: very low `max_tokens` on the free tier, or the model's
generation step is broken when given a large tool-call context.

### Recommendation
Do not use HY3 free tier for tool-calling comparisons. It may work in simple
mode (untested).

## OpenRouter Free-Tier Rate Limiting

`poolside/laguna-m.1:free` hit HTTP 429 after just 2 tool calls. OpenRouter
free-tier models (with `:free` suffix) are aggressively rate-limited — expect
1-3 calls before throttling. This makes them unsuitable for tool-calling
mode (which needs 3-10 calls per model per test).

### Workaround
- Use Ollama Cloud for free-tier model testing — no rate limits observed across
  16+ test runs
- If you must use OpenRouter free-tier models, stick to `--mode simple` (1 call
  per model)
- `COMPARE_CONFIRM_PAID=1` env var bypasses the cost gate for all OpenRouter
  models, including `:free` suffix ones that cost $0

## Kimi K3 (openrouter) — Detailed Profile\n\n**Overall: 9.5/10 on test A, 8.5/10 on test C. Top performer on efficiency.**\n\nTested 2026-07-17. 2.8T param MoE, 1M context, $3/M input / $15/M output.\n\n### Strengths\n- **Efficient tool calling**: Converged in 3 turns (35.6s) on test A —\n  searched docs.python.org directly, extracted, answered. No wasted turns.\n- **Correct answers**: Identified Python 3.14 + PEP 750 (t-strings) + PEP 649/749\n  (deferred annotations) from official docs.\n- **Token efficiency**: 3,341 tokens in / 562 tokens out — 2.7× fewer tokens\n  than GLM-5.2 on the same test.\n- **Test C (reverse proxy)**: Converged in 3 turns (38.4s), 2,600 tok in /\n  744 tok out. Recommended Caddy with automatic HTTPS as key feature.\n  Again most efficient — 4× fewer tokens than GLM-5.2.\n\n### Weaknesses\n- **Answer depth**: On test C, the answer was correct but thinner than\n  Cursor Grok 4.5 High (no comparison table, fewer citations). Wins on\n  efficiency, not on answer richness.\n\n### Best for\nTool-calling tasks where efficiency matters. Strong first choice for\nresearch lookups. When answer quality/structure matters more than token\n  cost, Cursor Grok 4.5 High may produce better-formatted results.

## GLM 5.2 (ollama-cloud) — Test A Update (2026-07-17)

On re-test with max_turns=10, GLM-5.2 converged in 6 turns (34.1s) on test A.
Correct answer (Python 3.14, same 2 features) but took a detour through blog
posts before landing on official docs. 9,023 tokens in / 1,052 tokens out.
Judge scored it 9.0/10 vs Kimi K3's 9.5/10 — same quality, less efficient.

## Meta Muse Spark 1.1 (openrouter) — Geofenced

**HTTP 403: "This model is only available in the United States."**

Muse Spark 1.1 is US-only on OpenRouter. If running from outside the US,
this model will fail immediately with no output. Do not include in
comparisons unless you have a US-based proxy or BYOK arrangement.

## CLI Model Integration Pattern (2026-07-17)

For models accessible only through CLI tools (Codex CLI, Cursor CLI), run
them separately and merge results into the blind comparison:

1. **API models** (OpenRouter, Ollama Cloud) — run through `compare.py` with
   `--output` flag to save structured JSON results
2. **CLI models** — run in parallel via `terminal(background=true)` with
   `notify_on_complete=true`, save output to `/tmp/<model>_result.json`
3. **Merge** — present all responses anonymously (shuffle A-E), let user vote,
   then reveal all identities including CLI models

### CLI model launch patterns

**Codex CLI:**
```bash
codex exec --skip-git-repo-check -m gpt-5.5 "prompt" > /tmp/codex_result.json
```

**Cursor CLI:**
```bash
agent -p --trust --model "cursor-grok-4.5-high" --sandbox disabled "prompt" > /tmp/cursor_result.json
```

⚠️ Codex CLI may not support the latest models — `gpt-5.6-sol` required a
newer Codex version; fell back to `gpt-5.5`. Always test model availability
with a trivial prompt first.

⚠️ Cursor CLI `--sandbox disabled` is required for web access — default\nsandbox blocks all network calls, so tool-calling tests will fail without it.\n\n⚠️⚠️ **UPDATE**: `--sandbox disabled` alone is NOT enough. The Cursor CLI\nrequires `--force` for web access in headless mode. `--trust --sandbox disabled`\nstill blocks web requests. Use `--force` (which implies `--trust`).\nConfirmed 2026-07-17 across 3 attempts.

## GPT-5.5 via Codex CLI — Detailed Profile\n\n**Overall: 9.0/10 on test A, 8.5/10 on test C. Thorough but expensive.**\n\nTested 2026-07-17 via Codex CLI v0.135.0. Note: gpt-5.6-sol not supported\nby this Codex version — used gpt-5.5 as fallback.\n\n### Strengths\n- **Thorough research**: On test C, cited 5+ sources with links (caddyserver.com,\n  NPM GitHub, Traefik docs, homelab comparison). Compared NPM, Traefik, Caddy\n  with clear tradeoffs.\n- **Correct answers**: Both tests A and C correct. Noted patch version (3.14.6)\n  that other models missed on test A. Picked free-threaded mode as #1 feature\n  on test A (valid but less commonly cited).\n\n### Weaknesses\n- **Massive token overhead**: 37,450 tokens on test A, 50,799 on test C.\n  This is Codex CLI overhead (verbose tool-calling format), not the model itself.\n  ~10× more tokens than Kimi K3 for similar quality.\n- **Model version lag**: Codex CLI v0.135 doesn't support gpt-5.6-sol.\n  Must use gpt-5.5 as fallback until Codex is upgraded.\n\n### Best for\nDeep research where token cost doesn't matter and citations are important.\nUse when you have Codex subscription and want thorough, well-sourced answers.\n\n## Cursor Grok 4.5 High via Cursor CLI — Detailed Profile\n\n**Overall: 9.0/10 on test C (tool calling). Best answer structure.**\n\nTested 2026-07-17 via Cursor CLI (`agent` binary). Required `--force` flag\nfor web access in headless mode.\n\n### Strengths\n- **Best structured answer**: On test C, produced a comparison table\n  (\"when to pick something else\"), Caddyfile code example, and clear decision\n  framework. Most useful answer for someone making a real decision.\n- **Diverse sources**: Cited 5 sources (selfhosting.sh, Big Iron, How-To Geek,\n  CloudHostReview, TechFuel) — more diverse than other models.\n- **Good detail**: Mentioned `annotationlib` VALUE/FORWARDREF/STRING formats\n  (test A), 20-40MB idle RAM for Caddy (test C). Technical depth.\n- **Token efficient**: ~8,500 tok in / ~1,200 tok out — between Kimi K3 and\n  GLM-5.2. Good balance of depth and efficiency.\n\n### Weaknesses\n- **Web access flaky in headless**: Required 3 attempts to get web working.\n  `--trust` alone → blocked, `--trust --sandbox disabled` → blocked,\n  `--force` → works. Must always use `--force` for web-dependent tasks.\n- **First two attempts failed**: On test A, the first run produced no answer\n  (\"web search and fetching python.org were blocked\"). Only succeeded on\n  third attempt with `--force`.\n\n### Best for\nAnswer quality / structure. When the user needs a well-formatted, actionable\nanswer with comparison tables and code examples. Best used through Cursor CLI\nwith `--force --sandbox disabled --model "cursor-grok-4.5-high"`.

Test A's `max_turns` was bumped from 5 to 10 in the TEST_BANK. The original
5 was sufficient for GLM on a good run, but Kimi K3 used only 3 turns while
GLM needed 6 on re-test. 10 turns gives adequate headroom for all models.

## max_turns Calibration

| Test | 5 turns | 10 turns | Recommendation |
|---|---|---|---|
| A (Python version) | ✅ GLM converged | ✅ Both converged | 5 is sufficient |
| B (GitHub stars) | ✅ GLM converged | ✅ GLM converged | 5 is sufficient |
| C (Reverse proxy) | ❌ Both failed | ✅ Both converged | **10 needed** |
| E (LRU cache) | ❌ HY3 failed | ✅ GLM converged | **10 needed** |

Tests C and E require multiple search + extract + synthesize cycles. The
original 5-turn cap was too low. Tests A and B are simpler lookups where 5
turns suffices.

The per-test `max_turns` field in TEST_BANK controls this. Edit the test entry
in `scripts/compare.py` to adjust.

## Judge Model Notes

Using `ollama-cloud:glm-5.2` as the judge worked well — it produces structured
JSON evaluations with scores, strengths, and weaknesses. However, the judge
can be biased when it is also a contestant:

- In test A round 2 (GLM vs MiniMax), GLM was the judge AND a contestant. It
  scored itself 1.0 (fairly, since it failed to converge) and MiniMax 9.5.
  No evidence of self-bias in this run.
- In test B, GLM judged itself the winner (8.5) vs MiniMax (4.0). The scores
  were fair — GLM converged and MiniMax didn't.

**Recommendation**: Using a contestant as judge is acceptable when the judge
model fails to converge (it can't favor itself if it didn't produce output).
For closer contests, consider using a third model as judge.

## Coding & Code Review Tests (2026-07-17)

### Coding Test J — LRU Cache

**Task:** Implement LRU cache with O(1) get/put, type hints, docstring, no
OrderedDict/lru_cache.

| Model | Tokens | Time | Quality | Notes |
|---|---|---|---|---|
| **Kimi K3** | 145 in / 2,354 out | ~3min | Best code quality | `__slots__`, `cast()`, `__len__`, docstrings on every method |
| GLM-5.2 | 47 in / 2,724 out | 23s | 10/10 judge | Generics, dummy nodes, edge cases, comprehensive docstrings |
| GPT-5.5 (Codex) | ~12,300 | 45s | Clean | Standard impl, Generic, sentinel nodes |
| Cursor Grok 4.5 | ~9,300 | ~45s | No code output | Only output a summary — use `--force` for actual code |

### Code Review Test O — SQL Injection

**Planted bugs:** SQL injection (string concat), unreliable fetchone/while loop,
unnecessary commit, print leaking PII, SELECT *, unclosed cursor. **Subtle bug:**
the while loop drains all rows then returns the final None — function always
returns None.

| Model | Tokens | Time | Issues | Notes |
|---|---|---|---|---|
| **Cursor Grok 4.5** | ~9,300 | ~39s | 10 issues | Found ALL bugs incl. "returns None" (BLOCKING). Best structured. |
| GPT-5.5 (Codex) | 6,852 | ~39s | 7 issues | Also caught "returns None" (BLOCKING). Clean, concise. |
| Kimi K3 | 145 in / 2,354 out | ~3min | 7 issues | Misread prompt as truncated. Uniquely caught email case-sensitivity. |
| GLM-5.2 | 103 in / 1,267 out | 14s | 9.5/10 judge | Missed "returns None". Misidentified syntax as "f-string". |

**Key calibration finding:** The "always returns None" bug (while loop drains
all rows, returns final None) is a good discriminator — only Cursor Grok 4.5
High and GPT-5.5 caught it. GLM-5.2 and Kimi K3 missed it. It requires tracing
control flow, not just pattern-matching SQL injection.

**Kimi K3 prompt comprehension issue:** Kimi K3 thought the code was truncated
when it was complete. The escaped quotes in the JSON payload likely caused this.
Significant issue for code review tasks where code is passed via API.

## Kimi K3 Rate Limiting (2026-07-17)

Kimi K3 on OpenRouter hit HTTP 429 on both coding and code review tests
simultaneously. The shared OpenRouter pool for moonshotai/kimi-k3 is
aggressively throttled. Workaround: wait 15-30s and retry via direct API call,
or add a Moonshot API key to OpenRouter (BYOK) for dedicated rate limits.

## 2026-10-14: mistral-large-4 vs glm-5.3 vs kimi-k3 (Ollama Cloud, glm-5.3-flash judge, 6 tests: J M O H6 A S1)

- kimi-k3 best overall avg (8.40) and most consistent — never below 8.0; won test A (tools/research) by catching Python 3.15 via date-agnostic queries + devguide status check.
- glm-5.3 dominant on one-shot coding/review (9.2-9.5 across J M O H6) but weak on multi-turn: 5.7 on A (wrong Python version, 2025-anchored queries). S1 first run died on a turn-1 read timeout (infra, not model); 240s-timeout rerun scored 8.9 (2nd, behind mistral-large-4 9.4). Final corrected battery averages: glm-5.3 8.70 > kimi-k3 8.35 > mistral-large-4 7.87.
- mistral-large-4 middle: strong sandbox execution (9.2 on S1, best structured write_file+run_python+verify loop) but weakest coding penmanship (8.0-8.5) and review scores (7.4/8.1).
- Label order was identical across all 6 runs in the output JSONs (A=mistral-large-4 every time) — the script does not reshuffle per test run; fine for judge mode, breaks unbiased voting across multiple tests. Shuffle manually if running a multi-test blind-vote battery.
- Results: ~/.hermes/cache/mistral_test/*.json + battery_full.log (full judge verdicts).

## 2026-10-14: + gemini-4-argon (OpenRouter, $0.12 for 6 tests) — 4-way re-judge of same responses

- Argon scored 4th place on ALL one-shot tests (J 6.5, M 7.0, H6 7.6) except review O (8.5, 2nd — only response besides best to flag issues cleanly). avg 7.18, 0/6 wins. Weak relative to price; glm-5.3 beat it everywhere on one-shot.
- Method note: single-model addition via direct API + re-judge whole field with responses from stored JSONs (labels A-D by stored order). S1 caveat: if a stored response was a timeout artifact, splice the successful rerun response in before re-judging (else the stale 0.5 propagates). Works well — one consistent judging pass without re-running free models.
- Fresh-judge drift: same responses judged in a second pass moved scores ±0.5 (glm J 9.5→9.5 stable; mistral J 8.5→9.0). Cross-run differences < ~1 point are within judge noise.

## compare.py Single-Model Limitation

The compare script requires at least 2 models (--models flag). To test a
single model (e.g., retrying after rate limit), use direct API calls:

```bash
curl -s "https://openrouter.ai/api/v1/chat/completions" \
  -H "Authorization: Bearer $OPENROUTER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"moonshotai/kimi-k3","messages":[...],"max_tokens":8192}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['choices'][0]['message']['content'])"
```

## Vote History Location

Results from this session were saved to:
`~/.hermes/data/model_compare_history.jsonl`

Format: {"timestamp", "test", "models", "winner", "scores", "is_blind"}
## Muse Spark Open findings (24-test battery, 2026-10-16)
Ran `ollama-cloud:muse-spark-open` vs `glm-5.3-flash` vs `deepseek-v4.1-flash`,
judge glm-5.3 (minimax-m3 judge dropped mid-run per user). All on ollama-cloud
(free) — muse-spark-open is ALSO on ollama-cloud, not only OpenRouter/Modal.

- Wins (glm judge): muse 5 tools A/E/H1 + coding L/M; glm-5.3-flash 13
  (all coding except L/M, all 7 review, tools H2/S3); deepseek 6 (tools factual
  S-tests + B/C). Avg scores: glm 8.18, deepseek 7.77, muse 7.00.
- Agentic chain weakness (the headline): muse failed to converge 3/11 tools
  tests (C 10-turn, H1/H2 12-turn caps) on long chains — burns turns on
  redundant searches then hits the cap. glm/deepseek each failed 2/11 (E, H1).
- muse output is token-lean (42.7k out total vs 140k glm / 93k deepseek) and
  fast (333s total), good first-attempt quality on research synthesis (A, E).
- muse review mode is its weakest area — last on all 7 review tests.
- muse calls tools even for trivial prompts when tools are present (PONG test
  → emitted a web_search call). Instruct prompts without tools behave normally.
- glm-5.3-flash timeouts: 2/24 single-shot coding/review calls hit read
  timeouts (32k reasoning budget consumed, H3 19.4k + H5 25.9k out tokens on
  rerun, 133s/221s). Retry recovered both. Watch read timeouts on hard prompts.
- Ollama Cloud muse-spark-open serves from SG fine (no geofence; OpenRouter
  meta/muse-spark-1.1 was US-only in past tests; muse-spark-open on OpenRouter
  also works from SG, served by Modal).
- Judge artifacts: per-test JSONs + traces in
  ~/.hermes/data/battery_muse_20261016/ (aggregated.json, judge_glm53_*.json).

## Nemotron 3.5 Super VL findings (24-test battery, 2026-10-16)
`nvidia:nvidia/nemotron-3.5-super-vl-120b-a12b` (NIM, free) vs glm-5.3-flash +
deepseek-v4.1-flash, judge glm-5.3. Artifacts: ~/.hermes/data/battery_nemotron_20261016.

- Wins: nemotron 2/24 (coding H3, retry-decorator M). glm-5.3-flash 17 (all 7
  review, most coding). deepseek 5 (short factual tools tests A/E/S1/S4/S5).
  Avg scores: glm 8.38, deepseek 7.06, nemotron 6.75.
- nemotron is token-lean (57k out vs 142k glm / 137k deepseek across 24 tests)
  and decent on single-shot coding, but weak on long tool chains: 3/11
  non-converged (C, E, H2) and mostly middle-of-pack on research synthesis.
- Reliability: 3 NIM HTTP 500 "Failed to generate completions" errors across
  the battery (H6, H2, S3 arms) — compare.py marks such arms success=True with
  0 tokens; always check tokens>0 or content starts with "[Error" before
  trusting a rollup. Retries recovered all three.
- glm-5.3-flash read-timeout pattern reproduced: timed out again on the same
  H3/H5 prompts (2nd battery in a row) — these two prompts are systematically
  over-budget for it; arm-level retry recovers.
- Judge-family bias caveat applies: glm-5.3 judged while glm-5.3-flash
  competes; it still scored glm 0.0 where response was empty, and nemotron
  won H3/M with 9.2.

## Battery harness + judge convention (2026-10-16)
- Judge = glm-5.3 (ollama-cloud), sole judge; minimax-m3 dropped per user.
- Reusable harness, env-driven, per-battery dirs under ~/.hermes/data/:
  `run_battery2.sh` (env BATTERY_OUTDIR, BATTERY_MODELS, BATTERY_JUDGE; one
  shell per mode tools/coding/review, tests sequential inside each) ->
  `judge_rerun.py` in battery_muse_20261016/ (BATTERY_OUTDIR-aware, 4
  threads, resume-safe via existing judge_glm53_* files) -> `aggregate.py`
  (BATTERY_OUTDIR-aware; parses compare.py logs for per-test verdicts and
  rollups). Judge replies use blind labels; normalize "RESPONSE B"-style keys
  to A/B/C.
- compare.py arm-reliability gotcha: error arms (HTTP 500 / read timeout) can
  be recorded success=True with 0 tokens and the error text as content.
  Filter arms on tokens_out>0 and content not starting with "[Error" before
  rollups; judges score empty arms 0.0.
- glm-5.3-flash read-timeout pattern: the same hard prompts (H3, H5) timed
  out in both batteries; single-arm direct-curl retry with 32k budget
  recovers, and the patched JSON must be SAVED after in-memory fixes.
- Ornith-1.0-35B (35B MoE agentic coder on Qwen 3.5, MIT, 262K ctx): not on
  Ollama Cloud/OpenRouter/NIM; hosted only at FriendliAI plus small gateways
  (Umbra, Interfaze); community GGUF maxwell1500/ornith-35b for local pulls.
