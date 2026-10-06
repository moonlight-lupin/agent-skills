# Skill Review Methodology — reviewing a SKILL.md package

A companion to `github-workflow/references/review-output-template.md` § "Skill Review". That file
covers the review *output format* (severity levels, strengthen pattern, actionable observations).
This file covers the *methodology* — what to grep, what to check, and the concrete fix patterns
that emerged from reviewing real skills (`image-studio` Path C, `clips-studio`).

The methodology operates on two layers: **writing-for-agents levers** (the conceptual review
framework from [Matt Pocock's writing-for-agents](https://github.com/mattpocock/skills/tree/main/skills/productivity/writing-for-agents))
that drive *why* each check matters, and the **grep checklist** that implements the checks
operationally. Run the lever audit first to find structural defects; run the greps to find
drift defects.

## Contents

- **Writing-for-agents review levers** — L1 description quality · L2 the two loads · L3 information hierarchy · L4 steps and completion criteria · L5 leading words · L6 pruning · L7 peer-matched structure · L8 cross-reference parity
- **The three-sources-of-truth problem** — SKILL.md ↔ scripts ↔ references drift
- **The grep checklist** — 12 checks: 1 model-ID parity · 2 trigger phrases vs body scope · 3 pricing rate consistency · 4 guardrail-strength asymmetry · 5 over-application safety · 6 duration/input bounds · 7 redundant matching tuples · 8 doc-vs-code formatting claims · 9 stale file references · 10 cross-surface wording (regulated domains) · 11 escape hatches · 12 brittle exact-string matching
- **Severity calibration for skill reviews**
- **The "strengthen" pattern for skill reviews**
- **Concrete fix patterns from real reviews** — generalize hardcoded subject · pricing registry completeness · duration validation · double-import cleanup · CSV date formatting gap · silent deduplication · stale docstring references · regulated-domain wording · brittle placeholder matching · expose internal helper params · context-dependent guardrail scope · cross-sibling consistency · `.env` export-prefix parsing · case-sensitive CLI dispatch
- **The review-to-patch workflow**
- **Writing skill test suites — the self-contained fixture pattern**
- **Cross-reference**

## Writing-for-agents review levers

Apply these before the grep checklist. Each lever names a structural property the skill should
have, the failure mode when it's missing, and how to check it.

### Lever 1 — Context pointer (description quality)

The description is the skill's top-level context pointer, always loaded in the agent's context
window. Its job is **invocation** — stating what the skill is and listing the branches that
should trigger reaching it. Every word costs tokens on every turn.

**Check:**
```bash
# Does the description start with "Use when ..."?
head -20 SKILL.md | grep -c "Use when"
# Is it under 1024 chars?
python3 -c "import yaml, pathlib; fm = yaml.safe_load(pathlib.Path('SKILL.md').read_text().split('---')[1]); print(len(fm.get('description','')))"
# Does it front-load identity instead of triggers?
head -20 SKILL.md | grep -i "description:" | grep -iv "use when"
```

**Failure modes:**
- **Identity before triggers** — opens with what the skill IS, not when to reach for it. The
  body's first paragraph covers identity; the description should cover triggers.
- **Feature list** — enumerates capabilities the body already documents. Cut identity the body
  carries.
- **Synonyms renaming one branch** — "compare models", "test these models", "A/B test" when
  they all trigger the same branch. Collapse to one trigger per branch.

### Lever 2 — The two loads

Every document and pointer spends one of two budgets:

- **Context load** — always-loaded material (description, AGENTS.md lines) costs tokens every
  turn whether or not it fires.
- **Cognitive load** — user-invoked skills (`disable-model-invocation: true`) cost zero context
  load but the human must remember they exist.

**Check:**
```bash
# Is the invocation mode correct?
grep -n "disable-model-invocation" SKILL.md
# If user-invoked, is the description stripped to a one-line summary?
grep -c "Use when" SKILL.md  # should be 0 for user-invoked
```

**Failure mode:** a skill that the system prompt already injects (like a behavior stack baked
into SOUL.md) still carries a model-invoked description — pure redundant context load. Make it
user-invoked or remove the description.

### Lever 3 — Information hierarchy

A skill is built from **steps** (ordered actions) and **reference** (definitions, rules, facts
consulted on demand). The hierarchy, ranked by immediacy:

1. **In-file step** — primary tier: what the agent does, in order.
2. **In-file reference** — consulted on demand.
3. **Disclosed reference** — pushed into a linked file, loaded only when a pointer fires.

**Check:**
```bash
# Is the skill over 15k chars (sprawl)?
wc -c SKILL.md
# Are there sections that are reference material sitting at primary tier?
grep -n "^## " SKILL.md  # look for sections that are definitions, not steps
# Does bulky branch-specific material have a pointer to a reference file?
grep -c "references/" SKILL.md
```

**Failure modes:**
- **Sprawl** — too long even when every line is live. Cure: disclose reference behind pointers,
  split by branch or sequence.
- **Build history / changelog sediment** — shipped-batch logs, commit hashes, per-phase review
  findings. This is project history, not operational guidance. Move to `references/build-history.md`
  or delete. The skill should describe current state, not project evolution.
- **Scattered reference** — a concept's definition, rules, and caveats spread across sections
  instead of co-located under one heading. Reading one part should bring its neighbours.

### Lever 4 — Steps and completion criteria

Every step ends on a **completion criterion** — the condition that tells the agent the work is
done. Two properties make it a lever:

- **Clarity** — can the agent tell done from not-done? A vague bound ("understanding reached")
  invites premature completion.
- **Demand** — how much it requires. "Every modified model accounted for" forces thorough work
  where "produce a change list" does not.

**Check:**
```bash
# Do steps have explicit completion criteria?
grep -in "done when\|completion criterion\|verify\|check:" SKILL.md
# Are criteria checkable vs vague?
grep -in "understand\|review\|ensure\|consider" SKILL.md  # vague verbs
```

**Failure mode:** a step says "write down the boundaries" without specifying what "done" looks
like. Add: "**Done when** every changed boundary has a row in the integration-boundaries table."

### Lever 5 — Leading words

A **leading word** is a compact concept already living in the model's pretraining (e.g.
*tracer bullet*, *fog of war*, *red*, *Chesterton's Fence*) that the agent thinks with while
running the skill. It encodes a behavioural principle in the fewest tokens by recruiting priors
the model already holds. Repeated as a token, never as a sentence.

**Check:**
```bash
# Are there compact leading words used consistently?
grep -oin "Chesterton\|tracer\|red\|fog of war\|tight\|relentless" SKILL.md
# Are there restatements a single word could retire?
grep -in "fast, deterministic\|loop you believe in\|be thorough\|be careful" SKILL.md
```

**Failure mode:** a triad spelled out at three sites, or a pointer spending a sentence to gesture
at one idea — each is a passage begging to collapse into a single token. "fast, deterministic,
low-overhead" → _tight_. "a loop you believe in" → _red_.

### Lever 6 — Pruning

- **Single source of truth** — each meaning in one authoritative place. Duplication costs
  maintenance and inflates prominence.
- **No-op test** — does the sentence change behaviour versus the model's default? If not, delete
  the whole sentence. "Be thorough" when the agent is already thorough-ish is a no-op; the fix
  is a stronger word (_relentless_), not a different technique.
- **Negation** — steering by prohibition backfires (_don't think of an elephant_). Prompt the
  positive — state the target behaviour so the banned one is never spoken. Keep a prohibition
  only as a hard guardrail you can't phrase positively, paired with what to do instead.
- **Sediment** — stale layers that settle because adding feels safe and removing feels risky.

**Check:**
```bash
# Duplicated content (same meaning in 2+ places):
grep -in "^###\|^##" SKILL.md | sort | uniq -d  # duplicate headings
# Negation-based scoping:
grep -in "do not\|don't\|never\|NOT\|what this skill is not" SKILL.md
# No-op prose:
grep -in "be thorough\|be careful\|use best practices\|ensure that\|make sure" SKILL.md
# Build history / changelog sediment:
grep -in "batch\|shipped\|commit\|phase\|codex review\|opus review\|PR #" SKILL.md | head -20
```

**Failure modes:**
- A pitfall duplicated verbatim (tablina had 7 duplicated pitfalls, one 3×). Delete all but the
  first occurrence.
- A "What This Skill Is NOT" section with negation statements. Replace with a positive scope
  statement: "This skill handles X, Y, Z" instead of "This skill does NOT handle A, B, C".
- Build history with commit hashes and per-phase review findings. The skill describes current
  state, not project evolution.

### Lever 7 — Peer-matched structure (Hermes-specific)

Every Hermes skill follows the peer-matched shape:

```yaml
---
name: my-skill
description: Use when <trigger>. <one-line behavior>.
version: 1.0.0
author: <author>
license: MIT
metadata:
  hermes:
    tags: [short, descriptive, tags]
    related_skills: [other-skill, another-skill]
---
```

**Check:**
```bash
# Are all frontmatter fields present?
python3 -c "
import yaml, pathlib
fm = yaml.safe_load(pathlib.Path('SKILL.md').read_text().split('---')[1])
for f in ['name','description','version','author','license']:
    assert f in fm, f'MISSING: {f}'
assert 'metadata' in fm and 'hermes' in fm['metadata'], 'MISSING: metadata.hermes'
for f in ['tags','related_skills']:
    assert f in fm['metadata']['hermes'], f'MISSING: metadata.hermes.{f}'
print('Frontmatter OK')
"
# Does the structure match peers?
grep -c "^## Overview" SKILL.md       # should be 1
grep -c "^## When to Use" SKILL.md    # should be 1
grep -c "^## Common Pitfalls" SKILL.md # should be 1
grep -c "^## Verification" SKILL.md   # should be 1
```

**Failure modes:**
- Tags/related_skills at root YAML level instead of nested under `metadata.hermes`.
- Missing `## Overview` (jumps from frontmatter to body).
- Missing `## Verification Checklist` (no post-action verification).
- `related_skills` references that don't resolve in-repo.

### Lever 8 — Cross-reference parity

For skills with scripts, three surfaces must agree:

| File | What it holds | Drift risk |
|---|---|---|
| `SKILL.md` | Triggers, mode routing, steps, trigger phrases | Trigger phrases claim scope the body doesn't cover |
| `scripts/*.py` | Model IDs, pricing registry, argument mapping, validation | Model IDs in docs but missing from pricing dict; missing validation bounds |
| `references/*.md` | Model registries, guides, checklists, prompt skeletons | Interiors-specific language in a subject-agnostic skill; rates that don't match code |

These three must agree. They drift because each is edited at different times for different reasons.

**Check:** see the grep checklist below — each grep finds a specific drift class.

**Failure modes (from real reviews):**
- SKILL.md says "audio by default" but script sends `generate_audio=False` (clips-studio).
- SKILL.md says "Grok 4.6" but orchestrate-and-review section still says "Grok 4.5" (cursor-cli).
- Reference file lists a model as "draft default" but script and SKILL.md use a different model
  (clips-studio).

## The three-sources-of-truth problem

A skill package has three places where facts live:

| File | What it holds | Drift risk |
|---|---|---|
| `SKILL.md` | Triggers, mode routing, steps, trigger phrases | Trigger phrases claim scope the body doesn't cover |
| `scripts/*.py` | Model IDs, pricing registry, argument mapping, validation | Model IDs in docs but missing from pricing dict; missing validation bounds |
| `references/*.md` | Model registries, guides, checklists, prompt skeletons | Interiors-specific language in a subject-agnostic skill; rates that don't match code |

These three must agree. They drift because each is edited at different times for different reasons.

## The grep checklist

Run these before declaring a skill review complete. Each finds a specific class of drift.

### 1. Model ID parity (docs ↔ code)

```bash
# IDs in reference docs but missing from the script's pricing/constants:
grep -o 'fal-ai/[a-z0-9/.-]*' references/*.md | sort -u | while read id; do
  grep -q "\"$id\"" scripts/*.py || echo "MISSING FROM CODE: $id"
done

# Pricing entries in code but not documented in references:
grep -o '"fal-ai/[^"]*"' scripts/*.py | tr -d '"' | sort -u | while read id; do
  grep -q "$id" references/*.md || echo "MISSING FROM DOCS: $id"
done
```

**What you're looking for:** a model ID listed in `references/fal-models.md` as an alternative
but absent from `VIDEO_PRICING` / `IMAGE_PRICING` in the script → `--model that-id` returns "no rate
on file" and the cost log records `null`. Conversely, a pricing entry in code with no doc entry →
undocumented alternative the user won't know exists.

### 2. Trigger phrases vs body scope

```bash
# Read the description triggers, then grep the body for evidence the scope is actually handled.
# Example: description says "clean up / enhance a photo" (subject-agnostic) but body says "room".
grep -n "room\|space\|interiors\|portrait\|product\|food\|landscape" SKILL.md references/*.md
```

**What you're looking for:** the description's trigger phrases claim a scope the body doesn't
actually handle. A skill that triggers on "clean up a photo" but has a prompt skeleton hardcoded to
`[room/space]` and a discipline section about "what's out the window" will produce awkward prompts
for portraits, products, food, and landscapes.

### 3. Pricing rate consistency

```bash
# Ranges in docs (e.g. "$0.11–0.20/s") flattened to a single value in code:
grep -o '\$0\.[0-9]*' references/*.md | sort -u   # doc rates
grep -o '"rate": [0-9.]*' scripts/*.py             # code rates
```

**What you're looking for:** a doc says "$0.11–0.20/s" but the code uses a flat `$0.15` (midpoint)
with no comment noting it's a midpoint. The estimate is reasonable, but the user should know the
code uses a midpoint and the dashboard is authoritative.

### 4. Guardrail-strength asymmetry

```bash
# Find imperatives that overpower their guardrails:
grep -n "pick every\|always\|never\|must" SKILL.md references/*.md
```

**What you're looking for:** an instruction like "pick every issue the photo actually has" — the
imperative ("pick every") is strong, the guardrail ("actually has") is weak. On weaker models the
imperative wins. Check if there's a "drop if you can't see the sign" rule or a validation gate
between scan and assemble.

### 5. Over-application safety for active transformations

For each checklist row that is an *active transformation* (perspective correction, lens distortion,
chromatic aberration, crop, spot-clean, duration change, model swap), ask: **what happens if it's
applied when the issue isn't present?** Active transformations *change* a correct image/behavior —
that's an honesty violation, not a no-op.

### 6. Duration / input bounds validation

```bash
# Check if the script validates --duration, --resolution, etc. against per-model constraints:
grep -n "max.*duration\|duration.*max\|too long\|maximum\|MIN\|MAX" scripts/*.py
```

**What you're looking for:** models have max durations (Kling 2.5 Turbo = 10s, Veo ≈ 8s, Seedance
4–12s). If `--duration 60` passes the CLI parser and hits the API, it gets a confusing error from
fal instead of a clear local message. A `MAX_DURATION` dict + `_check_duration()` helper catches
over-long requests before the paid call.

### 7. Redundant matching tuples

```bash
# If the script uses substring matching (_model_has), check for redundant entries:
grep -A3 "AUDIO_MODELS\\|START_IMAGE\\|CAMERA_FIXED" scripts/*.py
```

**What you're looking for:** `("veo3.1", "kling-video/v3", "kling-video/v3/pro")` where
`"kling-video/v3/pro"` is a substring of `"kling-video/v3"` and will never independently match.

### 8. Doc-vs-code formatting claims

```bash
# Find formatting claims in docs and grep the code for the implementation:
grep -in "render.*as\\|format.*as\\|display.*as\\|DD MMM\\|ISO" SKILL.md references/*.md
# Then check if the code actually handles the data format the example uses:
grep -n "isinstance.*str\\|csv\\.DictReader\\|csv\\." scripts/*.py
```

**What you're looking for:** a doc says "dates render as DD MMM YYYY" but the code only handles
`datetime` objects. If the example uses CSV data (where dates are strings, not datetime objects),
the claim is unfulfilled — CSV dates pass through as raw ISO strings. This is caught by functional
testing with the data format the example actually uses, not just `py_compile`.

### 9. Stale file references

```bash
# Grep docstrings/comments for file references and verify they exist:
grep -oP "(?:from|see|see also) [A-Z_]+\\.md|PRINCIPLES\\.md|DESIGN\\.md" scripts/*.py | while read ref; do
  f=$(echo "$ref" | grep -oP '[A-Z_]+\\.md')
  find . -name "$f" | grep -q . || echo "STALE REF: $f referenced but not found"
done
```

### 10. Cross-surface wording consistency (regulated domains)

```bash
# For skills with a regulated-domain discipline (sanctions, compliance, legal, medical),
# grep for the key terms across ALL surfaces — SKILL.md, references, AND the script's
# user-facing strings (dossier headers, note strings, error messages):
grep -in "compliance\\|AML\\|clear\\|block\\|determination\\|fund administrator\\|escalate" \
  SKILL.md references/*.md scripts/*.py
```

**What you're looking for:** the `dossier()` function in `entity_research.py` said "escalate to
compliance / the fund administrator" but SKILL.md, `boundaries-and-sanctions.md`, and the
`screen_lists` note string all said "compliance / AML function". In a regulated domain, wording
inconsistency across surfaces is not just a style issue — "fund administrator" is a specific
fund-industry role, wrong for a generic de-branded skill. The script's user-facing strings (dossier
headers, note strings, error messages) are a **fourth source of truth** that the 3-surface model
misses — check them too.

### 11. Escape hatch not exposed

```bash
# Check if internal helpers accept parameters that the public function doesn't pass through:
grep -n "def _match\\|def screen_lists\\|threshold" scripts/*.py
```

**What you're looking for:** `_match(query, entries, threshold=0.6)` accepted a `threshold`
parameter, but `screen_lists()` called `_match(name, entries)` without passing it — so users
couldn't tune sensitivity through the public API. Any internal helper parameter that a user might
reasonably want to override (threshold, timeout, max results) should be exposed through the public
function with a matching default.

### 12. Brittle exact-string placeholder matching

```bash
# Look for exact-string comparisons against data-source placeholders:
grep -n '"-0- "\\|!= "-0- "\\|== "-0- "' scripts/*.py
```

**What you're looking for:** `_parse_ofac_sdn` checked `row[1] != "-0- "` (exact-space match). A
`"-0-"` entry *without* the trailing space would pass the check and create a fake name entry.
OFAC has changed CSV formatting before (whitespace, quoting). Fix: `row[1].strip() not in ("",
"-0-")` — handles both forms, format-agnostic. Any exact-string comparison against external data
should be `.strip()`ed and checked against both with/without-space forms.

## Severity calibration for skill reviews

| Severity | Example |
|---|---|
| 🔴 Should fix | Doc references a model the code can't price; trigger phrases claim scope the body doesn't cover |
| 🟡 Nice to fix | Undocumented endpoints in code; redundant matching tuples; double imports; missing validation bounds |
| 🟢 Minor | Cost rate uses midpoint of range without comment; example path inconsistency; no test suite |

## The "strengthen" pattern for skill reviews

When the user asks you to strengthen an observation, the depth comes from:

1. **Grep for the specific language** — `grep -n "room\|space\|interiors" references/*.md SKILL.md`
2. **Build an evidence table** — location → exact quote → why it's wrong, with line numbers
3. **Name the failure mode concretely** — "a portrait photo hitting Path C gets a prompt skeleton
   about 'rooms' and 'furniture' — the agent has no guidance for non-interiors subjects"
4. **Assess severity with reasoning** — "medium — won't crash but produces awkward prompts for the
   more common use case (phone portraits, product shots)"
5. **Propose the actual fix** — not "generalize it" but "replace `[room/space]` → `[subject]`, add
   a subject-types table with 5 rows, move the real-estate callout into the table"
6. **Draft the patch and apply it** — the user will often say "yes please"; have patches ready on a
   working branch, verified (`py_compile`, `grep` for remnants), with the diff shown before push

## Concrete fix patterns from real reviews

### Pattern: generalize a subject-hardcoded skill

**Problem:** Path C of `image-studio` triggered on "clean up a photo" (subject-agnostic) but every
instructional surface was hardcoded to interiors/real-estate — "room", "furniture", "what's out the
window", "real-estate interiors photography".

**Fix (applied in `review/path-c-generalization`):**
1. Add a **subject-types table** (Interiors, Portrait, Product, Food, Landscape) with per-subject
   "keep exactly" features and common issue row #s
2. Generalize the prompt skeleton: `[room/space]` → `[subject]`, "interiors shot" → neutral,
   "real-estate interiors photography" → "professional photography"
3. Generalize the discipline section: "what the space is" → "what the subject is"
4. Move the real-estate honesty callout into the subject table, not the default frame
5. Add a "What NOT to do" section with ❌/✅ examples and the rule: "if you cannot see the
   tell-tale sign for a row, do not include that fix"
6. Add a validation gate between scan and assemble: list selected issues + evidence to the user
   before the paid call

### Pattern: pricing registry completeness

**Problem:** `clips-studio` referenced LTX-2 and wan-pro in `fal-video-models.md` as alternatives,
but neither had a `VIDEO_PRICING` entry → `--model fal-ai/ltx-2-19b/text-to-video` returned "no rate
on file" and the cost log recorded `null`.

**Fix (applied in `review/clips-studio-fixes`):**
1. Add the missing models to `VIDEO_PRICING` with conservative `*(verify)*` rates
2. For per-megapixel models (LTX-2), add a new `per_megapixel` cost kind to `_video_cost()` —
   estimate as `1080p × 24fps × duration` megapixels × rate
3. Update the reference doc to note the code's estimation method (e.g. "falvid.py estimates ~249 MP
   for 5s/1080p@24fps → ~$0.019")
4. Cross-check: `DEFAULT_MODELS` entries must all have `VIDEO_PRICING` entries (add a test for this)

### Pattern: duration validation

**Problem:** `clips-studio` accepted `--duration 60` without validation. Models cap at 5–15s, so
fal returned a confusing API error and wasted a round-trip.

**Fix:**
1. Add a `MAX_DURATION` dict keyed by model-family substring (e.g. `"kling-video/v2.5-turbo": 10`)
2. Add a `_check_duration(model, duration)` helper that exits with a clear message citing the max
3. Wire it into all command functions after the `duration < 1` check, before any API call
4. Add a test: `_check_duration` for each model family at boundary, over-boundary, and unknown

### Pattern: double-import cleanup

**Problem:** `_build_video_args()` called `_import_deps()` + `_require_fal_key()`, then `_run()`
called them again — double import, double key check, no way to dry-run argument validation.

**Fix:**
1. Refactor `_build_video_args` to receive `fal_client` as a parameter
2. Callers (`cmd_animate`, `cmd_camera`) import once and pass it through
3. `_run` remains the single chokepoint for the API call + key check

### Pattern: CSV date formatting gap (doc-vs-code)

**Problem:** `fill-template` SKILL.md and `tokenising-guide.md` both stated "dates render as DD MMM
YYYY", but `_fmt_value()` only formatted `datetime`/`date` objects. CSV data arrives via
`csv.DictReader` as plain strings (`"2026-07-01"`), not datetime objects — so CSV dates rendered as
the raw ISO string, not `01 Jul 2026`. The documentation over-promised.

**How to catch it:** functional testing with both data formats. Create an xlsx data file (real
datetime cells) and a CSV data file (string dates), run the full pipeline, and compare outputs.
If the doc claims a formatting behavior, test it with the data format the example uses.

**Fix (applied in `review/fill-template-fixes`):**
1. Add a `_try_parse_date(s)` helper that detects ISO date strings (`YYYY-MM-DD`, `YYYY/MM/DD`)
   with month/day sanity checks (so `2026-13-01` doesn't parse)
2. Wire it into `_fmt_value()` as a fallback for string values — non-date strings pass through
3. Test edge cases: `REF-0001` (has dashes but isn't a date), `0` (zero is a real value, not
   missing), invalid month/day, already-formatted dates

**Generalization:** any skill that claims "X renders as Y" needs a functional test with the
*actual data format the example uses*, not just the format that happens to produce objects.

### Pattern: silent deduplication hiding repeated content

**Problem:** `fill-template`'s `read_content()` used a `seen` set and silently dropped duplicate
paragraphs. A name appearing in both the body and the header would show once in `read_content`
output, but `tokenise` would report 2 hits — confusing the user during the analysis step.

**Fix:** replace silent dedup with a `(×N)` count marker. Use `collections.Counter` to count
paragraph occurrences, then render repeated text once with `  (×N)` appended. The user sees every
location the tokeniser will touch. Update SKILL.md to document the `(×N)` behavior.

**Generalization:** any "analyse/read" function that deduplicates should show the count, not
silently drop. The downstream operation (tokenise, replace, generate) touches *every* occurrence —
the analysis view must reflect that.

### Pattern: stale file references in docstrings

**Problem:** `fill-template`'s `fill_template.py` docstring said "Design rules (from PRINCIPLES.md):"
but no `PRINCIPLES.md` file existed in the skill directory — the principles lived in `SKILL.md` under
`## Principles`.

**How to catch it:** grep docstrings and comments for file references and verify each exists:
```bash
grep -n "from \|see \|see also \|PRINCIPLES\|\.md" scripts/*.py | grep -v "^.*:#" | while read line; do
  # extract the referenced filename and check if it exists
  :
done
```

**Fix:** update the reference to point to the actual location (`SKILL.md ## Principles`) or drop
the parenthetical.

### Pattern: cross-surface wording consistency in regulated domains

**Problem:** `entity_research.py`'s `dossier()` function header said "escalate to compliance / the
fund administrator" but SKILL.md, `boundaries-and-sanctions.md`, and the `screen_lists` note string
all said "compliance / AML function". "Fund administrator" is a fund-industry-specific role — wrong
for a generic, de-branded skill.

**How to catch it:** the 3-surface model (SKILL.md ↔ scripts ↔ references) misses a **fourth**
source of truth: the script's user-facing strings (dossier headers, note strings, error messages).
Grep for the key regulated terms across all four surfaces and compare wording. In a regulated domain
(sanctions, compliance, legal, medical), inconsistent wording across surfaces is not just a style
issue — it can misdirect the escalation path.

**Fix (applied in `review/entity-research-fixes`):** align the dossier header to "compliance / your
AML function", matching the other three surfaces. Add a test that asserts the dossier output
contains the correct wording and does NOT contain the old wording.

### Pattern: brittle exact-string placeholder matching

**Problem:** `_parse_ofac_sdn` checked `row[1] != "-0- "` — an exact-string match including the
trailing space. A `"-0-"` entry without the trailing space would pass the check and be treated as a
real name, polluting the entries list with fake sanctions targets.

**Fix:** change to `row[1].strip() not in ("", "-0-")` — handles both `"-0- "` and `"-0-"`, and is
format-agnostic against future whitespace changes. Add tests for both placeholder forms (with and
without trailing space) to lock the fix.

**Generalization:** any exact-string comparison against external data (CSV placeholders, delimiter
sentinels, empty-field markers) should be `.strip()`ed and checked against both with/without-space
forms. External data formats drift.

### Pattern: expose internal helper parameters through the public API

**Problem:** `_match(query, entries, threshold=0.6)` accepted a `threshold` parameter for tuning
match sensitivity, but `screen_lists()` called `_match(name, entries)` without passing it — users
had no way to tune sensitivity (broader recall vs fewer false positives) through the public API.

**Fix:** add `threshold: float = 0.6` to `screen_lists()` and pass `threshold=threshold` to
`_match()`. Document the parameter in the docstring (what it controls, what lowering/raising does).
Any internal helper parameter that a user might reasonably want to override (threshold, timeout,
max results, cache TTL) should be exposed through the public function with a matching default.

## The review-to-patch workflow

This session's workflow for reviewing skills and producing patches:

1. **Clone via SSH** (PAT may lack PR read scope) → `git clone git@github.com:owner/repo.git`
2. **Diff the branches** → `git diff origin/main..origin/feature-branch --stat`
3. **Read all files** in the skill package: `SKILL.md`, every `references/*.md`, every `scripts/*.py`
4. **Run the grep checklist** above — each grep finds a specific drift class
5. **Compile the script** → `python3 -m py_compile scripts/*.py`
6. **Present the review** with severity-tagged findings (🔴/🟡/🟢), evidence tables, and fix proposals
7. **On "strengthen"**: re-grep for specific language, build evidence tables, name the failure mode,
   propose the concrete patch
8. **On "patch all"**: create a working branch, apply patches, verify (`py_compile` + tests + grep
   for remnants), show the diff, commit with a detailed message
9. **Add tests** for the fix patterns — pricing registry consistency, duration bounds, cost
   computation (per-second, per-clip, per-megapixel, audio, 4K multiplier)

## Writing skill test suites — the self-contained fixture pattern

When a skill review finds "no test suite", the tests you add should be **self-contained** — no
external files, no network, no `FAL_KEY`, no credentials. Build synthetic fixtures in a `tempfile`
directory inside the test. This pattern emerged from testing `fill_template.py`, `falvid.py`, and
`entity_research.py`:

### Structure

```python
import sys, tempfile, unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import fill_template as ft  # noqa: E402
from docx import Document  # noqa: E402
import openpyxl  # noqa: E402
```

### Fixture helpers (build the minimal input the skill needs)

```python
def _make_docx(path, paragraphs, *, header=None, footer=None):
    """Create a .docx with the given paragraph strings."""
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    if header or footer:
        section = doc.sections[0]
        if header: section.header.add_paragraph(header)
        if footer: section.footer.add_paragraph(footer)
    doc.save(str(path))

def _make_data_csv(path, headers, rows):
    """Write a CSV data file (ensure parent dir exists first)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in rows: w.writerow(row)
```

### Key lessons

1. **`Path(path).parent.mkdir(parents=True, exist_ok=True)`** before `open()` in CSV helpers —
   `tempfile.mkdtemp()` creates the directory but `open("dir/file.csv")` needs the *parent* to
   exist. Without this, 11 tests fail with `FileNotFoundError`.

2. **Force reimport when testing iteratively**: `if 'fill_template' in sys.modules: del
   sys.modules['fill_template']` — the module cache will serve the old version after you patch the
   script, making you think the fix didn't work.

3. **Test the formatting claim with the data format the example uses** — if the SKILL.md example
   uses CSV data, test with CSV (strings), not just xlsx (datetime objects). This is what caught
   the `fill-template` date formatting gap.

4. **Test edge cases that distinguish real values from missing data**: `Amount=0` should show as
   `0`, not `«MISSING»`; `REF-0001` has dashes but isn't a date; `"-0-"` without trailing space
   should be skipped by the OFAC parser. These are the cases that break in production.

5. **Registry consistency tests** — assert that every `DEFAULT_MODELS` entry has a
   `VIDEO_PRICING`/`IMAGE_PRICING` entry; assert every `MAX_DURATION` needle matches at least one
   pricing model (dead code check); assert every pricing spec has a valid `kind`. These catch
   drift between the three sources of truth at test time, not at review time.

6. **LSP import errors are expected** — `Import "fill_template" could not be resolved` is a Pyright
   static-analysis limitation (the script is in `scripts/`, not on the Python path at lint time).
   The tests pass at runtime because `sys.path.insert` handles it. Don't chase the LSP error.

### Pattern: context-dependent guardrail scope (PII / compliance stripping)

**Problem:** `people-enrichment` SKILL.md carried full compliance guardrails ("confirm legitimate
purpose", "flag GDPR / local privacy law", "keep collection proportionate", "personal data has
legal weight"). For a personal repo (not client-facing), this is overhead the user doesn't want —
they explicitly asked to "remove the PII controls".

**How to catch it:** ask the user about the deployment context before reviewing a skill with
regulated-domain guardrails. A skill shipped to a personal repo vs a client-facing product have
different compliance needs. Grep for the guardrail language:

```bash
grep -in "legitimate purpose\|GDPR\|proportionate\|privacy law\|legal weight\|sensitive.*individual" SKILL.md
```

**Fix (applied in `review/people-enrichment-fixes`):**
1. Strip the compliance/guardrail language from: description, scope, data-handling, pitfalls,
   verification checklist
2. **Keep operational security** (`.env` / API-key-as-secret handling) — that's not compliance,
   it's key management
3. Keep the functional code untouched — the enrichment logic, contact_status, PII field handling
   all stay; only the compliance *language* around them is removed
4. Re-verify after stripping: the skill should still function identically, just without the
   "confirm purpose before enriching" gates

**Generalization:** compliance guardrails are context-dependent. A skill reviewed for a regulated
client needs them; a skill for a personal repo doesn't. Ask before assuming. When stripping,
preserve operational security (key handling, secret protection) — that's not compliance overhead.

### Pattern: cross-sibling consistency (check fixes already applied to one sibling)

**Problem:** The cp1252 console encoding fix (`stream.reconfigure(encoding="utf-8")` in `main()`)
was present in `falvid.py` and `fill_template.py` but missing from `enrich.py` — three sibling skills
in the same repo (`agent_skills`). The first two got the fix in earlier reviews; the third didn't.

**How to catch it:** when reviewing a skill that has siblings (same repo, same author, similar
structure), check whether fixes applied to one are present in the others:

```bash
# In the repo root, grep across all sibling skills for a fix pattern:
grep -l "reconfigure.*utf-8" creative/*/scripts/*.py productivity/*/scripts/*.py research/*/scripts/*.py
# If some have it and some don't, that's a cross-sibling consistency gap.
```

**Fix:** apply the same fix to all siblings in one pass. The review should cover all skills in the
repo, not just the one under review. When you find a fix pattern in one sibling, grep the others.

**Generalization:** skills in the same repo by the same author share conventions (console encoding,
error handling, cost logging, test patterns). A fix applied to one should be checked against all.
This is especially true for: cp1252 fixes, `--self-test` patterns, cost-log JSONL formats, retry
logic, and `.env` key resolution.

### Pattern: `.env` parsing — `export` prefix handling

**Problem:** `load_dotenv_value` in `enrich.py` parsed `KEY=VALUE` lines but didn't handle
`export KEY=VALUE` (common in shell-style `.env` files inherited from `.bashrc` conventions). A
user who writes `export PDL_API_KEY=*** in their `.env` would get `None` — the parser looked
for key `"PDL_API_KEY"` but found `"export PDL_API_KEY"`.

**Fix:** strip the `export ` prefix before partitioning on `=`:
```python
if line.startswith("export "):
    line = line[len("export "):]
k, _, v = line.partition("=")
```

**Generalization:** `.env` parsers should handle both `KEY=VALUE` and `export KEY=VALUE` forms.
The `export` prefix is a common shell convention that leaks into `.env` files. Also handle quoted
values (`strip('"').strip("'")`) and comments (`#` lines).

### Pattern: case-sensitive CLI backward-compat dispatch

**Problem:** `enrich.py`'s backward-compat check in `main()` used `argv[0].startswith("person")` —
case-sensitive. `Person-Enrich` (uppercase P) would fail the starts-with check, enter the
backward-compat block, and produce a confusing double-subcommand error.

**Fix:** lowercase `argv[0]` before the starts-with checks:
```python
first = argv[0].lower() if argv else ""
if argv and first not in KNOWN and not first.startswith("person") and not first.startswith("company"):
```

**Generalization:** any CLI dispatch that uses `startswith` or `in` against subcommand names should
lowercase first. Subcommands are conventionally lowercase, but users type both.

## Cross-reference

- `github-workflow/references/review-output-template.md` § "Skill Review" — the review output
  format, severity guide, and the strengthen pattern. This file is the methodology companion.
- [Matt Pocock's writing-for-agents](https://github.com/mattpocock/skills/tree/main/skills/productivity/writing-for-agents)
  — the conceptual framework (context pointers, two loads, information hierarchy, completion
  criteria, leading words, pruning) that the 8 levers above operationalize. The SKILL.md and
  SKILL-MECHANICS.md are the primary source for the lever definitions.
- `hermes-agent-skill-authoring/SKILL.md` pitfalls #10–20 — cross-reference drift,
  guardrail-strength asymmetry, pricing registry completeness, input validation bounds,
  double-import cleanup, doc-vs-code formatting claims, silent deduplication, regulated-domain
  wording consistency, brittle placeholder matching, escape hatch exposure, self-contained tests.
  This file is the "full grep checklist" referenced there.
