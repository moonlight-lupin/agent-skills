# pexels-stock-photos

Search and download free real-world stock photos from the [Pexels API](https://www.pexels.com/api/).
Use when the user wants a **real photo** (not AI-generated) — for presentations,
articles, social media, or any context needing professional photography.

## Structure

```
pexels-stock-photos/
├── SKILL.md                    # Workflow doc: routing, API reference, attribution
├── README.md                   # This file
└── tests/
    └── test_skill.py           # SKILL.md frontmatter + routing-contract tests
```

## Requirements

- `curl` (pre-installed on most systems)
- `PEXELS_API_KEY` environment variable — get a free key at https://www.pexels.com/api/
- No Python dependencies required for the skill itself (curl-based)
- Python 3.11+ + `pytest` for the test suite only

## API limits

- 200 requests per hour
- 20,000 requests per month
- Free for commercial and non-commercial use
- Attribution required (photographer name + Pexels link)

## License

MIT