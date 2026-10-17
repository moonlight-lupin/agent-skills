# Background Build Polling — Don't Exhaust the Iteration Budget

## The Problem

When a Cursor build runs in the background with `notify_on_complete=true`,
tight-polling it every few seconds exhausts the tool-iteration budget.

Each `process(action="poll")` call consumes one tool-iteration slot. A build
that takes 5-8 minutes will burn 40+ poll calls, hitting the max-iteration
limit before the build finishes. The orchestrator is then forced into a new
turn to recover, losing in-flight context.

## When It Happened

This pattern was hit twice in one build session (Aug 2026):

1. **Fix-round build** (Cursor Grok 4.6 High, ~4 min): 30+ poll calls before
   the iteration limit hit. The build finished normally, but the orchestrator
   could not process the result — a new user turn was needed to recover.

2. **CommandRegistry feature build** (Cursor Grok 4.6 High, ~7 min): 40+ poll
   calls. Same outcome — iteration limit hit mid-build.

## The Fix

**Dispatch with `notify_on_complete=true`, then STOP.**

Do one of:
- Write the next brief (for the next batch)
- Update docs or roadmap
- Plan the next batch's blocking edges
- Deliver a status update to the user

The completion notification arrives as a new message automatically. When it
arrives, verify the build independently and proceed.

## If the User Asks for a Status Check

Poll ONCE and report. Do not loop. If the build is still running, say so and
move on to other work.

## Timer discipline (user-required pattern)

When waiting for a coding agent, ALWAYS set a bounded background timer:
`terminal(background=true, notify=true, "sleep <estimate> && echo 'TIMER: check due (<proc-id>)'")`. Each timer tick fires as a message; on each tick poll
ONCE and report progress, then re-arm a fresh timer if the build is still
running. Do not loop-poll between ticks. A timer firing while the build is
still mid-edit is NOT a stall — check process liveness (`ps aux | grep
cursor-grok`) and `git status` for fresh edits before assuming anything.
Do not arm a second timer for the same in-flight build; one live timer per
round is enough — the completion notification is the real signal.

## Long-reasoning builders look stalled — check edit velocity, not wall clock

A fix round on control-flow-heavy code (reordering discover → cap → backup
→ strip across a 1,700-line module) can run 30-45 minutes before its FIRST
edit lands. A timer tick showing no `git status` changes is not a stall
while the process is alive. Judge by whether CPU is being consumed and
whether the previous rounds of the same project also started late; a
Grok-high builder spends the early phase reasoning through the reorder
before touching files. Escalate (steer, kill, re-dispatch) only when BOTH
the elapsed time exceeds roughly double the previous round's total AND the
log tail has not advanced between two consecutive ticks. Inspecting the
builder's transcript files mid-run is blocked in background sessions —
rely on `git status`, process liveness, and the log tail; a mid-run
transcript dive is not worth a blocked command.

## Mid-build user feedback: queue, do not interrupt

User corrections arriving while a builder runs go into a scratch buffer
(scratchpad or the next brief draft), NOT into the running build. At the
round boundary, merge corrections (later messages supersede earlier ones),
write the fresh numbered brief, dispatch. Rationale: an interrupted build
loses its place; a merged brief keeps the delta reviewable.

## Why This Is Hard to Follow

The instinct is to "watch" the build — but background processes are designed
to be fire-and-forget. The `notify_on_complete` mechanism exists precisely so
the orchestrator does not need to poll. Trust it.

## Cost of Violation

- Burns 40+ tool-iteration slots on a single build
- Forces a context-compaction or new turn to recover
- Loses any in-flight work from the current turn
- The user sees no progress because the orchestrator is stuck in a poll loop
