"""Tests and the plugin fallback must share one bm25_retriever module object."""


def test_tests_and_plugin_share_module_identity():
    import sys
    from pathlib import Path
    import importlib.util

    import bm25_retriever as br

    plugin_dir = Path(__file__).resolve().parent.parent
    # spec_from_file_location does not insert into sys.modules, so the
    # relative package import fails and the plugin takes its fallback path.
    spec = importlib.util.spec_from_file_location(
        "skill_retrieval_idcheck", str(plugin_dir / "__init__.py")
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    assert "skill_retrieval_idcheck" not in sys.modules
    assert m.get_index is br.get_index
    assert m.clear_index_cache is br.clear_index_cache
    assert m.get_skill_info is br.get_skill_info
    assert sys.modules["bm25_retriever"] is br
