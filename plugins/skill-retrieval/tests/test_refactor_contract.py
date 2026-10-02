"""Hermes-authored refactor contract tests (skill-retrieval monkey-patch removal).

These encode the catalog rule 9 contract. The builder must make them pass
WITHOUT modifying this file.

Honest-RED contract: before the refactor each test fails on an assertion
(not an import error) because the monkey-patches still exist.
"""
import ast
import re
from pathlib import Path



PLUGIN_DIR = Path(__file__).resolve().parent.parent
INIT_PATH = PLUGIN_DIR / "__init__.py"


def test_no_core_override_monkey_patches_removed():
    """Catalog rule 9 'no core override': the plugin must not assign/wrap any
    agent.prompt_builder attribute (build_skills_system_prompt or
    clear_skills_system_prompt_cache). A regex scan of the module source is
    the shape the catalog admission scan uses."""
    src = INIT_PATH.read_text(encoding="utf-8")
    # Assignment to any prompt_builder.<attr> — both current patches match this.
    bind = re.search(r"prompt_builder\.\w+\s*=", src)
    assert bind is None, f"monkey-patch still present at match {bind!r}"
    assert "clear_skills_system_prompt_cache" not in src, (
        "wrapper of clear_skills_system_prompt_cache still present"
    )


def test_registration_uses_public_surfaces():
    """register(ctx) must install: the per-turn pre_llm_call hook, the
    llm_request middleware (names-only skills rewrite), and the
    on_skill_lifecycle observer (index invalidation) — through ctx only.
    On hosts without a runtime, the source itself declares the intent."""
    src = INIT_PATH.read_text(encoding="utf-8")
    assert 'register_middleware("llm_request"' in src, (
        "llm_request middleware not registered through ctx"
    )
    assert '"on_skill_lifecycle"' in src, (
        "on_skill_lifecycle observer not subscribed"
    )
    assert '"pre_llm_call"' in src, "pre_llm_call hook no longer registered"


def test_names_only_rewrite_is_a_pure_function():
    """The names-only compaction must live in a module-level pure function the
    middleware reuses, so request rewriting is deterministic and testable."""
    src = INIT_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    funcs = {
        node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "compact_available_skills_block" in funcs, (
        "pure rewrite function compact_available_skills_block missing"
    )