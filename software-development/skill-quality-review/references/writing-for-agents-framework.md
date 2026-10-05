# Writing-for-Agents Review Framework

The lever set for reviewing SKILL.md files. Blends Matt Pocock's `writing-for-agents` (github.com/mattpocock/skills) with Hermes `hermes-agent-skill-authoring` peer-matched structure.

Source: https://github.com/mattpocock/skills/tree/main/skills/productivity/writing-for-agents

## Contents

- 1. Context pointers (description quality)
- 2. The two loads
- 3. Information hierarchy
- 4. Steps and completion criteria
- 5. Leading words
- 6. Pruning
- 7. Peer-matched structure (Hermes-specific)
- 8. Cross-reference parity (for skills with scripts)
- Severity calibration
- Parallel review dispatch

## 1. Context pointers (description quality)

The description is the skill's top-level context pointer — always loaded in the system prompt. Every word costs tokens every turn.

- **Front-load the leading word** — the pointer is where it does its triggering work.
- **One trigger per branch.** Synonyms renaming a single branch are duplication — collapse them.
- **Cut identity that the body already carries.** Keep the description to triggers, plus any "when another skill needs..." reach clause.
- Description <= 1024 chars (Hermes validator enforced).
- Model-invoked skills should start with "Use when ...".
- **Variance bug rule** (upstream 2026-10 revision): the pointer's *wording*, not its target, decides when the agent reaches the material. A must-have target behind a weakly worded pointer is a variance bug — sharpen the wording first; inline the material only if sharpening fails.

Source of pointer doctrine, current revision: https://raw.githubusercontent.com/mattpocock/skills/main/skills/productivity/writing-for-agents/SKILL.md (sibling upstream file `SKILL-MECHANICS.md` covers frontmatter, invocation choice, router skills).

## 2. The two loads

Every document and pointer spends one of two budgets:

- **Context load** — the cost of always-loaded material on the agent's window. A model-invoked skill's description pays this every turn. The price of agent-discoverability.
- **Cognitive load** — the cost on the human. A user-invoked skill (`disable-model-invocation: true`) costs zero context load, but the human must remember it exists.

Pick model-invocation only when the agent must reach the skill on its own, or another skill must invoke it. If a skill only fires by hand, make it user-invoked and pay no context load.

SKILL-MECHANICS.md nuances (upstream 2026-10): model-invocation **includes** user reach — a description only adds agent discovery, never removes the human's ability to type the name. Shared reference two user-invoked skills both need can live in neither (with no descriptions, neither can fire the other): push it to a plain file outside the skill system. A router skill can only **hint**, never fire its targets.

## 3. Information hierarchy

A document is built from **steps** (ordered actions) and **reference** (definitions, rules, facts) that mix freely. The ladder:

1. **In-file step** — the primary tier: what the agent does, in order.
2. **In-file reference** — consulted on demand. A legitimately flat peer-set is fine.
3. **Disclosed reference** — pushed behind a context pointer into a linked file, loaded only when the pointer fires.

**Progressive disclosure** is the move down the ladder — out of SKILL.md into `references/*.md` — so the top stays legible. Push too little down and the top bloats; push too much and you hide material the agent actually needs.

**Co-location** decides what sits beside material once there: keep a concept's definition, rules, and caveats under one heading, not scattered.

**Sprawl** is the failure mode: a document simply too long, even when every line is live and unique. Cure: disclose reference behind pointers, split by branch or sequence.

## 4. Steps and completion criteria

Every step ends on a **completion criterion** — the condition that tells the agent the work is done. Two properties make it a lever:

- **Clarity** — can the agent tell done from not-done? A vague bound invites **premature completion**: ending the step before genuinely done. Defend: sharpen the bound first (cheap, local). Only if irreducibly fuzzy AND you observe the rush, hide post-completion steps by splitting the sequence.
- **Demand** — how much it requires. "Every modified model accounted for" forces thorough work where "produce a change list" does not.

The strongest criteria are both checkable and exhaustive.

Upstream refinements (2026-10 revision): post-completion steps are the *pull* that tempts the agent to rush the current step; their visibility is the cost, the criterion's clarity the resistance. Hiding later steps by splitting only works across a **real context boundary** (hand-off, subagent dispatch) — an inline call leaves them in context and clears nothing. **Demand drives legwork**: exhaustive wording ("every rule applied") binds a body of flat reference just as "every step done" binds a sequence — which is how an all-reference document still carries an exhaustiveness bar.

## 5. Leading words

A **leading word** is a compact concept already living in the model's pretraining (e.g. _tracer bullet_, _fog of war_, _red_, _lesson_) that the agent thinks with while running the document. It encodes a behavioural principle in the fewest tokens by recruiting priors the model already holds.

It anchors twice. In the body, _execution_. In a pointer, _invocation_ — when the same word lives in prompts, docs, and code, the agent links that shared language to the material.

Hunt for restatements that a single word can retire: "fast, deterministic, low-overhead" -> _tight_. "a loop you believe in" -> _red_.

