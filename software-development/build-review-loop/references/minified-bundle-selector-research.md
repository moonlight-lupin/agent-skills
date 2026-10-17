# Minified-bundle selector research (style against what shipped, not what you guess)

Learned in the Hermes Desktop Android wrapper dispatches (8h→9, 2026-09-01). The
app wraps a Vite-built renderer that is READ-ONLY; all mobile fixes live in a
bridge/tweaks layer of CSS + JS injected over the bundle. Every selector used by
a tweak must be verified against the ACTUAL bundled DOM — twice this project
burned multiple device-test cycles on selectors that "should" exist.

## The technique

The renderer ships as minified dist/www/assets/*.js. Source maps absent.
Extract ground truth with node one-liners (no tooling needed):

    node -e "
    const fs=require('fs');
    const s=fs.readFileSync('app/www/assets/settings-XXXX.js','utf8');
    const i=s.indexOf('Auxiliary models');   // i18n literal from the UI
    console.log(i, JSON.stringify(s.slice(Math.max(0,i-300),i+200)));
    "

What to extract, with examples verified live:

- **data-slot inventory**: match `data-slot` in the bundle — the renderer's own
  semantic hooks; prefer these over class hashes.
- **i18n strings** (i18n-*.js) as anchors: the string you SEE on screen locates
  the component that renders it, even when class names are hashes.
- **Minified component defs**: the anchor region calls sU({...}); find the def
  with `function sU(` or `sU=` and read the JSX it renders.
- **State attributes**: confirm the DOM actually carries the state before
  keying CSS on it. Dispatch 9: the disclosure row does NOT set data-state;
  it renders a button with aria-expanded={open}. Verified by reading the
  minified JSX. (Dispatch 8h: Tailwind v4 compiles -translate-x-1/2 to a
  standalone `translate: -50%` property, NOT transform — geometry CSS must
  target both.)
- **z-index constants**: Radix-style portals carry numeric z from JS constants
  (zIndex:C, Y=10); the settings dialog backdrop is data-overlay-surface with
  fixed inset-0. Pick override values that beat the renderer's own tier (its
  --z-modal-popover: 140) rather than inventing shell-max values.
- **Router flavor**: check the upstream source if present (main.tsx:86
  HashRouter) — route-detection hooks must cover hashchange AND
  pushState/replaceState patches, since HashRouter uses both seams.

## Embed verified facts in the spec

Put the extracted selectors/constants directly in the dispatch brief with
file:line evidence, and mandate "measure, don't guess; verify against
app/www/assets". Result: the builder used correct selectors first try, and the
reviewer's "does the renderer actually set aria-expanded?" question was
pre-answered with bundle evidence.

## Attribute bench noise before blaming the diff

The bench harness may emit pre-existing noise (stale probes referencing
selectors that no longer exist, producing null.getBoundingClientRect page
errors). Attribution recipe: git stash, run bench, git stash pop — if the
noise count matches on clean HEAD, it is not your diff's regression. Compare
geometry values (dock rect, heights) against the last-good baseline JSON instead
of eyeballing.

## Test-quality finding classes (repeat Codex findings)

These classes recur in reviews of tweak-layer work; write tests that resist them:

1. **Manual-sync bypass**: a test calls syncX() by hand right after pushState,
   so it passes even if the production hook never patched pushState. Tests must
   exercise the wiring (fire the navigation, assert the DOM state), never the
   function directly.
2. **Bare-token grep**: asserting `z-index: 140` appears SOMEWHERE in the CSS
   file passes when the declaration moved to an unrelated rule. Parse rules and
   assert (selector, declaration) pairs coexist in the same block.
3. **Single-open DOM tests**: for sheets/lists built by injection, open-close-
   reopen and assert exactly-once counts (one list, N rows, one icon per row).

## Adjudicate reviewer findings against the mandate

The reviewer sees the diff, NOT the dispatch spec. Dispatch 9's Codex run
returned BLOCKING "changes outside permitted scope" for VERSION +
diagnostics.ts edits — those edits were ordered by the spec itself (the
reviewer was never shown the spec). Adjudicate each finding against the
original mandate before dispatching fixes: dismiss-with-cause and document, or
fix. Blindly applying all findings can revert spec-ordered work.

While the review runs, pre-verify its open questions yourself in parallel
(bundle-grep the disputed selector) — it speeds adjudication and catches
reviewer errors before they reach the fix round.
