---
name: input-token-analysis
description: "Use when input token spend needs explaining and fixing."
license: MIT
metadata:
  version: 1.2.0
  author: moonlight-lupin
  platforms: [linux]
  tags: [tokens, audit, cost, accounting, agent-ops]
  related_skills: [input-token-overheads, skill-maintainer]
---

# Input Token Analysis

Explain aggregate input token consumption. Answer three questions with numbers: where did the tokens go, which consumers dominate, what config or prompt change reduces them. Distinct from `input-token-overheads`, which audits per-turn system-prompt blocks. This skill audits total volume across sessions, cron fires, and tool traffic.

## When to Use

- Monthly/weekly input token bill is large and unexplained (e.g. "2.4B tokens in 30 days")
- After applying token-saving changes — measure the delta against a baseline
- A cron job is suspected of runaway token use

For per-turn context-window health, use `input-token-overheads`. For API billing disputes, use the provider's usage dashboard — local telemetry cannot see provider-side caching.

## Quick Start

Run the audit script (read-only, pure stdlib):

```bash
python3 ~/.hermes/skills/agent-ops/input-token-analysis/scripts/audit.py --days 30
# other profiles: --db ~/.hermes/profiles/<name>/state.db
# custom cron ledger: --cron-audit /path/to/usage_audit.jsonl --jobs /path/to/jobs.json
```

The script prints: totals by task/model/provider, cache-read and cache-write columns, weighted per-call averages (long sessions and short-session floor), top sessions, cron offenders, active-only tool-result volume with the tool-share percentage, and oversized-result counts. Everything is derived from real DB rows — never estimate by hand when the script can measure.

## Pre-Check Discipline

Verify before advising. Advice formed from memory is not acceptable.

1. **Config keys and current values** — read the live value first: `hermes config get <key>`. Never state a current value from memory or assume the default is in force.
2. **Defaults and mechanisms** — confirm a key exists and what it does against the installed build (`hermes_cli/config_defaults.py`) or the Hermes docs. If the installed build and docs disagree, say so.
3. **Provider behavior** — do not assume a provider reports cache fields, honors a pricing tier, or counts tokens a certain way. Probe it or check its current docs before claiming.
4. **Unverifiable claims** — mark them UNVERIFIED in the report. A labeled unknown beats a confident guess.

A proposal that cites an unverified key, value, or mechanism is incomplete. Complete the pre-check or drop the proposal.

## Interpretation

Rank consumers, then map each to a pre-checked lever:

