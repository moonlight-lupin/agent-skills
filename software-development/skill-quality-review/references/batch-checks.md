# Batch Checks — Automated SKILL.md Quality Checks

Run these as an `execute_code` block. Each produces a structured report. Collect findings into MAJOR / MINOR / NIT severity buckets.

## Contents

- Pre-flight
- Check 1: Frontmatter validation
- Check 2: Description identity leakage
- Check 3: Trigger ratio
- Check 4: Completion criteria
- Check 5: Structure gaps
- Check 6: Name match
- Check 7: Boilerplate duplication
- Check 8: Cross-sibling consistency
- Check 9: No-op prose
- Bulk frontmatter fix script
- Check 10: "Use when" description prefix (from Aug 2026 review)
- Check 11: `metadata.hermes` nesting (from Aug 2026 review)
- Check 12: Literal duplicate lines (from Aug 2026 review)
- Check 13: Two-loads mismatch (from Aug 2026 review)
- Check 14: Contradictory DEFAULT labels (from Aug 2026 review)

## Pre-flight

```python
import re, pathlib, yaml
repo = pathlib.Path("<repo-root>")
skills = sorted(repo.rglob("SKILL.md"))
```

## Check 1: Frontmatter validation

```python
for skill_md in skills:
    content = skill_md.read_text()
    m = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    fm = yaml.safe_load(m.group(1)) if m else {}
    missing = [f for f in ['name','description','version','author','license','metadata'] if f not in fm]
    desc_len = len(str(fm.get('description','')))
    has_trigger = 'Use when' in str(fm.get('description',''))
    issues = []
    if missing: issues.append(f"missing: {missing}")
    if desc_len > 1024: issues.append(f"desc OVER LIMIT ({desc_len})")
    if not has_trigger: issues.append("no 'Use when'")
    status = "OK" if not issues else "FAIL"
    print(f"{status} {skill_md.parent.name:35s} desc={desc_len:5d} {'; '.join(issues)}")
```

## Check 2: Description identity leakage

Identity phrases that belong in the body, not the invocation surface:

```python
identity = ['intent-first','deterministic','computed locally','local engine',
            'never invents','standalone','ships presets','self-sufficient',
            'draft for review','drafts not advice','decision-support',
            'human-in-the-loop','no other toolkit']
for skill_md in skills:
    content = skill_md.read_text()
    m = re.search(r'description:\s*(?:>-)?\n(.*?)(?=\n---|\nversion)', content, re.DOTALL)
    desc = m.group(1) if m else ""
    leaked = [i for i in identity if i.lower() in desc.lower()]
    if leaked:
        print(f"  {skill_md.parent.name}: {leaked}")
```

## Check 3: Trigger ratio

Trigger content should be >= 25-30% of description chars. Lower means identity is crowding out invocation.

```python
for skill_md in skills:
    content = skill_md.read_text()
    m = re.search(r'description:\s*(?:>-)?\n(.*?)(?=\n---|\nversion)', content, re.DOTALL)
    desc = re.sub(r'\s+', ' ', m.group(1).strip()) if m else ""
    triggers = re.findall(r'"([^"]+)"', desc)
    trigger_chars = sum(len(t) for t in triggers)
    pct = trigger_chars * 100 // len(desc) if desc else 0
    if pct < 25:
        print(f"  {skill_md.parent.name}: {pct}% (low)")
```

## Check 4: Completion criteria

Each numbered step should end on a checkable "Done when" criterion.

```python
for skill_md in skills:
    content = skill_md.read_text()
    steps = re.findall(r'### \d+\s*[-]\s*', content)
    done_when = content.count("Done when")
    if len(steps) > 0 and done_when == 0:
        print(f"  {skill_md.parent.name}: {len(steps)} steps, 0 completion criteria")
```

## Check 5: Structure gaps

```python
for skill_md in skills:
    content = skill_md.read_text()
    missing = [s for s in ['## Files','## Common Pitfalls'] if s not in content]
    if missing:
        print(f"  {skill_md.parent.name}: missing {missing}")
```

## Check 6: Name match

```python
for skill_md in skills:
    content = skill_md.read_text()
    dir_name = skill_md.parent.name
    m = re.search(r'^name:\s*(.+)', content, re.MULTILINE)
    fm_name = m.group(1).strip() if m else "?"
    # Check against common prefix patterns
    prefixes = ['', 'fpa-', 'data-']
    expected_names = [f"{p}{dir_name}" for p in prefixes]
    if fm_name not in expected_names:
        print(f"  MISMATCH: {dir_name} -> {fm_name}")
```

## Check 7: Boilerplate duplication

```python
import difflib
sections = ['## Principles','## Data handling','## Feedback','## Trust','## Boundaries']
for section in sections:
    texts = []
    for s in skills:
        content = s.read_text()
        m = re.search(rf'{re.escape(section)}\n(.+?)(?=\n## |\Z)', content, re.DOTALL)
        if m:
            texts.append((s.parent.name, m.group(1).strip()))
    if len(texts) > 2:
        base = texts[0][1]
        identical = sum(1 for _, t in texts if t == base)
        if identical > 2:
            print(f"  {section}: {identical}/{len(texts)} identical")
```

## Check 8: Cross-sibling consistency

```python
conventions = {
    'British English': ['colour','organisation','behaviour','analyse'],
    'DD MMM YYYY': ['DD MMM YYYY'],
    'License type': ['MIT','Proprietary','Apache'],
}
for conv_name, markers in conventions.items():
    found = sum(1 for s in skills if any(m.lower() in s.read_text().lower() for m in markers))
    if found < len(skills):
        print(f"  {conv_name}: {found}/{len(skills)}")
```

