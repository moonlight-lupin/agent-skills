# Plan template and writing process

Templates, the plan-writing process, and the cross-artifact analyze checklists for the dev-pipeline spec stage (plan turn). The doctrine behind the task slicing (tracer bullets, blocking edges, expand-contract) is stated once in `task-doctrine.md`.

## Contents

- Plan Document Structure
  - Header (Required)
  - Constitution Gates
  - Task Structure
- Writing Process
  - Step 0: Consume the spec (if one exists)
  - Step 1: Understand Requirements
  - Step 2: Explore the Codebase
  - Step 3: Design Approach
  - Step 4: Write Tasks
  - Step 5: Add Complete Details
  - Step 6: Review the Plan
  - Step 7: Cross-Artifact Consistency (analyze)
- Principles (DRY / YAGNI / TDD / Frequent commits)
- Common Mistakes

## Plan Document Structure

### Header (Required)

Every plan MUST start with:

```markdown
# [Feature Name] Implementation Plan

> **For Hermes:** `test-evals` writes each task's test cases RED, then the `build` stage implements this plan task-by-task. **Tier:** T_ (`orchestrator/references/size-tiers.md`). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

## Global Constraints

[Project-wide requirements — version floors, dependency limits, naming and copy rules, platform requirements — one line each, with exact values copied verbatim from the spec. Every task's requirements implicitly include this section.]
```

### Constitution Gates

Continues inside the header template. Skip if no `.hermes/constitution.md` and no user-stated governing principles; the SKILL.md "Constitution gates" section defines the standard gate list.

```markdown
## Constitution Gates

[Optional but recommended — skip if no project constitution exists. If a `.hermes/constitution.md` exists or the user stated governing principles, encode them as pre-implementation gates the plan must pass before any task runs. These act as compile-time checks on architectural decisions. If a gate fails, the plan must document why in a "Complexity Tracking" note rather than silently proceeding.]

### Phase -1: Pre-Implementation Gates

#### Simplicity Gate
- [ ] Using ≤3 projects / packages? (If more, document justification)
- [ ] No future-proofing for requirements not in the spec?

#### Anti-Abstraction Gate
- [ ] Using framework features directly rather than wrapping them?
- [ ] Single model representation (no parallel/competing representations)?

#### Test-First Gate
- [ ] Every task names its test cases (behavior, seam, expected value + source) so `test-evals` can write them RED before implementation?
- [ ] Acceptance criteria from the spec map to test assertions?
- [ ] Every rule with state has a case table (`briefs/references/case-tables.md`) and every row is a named test case?

#### Integration-First Gate
- [ ] Contracts / interfaces defined before implementation tasks?
- [ ] Integration tests planned, not just unit tests?

#### [Project-Specific Gate]
- [ ] [e.g. "Security-First: all user inputs validated — name the validation task(s)"]
```

Gate checks run during self-review. A failed gate does not block the plan — it requires a documented justification in the Complexity Tracking section. This makes architectural decisions accountable rather than implicit.

### Task Structure

Each task follows this format:

````markdown
### Task N: [Descriptive Name]

**Objective:** What this task accomplishes (one sentence)

**Files:**
- Create: `exact/path/to/new_file.py`
- Modify: `exact/path/to/existing.py:45-67` (line numbers if known)
- Test: `tests/path/to/test_file.py`

