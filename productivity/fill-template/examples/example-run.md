# Worked example — mail-merge a confirmation letter over a list

A fictional, illustrative run. No binary templates are shipped — bring your own master `.docx`/`.xlsx`
and a data table. This shows the tokenise → confirm → generate flow end to end.

## The inputs (you supply these)

- **Master:** `Letter_master.docx` — a one-page letter that reads, in part:
  > Dear Ms Jordan Lee,
  > We confirm your subscription of **$1,000,000**, effective **01 Jul 2026**. Your reference is
  > **REF-0001**.
- **Data:** `recipients.csv` with a header row:

  ```csv
  Recipient,Amount,EffectiveDate,Reference
  Ms Jordan Lee,1000000,2026-07-01,REF-0001
  Mr Sam Okafor,2500000,2026-07-01,REF-0002
  Dr Mei Chen,500000,2026-07-08,REF-0003
  ```

## 1–2. Analyse, then propose tokens

```python
from fill_template import read_content, tokenise, tokens_in, load_rows, generate

print(read_content("Letter_master.docx"))   # eyeball the varying parts
```

Proposed tokens (note `Recipient` differs from the name in the letter, so it's mapped later):
`Ms Jordan Lee → {{Name}}`, `$1,000,000 → {{Amount}}`, `01 Jul 2026 → {{EffectiveDate}}`,
`REF-0001 → {{Reference}}`.

## 3. Confirm, then tokenise

After the user signs off the token list:

```python
rep = tokenise("Letter_master.docx", "Letter_tokenised.docx",
               [{"find": "Ms Jordan Lee", "token": "Name"},
                {"find": "$1,000,000",    "token": "Amount"},
                {"find": "01 Jul 2026",   "token": "EffectiveDate"},
                {"find": "REF-0001",      "token": "Reference"}])
print(rep["not_found"])         # must be empty before generating
print(tokens_in("Letter_tokenised.docx"))   # {'Name','Amount','EffectiveDate','Reference'}
```

## 4–5. Load data and generate one file per row

```python
headers, rows = load_rows("recipients.csv")

report = generate(
    "Letter_tokenised.docx", rows,
    token_to_column={"Name": "Recipient"},     # token Name ← column Recipient; the rest match
    outdir="out",
    name_pattern="Letter_{Recipient}",
)
```

`1000000` renders as supplied (format the column in the data file if you want `$1,000,000`);
`2026-07-01` renders as **01 Jul 2026**.

## 6. Report back

```
3 files written to out/:
  out/Letter_Ms Jordan Lee.docx
  out/Letter_Mr Sam Okafor.docx
  out/Letter_Dr Mei Chen.docx
unmapped_tokens: []      missing (per file): none
```

If any token had no value for a row, that file would contain a visible `«MISSING: Token»` flag and the
report would list it — fix the data or the mapping and re-run rather than hand-editing the output.
These are **drafts for a person to review** before they go out.
