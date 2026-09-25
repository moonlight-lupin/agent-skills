# Validation Gates — Deterministic Report Verification

This reference holds the full contract for `scripts/research_validation.py`:
the evidence store, the three gates, and the failure loop. SKILL.md carries
only the pointers; this file is the source of truth.

The script is stdlib-only, deterministic, MIT like the plugin. It checks
structure, not judgment. Concepts were ported from external skill reviews;
the implementation is original.

## When to run

Every report with 5+ sources passes all three gates before delivery.

```bash
python3 <skill_dir>/scripts/research_validation.py validate-report  --report <report.md>
python3 <skill_dir>/scripts/research_validation.py verify-citations --report <report.md>
python3 <skill_dir>/scripts/research_validation.py verify-claims    --dir <run_dir> --strict --provider-used donsetch
```

- `validate-report`: required sections as `##` headings that start with the
  section name (`## Gaps and open questions` counts; `## Mind the Gaps` and
  `### Sources of revenue` do not) — including **Contradictions** and **Gaps**,
  both mandatory — no placeholder text (TBD/TODO/truncation), research-stats
  block present, evidence key legend under Sources (a missing Sources section
  no longer skips the legend check).
- `verify-citations`: every inline `[N]` resolves to a Sources row, every row
  is cited, URLs well-formed, suspicious generic-title patterns flagged, no
  citation ranges. A bracketed year (`fiscal [2024]`) is prose, not a citation,
  unless the Sources list has an entry with that number.
- `verify-claims --strict`: every factual claim's stored evidence snippet must
  actually support it (deterministic token/number/year/entity overlap; a
  contradicting figure or year caps the score below supported). Exit 1 on
  unsupported factual claims — fix the claim or add real evidence, never the
  score. `--provider-used <provider>` records the search provider actually
  used (e.g. `donsetch`) into `run_manifest.json`; pass it on the final
  verify-claims run. Three further checks, warnings by default and failures
  under `--strict`:
  - **`[VERIFIED]` independence** — a claim stored with `"basis": "verified"`
    needs its snippet and added evidence to come from sources on ≥2 different
    hosts (`www.` ignored). Otherwise add real corroboration or store it as
    `sourced`.
  - **Counter-evidence** — once the store holds 5+ sources, at least one claim
    must have `"polarity": "refute"`. If you searched and found none, pass
    `--refute-none "<what you searched>"`; the reason is kept in the manifest.
  - **Source-quality mix** — reported as `source_quality` (counts plus
    healthy / acceptable / weak, per SKILL.md §3e). `weak` adds a warning but
    never fails: flag it under Gaps.

## Loop

Validate → fix → re-run all three. Max 3 cycles. Still failing after 3 → stop
and report the remaining problems to the user honestly. Never skip the gates,
never deliver with a red gate.

For quick 2-3 source reports (no evidence store), `verify-claims` returns a
warning rather than failing — record it in the stats block.

## Evidence store (Step 3b.1)

From the first retrieval round, persist evidence to disk so it survives
context compaction. Use the store subcommands:

```bash
python3 <skill_dir>/scripts/research_validation.py init-run --dir <run_dir> --query "<question>" --mode simple|moderate|complex --provider donsetch|auto
python3 <skill_dir>/scripts/research_validation.py register-source --dir <run_dir> --json '{"url": "...", "title": "...", "quality": "primary"}'
python3 <skill_dir>/scripts/research_validation.py add-claim --dir <run_dir> --json '{"claim_id": "c1", "claim": "...", "kind": "factual|interpretive|projective|synthesis", "polarity": "support|refute|neutral", "basis": "verified|sourced|reasoned|estimated", "snippet": "exact quote", "source_id": "<from register-source>"}'
python3 <skill_dir>/scripts/research_validation.py add-evidence --dir <run_dir> --json '{"claim_id": "c1", "snippet": "second corroborating quote", "source_id": "..."}'
```

- `quality` must be `primary`, `secondary` or `tertiary`; `polarity` and
  `basis` are validated too (case-insensitive). A typo is rejected, not stored.

- `run_dir` is the report's output folder (same folder as the final report file).
- `register-source` returns a stable sha256 `source_id`; dedup is automatic
  (URL canonicalization strips tracking params).
- Add claims and evidence **during** the loop (§3d), not at the end. An
  append-only `claims.jsonl` is the fabrication-detection backbone for the
  gates.
- On context compaction, the store is ground truth — re-read `claims.jsonl`
  instead of trusting compressed memory.

## Known scoring limitations

The support scorer is deterministic token/number/year/entity overlap with
contradiction caps. Accepted limitations, by design:

- Negation and polarity are not parsed.
- Entity overlap can false-red on capitalized common nouns.
- A missing signal in the snippet (no figures, no years) caps the score
  rather than proving support.
- Magnitude abbreviations are normalised (`2.4bn` = `2.4b` = `2.4 billion`;
  `mn`/`mln`/`mm` = `m`; `tn`/`trn` = `t`), but other unit variants still count
  as different figures — write figures in one format per report.
- A yearlike value adjacent to a magnitude word is treated as prose.
- Digit runs inside product names ("iPhone15", "v2000") are figures, not years.

## Tests

`tests/test_research_validation.py` (in this skill's `tests/`) covers the
evidence store, claim-support scoring, citation verification, and structure
validation; `tests/test_gate_hardening_v180.py` covers the v1.8.0 hardening.
Run with `python3 -m pytest research/deep-research/tests/ -q`.