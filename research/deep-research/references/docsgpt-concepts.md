# DocsGPT ResearchAgent — Concepts Adapted for Deep Research v1.5.0

**Source:** [arc53/DocsGPT](https://github.com/arc53/DocsGPT) (MIT license)
**File:** `application/agents/research_agent.py`
**Reviewed:** July 2026, v0.18.0

## Concept Mapping

| DocsGPT ResearchAgent concept | Deep Research v1.5.0 adaptation | How it differs |
|---|---|---|
| Complexity caps (simple=2, moderate=4, complex=6) | Adaptive depth (simple=2, moderate=3, complex=5) | Tighter caps — our prompt-based workflow is slower per round than their Python loop, so fewer rounds is more efficient. **Always use the skill's caps (2/3/5), not DocsGPT's (2/4/6).** |
| Clarification phase (JSON LLM call → 1-3 questions → metadata flag for follow-up) | Step 0: optional clarification (heuristic, not LLM call) | We use a heuristic check rather than an LLM call — lighter weight, no extra tokens |
| Token budget tracking (`_tokens_used` counter, `token_budget` hard limit) | Token budget awareness in synthesis + stopping check | We can't track exact tokens (prompt-based, not code), so we approximate and use it as a soft signal |
| Citation deduplication (`CitationManager` class, dedup by URL+title) | Numbered citations `[1]`, `[2]` with URL dedup | Same dedup logic, applied as prose instructions rather than Python code |
| Progressive empty-search refinement (two-strike hint injection) | Three-tier refinement protocol (broader → different angle → move on) | We add an explicit third tier (move on) that DocsGPT doesn't have |
| Synthesis prompt (plan + findings + references passed explicitly) | Synthesis prompt structure guidance | Same concept — we instruct the agent to consult all sources explicitly rather than relying on cumulative state |

## What was NOT adapted

| DocsGPT concept | Why not |
|---|---|
| Parallel research steps (`parallel_workers=3`) | Already have Subagent Mode with `delegate_task` — covers the same use case |
| Streaming progress events (`yield {"type": "research_progress", ...}`) | Not applicable — our skill is prompt-based, not a streaming Python generator |
| `ToolExecutor` abstraction | Not applicable — Hermes tools are called directly |
| Internal search tool (searches ingested documents) | Not applicable — our skill uses `web_search`/`web_extract`, not a document store |
| Wiki tool integration | Not applicable — no wiki in our research workflow |
| Think tool (`THINK_TOOL_ENTRY`) | Hermes already has native reasoning — no explicit "think" tool needed |

## DocsGPT ResearchAgent architecture (for reference)

```
Phase 0: Clarification
  → LLM assesses if question needs clarification
  → If yes: yield clarification text, stop, wait for user
  → If no: proceed

Phase 1: Planning
  → LLM decomposes question into steps + complexity assessment
  → Complexity caps: simple=2, moderate=4, complex=6
  → Returns: list of {query, rationale} + complexity string

Phase 2: Research (per step)
  → For each step in plan:
    → Run research loop (max_sub_iterations=5)
    → LLM generates tool calls (search, think, wiki)
    → Execute tools, collect results
    → If search returns empty: inject refinement hint
    → If two consecutive empties: inject stronger hint
    → After max iterations: ask LLM to summarize findings
    → Collect sources from InternalSearchTool → CitationManager
  → Token budget + timeout checks between steps

Phase 3: Synthesis
  → Construct prompt: original question + plan summary + all intermediate reports + references
  → Stream synthesis LLM response
  → Yield final sources + tool calls
```

## Key design decisions in DocsGPT worth noting

1. **Complexity caps are adaptive, not fixed.** The LLM decides complexity during planning. This prevents over-searching simple questions.

2. **Clarification uses metadata flags, not string matching.** `_is_follow_up()` checks `metadata.is_clarification` on the last chat message — robust to user phrasing variations.

3. **Token budget is a hard stop, not a suggestion.** `_is_over_budget()` breaks the research loop immediately. In our prompt-based adaptation, this is a soft signal because we can't count tokens precisely.

4. **Citation dedup is by (source, title).** Same source seen twice → same citation number. This keeps the reference list clean.

5. **Empty-search refinement is progressive, not single-shot.** Two consecutive empties trigger a stronger hint. We extended this to a third tier (move on).