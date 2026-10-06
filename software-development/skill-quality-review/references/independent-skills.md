# Independent Skills When a Reference Toolkit Exists

When building an agent skill for a domain where a separate reference toolkit already exists (e.g. an accounting-toolkit repo with 34 skills and 7 foundations, or a separate audit-suite plugin), the new skill must be **independent**.

## The pattern

1. A domain has an existing, comprehensive reference toolkit (foundations, engines, playbooks).
2. A new product-specific skill is needed (e.g. an ERP agent skill that calls MCP tools).
3. The new skill covers the same domain ground but binds to a different execution layer.

## What to do

- **Study the reference toolkit** for domain coverage — read its foundations, engines, and skill playbooks.
- **Do gap analysis** — identify what the new skill's reference files miss that the reference toolkit covers.
- **Fill the gaps** into the new skill's own reference files with original content.
- **No cross-references** — do not link to the reference toolkit repo, do not mention it by name, do not say "see accounting-toolkit/foundations/doctrine.md".
- **The skill stands on its own.** A user who installs only the new skill gets full domain coverage without needing the reference toolkit.

## User correction (Aug 2026)

User said: "Want it to be independent. I want the Hermes erp agent skill to see if there's any gap with accounting toolkit and bridge that accordingly."

The first attempt linked the ERP skill to the accounting-toolkit repo with cross-references. The user corrected this. The fix was to revert all cross-references, study the accounting-toolkit for domain content, and write 7 new reference files + update 3 existing ones with original content covering the same ground.

## Why independence matters

- The reference toolkit may be private, licensed differently, or move repositories.
- A skill that depends on an external repo breaks when that repo is unavailable.
- The skill should be self-contained for distribution.
- Gap analysis against a reference toolkit is a technique for ensuring coverage — the reference toolkit informs the content, but does not appear in the output.