Prefer **pretrained words over coined ones** (upstream 2026-10 revision): a made-up word recruits no priors — you pay in definition tokens what an existing word gives free. Repeat a leading word as a **token, never as a sentence**; that is how it accumulates its distributed definition. Assume every document carries restatements some leading word can retire — hunt them.

**Negation** is the failure mode beside this lever: steering by prohibition drags the forbidden behaviour into context. Prompt the **positive** — state the target behaviour so the banned one is never spoken. Keep a prohibition only as a hard guardrail you cannot phrase positively; pair it with what to do instead.

## 6. Pruning

- **Single source of truth** — each meaning in one authoritative place, so changing behaviour is a one-place edit. Duplication costs maintenance and inflates prominence.
- **No-op test** — run on each sentence in isolation: does it change behaviour versus the model's default? If not, delete the whole sentence, don't trim words from it. The test is model-relative: settle it by running the document, not by debate.
- **Sediment** — stale layers that settle because adding feels safe and removing feels risky. The default fate of any skill without a pruning discipline.
- **Relevance** — does the line still bear on what the document does? Shorter documents are easier to keep relevant.
- **The environment is a source of truth too** (upstream 2026-10 revision): package.json scripts, config files, directory layout, `--help` output. A document that restates them is a **cache** — a copy of a lookup, earning its load only when the lookup is expensive. Cache what the agent cannot find by looking (unwritten convention, reason behind a choice, gotcha no config confesses); leave one-file, one-command lookups to the environment, where they cannot go stale.

## When to split (upstream 2026-10 revision)

Splitting one document into two spends one of the two loads; split only when the cut earns it:

- **By sequence** — split a run of steps where post-completion steps tempt the agent to rush the one in front of it; keeping them out of view drives more legwork on the current task. Beware the reverse: merging sequences exposes each step's later steps to what follows, inviting premature completion.
- **By invocation** — skill-specific; see the SKILL-MECHANICS.md link under lever 1.

## 7. Peer-matched structure (Hermes-specific)

Frontmatter: `name`, `description`, `version`, `author`, `license`, `metadata.hermes.{tags, related_skills}`.

Structure: `# Title` -> `## Overview` -> `## When to Use` -> body -> `## Common Pitfalls` -> `## Verification Checklist`.

Size: aim for 8-15k chars. Over 20k, split into `references/*.md`. `related_skills` should resolve in-repo.

## 8. Cross-reference parity (for skills with scripts)

Three sources of truth must agree:

| File | What it holds | Drift risk |
|---|---|---|
| `SKILL.md` | Triggers, mode routing, steps | Trigger phrases claim scope the body doesn't cover |
| `scripts/*.py` | Model IDs, pricing, validation | Model IDs in docs but missing from pricing dict |
| `references/*.md` | Model registries, guides, checklists | Rates that don't match code |

Grep checklist: model ID parity (docs <-> code), trigger phrases vs body scope, pricing rate consistency, duration/input bounds validation, stale file references, brittle exact-string matching.

## Severity calibration

| Severity | Example |
|---|---|
| RED (should fix) | Description claims scope the body doesn't cover; model ID in docs but code can't price; missing completion criterion on a key step; description over 1024 chars; contradictory DEFAULT labels in one table; stale version references after upgrade; audio/feature default inconsistent across SKILL.md ↔ script ↔ references; two-loads mismatch (model-invoked skill whose body says "don't load per-session"); literal duplicate content |
| YELLOW (nice to fix) | No-op prose; negation where positive works; undocumented model in code; sprawl past 15k chars; missing `## Overview`; `metadata.hermes` nesting wrong; environment-state in description; missing completion criterion on secondary step; FTS5 rebuild instructions duplicated between SKILL.md and reference |
| GREEN (minor) | Cost rate uses midpoint without comment; example path inconsistency; missing Verification Checklist; good progressive disclosure; strong leading words |

## Parallel review dispatch

For reviewing 12+ skills, dispatch 2 parallel `delegate_task` subagents (6 skills each). Each reads the full SKILL.md + linked files, applies all 8 levers, and returns structured findings. Consolidate after both complete.

### Per-skill report format

Each subagent should produce a structured JSON report per skill:

```
{
  "skill_name": "...",
  "size_chars": N,
  "findings": [
    {
      "severity": "RED|YELLOW|GREEN",
      "category": "1-8 lever name",
      "description": "what's wrong",
      "evidence": "exact line quote",
      "fix_proposal": "concrete fix"
    }
  ],
  "overall_assessment": "paragraph"
}
```

Include a cross-cutting summary table at the end: skill name, size, RED/YELLOW/GREEN counts, grade. This makes it easy for the parent agent to prioritize fixes.

### Reading linked files

Each subagent must read ALL linked files in `references/` and `scripts/` subdirectories, not just SKILL.md. Cross-reference parity (lever 8) requires comparing model IDs, pricing, trigger phrases, and feature defaults across SKILL.md ↔ scripts ↔ references — you can't check parity from SKILL.md alone. Use `os.walk()` on the skill directory to discover all files, then read each one.

This turns a serial 30-minute review into a 5-minute parallel one.