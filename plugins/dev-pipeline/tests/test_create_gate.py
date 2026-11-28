"""Full smoke matrix for the dev-pipeline pre_tool_call skill-create gate (v0.1.7).

Importable pytest module: every ``test_*`` function runs under
``pytest --import-mode=importlib`` AND via the direct runner
(``python3 tests/test_create_gate.py``), which collects the same functions.

Isolation: every case that writes anything runs inside a fixture HERMES_HOME
(temp dir honoring TMPDIR — NO ``dir=`` pin). The live ``~/.hermes/skills``
tree is READ-ONLY to this suite; the live ``.allow-create`` flag is never
renamed, moved, or consumed — live-root probing happens only when no live flag
exists at the RESOLVED flag path (and the probe SKIPS when one does), and
skips with a reason when the live skills tree is unreadable.

v0.1.2 matrix additions (round-3): active-profile-only existence scope
(cross-profile block), recursive directory-name find at any depth, registered
prefixed plugin-skill names vs gated bare stage names, operations as a JSON
string, empty-operations fallback to flat fields.

v0.1.3 matrix additions (round-4): walker-only existence oracle (direct
two-level candidate lookup DELETED — no excluded-dir-nesting bypass), runtime
frontmatter-name parity (unique holder exists; ambiguous holder gated), the
skipped-dir differential: a symlinked dir name resolves in NEITHER the gate
nor the runtime walker (neither follows dir symlinks), falsy/unknown
operations shapes still gate the flat create, the resolved flag path is
carried in the block message, a real Cyrillic homoglyph case asserts the
malformed-name token, and the direct runner exits cleanly on skips.

v0.1.4 matrix additions (round-5): a configured ROOT carrying an excluded
component is skipped ENTIRELY (names under it stay gated — runtime parity),
frontmatter claimants deduped by the RESOLVED SKILL.md file (two dirs
symlinking one SKILL.md = one holder), two-pass lookup sequence (a
frontmatter-reading failure cannot block a dir-name-matching create),
mutating batches disarm frontmatter-only existence, and dict-structured
operations never drop the CALL's own flat create.

v0.1.5 matrix additions (round-6): every DISCOVERED SKILL.md path is
re-checked at FILE level by the runtime exclusion predicate before it may
count as a claimant (a root whose top-level SKILL.md is a DIRECTORY escaped
the walker's filename-based has_skill_md pruning — os.walk files it into
dirnames — while the runtime's rglob + is_excluded_skill_path full-path check
excludes the support-dir tree under it: an external root like a skill's own
dir with references/nested/SKILL.md passed flag-free while the runtime
created 'nested' fresh), multi-entry batches (more than one well-formed
entry: several creates, or one create plus any mutating op) get NO existence
short-circuit at all — every well-formed create gated, an already-existing
name's runtime ``already exists`` rejection accepted as over-gating
(Opus N1: a mid-batch create can add a frontmatter claimant making an
existing display name ambiguous; Opus N2: [delete X, create X] recreates
fresh mid-batch) — while single-op calls keep the full runtime-parity
existence check, and a dict-operations payload whose nested level is
unparseable no longer emits the call's flat create twice (two identical
pendings would flip the multi-entry rule).

v0.1.7 matrix additions (round-8): the create-gate is SCOPED to the
software-development category — a create whose category normalizes
(strip + lower) to 'software-development' keeps every gated behavior
(existence parity, multi-entry batch gating, one-flag-one-create,
malformed-name block, flag consume-before-allow), while EVERY OTHER category
string (case/whitespace variants that do not normalize to it), any non-string
category, and an absent/empty category passes UNGATED: it contributes
nothing, never blocks (a malformed NAME on such a create is the runtime's
business, never a gate block), never counts toward the multi-entry rule, and
never consumes the flag. New cases: a non-dev category passes flag-free and
consumes nothing, a no-category create passes, a mixed batch (gated +
ungated) gates only the gated create (one flag still authorizes exactly it),
category normalization ('Software-Development ', 'SOFTWARE-DEVELOPMENT'),
the flag is NOT consumed on ungated passes, and the block message now says
the gate reserves new SOFTWARE-DEVELOPMENT skills.
"""

import contextlib
import errno
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent

# pytest is OPTIONAL: importable here does not mean RUNNING under pytest (the
# direct runner runs WITH a system pytest on sys.path). _skip() gates on
# PYTEST_CURRENT_TEST so it raises real pytest.skip only inside a pytest item;
# everywhere else it raises the module-local _Skipped (an Exception) the
# direct runner catches cleanly.
try:
    import pytest as _pytest
except ImportError:  # direct runner without pytest installed
    _pytest = None


class _Skipped(Exception):
    """Direct-runner-compatible skip marker (under pytest, pytest.skip is used)."""


def _skip(reason: str) -> None:
    if _pytest is not None and os.environ.get("PYTEST_CURRENT_TEST"):
        _pytest.skip(reason)
        return
    raise _Skipped(reason)


_SKIPPED_TYPES: tuple = (_Skipped, _pytest.skip.Exception) if _pytest else (_Skipped,)

NEW_BLOCK_MSG_TOKENS = (
    "New skill blocked", "Ask the user to create the single-use allow flag",
    "SOFTWARE-DEVELOPMENT")
MALFORMED_MSG_TOKEN = "not a well-formed skill name"
BATCH_MSG_TOKEN = "one allow flag authorizes exactly one create"
UNLINK_FAIL_TOKEN = "could not be removed"

_PLUGIN = None


