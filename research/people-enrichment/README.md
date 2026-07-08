# people-enrichment

People Data Labs (PDL) **person & company enrichment / search** skill for AI agents — looks up profiles, work history, LinkedIn URLs and firmographics, or finds people/companies by criteria, and writes a styled `.xlsx`.

## Structure

```text
people-enrichment/
├── SKILL.md                       # Workflow doc: 5 commands, dry-run, key handling, PII/data-handling, tuning
├── scripts/
│   └── enrich.py                  # CLI: person-enrich/identify/search, company-enrich/search, --dry-run, --self-test
└── references/
    ├── sample_input.csv           # Example people input (fictional)
    └── sample_companies.csv       # Example companies input (fictional)
```

## Requirements

- Python 3.8+
- `pip install openpyxl` (HTTP uses the stdlib `urllib` — no `requests` needed)
- `PDL_API_KEY` — set as an environment variable or in a `.env` (never commit it). Get one at https://www.peopledatalabs.com
- Network access to the PDL API for live runs. `python scripts/enrich.py --self-test` and `--dry-run` run offline.

## Useful commands

```bash
python scripts/enrich.py --self-test
python scripts/enrich.py person-enrich --input people.csv --dry-run
python scripts/enrich.py person-search --company "Northwind Capital" --title director --size 25 --dry-run
python scripts/enrich.py company-enrich --input companies.csv --output firms.xlsx
```

## Data & privacy

Enrichment sends a real name/company to a third-party data provider and may return real personal data. Confirm a legitimate, proportionate purpose, keep collection relevant to that purpose, and mind GDPR / local privacy law. Do **not** scrape LinkedIn directly — this uses the licensed PDL aggregator instead.

## License

MIT
