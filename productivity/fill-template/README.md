# fill-template

Mail-merge skill for AI agents: take **one master template** (`.docx` letter/form or `.xlsx` form)
and a **data table**, and produce **one filled file per row** — tokenise → confirm → generate, with a
never-invent MISSING flag. Fully local; generates files only.

## Structure

```
fill-template/
├── SKILL.md                       # Workflow: analyse → tokenise → confirm → generate → report
├── scripts/
│   └── fill_template.py           # Engine: read_content, tokenise, tokens_in, load_rows, generate
├── references/
│   └── tokenising-guide.md        # Choosing/naming tokens, exact-match rule, MISSING flag
└── examples/
    └── example-run.md             # Worked end-to-end run (bring your own master + data)
```

No binary templates are shipped — bring your own master `.docx`/`.xlsx` and a `.csv`/`.xlsx` data
table. The example walks through the format.

## Requirements

- Python 3.8+
- `pip install python-docx openpyxl`
- No network access and no credentials — fully local file I/O.

## License

MIT
