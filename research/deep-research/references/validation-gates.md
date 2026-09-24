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

- `validate-report`: required sections (including **Contradictions** and
  **Gaps** — both mandatory), no placeholder text (TBD/TODO/truncation),
  research-stats block present, evidence key legend under Sources.
- `verify-citations`: every inline `[N]` resolves to a Sources row, every row
  is cited, URLs well-formed, suspicious generic-title patterns flagged, no
  citation ranges.
- `verify-claims --strict`: every factual claim's stored evidence snippet must
  actually support it (deterministic token/number/year/entity overlap; a
  contradicting figure or year caps the score below supported). Exit 1 on
  unsupported factual claims — fix the claim or add real evidence, never the
  score. `--provider-used <provider>` records the search provider actually
  used (e.g. `donsetch`) into `run_manifest.json`; pass it on the final
  verify-claims run.

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
python3 <skill_dir>/scripts/research_validation.py init-run --dir <run_dir> --query "<question>" --provider donsetch|auto
python3 <skill_dir>/scripts/research_validation.py register-source --dir <run_dir> --json '{"url": "...", "title": "...", "quality": "primary"}'
python3 <skill_dir>/scripts/research_validation.py add-claim --dir <run_dir> --json '{"claim_id": "c1", "claim": "...", "kind": "factual|interpretive|projective|synthesis", "snippet": "exact quote", "source_id": "<from register-source>"}'
python3 <skill_dir>/scripts/research_validation.py add-evidence --dir <run_dir> --json '{"claim_id": "c1", "snippet": "second corroborating quote", "source_id": "..."}'
```

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
- Format variants count as different figures ("2.4b" ≠ "2.4bn") — write
  figures in one format per report.
- A yearlike value adjacent to a magnitude word is treated as prose.
- Digit runs inside product names ("iPhone15", "v2000") are figures, not years.

## Tests

`tests/test_deep_research_gates.py` (plugin root) — 78 tests covering the
evidence store, claim-support scoring, citation verification, and structure
validation. Run with `python3 -m pytest tests/test_deep_research_gates.py`.