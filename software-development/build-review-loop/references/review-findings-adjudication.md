# Review-findings adjudication + recurring test-quality findings (2026-09-01, Dispatch 9)

How the orchestrator handles reviewer output in the build-review loop.

## Contents

- Adjudicate data-source findings against live data freshness, not code comments
- Adjudicate scope-violation BLOCKINGs against the dispatch spec
- Recurring test-quality findings and their fixes
- Recurring production-code findings (reviewers flag these repeatedly)
- Reproduce every finding before dispatching the fix round
- Trace file provenance through the session database when freshness is ambiguous
- Split verdicts (one lane REQUEST CHANGES, one SHIP) are adjudicated by probe, not by majority
- Two reviewers in one loop: depth tiers are real — budget accordingly
- Delta re-review: two-part dispatch shape
- Numbered delta findings: carry the evidence into the fix brief, merge overlaps, list the skips
- Fix rounds route back to the builder
- Deferred-with-cap items: give the builder a time box and a stop rule
- Ship-gate adjudication: reproduce, then reclassify with live data
- Delta rounds demand fix rounds; the final confirmation round can still find test-coverage gaps
- Bind adjudications in the re-review prompt to stop re-litigation
- Reviewer verification requests pay off — encode them as facts
- Builder accommodations and disagreements are adjudicated in the round, not passed through
- A test can pin a spec violation — spec wins, retarget under explicit authorization
- Confirm-round convergence on new numeric/scoring code: fresh full-state diffs, one more evasion class per round
- Severity disagreement between reviewers is resolved by the reproducing probe, not by consensus

## Adjudicate data-source findings against live data freshness, not code comments

When a reviewer flags "X overrides Y" as a data-integrity bug, do not accept
or dismiss it from the code alone. Determine which source is actually FRESH on
the live install: compare record counts and mtimes in both stores (e.g. YAML
file vs SQLite KV row), and trace which surface (daily briefing, weekly
review, CLI) reads which side. A reviewer's prescribed fix can be exactly
backwards when its premise ("SQLite is authoritative") is false on the live
install — the code comment may name one authority while real edits land only
in the other. The finding's OBSERVATION may still be real (two stores CAN
diverge); split the finding: dismiss the prescribed fix with evidence, keep a
reframed finding ("add a divergence check / pick one source order explicitly")
in the fix brief.

