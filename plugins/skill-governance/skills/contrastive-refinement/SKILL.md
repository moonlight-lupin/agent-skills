---
name: contrastive-refinement
description: "Use when a skill or harness edit needs evidence before it lands — probe candidates on the same task, compose from contrasts, keep lessons with evidence."
license: MIT
metadata:
  version: 0.2.0
  author: moonlight-lupin
  platforms: [linux, macos, windows]
  tags: [agent-ops, skill-improvement, evidence, refinement]
  related_skills: [repo-adoption-review, build-review-loop]
---

# Contrastive Skill Refinement

Refine a skill or harness edit with measured behavior, not judgment alone.
Before an edit lands, run candidate versions of the skill on the SAME probe
task, compare deliverables blind, and compose the surviving edit. Every
recorded lesson carries an evidence line naming the observed contrast. This
skill only changes skill definitions; for application code changes use
`build-review-loop`.

Pattern source: Harness² (google-research/harness2, Apache-2.0,
arXiv:2610.14224) — the Propose–Probe–Compose loop and the evidence-required
lesson format, ported to Hermes skill dirs. See
`references/harness2-adaptation.md` for what was ported and what was not.

## When to Use

- An edit to a skill promises better output but nobody has measured it
- Two candidate edits both look right and you must pick one
- A skill failed a real task and you want a proven fix, not a guess
- A lesson about a skill needs to be written down and should carry evidence

**Don't use for:** typo and frontmatter fixes (no behavior change), live code
repos (`build-review-loop`), first drafts of brand-new skills (nothing to
contrast yet).

**Fire backlog:** an unanswered advisory re-fires every session until its
fire row is closed. The contrastive-advisor plugin (v0.2.0+) self-installs a
clearance cron (`contrastive-advisor fire clearance`) that closes backlog
fires by classification (see its docs/README.md). Running this skill
WITHOUT the plugin: either create an equivalent sweeper cron yourself with
the same classification rules, or close each fire in the editing session —
a documented classification with real-execution evidence is a legitimate
close; never leave the demand unanswered.

**When the contrastive-advisor fires but the edit fits 'Don't use for':**
respond with a documented classification, not a probe cycle. Create the
per-skill probe dir (`~/.hermes/skill-probes/<skill>/<tag>/`) with a
`probe.md` stating WHAT was edited and WHY the edit makes no behavioral
claim (diff scope: quoted lines preserved verbatim, only a pointer/label/metadata
changed), plus a `selection.md` recording the decision and the commitment
rule: any FUTURE behavioral edit to this skill runs the full cycle. Never
fabricate probe evidence; never leave the advisor's demand unanswered — an
undocumented gap re-fires every session, and inventing a cycle result poisons
the evidence root. This also covers consolidation edits (a no-loss pointer
repoint with 0 rule-title deltas): the no-loss check IS the evidence line.

**Reconstruct the actual edit before classifying — do not classify from
memory.** Pull the edit from the session store: query `state.db` `messages`
(`tool_calls` column) for the fire's `session_id`, parse each call's
`function.arguments` (a doubly-encoded JSON string), and extract the
`skill_manage`/`patch`/`write_file` operations naming the skill. Behavioral
claims backed by live execution in the editing session (a procedure that was
run end-to-end against the real target) satisfy the evidence gate without a
synthetic cycle.

Three legitimate classifications beyond the mechanical one:
- **Unresolved provenance** — the file changed but no logged tool row or
  backup carries the delta (parallel sessions and file writes outside the
  tool-call store). Document the gap, describe the current content class,
  and treat the skill's next edit as gate-bearing. Never guess the edit's
  purpose.
- **Orphan fire** — the fired skill name has no SKILL.md in the tree (or a
  frontmatter-only sweep confirms absence). Close as orphan; do not classify
  an edit to a nonexistent artifact.
- **Real-environment execution evidence** — a behavioral edit whose procedure
  was already exercised against the live target in the editing session. State
  the reopen condition in the selection doc.

Close the bookkeeping too: set `answered_at` (+`answered_with` pointer) on
the fire's rows in `~/.hermes/skill-probes/fire-ledger.jsonl`, and clear
the advisor's pending record in its plugin-data `state.json` when the fire
belongs to another session.

## Concepts

- **Probe task** — one fixed, realistic task for the target skill, with inputs
  on disk. The judge is deliverable comparison, not a rubric score.
- **Baseline** — the current skill, run once on the probe task.
- **Candidate** — one proposed edit (INV or DOM), applied to a COPY of the
  skill, never to the live skill. The standard cycle uses two candidates:
  one INV, one DOM. A second pair of candidates is an extension, not default.
- **INV edit** — skill-agnostic lever: a checklist, a script gate, an output
  contract, a guardrail.
