# CI watch-and-fix loop + PR hygiene

The post-push contract for every branch a build (or fix) produces. Lives here because both CI handling and PR shape are commit-adjacent review duties after the review-commit gate.

## CI watch-and-fix loop

After push:

1. **Watch CI** to completion on the pushed head (background job with notification, not a busy poll). Which lane runs is deployment-specific; a branch with no CI configured ends this loop here — say so and proceed.
2. **Read failing jobs** before changing anything: which job, which step, the exact error. A failure the local suite never produced (timeout, flaky network, resource limit) is classified as environment, not code.
3. **Reproduce locally.** Run the failing job's command set locally. Local green + CI red is an environment/CI-configuration finding, not a fix round on code.
4. **Fix with the same review budget rules** as the confirm rounds of this tier: one CI fix round = one commit addressing the classified failure, re-pushed, CI re-watched. Budget = a fresh confirm budget of the gating tier, separate from the review rounds already spent; when it is spent, stop and report the remaining failure with the analysis — do not keep re-pushing blind.
5. Cap total CI fix rounds at the tier's confirm budget unless the user extends it. Never mark a milestone "done" with red CI on the head that claims it.

**Pre-existing CI failures stay named, not ignored.** A failure present on `main` (or the merge base) before this branch's first push is a pre-existing failure: cite it by job name and error, link it in the PR body, and keep it visible in the final report. It is not "fixed" by ignoring, re-running until green, or marking the check expected-to-fail. Fixing pre-existing failures is a separate decision for the owner — it may be out of this build's scope, but it is never silent.

## PR hygiene

- **Draft PR from the feature branch** at first push (`review-commit`'s Step C opens or updates it; the branch never merges without the gate).
- **Split early.** One concern per PR. Split when the diff passes the milestone size guide (~3,000 changed lines) or when unrelated concerns travel together (a fix plus a feature is two PRs).
- **PR body = intent, test evidence, risk tier.** State what the change does and why, the commands run with their results, what was deliberately not run and why, and the risk tier the review gate set. Link the issue or the spec/plan path when one exists.
- **No force-push to shared or default branches.** The feature branch may rebase its own unreviewed head; anything others may have seen is append-only.
- **No secrets, tokens, keys, recovery codes, or personal paths** in commits, logs, test fixtures, the PR body, or CI output pasted into it.
- **Do not invent CI infrastructure.** These rules describe how to work with the CI a project already has; they do not add GitHub Actions, runners, or new dependencies.

## Interplay with the confirm rounds

CI failures found before the review gate are build defects — fix them inside the build loop and re-enter the gate. CI failures found after the gate has passed are handled by this loop with a fresh confirm budget of the gating tier — separate from the review rounds that gated the branch. Two loops, one budget rule: each draws its own.
