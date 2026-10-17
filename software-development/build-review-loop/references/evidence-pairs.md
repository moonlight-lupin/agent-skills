# Evidence Pairs

Every delivered batch carries an **evidence pair**: the state before the
change and the state after, captured the same way. The pair is embedded in
the delivery — PR body, commit message thread, or final report — not stored
beside it. A claim about the change without its pair is unverified prose.

Ported concept (Sep 2026) from michaelshimeles/skills "prove" beat
(evidence-driven-testing). See *Adaptation* below for what was NOT taken.

## Capture rules

- Capture the **before** while reproducing the issue — before the fix, when
  it is cheapest. A before captured after the fix is a reconstruction, not
  evidence.
- Capture **after** with the same method as the before. A screenshot vs a
  screenshot; a measured number vs the same measurement re-run. Method
  change = invalid pair.
- No visual surface? Use **measured numbers or output pairs** instead:
  the failing check output vs the passing one, the slow timing vs the fast
  one, the wrong total vs the right one.
- Keep pairs **local** (workspace, `/tmp`, repo `docs/` when meant to
  ship). Never upload to public hosts — screenshots of customer or
  internal surfaces are sensitive.

## Where the pair lives

| Delivery | How the pair is embedded |
|---|---|
| PR | Markdown table `\| Before \| After \|` in the body; images via repo-relative paths or uploaded assets |
| Delivery message | Before/after blocks side by side |
| Commit for a small fix | Before/after output pasted in the message body |

The loop's dual review (Codex + Opus) judges the diff; the pair is for the
human — it answers "does the change do what it claims" in one look.

## Completion criterion

A batch's delivery step is done only when every user-visible claim in it
has a pair beside it. `--gate` open + attestation verified + evidence pairs
embedded = deliverable.

## Adaptation (source: michaelshimeles/skills)

Ported: the before/after pair as a delivery requirement, and the
"capture before while reproducing" timing rule.

NOT adopted: their `@vercel/before-and-after` CLI (uploads to a public
host by default — 0x0.st; unacceptable for Phronesis/customer surfaces),
`greploop` (needs Greptile; our Codex+Opus dual review is stricter),
`unslop` (controlled-English is our writing standard), `new-feature`
worktree flow (our parallel dispatches use disjoint brief ownership,
pitfall (parallel dispatches); worktree isolation remains an option for true conflicts),
`code-structure` service-layer skill (already covered by our
architecture review checklist).
