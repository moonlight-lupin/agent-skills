# task-brief

Prompt-quality skill for AI agents: before substantial work starts, the agent compiles a short
**task brief** — **Goal** (what "done" looks like) · **Context** · **Constraints** (the
organisation's standing rules injected automatically) · **Assumptions** (flagged fills) ·
**Tooling** (which installed skill does the work) — confirms it with the user, executes against
it, then closes the loop against the Goal line. At most 2–3 clarifying questions, and only where
the answer would change the output; skips itself on trivial asks.

The user never has to write a better prompt — the agent does the structuring, and a one-word
"go" (or a one-word correction) catches misreadings at the cheapest possible point.

## Structure

```
task-brief/
└── SKILL.md          # The whole skill: when to run, the brief shape, compile rules,
                      # worked example, principles, pitfalls, verification checklist
```

Reasoning-only — no scripts, references or assets.

## Requirements

- None. No Python, no network access, no credentials — pure prompt workflow.

## License

MIT
