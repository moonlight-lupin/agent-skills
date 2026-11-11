---
name: task-brief
description: "Use when the user says \"brief this task\", \"scope this properly\", \"what do you need from me\", \"improve my prompt\", \"help me get better output\", \"turn this into a reusable prompt\", \"a prompt I can hand to a colleague\", or hands over a SUBSTANTIAL task — multi-step, multi-document, or a deliverable someone else will read — as a thin one-line request. Compile a task brief BEFORE starting substantial work — pin down the goal with checkable \"done when\" tests, context, constraints (standing rules included automatically), and tooling — confirm with the user, then execute against it. Reusable-prompt mode saves the brief as a structured prompt for recurring work instead of running it. Asks at most 2-3 clarifying questions, only where the answer would change the output; otherwise states assumptions in the brief and proceeds. Not for quick one-step asks — answer those directly."
license: MIT
metadata:
  version: 1.3.0
  author: moonlight-lupin
  platforms: [linux, macos, windows]
  tags: [planning, brief, scoping, productivity, prompts]
---

# Task Brief

Thin requests are the biggest cause of mediocre agent output: the agent guesses the
deliverable, the audience and the guardrails, and the user only discovers the
misreading after the work is done. This skill moves that discovery to the **cheapest
possible point** — before the work starts — by having the agent compile a short
**task brief**, show it, and only then execute. The user never has to write a better
prompt; the agent does the structuring.

