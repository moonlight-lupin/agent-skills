#!/usr/bin/env python3
"""Plugin layout and de-CoS grep guard for Lumen."""

from __future__ import annotations

import ast
import filecmp
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "company" + ".yaml",
    "state" + "_" + "db",
    "chief" + "_" + "of" + "_" + "staff",
    "chief" + "-of-" + "staff",
    "chief" + " of " + "staff",
)


def test_plugin_yaml_identity():
    path = PLUGIN_ROOT / "plugin.yaml"
    assert path.is_file()
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["name"] == "lumen"
    version = str(data["version"])
    parts = version.split(".")
    assert len(parts) >= 2
    assert all(p.isdigit() for p in parts)
    assert data.get("name")
    assert data.get("version")


def test_license_and_readme_exist_and_nonempty():
    for name in ("LICENSE", "README.md"):
        path = PLUGIN_ROOT / name
        assert path.is_file(), f"missing {name}"
        assert path.read_text(encoding="utf-8").strip(), f"{name} is empty"


def test_sample_wiki_fixtures_are_byte_identical():
    plugin_wiki = PLUGIN_ROOT / "tests" / "fixtures" / "sample_wiki"
    repo_wiki = PLUGIN_ROOT.parent / "tests" / "fixtures" / "sample_wiki"
    assert plugin_wiki.is_dir()
    if not repo_wiki.is_dir():
        pytest.skip("sibling repo fixture tests/fixtures/sample_wiki is absent")
    plugin_files = {
        path.relative_to(plugin_wiki): path
        for path in plugin_wiki.rglob("*")
        if path.is_file()
    }
    repo_files = {
        path.relative_to(repo_wiki): path
        for path in repo_wiki.rglob("*")
        if path.is_file()
    }
    assert plugin_files.keys() == repo_files.keys()
    mismatched = [
        rel.as_posix()
        for rel, path in plugin_files.items()
        if not filecmp.cmp(path, repo_files[rel], shallow=False)
    ]
    assert mismatched == []


def test_skill_dirs_have_skill_md():
    for name in ("wiki", "curator"):
        skill = PLUGIN_ROOT / "skills" / name / "SKILL.md"
        assert skill.is_file(), f"missing {skill}"
        text = skill.read_text(encoding="utf-8")
        assert text.startswith("---")
        end = text.index("---", 3)
        fm = yaml.safe_load(text[3:end]) or {}
        assert fm.get("name") == name
        desc = fm.get("description") or ""
        assert desc
        assert len(desc) <= 1024


def test_register_exposed():
    init_path = PLUGIN_ROOT / "__init__.py"
    source = init_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "register"]
    assert fns, "register(ctx) must be defined"
    args = [a.arg for a in fns[0].args.args]
    assert args == ["ctx"] or args[0] == "ctx"

    spec = importlib.util.spec_from_file_location("lumen_plugin", init_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)

    class RecordingCtx:
        """Mirrors hermes_cli.plugins.PluginContext.register_skill."""

        def __init__(self) -> None:
            self.registered: list[tuple[str, Path, str, dict]] = []

        def register_skill(self, name, path, description="", frontmatter=None) -> None:
            self.registered.append((name, Path(path), description, dict(frontmatter or {})))

    ctx = RecordingCtx()
    mod.register(ctx)
    assert [entry[0] for entry in ctx.registered] == ["wiki", "curator"]
    for name, path, description, frontmatter in ctx.registered:
        assert path.is_file(), f"missing SKILL.md for {name}: {path}"
        assert path.name == "SKILL.md"
        text = path.read_text(encoding="utf-8")
        expected = yaml.safe_load(text[3 : text.index("---", 3)]) or {}
        assert description, f"empty description for {name}"
        assert description == expected["description"]
        assert frontmatter == expected


