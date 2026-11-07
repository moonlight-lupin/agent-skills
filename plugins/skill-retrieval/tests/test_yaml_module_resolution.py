"""Regression tests for issue #28: YAML module resolution on CPython 3.14.

PyYAML historically shipped no CPython 3.14 wheel, so ``import yaml`` failed
on 3.14 venvs and the BM25 corpus silently came back empty. PR #29 adds
``_yaml_module()``, which prefers the host's ``hermes_yaml`` (ruamel) facade
and falls back to PyYAML. These tests pin the resolution contract:

- hermes_yaml preferred when importable;
- PyYAML used when hermes_yaml is absent;
- every ``yaml.*`` attribute used at the call sites exists on whichever
  module resolves (safe_load, YAMLError);
- ``_parse_skill_md`` keeps its never-raises contract even if BOTH modules
  are missing;
- malformed frontmatter raises YAMLError from the resolved module and is
  swallowed to ("", "", "").
"""

import sys
import types
from pathlib import Path

import pytest

import bm25_retriever as br


def _fake_yaml_module(name, attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


@pytest.fixture(autouse=True)
def _reset_yaml_cache():
    """Each test starts with a cold _YAML_MODULE cache."""
    br._YAML_MODULE = None
    yield
    br._YAML_MODULE = None


class _FakeYamlError(Exception):
    pass


@pytest.fixture
def no_yaml_modules(monkeypatch):
    """Make both `hermes_yaml` and `yaml` unimportable, and drop any cached copies."""
    monkeypatch.delitem(sys.modules, "hermes_yaml", raising=False)
    monkeypatch.delitem(sys.modules, "yaml", raising=False)

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("hermes_yaml", "yaml"):
            raise ModuleNotFoundError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    import builtins
    monkeypatch.setattr(builtins, "__import__", fake_import)


# ── resolution order ────────────────────────────────────────────────────────

def test_yaml_module_prefers_hermes_yaml_when_present(monkeypatch):
    """When hermes_yaml imports, it is returned even if PyYAML also exists."""
    fake = _fake_yaml_module("hermes_yaml", {"safe_load": lambda s: {}, "YAMLError": _FakeYamlError})
    monkeypatch.setitem(sys.modules, "hermes_yaml", fake)
    assert br._yaml_module() is fake


def test_yaml_module_falls_back_to_pyyaml(monkeypatch):
    """No hermes_yaml -> PyYAML module is used."""
    monkeypatch.delitem(sys.modules, "hermes_yaml", raising=False)
    fake = _fake_yaml_module("yaml", {"safe_load": lambda s: {}, "YAMLError": _FakeYamlError})
    monkeypatch.setitem(sys.modules, "yaml", fake)
    assert br._yaml_module() is fake


# ── facade surface parity ───────────────────────────────────────────────────

def test_resolved_module_exposes_safe_load_and_yamlerror():
    """Both call-site attributes (safe_load, YAMLError) must exist on the
    resolved module — whichever engine won."""
    resolved = br._yaml_module()
    assert callable(resolved.safe_load)
    assert isinstance(resolved.YAMLError, type) and issubclass(resolved.YAMLError, BaseException)


def test_yaml_module_resolved_once_and_cached(monkeypatch):
    """Second call must return the cached module without re-importing."""
    fake = _fake_yaml_module("hermes_yaml", {"safe_load": lambda s: {}, "YAMLError": _FakeYamlError})
    monkeypatch.setitem(sys.modules, "hermes_yaml", fake)
    import builtins
    real_import = builtins.__import__
    calls = []

    def counting_import(name, *args, **kwargs):
        if name == "hermes_yaml":
            calls.append(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", counting_import)
    assert br._yaml_module() is fake
    assert br._yaml_module() is fake
    assert calls == ["hermes_yaml"]  # imported exactly once


# ── never-raises contract ───────────────────────────────────────────────────

def test_parse_skill_md_never_raises_when_both_yaml_modules_missing(tmp_path, no_yaml_modules):
    """Both YAML modules missing must not propagate ModuleNotFoundError out
    of _parse_skill_md — the documented contract is never-raises."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\nname: demo\ndescription: d\n---\n\nbody\n")
    # Must return the empty triple, not raise.
    assert br._parse_skill_md(skill_md) == ("", "", "")


def test_parse_skill_md_malformed_yaml_returns_empty(tmp_path, monkeypatch):
    """A frontmatter block that the resolved engine rejects with its own
    YAMLError subclass must be swallowed to ("", "", "")."""
    class Boom(Exception):
        pass

    def bad_load(_text):
        raise Boom("malformed")

    fake = _fake_yaml_module("hermes_yaml", {"safe_load": bad_load, "YAMLError": Boom})
    monkeypatch.setitem(sys.modules, "hermes_yaml", fake)

    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text("---\nname: [unclosed\n---\n\nbody\n")
    assert br._parse_skill_md(skill_md) == ("", "", "")


def test_parse_skill_md_happy_path_parses_frontmatter(tmp_path, monkeypatch):
    """End-to-end: a valid SKILL.md parses name/description through whatever
    YAML module _yaml_module() resolves on this host."""
    skill_md = tmp_path / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: demo-skill\n"
        "description: A demo skill for regression pinning.\n"
        "---\n"
        "\n"
        "# Demo\n"
    )
    name, desc, _preview = br._parse_skill_md(skill_md)
    assert name == "demo-skill"
    assert "demo skill" in desc.lower()
