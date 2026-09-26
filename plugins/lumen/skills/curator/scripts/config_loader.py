#!/usr/bin/env python3
"""Load Lumen plugin configuration from ``shared/config/lumen.yaml``.

Resolution order for the config file:
1. Explicit ``--config`` path passed to :func:`load_config`
2. ``LUMEN_CONFIG`` environment variable
3. ``<plugin_root>/shared/config/lumen.yaml``

Wiki path resolution (after the file is loaded):
1. ``paths.wiki_path`` in the config
2. ``WIKI_PATH`` environment variable
3. ``~/wiki``
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Mapping

try:
    import yaml
except Exception:  # pragma: no cover - PyYAML is required in practice
    yaml = None


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = PLUGIN_ROOT / "shared" / "config" / "lumen.yaml"

DEFAULT_TIMEZONE = "Asia/Singapore"
DEFAULT_MAX_WRITE_PAGES = 20
DEFAULT_MEMORY_SOURCE = "auto"
VALID_MEMORY_SOURCES = frozenset({"auto", "json-file", "mnemosyne", "none"})


class ConfigError(Exception):
    """Raised when an explicitly selected config file cannot be used."""

    def __init__(self, path: Path | str, reason: str) -> None:
        self.path = str(path)
        self.reason = reason
        super().__init__(f"{self.path}: {reason}")


def default_wiki_path() -> Path:
    env = os.environ.get("WIKI_PATH", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / "wiki"


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _config_is_explicit(config_path: str | os.PathLike[str] | None) -> bool:
    if config_path:
        return True
    return bool(os.environ.get("LUMEN_CONFIG", "").strip())


def _yaml_parse_reason(exc: BaseException) -> str:
    mark = getattr(exc, "problem_mark", None)
    line = getattr(mark, "line", None)
    column = getattr(mark, "column", None)
    if isinstance(line, int) and isinstance(column, int):
        return f"yaml parse error at line {line + 1} column {column + 1}"
    return "yaml parse error"


def _emit_config_issue(path: Path, reason: str, explicit: bool) -> None:
    if explicit:
        raise ConfigError(path, reason)
    print(f"warning: {path}: {reason}; using defaults", file=sys.stderr)


def _is_pathish_key(key: str) -> bool:
    name = str(key)
    return name in {"wiki_path", "wiki_dir"} or name.endswith("_path") or name.endswith("_dir")


def _is_valid_path_value(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    try:
        text = os.fspath(value)
    except TypeError:
        return False
    return isinstance(text, str) and bool(text.strip())


def _validate_path_values(paths: Mapping[str, Any], source_path: Path) -> None:
    for key, value in paths.items():
        if not _is_pathish_key(str(key)):
            continue
        if value is None or value == "":
            continue
        if not _is_valid_path_value(value):
            raise ConfigError(source_path, f"paths.{key} is not a path string")


def _is_int_like(value: Any) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return False
        try:
            int(text)
            return True
        except ValueError:
            return False
    return False


def _section_mapping(
    raw: Mapping[str, Any], key: str, path: Path, explicit: bool
) -> dict[str, Any]:
    if key not in raw:
        return {}
    value = raw[key]
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    _emit_config_issue(path, f"{key} is not a mapping", explicit)
    return {}


def _merge_defaults(
    data: Mapping[str, Any] | None,
    *,
    source_path: Path,
    explicit: bool,
) -> dict[str, Any]:
    raw = _as_mapping(data)
    paths = _section_mapping(raw, "paths", source_path, explicit)
    curator = _section_mapping(raw, "curator", source_path, explicit)
    _validate_path_values(paths, source_path)

    wiki_raw = paths.get("wiki_path")
    if wiki_raw in (None, ""):
        wiki_path = str(default_wiki_path())
    else:
        wiki_path = os.fspath(wiki_raw) if not isinstance(wiki_raw, str) else wiki_raw

    merged_paths = dict(paths)
    merged_paths["wiki_path"] = wiki_path

    max_write = curator.get("max_write_pages", DEFAULT_MAX_WRITE_PAGES)
    if "max_write_pages" in curator and not _is_int_like(curator.get("max_write_pages")):
        _emit_config_issue(source_path, "curator.max_write_pages is not int-like", explicit)
        max_write = DEFAULT_MAX_WRITE_PAGES

    memory_source = curator.get("memory_source") or DEFAULT_MEMORY_SOURCE
    if curator.get("memory_source") not in (None, ""):
        memory_source = str(curator.get("memory_source")).strip().lower()
        if memory_source not in VALID_MEMORY_SOURCES:
            _emit_config_issue(
                source_path,
                "curator.memory_source must be one of auto, json-file, mnemosyne, none",
                explicit,
            )
            memory_source = DEFAULT_MEMORY_SOURCE

    merged_curator = {
        "timezone": curator.get("timezone") or DEFAULT_TIMEZONE,
        "max_write_pages": max_write,
        "memory_source": memory_source,
    }
    for key, value in curator.items():
        merged_curator.setdefault(key, value)

    result = dict(raw)
    result["paths"] = merged_paths
    result["curator"] = merged_curator
    return result


def _read_yaml(path: Path, *, explicit: bool = False) -> dict[str, Any]:
    if not path.is_file():
        if explicit:
            raise ConfigError(path, "missing or unreadable")
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        _emit_config_issue(path, "invalid UTF-8", explicit)
        return {}
    except OSError:
        if explicit:
            raise ConfigError(path, "missing or unreadable")
        _emit_config_issue(path, "unreadable", explicit)
        return {}
    if yaml is None:
        _emit_config_issue(path, "PyYAML is not available", explicit)
        return {}
    try:
        loaded = yaml.safe_load(text)
    except Exception as exc:
        _emit_config_issue(path, _yaml_parse_reason(exc), explicit)
        return {}
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, Mapping):
        _emit_config_issue(path, "not a mapping", explicit)
        return {}
    return loaded


def resolve_config_path(config_path: str | os.PathLike[str] | None = None) -> Path:
    if config_path:
        return Path(str(config_path)).expanduser()
    env = os.environ.get("LUMEN_CONFIG", "").strip()
    if env:
        return Path(env).expanduser()
    return DEFAULT_CONFIG_PATH


def load_config(config_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    explicit = _config_is_explicit(config_path)
    path = resolve_config_path(config_path)
    data = _read_yaml(path, explicit=explicit)
    merged = _merge_defaults(data, source_path=path, explicit=explicit)
    merged["_source_path"] = str(path)
    return merged


def get_wiki_path(config: Mapping[str, Any] | None = None) -> Path:
    cfg = config if isinstance(config, Mapping) else {}
    paths = _as_mapping(cfg.get("paths"))
    raw = paths.get("wiki_path")
    if raw in (None, ""):
        path = default_wiki_path()
    elif not _is_valid_path_value(raw):
        source = cfg.get("_source_path") or "paths.wiki_path"
        raise ConfigError(source, "paths.wiki_path is not a path string")
    else:
        text = raw if isinstance(raw, str) else os.fspath(raw)
        path = Path(text).expanduser()
    return path.resolve()


def get_timezone(config: Mapping[str, Any] | None = None) -> str:
    cfg = config if isinstance(config, Mapping) else {}
    curator = _as_mapping(cfg.get("curator"))
    tz = curator.get("timezone")
    if tz:
        return str(tz)
    return DEFAULT_TIMEZONE


def get_memory_source(config: Mapping[str, Any] | None = None) -> str:
    cfg = config if isinstance(config, Mapping) else {}
    curator = _as_mapping(cfg.get("curator"))
    raw = curator.get("memory_source") or DEFAULT_MEMORY_SOURCE
    return str(raw).strip().lower() or DEFAULT_MEMORY_SOURCE


def get_max_write_pages(config: Mapping[str, Any] | None = None) -> int:
    """Return the ingest cap. 0 or negative disables the cap."""

    cfg = config if isinstance(config, Mapping) else {}
    curator = _as_mapping(cfg.get("curator"))
    value = curator.get("max_write_pages", DEFAULT_MAX_WRITE_PAGES)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_WRITE_PAGES
    return 0 if parsed <= 0 else parsed