| Finding | Signal | Lever |
|---------|--------|-------|
| Long sessions dominate | Top sessions >200 api_calls, >40M input | First check the provider's cache discount. With caching, a warm session re-reads history cheaply; reset only when uncached dead weight dominates. Every reset re-pays the full prefix at full price. Check compression actually fires (compact count >0) |
| background_review large | task='background_review' >5% of total | `auxiliary.background_review.max_input_tokens` (default 600000) or `enabled: false`; manual `/refine` still works. Also route `auxiliary.background_review.model` to a cheaper model — a different model replays a compact digest instead of the full transcript |
| One cron job dominates | avg prompt_tokens/fire in the millions | Rewrite its prompt with a read budget: date-bounded source data, skip oversized items, narrow scroll windows, stop-at-cap and defer |
| Cron cost at the floor | avg tokens/fire near the per-call floor (25-30k) | The fixed scaffolding floor times fire count dominates: reduce fire frequency or merge jobs rather than shrinking prompts |
| Tool results dominate context | tool chars >70% of STORED active content (upper bound on sent; script prints the share) | `tool_output.max_bytes` (default 50000), `file_read_max_chars` (default 100000), spillover budget. Under provider caching, savings concentrate on the first turn a result appears and on compression avoidance — stable results re-read via cache are cheap. Oversized results spill to `$HERMES_HOME/cache/spillover/` as preview + path |
| Duplicate skill loads | same skill body loaded N times per session | Behavioral rule: never re-call skill_view for a skill already in context. Under caching the direct re-read is discounted; the real damage is context pressure triggering earlier compression, which busts the cache |
| High per-call floor at short sessions | script's weighted avg for <50-call sessions (typically 25-40k) | Fixed baseline (system prompt + tool schemas) — reduce via `input-token-overheads`, not this skill |
| Subagent fan-out heavy | many delegate_task spawns; each re-pays the full system prompt + tool schemas uncached | Route `delegation.model` to a cheaper model for mechanical subtasks; batch tool calls into one execute_code call instead of fanning out; cap concurrent subagents |
| Compression firing often | compression events per session high; `compression_ineffective_count` >0 | Each compression rewrites history into a new prefix = full-price cache miss for everything after. Weigh `compression.threshold` against the provider's cache discount; route the compression summarizer (`auxiliary.compression.model`) to a cheap model — it reads the entire conversation |
| cache_read ≈ 0 on a provider | provider emits no cached-token field at all (then local input IS the full prompt and share is unmeasurable — check the provider's billing dashboard), vs provider reports the field but it is 0 (caching genuinely off: short sessions, unstable prefix, or TTL expiry — investigate) |
| Cheap-task traffic on premium models | title_generation/approval/vision rows on the main model | Route each `auxiliary.<task>.model` to a flash-class model; near-free savings on frequent small calls |
| Token ranking ≠ cost ranking | a cheap model consumes 10x the tokens of a premium one | Rank by `estimated_cost_usd`/`actual_cost_usd` per billing_provider; exclude `billing_mode='subscription_included'` rows (zero marginal cost) from optimization effort |

## Procedure

### 1. Establish the baseline

Run the script for the window in question. Record: total input, per-task breakdown, top-10 sessions, cron offender stats, tool-char share, cache columns, cost totals. Save the output next to the changes you plan to make.

Done when: every number in the final report traces to a script line.

### 2. Pre-check each candidate lever

Before any lever enters a proposal, verify it on the live instance: key exists (`hermes config get`), current value known, mechanism matches the installed build or docs. Check the provider's reporting behavior before making cache-related claims.

Done when: every lever in the draft proposal has a verified key + current value, or is marked UNVERIFIED with what is missing.

### 3. Rank and map

Order consumers by tokens AND by estimated cost (they can disagree). For each of the top 3, name the pre-checked lever. If a consumer maps to no lever, say so explicitly instead of inventing one.

Done when: top 3 consumers each have a pre-checked lever or an explicit "no local lever" verdict.

### 4. Propose changes

Proposals in impact order, each with: config key or prompt edit, expected saving, revert path. Compute expected saving per billing_provider with that provider's cache discount applied; where the provider does not report cache fields, state the estimate is bounded and verify on the provider dashboard. Config edits go through `hermes config set` — direct file edits to config.yaml are blocked by the tooling (verified 2026-09-02). Cron prompt edits: back up the old prompt first, edit, then verify shape (`{"jobs": [...], "updated_at": ...}`) and schedules survived.

Done when: the user approved each change and it is applied AND read back verified.

### 5. Schedule the delta check

Create a one-shot cron ~30 days out that re-runs this skill with the old baseline in its prompt. Include: baseline numbers, the list of applied changes, and per-change pass criteria (e.g. "job X avg prompt_tokens/fire >2M = not fixed").

Done when: the delta-check cron exists (`hermes cron list` shows it) and its prompt contains the baseline numbers, applied-change list, and pass criteria.

## Pitfalls

1. **Open state.db read-only** (`file:...?mode=ro`, uri=True, URL-encode the path). It is live and can be hundreds of MB; a writer connection risks locks.
2. **input_tokens semantics differ by provider wire format.** Anthropic-style wires report `cache_read_tokens` IN ADDITION to input (true prompt ≈ input + cache_read + cache_write); OpenAI-style `prompt_tokens` includes cached tokens as a subset. Empirical check: if cache_read > input_tokens for a row, that provider excludes cache from input. Never compare raw input_tokens across providers; compute effective prompt per billing_provider. The cache-share ratio is only meaningful within one convention.
3. **jobs.json has two observed shapes** — `{"jobs": [...], "updated_at": ...}` and a bare list. Handle both before and after editing; verify the container shape after any write.
4. **Cache-share 0 does not prove no caching.** Some providers return no cached-token field in `usage` at all (one such provider verified 2026-09-02 — its usage object carried only prompt/completion/total), so local telemetry is blind to their caching. Others report cache reads per call. Check each provider's docs and billing dashboard for ground truth.
5. **sessions.input_tokens and session_model_usage differ by attribution**, not just timing: task rows are cumulative per session and attributed by last_seen (pulling pre-window spend into the window), while per-session ranking uses start/activity dates. State the skew direction when totals do not reconcile; never mix the two totals in one sum.
6. **token_count column is often NULL** — measure content size with LENGTH(), and remember chars ≈ tokens/4 only as a rough proxy.
7. **Compaction and inactivity skew stored content.** Filter messages by `active=1`: compacted rows were replaced by summaries and inactive rows are no longer sent. Stored active content is still an upper bound on sent content (truncation already applied at capture time). Live-vs-compacted splits explain why a session's DB size can exceed its context.
8. **A single fire can dwarf everything** — scan for max(prompt_tokens) in the cron ledger before averaging; one multi-million-token fire hides inside a healthy-looking mean.
9. **Cron ledger prompt_tokens semantics are per-fire and under-documented** — one line per fire, but an agentic fire makes many API calls with context re-sent each call. Treat avg tokens/fire as a lower bound on true cron input and verify against a fire's session rows when precision matters.
10. **Per-call averages must be weighted** — SUM(input)/SUM(calls), never AVG of per-session ratios; a 200-call session and a 10,000-call session count equally otherwise.

## Verification Checklist

- [ ] Script ran read-only against every relevant profile DB (default + any active profiles)
- [ ] Totals cross-checked with attribution skew stated (task rows by last_seen vs sessions by start/activity)
- [ ] Each top consumer mapped to a pre-checked lever or marked "no local lever"
- [ ] Every proposed lever pre-checked: key exists, current value read live, mechanism confirmed
- [ ] Applied changes read back verified (`hermes config get`, cron jobs.json re-parse)
- [ ] Old prompts/config backed up with paths recorded
- [ ] Delta-check cron scheduled with baseline + pass criteria in its prompt
