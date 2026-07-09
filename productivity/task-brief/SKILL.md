---
name: task-brief
description: >
  Compile a task brief BEFORE starting substantial work — pin down the goal (what
  "done" looks like), the context (everything known that bears on the task), the
  constraints (guardrails, with the organisation's standing rules included
  automatically) and the tooling (which installed skill or tool will do the work) —
  confirm it with the user, then execute against it. Use whenever the user says
  "brief this task", "brief this first", "make sure you understand before you
  start", "scope this properly", "compile a brief", "what do you need from me",
  "improve my prompt", "help me get better output", or hands over a SUBSTANTIAL
  task — multi-step, multi-document, or producing a deliverable someone else will
  read — as a thin one-line request. Asks at most 2-3 clarifying questions, and
  only where the answer would change the output; otherwise it states its
  assumptions in the brief and proceeds. Not for quick one-step asks — just answer
  those directly.
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
---

# Task Brief

Thin requests are the biggest cause of mediocre agent output: the agent guesses the
deliverable, the audience and the guardrails, and the user only discovers the
misreading after the work is done. This skill moves that discovery to the **cheapest
possible point** — before the work starts — by having the agent compile a short
**task brief**, show it, and only then execute. The user never has to write a better
prompt; the agent does the structuring.

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
- **Goal** — what "done" looks like: the deliverable, its format, its audience,
  and the test it must pass.
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
3. **Inject the standing constraints — don't ask about them.** Every organisation
   has rules that apply to all its work; they go into **Constraints** automatically
   (list only the ones that bite). Source them from the host environment first — the
   system prompt, org instructions, a `CLAUDE.md` / agents file, a principles or
   style document. Where none are defined, apply these defaults: outputs are
   **drafts for a person to review, not advice**; **never invent** a fact — ask or
   leave a visibly flagged blank; keep spelling, date and currency conventions
   consistent with the house style; **confidential data stays local** — de-identify
   before anything crosses to an external tool; the **action boundary** — prepare,
   never send / post / pay / file / sign without an explicit go-ahead.
4. **Route the tooling.** Survey what is actually installed (skills, connectors,
   scripts) and name the most specific one that will do the work. If a better-suited
   capability exists but isn't installed, say so as advisory — never make the brief
   depend on something the user doesn't have. If nothing fits, say that too, and
   proceed with general capability.
5. **Confirm, then execute.** Show the brief and wait for a go / corrections — a
   one-word "go" is enough; this is a glance, not a form. Then do the work
   **against the brief**.
6. **Close the loop.** On delivery, check the output against the **Goal** line and
   say plainly which parts of "done" are met and which are outstanding — never
   claim a check that didn't run.

## Worked example (fictional)

> User: *"put together something on the Northwind account numbers for Thursday's
> call"*

The agent checks the folder (finds `northwind-q2-summary.xlsx`), then asks two
questions — audience (internal team vs the client) and form (one-page dashboard vs
talking-points memo) — and compiles:

```
**Task brief — Northwind Q2 numbers for Thursday's call**
- **Goal** — a one-page dashboard (PDF via browser print) of the Northwind
  account's Q2 numbers, for the internal team call on Thu 12 Mar; done = the
  reader sees revenue vs budget, pipeline and overdue items at a glance.
- **Context** — source: northwind-q2-summary.xlsx (this folder); Q1 comparison
  available in the same file; internal audience per your answer.
- **Constraints** — internal draft, not for client distribution; figures traced
  to the source file, none invented; consistent currency and date formats.
- **Assumptions** — "numbers" = the account KPIs, not the contract terms (say
  if you want those in).
- **Tooling** — the installed dashboard/visualisation skill; spreadsheet read
  via the local data engine.
```

User replies "go, add contract renewals" — one correction, caught before the work,
not after.

## Principles

- **Drafts, not advice** — the brief and the work it frames are drafts for a person
  to review, not professional advice.
- **Never invent** — a gap the user doesn't close becomes a flagged assumption or a
  visible blank, never a plausible guess.
- **Proportionality** — the brief must cost less than the misunderstanding it
  prevents; skip it on trivial asks.
- **Honesty and calibration** — close the loop against the Goal line and report
  what's met and what's outstanding, plainly.
- **The confirmation moment is the value** — a misreading corrected before the work
  starts is nearly free; the same correction after delivery costs the whole task.

## Data handling

The brief itself often quotes client, counterparty or personal context — it lives
**in chat and the local working folder only**; never send a brief to an external or
third-party tool. If a step in the *task* would cross to an external service,
de-identify sensitive data first and confirm the egress with the user. This skill
itself needs no network, no scripts and no credentials.

## Pitfalls

1. **Interrogation fatigue** — more than 2–3 questions up front and users stop
   answering; convert the rest to flagged assumptions.
2. **Asking what you can read** — a question about something already in the folder
   or the conversation erodes trust in the whole brief.
3. **Generic constraints padding** — listing every standing rule on every brief
   buries the one that matters; include only the rules that bite this task.
4. **Skipping the close-the-loop step** — the Goal line is the test of "done";
   delivering without checking against it wastes the brief.
5. **Tool dependence** — naming a tool the user doesn't have as the plan; keep
   uninstalled capabilities advisory.

## Verification checklist

- [ ] Substantial task confirmed (or explicit invocation) — not a trivial ask.
- [ ] Request, conversation, files and memory mined before any question was asked.
- [ ] At most 2–3 questions asked, each one output-changing.
- [ ] Standing rules injected from the host environment (or the defaults), not asked.
- [ ] Brief shown and confirmed by the user before the work started.
- [ ] Output checked against the Goal line; met vs outstanding reported.

## Requirements

- None — a reasoning-only skill: no Python, no network, no credentials. Runs in any
  agent environment that can read this file.