**Interfaces:**
- Consumes: [what this task uses from earlier tasks — exact signatures]
- Produces: [what later tasks rely on — exact function names, parameter and return types. A task's implementer sees only their own task; this block is how they learn the names and types neighboring tasks use.]

**Test cases** (written and run RED by `test-evals`; the implementer does not edit them):

| Test | Behavior | Seam (+ seam note) | Input | Expected | Source of expected |
|---|---|---|---|---|---|
| `test_specific_behavior` | [what the caller observes] | [public entry point] — [catches X, misses Y] | [input] | [value] | [spec AC-3 / worked example / literal] |

- [ ] **Step 1: Confirm the RED tests fail for the stated reason**

Run: `pytest tests/path/test.py::test_specific_behavior -v`
Expected: FAIL — "function not defined"

- [ ] **Step 2: Write minimal implementation**

```python
def function(input):
    return expected
```

- [ ] **Step 3: Run test to verify pass**

Run: `pytest tests/path/test.py::test_specific_behavior -v`
Expected: PASS

- [ ] **Step 4: Hand back for verification** — the orchestrator verifies and commits (`git add src/path/file.py` — the test file was committed RED by `test-evals`).
````

## Writing Process

### Step 0: Consume the spec (if one exists)

Before understanding requirements from scratch, check for a spec artifact:

```python
# Look for specs in the workspace
search_files("*.md", target="files", path=".hermes/specs/")
```

If a spec exists (from the spec turn of this stage), read it and treat it as the **source of truth for WHAT and WHY**. The SKILL.md "Consume the spec first" section holds the folding rules (stories → tasks, NFRs and constraints → Global Constraints verbatim, markers → resolve or carry flagged).

The spec tells you **what** to build. Your plan decides **how**. If no spec exists, infer requirements from the user's description — but note that starting from a spec produces higher-quality plans because intent has already been pinned.

### Step 1: Understand Requirements

Read and understand:

- Feature requirements
- Design documents or user description
- Acceptance criteria
- Constraints

### Step 2: Explore the Codebase

Use Hermes tools to understand the project:

```python
# Understand project structure
search_files("*.py", target="files", path="src/")

# Look at similar features
search_files("similar_pattern", path="src/", file_glob="*.py")

# Check existing tests
search_files("*.py", target="files", path="tests/")

# Read key files
read_file("src/app.py")
```

### Step 3: Design Approach

Decide:

- Architecture pattern
- File organization
- Dependencies needed
- Testing strategy

### Step 4: Write Tasks

Create tasks in order:

1. Setup/infrastructure
2. Core functionality (TDD for each)
3. Edge cases
4. Integration
5. Cleanup/documentation

### Step 5: Add Complete Details

For each task, include:

- **Exact file paths** (not "the config file" but `src/config/settings.py`)
- **Complete code examples** (not "add validation" but the actual code)
- **Exact commands** with expected output
- **Verification steps** that prove the task works

### Step 6: Review the Plan

Check:

- [ ] Tasks are sequential and logical
- [ ] Each step is bite-sized (2-5 min); each task is one test cycle worth one reviewer gate
- [ ] File paths are exact
- [ ] Code examples are complete (copy-pasteable)
- [ ] Commands are exact with expected output
- [ ] No missing context
- [ ] DRY, YAGNI, TDD principles applied

### Step 7: Cross-Artifact Consistency (analyze)

If a spec artifact exists, run a cross-artifact consistency check — the plan against the spec, not just the plan against itself. This is the `analyze` phase adapted from spec-kit.

**Coverage check — spec → plan:**

- [ ] Every user story in the spec has at least one task implementing it
- [ ] Every acceptance criterion maps to a task's verification step (test assertion or observable check)
- [ ] Every non-functional requirement appears in Global Constraints or a specific task
- [ ] Every edge case in the spec has a corresponding task or is explicitly deferred with a note
- [ ] Every constraint copied verbatim from the spec, not paraphrased into ambiguity

**Drift check — plan vs spec:**

- [ ] No plan task introduces features absent from the spec (scope creep)
- [ ] No plan task contradicts a spec requirement
- [ ] No `[NEEDS CLARIFICATION]` marker from the spec was silently resolved in the plan without user input

**Gate check:**

- [ ] Every constitution gate either passes or has a documented justification in Complexity Tracking

If the coverage check finds a spec requirement with no task, add the task. If the drift check finds scope creep or contradiction, fix the plan. This check catches the most common planning failure: a plan that looks internally consistent but has drifted from the intent it's supposed to serve.

## Principles

### DRY (Don't Repeat Yourself)

**Bad:** Copy-paste validation in 3 places
**Good:** Extract validation function, use everywhere

### YAGNI (You Aren't Gonna Need It)

**Bad:** Add "flexibility" for future requirements
**Good:** Implement only what's needed now

```python
# Bad — YAGNI violation
class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email
        self.preferences = {}  # Not needed yet!
        self.metadata = {}     # Not needed yet!

# Good — YAGNI
class User:
    def __init__(self, name, email):
        self.name = name
        self.email = email
```

### TDD (Test-Driven Development)

Every task that produces code carries the TDD cycle, split across stages:

1. Name the test cases (this plan)
2. Write them and run to verify failure (`test-evals`)
3. Write minimal code (`build` implementer)
4. Run to verify pass (`build` implementer, then the orchestrator)

### Frequent Commits

The orchestrator commits after every verified task (the implementer does not commit):

```bash
git add [files]
git commit -m "type: description"
```

## Common Mistakes

### Vague Tasks

**Bad:** "Add authentication"
**Good:** "Create User model with email and password_hash fields"

### Incomplete Code

**Bad:** "Step 1: Add validation function"
**Good:** "Step 1: Add validation function" followed by the complete function code

### Missing Verification

**Bad:** "Step 3: Test it works"
**Good:** "Step 3: Run `pytest tests/test_auth.py -v`, expected: 3 passed"

### Missing File Paths

**Bad:** "Create the model file"
**Good:** "Create: `src/models/user.py`"
