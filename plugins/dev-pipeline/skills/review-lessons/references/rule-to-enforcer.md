# Rule → Enforcer

The `correct` practice, adapted from Lauren Tan's pstack pack (the `correct`
skill; MIT, verified 2026-11-28): every recurring correction gets its own
enforcement level, and prose is the LAST resort, not the first.

## The ladder (fixed order)

`architecture → types → lint → CI → test → doc`

For a correction that must not recur, pick the HIGHEST level that can enforce
it mechanically:

1. **Architecture** — make the wrong thing impossible by shape (a seam callers
   cannot bypass; a module that owns the invariant). Strongest: zero review
   effort after it exists.
2. **Types** — the type system rejects the mistake at compile time (a newtype
   instead of a bare string; an enum instead of booleans).
3. **Lint** — a static rule catches the pattern (naming, forbidden imports,
   annotation requirements) before anything runs.
4. **CI** — a pipeline stage fails on the condition (a size cap, a diff-hygiene
   check, a manifest contract) even when a local run skips it.
5. **Test** — a test at a public seam fails when the property is violated.
   Weakest mechanical rung: tests can be edited, skipped, or deleted.
6. **Doc** — the rule lives as prose only, with an owner. Acceptable ONLY when
   no mechanical level can reach it — e.g. judgment calls ("is this premise
   load-bearing?"). A doc rule should name its verification (what evidence a
   reviewer looks for), or it is not a rule yet.

## Use in fix rounds

- When a reviewer finding recurs, ask first: which rung enforces it? Land the
  enforcement with the fix, not the explanation.
- When correcting the same thing a SECOND time, do not correct it twice —
  promote it one rung up the ladder.
- A lesson filed in this library that names a mechanism belongs at its rung
  instead; a rule filed twice as prose is the "second contradicting copy"
  warning in the review-lessons body.
