# Efficacy Rubric Template

Copy per test. Fill one block per scenario. Scenarios must be verbatim-identical across arms;
target each rubric at a change the refactor made (pointer firing, dedupe, noise rejection, new-rule recall).

```markdown
# <Skill> A/B — Scenarios & Rubric

Controlled test: old vs refactored <skill>. Same model, same scenario prompts. Only variable: skill version.
Each child reads ONE arm's files and answers its scenarios in order, using only the material.

### S<n> — <what the refactor changed, e.g. pointer efficacy>
<verbatim scenario prompt — identical text in both dispatches>

Rubric (1 pt each):
- a) <checkable behavior point>
- b) <arm-discriminating point, e.g. consults references/<file>.md — measures pointer firing>
- c) <noise-rejection point — does NOT do the counterproductive thing>

## Scoring protocol
- One child per arm, identical goal text, path is the only context difference.
- Score each cell 0-3 (a/b/c). Report per-scenario and aggregate.
- State limits: n=1 per cell is directional; measures single-turn rule recall, not end-to-end outcomes.
```