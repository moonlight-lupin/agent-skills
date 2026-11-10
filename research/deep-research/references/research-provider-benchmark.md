# External Research-Provider Head-to-Head (Perplexity Agent API)

Recipe for benchmarking this skill's loop against an external research provider
on one test question. Provider card covers Perplexity's Agent API as measured.

## Command rules

- Pick a test query the user cares about. Send the SAME raw question to both
  systems. Never inject dates, model hints, or scope refinements into the
  provider's copy — how each system grounds time and scopes itself is part of
  the test, not preprocessing.
- The provider run chains many searches server-side and can take several
  minutes: launch it in the background with a generous curl `-m` (measured
  `high` run: ~6 min), drive this skill's loop in the foreground meanwhile,
  then synthesize the comparison only when both sides are complete.
- Never score the provider's claims from its own citations. Re-verify its
  central ranking/figures yourself against the primary source (own fetch).
  An unverified citation chain is the exact failure mode this test measures.

## Perplexity Agent API (measured provider card)

- Endpoint: `POST https://api.perplexity.ai/v1/agent`, body `{"preset": ...,
  "input": ...}`. Presets: `fast` (single-fact lookups), `low` (multi-hop
  wide aggregation), `medium`, `high` (deep-research class), `xhigh`
  (highest-quality tier). The legacy Sonar `chat/completions` surface is
  retired — new work uses `/v1/agent` only.
- Key: `PERPLEXITY_API_KEY`, resolved from the environment (exported by the
  host's profile startup, or set in your shell session before the run). Never
  `source` a whole `.env` file — unquoted lines break it.
- Validate auth with a cheap `fast` ping first (~1¢), then launch the real run.
- Response shape: `output[]` steps — `search_results` (items: url, title,
  date, snippet), `fetch_url_results`, `message` (`content[].text` = the
  answer). `usage.cost.total_cost` carries the price; `model` is the routed
  underlying model — record the response's own `model` field, never assume.
- Cost profile (measured): `high` ≈ $0.6–0.65 per run, ~500K input tokens;
  search_web and fetch_url tool calls bill inside that. Budget accordingly.
- The `-o` file appears only when the run completes; if it seems stuck, check
  `ps` elapsed time on the curl before concluding failure.

## Scoring pass (same rubric per provider)

1. Verify the provider's central claims against primary sources yourself.
2. Count: wall time, cost, result URLs seen + unique domains, pages fetched,
   sources cited, answer size.
3. Score coverage: independent (non-self-reported) evaluation material,
   contradiction surfacing across sources, date semantics (announcement vs
   availability dates), honesty markers (empty cells, harness caveats,
   unsupported-cell handling).
4. Deliver the verdict as complementary positioning — e.g. provider as fast
   broad first pass, this skill as the adversarial verification layer that
   fact-checks the provider's ranking claims — not winner-take-all.

## Measured provider behavior (calibration for scoring)

Strengths seen: renders JS-built aggregator tables that HTTP/tier-2 fetches
return as class-name soup; handles two-date releases correctly (announcement
vs weights date) and states the convention it chose; flags harness
heterogeneity on task scores and leaves cells empty where vendors publish
nothing; breadth into dozens of domains per run; per-claim `[web:N]` citations.

Gaps seen: omits independent government/academic evaluations unless the
question names them; presents one coherent ranking without surfacing
cross-index contradictions; no deterministic post-validation of its own
structure/citations.
