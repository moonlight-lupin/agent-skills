---
name: input-token-overheads
description: Use when auditing per-turn input token overhead on Hermes.
version: 1.3.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [tokens, overhead, context, optimization, agent-ops]
    category: agent-ops
    related_skills: [hermes-compression-tuning, skill-curation]
    requires_toolsets: [terminal]
---

# Input Token Overheads

Audit every source of per-turn input token cost on a Hermes Agent instance. Measure each, rank by cost, act on the top consumers.

## When to Use

- User says "token overhead", "context too large", "why is input so expensive"
- Model output quality degrades from context dilution
- Cost optimization — fewer input tokens per turn means lower API spend
- After adding skills, plugins, or tools — verify the overhead delta

## The Overhead Map

Every turn, Hermes injects these blocks into the system prompt **before the user's message**:

| Block | When loaded | Cost model |
|-------|-------------|------------|
| Skill descriptions | Every turn (skill-retrieval top-K) | ~200 chars per description, K per turn |
| Memory (personal notes) | Every turn | Static, grows with usage |
| User profile | Every turn | Static, grows as preferences accumulate |
| Memory provider context | Every turn (if memory plugin active) | Dynamic, 5 memories recalled by default |
| Tool schemas (direct) | Every turn | Full JSON schema per enabled tool |
| Deferred tool catalog | Every turn (if configured) | Name + description only |
| Mandatory skills | Every turn (if configured) | Full SKILL.md body |
| Platform formatting rules | Every turn | Fixed, platform-specific |
| Behavioral rules | Every turn | Fixed system prompt text |
| Full skill body | On-demand (skill_view) | Only when a skill is loaded |
| Compression summary | After threshold | Replaces older messages with a summary |

**On-demand (not per-turn):** full SKILL.md via `skill_view`, deferred tool schemas via `tool_describe`, reference files via `skill_view(file_path=...)`.

## Health Ratio

The health metric is **overhead ratio**: overhead tokens divided by the model's context window. The absolute number matters for cost; the ratio matters for quality.

| Ratio | Rating | Notes |
|-------|--------|-------|
| < 5% | Excellent | Most of the window available for conversation |
| 5-15% | Healthy | Normal for a capable agent with tools, skills, memory |
| 15-25% | Acceptable | Approaching the limit. Consider trimming. |
| > 25% | Unhealthy | Eats conversation capacity. Cost and quality risk. |

**Why the ratio matters:** Three studies confirm that input length degrades model performance independent of content quality:

1. **Lost in the Middle** (Liu et al., TACL 2023) — Models follow a U-shaped curve: best recall at the start and end of context, severe degradation in the middle. Overhead sits at the top of every turn, but it pushes conversation history into the degradation zone. [arxiv.org/abs/2307.03172](https://arxiv.org/abs/2307.03172)

2. **Same Task, More Tokens** (Levy et al., ACL 2024) — Reasoning performance degrades at input lengths far shorter than the model's stated maximum. The degradation appears even when the extra tokens are padding with no distracting content. The model's technical context window is not its effective context window. [aclanthology.org/2024.acl-long.818](https://aclanthology.org/2024.acl-long.818/)

3. **Context Length Alone Hurts** (Du et al., EMNLP 2025) — Performance degrades 14-85% as input length increases, even when retrieval is perfect, irrelevant tokens are replaced with whitespace, or all tokens except relevant ones are masked. The sheer length of the input is itself a limitation. [aclanthology.org/2025.findings-emnlp.1264](https://aclanthology.org/2025.findings-emnlp.1264/)

**Cost compounding:** Overhead is paid every turn. At 10k tokens over 100 turns, that is 1M input tokens spent on overhead alone. Reducing overhead by 2k tokens saves 200k tokens per 100-turn session.

**Mitigations from the research:**

| Finding | Source | Action |
|---------|--------|--------|
| Models recall start and end of context best; middle degrades | Liu et al. 2023 | Keep overhead at the top (Hermes already does this). Avoid pushing critical conversation history into the middle — lower compression threshold if history is being compressed too aggressively |
| Reasoning degrades well below the stated context window maximum | Levy et al. 2024 | Treat the effective context window as 50-70% of the advertised maximum. Target an overhead ratio under 10% of the advertised window, not the effective one |
| Sheer input length hurts even with perfect retrieval and no distraction | Du et al. 2025 | Reduce overhead aggressively. Every 1k tokens of overhead removed improves reasoning quality, not just cost. The study's mitigation: prompt the model to recite key evidence before solving — equivalent to Hermes compression summarizing relevant context |
| Tool calling degrades 7-85% as tool catalog grows from 8k to 120k tokens | LongFuncEval (arxiv 2505.10570) | Keep the enabled toolset count low. Prefer deferred tools (loaded on demand) over always-on schemas. Disable unused toolsets |

## Procedure

### 1. Measure each overhead source

Run the audit script to get real numbers:

```bash
python3 -c "
import yaml, pathlib, glob, os, re

# --- Skill descriptions (skill-retrieval index) ---
files = glob.glob(os.path.expanduser('~/.hermes/skills/**/SKILL.md'), recursive=True)
total_desc = 0; count = 0; by_cat = {}
for f in files:
    try:
        text = pathlib.Path(f).read_text()
        m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
        if not m: continue
        fm = yaml.safe_load(m.group(1))
        if not fm: continue
        desc = fm.get('description', '')
        if not desc: continue
        cat = f.split('/skills/')[1].split('/')[0]
        by_cat.setdefault(cat, [0,0]); by_cat[cat][0] += len(desc); by_cat[cat][1] += 1
        total_desc += len(desc); count += 1
    except: pass
avg = total_desc // max(count, 1)
print(f'Skills: {count} total, {total_desc} chars in descriptions')
print(f'  Top-K per turn: ~{6*avg} chars (~{6*avg//4} tokens) at K=6')
print(f'  By category (top 5):')
for cat, (sz, cnt) in sorted(by_cat.items(), key=lambda x: -x[1][0])[:5]:
    print(f'    {sz:>6} chars ({cnt:>2} skills) {cat}')

# --- Disabled skills (savings) ---
with open(os.path.expanduser('~/.hermes/config.yaml')) as fh:
    cfg = yaml.safe_load(fh)
disabled = cfg.get('skills',{}).get('disabled',[])
print(f'  Disabled: {len(disabled)} skills (saves ~{len(disabled)*avg} chars)')

# --- Compression config ---
comp = cfg.get('compression',{})
print(f'  Compression: threshold={comp.get(\"threshold\")}, target_ratio={comp.get(\"target_ratio\")}, protect_last={comp.get(\"protect_last_n\")}')
"
```

For memory provider counts (if Mnemosyne is installed):

```bash
python3 -c "
import sqlite3, os, glob
for db in glob.glob(os.path.expanduser('~/.hermes/**/mnemosyne.db'), recursive=True):
    conn = sqlite3.connect(db); c = conn.cursor()
    for t in ['working_memory','episodic_memory','canonical_facts','memoria_facts']:
        try:
            c.execute(f'SELECT COUNT(*) FROM {t}'); print(f'  {t}: {c.fetchone()[0]} rows')
        except: pass
    conn.close()
"
```

**Done:** every overhead source measured with a char count and token estimate.

### 2. Rank by cost

Sort all sources by tokens per turn. The typical ranking:

1. **Tool schemas** — largest fixed cost. Scales with enabled toolset count.
2. **Behavioral rules + system prompt** — fixed text.
3. **Mandatory skills** — full SKILL.md body per mandatory skill.
4. **Memory + user profile** — static blocks.
5. **Deferred tool catalog** — name + description per deferred tool.
6. **Skill descriptions** — skill-retrieval top-K injection.
7. **Memory provider context** — dynamic recall, 5 by default.

**Done:** sources ranked. Top 3 are the optimization targets.

### 3. Act on top consumers

**Tool schemas (largest fixed cost):**
- Audit enabled toolsets: `hermes tools` in the dashboard
- Disable unused toolsets (each removes 1-3 tool schemas from every turn)
- Use `platform_toolsets.cli` in config.yaml to control per-profile toolset access
- Prefer deferred tools (loaded on demand) over always-on tools

**Memory blocks:**
- Load `skill_view(name='hermes-compression-tuning')` for compression tuning
- Prune memory entries that are stale or duplicated
- Keep the memory block under its budget — if full, batch-remove stale entries before adding new ones

**Skill descriptions:**
- Disable unused skills in `config.yaml` under `skills.disabled` — each removed skill saves ~200 chars from the retrieval index
- Keep descriptions under 60 chars (the system-prompt budget) — longer descriptions are truncated and waste tokens without improving routing

**Memory provider (if installed):**
- Run consolidation to move working to episodic, reducing the working set
- Invalidate stale facts
- Lower the recall `limit` parameter if context is tight

**Done:** at least one optimization applied to each top-3 source.

### 4. Verify the delta

Re-run the audit script from step 1. Compare token estimates before and after.

**Done:** before/after delta reported. If no meaningful reduction, the remaining overhead is structural (system prompt + behavioral rules) and cannot be reduced without config changes.

## Pitfalls

| Problem | Cause | Fix |
|---------|-------|-----|
| Audit script returns 0 skills | YAML frontmatter parse fails on multi-line descriptions | Use regex `re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)` not `text.index` |
| Disabling a toolset breaks a workflow | A skill depends on that toolset | Check `requires_toolsets` in the skill's frontmatter before disabling |
| Memory pruning removes a needed fact | Aggressive removal without checking last-used | Check recall_count and last_recalled before removing |
| Compression triggers too early | `threshold` set too low | Raise it for longer context windows, but watch for quality degradation |
| Compression triggers too late | `threshold` set too high | Lower it — but compression summaries themselves cost tokens |
| Mandatory skill overhead seems unavoidable | It is configured in behavioral rules | Accept the cost, or remove the mandatory load requirement in config |

## Verification

- Re-run audit script — confirm token estimates dropped
- `hermes tools` — confirm only needed toolsets enabled
- Memory block — confirm under budget
- Memory provider counts — confirm working set reduced after consolidation
- Monitor next session: quality should not degrade from reduced context