---
name: grill
description: "Use when a plan is fuzzy and needs hardening before a spec — decision-tree grilling in frontier rounds, every open decision put as a numbered question with a recommended answer, until shared understanding. The pipeline's home for collecting foreseeable important forks before the spec. Triggers: 'grill me', 'grill this plan', 'stress-test this', 'poke holes in this', 'harden this design', pre-spec hardening, unresolved decisions."
metadata:
  version: 1.2.0
  author: moonlight-lupin
  license: MIT
  platforms: [linux, macos, windows]
  hermes:
    tags: [grilling, interview, decision-tree, frontier, planning, stress-test, pre-spec, clarify, questions]
    related_skills: [spec, orchestrator, doubt-driven-development]
---

# Grill

## Overview

Interview the user relentlessly about every aspect of a plan or design until you reach a **shared understanding**. Walk down each branch of the decision tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

The goal is not to reach agreement quickly — it is to make every implicit call explicit, so nothing important is left silently assumed.

Grilling is an interview, not an execution — it produces alignment, not artifacts. Every decision surfaced and settled is what the `spec` stage synthesizes afterward.

## When to Use

- User says "grill me", "stress-test this plan", "poke holes in this", "harden this design"
- A plan feels roughly right but unresolved decisions are hiding in it
- Before writing a spec (pre-spec hardening)
- User wants to find soft spots in a design before committing to code
- Before any S2/S3 build where the plan is still fuzzy, and before any S1
  build whose ask is ambiguous — grill is where the session's foreseeable
  **important forks** are collected and settled
  (`orchestrator/references/unattended.md` is the definition's single home).
  The session must not proceed to the spec while known important forks are
  open.

**Don't use for:**

- Plans that are already fully specified — go straight to the `spec` stage
- Simple, unambiguous tasks
- Post-hoc code review (use the `review-commit` stage)

## The Decision Tree

The mental model is a **decision tree**: every plan branches into decisions, and decisions depend on each other. Grilling descends that tree round by round, so an early answer can reshape which questions come next.

```
        Plan
       /    \
   Decision A   Decision B (depends on A)
   /     \           |
  A1     A2         B1
  |                   |
  ...               ...
```

## Frontier rounds

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask *now* without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round's answers reshape the tree: settled decisions push the frontier outward and unblock the questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a *later* round, not this one.

The session is done when the frontier is empty: every branch of the decision tree visited, nothing left silently assumed.

## Rules

### One question at a time

Frontier rounds replace the old strictly-one-at-a-time model, but the underlying rule still bites: a user who is handed the entire decision tree at once is bewildered and loses the structure that makes the interview converge. A round contains the whole unlocked frontier and nothing more — every question a numbered entry the user answers directly. A question whose answer depends on another still-open question waits for a later round.

### Provide a recommended answer

Each question comes with **your recommended answer**. The user reacts to a proposal, not a blank prompt. This makes the interview faster and surfaces your reasoning for the user to correct.

Word each question so "yes" accepts the recommended answer: "I recommend 15 minutes because the spec says security-first — agree? (yes = 15 minutes)". A "yes"-accepting question turns a round of answers into a round of confirmations.

### Facts vs decisions

If a *fact* can be found by exploring the environment (filesystem, tools, codebase, docs), **look it up rather than asking**. Finding a fact is your job, never the user's: when a frontier question needs a fact from the environment, dispatch a subagent to look it up — never ask the user for anything you could retrieve yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the subagent to report; ask the rest of the frontier now. The *decisions*, though, are the user's — put each one to them and wait for their answer.

### Dependency order

Resolve parent decisions before children. An early answer may close off branches or open new ones. Don't ask about B if B depends on A and A is unresolved — B's questions join the round after A is settled.

Recompute the frontier every round: settled decisions push it outward and unblock the questions that depended on them; an answer that opens new sub-decisions puts those sub-decisions on the next frontier.

### Don't act until confirmed

Do not act on the plan until the user confirms you have reached a shared understanding. Grilling is an interview, not an execution — it produces alignment, not code.

## Process

1. **Understand the plan.** Read the conversation context. If the user references a file (spec, design doc, issue), fetch and read it first.

2. **Map the decision tree.** Identify the major decisions and their dependencies. Don't share this map — just use it to order your rounds.

3. **Ask a round.** Walk the tree one frontier at a time: compute the frontier — every decision whose prerequisites are settled. Ask all of it in one numbered round, each question with a recommended answer. Dispatch subagent lookups for any retrievable facts (see *Facts vs decisions*) and ask the questions that don't depend on them now. Wait for the answers.

4. **Recompute the frontier.** Fold each answer in: settled decisions unblock their dependents; answers that opened new sub-decisions put them on the next frontier. Ask the next round. Repeat until nothing is left.

5. **Confirm shared understanding.** When all branches are visited, summarize the resolved decisions and ask the user to confirm the summary ("anything to adjust?"). Once the user confirms, move on to the next stage without asking permission — a stage handoff is not an important fork (`orchestrator/references/unattended.md`). The interview's questions are the only questions; after it closes, the session continues unattended.

## What makes a good grilling question

- **Specific, not abstract.** "Should the auth token expire after 15 minutes or 24 hours?" > "What are your thoughts on auth?"
- **Recommends, doesn't defer.** "I recommend 15 minutes because the spec says security-first. Agree?" > "How long should the token last?"
- **Resolves, doesn't explore.** Each question should settle something, not open a rambling discussion.
- **One decision per question.** Don't bundle "Should we use Redis AND should the TTL be 1 hour?" into one question.

## Completion Criteria

- Every major decision branch in the tree has been visited
- Each resolved decision has a clear answer (not "we'll figure it out later")
- The frontier is empty — nothing left silently assumed
- The user has confirmed shared understanding
- No decision depends on an unresolved parent

## Common Pitfalls

1. **Firehosing questions.** A round is the whole *unlocked frontier*, and only the frontier — dumping the entire decision tree in one message, or bundling questions that depend on still-open answers, overwhelms the user and loses the dependency structure. Numbered frontier rounds, always.

2. **Asking about facts.** "What version of Python does this project use?" — read the `pyproject.toml` instead. Dispatch a subagent for any retrievable fact; only ask the user about decisions.

3. **Not providing a recommendation.** A blank prompt forces the user to do your work. Always propose an answer with reasoning, worded so "yes" accepts it.

4. **Acting mid-grill.** Starting to write code or files before the user confirms shared understanding. Grilling is an interview, not execution.

5. **Skipping branches.** Not visiting a decision because it seems trivial. Trivial decisions made implicitly are the ones that bite later.

6. **Not recursing.** When the user's answer opens a new sub-decision, moving on without putting it on the next frontier.

## Where it fits

Grill is the **pre-spec hardening step** of the dev-pipeline pipeline. It comes before `spec`:

- Plan fuzzy → grill here first.
- Plan already clear → skip straight to the `spec` stage — `spec` synthesizes what's already known, it doesn't interview.
- Residual ambiguity after the spec is saved is resolved by the spec stage's inline **clarify** phase (`[NEEDS CLARIFICATION]` markers resolved with the user, answers folded back into the spec) — run after spec, before planning.

The pipeline runs unattended around this interview (`orchestrator/references/unattended.md`): grill is the one stage that asks questions by design, and it exists so every later stage can run without pausing — foreseeable important forks are settled here, and the session does not proceed to spec while known ones are open.

The canonical chain diagram and the whole-pipeline flow map live in the pipeline's orchestrator stage; this stage is the front door for building anything non-trivial.

If doubt surfaces *while executing* an already-agreed plan — the user is mid-build and skeptical of a step — that is `doubt-driven-development`'s discipline with its own trigger, not a re-grill. Load that skill instead.
