"""Test bootstrap: make the plugin dir a valid package root for pytest.

The plugin dir name (skill-governance) is not a Python identifier, so pytest's
importlib mode derives an invalid module name when this dir is the rootdir.
Inserting the parent on sys.path lets `import skill_governance` resolve via the
dir name mapped in `_plugin()`; with the parent on sys.path the package import
succeeds under importlib mode and the relative import in __init__.py works.
"""
import sys
from pathlib import Path

_PLUGIN_DIR = str(Path(__file__).resolve().parents[1])
_PARENT = str(Path(__file__).resolve().parents[2])
for _p in (_PARENT, _PLUGIN_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)
