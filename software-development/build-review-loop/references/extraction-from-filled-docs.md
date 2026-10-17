# Fill-Template Extraction Design Notes

Domain depth for template extraction from filled documents (.docx mail-merge reverse direction). Load when designing or reviewing extraction logic (instance grouping, tokenisation, collapse, document XML validity).

## Grouping / fingerprinting

- **Fingerprints must carry structural context, not just text shape** — if a fingerprint substitutes typed values with a placeholder and keeps nothing else, `INV-2001` in column 1 and `$10.00` in column 2 hash identically and align as one role. Fold the record's location (table index, column index, section, header/footer) into the fingerprint so cells in different columns can never align as one role. Table rows align as instances; columns as roles.

- **Repeated constant text is not an instance role** — boilerplate repeated once per letter (`Thank you.` ×N) has a repeating fingerprint with NO typed-value variation. Gate role selection on variation: a fingerprint is a role only if its occurrences carry DIFFERENT typed values. Constant-only repeats stay boilerplate; when nothing varies anywhere, distinguish "collapsed because nothing varied" from "genuinely one instance" before promoting constants to tokens — otherwise byte-identical letters produce every value tokenised (the inverse of the intended rule).

- **Instance count from min(counts) under-counts when boilerplate aliases inflate one group** — compute the instance count from role fingerprints (varying groups) only.

## Document mutation (collapse)

- **Never run collapse before slots are computed** — if token extraction yields zero tokens (pattern mismatch, untyped variation), collapsing still deletes instance 1..n-1 content: destructive output that reports `status: no-tokens` as if it were merely uninformative. Compute slots first; collapse only when slots survived; otherwise save the untouched copy.

- **Table collapse must preserve XML validity and unclaimed content** — deleting `<w:p>` from a `<w:tc>` leaves a schema-invalid cell (CT_Tc requires at least one `<w:p>`; Word offers "repair"). Delete a whole `<w:tr>` only when EVERY non-empty paragraph in it is a claimed extra-instance record; otherwise keep the row, remove only matched paragraphs (maintaining one `<w:p>` per cell), and emit an uncertain note — unclaimed cells carry the recipient's unique data.

- **Dedupe records by underlying XML identity** — linked headers/footers (`is_linked_to_previous`) return the SAME underlying paragraph object for every inheriting section; collecting it twice makes collapse delete the shared node, wiping the letterhead from all sections. Dedupe by `id(paragraph._p)` (or the lxml element id) at collection time; never delete a paragraph still retained by instance 0.

- **lxml elements have no value equality** — comparing them with `==` is identity comparison. Use a set of `id(...)`.

## Security / correctness gates

- **`name=`-style output parameters are a path-escape vector** — reject names containing `/`, `\`, `..` segments, or absolute forms; assert resolved outputs stay under the output dir. Verified escape: `name='../../evil'` wrote files outside the output directory.

- **Hard links defeat realpath-based self-overwrite guards** — `os.path.realpath(dest) == realpath(src)` is false for a hard link (different path, same inode), and `Document.save()` truncates the shared inode, corrupting the source. Guard with `os.path.samefile(src, dest)` on existing destinations (template and CSV), not realpath comparison.

- **Silent no-ops must not look like success** — a token-free document must return an explicit status (`no-tokens`), never a 0-byte skeleton; an empty skeleton carries no signal about why it is empty (write zero bytes and let the status carry the meaning).

- **Unaligned instance-unique paragraphs leak recipient data if kept as boilerplate** — a paragraph belonging to only one instance (a personal PS) is neither tokenised nor collapsed, so it lands in the template and ships that recipient's data in every generated document. Record every unaligned record under `uncertain` at minimum.

- **not_found slots must be dropped from tokens/data/mapping** — a slot whose value could not be located (e.g. inside a hyperlink) left in the mapping silently fills other recipients' letters with the wrong person's data.

## Reviewer traps observed

- Isolated guard-helper probes can show a leak the guarded call path already prevents — probe through the public entry point, and check EVERY call site of a guard (env and headers in the same converter are separate paths).
- Fixing one failure mode can trade it for its inverse (e.g. "deletes second letter" → "tokenises everything"). After a grouping fix, re-test BOTH the original failing case and the case the old code got right.

## Promote/broadcast semantics (Sep 2026 agent-skills loop)

- **Constant promotion is single-instance-only** — in aligned repeating instances, an invariant value (fee $5.00 identical in every letter) is a CONSTANT, not a token. Promotion logic must fire only on the single-instance fallback path, never on the aligned multi-instance path (where identical values across instances mean boilerplate).
- **Singleton header/footer slots must broadcast to every skeleton row** — a header slot appears once in the document but belongs to every record; populate all rows with the same value, or refill reports the slot missing for rows 2..n.
- **Diagnostics are an output surface for secrets too** — validation errors that echo raw argument values (path containment checks) leak credential-shaped values into reports and logs before masking runs. Report index + violation class only ("args[1]: path escapes plugin root"), never the value.
- **Container type-checks before coercion** — `list(str)` char-splits ("--port=3000" → 11 single-char args). Validate the container is a JSON array of strings at the config edge; reject objects/strings cleanly.
- **A fix's own validation can create a new leak** — a new arg-validation path (dot-command rejection) became the leak vector (raw value in the error text). Every new diagnostic path must construct error text from index + violation class only.