Corollary — reviewer probes inherit your fixture bugs: when two reviewers
claim the same misbehavior ("migration clobbers the store", "get_kv returns
YAML over the store") and your own probe CONFIRMS it, check the probe's
fixture before writing the fix brief. A fixture created at the wrong DB path
or with the wrong table schema reproduces phantom clobbers — the migration
wrote beside your fixture, your read hit the fresh file, and the 'clobber'
was the migration seeing an empty store. Rebuild the fixture through the
module's own path resolver and schema, re-run the probe, and only then
adjudicate; two independent reviewers agreeing on a phantom is possible when
both read the same wrong fixture premise in the code-under-probe's
environment, but a probe that contradicts the code's own tests is suspect
first. (Cost of missing this: one full adjudication cycle re-derived findings
the code never had.)

## Adjudicate scope-violation BLOCKINGs against the dispatch spec

Codex flagged "changes files outside the permitted boundary" as BLOCKING because
the diff touched `VERSION`, `diagnostics.ts`, and test version-pins. But the
dispatch spec HAD ordered the version bump ("bump it" was an explicit gate
item), and BRIEF.md's own spec-append was in the diff. Reverting would have
been wrong.

Rule: when a reviewer claims scope violation, diff the finding against the
dispatch spec BEFORE reverting. Spec-ordered changes are not violations —
dismiss with cause and say so in the report ("dismissed: spec item 6 ordered
this bump"). Do not silently ignore a BLOCKING either: adjudicate it on the
record. If the reviewer was right that something crept in un-ordered, revert
that hunk only.

## Recurring test-quality findings and their fixes

All four appeared in one Codex review of bridge-layer tests; expect them again.

1. **Hook-bypass tests (MAJOR).** A test for a history-patching hook called
   `syncReservedRouteAttr()` MANUALLY right after `pushState`/`replaceState` —
   it passes even if the hook never patches anything. Fix: fire the history
   call and assert the DOM attribute directly, no manual sync; add a real
   back/forward case (`pushState` to a route, `history.back()`, wait for the
   popstate that actually restores the prior hash — jsdom can emit a stale
   popstate while still on the old URL, so gate on the hash, not the event).
2. **Loose string-grep CSS tests (MINOR).** Asserting `border-radius: 12px`
   appears "somewhere in mobile.css" passes forever — the token can move to an
   unrelated rule. Fix: parse CSS into (selector, body) rule blocks (a small
   `cssRules()` helper) and assert the selector AND declaration coexist in the
   same block.
3. **Single-open DOM tests (MINOR).** Opening an injected panel once proves
   nothing about re-open idempotence (duplicate rows/icons, leaked listeners).
   Fix: open → close → reopen, then assert EXACTLY one list, exactly N rows
   (one per config entry), exactly one icon per row.
4. **Over-broad state selectors (NIT).** A chevron-rotate rule targeting every
   descendant SVG in a disclosure button works today but rotates any future
   leading icon too. Fix: target the specific child the renderer renders last
   (e.g. `button[aria-expanded="true"] > span:last-child :is(svg, …)`).

## Recurring production-code findings (reviewers flag these repeatedly)

- **`except OSError` does not catch `UnicodeDecodeError`** — `Path.read_text`
  raises `UnicodeDecodeError`, which subclasses ValueError, not OSError. In a
  per-item aggregator (read every file in a directory, count matches), one
  unreadable item then unwinds to the OUTER handler and zeros the whole
  aggregate report — a single non-UTF-8 file erased every section of a weekly
  summary. Fix shape: wrap the read per item, catch `(OSError, ValueError)`
  (or `UnicodeDecodeError` explicitly), `continue`; keep the outer
  catch-all for genuinely unexpected failures only. Same audit applies to any
  new `read_text` a fix round adds.

## Reproduce every finding before dispatching the fix round

A reviewer's finding is a claim about code behavior, not a fact. Before the fix
brief goes out, reproduce each finding against the current tree with a minimal
probe (import the function, call it with the flagged input, observe). Three
outcomes, each handled differently:

- **Reproduced as stated** — forward verbatim into the fix brief, with the
  probe's observed output as evidence so the builder doesn't re-derive it.
- **Not reproduced as stated but a real variant exists** — rewrite the finding
  in the brief to the verified form. A builder given a false repro either burns
  a round on a non-bug or "fixes" the wrong thing; the corrected variant keeps
  the reviewer's insight and drops the wrong mechanism.
- **Not reproducible at all** — dismiss with cause on the record, citing the
  probe — but if the finding is plausible, tell the builder to RE-VERIFY it
  first with its own probe before treating it as dismissed (a delta-round
  hard-link claim the orchestrator could not reproduce was sent back for
  re-verification rather than dismissed, because the orchestrator's probe was
  itself ambiguous: the source file's text looked tokenised).

Trust the probe only after checking the probe itself: build it to PASS on
known-good input first, then point it at the flagged inputs. A probe that omits
a required field (e.g. a schema-validation probe missing the document's
`$schema`) makes every finding look accepted or rejected for the wrong reason —
it tests the probe, not the code. On one dual review, 8/8 semantic findings
initially read as "schema rejects them" because the probe document lacked
`$schema`; the corrected probe showed all 8 were genuinely accepted and all 8
were real findings. Conversely one overwrite claim did not reproduce as stated
but a real collision variant did — the brief carried the corrected form.

Ambiguous probes: check the OBSERVER before trusting a negative. When a probe
compares two paths that are hard links to one inode (or otherwise aliases),
reading either path shows the other's contents — 'source unchanged' may mean
the reference copy itself moved. Write a reference copy BEFORE the operation,
compare bytes against that copy, and check `os.stat().st_ino`/`samefile` when
aliasing is possible. A hard-link overwrite claim dismissed as
'not reproduced' was in fact real; the builder's careful re-probe (reference
bytes captured first, inode checked) flipped the verdict. When your own probe
is ambiguous — you cannot state confidently which file changed — do not
dismiss; send the item back for builder re-verification with an explicit
instruction to re-probe before fixing.

Also: fix-round findings cluster by SUBSYSTEM, and a stale-brief race makes
the split invisible. When a fix round's brief was superseded mid-flight, the
builder may deliver only the OLD brief's items — items verified as still
reproducing after the round are NOT 'the fix failed', they are 'never
dispatched'. Enumerate the still-failing items explicitly in the follow-up
brief (with fresh probe output as evidence) instead of re-sending the whole
superseded brief.

Probe fixtures must resolve storage paths through the CODE's own resolver,
not the layout you assume. A hand-built SQLite fixture at a path the module
does not actually use (e.g. `{root}/.state/state.db` when the code opens
`{project_root}/state.db`) splits the probe across two databases: guards look
like they clobber data (the write landed in the fresh DB the code created
beside your fixture), divergence checks read the wrong row, and findings get
confirmed or dismissed for phantom reasons — an entire verification pass ran
against the wrong file before the fixture was corrected and every verdict
changed. Import the module's path resolver (e.g. `_db_root(config)`) and
create the fixture exactly there, then assert the seed row is visible through
the module's own read API BEFORE running the probe body. Confirm through the
module's read path, not just file existence: a fixture built with a guessed
row schema (3-column table instead of the real `(store_name, key, value,
updated_at)` PK layout) makes the module's own read return wrong data and the
migration's overwrite look like a clobber — the probe must round-trip the
seed through the module's API first.

## Trace file provenance through the session database when freshness is ambiguous

mtime + record counts say WHICH source is fresher, not WHO wrote it or why. When
a dual-store divergence needs a ruling (is the newer YAML a stray hand-edit or
the operator's real state?), query the Hermes session database (the profile's
`state.db`, `messages` table) for the file's write history:
`SELECT session_id, datetime(timestamp+28800,'unixepoch'), tool_name,
substr(content,1,150) FROM messages WHERE content LIKE '%<filename>%' AND
tool_name IN ('write_file','patch') ORDER BY rowid` — the matched rows give the
writing session, timestamp, and (via the assistant message's `tool_calls` JSON)
the full written content. A write made at the user's explicit request inside a
deliberate session is authoritative state; an old migration artifact is not.
One query settles what code comments and reviewer premises cannot. Adjust the
timezone offset (+28800 = UTC+8) to the deployment's zone.

Expect asymmetric evidence from the two reviewers: the execution-enabled one
(Codex, danger-full-access) probes runtime behavior with in-memory calls and its
runtime claims are usually repro-provable in minutes; the static one (Claude
Code sandbox) cites file:line from reading — its line citations reliably check
out, but its premises about which data source is authoritative still need the
live-data check above. Adjudicate each on its own evidence, not its lane.

The static lane can also lose code execution ENTIRELY (sandbox denies even
`.venv/bin/python` probes) while still returning a full structured review.
Read its opening line for the admission ("I could not execute Python in this
session") and treat the whole report as static-only: every runtime claim in it
needs an orchestrator probe before entering a fix brief, and its per-item
FIXED/PARTIAL table is code-quote evidence, not probe evidence. Do not
dismiss the report for the gap — static-only findings on the same round still
included a real status-vocabulary regression and a silent-failure handler the
execution lane missed. Also note its verdict can arrive without any full-suite
run: it cannot confirm the builder's suite count, so run the suite yourself
(the orchestrator runs it every round regardless).

Static-lane dispatches fail more often and for simpler reasons than
execution-lane dispatches: expect one relaunch per dual review. The two failure modes are (a) permission flags rejected under root
(`--dangerously-skip-permissions` never works as root — see
tool-mechanics-pitfalls #34) and (b) sandbox path errors — the reviewer
sandboxed to the repo cannot read prompt files in /tmp; relaunch with
`--add-dir /tmp/<briefdir>`. Budget the wall-clock for one static-lane retry
when scheduling the round; a dead static lane discovered only at synthesis
time halves the review for free.

Treat a reviewer's own full-suite failure count as environment evidence, not a
regression claim. A reviewer whose sandbox lacks the project's optional deps
(`google-auth`/`pymupdf`/`msal`-class packages) reports "N passed / 23 failed"
with every failure an import error — that is a report that the TARGETED suites
it ran are green and its environment is incomplete. Never forward such a list
as a regression finding; the orchestrator's own full-suite run from the real
environment is the sole authority for "suite green" (run it every round
regardless, and quote your count in the next brief so reviewers stop
re-deriving it).

## Split verdicts (one lane REQUEST CHANGES, one SHIP) are adjudicated by probe, not by majority

A dual review can split: the execution lane returns 1 MAJOR + 1 MINOR with
probes, the static lane returns SHIP with 9 minor/nit findings on the same
delta. Neither verdict word decides — each finding stands on its own
reproduction. An execution-lane MAJOR that the orchestrator's own probe
reproduces (a trend series flatlining at its last nonzero value after the
currency settles, verified in a 20-line temp-dir probe) gets fixed even when
the other lane said SHIP; static-lane minors get triaged as fix-now (cheap,
testable), document-only (an upstream adjudication's consequence — e.g. daily
vs weekly AR semantic split pinned by an attested test — is a documented
split, not a bug), or skip-listed nits. Record the per-finding routing in the
next brief so the final confirmation round knows what was deliberately not
fixed. A SHIP verdict is never overridden by severity inflation from the other
lane; a SHIP never overrides a probe-confirmed MAJOR either.

## Two reviewers in one loop: depth tiers are real — budget accordingly

When dispatching a dual review (Codex + a second reviewer), the second
reviewer is not a redundancy check — it routinely finds a defect class the
first missed entirely. On one repo round, Codex returned 8 findings (3
BLOCKING) while the second reviewer returned 35 (5 BLOCKING) including a
structural defect (a generated artifact retaining all N source instances, so
filling one row duplicated the letter) that BOTH the orchestrator's contract
tests and the first reviewer missed — because the contract test only grepped
concatenated output, which masks per-file duplication. Two rules follow:

1. **Verify the second reviewer's headline (most-severe) claim by direct
   probe before acting on either review** — it may be wrong, but if it
   reproduces, it re-frames the whole fix round. Adjudicate every finding
   against probes, not reviewer authority (see above).
2. **Contract tests that only check aggregate/concatenated output cannot
   catch shape defects in per-item artifacts.** When writing contract tests,
   assert on a SINGLE generated artifact's full content (fill one row, read
   one file, assert the whole text), not on values appearing "somewhere in
   the combined output". The grep-the-concatenation pattern passes even when
   every item is wrong.

Also: run both reviews in parallel from the start (two background sessions,
same prompt file) — a sequential second review doubles wall-clock time for
the same coverage.

## Delta re-review: two-part dispatch shape

Frame the re-review prompt as two explicit jobs, in this order: (1) spot-check
that YOUR OWN prior findings actually landed (name them), (2) hunt for NEW
issues introduced by the fixes themselves. This shape outperforms a generic
'review the diff again' because fix-round regressions cluster in freshly
changed code and reviewers otherwise re-litigate old ground. Pass the commit
range and the prior findings' IDs so the reviewer can map old→fixed. Expect
the delta round to return mostly fix-regressions, not new original findings —
and treat an unfixed prior finding the reviewer re-flags as a fix-round
failure, not a new finding.

Require the verdict to carry a PER-PRIOR-FINDING disposition table:
FIXED / PARTIAL / NOT FIXED with one line of evidence each, then new findings
severity-tagged. A bare verdict lets 'fixed' hide behind a summary; the table
is what the next fix brief maps item-by-item, and a PARTIAL row names the
exact residual (e.g. "week scoping works except undated paid invoices")
instead of reopening the whole finding.

## Numbered delta findings: carry the evidence into the fix brief, merge overlaps, list the skips

When a delta re-review returns numbered findings (e.g. R1-R5 from one
reviewer, N1-N22 from the other), the fix brief carries per item: the
finding, the orchestrator's probe verdict (confirmed / variant /
not-reproduced, with observed output), the mapped fix, and a regression-test
requirement — not a bare forwarding of reviewer text. Overlapping findings
from two reviewers get ONE item noting both IDs, so a follow-up round cannot
double-fix. Triage explicitly: BLOCKING + MAJOR get fixed; NITs go into an
explicit 'skip' list ('unless trivial') — an unlisted nit invites the builder
to spend the round on cosmetics, and an unlisted skip invites re-reporting.
Two failure shapes this avoids: a builder redoes the previous round's work
because the brief it read was superseded mid-flight, and unverifiable claims
get fixed-or-dismissed silently without a recorded verdict.

## Fix rounds route back to the builder

Even when findings are test-only rewrites, dispatch the fix round to the
builder (Cursor) with the findings enumerated verbatim + the fix approach per
finding — do not hand-edit the tests yourself mid-loop. The orchestrator's job
after the fix round is re-running the gates (npm test, tsc, bench) and
spot-checking the specific assertions that were supposed to change.

Exception: a finding whose only fix is a test-expectation edit (the base
branch writes to a different path/shape than the test asserts) is
orchestrator-owned — fix it directly the same turn (see persistent-loop-plan
steering rule #7), then tell the builder the test is fixed and to resume.

## Deferred-with-cap items: give the builder a time box and a stop rule

When an item was deferred in earlier rounds and finally gets dispatched
(party-count inference deferred twice before being built), do not send it as
"also fix this" — give it an explicit cap ("15 min") and a fan-out stop rule
("if the change touches more than the named files, STOP and mark DEFER").
This converts a scope-creep risk into a bounded attempt, and the DEFER
outcome is an acceptable report. A bounded attempt that lands cleanly beats
an unbounded one that eats the round.

## Ship-gate adjudication: reproduce, then reclassify with live data

A confirmation pass that returns DO-NOT-SHIP on residuals needs three
orchestrator actions before the next fix round:

1. **Reproduce each NOT-RESOLVED claim** (probe against current HEAD — see
   above). Claims that reproduce get exact probe scripts in the fix brief.
2. **Read the live source-of-truth data once** and check whether the trigger
   case can actually occur in production (a header-position collision the
   production sheet never produces is hardening, not ship-blocking).
3. **Decide ship vs one-more-round with the severity table, not the verdict
   word** — a DO-NOT-SHIP whose residuals are one live-triggerable edge
   (merge/twin records) plus two hardening/cosmetic items may still justify
   the round if the wedding/deadline is near; present the user a compact
   choice (fix vs ship-with-known-issues) and default to the recommended
   option on no-response rather than blocking.

## Delta rounds demand fix rounds; the final confirmation round can still find test-coverage gaps

Expect each delta round to demand its own fix round even when the item count
shrinks — and expect the release-gate (SHIP-verdict) round to still return
2-3 MINOR test-coverage gaps: tests whose NAME advertises a property the
assertions do not pin (a kind-filter test whose two snapshot kinds share one
key — deleting the filter still passes), and negative-fixture tests that
assert a vacuous literal ("a source-code string never appears in rendered
HTML") instead of feeding the forbidden input and asserting its absence.
Fix shape: the discriminating fixture (distinct key per kind; a real
conflicting top-level field that must NOT appear in the render) plus one
consistency nit (route every call site through the dedicated helper rather
than two spellings of the same lookup). These are builder-dispatch items —
but when they are the ONLY remaining items and are one-line test edits, the
orchestrator may close them directly as test-only changes, then run the
touched files. Also ask the reviewer to double-check its OWN new tests in the
delta: a builder writing this round's `test_*_rN.py` can pin dedupe while
leaving the kind filter its test name promises unguarded.

## Bind adjudications in the re-review prompt to stop re-litigation

When the orchestrator overrules a reviewer's prescribed fix (e.g. both
reviewers said "store-first, drop the YAML read" and live data proved YAML
fresh and correct), write the ruling INTO the next review prompt as a binding
adjudication list: "X was adjudicated — do not re-propose Y. Here is why." A
reviewer not bound re-derives the same wrong premise and re-flags it, burning
a round. Pair each binding with the one-line evidence so a reviewer that
disagrees can challenge it on facts rather than silently complying. Also list
the orchestrator's already-completed independent verifications (suite count,
byte-identical render probes, live-install divergence probes) as "already
done — do not redo, may spot-check": reviewers otherwise spend their context
re-running the same suite instead of hunting what the probes would miss (logic
errors, HTML escaping of newly interpolated values, contract drift between a
producer's output keys and the renderer's expectations), and treat accepted
builder disagreements as settled design, not findings.

Also bind the builder's accepted ACCOMMODATIONS: when a builder reports "item
implemented, except the strictest form would break an attested test — left
lenient there", adjudicate it in the same round: either accept the leniency
(it is fixture-mandated, not a defect) and list it as settled in the next
review prompt, or schedule a re-attestation round that tightens the fixture.
An unbound accommodation gets re-reported by the next reviewer as a fresh
PARTIAL finding at full severity. (v0.5.7: undated-paid leniency and the
doctor never-written mapping were both fixture-mandated; both were accepted
and bound in the r3 review prompt before the reviewers could re-flag them.)

Bind the orchestrator's OWN spec errors the same way when they surface as
findings: when the true root cause is a defect in your brief or red test
(wrong import name, wrong baseline for a byte-identity probe, a fixture at a
path the module never opens), fix the artifact yourself, re-attest, and add
the corrected rule to the next brief as settled — otherwise the next reviewer
re-derives the same defect from your artifact and re-flags code that is now
correct. Byte-identity baselines specifically: diff against the commit BEFORE
the whole feature series began, never the previous fix round's commit — a
baseline that already contains the fix reports a false diff and costs a
re-derivation.

Re-attestation mechanics when a binding changes an attested assertion: the
orchestrator edits the test file itself (test-only code, see `review-findings-adjudication.md` — own the fixture fix),
re-runs it to confirm it now FAILS against current code (the red state is the
contract the builder must satisfy), runs `attest_file.py attest` with the
ruling in the --note, and commits both files in one commit BEFORE the builder
dispatch. An attested test re-attested but still green against the old code
locks the bug in as the new contract.

## Reviewer verification requests pay off — encode them as facts

Telling the reviewer "verify against the bundles, don't assume" produced the
chevron finding being confirmed-correct (renderer really sets
`aria-expanded`) and a NIT about breadth. Always include the instruction to
verify claims against the read-only source/dist, and pre-verify the
highest-risk claims yourself so you can adjudicate rather than relay.

## Builder accommodations and disagreements are adjudicated in the round, not passed through

When a builder reports "implemented, except X where the strict reading would
break an attested fixture — left lenient" or "did Y differently from the brief
because Z", do not forward either to the reviewers as a finding-shaped item.
Adjudicate each in the same round: accepted accommodations (fixture-mandated
leniency) and accepted disagreements (a builder's brief clause was wrong, e.g.
registering a derived store would make doctor warn) become settled design, and
the next review prompt binds them like any other adjudication. An unbound
builder-disagreement re-enters the next review as a fresh finding and burns a
round; a builder disagreement that is genuinely wrong is instead re-dispatched
with the corrected reasoning — not left for reviewers to rediscover.

## A test can pin a spec violation — spec wins, retarget under explicit authorization

When a review flags that a behavior violates the spec AND a test currently pins
that behavior (e.g. a RED test asserting install "never mutates the review
queue" while the spec says cron creation IS a review-queue action), the spec
wins — but tests are normally untouchable, so the retarget needs explicit
authorization in the fix brief: name the exact test, the exact new assertion,
and the one-line justification. Two follow-through rules:

1. **Check the sibling pins before dispatching.** One retarget usually forces
   others in the same file that pinned the old behavior (idempotent reinstall
   via direct shell, doctor reconciliation after install) — retarget each
   minimally and list every test edit with a one-line justification in the fix
   report, or the next reviewer flags them as coverage erosion.
2. **Distinguish the primitive from the operator surface.** When the finding
   targets a flow the operator reaches (`workflows install`) but the primitive
   beneath it (`install_workflow_cron`) has a dozen direct-call tests that are
   NOT authorized to retarget, gate the operator surface only, implement the
   primitive as the post-claim executor, and record the deviation explicitly —
   an unrecorded half-gate reads as the fix being done when the API path still
   bypasses it.

Related: the weak strip-contract test that let the violation through asserted
an OR-chain (`"HALT" in strip or "DEGRADED" in strip or "GO" in strip`) — a
tautology that passes on essentially any non-empty output. When a fix brief
retargets a weak contract, pin the SPEC'S WORDING (the exact phrase US-8
specifies), not another OR-chain; and grep new RED test files for
`assert A or B or C`-shaped assertions on outputs that must be exact.

## Confirm-round convergence on new numeric/scoring code: fresh full-state diffs, one more evasion class per round

When the reviewed artifact is new scoring/matching/normalization code (not a
diff of a mature system), each fresh full-state diff surfaces exactly one more
evasion class the previous fix created or exposed: spelled-out magnitude
words → overlapping year ranges → comma-grouped numbers and digits inside
product tokens → occurrence-level vs whole-text exclusion rules. Two
practices make the loop converge instead of drift:

1. **Dispatch every confirm round on a FRESH full-state diff exported at
   dispatch time, and re-derive the regression sweep before trusting the fix.**
   A confirm round judges the current state, not the incremental round diff.
   Before dispatching, run an in-process sweep of every prior finding's input
   pair — a scripted probe of ~20 named cases takes seconds and catches the
   fix that breaks a prior round's behavior (a whole-text boundary rule fixed
   one evasion but missed the case where a bare year elsewhere in the same
   sentence excused the embedded digits inside a product token).
2. **Carry an explicit do-NOT-re-report list of accepted design limitations
   in every confirm prompt**, and grow it each round. A reviewer without the
   list re-litigates accepted semantics as findings (negation not parsed,
   format variants counted separately, figure cap firing on missing signal)
   and drowns the one real new finding. The prompt also asks the reviewer to
   probe the specific class just fixed ("check the boundary-consistency of
   the year-exclusion rule") — the hunting instruction that finds the next
   evasion class.

Also on this code class: patch the DESIGN (boundary semantics shared by the
exclusion rule and the year extractor), not the instance — a one-off helper
that scans the whole text re-introduces the whole-text-vs-occurrence bug the
design already had; the occurrence-level check (look at the characters
immediately adjacent to each match) is the fix that survives review.

Also note the line-citation hazard when relaying findings: a reviewer's
"the weak contract lives at file.py:365-389" may point at a DIFFERENT test
than the one that actually pins the behavior (line ranges drift as files grow).
Grep for the assertion's content, not the cited line, before writing the
retarget.

## Severity disagreement between reviewers is resolved by the reproducing probe, not by consensus

The two reviewers can flag the SAME code path at different severities (one
MINOR, one MAJOR). The severities describe each reviewer's own worst
imagined outcome; the probe shows the ACTUAL one. Run the probe and set the
brief's severity from what reproduces: a MINOR-labeled claim whose probe
shows unrecoverable data loss is a MAJOR item; a MAJOR-labeled claim whose
probe shows only a cosmetic warning is a MINOR. In one round the same
strip-before-backup ordering produced both a reviewer-MINOR "backup misses
pre-mutation state" and a reviewer-MAJOR "cap-deferred source loses data" —
the probe confirmed the MAJOR outcome (deferred source gutted, nothing
recoverable) and the brief carried MAJOR with both reviewer IDs noted.
Severity is a property of the observed failure mode, not of the reviewer who
reported it; note both reviewer IDs in the brief so the confirm round can
map each to the fix.

## Builder stops on internally inconsistent contract tests — own the fixture fix (moved from SKILL.md pitfalls, 2026-10-16 refactor)

1. **When a reviewer finds your OWN contract tests internally inconsistent, the builder stopping and diagnosing is the correct outcome — own the fixture fix** — the Batch 3 builder was briefed "tests must pass, do not modify them," hit a contradiction (one test demanded v2 repair, another demanded v2 skip), and correctly STOPPED with a diagnosis instead of warping production code or silently weakening tests. The orchestrator then owned the fix: rewrote the fixture to simulate the legacy era faithfully (mutate existing lines + write a v1 digest attesting repaired values — see `tool-mechanics-pitfalls.md` — classify errors by retry semantics) and updated the now-wrong test. Pattern: brief builders with "if the tests contradict the brief, STOP and report — do not force it"; treat a stop-with-diagnosis as a success signal, not a failed build. Test-authoring bugs are Hermes's to fix directly (test-only code, no Cursor dispatch needed — see see `tool-mechanics-pitfalls.md` — contract tests satisfied by unsanctioned design changes).

## Cycle principles distilled from past projects (2026-10-16)

- **Unrelated findings can be ONE missing responsibility.** When an external review groups several findings (a helper, an exit code, a validator placement) under one absence, the group is a diagnosis: nothing owns the concept. Fix the ownership problem, not the three symptoms. A smeared responsibility shows as the same helper, format, or decision copied or re-derived in several places.
- **When a reviewer contradicts a rule you encoded yourself, verify in source, then re-derive the rule.** Fixing by the reviewer's letter alone can break the invariant the rule protects (e.g. rewriting attested values instead of converging with attestation). Encode the derived rule in red tests and put the derivation in the brief — a builder told only "make the finding go away" may implement the wrong mechanism.
- **Present deferred MAJORs as design questions, not to-dos.** "Deferred findings + a user domain concept can dissolve a hazard class — design away the danger, don't patch around it." A product decision can collapse several findings into one design change: split the object into an immutable identity plus a mutable label, derive storage from identity only, and remove dangerous operations from surfaces that do not need them instead of hardening them there.
- **Deferrals recorded with reasons are part of the deliverable.** A deferred item lives in a written artifact with its reason; without it the next round re-litigates.
