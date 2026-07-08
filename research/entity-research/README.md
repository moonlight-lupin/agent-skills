# entity-research

Background-research skill for AI agents: turn a company or person name into a **cited dossier** —
identity, ownership, adverse media, sanctions/PEP **signals**, and litigation — for a human to review.

**Research and compilation, not a determination.** It never screens, clears or blocks anyone; a
sanctions/PEP name-match is a *signal to escalate* to a qualified compliance/AML function.

## Structure

```
entity-research/
├── SKILL.md                          # Workflow: 6 research lenses, sources, the signal-not-determination rule
├── scripts/
│   └── entity_research.py            # screen_lists (public sanctions name-match), dossier builder, --self-test
└── references/
    ├── research-lenses.md            # Per-lens checklist, query patterns, source weighting
    └── boundaries-and-sanctions.md   # The lists, signal-not-determination, false positives, privacy guardrails
```

## Requirements

- Python 3.8+ (stdlib only for the bundled helpers).
- Session **web search + fetch** tools for the research lenses (provided by the host agent).
- **Network** for `screen_lists` (fetches OFAC / UK-OFSI / UN public lists). `python
  scripts/entity_research.py --self-test` runs an offline self-test.
- Optional: `PDL_API_KEY` + the `people-enrichment` skill for ownership/people depth.

## Boundaries

`screen_lists` does token-based name matching against partial public lists — it is **not** a
fuzzy/phonetic professional screening tool. A no-match is **not** a clearance, and a match is **not** a
finding; verify with a compliance function. Research people only for a legitimate purpose, from public
information.

## License

MIT
