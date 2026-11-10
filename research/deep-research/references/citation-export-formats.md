# Export Format Specifications

The export command is:

```bash
python scripts/source_db.py export --topic TOPIC --format markdown|bibtex|csv|json [--output FILE]
```

If `--output` is omitted, the export is written to stdout. If an output path is
provided, give that file path to the user.

## Markdown

Markdown export groups sources by topic and renders each source as:

```markdown
## ai regulation
- [AI Act Implementation Timeline](https://example.org/ai-act) — Primary timeline source (2026-07-06)
- [Commission FAQ](https://example.org/faq) — Clarifies reporting obligations (2026-07-06)
```

Rules:

- Heading: `## {topic}`.
- Entry: `- [Title](URL) — notes (accessed_at)`.
- If title is missing, the URL is used as link text.
- If notes are missing, `No notes` is used.

## BibTeX

BibTeX export emits one `@misc` entry per source:

```bibtex
@misc{source1_ai_act_implementation_timeline,
  title={AI Act Implementation Timeline},
  url={https://example.org/ai-act},
  note={Primary timeline source},
  urldate={2026-07-06}
}

@misc{source2_commission_faq,
  title={Commission FAQ},
  url={https://example.org/faq},
  note={Clarifies reporting obligations},
  urldate={2026-07-06}
}
```

Rules:

- Entry type: `@misc`.
- Key: generated from source id plus a title/url slug.
- Fields: `title`, `url`, `note`, `urldate`.
- Missing notes fall back to a topic note.

## CSV

CSV export uses this exact header order:

```csv
id,url,title,topic,source_type,accessed_at,notes,verified,last_checked
1,https://example.org/ai-act,AI Act Implementation Timeline,ai regulation,report,2026-07-06,Primary timeline source,1,2026-07-06
2,https://example.org/faq,Commission FAQ,ai regulation,web,2026-07-06,Clarifies reporting obligations,1,
```

Rules:

- `verified` is written as `1` or `0`.
- `session_id` and `url_normalized` are not included in CSV to keep the table compact.
- Use JSON export when all fields are required.

## JSON

JSON export emits an array of full source objects:

```json
[
  {
    "accessed_at": "2026-07-06",
    "id": 1,
    "last_checked": "2026-07-06",
    "notes": "Primary timeline source",
    "session_id": "research-2026-07-06",
    "source_type": "report",
    "title": "AI Act Implementation Timeline",
    "topic": "ai regulation",
    "url": "https://example.org/ai-act",
    "url_normalized": "https://example.org/ai-act",
    "verified": true
  }
]
```

Rules:

- Boolean `verified` is rendered as JSON `true`/`false`.
- All database fields are included.
- Output is pretty-printed with stable key ordering for readable diffs.
