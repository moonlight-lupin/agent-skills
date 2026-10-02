"""Make the scripts/ directory importable from tests.

Tests import ``bm25_retriever`` as a top-level module (scripts/ on
sys.path). The plugin package imports the same file as
``scripts.bm25_retriever``. Alias those names onto one module object so
index caches are not split across two identities.
"""
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
PLUGIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN))  # after the SCRIPTS insert
import scripts.bm25_retriever as _br

sys.modules.setdefault("bm25_retriever", _br)  # unify module identity


@pytest.fixture(autouse=True)
def _hermetic_disabled_skills(monkeypatch):
    """Neutralize host config bleed into the runtime cache key.

    When the ambient environment can import the real Hermes core (e.g. the
    agent kernel's PYTHONPATH), `_session_platform_key_parts` reads the
    host's real `skills:` config and folds ~78 real skill names into the
    index cache key — the suite's results then depend on where pytest ran.
    Tests that care about disabled sets monkeypatch this themselves (their
    patches run after this one and win). Host-config behavior is covered by
    test_index_cache's self-contained fixture, which stubs the whole agent
    module; nothing here exercises the real host config deliberately.
    """
    try:
        import agent.skill_utils as _su  # real core when ambient env exposes it
    except Exception:
        return  # hermetic env: nothing to neutralize
    monkeypatch.setattr(_su, "get_disabled_skill_names", lambda platform=None: set(), raising=True)