- **DOM edit** — domain-specific content: a rule, an example, a parameter
  tuned to the skill's actual subject matter.
- **Composition** — one final edit merged from the contrasts that survived
  blind comparison. Additive: it changes only what the evidence showed.

## Procedure

1. **Choose the probe task.**
   Pick one realistic task for the target skill. Write inputs to a probe
   directory. The task must be judgeable by comparing the deliverable text.
   Completion: probe inputs exist on disk and will not change during the cycle.
   - Anti-contamination: describe the work in the probe prompt. Never
     mention that it is a test, a probe, a benchmark, or an evaluation —
     measurement language changes agent behavior.

2. **Run the baseline.**
   Execute the current skill on the probe task once. Save the deliverable and
   the trajectory in the probe directory. Completion: baseline deliverable
   exists.

3. **Propose candidates.**
   Write the candidate edits: one INV (a skill-agnostic lever: checklist,
   script gate, output contract, guardrail) and one DOM (a domain-specific
   rule, example, or parameter). Write more pairs only when a strong reason
   exists. Each candidate is a concrete patch to the target skill, written
   out in full. State the expected behavioral difference for each.
   Completion: every candidate has a written patch and a written expectation.

4. **Probe.**
   For each candidate, apply the patch to a COPY of the skill in a scratch
   directory and run the probe task with that copy. Run the candidates in
   parallel. Same model, same tools, same inputs — the only changing variable
   is the edit. Completion: one deliverable per candidate plus the baseline,
   all from identical probe inputs.

5. **Blind selection.**
   Run `<skill_dir>/scripts/contrast.py ids` — `<skill_dir>` is this skill's
   own directory (the path `skill_view` reports) — to assign anonymous ids to baseline plus
   every candidate deliverable. Read the deliverables blind, write one
   `<why>` line per deliverable, then unmask. Completion: a choice with a
   written reason naming the observed contrast — or no choice.
   - Fallback rule: if no contrast is visible, keep the baseline. One retry
     of a failed candidate is the ceiling; after that, keep the base.
   - Inconclusive probes kill the edit. Do not compose from vibes.

6. **Compose, probe the composition, then apply.**
   Merge only the contrasts that won blind into one final patch. Probe the
   composition once: apply it to a FRESH copy of the baseline (not a copy
   that already holds a candidate patch — that would apply an edit twice)
   and run the probe task one more time. A merge of two individually winning
   changes can still behave badly together. Compare the composition's
   deliverable against the baseline through the same blind procedure (new
   `ids` round, fresh `<why>` lines) before it lands: the composition must
   deliver and beat the baseline. Then apply via
   `skill_manage(action="patch", ...)` to the live skill: `name` is the
   target skill, `old_text` and `new_text` carry the composed edit. The edit
   is additive and minimal. If the composition probe loses, keep the
   baseline and discard the edit.
   Completion: patched skill, or a recorded decision to keep the base.

7. **Record the lesson with evidence.**
   Format (all four fields, or no entry):
   ```
   cue: When <situation>
   lesson: <the rule>
   evidence: <the observed contrast from the probe run>
   confidence: <scope of validity>
   ```
   Field values are single-line. `<skill_dir>/scripts/contrast.py lesson-check` enforces
   the gate: exit 0 required, and a value that is only a placeholder — `n/a`,
   `-`, `none`, `todo`, with or without markdown wraps (`**n/a**`, `N/A.`) —
   or one bare `<template>` tag counts as empty; evidence that assembles tag
   spans stays valid; a repeated field takes the last
   value. The gate is syntactic: it cannot judge the quality of an evidence
   sentence, that judgment belongs to Steps 4–6. Send the lesson to the
   target skill's lessons section or memory as fits. Completion: lesson
   saved, evidence line names a real observation.

## Post-Ship Monitoring (advisory artifacts)

When the composed edit lands as a DEPLOYED artifact — an advisory plugin, a
harness hook — the proof burden shifts from "the edit won the probe" to "the
artifact actually fires in the live host". Registry rows ('enabled',
correct version) and a clean load log prove DISCOVERY, not binding; many
hooks log nothing on success, so silence is not evidence. Verify with:

1. **One real end-to-end fire.** Perform one genuine behavioral edit the
   artifact exists to catch, and check ALL of: the artifact's durable state
   appears on the first pending write (e.g. its plugin-data state file), the
   host logs carry no contract-rejection or load-failure lines after the
   restart marker, and the artifact's output surfaces where the host injects
   it. Never conclude from log absence alone.
2. **Know the injection point.** `pre_llm_call` context is injected into the
   user message that STARTS a turn: an advisory queued mid-turn by a tool
   call surfaces at the start of the NEXT user-initiated turn, never in the
   same turn as the triggering edit. Plan observation windows accordingly.
