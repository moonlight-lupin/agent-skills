# Fix-phase pitfalls — orchestrating multi-agent skill fixes

Discipline for the fix phase after a skill review: batching, parallel agents, and proof-of-no-loss. Lessons from the pere-toolkit best-practices batches (5-6 Oct 2026, five agents in parallel across 52 skills).

## 1. Order the batches so trimming comes last

Fixing callability ADDS lines (pere: about +480); the conciseness pass then removed 522. Trimming first would have cut text the call lines needed, and the trimmers could have deleted the new call lines. Run conciseness on settled text — always last.

## 2. Prove nothing load-bearing was lost

After a conciseness pass, run a scripted check that every code span and CLI command in the previous commit is still present in the new text (verbatim span match over `git diff HEAD~1 --name-only`). Pere's check flagged 7 spans; all were generic signatures beside surviving concrete calls — the flagged-but-surviving rule from Check 15 interpretation. Report the count and disposition in the batch summary.

## 3. Regex boilerplate replacement eats neighbours

A pattern like `…end of paragraph\.[^\n]*$` deleted text that carried on after the paragraph on the same line, in 4 of 47 files. One was the opening of a call line. Rules:

- Match to the paragraph end only, never to end-of-line blindly.
- Diff every replaced span against HEAD before committing.

## 4. CRLF from Python writers

Agents' Python edits wrote CRLF line endings twice (platform-dependent default). Put `open(p, "w", encoding="utf-8", newline="\n")` in every agent prompt that writes files, and lint for CRLF (`grep -rlP '\r$'` over changed files) before commit.

## 5. Shared resources make parallel test runs flaky

Agents each running the full test suite fought over LibreOffice; recalc tests failed at random, though each passed on a solo run. Tell agents to REPORT such failures, not chase them, and have the orchestrator run the suite solo before each commit.

## 6. Announce a new lint rule before agents run tests

Adding a lint rule (pere: the TOC rule) mid-batch made every agent's "suite must be green" gate fail. Message agents first, or land the rule after their batch completes.

## 7. Partition by file; keep the orchestrator out of agents' files mid-run

Mechanical cross-cutting edits (boilerplate, TOCs) go before or after an agent batch, never during. This extends the SKILL.md pitfall on parallel write conflicts — the safe pattern is partition by directory or file, with the orchestrator touching only files no agent owns.

## 8. Verify reviewer findings before fixing

Two independent reviewers plus a re-check still produced three false findings on pere (IM terminology, return-on-cost, "pywin32 missing"). Each finding needs a quoted locator and a spot-check before it becomes a fix task. Counts come from scripts, not reviewer estimates.

## Batch sequencing template

1. Mechanical pre-pass (frontmatter, TOCs, packages) — orchestrator, scripted.
2. Agent batch, partitioned by file (callability + instructions + defaults fixes together per skill). Prompt includes: newline="\n" in every open(), report-don't-chase for flaky tests, new lint rules announced.
3. Orchestrator solo test run + commit.
4. Terminology / boilerplate / conciseness pass on the now-settled text.
5. No-loss proof (§2) + final full check re-run.