def test_register_falls_back_for_legacy_two_arg_ctx():
    init_path = PLUGIN_ROOT / "__init__.py"
    spec = importlib.util.spec_from_file_location("lumen_plugin_legacy", init_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    class LegacyCtx:
        def __init__(self) -> None:
            self.registered: list[tuple[str, Path]] = []

        def register_skill(self, name, path) -> None:
            self.registered.append((name, Path(path)))

    ctx = LegacyCtx()
    mod.register(ctx)
    assert [name for name, _ in ctx.registered] == ["wiki", "curator"]


def test_no_forbidden_references():
    hits = []
    skip_parts = {".git", "__pycache__", ".pytest_cache"}
    for path in PLUGIN_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_parts for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".md", ".yaml", ".yml", ".txt", ".json"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lowered = text.lower()
        for needle in FORBIDDEN:
            if needle.lower() in lowered:
                rel = path.relative_to(PLUGIN_ROOT)
                hits.append(f"{rel}: {needle}")
    assert hits == [], "forbidden references:\n" + "\n".join(hits)


def _is_runtime_bytecode_name(name: str) -> bool:
    return name.endswith((".pyc", ".pyo")) and "cpython" in name


def _publication_binary_hits(root: Path) -> list[str]:
    skip_parts = {".git", ".pytest_cache"}
    blocked_suffixes = {".pyc", ".pyo", ".so", ".pyd"}
    hits = []
    for path in root.rglob("*"):
        if any(part in skip_parts for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if path.is_dir() and path.name == "__pycache__":
            children = list(path.iterdir())
            if not children or any(not _is_runtime_bytecode_name(child.name) for child in children):
                hits.append(rel)
            continue
        if not path.is_file():
            continue
        name = path.name
        suffix = path.suffix.lower()
        if name == "publication-probe.pyc":
            hits.append(rel)
            continue
        if suffix in blocked_suffixes and not (
            "__pycache__" in path.parts and _is_runtime_bytecode_name(name)
        ):
            hits.append(rel)
    return hits


def test_plugin_tree_rejects_publication_binaries():
    hits = _publication_binary_hits(PLUGIN_ROOT)
    assert hits == [], "publication binaries in plugin tree:\n" + "\n".join(hits)


def test_pycache_directory_cannot_ship_in_plugin_tree(tmp_path):
    plugin = tmp_path / "plugin"
    cache = plugin / "skills" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "hidden.pyc").write_bytes(b"\0")
    hits = _publication_binary_hits(plugin)
    assert any(part == "__pycache__" or "/__pycache__/" in part or part.endswith("/__pycache__") for part in hits), hits


def test_license_has_neutral_copyright():
    path = PLUGIN_ROOT / "LICENSE"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Copyright (c) 2026 Lumen contributors" in text


def test_readme_has_no_internal_paths_or_cos_hermes_refs():
    path = PLUGIN_ROOT / "README.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "/root/" not in text
    lowered = text.lower()
    for needle in FORBIDDEN:
        assert needle.lower() not in lowered, f"hermes CoS-internal reference in README: {needle}"


def test_curated_pages_roundtrip_source_id(tmp_path):
    scripts = PLUGIN_ROOT / "skills" / "curator" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import wiki_curator

    wiki = tmp_path / "wiki"
    wiki.mkdir()
    source_id = "src-roundtrip-42"
    item = wiki_curator.SourceItem(
        source_id=source_id,
        source_kind="memory",
        title="Roundtrip title",
        text="Roundtrip body about Dana",
        timestamp=datetime.now(timezone.utc),
        people=["Dana"],
    )
    curator = wiki_curator.WikiCurator(
        {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
    )
    curator.curate_items([item])
    marker = f"[source: {source_id}]"
    hits = []
    for path in wiki.rglob("*.md"):
        if path.is_file() and marker in path.read_text(encoding="utf-8"):
            hits.append(path.relative_to(wiki).as_posix())
    assert hits, f"expected source marker {marker!r} on generated pages"
    assert any(name.startswith("people/") for name in hits)
    assert any(name.startswith("daily/") for name in hits)