3. **Effectiveness, not just firing.** The outcome signal is probe cycles
   appearing under the evidence root within the review window after fires —
   a cycle needs BOTH its planning and selection files present. Count
   fires and false-positives from a DURABLE LEDGER THE ARTIFACT WRITES
   ITSELF at delivery time (one row per injected advisory, plus auto-close
   when the answering cycle lands) — not from chat logs: an in-band
   injection leaves no host log line, the pending record expires after its
   TTL, compaction prunes the conversation, and a hand-maintained ledger
   cannot recover past fires (pre-ledger fires can only be mined from the
   session store's `messages` table — see log-analyzer). If the deployed
   artifact lacks self-recording, add it before judging the trial. If host
   logs do not record tool arguments, the detection-rate denominator is
   unobservable — label the rate UNVERIFIED rather than computing it from
   fire counts alone.
4. **Decision at the review date** (two weeks is the default): keep,
   tune (TTL, thresholds, marker lists, exclusions), or disable. Catalog or
   manifest publication waits until after that decision.

## Pitfalls

- **Same-model control is the whole validity claim.** If a probe runs a
  different model or tools than the baseline, the contrast measures the
  model, not the edit.
- **Blinding breaks silently.** File names, paths, or self-reports often
  reveal the candidate identity. Use the anonymized ids output only.
  In-context selection: have every probe arm return the DELIVERABLE only
  (no process notes in the report body — notes leak identity and pad the
  comparison), save deliverables to files, re-read them by anon id, and
  write the `<why>` lines from the files. When the arms already reported
  with identities visible in the conversation, the honest compromise is
  the file re-read — record it in the selection doc; do not claim the
  comparison was blind when it was not.
- **The cost shape is near-fixed.** A standard cycle is one baseline run
  + two candidate runs + one composition-probe run (about 4 model runs),
  then the selection round, which is your own read of the deliverables, not
  a rollout. A candidate retry (Step 5 ceiling) can add one run. The `--k`
  and `--mode` flags in `<skill_dir>/scripts/contrast.py ids` are
  shuffle-seed tags only; they do not change the run count. Budget the probe
  task to be small enough for that.
- **A winning contrast may be probe-specific.** Confidence says the scope.
  Generalize only when the contrast is structural, not cosmetic.
  Deliverable-quality contrasts (malformed output, missing
   sections, wrong art) are strong from a single run — output damage is not
   variance. Efficiency contrasts (call counts, duration) are the WEAKEST class:
   one run cannot separate the edit's effect from run-to-run model variance —
   rerun for the same direction before applying an efficiency-only edit, and say
   so in the lesson's confidence line.
- **Compose at most one new rule per tool section.** Two winning candidates
  that touch the same tool section can interact: a merged process rule next to
  an existing fallback can push the composed run toward hand-computing an
  output instead of reproducing a known figure — both parts won alone, the
  merge lost its own gate. Keep the baseline when that happens; the fallback
  rule exists for exactly this.
- **Apply the composed edit with anchors taken from a FRESH read of the live skill, never from the probe copies.** Copies drift from live (local rewordings, different frontmatter layout), and an `old_string` reused from a probe copy or from the composed deliverable text fails to match or matches the wrong region. Compose the edit as an abstract change, then re-derive the anchor from the most recent skill_view of the live file immediately before the skill_manage call.
- **Pick the pilot target from usage data.** Read `.usage.json` at the skills root and choose the lowest `use_count` skill that still earns improvement; never pilot a cycle on a load-bearing skill (money, user content, repo operations) without the user's go. The fallback rule protects against loss, but the cycle still rewrites files. If the target has an upstream-provenance row in `UPSTREAM_MANIFEST.md`, a local refinement is drift by definition — record `✅ keep-ours (...)` on that manifest row or carry the fix upstream, never leave the row untouched.
- **The live session's skill loader is cached.** A newly installed skill is
  visible to the next session, not this one — test through file paths here.

## Quick Reference

`<skill_dir>` is this skill's own directory — the path `skill_view` reports
for this skill. Run the script from anywhere:

```bash
# Anonymous ids for blind selection (deterministic per task/k/mode seed)
python3 <skill_dir>/scripts/contrast.py ids --labels base,inv1,dom1 --task probe-1 --k 1

# Evidence gate for lessons (reads stdin, exit 0 = valid)
python3 <skill_dir>/scripts/contrast.py lesson-check < lesson.md
```

## Verification

- Probe cycle directory holds: probe inputs, baseline deliverable, one
  deliverable per candidate, the anonymized mapping, the `<why>` lines.
- The chosen edit has a written contrast evidence line.
- `<skill_dir>/scripts/contrast.py lesson-check` passes on the recorded lesson.
- The live skill shows only the composed additive edit (diff the target
  skill before and after).