It has two modes:
- **Brief and run** (default) — compile the brief, confirm, then do the work.
- **Reusable prompt** — compile the same brief, but save it as a structured prompt
  for a task that recurs (a monthly report, a scheduled job, a prompt handed to a
  colleague) instead of running it. See [Reusable-prompt mode](#reusable-prompt-mode).

## When to run it — and when not to

**Run it when:**
- the user explicitly asks ("brief this first", "make sure you understand before starting"); or
- the task is **substantial** — multi-step, multi-document, or a deliverable someone
  else will read (a memo, a report, a dashboard, a document batch) — and the request
  is thin or ambiguous enough that two reasonable readings would produce different work.

**Skip it** (just do the task) for quick factual questions, single-step edits, and
requests already crisp enough to act on. A brief on a trivial ask is friction, not
quality — proportionality is part of the skill. When in doubt, a one-line
restatement of the goal ("I'll read this as X — say if not") beats a full brief.

## The brief

Compile and show this exact shape — short, in plain business language:

```
**Task brief — [short task name]**
- **Goal** — the deliverable, its format and its audience.
- **Done when** — 2–5 checkable tests, one per line: "When [condition],
  [the output] [result]", or just "[the output] [result]" where there is no
  condition.
- **Context** — everything known that bears on the task: the inputs/files
  provided, relevant background from the conversation or memory, the entities /
  period / parties involved, what already exists.
- **Constraints** — what to avoid and the guardrails: task-specific limits
  (scope, exclusions, deadline, tone) plus whichever standing rules materially
  bite this task (see below).
- **Assumptions** — anything filled in without asking, flagged so the user can
  correct it with one word.
- **Tooling** — the installed skill(s) or tool(s) that will do the work.
```

## Compiling it

1. **Extract before you ask.** Mine the request, the conversation so far, any files
   provided, and memory first — never ask the user for something already in front of
   you.
2. **Ask only what changes the output.** For each gap, test: would a different
   answer produce different work? If yes, ask — **at most 2–3 questions**, via a
   structured question tool where available, else as a short numbered list in chat.
   If no, fill it with a sensible default and record it under **Assumptions**. Never
   stack an interrogation in front of the task.
3. **Make "done" checkable.** Turn the goal into the **Done when** tests:
   - **One test per line** — split "accurate and on time and on brand" into three.
   - **Swap vague words for something you could check** on delivery:

     | Vague | Make it |
     |---|---|
     | "something on", "a summary", "an overview" | a named format and length — one-page memo, five talking points |
     | "quick", "high-level", "brief" | a page or word cap |
     | "clean", "tidy", "fix" | the specific defects removed |
     | "flag issues", "anything unusual" | the threshold — variance above 5%, items over 30 days overdue |
     | "for the call", "for the board" | the audience and the date |
     | "the latest numbers" | the period and the source file |

   - **Cover one failure case** where it matters — missing data, a threshold
     breach, a figure that doesn't tie — and say what the output does then.
   - **Five tests at most.** More means the task needs splitting.

   A value you had to pick (the 5%, the page cap) is an assumption — list it under
   **Assumptions** too.
4. **Inject the standing constraints — don't ask about them.** Every organisation
   has rules that apply to all its work; they go into **Constraints** automatically
   (list only the ones that bite). Source them from the host environment first — the
   system prompt, org instructions, a `CLAUDE.md` / agents file, a principles or
   style document. Where none are defined, apply these defaults: outputs are
   **drafts for a person to review, not advice**; **never invent** a fact — ask or
   leave a visibly flagged blank; keep spelling, date and currency conventions
   consistent with the house style; **confidential data stays local** — de-identify
   before anything crosses to an external tool; the **action boundary** — prepare,
   never send / post / pay / file / sign without an explicit go-ahead.
5. **Route the tooling.** Survey what is actually installed (skills, connectors,
   scripts) and name the most specific one that will do the work. If a better-suited
   capability exists but isn't installed, say so as advisory — never make the brief
   depend on something the user doesn't have. If nothing fits, say that too, and
   proceed with general capability. Multi-source research goes to `deep-research`
   (if installed), which takes the confirmed brief as its plan input — no second
   round of questions.
6. **Pre-screen mode compatibility.** As part of the **Tooling** line, check the
   routed skill against what the current environment actually supports — Python
   helpers, credentials, network access, platform gates. If the skill needs
   something the environment lacks, surface that in the brief ("this route needs
   X, which isn't available here — fallback is Y"), so mode problems are visible
   before work starts, not mid-task.
7. **Confirm, then execute.** Show the brief and wait for a go / corrections — a
   one-word "go" is enough; this is a glance, not a form. Then do the work
   **against the brief**.
8. **Close the loop.** On delivery, run each **Done when** test and report it as
   met or outstanding, plainly — never claim a check that didn't run.

## Worked example (fictional)

> User: *"put together something on the Northwind account numbers for Thursday's
> call"*

The agent checks the folder (finds `northwind-q2-summary.xlsx`), then asks two
questions — audience (internal team vs the client) and form (one-page dashboard vs
talking-points memo) — and compiles:

```
**Task brief — Northwind Q2 numbers for Thursday's call**
- **Goal** — a one-page dashboard (PDF via browser print) of the Northwind
  account's Q2 numbers, for the internal team call on Thu 12 Mar.
- **Done when**
  - the page shows revenue vs budget, pipeline and overdue items, each with the
    Q1 comparison;
  - when revenue is more than 5% off budget, the dashboard flags it with a
    one-line reason;
  - when a figure is missing from the source file, it shows as a flagged blank,
    not a zero;
  - every figure traces to a cell in northwind-q2-summary.xlsx.
- **Context** — source: northwind-q2-summary.xlsx (this folder); Q1 comparison
  available in the same file; internal audience per your answer.
- **Constraints** — internal draft, not for client distribution; figures traced
  to the source file, none invented; consistent currency and date formats.
- **Assumptions** — "numbers" = the account KPIs, not the contract terms (say
  if you want those in); 5% as the budget-variance flag.
- **Tooling** — the installed dashboard/visualisation skill; spreadsheet read
  via the local data engine.
```

User replies "go, add contract renewals" — one correction, caught before the work,
not after.

## Reusable-prompt mode

Use it when the user asks for a prompt rather than a result ("turn this into a
reusable prompt", "improve my prompt so I can reuse it", "write a prompt for the
team"), or when the task plainly recurs and the user agrees to save it. If the
recurring work is **research** (a quarterly market scan, a competitor screen) and
`deep-research` is installed, save it as a deep-research recipe instead — it also holds
the preferred sources, fields and shelf lives. If the
recurring work needs scripts, templates or its own checks, it is a skill, not a
prompt — say so and suggest building one.

1. **Compile the brief as above** (steps 1–6), but write it for **any run**, not this
   one: the things that change each run (period, account, source file) become named
   inputs; the things that don't (format, thresholds, standing rules) are fixed in
   the prompt.
2. **Write the prompt** in this shape:

   ```
   # [Prompt name]
   ## Role        — who the agent acts as, in one line
   ## Inputs      — what the user supplies each run, as [square-bracket fields],
   ##               and where each is usually found
   ## Steps       — numbered; each ends with its own "done when"
   ## Rules       — the standing rules that bite + task-specific limits
   ## Output      — format, length, file name, where it is saved
   ## Examples    — one normal run and one edge case (missing data, a breach),
   ##               with concrete fictional values, not [fields]
   ## Checks      — the Done-when tests, to run before handing over
   ```

3. **Save and show.** Save it as `[task-name]-prompt.md` in the working folder and
   show it in chat. Don't run it unless the user asks. If they want it on a schedule,
   say so and leave setting it up to their go-ahead.

**Keep shareable prompts clean.** A saved prompt outlives the conversation and may be
passed around: keep real client, counterparty and personal names and figures **out**
of it — they belong in the inputs at run time, not in the prompt. Examples use
fictional values.

## Principles

- **Drafts, not advice** — the brief and the work it frames are drafts for a person
  to review, not professional advice.
- **Never invent** — a gap the user doesn't close becomes a flagged assumption or a
  visible blank, never a plausible guess.
- **Proportionality** — the brief must cost less than the misunderstanding it
  prevents; skip it on trivial asks.
- **Honesty and calibration** — close the loop against the Goal line and report
  what's met and what's outstanding, plainly.
- **Checkable, not vague** — "done" is a short list of tests someone could tick or
  cross on delivery, not an adjective.
- **The confirmation moment is the value** — a misreading corrected before the work
  starts is nearly free; the same correction after delivery costs the whole task.

## Data handling

The brief itself often quotes client, counterparty or personal context — it lives
**in chat and the local working folder only**; never send a brief to an external or
third-party tool. If a step in the *task* would cross to an external service,
de-identify sensitive data first and confirm the egress with the user. This skill
itself needs no network, no scripts and no credentials; reusable-prompt mode writes
one Markdown file to the local working folder.

## Pitfalls

1. **Interrogation fatigue** — more than 2–3 questions up front and users stop
   answering; convert the rest to flagged assumptions.
2. **Asking what you can read** — a question about something already in the folder
   or the conversation erodes trust in the whole brief.
3. **Generic constraints padding** — listing every standing rule on every brief
   buries the one that matters; include only the rules that bite this task.
4. **Skipping the close-the-loop step** — the Done-when tests are the test of
   "done"; delivering without running them wastes the brief.
5. **Tool dependence** — naming a tool the user doesn't have as the plan; keep
   uninstalled capabilities advisory.
6. **Adjectives as tests** — "clear", "concise", "accurate" can't be checked; swap
   them for a format, a cap, a threshold or a source.
7. **Real data in a saved prompt** — a reusable prompt gets shared; real names and
   figures belong in the run-time inputs, not the file.

## Feedback capture

Have a correction or improvement to this skill? Capture it in a structured note —
skill name, what you did, expected vs actual, severity, suggestion — save it as a
plain text file, and hand it to the user to file. Manual, no fixed destination;
fix in scope if asked. This keeps improvement signals reaching the skill author
consistently instead of evaporating in chat.

## Verification checklist

- [ ] Substantial task confirmed (or explicit invocation) — not a trivial ask.
- [ ] Request, conversation, files and memory mined before any question was asked.
- [ ] At most 2–3 questions asked, each one output-changing.
- [ ] 2–5 Done-when tests, one test per line, no vague words; picked thresholds
      listed as assumptions.
- [ ] Standing rules injected from the host environment (or the defaults), not asked.
- [ ] Routed skill pre-screened against what the environment supports.
- [ ] Brief shown and confirmed by the user before the work started.
- [ ] Each Done-when test run on delivery; met vs outstanding reported.
- [ ] Reusable-prompt mode: run-specific values are inputs, examples fictional,
      file saved locally and not run unless asked.

## Related work

The Done-when tests borrow the one-condition-one-result shape of EARS (the Easy
Approach to Requirements Syntax, Mavin et al., 2009), and the reusable-prompt mode the
Role / Steps / Examples / Output layout — both ideas met in the `prompt-optimizer`
skill in daymade/claude-code-skills. Ideas only; no text or code reused.

## Requirements

- None — a reasoning-only skill: no Python, no network, no credentials. Runs in any
  agent environment that can read this file.