## Check 9: No-op prose

```python
no_ops = ['be careful','be thorough','best practices','use caution','be mindful',
          'make sure','ensure that','it is important','note that']
for skill_md in skills:
    found = [n for n in no_ops if n in skill_md.read_text().lower()]
    if found:
        print(f"  {skill_md.parent.name}: {found}")
```

## Bulk frontmatter fix script

When adding version/author/license/metadata to many files at once:

```python
tags_map = {
    # "<skill-dir-name>": [<tag>, <tag>, ...],
}
related_map = {
    # "<skill-dir-name>": [<related-skill>, ...],
}

for skill_md in sorted(repo.rglob("SKILL.md")):
    content = skill_md.read_text()
    dir_name = skill_md.parent.name
    skill_tags = tags_map.get(dir_name, ["<category>", "finance"])
    skill_related = related_map.get(dir_name, [])

    has_version = bool(re.search(r'^version:\s*\S', content[:500], re.MULTILINE))

    if has_version:
        content = re.sub(
            r'version:\s*[^\n]*',
            'version: 1.0.0\nauthor: <Author>\nlicense: <License>\n'
            'metadata:\n  hermes:\n'
            f'    tags: {skill_tags}\n'
            f'    related_skills: {skill_related}',
            content, count=1
        )
    else:
        parts = content.split('---\n', 2)
        new_fields = (
            f'version: 1.0.0\n'
            f'author: <Author>\n'
            f'license: <License>\n'
            f'metadata:\n  hermes:\n'
            f'    tags: {skill_tags}\n'
            f'    related_skills: {skill_related}\n'
        )
        content = f"---\n{parts[1]}{new_fields}---\n{parts[2]}"

    skill_md.write_text(content)
```

## Check 10: "Use when" description prefix (from Aug 2026 review)

Every model-invoked skill's description should start with "Use when". This was missing in 6/6 self-developed skills reviewed.

```python
for skill_md in skills:
    content = skill_md.read_text()
    m = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    fm = yaml.safe_load(m.group(1)) if m else {}
    desc = str(fm.get('description', ''))
    has_disable = 'disable-model-invocation' in m.group(1)
    if not has_disable and not desc.strip().startswith('Use when'):
        print(f"  FAIL {skill_md.parent.name}: description does not start with 'Use when'")
```

## Check 11: `metadata.hermes` nesting (from Aug 2026 review)

Skills should have `metadata: hermes: tags: [...]` and `metadata: hermes: related_skills: [...]`.

```python
for skill_md in skills:
    content = skill_md.read_text()
    m = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    fm = yaml.safe_load(m.group(1)) if m else {}
    issues = []
    if 'metadata' not in fm:
        issues.append("missing metadata")
    elif 'hermes' not in fm.get('metadata', {}):
        issues.append("missing metadata.hermes")
    else:
        h = fm['metadata']['hermes']
        if 'tags' not in h: issues.append("missing tags")
        if 'related_skills' not in h: issues.append("missing related_skills")
    if issues:
        print(f"  FAIL {skill_md.parent.name}: {'; '.join(issues)}")
```

## Check 12: Literal duplicate lines (from Aug 2026 review)

Copy-paste errors produce literal duplicate lines — duplicate table rows or verbatim-copied pitfall bullets.

```python
from collections import Counter
for skill_md in skills:
    content = skill_md.read_text()
    lines = [l for l in content.split('\n') if l.strip()]
    dupes = [line for line, count in Counter(lines).items() if count > 1]
    if dupes:
        print(f"  FAIL {skill_md.parent.name}: {len(dupes)} duplicate lines")
        for d in dupes[:3]:
            print(f"    {d.strip()[:80]}")
```

## Check 13: Two-loads mismatch (from Aug 2026 review)

A skill whose body says "don't load per-session" or "bake into SOUL.md" but has no `disable-model-invocation: true` flag.

```python
for skill_md in skills:
    content = skill_md.read_text()
    m = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    fm_text = m.group(1) if m else ""
    body = content[m.end():] if m else content
    anti_load = any(s in body.lower() for s in ['soul.md', "don't load", 'bake into', 'not loading', 'already injects'])
    has_disable = 'disable-model-invocation' in fm_text
    if anti_load and not has_disable:
        print(f"  FAIL {skill_md.parent.name}: body says don't load per-session, no disable-model-invocation flag")
```

## Check 14: Contradictory DEFAULT labels (from Aug 2026 review)

Multiple items in the same table or section labeled "DEFAULT" for the same task category.

```python
for skill_md in skills:
    content = skill_md.read_text()
    defaults = re.findall(r'\(DEFAULT[^)]*\)', content)
    if len(defaults) > 1:
        # Check if they're in the same table (within 20 lines of each other)
        lines = content.split('\n')
        default_lines = [i for i, l in enumerate(lines) if 'DEFAULT' in l and '|' in l]
        for i in range(len(default_lines) - 1):
            if default_lines[i+1] - default_lines[i] < 20:
                print(f"  WARN {skill_md.parent.name}: multiple DEFAULT labels in same table")
                break
```

When fixing identity leakage:
- **Keep:** opening one-liner (what it does), quoted trigger phrases, NOT-for disambiguators, reach clauses
- **Cut:** behavioral identity ("intent-first", "deterministic", "local engine", "never invents"), "Decision-support; a qualified person reviews", "Draft for review, not advice", "Standalone -- no other toolkit required"
- **Target:** triggers >= 30% of description chars, total <= 800 chars
- **Verify:** `len(desc) <= 800` and no identity phrases remain