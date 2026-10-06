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
- Check 14 extension: Degrees of freedom (from Oct 2026 pere-toolkit review)
- Check 15: Callability — can the agent run what the skill names? (from Oct 2026 pere-toolkit review)
- Check 16: Unworkable or non-independent instructions (from Oct 2026 pere-toolkit review)
- Check 8b: Library-wide terminology (from Oct 2026 pere-toolkit review)
- Check 17: Reference hygiene (TOC, depth, orphans)
- Check 18: Workflow scaffolding — progress checklist + feedback loop
- Check 19: Evaluation coverage

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

## Check 14 extension: Degrees of freedom (from Oct 2026 pere-toolkit review)

Check 14 above catches contradictory DEFAULT labels. On pere-toolkit the costly defect was the opposite shape — skill text that offered a choice where the engine required one. Four sub-checks, run across SKILL.md + linked references:

### a) Options with no default

A step that offers a choice without picking one. Grep for choice-pair patterns:

```python
choice_patterns = [
    r'(?:or|vs\.?|either)\s+(?:last\s+quarter|last\s+year|prior)',   # "same period last year or last quarter"
    r'\b(?:Excel|Word)\s+or\s+(?:Excel|Word)\b',
    r'(?:simple|discounted)\s+payback',
    r'\bX\s+or\s+Y\b',   # generic: any two-option phrasing with no default nearby
]
```

Every "A or B" phrasing within a step must have either a stated default ("default: last quarter") or an explicit escape hatch ("user's basis determines; ask"). Anthropic's guide: give one default plus an escape hatch. Findings are MINOR on Hermes profile, and on the plugin profile they sit in the fix list ahead of mechanical fixes.

### b) Loose wording on exact steps

Where the engine or validator has an exact tolerance, the prose must state it. Patterns: "aim for a few basis points" when the validator allows 5 bp; dates "inferred"; a provision "by hand". Check by listing each validator tolerance in `scripts/` (grep for `tolerance|abs(|<=|bp`), then grep the SKILL.md for the corresponding loose phrase.

### c) Judgement hidden in engine defaults

For each function the SKILL.md cites, list keyword defaults that carry a judgement (`discount_rate=0.08`, any threshold). The SKILL.md must either mention the default or instruct "pass X and state it". Check with `inspect.signature` — a cited function with a float/threshold default that never appears in the skill text is a finding.

### d) Voodoo constants

Module-level numeric thresholds with no rationale in code or docs (e.g. `TIERS = 75 / 50` with no comment). Grep for module-level numeric assignments, then check for a nearby rationale (comment, docstring, or SKILL.md mention). Fix pattern: require a provenance register — the pattern pere-toolkit adopted (a tests file enforcing every default number cites a source, e.g. `tests/test_provenance.py`).

## Check 15: Callability — can the agent run what the skill names?

The biggest defect class the method had no check for: 39 of 52 skills in pere-toolkit (5 Oct 2026 run) cited library engines with no way to import them, scripts whose `__main__` block ignores arguments and prints a demo, or call lines with wrong names/signatures. The method's other checks test how a skill reads; this one tests whether the instructions run.

### a) Classify every cited script: CLI or library

For each script the skill cites, `def main` + a `__main__` block that calls it = CLI. Otherwise library. A library citation needs an import recipe the agent can follow from the skill's base directory (e.g. `sys.path.insert(0, str(<skill_dir> / "scripts"))` + `import confirmations`). If the text names functions with no import recipe and no call line, that is the MAJOR finding.

**Import-recipe presence (separate sub-check, mechanical):** for every skill citing a `module.function` engine call, the skill text must carry the recipe line ("Calling the engines: …" with the sys.path recipe, or an inline import instruction). The harness resolves cross-skill calls — an engine importable from a sibling skill's scripts is NOT a finding — so the recipe check is a grep, not an execution:

```python
for skill_md in skills:
    text = skill_md.read_text()
    cites_engine = re.search(r'`[a-z_]+\.[a-z_]+\(', text)   # module.func(
    has_recipe = bool(re.search(r'Calling the engines|sys\.path|import recipe', text, re.I))
    if cites_engine and not has_recipe:
        print(f"  NO-RECIPE: {skill_md.parent.name} cites engines with no import recipe line")
```

(Cross-skill citation without a recipe is still a finding on repos that lack a shared calling-engines reference — the agent cannot know to look in a sibling's scripts/ without being told.)

### b) Execute every call-like span

Extract inline code spans that look like calls (`` `name(...)` ``) and fenced `python … .py` command lines, then execute each against small made-up inputs in a scratch directory. A call line that does not run — wrong name, missing required keyword, private function, dict key cited as a function — is a MAJOR finding.

Harness: `scripts/check_calls.py` in this skill.

```bash
python3 <this-skill>/scripts/check_calls.py <repo-root>
```

It classifies scripts (CLI/library), extracts call-looking spans plus command lines, probes them in a temp dir, and flags:

- call spans naming a target that does not exist anywhere in the skill or repo
- command lines resolving to no file at the cited path
- `def main` whose `__main__` block never calls it when arguments are given (the "demo whatever you pass" bug — three pere scripts had it)
- repo-relative CLI paths (`python skills/x/scripts/y.py`) that break once the plugin is installed

Interpretation rules:

- A cited *generic signature* beside a surviving *concrete call* is NOT a finding — inspect context before reporting (this rule comes from the conciseness pass falsely flagged 7 spans).
- Exit 1 with findings, 0 clean.

### c) Fix pattern

One shared "calling the engines" reference (import recipe, per-skill module map) plus one **verified call line** per cited function, placed in the workflow step that uses it. Verified means: you ran it.

## Check 16: Unworkable or non-independent instructions

Imperatives the declared toolset simply cannot do, and sign-off gates the signer cannot honestly pass. These produce confidently wrong behaviour, not just a messy file. MAJOR.

### a) Capability check

For each imperative sentence ("Recalc in Excel to confirm", "Run confirmations.py"), ask: can the executing agent do this with the tools this skill declares? If not, the skill must say what to do instead ("mark UNVERIFIED and hand to the user"). Grep for tool names outside the skill's declared surface:

```python
unavailable = ['excel', 'word document', 'spreadsheet recalc', 'open the file in']
for skill_md in skills:
    content = skill_md.read_text()
    for line in content.splitlines():
        if any(t in line.lower() for t in unavailable):
            # does the line offer an agent-side alternative?
            if not any(t in line.lower() for t in ['instead', 'unverified', 'ask the user', 'report to']):
                print(f"  CAPABILITY: {skill_md.parent.name}: {line.strip()[:90]}")
```

### b) Independence check

For any human-review or sign-off gate, the signer must not be the author of the thing under review. On pere-toolkit the FDD (feasibility-and-development) skill's human-review line asked the FDD provider to sign off the review of its own report. Grep for sign-off/review vocabulary, then read the surrounding roles:

```python
signoff_words = ['sign off', 'sign-off', 'approval', 'human review', 'reviewer', 'confirmer']
for skill_md in skills:
    for i, line in enumerate(skill_md.read_text().splitlines()):
        if any(w in line.lower() for w in signoff_words):
            # print with context for manual role check
            print(f"  REVIEW-GATE: {skill_md.parent.name}:{i+1}: {line.strip()[:90]}")
```

Then verify: the actor named in the gate (or the party the skill routes to for that input) is not also the author of the artifact under review. Flag if it is.

### c) Cross-skill contradiction

Where skill A promises an outcome that skill B — which A routes to — forbids or gates. On pere-toolkit, getting-started promised "instant screen verdict" while deal-screening forbids instant verdicts. Check: build the routing graph (each skill's "routes to"/trigger targets), then diff every promised outcome in A against B's own gates/frequency rules.

## Check 8b: Library-wide terminology (extends Check 8, now MINOR)

Check 8 covers mechanical conventions. The expensive drift on pere-toolkit was domain: one concept under several names ("landing" / "landing view" / "latest estimate" / "LE"), and one name meaning three things ("waterfall").

### Procedure

1. Build a term inventory across sibling skills: extract domain nouns from headings, tables, and glossary lines per skill.
2. Flag two shapes:
   - **Synonyms for one concept** — N names for the same thing. Fix: one glossary reference, applied at first use.
   - **One word, several concepts.** Fix: rename the minority senses.
3. **Verify-before-flag rule (mandatory).** Two of five drift findings on pere were false alarms on inspection ("IM", "return-on-cost" — each had legitimate local usage). Require, for each skill flagged, a **usage-context quote** — the actual sentence plus neighbouring sentence — before reporting the finding. A bare term-list match is not a finding.

## Check 17: Reference hygiene (TOC, depth, orphans)

Mechanical whole-tree sweep — see SKILL.md Workflow §9 and `scripts/check_references.py` (this skill vendors it). Checks reference files are one level deep, link targets resolve, and any reference over 100 lines carries a Contents list. Run `add_toc.py` (dry-run, then `--apply`) to fix missing TOCs; re-run the checker after.

## Check 18: Workflow scaffolding

Two checks on every SKILL.md with a workflow:

- **Progress checklist**: workflows with ≥7 discrete steps should carry a copyable checklist (checkbox list the agent ticks off as it goes). Count `^\d+\.` steps inside the main workflow section; if ≥7 and no `- [ ]` checklist exists in the file, flag. (Pere-toolkit at d4e0a2c: 0 of 52 skills had one, 18 were candidates.)
- **Named feedback loop**: quality-critical skills (produce numbers, pass a validator, or review artifacts) should name their validator and the validate → fix → re-run loop. Check 4 covers "Done when"; this covers the *loop*: `validate` step + `re-run after fix` step both present. A skill with a validator but no re-run-after-fix instruction is a finding.

## Check 19: Evaluation coverage

The A/B procedure (see `references/efficacy-ab-test.md`) measures single refactors. A library also needs a coverage metric:

- Report **evals per skill** (Anthropic's suggestion: ≥3 scenarios per skill). Build from the repo's eval/tests directory: map scenario file names to skills; flag skills with zero scenarios.
- **Model scope**: record which models the plugin targets (from README/plugin.json) and test only those. A judgement-heavy skill excluded from smaller models should never be probed with them — a Haiku run on a judgement-heavy skill is noise, not signal. Record the scope decision and its rationale next to the eval plan.

## Callability + unworkable-instruction quick checklist for fixes worth catching most

When budget is tight, these two checks catch the costly defects (ranked by pere-toolkit yield — see the fix priority table in SKILL.md):

1. Check 15 harness (call lines run, demos don't masquerade as CLIs)
2. Check 16 (every imperative executable with the declared tools; every sign-off gate independent)
3. Check 14 extension (every option has a default + escape hatch; tolerances stated; hidden engine defaults surfaced)
4. Check 17 (TOCs, depth, orphans — mechanical, cheap)
