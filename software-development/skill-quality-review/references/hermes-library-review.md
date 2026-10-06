# Hermes Library Review — local-library specifics

Platform specifics for reviewing the local Hermes skill library (`~/.hermes/skills/`). The batch checks in `references/batch-checks.md` are format-agnostic and apply everywhere; this file holds only the parts that need a Hermes runtime. Other platforms: skip this file — Workflow §A is a no-op for you.

## Identify most-used skills (usage frequency)

Query the session state store for actual `skill_view` load counts. This is more reliable than `.usage.json` (which may be missing or stale).

```python
import sqlite3, json
from collections import Counter
from pathlib import Path

db = str(Path.home() / ".hermes" / "state.db")
conn = sqlite3.connect(db)
cursor = conn.cursor()
cursor.execute("SELECT tool_calls FROM messages WHERE tool_calls LIKE '%skill_view%'")
skill_counter = Counter()
for row in cursor.fetchall():
    calls = json.loads(row[0]) if row[0] else []
    if not isinstance(calls, list): calls = [calls]
    for call in calls:
        func = call.get("function", call)
        if func.get("name") != "skill_view": continue
        args = json.loads(func.get("arguments", "{}"))
        name = args.get("name", "")
        if name: skill_counter[name] += 1
# Top N
for i, (skill, count) in enumerate(skill_counter.most_common(15), 1):
    print(f"{i:2d}. {skill:45s} {count:3d} loads")
```

## Classify self-developed vs builtin

Compare the user skills directory against the Hermes installation's bundled skills:

```python
from pathlib import Path
builtin_root = Path("/usr/local/lib/hermes-agent/skills")
builtin_names = {p.parent.name for p in builtin_root.rglob("SKILL.md")}
user_root = Path.home() / ".hermes" / "skills"
for skill in top_skills:
    is_builtin = skill in builtin_names
    # Check frontmatter author field for confirmation
    ...
```

Skills with `author: Hermes Agent` or `author: Hermes Agent + Teknium` in frontmatter but NOT in the builtin tree are user-created overrides (still self-developed). Skills in the builtin tree are bundled. Everything else is self-developed.

- **Usage frequency from state.db, not .usage.json.** The `.usage.json` file may not exist or may be stale; the state.db `messages.tool_calls` query gives actual load counts across all sessions.
- **Bundled skills are protected.** They cannot be patched via `skill_manage`; recommend `hermes curator adopt <name>`.

## Curator adoption

`hermes curator adopt <name>` brings a bundled skill into the user's tree where it can be patched and reviewed. After adoption, re-run the classification step — an adopted skill is self-developed from the review's point of view.

## Personal-library profile deltas

- Descriptions up to 1024 chars and MUST be trigger-style ("Use when ...") — the BM25 retrieval has no stemming, so both trigger and capability words as literal surface forms are load-bearing.
- Size: 8-15k chars target, >20k split to references/.
- Structure: When to Use + actionable body + Common Pitfalls + Verification Checklist minimum.
- `related_skills` entries should resolve in the local library.

## Fix priority for the Hermes-library profile

Frontmatter-first remains valid here because frontmatter carries load-bearing trigger surface (see SKILL.md § Fix priority): frontmatter → description identity leakage → Check 15 callability → missing sections → completion criteria → name mismatch → pitfalls section.