def _plugin():
    """Load the plugin module once (plain-module hermes test contract)."""
    global _PLUGIN
    if _PLUGIN is None:
        init_path = PLUGIN_DIR / "__init__.py"
        spec = importlib.util.spec_from_file_location("dev_pipeline_under_test", init_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PLUGIN = mod
    return _PLUGIN


def _call(args, tool_name="skill_manage", **extra):
    kwargs = {"session_id": "sess-1", "tool_call_id": "call-1", "turn_id": "t:ta:abc", "task_id": "task-1"}
    kwargs.update(extra)
    return _plugin()._on_pre_tool_call(tool_name=tool_name, args=args, **kwargs)


def _is_block(result):
    return isinstance(result, dict) and result.get("action") == "block" and isinstance(result.get("message"), str)


@contextlib.contextmanager
def fixture_home():
    """Isolated HERMES_HOME with a real existing skill (category 'test')."""
    # NO dir= pin (Muse round-3 finding #1): honor TMPDIR — /root was read-only
    # in the reviewer sandbox, the platform temp dir is always writable.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "hermes-home")
        skills = os.path.join(home, "skills")
        existing = os.path.join(skills, "test", "existing-skill")
        os.makedirs(existing)
        with open(os.path.join(existing, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("ok\n")
        # A flat (uncategorized) existing skill too, so creates without a
        # category resolve as existing.
        flat = os.path.join(skills, "existing-skill")
        os.makedirs(flat)
        with open(os.path.join(flat, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("ok\n")
        prev = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = home
        try:
            yield home, skills
        finally:
            if prev is None:
                os.environ.pop("HERMES_HOME", None)
            else:
                os.environ["HERMES_HOME"] = prev


def _set_flag(home):
    flag = os.path.join(home, "skills", ".allow-create")
    with open(flag, "w", encoding="utf-8", newline="\n") as f:
        f.write("ok\n")
    return flag


def _flag_of(home):
    return os.path.join(home, "skills", ".allow-create")


# --- 1. Flat shape -------------------------------------------------------------------


def test_flat_existing_create_passes():
    """v0.1.7: the existing-name pass-through must still hold for a GATED
    create (runtime-parity existence check); non-gated categories and
    category-less creates pass ungated without consulting the walker."""
    with fixture_home() as (home, _skills):
        # Gated category on an existing name: the walker resolves it -> pass.
        assert _call({"action": "create", "name": "existing-skill",
                      "category": "software-development"}) is None
        # Non-gated category string: passes ungated (consumes nothing).
        assert _call({"action": "create", "name": "existing-skill", "category": "test"}) is None
        # No category at all: passes ungated (consumes nothing).
        assert _call({"action": "create", "name": "existing-skill"}) is None


def test_flat_new_create_blocks_without_flag():
    """v0.1.7: the gated (software-development) category still blocks; the
    SAME name with NO category passes right through, ungated."""
    with fixture_home():
        r = _call({"action": "create", "name": "brand-new-skill",
                   "category": "software-development"})
        assert _is_block(r), r
        for tok in NEW_BLOCK_MSG_TOKENS:
            assert tok in r["message"]
        assert _call({"action": "create", "name": "brand-new-skill"}) is None, \
            "a category-less create must pass ungated (v0.1.7 scoping)"


def test_flag_single_allow_consumes_flag():
    with fixture_home() as (home, _skills):
        flag = _set_flag(home)
        r = _call({"action": "create", "name": "brand-new-skill",
                   "category": "software-development"})
        assert r is None, r
        assert not os.path.exists(flag), "flag must be consumed (unlinked) when the create is honored"


def test_malformed_name_with_flag_blocks_flag_intact():
    """v0.1.7 edge (b): a malformed NAME on a GATED create still blocks with
    the flag intact; the SAME malformed name on an UNGATED create is NOT the
    gate's business (the runtime rejects it anyway) — the gate passes."""
    with fixture_home() as (home, _skills):
        flag = _set_flag(home)
        r = _call({"action": "create", "name": "../traversal-evil",
                   "category": "software-development"})
        assert _is_block(r), r
        assert MALFORMED_MSG_TOKEN in r["message"]
        assert os.path.exists(flag), "flag must NOT be consumed on a malformed target"
        # Ungated malformed create: pass, flag untouched.
        assert _call({"action": "create", "name": "../traversal-evil", "category": "test"}) is None
        assert os.path.exists(flag), "an ungated malformed create consumes nothing"


def test_uppercase_and_homoglyph_names_block():
    with fixture_home():
        r = _call({"action": "create", "name": "MySkill",
                   "category": "software-development"})
        assert _is_block(r), r
        r = _call({"action": "create", "name": "my skill",
                   "category": "software-development"})
        assert _is_block(r), r
        # REAL homoglyph (round-4 fix #5): Cyrillic 'ѕ' (U+0455) in place of the
        # Latin 's' — the ASCII-only name rule rejects it, and the block must
        # carry the malformed-NAME token (not the flag directive: a flag would
        # not launder a malformed name).
        r = _call({"action": "create", "name": "ѕkill",
                   "category": "software-development"})
        assert _is_block(r), r
        assert MALFORMED_MSG_TOKEN in r["message"], r["message"]
        assert "single-use allow flag" not in r["message"], r["message"]


def test_dotted_name_allowed_per_runtime_rule():
    with fixture_home() as (home, _skills):
        # No flag: still blocked (a dotted name is a genuinely new skill).
        assert _is_block(_call({"action": "create", "name": "my.skill-v2",
                                "category": "software-development"}))
        # With flag: well-formed per runtime rule -> passes and consumes the flag.
        flag = _set_flag(home)
        assert _call({"action": "create", "name": "my.skill-v2",
                      "category": "software-development"}) is None
        assert not os.path.exists(flag)


# --- 2. Fast paths (must pass with no risky code) -------------------------------------


def test_plain_tool_unparseable_args_pass():
    assert _call({"path": "/x"}, tool_name="read_file") is None
    assert _call(None, tool_name="read_file") is None
    assert _call({"weird": object()}, tool_name="read_file") is None


def test_skill_manage_non_create_passes():
    with fixture_home():
        assert _call({"action": "patch", "name": "brand-new-skill", "old_string": "a", "new_string": "b"}) is None
        assert _call({"action": "write_file", "name": "brand-new-skill", "file_path": "x", "file_content": "y"}) is None
        assert _call({"action": "delete", "name": "anything"}) is None


def test_unidentifiable_create_passes_no_decision():
    with fixture_home():
        assert _call({"action": "create"}) is None
        assert _call({"action": "create", "name": 12345}) is None
        assert _call(None) is None
        assert _call({}) is None


# --- 3. Batch / operations shape (R1, R4) ----------------------------------------------


def test_batch_ops_trailing_new_create_blocks():
    with fixture_home() as (home, _skills):
        r = _call({"operations": [{"action": "patch", "name": "existing-skill", "old_string": "a", "new_string": "b"},
                                  {"action": "create", "name": "brand-new-skill",
                                   "category": "software-development"}]})
        assert _is_block(r), r


def test_benign_leading_create_cannot_smuggle_trailing_new_create():
    with fixture_home() as (home, _skills):
        r = _call({"operations": [{"action": "create", "name": "existing-skill", "content": "x",
                                   "category": "software-development"},
                                  {"action": "create", "name": "brand-new-skill", "content": "y",
                                   "category": "software-development"}]})
        assert _is_block(r), "a benign first entry must not smuggle the trailing new create"


def test_multi_entry_batch_gates_existing_name_too_even_with_flag():
    """Round-6 (Opus N1+N2): a batch with MORE THAN ONE well-formed entry gets
    NO existence short-circuit — the runtime runs its batch ops in order, so
    pre-batch directory state cannot be trusted; every well-formed create goes
    to pending. An already-existing target tool-errors at runtime ('already
    exists') and the whole batch rolls back — the gate blocking that batch,
    EVEN WITH the flag, is the accepted over-gating. Single-op calls (and
    single well-formed create-only batches, below) keep the full parity
    existence check unchanged."""
    with fixture_home() as (home, _skills):
        # [create existing, create new]: BOTH well-formed -> both pending ->
        # refused even with a flag (flag intact; one flag = one create does
        # not change: the refusal is the multi-entry no-short-circuit rule).
        flag = _set_flag(home)
        r = _call({"operations": [{"action": "create", "name": "existing-skill", "content": "x",
                                   "category": "software-development"},
                                  {"action": "create", "name": "brand-new-skill", "content": "y",
                                   "category": "software-development"}]})
        assert _is_block(r), r
        assert BATCH_MSG_TOKEN in r["message"]
        assert os.path.exists(flag), "multi-entry batch: flag must stay intact"
        # No-flag variant of the same shape blocks too.
        assert _is_block(_call({"operations": [
            {"action": "create", "name": "existing-skill", "content": "x",
             "category": "software-development"},
            {"action": "create", "name": "brand-new-skill", "content": "y",
             "category": "software-development"}]}))
        # REGRESSION (single-op parity unchanged): ONE well-formed create entry
        # of an existing name still passes (full existence check) with no flag.
        assert _call({"operations": [{"action": "create", "name": "existing-skill",
                                      "content": "x", "category": "software-development"}]}) is None
        # ...and a NEW single create entry with a flag still passes + consumes.
        flag = _set_flag(home)
        assert _call({"operations": [{"action": "create", "name": "brand-new-solo",
                                      "content": "x", "category": "software-development"}]}) is None
        assert not os.path.exists(flag)


def test_batch_double_new_create_under_flag_blocks_flag_intact():
    with fixture_home() as (home, _skills):
        flag = _set_flag(home)
        r = _call({"operations": [{"action": "create", "name": "brand-new-a", "content": "x",
                                   "category": "software-development"},
                                  {"action": "create", "name": "brand-new-b", "content": "y",
                                   "category": "software-development"}]})
        assert _is_block(r), r
        assert BATCH_MSG_TOKEN in r["message"]
        assert os.path.exists(flag), "double new create must NOT consume the flag"


def test_batch_double_new_create_no_flag_blocks():
    with fixture_home():
        r = _call({"operations": [{"action": "create", "name": "brand-new-a", "content": "x",
                                   "category": "software-development"},
                                  {"action": "create", "name": "brand-new-b", "content": "y",
                                   "category": "software-development"}]})
        assert _is_block(r), r


def test_batch_default_name_applies_to_nameless_op():
    with fixture_home():
        r = _call({"name": "brand-new-skill", "operations": [
            {"action": "create", "content": "x", "category": "software-development"}]})
        assert _is_block(r), "nameless batch create must inherit the top-level default name"


def test_batch_ops_overrides_flat_fields():
    with fixture_home() as (home, _skills):
        # operations present overrides flat action/name: the flat new name ignored.
        assert _call({"action": "create", "name": "brand-new-flat", "operations": [
            {"action": "create", "name": "existing-skill", "content": "x",
             "category": "software-development"}]}) is None
        # ...and the ops' new create is a genuine single new create: the flag
        # authorizes it (the flat name is ignored — operations overrides flat).
        flag = _set_flag(home)
        r = _call({"action": "create", "name": "existing-skill", "operations": [
            {"action": "create", "name": "brand-new-via-ops", "content": "x",
             "category": "software-development"}]})
        assert r is None, "flat args cannot veto ops overrides; one pending create + flag passes"
        assert not os.path.exists(flag), "the flag was consumed honoring the ops create"


# --- 3b. Defensive operations shapes (round-3 fix #4) -----------------------------------


def test_operations_json_string_new_create_is_gated():
    """operations arriving as a JSON STRING is parsed and examined like a list."""
    with fixture_home() as (home, _skills):
        payload = json.dumps([
            {"action": "patch", "name": "existing-skill", "old_string": "a", "new_string": "b"},
            {"action": "create", "name": "brand-new-via-json",
             "category": "software-development"},
        ])
        r = _call({"action": "create", "name": "existing-skill", "operations": payload})
        assert _is_block(r), "a JSON-string operations batch must be gated, not smuggled"
        # With the flag: the single new create inside the string payload passes.
        flag = _set_flag(home)
        assert _call({"action": "create", "name": "existing-skill", "operations": payload}) is None
        assert not os.path.exists(flag)
        # A JSON OBJECT wrapper that itself carries operations is examined too.
        wrapped = json.dumps({"operations": [{"action": "create", "name": "brand-new-wrapped",
                                              "category": "software-development"}]})
        assert _is_block(_call({"operations": wrapped})), "dict-wrapped JSON string must be gated"
        # Unparseable JSON string with NO flat create: nothing to decide -> pass
        # (the runtime tool-errors the payload anyway).
        assert _call({"operations": "{not json"}) is None


def test_operations_unknown_or_unparseable_shape_still_gates_flat_create():
    """Round-4 fix #3: an unknown truthy operations shape (unparseable string,
    truthy scalar, dict-structured anything) must GATE the flat create, never
    silently pass it."""
    with fixture_home() as (home, _skills):
        for ops in ("{not json", 123, {"operations": "junk"}, {"action": "create", "name": "brand-new-inner"},
                    3.14, ("not", "a", "shape"), b"\x00binary"):
            r = _call({"action": "create", "name": "brand-new-unknown",
                       "category": "software-development", "operations": ops})
            assert _is_block(r), (ops, r)
            assert MALFORMED_MSG_TOKEN not in r["message"], (ops, r)
        # ...but the same shapes with an EXISTING flat target still pass (no new create).
        for ops in ("{not json", 123, {"operations": "junk"}, 3.14):
            assert _call({"action": "create", "name": "existing-skill", "operations": ops}) is None, ops
        # Unknown shape with NO flat create at all: pass (nothing to gate).
        assert _call({"action": "patch", "name": "existing-skill", "operations": "{not json"}) is None


def test_operations_dict_is_not_json_string_wrap_agnostic_diff():
    """Round-4 fix #3: DICT-structured operations behave IDENTICALLY to the
    same payload JSON-STRING-WRAPPED (same recursion)."""
    with fixture_home() as (home, _skills):
        dict_shaped = {"operations": [{"action": "create", "name": "brand-new-dict",
                                       "category": "software-development"}]}
        string_shaped = json.dumps(dict_shaped)
        r1 = _call({"operations": dict_shaped})
        r2 = _call({"operations": string_shaped})
        assert _is_block(r1) and _is_block(r2), (r1, r2)
        # With a flag, BOTH forms honor the single new create and consume it.
        flag = _set_flag(home)
        assert _call({"operations": dict_shaped}) is None
        assert not os.path.exists(flag)
        flag = _set_flag(home)
        assert _call({"operations": string_shaped}) is None
        assert not os.path.exists(flag)
        # A dict-structured payload with action/no-operations at the top:
        # the recursion lands on its flat create, gated like the wrapped form.
        flatish = {"action": "create", "name": "brand-new-flatish",
                   "category": "software-development"}
        assert _is_block(_call({"operations": flatish}))
        assert _is_block(_call({"operations": json.dumps(flatish)}))
        # Round-5 fix #5 (Opus 1): a dict-structured (or JSON-string-wrapped
        # dict) operations value must NEVER drop the CALL's own flat create —
        # whatever the nested dict yields, the top flat create is also gated.
        # ('{"foo": 1}' used to drop the flat create entirely and PASS.)
        for inner in ({"foo": 1}, {"operations": []}):
            r = _call({"action": "create", "name": "brand-new-x",
                       "category": "software-development", "operations": inner})
            assert _is_block(r), ("dict-form flat create must survive the recursion", inner, r)
            r = _call({"action": "create", "name": "brand-new-x",
                       "category": "software-development", "operations": json.dumps(inner)})
            assert _is_block(r), ("wrapped-form flat create must survive the recursion", inner, r)
            # The same shapes with an EXISTING flat target still pass (no new
            # create anywhere in the payload).
            assert _call({"action": "create", "name": "existing-skill", "operations": inner}) is None, inner
            assert _call({"action": "create", "name": "existing-skill",
                          "operations": json.dumps(inner)}) is None, inner


def test_operations_falsy_values_fall_back_to_flat_and_stay_gated():
    """Round-4 fix #3: ANY falsy operations value ('', 'null' after parse, ' ',
    {}, 0, False, []) falls back to the flat fields — which are still GATED.
    (Strictly stricter than skill_manage: the runtime routes anything not-None
    to the batch path, which tool-errors non-array shapes.)"""
    with fixture_home() as (home, _skills):
        for ops in ("", " ", {}, 0, False, [], json.dumps(None), json.dumps(False), json.dumps(0)):
            # Flat existing target: pass.
            assert _call({"action": "create", "name": "existing-skill", "operations": ops}) is None, ops
            # Flat NEW target: BLOCK (never ungated).
            assert _is_block(_call({"action": "create", "name": "brand-new-falsy",
                                    "category": "software-development", "operations": ops})), ops
        flag = _set_flag(home)
        r = _call({"action": "create", "name": "brand-new-falsy",
                   "category": "software-development", "operations": ""})
        assert r is None
        assert not os.path.exists(flag), "the flat create under falsy ops consumed the flag"


def test_operations_empty_falls_back_to_flat_fields():
    """An empty (or absent) operations value falls back to the flat fields: the
    flat create is still gated (round-4 rewording of fix #3)."""
    with fixture_home() as (home, _skills):
        # Flat existing target -> pass.
        assert _call({"action": "create", "name": "existing-skill", "operations": []}) is None
        # Flat NEW target with empty operations -> BLOCK.
        assert _is_block(_call({"action": "create", "name": "brand-new-skill",
                                "category": "software-development", "operations": []}))
        # With a flag the flat new create is honored and consumes it.
        flag = _set_flag(home)
        r = _call({"action": "create", "name": "brand-new-skill",
                   "category": "software-development", "operations": []})
        assert r is None
        assert not os.path.exists(flag)
        # Absent operations behaves the same (flat path, gated).
        assert _is_block(_call({"action": "create", "name": "brand-new-skill",
                                "category": "software-development", "operations": None}))


# --- 4. Bundled stage names (R2 / round-3 fix #3) --------------------------------------


def test_all_ten_bare_skill_names_are_gated():
    """Bare stage names are NOT registered skill names — the loader registers the
    QUALIFIED names 'dev-pipeline:<stage>' (hermes_cli/plugins_content.py
    register_skill) — so every bare stage name is a genuinely new skill: gated.
    Pinned to the TEN expected names (six stages + review-lessons + briefs + the v0.6.0 debug
    route + the v0.6.1 repo-context): the test must fail if the bundled set grows or shrinks, not
    silently follow it.
    """
    mod = _plugin()
    assert mod._BUNDLED_SKILLS == (
        "spec", "build", "review-commit", "test-evals", "grill", "orchestrator",
        "review-lessons", "briefs", "debug", "repo-context")
    with fixture_home() as (home, _skills):
        for stage in ("spec", "build", "review-commit", "test-evals", "grill", "orchestrator",
                      "review-lessons", "briefs", "debug", "repo-context"):
            r = _call({"action": "create", "name": stage,
                       "category": "software-development"})
            assert _is_block(r), (stage, r)
        assert not os.path.exists(_flag_of(home)), "a block must never fabricate or consume a flag"
    # With one flag: a bare stage create is honored and consumes the flag.
    with fixture_home() as (home, _skills):
        for stage in ("spec", "orchestrator"):
            flag = _set_flag(home)
            assert _call({"action": "create", "name": stage,
                          "category": "software-development"}) is None, (stage, "flag must honor it")
            assert not os.path.exists(flag), stage


def test_prefixed_plugin_skill_names_pass_without_flag():
    """'dev-pipeline:<stage>' is the REGISTERED qualified name: exists -> pass."""
    mod = _plugin()
    with fixture_home() as (home, _skills):
        for stage in mod._BUNDLED_SKILLS:
            assert _call({"action": "create", "name": f"dev-pipeline:{stage}",
                          "category": "software-development"}) is None, stage
        assert not os.path.exists(_flag_of(home)), "registered names must not need the flag"
        # An UNKNOWN namespace is not this plugin's registered name -> gated.
        r = _call({"action": "create", "name": "other-plugin:spec",
                   "category": "software-development"})
        assert _is_block(r), r


# --- 5. Existence oracle quality (R2) ----------------------------------------------------


def test_symlink_escape_treated_nonexistent():
    with fixture_home() as (tmp_home, skills):
        outside = os.path.join(os.path.dirname(tmp_home), "outside-root", "poison-skill")
        os.makedirs(outside)
        with open(os.path.join(outside, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("ok\n")
        os.symlink(outside, os.path.join(skills, "poison-skill"))
        mod = _plugin()
        r = _call({"action": "create", "name": "poison-skill",
                   "category": "software-development"})
        assert _is_block(r), "symlink escape must count as NONEXISTENT (not an existence oracle spoof)"


def test_symlinked_dir_name_is_nonexistent_in_both_resolvers():
    """Round-4 parity (Opus finding 4): NEITHER resolver follows symlinked dirs.

    The runtime walker is ``root.rglob("SKILL.md")`` and pathlib's rglob does
    not recurse into symlinked directories on the runtime's Python (verified
    against the live runtime in round 4's differential probe); the gate's
    os.walk (followlinks=False) mirrors that. The old v0.1.2 gate said
    'inner-link' EXISTS because the deleted direct lookup realpath-resolved
    through the symlink (gate/runtime divergence). Parity invariant: the
    symlinked dir name is a genuinely NEW skill for BOTH -> BLOCK.
    """
    with fixture_home() as (_tmp_home, skills):
        target = os.path.join(skills, "test", "existing-skill")
        os.symlink(target, os.path.join(skills, "inner-link"))
        r = _call({"action": "create", "name": "inner-link",
                   "category": "software-development"})
        assert _is_block(r), "symlinked dir name must match the runtime walker: NOT exist"


def test_direct_candidate_lookup_deleted_no_excluded_dir_nesting_bypass():
    """Round-4 fix #1 (Codex probe): the direct root/<name> and
    root/<category>/<name> checks bypassed the walker's exclusion rule — a
    create target nested under node_modules (or any excluded dir name)
    answered EXISTS while the runtime scanner excludes it. Walker-only now:
    the category argument is inert (runtime create-dedup is category-free),
    so no category can smuggle the direct candidate back. v0.1.7: the gate
    itself only GATES category 'software-development' — other categories now
    pass ungated (a scoping decision; no excluded-dir walker bypass exists
    either way, since ungated creates never even consult the walker).
    """
    with fixture_home() as (_tmp_home, skills):
        for nesting in ("node_modules", "venv", ".tox"):
            d = os.path.join(skills, nesting, "fresh-skill")
            os.makedirs(d)
            with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write("ok\n")
        # GATED category: the walker must NOT report these nested names as
        # existing regardless of nesting (block, flag directive).
        assert _is_block(_call({"action": "create", "name": "fresh-skill",
                                "category": "software-development"})), \
            "a gated create of a nested name must stay gated"
        # v0.1.7: every non-gated category (and none) now passes ungated and
        # consumes nothing — no flag needed, no walker consulted.
        for category in (None, "node_modules", "venv", ".tox", "test"):
            r = _call({"action": "create", "name": "fresh-skill", "category": category})
            assert r is None, (category, r)


def test_scanner_exclusion_differential_matches_runtime_walker():
    """Round-4 differential (#1): pruning mirrors the runtime scanner exactly.

    A dot dir IN the runtime exclusion set is excluded by BOTH resolvers (its
    nested names stay nonexistent -> genuinely new -> gated); a dot dir NOT in
    the set is scanned by the runtime walker, so the gate must resolve it as
    existing too (differential parity is the invariant, not blanket dot-dir
    skipping).
    """
    with fixture_home() as (_tmp_home, skills):
        excluded = os.path.join(skills, "vendor", ".git", "buried-in-excluded-dir")
        os.makedirs(excluded)
        with open(os.path.join(excluded, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("ok\n")
        assert _is_block(_call({"action": "create", "name": "buried-in-excluded-dir",
                                "category": "software-development"}))
        scanned = os.path.join(skills, ".hidden-but-not-excluded", "name-in-unlisted-dot-dir")
        os.makedirs(scanned)
        with open(os.path.join(scanned, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("ok\n")
        r = _call({"action": "create", "name": "name-in-unlisted-dot-dir",
                   "category": "software-development"})
        assert r is None


def test_frontmatter_name_parity_unique_holder_exists():
    """Round-4 fix #2 (Codex): the runtime's FINAL _find_skill step resolves a
    skill by its SKILL.md frontmatter ``name:``, not just the dir name — a
    create of that display name must count as EXISTING (the runtime create
    would return 'already exists')."""
    with fixture_home() as (_tmp_home, skills):
        d = os.path.join(skills, "fm-owner")
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nname: fm-display-only\ndescription: t\n---\nbody\n")
        # Unique frontmatter holder: the display name exists (no flag needed).
        assert _call({"action": "create", "name": "fm-display-only",
                      "category": "software-development"}) is None
        # Directory-name priority is untouched: the DIR name also resolves.
        assert _call({"action": "create", "name": "fm-owner",
                      "category": "software-development"}) is None
        # A DIFFERENT dir whose frontmatter mismatches its own dir name: the
        # mismatch dir's DISPLAY name (unique) resolves; dir names resolve too.
        d2 = os.path.join(skills, "dir-different")
        os.makedirs(d2)
        with open(os.path.join(d2, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nname: some-other-display\ndescription: t\n---\nbody\n")
        assert _call({"action": "create", "name": "some-other-display",
                      "category": "software-development"}) is None
        assert _call({"action": "create", "name": "dir-different",
                      "category": "software-development"}) is None


def test_frontmatter_name_ambiguous_holder_is_gated():
    """Runtime parity: two skills claiming one display name makes _find_skill
    REFUSE to guess (returns None — the create proceeds fresh), so the gate
    must treat the name as genuinely new and gate it."""
    with fixture_home() as (_tmp_home, skills):
        for holder in ("fm-holder-a", "fm-holder-b"):
            d = os.path.join(skills, holder)
            os.makedirs(d)
            with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
                f.write("---\nname: contested-display\ndescription: t\n---\nbody\n")
        r = _call({"action": "create", "name": "contested-display",
                   "category": "software-development"})
        assert _is_block(r), "ambiguous frontmatter name must stay gated, not spoof existence"


def test_symlinked_duplicate_skill_md_is_one_holder():
    """Round-5 fix #2: frontmatter claimants are deduped by the RESOLVED
    SKILL.md FILE (the runtime's own dedupe key, ``skill_dir / 'SKILL.md'``
    resolved) — NOT the directory. Two directories symlinking ONE SKILL.md
    file are ONE holder: the display name exists (the runtime create would
    return 'already exists'), despite two distinct SKILL.md paths."""
    with fixture_home() as (_tmp_home, skills):
        real_dir = os.path.join(skills, "real-owner")
        os.makedirs(real_dir)
        with open(os.path.join(real_dir, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nname: shared-fm-display\ndescription: t\n---\nbody\n")
        for link_dir in ("link-view-a", "link-view-b"):
            d = os.path.join(skills, link_dir)
            os.makedirs(d)
            os.symlink(os.path.join(real_dir, "SKILL.md"), os.path.join(d, "SKILL.md"))
        mod = _plugin()
        # Sanity: the runtime resolver treats it as exactly one skill.
        assert len(mod._walk_find_frontmatter(skills, "shared-fm-display")) == 1
        # One holder -> the display name exists: no flag needed, no gate.
        r = _call({"action": "create", "name": "shared-fm-display",
                   "category": "software-development"})
        assert r is None


def test_dir_name_match_decides_through_parser_failure():
    """Round-5 fix #3 (Opus 5): the directory-name scan completes across ALL
    roots BEFORE the frontmatter pass — runtime sequence parity. Even when
    every frontmatter read raises, a name the runtime resolves by DIRECTORY
    name still passes (the frontmatter pass never runs for it); when ONLY the
    frontmatter pass could decide, the raise still propagates (fail closed,
    like the runtime's fallback lookup)."""
    with fixture_home() as (_tmp_home, skills):
        # A frontmatter-only holder exists too, so both passes have targets.
        d = os.path.join(skills, "fm-holder-seq")
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nname: seq-fm-display\ndescription: t\n---\nbody\n")
        mod = _plugin()
        orig = mod._frontmatter_name

        def raiser(skill_md):  # simulates a parser that raises (non-OSError)
            raise RuntimeError("frontmatter parser exploded")

        mod._frontmatter_name = raiser
        try:
            # Dir-name match ('existing-skill' is planted by the fixture):
            # decided by the DIRECTORY pass, frontmatter never consulted.
            r = _call({"action": "create", "name": "existing-skill",
                       "category": "software-development"})
            assert r is None
            # Frontmatter-only target: only that pass can decide -> it raises
            # -> propagates (fail closed, exactly the runtime's own behavior
            # when _read_frontmatter_name hits an unexpected parser error).
            try:
                _call({"action": "create", "name": "seq-fm-display",
                       "category": "software-development"})
            except RuntimeError:
                pass
            else:
                raise AssertionError("frontmatter-only lookup must keep failing closed on a raise")
        finally:
            mod._frontmatter_name = orig
        r = _call({"action": "create", "name": "seq-fm-display",
                   "category": "software-development"})
        assert r is None


def test_config_excluded_root_is_skipped_entirely():
    """Round-5 fix #1 (Codex): the exclusion check applies to a CONFIGURED
    ROOT's own full path components (runtime ``is_excluded_skill_path`` checks
    EVERY component) — a root like ``<x>/node_modules/skills`` is skipped
    ENTIRELY, so a name existing only under it stays GATED (the runtime
    scanner excludes every SKILL.md under such a root; the gate reporting
    exists there let a create pass without the flag while the runtime created
    it fresh — a bypass). A clean configured root keeps resolving normally."""
    with fixture_home() as (home, _skills):
        mod = _plugin()
        excluded_root = os.path.join(home, "external", "node_modules", "skills")
        planted = os.path.join(excluded_root, "in-excluded-root")
        os.makedirs(planted)
        with open(os.path.join(planted, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("ok\n")
        fm_dir = os.path.join(excluded_root, "fm-inside-excluded")
        os.makedirs(fm_dir)
        with open(os.path.join(fm_dir, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nname: fm-inside-excluded\ndescription: t\n---\nbody\n")
        clean_root = os.path.join(home, "external-clean", "skills")
        clean_dir = os.path.join(clean_root, "clean-named-skill")
        os.makedirs(clean_dir)
        with open(os.path.join(clean_dir, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("ok\n")
        orig = mod._skill_roots
        mod._skill_roots = lambda: [excluded_root, clean_root]
        try:
            assert mod._root_is_excluded(excluded_root) is True
            assert mod._root_is_excluded(clean_root) is False
            # The walker would dir-match these if the root were scanned: block proves the skip.
            r = _call({"action": "create", "name": "in-excluded-root",
                       "category": "software-development"})
            assert _is_block(r), "excluded-component root must be skipped entirely (dir-match gated)"
            assert _is_block(_call({"action": "create", "name": "fm-inside-excluded",
                                    "category": "software-development"}))
            # A clean root grants existence exactly as before.
            r = _call({"action": "create", "name": "clean-named-skill",
                       "category": "software-development"})
            assert r is None
        finally:
            mod._skill_roots = orig


def test_mutating_batch_disarms_frontmatter_existence():
    """Round-5 fix #4 (Opus 2), BROADER since round-6 (Opus N1+N2): when a batch
    carries ANY non-create (mutating) op together with its create(s), the batch
    gets NO pre-batch existence lookup at all — the runtime runs batch ops in
    order, so a patch/edit/delete can remove an existing holder mid-batch, a
    mid-batch create can ADD a frontmatter claimant that makes an existing
    display name ambiguous (the runtime then refuses to guess and creates
    fresh), and an already-existing create target tool-errors ('already
    exists') rolling the batch back: blocking is the accepted over-gating.
    Every well-formed create in such a batch goes to pending (flag honored for
    exactly one). A batch of ONLY creates keeps the pre-round-6 semantics: a
    single well-formed create entry gets the full runtime-parity existence
    check including frontmatter parity (passes as before)."""
    with fixture_home() as (home, _skills):
        d = os.path.join(home, "skills", "fm-holder-mut")
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nname: fm-batch-display\ndescription: t\n---\nbody\n")
        create_op = {"action": "create", "name": "fm-batch-display", "content": "x",
                     "category": "software-development"}
        # Sanity (single-op parity): a create-only batch with ONE well-formed
        # entry keeps frontmatter parity — the display name exists, no flag.
        assert _call({"operations": [dict(create_op)]}) is None
        # A create-only TWO-entry batch: no short-circuit either (round-6) —
        # gated even with a flag, flag intact.
        flag = _set_flag(home)
        r = _call({"operations": [dict(create_op),
                                  {"action": "create", "name": "brand-new-second", "content": "y",
                                   "category": "software-development"}]})
        assert _is_block(r), r
        assert os.path.exists(flag), "refused two-create batch must leave the flag intact"
        os.unlink(flag)  # clean slate for the no-flag mutator loop below
        # A patch in the batch disarms the pre-batch existence answer: gated.
        for mutator in ({"action": "patch", "name": "existing-skill", "old_string": "a", "new_string": "b"},
                        {"action": "delete", "name": "existing-skill"}):
            r = _call({"operations": [mutator, dict(create_op)]})
            assert _is_block(r), (mutator, r)
        # With a flag the single pending create is still honored (and consumed).
        flag = _set_flag(home)
        r = _call({"operations": [{"action": "patch", "name": "existing-skill",
                                   "old_string": "a", "new_string": "b"}, dict(create_op)]})
        assert r is None, "one pending create + flag passes even in a mixed batch"
        assert not os.path.exists(flag)


def test_round6_frontmatter_claimant_batch_no_short_circuit():
    """Round-6 Opus N1: a create-only batch that (a) creates a skill whose
    frontmatter ``name:`` claims an ALREADY-claimed display name and (b) then
    creates that display name itself must be BLOCKED regardless of the flag.
    At runtime the second create runs AFTER the first added a second claimant:
    the display name becomes ambiguous, _find_skill refuses to guess, and the
    create proceeds FRESH — so pre-batch 'exists' was a lie; the multi-entry
    no-short-circuit rule never consults it."""
    with fixture_home() as (home, _skills):
        z = os.path.join(home, "skills", "z")
        holder = os.path.join(z, "fm-holder-bar")
        os.makedirs(holder)
        with open(os.path.join(holder, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nname: bar\ndescription: t\n---\nbody\n")
        # Sanity OUTSIDE the batch: 'bar' resolves as existing (unique
        # frontmatter holder) — full parity check, no flag, passes.
        r = _call({"action": "create", "name": "bar", "category": "software-development"})
        assert r is None
        batch = {"operations": [
            {"action": "create", "name": "new-a", "category": "software-development",
             "content": "---\nname: bar\ndescription: claims bar\n---\nbody\n"},
            {"action": "create", "name": "bar", "content": "x",
             "category": "software-development"},
        ]}
        # No flag: block regardless of 'bar' existing pre-batch.
        r = _call(batch)
        assert _is_block(r), r
        assert BATCH_MSG_TOKEN in r["message"]
        # With a flag: STILL blocked (two creates -> one-flag rule refuses) and
        # the flag stays intact.
        flag = _set_flag(home)
        r = _call(batch)
        assert _is_block(r), ("regardless of the flag", r)
        assert os.path.exists(flag), "flag must not be consumed for a refused batch"


def test_round6_delete_then_recreate_batch_gated_no_short_circuit():
    """Round-6 Opus N2: a [delete X, create X] batch — X exists pre-batch —
    must still gate its create: at runtime the delete removes X mid-batch and
    the create runs on a GENUINELY FRESH name (recreating X), so pre-batch
    existence cannot short-circuit the create. Without a flag: block (the
    flag directive). With a flag: the single pending create is honored and the
    flag consumed. Regression: a single-op create of X (no batch) still passes
    with full parity."""
    with fixture_home() as (home, _skills):
        batch = {"operations": [{"action": "delete", "name": "existing-skill"},
                                {"action": "create", "name": "existing-skill", "content": "x",
                                 "category": "software-development"}]}
        # No flag: gated even though X exists pre-batch.
        r = _call(batch)
        assert _is_block(r), r
        for tok in NEW_BLOCK_MSG_TOKENS:
            assert tok in r["message"], r["message"]
        # Single-op regression: without the batch, an existing name passes.
        r = _call({"action": "create", "name": "existing-skill",
                   "category": "software-development"})
        assert r is None
        # With a flag: the single pending create is honored -> flag consumed.
        flag = _set_flag(home)
        assert _call(batch) is None
        assert not os.path.exists(flag)


def test_dir_without_skill_md_is_nonexistent():
    with fixture_home() as (_tmp_home, skills):
        os.makedirs(os.path.join(skills, "hollow-skill"))  # no SKILL.md inside
        assert _is_block(_call({"action": "create", "name": "hollow-skill",
                                "category": "software-development"}))


def test_no_scan_caps_regression():
    mod = _plugin()
    assert not hasattr(mod, "_DIR_VISIT_CAP"), "4000-entry cap must be gone"
    assert not hasattr(mod, "_DIR_DEPTH_CAP"), "depth cap must be gone"
    with fixture_home() as (_tmp_home, skills):
        for i in range(220):
            os.makedirs(os.path.join(skills, f"bulk-old-{i:04d}"))
            with open(os.path.join(skills, f"bulk-old-{i:04d}", "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("ok\n")
        # Every bulk name resolves as existing; a new one still blocks.
        for i in (0, 110, 219):
            r = _call({"action": "create", "name": f"bulk-old-{i:04d}",
                       "category": "software-development"})
            assert r is None
        assert _is_block(_call({"action": "create", "name": "brand-new-after-bulk",
                                "category": "software-development"}))
        # No cap left means no false-block generator: probe with flag passes.
        flag = _set_flag(_tmp_home)
        r = _call({"action": "create", "name": "brand-new-after-bulk",
                   "category": "software-development"})
        assert r is None
        assert not os.path.exists(flag)


# --- 5b. Active-profile existence scope + recursive find (round-3 fixes #1/#2) -----------


def test_cross_profile_existing_name_still_blocks():
    """A name existing ONLY in a sibling (INACTIVE) profile is a genuinely new
    skill for the active profile: the runtime would create it fresh there, so
    the gate must TREAT IT AS NONEXISTENT and block (round-3 fix #1)."""
    with fixture_home() as (home, _skills):
        sibling_skill = os.path.join(
            home, "profiles", "inactive", "skills", "sibling-only-skill")
        os.makedirs(sibling_skill)
        with open(os.path.join(sibling_skill, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("ok\n")
        mod = _plugin()
        assert not any(
            os.sep + "profiles" + os.sep in r for r in mod._skill_roots()), mod._skill_roots()
        r = _call({"action": "create", "name": "sibling-only-skill",
                   "category": "software-development"})
        assert _is_block(r), "cross-profile-only existence must NOT satisfy the gate"
        for tok in NEW_BLOCK_MSG_TOKENS:
            assert tok in r["message"]


def test_deep_nested_name_exists_gated_parity():
    """Runtime _find_skill mirror (round-3 fix #2), under the v0.1.7 scoping:
    a SKILL.md at ANY depth whose enclosing directory name equals the target
    makes the name exist for a GATED create (root/team/<name>/SKILL.md) — the
    walker is category-free even though the gate decision is not. A NON-gated
    category on the same name passes ungated (the walker is not consulted:
    that is the scoping decision, not a walker failure)."""
    with fixture_home() as (_tmp_home, skills):
        deep = os.path.join(skills, "team", "deep-named-skill")
        os.makedirs(deep)
        with open(os.path.join(deep, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("ok\n")
        r = _call({"action": "create", "name": "deep-named-skill",
                   "category": "software-development"})
        assert r is None
        # A non-gated category on the same existing name: passes ungated.
        r = _call({"action": "create", "name": "deep-named-skill", "category": "team"})
        assert r is None


def test_deep_name_in_support_dir_is_not_existence_spoof():
    """Support dirs under an existing SKILL.md-bearing skill are pruned like the
    runtime walker: a stray SKILL.md under references/ cannot spoof existence."""
    with fixture_home() as (_tmp_home, skills):
        spoof = os.path.join(skills, "test", "existing-skill", "references", "sneaky-name")
        os.makedirs(spoof)
        with open(os.path.join(spoof, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("ok\n")
        assert _is_block(_call({"action": "create", "name": "sneaky-name",
                                "category": "software-development"}))


def test_discovered_skill_md_file_level_exclusion_gates():
    """Round-6 fix #1 (Codex): every DISCOVERED SKILL.md path is re-checked at
    FILE level by the runtime exclusion predicate (agent.skill_utils
    is_excluded_skill_path on its FULL path) before it may count as a claimant.

    The walker's directory-name pruning keys on 'SKILL.md' in os.walk's
    FILENAMES — a top-level SKILL.md that is a DIRECTORY (or a symlink to one)
    is filed into DIRNAMES instead, so has_skill_md stays False and the walker
    descends into a references/ tree under the root that the runtime's rglob +
    full-path check excludes ENTIRELY. Layout: external root = a skill's own
    dir (top-level SKILL.md present), with references/nested/SKILL.md inside.
    Runtime: _iter_skill_dirs excludes root/references/nested/SKILL.md ->
    _find_skill('nested') = None -> the create runs FRESH. The old gate PASSED
    'nested' flag-free (a bypass); the fixed gate re-checks the discovered
    file and finds nothing -> GATED. A clean sibling root keeps granting
    existence exactly as before."""
    with fixture_home() as (home, _skills):
        mod = _plugin()
        ext = os.path.join(home, "external-skill-root")
        os.makedirs(ext)
        os.makedirs(os.path.join(ext, "SKILL.md"))  # DIRECTORY named SKILL.md
        nested = os.path.join(ext, "references", "nested")
        os.makedirs(nested)
        with open(os.path.join(nested, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("---\nname: nested-fm-alias\ndescription: t\n---\nbody\n")
        clean_root = os.path.join(home, "external-clean", "skills")
        os.makedirs(clean_root)
        clean_skill = os.path.join(clean_root, "clean-named-skill")
        os.makedirs(clean_skill)
        with open(os.path.join(clean_skill, "SKILL.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("ok\n")
        try:  # the runtime's own verdict on this file (best-effort import)
            from agent.skill_utils import is_excluded_skill_path as _runtime_excl
            runtime_verdict = _runtime_excl(os.path.join(nested, "SKILL.md"))
        except ImportError:
            # Sandbox without the runtime sources: the gate's own full-path
            # mirror decides (direct runner / hermetic pytest runs).
            runtime_verdict = mod._file_is_excluded(os.path.join(nested, "SKILL.md"))
        assert runtime_verdict is True, \
            "the runtime itself excludes this file: the gate must follow"
        assert not mod._root_is_excluded(ext), "the ROOT is clean; only the file-level check catches it"
        orig = mod._skill_roots
        mod._skill_roots = lambda: [os.path.join(home, "skills"), ext, clean_root]
        try:
            # Direct helper: the discovered file is excluded; the mirror agrees.
            assert mod._file_is_excluded(os.path.join(nested, "SKILL.md")) is True
            assert not mod._file_is_excluded(os.path.join(clean_skill, "SKILL.md"))
            # Walker no longer counts the support-nested file (dir pass and
            # frontmatter pass both filtered): the create of 'nested' GATES.
            assert mod._walk_find_dir(ext, "nested") is False
            assert mod._walk_find_frontmatter(ext, "nested-fm-alias") == set()
            assert _is_block(_call({"action": "create", "name": "nested",
                                    "category": "software-development"})), \
                "names resolvable only through the excluded file must stay gated (no flag)"
            assert _is_block(_call({"action": "create", "name": "nested-fm-alias",
                                    "category": "software-development"})), \
                "frontmatter claims through the excluded file must not satisfy the gate either"
            assert not os.path.exists(_flag_of(home)), "no flag was present: none may be consumed"
            # A clean root's skills keep resolving normally (parity, no flag).
            r = _call({"action": "create", "name": "clean-named-skill",
                       "category": "software-development"})
            assert r is None
        finally:
            mod._skill_roots = orig


# --- 6. Flag atomicity (R4) ---------------------------------------------------------------


def test_flag_unlink_failure_blocks_flag_left():
    with fixture_home() as (home, _skills):
        flag = _set_flag(home)
        mod = _plugin()
        orig_unlink = os.unlink

        def failing_unlink(path, *a, **kw):
            raise OSError(errno.EACCES, "permission denied", path)

        os.unlink = failing_unlink
        try:
            r = _call({"action": "create", "name": "brand-new-skill",
                       "category": "software-development"})
        finally:
            os.unlink = orig_unlink
        assert _is_block(r), "unlink failure must BLOCK, never pass with the flag intact"
        assert UNLINK_FAIL_TOKEN in r["message"], "block must carry the flag-left note"
        assert os.path.exists(flag)


def test_flag_absent_no_consumption_on_block_path():
    with fixture_home() as (home, _skills):
        r = _call({"action": "create", "name": "brand-new-skill",
                   "category": "software-development"})
        assert _is_block(r), r
        assert not os.path.exists(_flag_of(home)), "blocked path must not create a flag"


# --- 7. Fail-closed error behavior (R3) ----------------------------------------------------


def test_internal_error_propagates_on_create_decision():
    with fixture_home():
        mod = _plugin()
        orig = mod._skill_dir_exists

        def boom(*a, **kw):
            raise RuntimeError("oracle exploded")

        mod._skill_dir_exists = boom
        try:
            try:
                mod._on_pre_tool_call(
                    tool_name="skill_manage",
                    args={"action": "create", "name": "brand-new-skill",
                          "category": "software-development"})
            except RuntimeError:
                pass  # expected: create decisions fail CLOSED (runtime turns raise into block)
            else:
                raise AssertionError("create decision must PROPAGATE internal errors (fail-closed)")
        finally:
            mod._skill_dir_exists = orig


def test_fast_path_cannot_raise():
    mod = _plugin()
    orig = mod._skill_dir_exists
    mod._skill_dir_exists = _boom_static
    try:
        assert mod._on_pre_tool_call(tool_name="read_file", args={"path": "/etc/passwd", "extra": object()}) is None
        assert mod._on_pre_tool_call(tool_name="terminal", args=None) is None
    finally:
        mod._skill_dir_exists = orig


def _boom_static(*a, **kw):
    raise RuntimeError("must never be reached from the fast path")


def test_block_message_asks_user_for_flag():
    with fixture_home():
        r = _call({"action": "create", "name": "brand-new-skill",
                   "category": "software-development"})
        assert "Ask the user" in r["message"], "R7 framing: ask the user to create the flag"


def test_block_message_carries_resolved_flag_path():
    """Round-4 fix #4 (Opus): the flag directive must interpolate the RESOLVED
    flag path, not a hardcoded ~/.hermes/... — under an active profile the
    resolved path differs and a hardcoded path would be an unusable instruction."""
    with fixture_home() as (home, _skills):
        r = _call({"action": "create", "name": "brand-new-skill",
                   "category": "software-development"})
        resolved = _flag_of(home)  # fixture home's RESOLVED flag path
        assert resolved in r["message"], r["message"]
        assert f"echo ok > {resolved}" in r["message"], r["message"]
        assert f"echo ok > ~/.hermes/skills/.allow-create" not in r["message"], \
            "hardcoded default-home path must not leak into the directive"
        # Directive is built at decision time: a DIFFERENT home later gets its own path.
        with tempfile.TemporaryDirectory() as other:
            other_home = os.path.join(other, "other-home")
            os.makedirs(os.path.join(other_home, "skills"))
            prev = os.environ.get("HERMES_HOME")
            os.environ["HERMES_HOME"] = other_home
            try:
                r2 = _call({"action": "create", "name": "brand-new-skill",
                            "category": "software-development"})
            finally:
                if prev is None:
                    os.environ.pop("HERMES_HOME", None)
                else:
                    os.environ["HERMES_HOME"] = prev
            assert os.path.join(other_home, "skills", ".allow-create") in r2["message"], r2["message"]


def test_unlink_failure_note_carries_resolved_flag_path():
    with fixture_home() as (home, _skills):
        flag = _set_flag(home)
        mod = _plugin()
        orig_unlink = os.unlink

        def failing_unlink(path, *a, **kw):
            raise OSError(errno.EACCES, "permission denied", path)

        os.unlink = failing_unlink
        try:
            r = _call({"action": "create", "name": "brand-new-skill",
                       "category": "software-development"})
        finally:
            os.unlink = orig_unlink
        assert UNLINK_FAIL_TOKEN in r["message"]
        assert flag in r["message"], f"resolved flag path must appear: {r['message']}"


# --- 8. Registration ------------------------------------------------------------------------


class _FakeCtx:
    def __init__(self):
        self.skills = []
        self.hooks = []

    def register_skill(self, name, path):
        assert ":" not in name
        self.skills.append((name, path))

    def register_hook(self, event, cb):
        self.hooks.append((event, cb))


def test_register_wires_ten_skills_and_hook():
    mod = _plugin()
    ctx = _FakeCtx()
    mod.register(ctx)
    assert len(ctx.skills) == 10, ctx.skills
    assert ctx.skills == sorted(ctx.skills, key=lambda t: mod._BUNDLED_SKILLS.index(t[0]))
    assert len(ctx.hooks) == 1 and ctx.hooks[0][0] == "pre_tool_call"


def test_gateway_loader_package_fidelity():
    """Exec __init__.py AS A PACKAGE (gateway loader context) and call register(ctx).

    sys.modules entries it installs are REMOVED afterward (round-4 fix #5: the
    old version polluted the interpreter's module cache for every later test)."""
    init_path = PLUGIN_DIR / "__init__.py"
    pkg = types.ModuleType("hermes_plugins")
    pkg.__path__ = []
    name = "hermes_plugins.dev_pipeline_under_test_pkg"
    sys.modules[name] = pkg  # temporarily, so the parent package name resolves
    try:
        spec = importlib.util.spec_from_file_location(
            name, init_path, submodule_search_locations=[str(PLUGIN_DIR)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules["hermes_plugins"] = pkg
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        assert mod.__package__ == name, "relative-import chain must resolve in the loader context"
        ctx = _FakeCtx()
        mod.register(ctx)
        assert len(ctx.skills) == 10 and len(ctx.hooks) == 1
    finally:
        sys.modules.pop(name, None)
        sys.modules.pop("hermes_plugins", None)
        assert "hermes_plugins" not in sys.modules, "stub module must not survive the test"
        assert name not in sys.modules, "test module stub must not survive the test"


# --- 9. Live roots (READ-ONLY; never touches the live allow flag) -----------------------------


def test_live_roots_readonly_probe():
    """Round-5 fix #6 (Opus 3): the probe resolves EVERYTHING through the
    plugin's own resolver — mod._flag_path() and mod._skill_roots() — never a
    hardcoded ~/.hermes/skills path (wrong under a profile or HERMES_HOME), and
    SKIPS ENTIRELY when a real single-use flag exists at the RESOLVED path, so
    a live flag can never be consumed by this read-only suite."""
    mod = _plugin()
    live_flag = mod._flag_path()
    live_skills = os.path.dirname(live_flag)
    roots = [r for r in mod._skill_roots() if os.path.isdir(r)]
    if not roots:
        _skip("no live skill roots resolvable in this sandbox")
    if not os.access(live_skills, os.R_OK | os.X_OK):
        _skip("live skills dir (%s) missing or unreadable in this sandbox (read-only root)" % live_skills)
    if os.path.isfile(live_flag):
        _skip("a real single-use allow flag exists at %s — skipping so it is never consumed" % live_flag)
    # An existing live skill (any entry carrying SKILL.md at depth <= 2) passes.
    existing = None
    for root in roots:
        if not os.access(root, os.R_OK | os.X_OK):
            continue
        try:
            entries = sorted(os.listdir(root))
        except OSError:
            _skip("live root %s became unreadable mid-probe" % root)
        for name in entries:
            cand = os.path.join(root, name)
            if name.startswith("."):
                continue
            if os.path.isfile(os.path.join(cand, "SKILL.md")):
                existing = name
                break
            try:
                for entry in sorted(os.listdir(cand)):
                    if entry.startswith("."):
                        continue
                    if os.path.isfile(os.path.join(cand, entry, "SKILL.md")):
                        existing = entry
                        break
            except OSError:
                pass
            if existing:
                break
        if existing:
            break
    assert existing, "live skills root should contain at least one skill for the probe"
    r = _call({"action": "create", "name": existing, "category": "software-development"})
    assert r is None
    assert not os.path.isfile(live_flag), "the read-only probe must never consume the live flag"
    # A nonexistent live skill blocks (no flag was present at probe start).
    assert _is_block(_call({"action": "create", "name": "zz-gate-probe-nonexistent",
                            "category": "software-development"}))
    assert not os.path.isfile(live_flag), "a block must never fabricate or consume the live flag"


# --- Direct runner ---------------------------------------------------------------------------


def run_all() -> list[tuple[str, str]]:
    results = []
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            # _SKIPPED_TYPES catches pytest's Skipped FIRST: it subclasses
            # BaseException, so a bare `except Exception` would miss it and
            # crash the direct runner with a traceback (round-4 fix #5).
            except _SKIPPED_TYPES as exc:
                results.append((name, f"SKIP: {exc}"))
            except BaseException as exc:  # noqa: BLE001 - direct runner reports, does not hide
                results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            else:
                results.append((name, "PASS"))
    return results



# --- Round-7 (F1 + depth>0 dedupe) regression tests ------------------------------------------


def test_dangling_skill_md_symlink_is_never_a_claimant():
    """F1: a dangling SKILL.md symlink must not make a name exist (gate blocks)."""
    with fixture_home() as (home, skills):
        os.makedirs(os.path.join(skills, "ghost"))
        os.symlink("/nowhere/dangling-target", os.path.join(skills, "ghost", "SKILL.md"))
        # No flag: ghost resolves as NEW -> block with the directive.
        assert _is_block(_call({"action": "create", "name": "ghost",
                                "category": "software-development"}))
        # With a flag: single well-formed create honored and consumed.
        _set_flag(home)
        r = _call({"action": "create", "name": "ghost",
                   "category": "software-development"})
        assert r is None
        assert not os.path.isfile(_flag_of(home)), "single-use flag must be consumed"


def test_nested_depth_scalar_ops_flag_still_honors_single_create():
    """Round-6 over-block fix: dict-wrapped scalar ops at depth>0 yield ONE
    pending (the caller's flat create) so the single-use flag works."""
    with fixture_home() as (home, skills):
        _set_flag(home)
        r = _call({"action": "create", "name": "brand-new-x",
                   "category": "software-development", "operations": "{\"ops\": null}"})
        assert r is None, f"expected flag-honored pass, got {r!r}"
        assert not os.path.isfile(_flag_of(home)), "flag consumed for the one honored create"


def test_nested_depth_limit_flag_still_honors_single_create():
    """Depth-limit branch at depth>0 must not duplicate the flat create:
    deep nesting + flag => exactly one create honored."""
    with fixture_home() as (home, skills):
        _set_flag(home)
        deep_ops = "[]"
        for _ in range(8):
            deep_ops = "{\"operations\":" + deep_ops + "}"
        r = _call({"action": "create", "name": "brand-new-y",
                   "category": "software-development", "operations": deep_ops})
        assert r is None, f"expected single flag-honored pass, got {r!r}"
        assert not os.path.isfile(_flag_of(home))


def test_nested_empty_batch_string_flag_still_honors_single_create():
    """Empty batch string inside a dict wrapper at depth>0: caller carries the
    single flat create; with a flag it is honored once."""
    with fixture_home() as (home, skills):
        _set_flag(home)
        r = _call({"action": "create", "name": "brand-new-z",
                   "category": "software-development", "operations": "{\"operations\": \"[]\"}"})
        assert r is None, f"expected single flag-honored pass, got {r!r}"
        assert not os.path.isfile(_flag_of(home))




# --- 10. v0.1.7 category scoping (software-development ONLY) ----------------------------------


def test_non_dev_category_passes_flag_free_and_consumes_nothing():
    """v0.1.7: ANY category other than software-development — other plain
    strings, non-string values, lookalikes that do not normalize to the gated
    one — passes WITHOUT the flag and consumes nothing (a genuinely new name,
    so only the category scoping lets it through)."""
    with fixture_home() as (home, _skills):
        for category in ("test", "media", "node_modules", "Software",
                         "software_development", "software-development-but-really-not",
                         "SOFTWARE DEVELOPMENT", 123, True, None):
            r = _call({"action": "create", "name": "brand-new-ungated", "category": category})
            assert r is None, (category, r)
        # With a flag present, the ungated pass consumes NOTHING.
        flag = _set_flag(home)
        for category in ("test", 123, None):
            r = _call({"action": "create", "name": "brand-new-ungated", "category": category})
            assert r is None, (category, r)
        assert os.path.exists(flag), "an ungated pass must never consume the flag"


def test_no_category_create_passes_flag_free_and_consumes_nothing():
    """v0.1.7: a create with NO category (absent, empty string, whitespace-only)
    is NOT gated — it passes exactly like a registered-name create and never
    consumes the flag."""
    with fixture_home() as (home, _skills):
        for category in ("", " ", None):
            r = _call({"action": "create", "name": "brand-new-nocat", "category": category})
            assert r is None, (repr(category), r)
        r = _call({"action": "create", "name": "brand-new-nocat"})
        assert r is None, "a create without a category key must pass ungated"
        flag = _set_flag(home)
        r = _call({"action": "create", "name": "brand-new-nocat"})
        assert r is None
        assert os.path.exists(flag), "a category-less pass must never consume the flag"


def test_mixed_batch_gates_only_the_gated_create():
    """v0.1.7 edge (a): a batch mixing a dev-gated create and an ungated one
    decides ONLY the gated create — the ungated one vanishes from the decision
    pipeline (never counts toward the multi-entry rule, never blocks, never
    consumes). One flag still authorizes exactly the gated one."""
    with fixture_home() as (home, _skills):
        ungated = {"action": "create", "name": "brand-new-ungated", "content": "x"}
        batch = {"operations": [dict(ungated),
                                {"action": "create", "name": "brand-new-gated", "content": "y",
                                 "category": "software-development"}]}
        # No flag: the gated create alone decides -> the flag directive (NOT
        # the multi-entry batch message: the ungated entry cannot make the
        # batch multi-entry).
        r = _call(batch)
        assert _is_block(r), r
        for tok in NEW_BLOCK_MSG_TOKENS:
            assert tok in r["message"], r["message"]
        assert BATCH_MSG_TOKEN not in r["message"], \
            f"an ungated entry must not push the batch into the multi-entry rule: {r['message']}"
        # With one flag: the gated create is honored (flag consumed); the
        # ungated create was never part of the decision.
        flag = _set_flag(home)
        r = _call(batch)
        assert r is None, r
        assert not os.path.exists(flag), "the flag authorizes exactly the one gated create"
        # Round-9 N1 correction: an ungated companion disqualifies the
        # existence short-circuit (it CAN add a frontmatter claimant
        # mid-batch, making the gated name ambiguous/fresh at runtime), so
        # even an existing-name gated create needs its flag in a mixed batch
        # (conservative, fail-closed; flag consumed on honor).
        mixed_existing = {"operations": [dict(ungated),
                                         {"action": "create", "name": "existing-skill", "content": "y",
                                          "category": "software-development"}]}
        assert _is_block(_call(mixed_existing))
        _set_flag(home)
        assert _call(mixed_existing) is None
        assert not os.path.exists(_flag_of(home))
        # Order swap: the ungated entry FIRST changes nothing about the gating.
        r = _call({"operations": [{"action": "create", "name": "brand-new-gated-2", "content": "y",
                                   "category": "software-development"}, dict(ungated)]})
        assert _is_block(r), r


def test_category_normalization_gates_software_development_variants():
    """v0.1.7 edge (c): the gated comparison runs on strip().lower() — case
    variants and surrounding whitespace of 'software-development' all GATE;
    lookalikes that do not normalize to it stay ungated (and leave any flag
    untouched)."""
    with fixture_home() as (home, _skills):
        for category in ("software-development", "Software-Development", "SOFTWARE-DEVELOPMENT",
                         " Software-Development ", " software-development", "SOFTWARE-Development "):
            r = _call({"action": "create", "name": "brand-new-normalized", "category": category})
            assert _is_block(r), (repr(category), r)
            assert "SOFTWARE-DEVELOPMENT" in r["message"], (repr(category), r["message"])
        # Not-gated lookalikes pass flag-free.
        for category in ("software_development", "Software Development", "dev-software-development"):
            r = _call({"action": "create", "name": "brand-new-lookalike", "category": category})
            assert r is None, (repr(category), r)
        # A flag survives every ungated pass untouched...
        flag = _set_flag(home)
        for category in ("software_development", "Software Development"):
            r = _call({"action": "create", "name": "brand-new-normalized", "category": category})
            assert r is None, (repr(category), r)
        assert os.path.exists(flag), "lookalike categories are not gated: the flag survives"
        # ...and still authorizes the next case-normalized GATED create.
        r = _call({"action": "create", "name": "brand-new-normalized",
                   "category": "  SOFTWARE-development "})
        assert r is None
        assert not os.path.exists(flag), "the normalized gated create consumed the flag"


def test_flag_not_consumed_on_ungated_pass():
    """v0.1.7: the flag survives ANY ungated pass untouched — including a
    malformed name on an ungated create (edge b) — and remains valid for the
    next gated create."""
    with fixture_home() as (home, _skills):
        flag = _set_flag(home)
        assert _call({"action": "create", "name": "brand-new-ungated", "category": "test"}) is None
        assert _call({"action": "create", "name": "brand-new-ungated"}) is None
        assert _call({"action": "create", "name": "../traversal-evil", "category": "test"}) is None
        assert os.path.exists(flag), \
            "ungated passes (including malformed-ungated) must never consume the flag"
        r = _call({"action": "create", "name": "brand-new-gated-after",
                   "category": "software-development"})
        assert r is None
        assert not os.path.exists(flag), "the surviving flag still authorizes one gated create"


def test_gated_block_message_reserves_software_development():
    """v0.1.7 edge (d): the flag directive says the gate reserves new
    SOFTWARE-DEVELOPMENT skills (and only those)."""
    with fixture_home():
        r = _call({"action": "create", "name": "brand-new-skill",
                   "category": "software-development"})
        assert "reserves new SOFTWARE-DEVELOPMENT skills" in r["message"], r["message"]

if __name__ == "__main__":
    rows = run_all()
    print(f"{'TEST':66} | RESULT")
    print("-" * 96)
    failures = 0
    skipped = 0
    for label, verdict in rows:
        print(f"{label:66} | {verdict}")
        if verdict.startswith("FAIL"):
            failures += 1
        elif verdict.startswith("SKIP"):
            skipped += 1
    print("-" * 96)
    print(f"TOTAL {len(rows)} | PASS {len(rows) - failures - skipped} | SKIP {skipped} | FAIL {failures}")
    sys.exit(1 if failures else 0)
