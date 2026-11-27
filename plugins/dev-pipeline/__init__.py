"""dev-pipeline plugin — create-gate policy hook.

Registers a ``pre_tool_call`` POLICY hook that vets ``skill_manage`` calls
carrying ``create`` targets.

What is gated
    Only creates whose ``category`` normalizes (strip + lowercase) to
    ``software-development``. Every other create — different category,
    non-string, or absent — never blocks and never consumes the flag, but it
    DOES count toward the batch rule: an ungated create can add a frontmatter
    claimant mid-batch, so it participates in the multi-entry decision.
    Registered plugin skill names (``dev-pipeline:<stage>``) pass through as
    already-existing.

One flag, one create
    A create is allowed only when the single-use allow flag (active home's
    ``skills/.allow-create``, resolved at decision time) is present, and the
    flag is UNLINKED BEFORE the create passes. One flag authorizes exactly
    one create; an unlink failure blocks with the flag left in place. In a
    mixed batch only the gated create is decided, and one flag still covers
    exactly that one.

Existence check (runtime parity)
    For single gated creates the gate mirrors the runtime ``_find_skill``
    walker: a bare name exists where a ``SKILL.md`` whose enclosing
    directory equals the target name is found under the runtime's active
    skill roots (directory scan first, frontmatter-name pass second,
    ``agent.skill_utils.is_excluded_skill_path`` applied to roots and every
    discovered ``SKILL.md`` at file level, symlinked directories not
    descended). Multiple distinct frontmatter claimants are ambiguous —
    the runtime refuses to guess and creates fresh, so the gate gates it.
    The walker history and round-by-round fix records live in
    ``plugins/dev-pipeline/CHANGELOG.md``.

Batches are gated STRICTER than the runtime
    Both payload shapes are examined (flat create; ``operations`` as list,
    dict, or JSON string, including falsy/unknown shapes, which fall back to
    the flat fields). Payloads with no identifiable create name, and calls
    carrying no flat create, pass with NO decision (ungated). A batch with
    more than one well-formed entry gets NO pre-batch existence
    short-circuit: every well-formed create goes to pending, because
    mid-batch delete/create/patch can invalidate pre-batch directory state.
    Accepting ``already exists`` rollbacks for those is the documented
    over-gating. A single-entry batch keeps full runtime-parity existence
    checking ONLY when it has a single create, no mutating operation, and no
    other create of any category. Creates whose names are outside the
    well-formed set are rejected regardless of the flag, and the flag is
    left in place.

Fail-closed contract
    A ``pre_tool_call`` callback that raises or times out blocks the tool
    (hermes_cli/plugins_dispatch.py). This hook relies on it deliberately:
    non-``skill_manage`` calls return ``None`` before any fallible code, and
    on a create decision there is NO blanket try/except — an unexpected
    internal error propagates and becomes a block. An undecided gate must
    never pass a create.

Accepted boundary risks (documented, deliberate)
    1. File-tool bypass: the hook gates ONLY ``skill_manage``. The allow flag
       is an ordinary file the agent can write itself, and skills can be
       created outside ``skill_manage`` with terminal/write_file. The flag
       therefore asks for consent on the skill_manage path; consent across
       other tools depends on those tools' own policies.
    2. TOCTOU: the decision is a snapshot of the tree at decision time —
       parallel tool calls may interleave mutations between decision and
       execution, and the gate cannot serialize them.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# This plugin's OWN bundled stage skills. register() registers them under their
# QUALIFIED names '<namespace>:<name>' (hermes_cli/plugins_content.py
# ``register_skill``: ``qualified = f"{namespace}:{name}"`` with namespace =
# ``manifest.skill_namespace or manifest.name`` -> 'dev-pipeline:spec', etc).
# The bare names ('spec', 'build', ...) are NOT registered skill names — a
# create of a bare stage name is a genuinely NEW skill and requires the flag.
_BUNDLED_SKILLS = (
    "spec",
    "build",
    "review-commit",
    "test-evals",
    "grill",
    "orchestrator",
    "review-lessons",   # v0.2: lessons library split out of review-commit
    "briefs",           # v0.3.1: brief templates, case tables, stamp script
)

_PLUGIN_SKILL_NAMESPACE = "dev-pipeline"

_FLAG_BASENAME = ".allow-create"

# Mirror of the runtime name rule (tools/skill_manager_tool.py L112):
# ``VALID_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9._-]*$')`` with
# ``MAX_NAME_LENGTH = 64``. Dots allowed; uppercase and homoglyphs rejected.
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_NAME_MAX = 64

# Scanner exclusions. PRIMARY source: the runtime's own constants
# (agent.skill_utils EXCLUDED_SKILL_DIRS / SKILL_SUPPORT_DIRS) so the gate and
# the runtime walker cannot drift; the mirrored literals below are the
# fail-safe only for a gate running outside a Hermes process. Pruning is done
# at walk time by DIRECTORY-NAME membership as an OPTIMISATION for ordinary
# trees; it is NOT the authoritative filter. The authoritative claimant filter
# is the runtime's post-hoc ``is_excluded_skill_path`` parts check applied to
# EVERY discovered SKILL.md's full path (``_file_is_excluded``) - round-6
# found real trees (a root whose top-level SKILL.md is a directory) where
# walk-time pruning alone let an excluded nested SKILL.md count as a claimant.
_EXCLUDED_SKILL_DIRS_FALLBACK = frozenset((
    ".git", ".github", ".hub", ".archive", ".curator_backups", ".locks",
    ".venv", "venv", "node_modules", "site-packages", "__pycache__",
    ".tox", ".nox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
))
_SKILL_SUPPORT_DIRS_FALLBACK = frozenset(("references", "templates", "assets", "scripts"))


def _scanner_exclusions() -> tuple[frozenset, frozenset]:
    """(excluded dir names, support dir names) — runtime constants when importable."""
    try:
        from agent.skill_utils import EXCLUDED_SKILL_DIRS, SKILL_SUPPORT_DIRS

        return frozenset(EXCLUDED_SKILL_DIRS), frozenset(SKILL_SUPPORT_DIRS)
    except Exception:
        logger.debug(
            "dev-pipeline create-gate: agent.skill_utils constants unavailable; "
            "using mirrored exclusion fallbacks", exc_info=True)
        return _EXCLUDED_SKILL_DIRS_FALLBACK, _SKILL_SUPPORT_DIRS_FALLBACK


# Diagnostic size guard for the recursive walk: when a root yields MORE than
# this many SKILL.md-bearing directories, warn ONCE (per process) that the
# root is large. The walk itself is NEVER truncated — a truncated walk would
# report a late-listed skill as nonexistent (a false block), which is worse
# than one slow walk on a big skills tree.
_WALK_GUARD = 10_000
_walk_guard_warned = False


def _hermes_home() -> str:
    """Active Hermes home: runtime resolver first, env fallback, platform default."""
    try:
        from hermes_constants import get_hermes_home

        return str(get_hermes_home())
    except Exception:
        logger.debug("dev-pipeline create-gate: hermes_constants unavailable", exc_info=True)
        return os.environ.get("HERMES_HOME") or os.path.expanduser(os.path.join("~", ".hermes"))


def _skill_roots() -> list[str]:
    """The ACTIVE profile's real skill roots — exactly what the runtime resolves.

    Primary source: agent.skill_utils.get_all_skills_dirs() — the active
    profile's skills dir, then ``skills.create_dir``, then
    ``skills.external_dirs`` (config). Fallback when the runtime import is
    unavailable: the active home's ``<home>/skills``. Sibling profiles
    (``<home>/profiles/*/skills``) are deliberately NOT roots: the runtime
    creates a name that exists only in an inactive profile fresh in the
    ACTIVE profile, so such a name must stay gated (fix #1, round 3).
    Unreadable roots are skipped by the caller.
    """
    roots: list[str] = []
    try:
        from agent.skill_utils import get_all_skills_dirs

        for d in get_all_skills_dirs():
            roots.append(str(d))
    except Exception:
        logger.debug("dev-pipeline create-gate: runtime skill roots unavailable", exc_info=True)
    home = _hermes_home()
    roots.append(os.path.join(home, "skills"))
    seen: set[str] = set()
    return [r for r in roots if not (r in seen or seen.add(r))]


def _flag_path() -> str:
    return os.path.join(_hermes_home(), "skills", _FLAG_BASENAME)


def _path_safe(name: str) -> bool:
    """Safe to use as ONE path component in a skills root."""
    return (
        isinstance(name, str)
        and bool(name)
        and name not in (".", "..")
        and "/" not in name
        and "\\" not in name
        and os.sep not in name
        and (os.altsep is None or os.altsep not in name)
    )


def _name_well_formed(name: str) -> bool:
    """Matches the runtime's actual create-name rule (dots allowed)."""
    return (
        isinstance(name, str)
        and len(name) <= _NAME_MAX
        and _NAME_RE.match(name) is not None
    )


def _registered_plugin_skill(name: str) -> bool:
    """'dev-pipeline:<stage>' — the qualified name register_skill actually registers.

    hermes_cli/plugins_content.py, register_skill(): ``qualified =
    f\"{namespace}:{name}\"`` (namespace = ``manifest.skill_namespace or
    manifest.name``, dev-pipeline is a local plugin so the namespace is its
    manifest name). Names of OTHER plugins' namespaces are unknown here and do
    NOT count as existing.
    """
    ns, sep, bare = name.rpartition(":")
    if not sep:
        return False
    return ns == _PLUGIN_SKILL_NAMESPACE and bare in _BUNDLED_SKILLS


# The ONLY category the create-gate reserves (v0.1.7): a create call whose
# category normalizes (strip + lowercase) to this string is gated; every
# other category — and a create with no category at all — passes ungated.
_GATED_CATEGORY = "software-development"


def _is_gated_category(category) -> bool:
    """True iff the create call's category IS the gated one (software-development).

    Normalization: the comparison runs on ``category.strip().lower()``, so
    case variants and surrounding whitespace ('Software-Development ',
    'SOFTWARE-DEVELOPMENT', ' software-development ') all gate. A NON-STRING
    category (or None/absent/empty/whitespace-only) is NOT gated: those
    creates pass through the decision pipeline unconsumed. (The runtime
    validates non-string categories itself; the gate has nothing to decide.)
    """
    return (
        isinstance(category, str)
        and category.strip().lower() == _GATED_CATEGORY
    )


def _frontmatter_name(skill_md: str):
    """Runtime ``_read_frontmatter_name`` mirror (tools/skill_manager_tool.py).

    Frontmatter ``name:`` — the name ``skills list`` displays — truncated to the
    same ``MAX_NAME_LENGTH`` budget. Same read as the runtime:
    ``utf-8-sig`` (strips a Notepad BOM) with ``errors="replace"``, the first
    4000 characters parsed by ``agent.skill_utils.parse_frontmatter`` (whose
    own failure mode for malformed YAML is key:value line splitting). An
    unreadable SKILL.md simply has no second name. Only a non-OSError failure
    of the runtime parser propagates — exactly like the runtime's fallback
    lookup, where it too would break ``_find_skill`` (fail closed).
    """
    try:
        with open(skill_md, "r", encoding="utf-8-sig", errors="replace") as f:
            content = f.read(4000)
    except OSError:
        logger.debug("dev-pipeline create-gate: frontmatter read failed for %s", skill_md, exc_info=True)
        return None
    try:
        from agent.skill_utils import parse_frontmatter

        frontmatter, _ = parse_frontmatter(content)
    except ImportError:
        # Same key:value line-splitting fallback parse_frontmatter itself uses
        # when nothing better is importable — keeps the gate hermetic outside a
        # Hermes process (runtime parity elsewhere is unaffected: it prefers
        # the runtime parser whenever that imports).
        frontmatter = _fallback_frontmatter(content)
    name = frontmatter.get("name")
    if isinstance(name, str):
        return name[:_NAME_MAX]
    return None


_FM_FENCE_RE = re.compile(r"\n---\s*\n")


def _fallback_frontmatter(content: str) -> dict:
    """Only when agent.skill_utils is unavailable: parse_frontmatter's own line-splitting shape."""
    if not content.startswith("---"):
        return {}
    end = _FM_FENCE_RE.search(content[3:])
    if not end:
        return {}
    frontmatter: dict = {}
    for line in content[3:end.start() + 3].strip().split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()
    return frontmatter


def _walk_find_dir(root: str, name: str) -> bool:
    """ONE root's directory-name scan — pass 1 of the runtime ``_find_skill`` mirror.

    The walk is the direct mirror of ``_find_skill``'s engine
    (``_iter_skill_dirs`` → ``root.rglob("SKILL.md")`` filtered by
    ``agent.skill_utils.is_excluded_skill_path``) restricted to the
    DIRECTORY-NAME match: a skill dir is any directory holding a SKILL.md not
    inside an excluded/dependency dir and not inside a support dir
    (references/templates/assets/scripts) that sits directly under a
    SKILL.md-bearing skill dir. SYMLINKED DIRECTORIES ARE NOT DESCENDED
    (os.walk default, ``followlinks=False``), which is the runtime walker's own
    behavior — pathlib ``rglob`` does not follow directory symlinks either, so
    a name reachable ONLY through a symlinked dir counts as nonexistent in
    BOTH resolvers. No truncation: the walk always completes; oversized roots
    only log a warning once. NOTE on "walk failure": ``os.walk`` silently
    SKIPS a directory it cannot list (permission/ACL) and raises nothing, so a
    walk never "fails" with an error — an unreadable root contributes NOTHING
    and every name under it resolves as NEW, i.e. the effect is the FAIL-SAFE
    BLOCK, never a pass.
    """
    global _walk_guard_warned
    excluded, support = _scanner_exclusions()
    seen_skill_md = 0
    for dirpath, dirnames, filenames in os.walk(root):
        has_skill_md = "SKILL.md" in filenames
        dirnames[:] = [
            d for d in dirnames
            if d not in excluded
            and not (has_skill_md and d in support)
        ]
        if has_skill_md:
            seen_skill_md += 1
            skill_md = os.path.join(dirpath, "SKILL.md")
            if _file_is_excluded(skill_md):
                continue  # runtime exclusion at full path: never a claimant
            if not os.path.exists(skill_md):
                # F1: a DANGLING SKILL.md symlink must never be a claimant.
                # Measured under the runtime interpreter (py3.14): Path.rglob
                # DOES yield dangling links, so the runtime dedup there
                # reports already-exists (nothing fresh is created) — this
                # exists() check is then STRICTER than the runtime (over-block,
                # safe direction). On interpreters where rglob requires
                # existence (<=3.12 behavior), it is exact parity. Either way
                # the gate never passes a name the runtime would create fresh.
                continue
            if os.path.basename(dirpath) == name:
                return True  # runtime returns on the first dir hit: read no further
    if seen_skill_md > _WALK_GUARD and not _walk_guard_warned:
        _walk_guard_warned = True
        logger.warning(
            "dev-pipeline create-gate: large skills root (%d SKILL.md dirs > guard %d) at %s — "
            "walk completed in full; guard is diagnostic only, never truncated",
            seen_skill_md, _WALK_GUARD, root)
    return False


def _walk_find_frontmatter(root: str, name: str) -> set[str]:
    """ONE root's frontmatter scan — pass 2 (the runtime's final lookup step).

    Runs only after EVERY root's directory-name scan has failed (sequence
    parity with the runtime, which reads frontmatter only as a last resort).
    Claimants are deduped by the RESOLVED SKILL.md FILE (realpath) — the
    runtime's dedupe key ``skill_dir / "SKILL.md"``, resolved — so two
    directories symlinking one SKILL.md are ONE holder, exactly like the
    runtime: a shared backing file is not a display-name ambiguity. Directory
    pruning is identical to the directory-name pass, and the same
    silent-skip-on-unreadable caveat applies (a name found only by an
    unreadable root resolves as NEW: fail-safe block, never a pass).
    """
    global _walk_guard_warned
    excluded, support = _scanner_exclusions()
    fm_matches: set[str] = set()
    seen_skill_md = 0
    for dirpath, dirnames, filenames in os.walk(root):
        has_skill_md = "SKILL.md" in filenames
        dirnames[:] = [
            d for d in dirnames
            if d not in excluded
            and not (has_skill_md and d in support)
        ]
        if has_skill_md:
            seen_skill_md += 1
            skill_md = os.path.join(dirpath, "SKILL.md")
            if _file_is_excluded(skill_md):
                continue  # runtime exclusion at full path: never a claimant
            if not os.path.exists(skill_md):
                # F1: a DANGLING SKILL.md symlink must never be a claimant.
                # Measured under the runtime interpreter (py3.14): Path.rglob
                # DOES yield dangling links, so the runtime dedup there
                # reports already-exists (nothing fresh is created) — this
                # exists() check is then STRICTER than the runtime (over-block,
                # safe direction). On interpreters where rglob requires
                # existence (<=3.12 behavior), it is exact parity. Either way
                # the gate never passes a name the runtime would create fresh.
                continue
            fm = _frontmatter_name(skill_md)
            if fm == name:
                try:
                    fm_matches.add(os.path.realpath(os.path.join(dirpath, "SKILL.md")))
                except OSError:
                    fm_matches.add(os.path.abspath(os.path.join(dirpath, "SKILL.md")))
    if seen_skill_md > _WALK_GUARD and not _walk_guard_warned:
        _walk_guard_warned = True
        logger.warning(
            "dev-pipeline create-gate: large skills root (%d SKILL.md dirs > guard %d) at %s — "
            "walk completed in full; guard is diagnostic only, never truncated",
            seen_skill_md, _WALK_GUARD, root)
    return fm_matches


def _root_is_excluded(root: str) -> bool:
    """The runtime exclusion check applied to a CONFIGURED ROOT's own full path.

    ``agent.skill_utils.is_excluded_skill_path`` checks EVERY path component;
    applying it to the root itself means a configured root like
    ``/configured/node_modules/skills`` is skipped ENTIRELY: the runtime
    scanner excludes every SKILL.md under it, so names "existing" there must
    stay gated (the gate reporting exists there would let a create pass
    without the flag while the runtime creates it FRESH — a bypass). Fallback
    when the runtime import is unavailable: the mirrored full-path rule over
    the same exclusion sets (logged at debug: the gate is then running on its
    own mirrored signature, so runtime signature drift stays visible).
    """
    try:
        from agent.skill_utils import is_excluded_skill_path

        return bool(is_excluded_skill_path(root))
    except Exception:
        logger.debug(
            "dev-pipeline create-gate: agent.skill_utils.is_excluded_skill_path "
            "unavailable for root %s; falling back to the mirrored full-path rule",
            root, exc_info=True)
        return _root_is_excluded_fallback(root)


def _root_is_excluded_fallback(root: str) -> bool:
    """Mirror of ``is_excluded_skill_path`` over the fallback exclusion sets:
    every component of the path against the excluded dir names, plus the
    support-dir rule (a support-dir ancestor that has a SKILL.md directly
    above). Path-generic: used for a configured ROOT's own path and for each
    DISCOVERED SKILL.md's full path. The SKILL.md-above probe is
    ``os.path.exists`` (runtime ``.exists()`` on the Path): a DIRECTORY (or
    resolvable symlink) named SKILL.md counts there exactly as it does in the
    runtime predicate — not ``isfile``."""
    parts = Path(root).parts
    if any(part in _EXCLUDED_SKILL_DIRS_FALLBACK for part in parts):
        return True
    for idx, part in enumerate(parts[:-1]):
        if idx > 0 and part in _SKILL_SUPPORT_DIRS_FALLBACK and os.path.exists(
                os.path.join(*parts[:idx], "SKILL.md")):
            return True
    return False


def _file_is_excluded(skill_md: str) -> bool:
    """The runtime exclusion check applied to a DISCOVERED SKILL.md's full path.

    ``tools/skill_manager_tool.py`` ``_iter_skill_dirs`` filters EVERY
    ``root.rglob('SKILL.md')`` yield through
    ``agent.skill_utils.is_excluded_skill_path`` on the FULL path — that
    file-level check is the AUTHORITATIVE claimant filter and this helper
    applies it before a discovered SKILL.md may count as a claimant (a
    directory-name match or a frontmatter holder). The walker's
    directory-name pruning is behaviorally equivalent for ORDINARY trees, but
    it misses a top-level ``SKILL.md`` that is a DIRECTORY (or a symlink to
    one): ``os.walk`` classifies it into ``dirnames`` (never ``filenames``),
    so ``has_skill_md`` stays False and the walker descends into a
    ``references/`` tree under it which the runtime's full-path check excludes
    entirely — the walker would count e.g. ``<skill>/references/nested`` as a
    'nested' skill dir while the runtime creates 'nested' FRESH (round-6 fix
    #1). Fallback when the runtime import is unavailable: the mirrored
    full-path rule (same function the root check mirrors; the fallback itself
    logs the mirrored-rule switch at debug).
    """
    try:
        from agent.skill_utils import is_excluded_skill_path

        return bool(is_excluded_skill_path(skill_md))
    except Exception:
        logger.debug(
            "dev-pipeline create-gate: agent.skill_utils.is_excluded_skill_path "
            "unavailable for %s; falling back to the mirrored full-path rule",
            skill_md, exc_info=True)
        return _root_is_excluded_fallback(skill_md)


def _skill_dir_exists(name: str, category=None) -> bool:
    """True iff the target already exists in the runtime's create-dedup scope.

    Exact mirror of the runtime ``_create_skill`` dedup check — ``_find_skill(name)``
    with NO category argument — over the ACTIVE profile's roots only, in the
    runtime's own SEQUENCE: (1) every root's DIRECTORY-NAME scan first (a dir
    with SKILL.md at any depth whose name equals the target — the runtime
    returns on the first hit); (2) ONLY when that entire scan has failed, the
    frontmatter pass (exactly ONE distinct frontmatter ``name:`` holder,
    deduped by the resolved SKILL.md FILE). Multiple frontmatter
    claimants are ambiguous: the runtime refuses to guess and returns not-found
    (its create proceeds fresh), so the gate must gate such a name. The
    ``category`` parameter is accepted but inert (the runtime only ever uses it
    for its own validation and the mkdir path). A configured root whose own
    path carries an excluded component is skipped entirely
    (``_root_is_excluded``), and every DISCOVERED SKILL.md path is re-checked
    at FILE level by the runtime exclusion predicate before counting as a
    claimant (``_file_is_excluded``) AND must actually EXIST (a dangling
    ``SKILL.md`` symlink appears in ``os.walk`` filenames but ``Path.rglob``
    does not yield it on runtimes where glob requires existence — counting it
    would pass a name the runtime creates fresh). Symlinked dirs are not followed
    (runtime-walker parity); excluded dirs are not scanned. On walk failure
    (an unreadable directory) ``os.walk`` raises NOTHING and silently skips —
    the root simply contributes nothing, so its names resolve as NEW and the
    gate BLOCKS: the fail-safe effect is a block, never a pass.
    (Round-6: this lookup is consulted ONLY for single-op calls — a batch
    with more than one well-formed entry, or any batch carrying a mutating
    op, skips it entirely: every well-formed create is gated pending.)
    """
    if _registered_plugin_skill(name):
        return True
    if not _path_safe(name):
        return False  # path-like/traversal names can never be real skill dirs
    for root in _skill_roots():
        if not os.path.isdir(root):
            continue
        if _root_is_excluded(root):
            continue  # the runtime scanner excludes this whole root: nothing there exists
        if _walk_find_dir(root, name):
            return True
    fm_hits: set[str] = set()
    for root in _skill_roots():
        if not os.path.isdir(root) or _root_is_excluded(root):
            continue
        fm_hits |= _walk_find_frontmatter(root, name)
    if len(fm_hits) == 1:
        return True  # unique frontmatter-name holder: the runtime's last-resort match
    if len(fm_hits) > 1:
        logger.warning(
            "dev-pipeline create-gate: display name %r is ambiguous (%d skills claim it) — "
            "runtime refuses to guess; directory names still resolve", name, len(fm_hits))
    return False


def _creates_and_mutation(ops, default_name) -> tuple[list, bool]:
    """(creates, mutating) from ONE flat operations list.

    A create with no name of its own inherits the batch default. ``mutating``
    is True when ANY entry is not a create (patch/edit/delete/write_file/
    remove_file, an unknown action, or an unrecognized entry): the runtime
    runs batch ops in order, so such an op can alter or delete the very
    knowledge the gate used to bless a later create's existence — especially a
    frontmatter ``name:`` claim, which a mid-batch edit can remove — which is
    why a mutating call (even with its single create) gets NO pre-batch
    existence lookup at all (round-6, Opus N2).
    """
    creates: list[tuple] = []
    mutating = False
    for op in ops:
        if isinstance(op, dict) and op.get("action") == "create":
            creates.append((op.get("name") or default_name, op.get("category")))
        elif op is not None:
            mutating = True
    return creates, mutating


def _flat_creates(args: dict) -> list[tuple]:
    """The flat shape's create target, if any (gated iff its category is gated)."""
    if args.get("action") == "create":
        return [(args.get("name"), args.get("category"))]
    return []


_MAX_OPS_NESTING = 5


def _extract_creates(args, _depth: int = 0):
    """(creates, mutating) — every (name, category) create target a call applies,
    plus whether the call carries ANY non-create (mutating) op.

    Covers the flat shape and the batch ``operations`` shape (including the
    batch top-level ``name`` default for nameless ops). ``mutating`` drives
    the ROUND-6 multi-entry rule in ``_decide``: a call with more than one
    well-formed entry — several creates, or one create plus any mutating op —
    gets NO pre-batch existence lookup at all (the runtime runs batch ops in
    order, so pre-batch directory state cannot be trusted); only single-op
    calls still consult the existence oracle.

    Truthiness rules, in
    the order the runtime decides them:

    - FALSY ``operations`` (absent, '', 'null'/''/0/False/None after JSON parse,
      ' ', {}, []) → the FLAT fields are extracted and GATED. Stricter than
      ``skill_manage`` (the runtime routes anything ``not None`` into
      ``_skill_manage_batch``, which tool-errors ''/{} but the truthiness of
      the batch's list check would also stop the batch there) — never a
      pass-through: a block of a payload the runtime rejects anyway costs
      nothing; passing one would leave a flat create ungated.
    - Truthy LIST → every create entry is examined (a benign leading entry
      cannot smuggle a trailing new create).
    - Truthy DICT, whether dict-structured or JSON-string-wrapped → examined
      by the SAME recursion (identical behavior for both forms); the CALL's
      own flat create is ALWAYS carried along with whatever the nested dict
      yields (a nested dict must not swallow a flat create the payload also
      carries).
    - Any other truthy shape (scalar like 123, or a string that fails JSON
      parsing) → an unknown shape: the FLAT create is still gated instead of
      passed. The runtime rejects these payloads, so gating their flat create
      only blocks something that failed anyway — and if the runtime's
      truthiness test ever ran the flat path, the gate holds.
    - Pathological nesting (past ``_MAX_OPS_NESTING``) → the flat create is
      gated (see unknown shapes above).
    """
    if not isinstance(args, dict):
        return [], False
    return _scan_ops_shapes(args, args, _depth)


def _scan_ops_shapes(args: dict, top_args: dict, depth: int):
    """(creates, mutating) for one nesting level of the ``operations`` shape.

    ``top_args`` is the CALL's own argument dict: when this (or a nested)
    level turns out UNKNOWN or unparseable, the flat create of the CALL is
    gated — a nested shape that says nothing still must not leave the call's
    own flat create ungated.
    """
    ops = args.get("operations")
    if ops:
        if isinstance(ops, str):
            try:
                parsed = json.loads(ops)
            except (ValueError, TypeError):
                # Unparseable string: an unknown shape — still gate the flat
                # create rather than pass. At depth 0 this IS the return;
                # DEEPER, the caller (the dict branch below) already carries
                # the call's flat create too — emitting it twice here would
                # make one well-formed create look like two entries (two
                # identical pendings flip the round-6 multi-entry rule), so a
                # nested level emits NOTHING and lets the caller carry it.
                return (_flat_creates(top_args), False) if not depth else ([], False)
            return _ops_shape_creates(parsed, top_args, depth)
        if isinstance(ops, list):
            return _creates_and_mutation(ops, args.get("name"))
        if isinstance(ops, dict):
            # Dict-structured operations: same recursion the JSON-string
            # wrapper takes (wrap parity). The CALL's own flat create joins
            # ONLY at depth 0 (the outermost branch owns it): at depth > 0 the
            # caller already carries it — adding it again would turn one
            # well-formed create into N+1 pendings (the N-level nesting bug
            # the round-7 suite caught).
            if depth >= _MAX_OPS_NESTING:
                return ([], False)  # caller carries the call's flat create
            nested_creates, nested_mutating = _scan_ops_shapes(ops, top_args, depth + 1)
            return nested_creates + (_flat_creates(top_args) if not depth else ([])), nested_mutating
        # Any other truthy shape (scalar): unknown — gate the flat create.
        return (_flat_creates(top_args), False) if not depth else ([], False)
    # Falsy or absent operations: fall back to the flat fields (still gated).
    return _flat_creates(args), False


def _ops_shape_creates(parsed, top_args: dict, depth: int):
    """(creates, mutating) from a JSON-parsed ``operations`` STRING value — same rules as the raw dict."""
    if isinstance(parsed, list):
        if parsed:
            return _creates_and_mutation(parsed, top_args.get("name"))
        # Empty batch string: the runtime tool-errors the dict-shaped
        # operations wrapper anyway - nothing can be created, so nothing to
        # gate. At depth > 0 the caller already carries the flat create.
        return ([], False) if depth else (_flat_creates(top_args), False)
    if isinstance(parsed, dict):
        if depth >= _MAX_OPS_NESTING:
            # Depth limit: the runtime tool-errors dict-shaped operations
            # regardless of nesting - return nothing to avoid duplicating the
            # caller's flat create at depth > 0.
            return ([], False) if depth else (_flat_creates(top_args), False)
        nested_creates, nested_mutating = _scan_ops_shapes(parsed, top_args, depth + 1)
        # Same depth-0-only flat-carry rule as the raw dict branch.
        return nested_creates + (_flat_creates(top_args) if not depth else ([])), nested_mutating
    # Truthy scalar (unknown shape) and falsy scalar ('null'/false/0) alike:
    # fall back to the CALL's flat fields (still gated) — but only at the top
    # level; at depth > 0 the caller carries the flat create (runtime
    # tool-errors dict-shaped operations either way, nothing can be created).
    return (_flat_creates(top_args), False) if not depth else ([], False)


def _block(message: str) -> dict:
    return {"action": "block", "message": message}


def _flag_directive() -> str:
    """Block message with the RESOLVED single-use allow flag path interpolated.

    The path is resolved at DECISION time (not import time): under an active
    profile the runtime home is ``<root>/profile_name``, and a hardcoded
    ``~/.hermes/...`` path would instruct a profile user to create a flag the
    hook would never look for.
    """
    return (
        "New skill blocked - the dev-pipeline create-gate reserves new "
        "SOFTWARE-DEVELOPMENT skills for explicit user consent. Ask the user to "
        "create the single-use allow flag "
        f"(echo ok > {_flag_path()}), then retry once; the hook consumes the "
        "flag after honoring one create. Prefer updating an existing skill instead."
    )


def _decide(tool_name: str, args):
    if tool_name != "skill_manage":
        # Fast path: non-skill_manage work passes before any code that can raise.
        return None
    creates, mutating = _extract_creates(args if isinstance(args, dict) else {})
    # NO blanket try/except from here on: errors on a create decision propagate
    # and the runtime fails closed (plugins_dispatch.py invoke_hook).
    classified = []     # (name, category) well-formed, non-registered, GATED
                        # (software-development) create candidates
    malformed = None
    total_creates = 0   # identifiable creates of ANY category: every one may add a claimant mid-batch
    for name, category in creates:
        if not isinstance(name, str) or not name:
            continue  # unidentifiable target: no decision (the runtime rejects it)
        if _registered_plugin_skill(name):
            continue  # a REGISTERED qualified name is a known skill: not a new-skill create
        gated = _is_gated_category(category)
        if not _name_well_formed(name) or not _path_safe(name):
            if not gated:
                # Ungated malformed NAME: the runtime's own validation rejects
                # it (mirror regex) — no fresh create possible. No gate block.
                continue
            # Malformed/path-like GATED create target: BLOCK with or without a
            # flag; the flag stays intact. (Reachable only for names that are
            # neither well-formed nor registered-qualified — e.g. bare stage
            # names are well-formed and gated further below; a create of an
            # uppercase or traversal name is refused by the runtime's own
            # validation anyway.)
            malformed = name
            break
        total_creates += 1
        if not gated:
            # v0.1.7 scoping: ONLY software-development creates are gated.
            # Every other category (and an absent/None/empty one) is SKIPPED
            # in the blocking pipeline exactly like registered-name creates:
            # never blocks, never consumes the flag. BUT it still counts in
            # total_creates — a mid-batch ungated create CAN add a frontmatter
            # claimant that makes the gated create ambiguous at runtime
            # (round-8 Codex/Opus N1), so it disqualifies the existence
            # short-circuit below without joining the flag logic.
            continue
        classified.append((name, category))
    if malformed is not None:
        return _block(
            f"Create target '{malformed}' is blocked: it is not a well-formed skill name "
            "(runtime rule: ^[a-z0-9][a-z0-9._-]*$). Fix the name, or update an "
            "existing skill instead.")
    pending = classified
    if not pending:
        return None
    # Round-6 (Opus N1+N2): a batch with MORE THAN ONE well-formed entry (>=2
    # well-formed creates, or exactly one create plus any mutating op) gets NO
    # existence short-circuit: the runtime runs its batch ops in order, so any
    # pre-batch existence answer can be made stale mid-batch (a delete removes
    # the holder; a create can add a frontmatter claimant that makes an
    # existing display name ambiguous, which the runtime resolves as fresh).
    # Every well-formed such create therefore stays pending:
    #   - a create that already exists tool-errors at runtime with
    #     ``already exists`` and the whole batch rolls back — the gate
    #     blocking it (even with a flag) is the ACCEPTED over-gating;
    #   - a create whose name is genuinely fresh at execution time is gated
    #     as it must be.
    # Round-6 (Opus N1+N2) + round-8 (Codex/Opus): a call gets the existence
    # short-circuit ONLY when NOTHING can mutate a claim mid-run: exactly one
    # identifiable create of ANY category, no mutating op, no other creates.
    # An ungated create still disqualifies it (round-8 N1) — a mid-batch
    # ungated create can add a frontmatter claimant that makes the gated
    # create ambiguous at runtime, which the runtime then creates fresh.
    multi_entry = len(pending) > 1 or (len(pending) == 1 and (mutating or total_creates > 1))
    if not multi_entry:
        # Single-op call (flat create, or exactly one well-formed create entry
        # with no other op): full runtime-parity existence check, including
        # frontmatter parity (nothing can mutate a claim mid-batch — there is
        # no batch to run out of order).
        if _skill_dir_exists(pending[0][0], pending[0][1]):
            return None  # targets an existing/known skill: not a new-skill create
    if len(pending) > 1:
        # One flag authorizes exactly ONE create: a batch with several new
        # software-development creates is refused even with the flag present
        # (flag stays intact).
        return _block(
            f"Batch contains {len(pending)} new SOFTWARE-DEVELOPMENT skill creates "
            f"({', '.join(n for n, _ in pending)}); one allow flag authorizes exactly one "
            "create. Ask the user to authorize genuinely new software-development skills "
            "one at a time, or update existing skills instead.")
    name, _category = pending[0]
    if not os.path.isfile(_flag_path()):
        return _block(_flag_directive())
    # Consume the flag BEFORE allowing the create; never pass with the flag intact.
    try:
        os.unlink(_flag_path())
    except OSError as exc:
        return _block(
            _flag_directive()
            + f" (Note: the allow flag could not be removed: {exc} — it is left in place.)")
    logger.info(
        "dev-pipeline create-gate: allow flag consumed; one create=%r honored", name)
    return None


def _on_pre_tool_call(tool_name: str = "", args=None, **kwargs):
    """pre_tool_call policy hook: block directive dict, or ``None`` to pass.

    Raises nothing on the pass-through path (non-``skill_manage``). On a create
    decision, internal errors PROPAGATE on purpose: the runtime fails closed on
    a raised policy hook (hermes_cli/plugins_dispatch.py, ``invoke_hook``), so
    an undecided gate blocks instead of passing a create.
    """
    return _decide(tool_name, args)


def register(ctx):
    """Wire the bundled stage skills and the pre_tool_call create-gate hook."""
    # register_skill() resolves the path against the PROCESS CWD, not the plugin
    # dir (hermes_cli/plugins_content.py) — build absolute paths from __file__ so
    # registration works from any cwd, including the gateway. The loader
    # registers each skill under its qualified name '<namespace>:<name>'.
    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    for skill_name in _BUNDLED_SKILLS:
        try:
            ctx.register_skill(
                skill_name, os.path.join(plugin_dir, "skills", skill_name, "SKILL.md"))
        except Exception as exc:
            logger.warning("dev-pipeline: register_skill(%s) failed: %s", skill_name, exc)
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    # Keep legacy skill-only contexts usable; modern Hermes exposes register_tool.
    if callable(getattr(ctx, "register_tool", None)):
        from .engineering import register_engineering
        register_engineering(ctx)
    logger.info("dev-pipeline plugin registered (pre_tool_call skill-create gate, %d bundled skills)", len(_BUNDLED_SKILLS))
