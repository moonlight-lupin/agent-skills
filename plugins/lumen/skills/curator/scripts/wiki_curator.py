#!/usr/bin/env python3
"""Autonomous wiki curator for the Lumen plugin.

The curator is intentionally conservative: it reads a configured memory source
through the adapter layer, then writes only inside the configured wiki
directory. It never calls providers, approves actions, deletes pages, merges
pages, removes sources, or changes operator-confirmed facts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml


SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from config_loader import ConfigError, get_max_write_pages, get_timezone, get_wiki_path, load_config
except Exception:  # pragma: no cover - degrade when the local loader is absent.
    class ConfigError(Exception):
        pass

    get_max_write_pages = None  # type: ignore[assignment]
    get_timezone = None  # type: ignore[assignment]
    get_wiki_path = None  # type: ignore[assignment]
    load_config = None  # type: ignore[assignment]


WIKI_DIRS = ("raw", "daily", "projects", "entities", "people", "decisions")
SEARCH_DIRS = ("entities", "concepts", "comparisons", "queries", "people", "projects", "decisions")
SEARCH_SKIP_NAMES = {"index.md", "overview.md", "SCHEMA.md", "purpose.md", "log.md"}
MANAGED_ROOT_FILES = {"index.md", "overview.md"}
AUTO_BLOCK_START = "<!-- lumen:auto:start -->"
AUTO_BLOCK_END = "<!-- lumen:auto:end -->"
SPECIAL_ROOT_FILES = {"index.md", "overview.md", "log.md", "purpose.md", "SCHEMA.md"}
REGEN_EXCLUDE_DIR_NAMES = {".lumen"}
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
TEXT_FIELDS = ("summary", "text", "content", "body", "note", "notes", "description", "title", "value")
TIME_FIELDS = ("received_at", "created_at", "updated_at", "timestamp", "time", "date", "ts")
SECTION_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
SOURCE_MARK_RE = re.compile(r"\[source:\s*([^\]]+?)\]")
_ORDERED_LIST_RE = re.compile(r"^\d+\.\s")
ENTITY_PAGE_DIRS = {"entities", "people", "projects", "decisions"}
GENERATED_SECTION_HEADINGS = frozenset({"source-backed observations", "recent activity"})
_CONFIDENCE_LABELS = {
    "high": 1.0,
    "medium": 0.5,
    "low": 0.0,
    "confirmed": 1.0,
    "unverified": 0.0,
}


@dataclass
class SourceItem:
    """Normalized memory/event record used by the curator."""

    source_id: str
    source_kind: str
    title: str
    text: str
    timestamp: datetime
    tags: list[str] = field(default_factory=list)
    people: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def day(self) -> str:
        return self.timestamp.date().isoformat()


@dataclass
class Change:
    action: str
    path: Path
    detail: str


@dataclass
class Finding:
    severity: str
    path: str
    message: str


# ─── General helpers ────────────────────────────────────────────────


def parse_since(value: str) -> timedelta:
    """Parse durations such as ``24h``, ``7d``, or ``90m``."""

    match = re.fullmatch(r"\s*(\d+)\s*([mhdw])\s*", value.lower())
    if not match:
        raise argparse.ArgumentTypeError(f"invalid duration {value!r}; use e.g. 90m, 24h, 7d, or 2w")
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    return timedelta(weeks=amount)


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


_SOURCE_TOKEN_RE = re.compile(r"\[(\s*source)\s*:", re.IGNORECASE)
_NAME_UNSAFE_RE = re.compile(r"[\[\]|#]+")


def _sanitize_inline(value: Any) -> str:
    """Render untrusted memory text safe for a single Markdown line.

    Collapses whitespace (no newlines, so no forged ``## `` sections), escapes
    a leading ``#`` and neutralises ``[source:`` / ``[[`` so record text cannot
    forge curator source markers or wikilinks.
    """

    text = re.sub(r"\s+", " ", _safe_str(value)).strip()
    text = _SOURCE_TOKEN_RE.sub(lambda match: f"[{match.group(1).strip()}\\:", text)
    while "[[" in text:
        text = text.replace("[[", "[\\[")
    if text.startswith("#"):
        text = f"\\{text}"
    return text


def _sanitize_name(value: Any) -> str:
    """Sanitise an untrusted person/project/entity name used as a title and wikilink."""

    return re.sub(r"\s+", " ", _NAME_UNSAFE_RE.sub(" ", _safe_str(value))).strip()


def _sanitize_item(item: "SourceItem") -> "SourceItem":
    return replace(
        item,
        title=_sanitize_inline(item.title),
        text=_sanitize_inline(item.text),
        people=_unique(_sanitize_name(name) for name in item.people),
        projects=_unique(_sanitize_name(name) for name in item.projects),
        entities=_unique(_sanitize_name(name) for name in item.entities),
    )


def _unique(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _safe_str(value)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return sorted(value, key=str)
    if isinstance(value, str):
        if not value.strip():
            return []
        if "," in value:
            return [part.strip() for part in value.split(",") if part.strip()]
        return [value.strip()]
    return [value]


def _slugify(title: str) -> str:
    """ASCII page slug: accents are folded (``Zoë`` -> ``zoe``); names with no
    ASCII letters/digits get a stable ``untitled-<sha256[:8]>`` so distinct
    names never share a page."""

    folded = "".join(
        ch for ch in unicodedata.normalize("NFKD", title) if not unicodedata.combining(ch)
    )
    slug = re.sub(r"[^a-z0-9]+", "-", folded.lower()).strip("-")
    if slug:
        return slug
    name = title.strip()
    if not name:
        return "untitled"
    return f"untitled-{hashlib.sha256(name.encode('utf-8')).hexdigest()[:8]}"


def _frontmatter_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool, date, datetime)) or value is None:
        return value
    if isinstance(value, list):
        return [_frontmatter_value(item) for item in value]
    if isinstance(value, tuple):
        return [_frontmatter_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(k): _frontmatter_value(v) for k, v in value.items()}
    return str(value)


def _dump_frontmatter(data: Mapping[str, Any]) -> str:
    plain = {str(k): _frontmatter_value(v) for k, v in data.items()}
    return yaml.safe_dump(plain, sort_keys=False, allow_unicode=True).strip()


def _parse_datetime(value: Any, default_tz: tzinfo) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        dt = datetime(value.year, value.month, value.day)
    else:
        text = _safe_str(value)
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    continue
            else:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz)
    return dt


def _now(config: Mapping[str, Any] | None = None) -> datetime:
    tz_name = "Asia/Singapore"
    try:
        if get_timezone is not None:
            tz_name = get_timezone(config) or tz_name
        else:
            curator = config.get("curator", {}) if isinstance(config, Mapping) else {}
            if isinstance(curator, Mapping) and curator.get("timezone"):
                tz_name = _safe_str(curator.get("timezone"), tz_name) or tz_name
        return datetime.now(ZoneInfo(tz_name))
    except (ZoneInfoNotFoundError, Exception):
        return datetime.now(timezone.utc)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _looks_like_record(value: Mapping[str, Any]) -> bool:
    return any(key in value and value.get(key) not in (None, "", []) for key in TEXT_FIELDS + TIME_FIELDS)


def _iter_record_mappings(data: Any) -> Iterable[Mapping[str, Any]]:
    """Yield plausible records from common list/dict memory-store shapes."""

    if isinstance(data, list):
        for item in data:
            if isinstance(item, Mapping):
                yield item
        return
    if not isinstance(data, Mapping):
        return

    for key in ("memories", "memory", "items", "records", "entries", "facts", "observations"):
        child = data.get(key)
        if isinstance(child, list):
            for item in child:
                if isinstance(item, Mapping):
                    yield item
            return
        if isinstance(child, Mapping):
            for item_key, item in child.items():
                if isinstance(item, Mapping):
                    merged = dict(item)
                    merged.setdefault("id", item_key)
                    yield merged
            return

    if _looks_like_record(data):
        yield data
        return

    for item_key, item in data.items():
        if isinstance(item, Mapping):
            merged = dict(item)
            merged.setdefault("id", item_key)
            if _looks_like_record(merged):
                yield merged
        elif isinstance(item, list):
            for record in item:
                if isinstance(record, Mapping):
                    yield record


def _extract_text(record: Mapping[str, Any]) -> tuple[str, str]:
    title = _safe_str(record.get("title") or record.get("name") or record.get("summary"), "Untitled")
    pieces: list[str] = []
    for field_name in TEXT_FIELDS:
        value = record.get(field_name)
        text = _safe_str(value)
        if text and text not in pieces:
            pieces.append(text)
    if not pieces:
        pieces.append(title)
    text = " — ".join(pieces)
    return title[:160], text[:1200]


def _record_timestamp(record: Mapping[str, Any], default: datetime) -> datetime:
    for field_name in TIME_FIELDS:
        parsed = _parse_datetime(record.get(field_name), default.tzinfo or timezone.utc)
        if parsed is not None:
            return parsed
    return default


def _extract_named_values(record: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    values: list[Any] = []
    for key in keys:
        if key in record:
            values.extend(_as_list(record.get(key)))
    return _unique(_normalise_name(v) for v in values)


def _normalise_name(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("name", "display_name", "email", "title", "company", "organization"):
            text = _safe_str(value.get(key))
            if text:
                return text
        return _safe_str(value)
    return _safe_str(value)


def _heuristic_entities(text: str) -> list[str]:
    """Extract a small set of likely proper-name entities without over-filing."""

    candidates = re.findall(r"\b(?:[A-Z][A-Za-z0-9&.'-]+)(?:\s+(?:[A-Z][A-Za-z0-9&.'-]+)){0,3}\b", text)
    stop = {
        "Draft",
        "Current",
        "Source",
        "Sources",
        "Recent",
        "Activity",
        "Open",
        "Questions",
        "The",
        "This",
        "Email",
        "Calendar",
        "Deadline",
        "Document",
    }
    filtered = [c.strip(" .,:;()[]") for c in candidates if c.strip(" .,:;()[]") not in stop]
    return _unique(filtered)[:5]


def _normalise_source_id(prefix: str, record: Mapping[str, Any], ordinal: int) -> str:
    for key in ("id", "event_id", "source_id", "key", "uuid"):
        text = _safe_str(record.get(key))
        if text:
            return re.sub(r"[^A-Za-z0-9_.:-]+", "_", text)[:120]
    seed = _safe_str(record)[:80]
    return f"{prefix}_{ordinal}_{abs(hash(seed)) % 1_000_000}"


# ─── Config and paths ────────────────────────────────────────────────


def _load_configuration(config_path: str | None) -> Mapping[str, Any]:
    if load_config is not None:
        loaded = load_config(config_path)  # type: ignore[misc]
        if loaded is not None:
            return loaded
    wiki = os.getenv("WIKI_PATH") or str(Path.home() / "wiki")
    return {
        "paths": {"wiki_path": wiki},
        "curator": {
            "timezone": "Asia/Singapore",
            "max_write_pages": 20,
            "memory_source": "auto",
        },
    }


def _wiki_path(config: Mapping[str, Any]) -> Path:
    if get_wiki_path is not None:
        return Path(get_wiki_path(config)).expanduser().resolve()
    paths = config.get("paths", {}) if isinstance(config, Mapping) else {}
    raw = paths.get("wiki_path") if isinstance(paths, Mapping) else None
    if raw in (None, ""):
        env = os.getenv("WIKI_PATH")
        if env:
            return Path(env).expanduser().resolve()
        return (Path.home() / "wiki").resolve()
    if isinstance(raw, bool) or not isinstance(raw, (str, os.PathLike)):
        raise ConfigError("paths.wiki_path", "paths.wiki_path is not a path string")
    text = raw if isinstance(raw, str) else os.fspath(raw)
    if not str(text).strip():
        raise ConfigError("paths.wiki_path", "paths.wiki_path is not a path string")
    return Path(text).expanduser().resolve()


def _excluded_from_regen(path: Path, wiki_path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(wiki_path.resolve())
    except ValueError:
        return True
    if any(part in REGEN_EXCLUDE_DIR_NAMES for part in rel.parts):
        return True
    cursor = path
    wiki = wiki_path.resolve()
    for _ in range(len(path.parts) + 1):
        if cursor.is_symlink():
            return True
        try:
            if cursor.resolve() == wiki:
                break
        except OSError:
            return True
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    return False


def _existing_nodes_trusted(target: Path, wiki_path: Path) -> bool:
    wiki = wiki_path.resolve()
    cursor = target
    for _ in range(len(target.parts) + 2):
        if cursor.is_symlink():
            return False
        if cursor.exists() and not cursor.is_dir():
            return False
        if cursor.exists():
            try:
                cursor.resolve().relative_to(wiki)
            except ValueError:
                return False
        try:
            resolved = cursor.resolve()
        except OSError:
            return False
        if resolved == wiki and not cursor.is_symlink():
            return True
        if cursor.parent == cursor:
            return False
        cursor = cursor.parent
    return False


def _is_markdown_block_start(line: str) -> bool:
    stripped = line.lstrip()
    return (
        stripped.startswith("#")
        or stripped.startswith("- ")
        or stripped.startswith("* ")
        or stripped.startswith("+ ")
        or _ORDERED_LIST_RE.match(stripped) is not None
    )


def _is_section_heading(line: str) -> bool:
    return SECTION_RE.match(line) is not None


def _is_generated_observation_start(line: str) -> bool:
    return line.lstrip().startswith("- [")


def _carries_different_source_marker(line: str, source_id: str) -> bool:
    return any(match.group(1).strip() != source_id for match in SOURCE_MARK_RE.finditer(line))


def _generated_section_line_ranges(lines: Sequence[str]) -> list[tuple[int, int]]:
    """Return [start, end) line ranges for generated section bodies (not the heading)."""

    headings: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = SECTION_RE.match(line)
        if match:
            headings.append((index, match.group(1).strip().casefold()))
    ranges: list[tuple[int, int]] = []
    for index, (line_no, heading) in enumerate(headings):
        if heading not in GENERATED_SECTION_HEADINGS:
            continue
        start = line_no + 1
        end = headings[index + 1][0] if index + 1 < len(headings) else len(lines)
        ranges.append((start, end))
    return ranges


def _span_within_any_range(start: int, end: int, ranges: Sequence[tuple[int, int]]) -> bool:
    return any(gen_start <= start and end <= gen_end for gen_start, gen_end in ranges)


def _line_in_ranges(index: int, ranges: Sequence[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in ranges)


def _source_ids_in_generated_sections(text: str) -> set[str]:
    _frontmatter, body, valid = split_frontmatter(text)
    payload = body if valid else text
    lines = payload.splitlines()
    found: set[str] = set()
    for start, end in _generated_section_line_ranges(lines):
        for line in lines[start:end]:
            for match in SOURCE_MARK_RE.finditer(line):
                source_id = match.group(1).strip()
                if source_id:
                    found.add(source_id)
    return found


def _unmarked_generated_observation_start(line: str) -> bool:
    """True for a curator `- [` observation bullet that does not yet carry a source marker."""

    if not _is_generated_observation_start(line):
        return False
    return SOURCE_MARK_RE.search(line) is None


def _attributed_block_spans(lines: Sequence[str], source_id: str) -> list[tuple[int, int]]:
    """Return [start, end) spans for one generated observation attributed to source_id.

    A generated observation starts at the unmarked ``- [`` bullet (see
    ``_append_bullets``) and ends on the line that carries ``[source: id]``.
    Marker-less hand-authored paragraphs are never absorbed in either
    direction. Blank lines and nested block-starts *between* that bullet and
    the marker stay inside the observation.
    """

    marker = f"[source: {source_id}]"
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(lines):
        if marker not in lines[index]:
            index += 1
            continue
        start = index
        cursor = index - 1
        while cursor >= 0:
            previous = lines[cursor]
            if _is_section_heading(previous):
                break
            if _carries_different_source_marker(previous, source_id):
                break
            if _is_generated_observation_start(previous):
                if not _unmarked_generated_observation_start(previous):
                    break
                start = cursor
                break
            cursor -= 1
        # The marker is the last line of the generated observation. Do not
        # absorb following marker-less paragraphs, operator notes, or blanks
        # that delimit unrelated hand-authored content.
        end = index + 1
        spans.append((start, end))
        index = end
    return spans


def _join_attributed_blocks(text: str, source_id: str) -> str:
    lines = text.splitlines()
    return "\n".join(
        "\n".join(lines[start:end]) for start, end in _attributed_block_spans(lines, source_id)
    )


def _with_wiki_override(config: Mapping[str, Any], wiki: str | None) -> Mapping[str, Any]:
    """Return a copy of config with paths.wiki_path overridden when ``wiki`` is set."""

    if not wiki:
        return config
    updated = dict(config)
    paths = updated.get("paths")
    paths_dict = dict(paths) if isinstance(paths, Mapping) else {}
    paths_dict["wiki_path"] = wiki
    updated["paths"] = paths_dict
    return updated


def _assert_under_wiki(path: Path, wiki_path: Path) -> None:
    resolved_parent = path.parent.resolve()
    resolved_wiki = wiki_path.resolve()
    if resolved_parent != resolved_wiki and resolved_wiki not in resolved_parent.parents:
        raise ValueError(f"Refusing to write outside wiki directory: {path}")


def _read_umask() -> int:
    current = os.umask(0)
    os.umask(current)
    return current


# Read once at import: os.umask can only be read by setting it.
_UMASK = _read_umask()


def _target_mode(path: Path) -> int:
    """Mode for a rewritten file: keep an existing file's mode, else 0o666 & ~umask.

    ``mkstemp`` creates 0600 files and ``os.replace`` keeps that mode, which
    would otherwise tighten every page the curator touches.
    """

    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        return 0o666 & ~_UMASK


def _atomic_write(path: Path, content: str, wiki_path: Path) -> None:
    _assert_under_wiki(path, wiki_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = _target_mode(path)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            if content and not content.endswith("\n"):
                handle.write("\n")
        os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


# ─── Frontmatter and section editing ────────────────────────────────


def _replace_auto_block(body: str, block: str) -> str:
    """Replace the first ``lumen:auto`` block in body, or append one when absent."""

    start = body.find(AUTO_BLOCK_START)
    end = body.find(AUTO_BLOCK_END, start + len(AUTO_BLOCK_START)) if start != -1 else -1
    if start != -1 and end != -1:
        return body[:start] + block + body[end + len(AUTO_BLOCK_END) :]
    prefix = body.rstrip()
    return f"{prefix}\n\n{block}\n" if prefix else f"{block}\n"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str, bool]:
    if not text.startswith("---\n"):
        return {}, text, False
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text, False
    raw = text[4:end]
    body = text[end + len("\n---") :].lstrip("\n")
    try:
        data = yaml.safe_load(raw) or {}
        if not isinstance(data, dict):
            return {}, body, False
        return data, body, True
    except yaml.YAMLError:
        return {}, body, False


def join_frontmatter(frontmatter: Mapping[str, Any], body: str) -> str:
    return f"---\n{_dump_frontmatter(frontmatter)}\n---\n\n{body.strip()}\n"


def _section_bounds(body: str, heading: str) -> tuple[int, int] | None:
    target = heading.strip().casefold()
    matches = list(SECTION_RE.finditer(body))
    for index, match in enumerate(matches):
        if match.group(1).strip().casefold() == target:
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            return start, end
    return None


def ensure_section(body: str, heading: str, default: str = "(None yet)") -> str:
    if _section_bounds(body, heading) is not None:
        return body
    return f"{body.rstrip()}\n\n## {heading}\n\n{default}\n"


def _append_bullets(body: str, heading: str, bullets: Sequence[str]) -> tuple[str, bool]:
    if not bullets:
        return body, False
    body = ensure_section(body, heading)
    bounds = _section_bounds(body, heading)
    if bounds is None:
        return body, False
    start, end = bounds
    section = body[start:end].strip("\n")
    lines = [] if section.strip() == "(None yet)" else section.splitlines()
    changed = False
    existing = "\n".join(lines)
    for bullet in bullets:
        bullet = bullet.strip()
        if not bullet:
            continue
        if not bullet.startswith("- "):
            bullet = f"- {bullet}"
        if bullet in existing:
            continue
        lines.append(bullet)
        existing += f"\n{bullet}"
        changed = True
    replacement = "\n\n" + ("\n".join(lines).strip() if lines else "(None yet)") + "\n\n"
    return body[:start] + replacement + body[end:], changed


def _set_section_text(body: str, heading: str, text: str) -> tuple[str, bool]:
    body = ensure_section(body, heading)
    bounds = _section_bounds(body, heading)
    if bounds is None:
        return body, False
    start, end = bounds
    replacement = f"\n\n{text.strip()}\n\n"
    if body[start:end] == replacement:
        return body, False
    return body[:start] + replacement + body[end:], True


def _confidence_as_float(value: Any) -> float | None:
    """Interpret confidence as a 0-1 float. Numeric values take precedence over labels."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    text = _safe_str(value).casefold()
    if not text:
        return None
    if text in _CONFIDENCE_LABELS:
        return _CONFIDENCE_LABELS[text]
    try:
        return max(0.0, min(1.0, float(text)))
    except ValueError:
        return None


def _normalise_confidence(value: Any, default: float = 0.5) -> Any:
    """Accept 0-1 floats and high/medium/low labels. Preserve existing labels."""

    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    text = _safe_str(value)
    if text.casefold() in _CONFIDENCE_LABELS:
        return text
    parsed = _confidence_as_float(value)
    return default if parsed is None else parsed


def _merge_frontmatter(existing: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in updates.items():
        if key in {"tags", "sources", "aliases"}:
            merged[key] = _unique(_as_list(merged.get(key)) + _as_list(value))
        elif key in {"status", "confidence", "seq", "title", "created"} and merged.get(key) not in (None, ""):
            continue
        else:
            merged[key] = value
    return merged


# ─── Source loading ─────────────────────────────────────────────────


def load_memory_items(wiki_path: Path, cutoff: datetime, default_now: datetime) -> list[SourceItem]:
    """Load memory.json through the json-file adapter (wiki_path/.knowledge)."""

    from adapters import JsonFileAdapter

    return JsonFileAdapter(wiki_path=wiki_path).load_items(cutoff, default_now)


def _load_adapter_items(config: Mapping[str, Any], wiki_path: Path, cutoff: datetime, now: datetime) -> list[SourceItem]:
    from adapters import get_adapter

    adapter = get_adapter(config, wiki_path=wiki_path)
    items = list(adapter.load_items(cutoff, now))
    items.sort(key=lambda item: item.timestamp)
    return items


# ─── Wiki curator ───────────────────────────────────────────────────


class WikiCurator:
    def __init__(self, config: Mapping[str, Any], dry_run: bool = False) -> None:
        self.config = config
        self.wiki_path = _wiki_path(config)
        self.dry_run = dry_run
        self.now = _now(config)
        self.today = self.now.date().isoformat()
        self.changes: list[Change] = []
        self._seq_max: dict[str, int] = {}
        # Sources whose pages were skipped this run (not marked processed, so
        # they are retried once the page is repaired).
        self._skipped_sources: set[str] = set()
        if get_max_write_pages is not None:
            self.max_write_pages = get_max_write_pages(config)
        else:
            curator_cfg = config.get("curator", {}) if isinstance(config, Mapping) else {}
            try:
                value = int(curator_cfg.get("max_write_pages", 20)) if isinstance(curator_cfg, Mapping) else 20
            except (TypeError, ValueError):
                value = 20
            self.max_write_pages = max(0, value)

    def _relative(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.wiki_path.resolve()).as_posix()
        except ValueError:
            return str(path)

    def ensure_dirs(self) -> None:
        if self.dry_run:
            return
        self.wiki_path.mkdir(parents=True, exist_ok=True)
        for name in WIKI_DIRS:
            path = self.wiki_path / name
            _assert_under_wiki(path / ".keep", self.wiki_path)
            path.mkdir(parents=True, exist_ok=True)

    def maybe_write(self, path: Path, content: str, action: str, detail: str) -> None:
        _assert_under_wiki(path, self.wiki_path)
        old = None
        try:
            old = path.read_text(encoding="utf-8")
        except OSError:
            pass
        normalized = content if content.endswith("\n") else f"{content}\n"
        if old == normalized:
            return
        self.changes.append(Change(action=action, path=path, detail=detail))
        if not self.dry_run:
            _atomic_write(path, normalized, self.wiki_path)

    def _next_seq(self, page_type: str) -> int:
        """Assign the next monotonic seq for pages of the same type."""

        if page_type not in self._seq_max:
            max_seq = 0
            for path in self.all_markdown_pages():
                frontmatter, _body, _title = self._page_summary(path)
                if _safe_str(frontmatter.get("type")) != page_type:
                    continue
                try:
                    seq = int(frontmatter.get("seq"))
                except (TypeError, ValueError):
                    continue
                if seq > max_seq:
                    max_seq = seq
            self._seq_max[page_type] = max_seq
        self._seq_max[page_type] += 1
        return self._seq_max[page_type]

    def page_path(self, page_type: str, title: str) -> Path:
        folder = {"person": "people", "project": "projects", "entity": "entities", "decision": "decisions", "daily": "daily"}.get(page_type, "entities")
        if page_type == "daily":
            return self.wiki_path / folder / f"{title}.md"
        return self.wiki_path / folder / f"{_slugify(title)}.md"

    def _new_page_body(self, title: str, observation: str | None = None, activity: str | None = None, sources: Sequence[str] = ()) -> str:
        source_bullets = "\n".join(f"- {source}" for source in _unique(sources)) or "(None yet)"
        observations = observation or "(None yet)"
        if observation and not observation.startswith("-"):
            observations = f"- {observation}"
        activities = activity or "(None yet)"
        if activity and not activity.startswith("-"):
            activities = f"- {activity}"
        return f"""# {title}

## Current summary

(Draft — auto-generated)

## Operator-confirmed facts

(None yet)

## Source-backed observations

{observations}

## Recent activity

{activities}

## Open questions

(None yet)

## Related pages

(None yet)

## Sources

{source_bullets}

## Last updated

{self.now.isoformat()}
"""

    def _skip_malformed_page(self, path: Path, old: str, valid: bool, source_id: str) -> bool:
        """Refuse to rewrite a page whose YAML frontmatter block does not parse.

        Rewriting would replace the author's frontmatter with fresh defaults, so
        the page is left byte-for-byte unchanged and reported for manual repair.
        """

        if valid or not old.startswith("---\n"):
            return False
        detail = f"malformed YAML frontmatter; page left unchanged (source {source_id}) — fix it by hand"
        print(f"warning: {self._relative(path)}: {detail}", file=sys.stderr)
        self.changes.append(Change("skip", path, detail))
        self._skipped_sources.add(source_id)
        return True

    def upsert_page(
        self,
        page_type: str,
        title: str,
        item: SourceItem,
        extra_tags: Sequence[str] = (),
        related_titles: Sequence[str] = (),
    ) -> None:
        path = self.page_path(page_type, title)
        source_ref = item.source_id
        day = item.day
        observation_text = _safe_str(item.text or item.title)[:600]
        observation = f"[{day}] {observation_text} [source: {source_ref}]"
        activity = f"[{day}] Mentioned in {item.source_kind}: {item.title} [source: {source_ref}]"
        tags = _unique([page_type, item.source_kind, *item.tags, *extra_tags])
        is_new = not path.exists()
        if is_new:
            frontmatter = {}
            body = self._new_page_body(title, observation=observation, activity=activity, sources=[source_ref])
        else:
            old = path.read_text(encoding="utf-8")
            frontmatter, body, valid = split_frontmatter(old)
            if self._skip_malformed_page(path, old, valid, source_ref):
                return
        updates = {
            "type": page_type,
            "title": title,
            "created": _safe_str(frontmatter.get("created"), day),
            "updated": self.today,
            "tags": tags,
            "sources": [source_ref],
            "status": "draft",
            "confidence": _normalise_confidence(frontmatter.get("confidence"), 0.5),
            "last_seen": self.now.isoformat(),
        }
        if is_new:
            updates["seq"] = self._next_seq(page_type)
            updates["relations"] = []
            if page_type == "entity":
                updates["aliases"] = []
        merged = _merge_frontmatter(frontmatter, updates)
        body = ensure_section(body, "Operator-confirmed facts")
        body, _ = _append_bullets(body, "Source-backed observations", [observation])
        body, _ = _append_bullets(body, "Recent activity", [activity])
        body, _ = _append_bullets(body, "Sources", [source_ref])
        related = [f"[[{related}]]" for related in related_titles if related and related != title]
        if item.day:
            related.append(f"[[{item.day}]]")
        body, _ = _append_bullets(body, "Related pages", related)
        body, _ = _set_section_text(body, "Last updated", self.now.isoformat())
        content = join_frontmatter(merged, body)
        action = "create" if not path.exists() else "update"
        self.maybe_write(path, content, action, f"{page_type} page from {source_ref}")

    def upsert_daily_page(self, item: SourceItem, related_titles: Sequence[str]) -> None:
        path = self.page_path("daily", item.day)
        activity = f"[{item.timestamp.strftime('%H:%M')}] {item.title} [source: {item.source_id}]"
        related = [f"[[{title}]]" for title in related_titles if title]
        is_new = not path.exists()
        if is_new:
            frontmatter = {}
            body = self._new_page_body(item.day, activity=activity, sources=[item.source_id])
        else:
            old = path.read_text(encoding="utf-8")
            frontmatter, body, valid = split_frontmatter(old)
            if self._skip_malformed_page(path, old, valid, item.source_id):
                return
        updates = {
            "type": "daily",
            "title": item.day,
            "created": _safe_str(frontmatter.get("created"), item.day),
            "updated": self.today,
            "tags": _unique(["daily", *item.tags]),
            "sources": [item.source_id],
            "status": "draft",
            "confidence": _normalise_confidence(frontmatter.get("confidence"), 0.5),
        }
        if is_new:
            updates["seq"] = self._next_seq("daily")
            updates["relations"] = []
        merged = _merge_frontmatter(frontmatter, updates)
        body, _ = _append_bullets(body, "Recent activity", [activity])
        body, _ = _append_bullets(body, "Related pages", related)
        body, _ = _append_bullets(body, "Sources", [item.source_id])
        body, _ = _set_section_text(body, "Last updated", self.now.isoformat())
        content = join_frontmatter(merged, body)
        action = "create" if not path.exists() else "update"
        self.maybe_write(path, content, action, f"daily log from {item.source_id}")

    def _processed_marker_path(self) -> Path:
        return self.wiki_path / ".lumen" / "processed.json"

    def _load_processed_ids(self) -> set[str]:
        data = _read_json(self._processed_marker_path())
        if isinstance(data, list):
            return {str(item) for item in data if item not in (None, "")}
        if isinstance(data, Mapping):
            raw = data.get("source_ids", data.get("ids", []))
            if isinstance(raw, list):
                return {str(item) for item in raw if item not in (None, "")}
        return set()

    def _source_ids_in_text(self, text: str) -> set[str]:
        found: set[str] = set()
        frontmatter, _body, _valid = split_frontmatter(text)
        for value in _as_list(frontmatter.get("sources")):
            source_id = _safe_str(value)
            if source_id:
                found.add(source_id)
        for match in SOURCE_MARK_RE.finditer(text):
            source_id = match.group(1).strip()
            if source_id:
                found.add(source_id)
        return found

    def _is_entity_like_page(self, path: Path) -> bool:
        try:
            rel = path.resolve().relative_to(self.wiki_path.resolve())
        except ValueError:
            return False
        return bool(rel.parts) and rel.parts[0] in ENTITY_PAGE_DIRS

    def _wiki_link_index(self, pages: Sequence[Path]) -> set[str]:
        names: set[str] = set()
        for path in pages:
            rel = self._relative(path)
            names.add(_normalise_link_target(path.stem))
            names.add(_normalise_link_target(rel))
            if rel.endswith(".md"):
                names.add(_normalise_link_target(rel[:-3]))
            _frontmatter, _body, title = self._page_summary(path)
            if title:
                names.add(_normalise_link_target(title))
        return names

    def _markdown_target_exists(self, from_path: Path, raw: str) -> bool:
        stripped = raw.strip()
        if not stripped:
            return True
        parts = stripped.split()
        if not parts:
            return True
        target = parts[0].strip("<>").split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            return True
        wiki = self.wiki_path.resolve()
        for cand in (from_path.parent / target, self.wiki_path / target):
            try:
                resolved = cand.resolve()
                resolved.relative_to(wiki)
            except (OSError, ValueError):
                continue
            if resolved.is_file():
                return True
        return False

    def _page_link_targets_exist(self, path: Path, text: str, index: set[str]) -> bool:
        wikilinks = WIKILINK_RE.findall(text)
        md_links = MD_LINK_RE.findall(text)
        if not wikilinks and not md_links:
            return False
        for link in wikilinks:
            if _normalise_link_target(link) not in index:
                return False
        for raw in md_links:
            if not self._markdown_target_exists(path, raw):
                return False
        return True

    def _page_supports_source_completion(self, path: Path, text: str, index: set[str]) -> bool:
        wikilinks = WIKILINK_RE.findall(text)
        md_links = MD_LINK_RE.findall(text)
        if not wikilinks and not md_links:
            return self._is_entity_like_page(path)
        for link in wikilinks:
            if _normalise_link_target(link) not in index:
                return False
        for raw in md_links:
            if not self._markdown_target_exists(path, raw):
                return False
        return True

    def _required_target_pages(self, item: SourceItem) -> list[Path]:
        people = item.people[:8]
        projects = item.projects[:6]
        entities = item.entities[:8]
        paths: list[Path] = []
        for person in people:
            paths.append(self.page_path("person", person))
        for project in projects:
            paths.append(self.page_path("project", project))
        skip = {name.casefold() for name in people + projects}
        for entity in entities:
            if entity.casefold() in skip:
                continue
            paths.append(self.page_path("entity", entity))
        return paths

    def _scan_ingested_source_ids(self, items: Sequence[SourceItem] = ()) -> set[str]:
        pages = self.all_markdown_pages()
        index = self._wiki_link_index(pages)
        text_by_path: dict[Path, str] = {}
        generated_ids_by_path: dict[Path, set[str]] = {}
        for path in pages:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            resolved = path.resolve()
            text_by_path[resolved] = text
            generated_ids_by_path[resolved] = _source_ids_in_generated_sections(text)
        complete: set[str] = set()
        seen: set[str] = set()
        for item in items:
            if item.source_id in seen:
                continue
            seen.add(item.source_id)
            targets = self._required_target_pages(item)
            if not targets:
                continue
            ok = True
            for path in targets:
                resolved = path.resolve()
                ids = generated_ids_by_path.get(resolved)
                if not ids or item.source_id not in ids:
                    ok = False
                    break
                if not self._page_supports_source_completion(resolved, text_by_path[resolved], index):
                    ok = False
                    break
            if ok:
                complete.add(item.source_id)
        return complete

    def _source_attributed_blob(self, source_id: str) -> str:
        chunks: list[str] = []
        for path in self.all_markdown_pages():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            _frontmatter, body, valid = split_frontmatter(text)
            payload = body if valid else text
            block = _join_attributed_blocks(payload, source_id)
            if block:
                chunks.append(block)
        return "\n".join(chunks)

    def _source_derived_content_matches(self, item: SourceItem) -> bool:
        blob = self._source_attributed_blob(item.source_id)
        if not blob:
            return False
        if item.title and item.title not in blob:
            return False
        writes_observation = bool(item.people or item.entities or item.projects)
        if writes_observation:
            body = _safe_str(item.text or item.title)[:600]
            if body and body not in blob:
                return False
        return True

    def _source_has_merged_pages(self, source_id: str) -> bool:
        for path in self.all_markdown_pages():
            if not self._is_entity_like_page(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            ids_on_page = self._source_ids_in_text(text)
            if source_id in ids_on_page and len(ids_on_page) > 1:
                return True
        return False

    def _strip_source_from_text(self, text: str, source_id: str) -> str:
        frontmatter, body, valid = split_frontmatter(text)
        if valid:
            frontmatter["sources"] = [
                value for value in _as_list(frontmatter.get("sources")) if _safe_str(value) != source_id
            ]
        body_lines = body.splitlines()
        generated = _generated_section_line_ranges(body_lines)
        marker = f"[source: {source_id}]"
        drop: set[int] = set()
        warned = False
        for start, end in _attributed_block_spans(body_lines, source_id):
            if _span_within_any_range(start, end, generated):
                drop.update(range(start, end))
                continue
            if not warned and any(
                marker in body_lines[i] and not _line_in_ranges(i, generated) for i in range(start, end)
            ):
                print(
                    f"warning: source {source_id} marker found outside generated sections; leaving it in place",
                    file=sys.stderr,
                )
                warned = True
        new_body = "\n".join(line for index, line in enumerate(body_lines) if index not in drop)
        if valid:
            return join_frontmatter(frontmatter, new_body)
        return new_body if new_body.endswith("\n") else f"{new_body}\n"

    def _strip_source_attributed_lines(self, item: SourceItem, *, wholly_owned_only: bool) -> bool:
        source_id = item.source_id
        declined = False
        for path in self.all_markdown_pages():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            ids_on_page = self._source_ids_in_text(text)
            if source_id not in ids_on_page:
                continue
            if wholly_owned_only and len(ids_on_page) > 1:
                declined = True
                continue
            stripped = self._strip_source_from_text(text, source_id)
            if stripped != text:
                self.maybe_write(path, stripped, "update", f"source {source_id} content changed")
        return declined

    def _known_processed_ids(self, items: Sequence[SourceItem] = ()) -> set[str]:
        return self._load_processed_ids() | self._scan_ingested_source_ids(items)

    def _store_processed_ids(self, ids: set[str]) -> None:
        if self.dry_run:
            return
        path = self._processed_marker_path()
        if not _existing_nodes_trusted(path.parent, self.wiki_path):
            return
        payload = json.dumps(sorted(ids), indent=2)
        try:
            _atomic_write(path, payload, self.wiki_path)
        except ValueError:
            return

    def _take_pre_curate_backup(self, outstanding_count: int) -> None:
        existing = list(self.wiki_path.rglob("*"))
        if not any(path.is_file() for path in existing):
            return
        backup_dir = self.wiki_path / ".lumen" / "backup" / self.now.strftime("%Y%m%dT%H%M%S")
        if not _existing_nodes_trusted(backup_dir, self.wiki_path):
            print(
                "warning: skipping backup: .lumen is not a trusted directory",
                file=sys.stderr,
            )
            self.changes.append(
                Change(
                    "skip",
                    self.wiki_path / ".lumen",
                    "skipping backup: .lumen is not a trusted directory",
                )
            )
            return
        planned: list[tuple[Path, Path]] = []
        for src in self.wiki_path.rglob("*"):
            if not src.is_file():
                continue
            if _excluded_from_regen(src, self.wiki_path):
                continue
            dest = backup_dir / src.relative_to(self.wiki_path)
            if not _existing_nodes_trusted(dest, self.wiki_path):
                print(
                    "warning: skipping backup: destination is not a trusted directory",
                    file=sys.stderr,
                )
                self.changes.append(
                    Change(
                        "skip",
                        dest,
                        "skipping backup: destination is not a trusted directory",
                    )
                )
                return
            planned.append((src, dest))
        backup_dir.mkdir(parents=True, exist_ok=True)
        for src, dest in planned:
            if not _existing_nodes_trusted(dest, self.wiki_path) or dest.is_symlink() or dest.parent.is_symlink():
                print(
                    "warning: skipping backup: destination is not a trusted directory",
                    file=sys.stderr,
                )
                self.changes.append(
                    Change(
                        "skip",
                        dest,
                        "skipping backup: destination is not a trusted directory",
                    )
                )
                return
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.parent.is_symlink() or dest.is_symlink():
                print(
                    "warning: skipping backup: destination is not a trusted directory",
                    file=sys.stderr,
                )
                self.changes.append(
                    Change(
                        "skip",
                        dest,
                        "skipping backup: destination is not a trusted directory",
                    )
                )
                return
            shutil.copy2(src, dest)
        self.changes.append(
            Change("backup", backup_dir, f"pre-curate wiki backup ({outstanding_count} items)")
        )

    def curate_items(self, items: Sequence[SourceItem]) -> None:
        items = [_sanitize_item(item) for item in items]
        self.ensure_dirs()
        processed = self._known_processed_ids(items)
        outstanding: list[SourceItem] = []
        changed: dict[str, bool] = {}
        for item in items:
            if item.source_id not in processed:
                outstanding.append(item)
                continue
            if self._source_derived_content_matches(item):
                continue
            changed[item.source_id] = self._source_has_merged_pages(item.source_id)
            outstanding.append(item)
        capped = list(outstanding)
        if self.max_write_pages > 0 and len(capped) > self.max_write_pages:
            capped = capped[: self.max_write_pages]
        if len(outstanding) > 5 and self.wiki_path.exists() and not self.dry_run:
            self._take_pre_curate_backup(len(outstanding))
        for item in capped:
            merged = changed.get(item.source_id)
            if merged is None:
                continue
            declined = self._strip_source_attributed_lines(item, wholly_owned_only=merged)
            if declined:
                print(
                    f"warning: source {item.source_id} changed but shares a merged page; manual review needed",
                    file=sys.stderr,
                )
        for item in capped:
            people = item.people[:8]
            projects = item.projects[:6]
            entities = item.entities[:8]
            related_titles = _unique([*people, *projects, *entities])
            self.upsert_daily_page(item, related_titles)
            for person in people:
                self.upsert_page("person", person, item, extra_tags=["person"], related_titles=related_titles)
            for project in projects:
                self.upsert_page("project", project, item, extra_tags=["project"], related_titles=related_titles)
            for entity in entities:
                # Do not duplicate a person/project as a generic entity.
                if entity.casefold() in {name.casefold() for name in people + projects}:
                    continue
                self.upsert_page("entity", entity, item, extra_tags=["entity"], related_titles=related_titles)
        if capped and not self.dry_run:
            processed.update(item.source_id for item in capped if item.source_id not in self._skipped_sources)
            self._store_processed_ids(processed)
        self.refresh_index()
        self.refresh_overview()
        self.append_action_log()

    def all_markdown_pages(self) -> list[Path]:
        if not self.wiki_path.exists():
            return []
        return sorted(
            path
            for path in self.wiki_path.rglob("*.md")
            if path.is_file() and not _excluded_from_regen(path, self.wiki_path)
        )

    def _page_summary(self, path: Path) -> tuple[dict[str, Any], str, str]:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}, "", ""
        frontmatter, body, _valid = split_frontmatter(text)
        title = _safe_str(frontmatter.get("title")) or self._title_from_body(body) or path.stem.replace("-", " ").title()
        return frontmatter, body, title

    @staticmethod
    def _title_from_body(body: str) -> str:
        for line in body.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return ""

    def _upsert_auto_block(self, path: Path, generated: str, defaults: Mapping[str, Any], detail: str) -> None:
        """Regenerate only the ``lumen:auto`` block of a root page; keep hand-written content."""

        block = f"{AUTO_BLOCK_START}\n{generated.strip()}\n{AUTO_BLOCK_END}"
        try:
            old: str | None = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            old = None
        except OSError:
            return
        if old is None:
            frontmatter = {**defaults, "updated": self.today}
            content = join_frontmatter(frontmatter, f"# {defaults['title']}\n\n{block}\n")
        else:
            frontmatter, body, valid = split_frontmatter(old)
            if not valid:
                body = old
            new_body = _replace_auto_block(body, block)
            if new_body == body:
                return
            if valid:
                merged = dict(frontmatter)
                merged.setdefault("type", defaults["type"])
                merged["updated"] = self.today
                content = join_frontmatter(merged, new_body)
            elif old.startswith("---\n"):
                # Malformed frontmatter: leave the author's text untouched apart from the block.
                content = new_body
            else:
                content = join_frontmatter({**defaults, "updated": self.today}, new_body)
        self.maybe_write(path, content, "update", detail)

    def refresh_index(self) -> None:
        pages = [p for p in self.all_markdown_pages() if p.name not in {"index.md", "overview.md", "log.md"}]
        grouped: dict[str, list[str]] = {}
        for path in pages:
            frontmatter, _body, title = self._page_summary(path)
            page_type = _safe_str(frontmatter.get("type"), path.parent.name)
            updated = _safe_str(frontmatter.get("updated"), "unknown")
            status = _safe_str(frontmatter.get("status"), "")
            rel = self._relative(path)
            row = f"- [{title}]({rel}) — type: `{page_type}`, updated: {updated}"
            if status:
                row += f", status: {status}"
            grouped.setdefault(page_type, []).append(row)
        sections = []
        for page_type in sorted(grouped):
            sections.append(f"## {page_type.title()}\n\n" + "\n".join(sorted(grouped[page_type])))
        generated = "Auto-regenerated content catalog.\n\n" + ("\n\n".join(sections) if sections else "(No pages yet)")
        defaults = {"type": "index", "okf_version": "0.2", "title": "Wiki Index"}
        self._upsert_auto_block(self.wiki_path / "index.md", generated, defaults, "refresh content catalog")

    def refresh_overview(self) -> None:
        pages = [p for p in self.all_markdown_pages() if p.name not in {"overview.md", "log.md"}]
        counts: dict[str, int] = {}
        recent: list[tuple[str, str, str]] = []
        for path in pages:
            frontmatter, _body, title = self._page_summary(path)
            page_type = _safe_str(frontmatter.get("type"), path.parent.name)
            counts[page_type] = counts.get(page_type, 0) + 1
            updated = _safe_str(frontmatter.get("updated"), "")
            if updated:
                recent.append((updated, title, self._relative(path)))
        count_lines = "\n".join(f"- {kind}: {counts[kind]}" for kind in sorted(counts)) or "- No pages yet"
        recent_lines = "\n".join(
            f"- {updated}: [{title}]({rel})" for updated, title, rel in sorted(recent, reverse=True)[:15]
        ) or "- No recent updates"
        generated = f"""Auto-regenerated summary of the wiki.

## Page counts

{count_lines}

## Recently updated

{recent_lines}

## Notes

- The block between the `lumen:auto` markers is maintained by `wiki_curator.py`; edit outside it.
- Draft pages contain source-backed observations only; operator-confirmed facts are never overwritten.
"""
        defaults = {"type": "overview", "title": "Wiki Overview"}
        self._upsert_auto_block(self.wiki_path / "overview.md", generated, defaults, "refresh wiki overview")

    def append_action_log(self) -> None:
        if self.dry_run or not self.changes:
            return
        path = self.wiki_path / "log.md"
        timestamp = self.now.isoformat()
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                content = ""
            if not content.startswith("---\n"):
                body = content
                frontmatter = {"type": "log", "title": "Wiki Action Log", "updated": self.today}
                content = join_frontmatter(frontmatter, body or "# Wiki Action Log\n")
        else:
            frontmatter = {"type": "log", "title": "Wiki Action Log", "created": self.today, "updated": self.today}
            content = join_frontmatter(frontmatter, "# Wiki Action Log\n")
        entries = [f"\n## {timestamp}\n"]
        for change in self.changes:
            entries.append(f"- {change.action}: `{self._relative(change.path)}` — {change.detail}")
        new_content = content.rstrip() + "\n" + "\n".join(entries).rstrip() + "\n"
        _atomic_write(path, new_content, self.wiki_path)
        self.changes.append(Change("update", path, "append action log"))

    def report_changes(self, items: Sequence[SourceItem]) -> str:
        lines = [
            f"Wiki path: {self.wiki_path}",
            f"Sources considered: {len(items)}",
            f"Planned changes: {len(self.changes)}",
        ]
        by_action: dict[str, int] = {}
        for change in self.changes:
            by_action[change.action] = by_action.get(change.action, 0) + 1
        for action in sorted(by_action):
            lines.append(f"- {action}: {by_action[action]}")
        if self.changes:
            lines.append("\nFiles:")
            for change in self.changes:
                lines.append(f"- {change.action}: {self._relative(change.path)} — {change.detail}")
        return "\n".join(lines)


# ─── Validation ─────────────────────────────────────────────────────


def _normalise_link_target(target: str) -> str:
    target = target.strip().split("#", 1)[0]
    if target.endswith(".md"):
        target = target[:-3]
    return target.replace(" ", "-").casefold().strip("/")


def validate_wiki(config: Mapping[str, Any]) -> list[Finding]:
    curator = WikiCurator(config, dry_run=True)
    wiki_path = curator.wiki_path
    findings: list[Finding] = []
    if not wiki_path.exists():
        return [Finding("ERROR", str(wiki_path), "Wiki path does not exist")]

    pages = curator.all_markdown_pages()
    title_map: dict[str, Path] = {}
    seen_titles: dict[str, tuple[str, Path]] = {}  # normalised title -> (display title, first path)
    inbound: dict[Path, int] = {path: 0 for path in pages}
    page_texts: dict[Path, str] = {}
    index_text = ""

    for path in pages:
        rel = curator._relative(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            findings.append(Finding("ERROR", rel, f"Cannot read page: {exc}"))
            continue
        page_texts[path] = text
        if path.name == "index.md":
            index_text = text
        frontmatter, body, valid = split_frontmatter(text)
        if not valid:
            findings.append(Finding("ERROR", rel, "Missing or malformed YAML frontmatter"))
        if valid and not frontmatter.get("type"):
            findings.append(Finding("ERROR", rel, "Missing required frontmatter field: type"))
        title = _safe_str(frontmatter.get("title")) or WikiCurator._title_from_body(body) or path.stem
        candidates = {
            _normalise_link_target(title),
            _normalise_link_target(path.stem),
            _normalise_link_target(rel),
            _normalise_link_target(rel[:-3] if rel.endswith(".md") else rel),
        }
        for candidate in candidates:
            title_map[candidate] = path

        # Duplicate page detection (same normalised title, different paths).
        norm_title = _normalise_link_target(title)
        if norm_title:
            if norm_title in seen_titles:
                other_title, other_path = seen_titles[norm_title]
                if other_path != path:
                    other_rel = curator._relative(other_path)
                    findings.append(
                        Finding("WARN", rel, f"Duplicate page title: '{title}' also at {other_rel}")
                    )
            else:
                seen_titles[norm_title] = (title, path)

        if valid:
            if "confidence" in frontmatter:
                confidence = _confidence_as_float(frontmatter["confidence"])
                if confidence is not None and confidence < 0.5:
                    findings.append(
                        Finding("WARN", rel, f"Low confidence page: confidence={frontmatter['confidence']}")
                    )
            status = _safe_str(frontmatter.get("status"))
            if status == "contested":
                findings.append(Finding("WARN", rel, "Contested page: status=contested"))

        updated = _safe_str(frontmatter.get("updated"))
        if updated:
            parsed = _parse_datetime(updated, timezone.utc)
            if parsed and datetime.now(parsed.tzinfo or timezone.utc) - parsed > timedelta(days=90):
                findings.append(Finding("INFO", rel, "Page is stale: updated more than 90 days ago"))

    for path, text in page_texts.items():
        rel = curator._relative(path)
        for link in WIKILINK_RE.findall(text):
            target = _normalise_link_target(link)
            linked = title_map.get(target)
            if linked is None:
                findings.append(Finding("WARN", rel, f"Broken wikilink: [[{link}]]"))
            elif linked != path:
                inbound[linked] = inbound.get(linked, 0) + 1

    if not index_text:
        findings.append(Finding("ERROR", "index.md", "Missing wiki index"))
    for path in pages:
        rel = curator._relative(path)
        if path.name not in SPECIAL_ROOT_FILES and "raw/" not in rel:
            title = _safe_str(split_frontmatter(page_texts.get(path, ""))[0].get("title")) or path.stem
            if index_text and rel not in index_text and title not in index_text:
                findings.append(Finding("WARN", rel, "Page is not listed in index.md"))
            if inbound.get(path, 0) == 0 and not rel.startswith("daily/"):
                findings.append(Finding("INFO", rel, "Orphan page: no inbound wikilinks"))

    return sorted(findings, key=lambda f: {"ERROR": 0, "WARN": 1, "INFO": 2}.get(f.severity, 3))


def format_findings(findings: Sequence[Finding]) -> str:
    if not findings:
        return "OK: no wiki structure issues found"
    counts: dict[str, int] = {}
    lines: list[str] = []
    for finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1
        lines.append(f"[{finding.severity}] {finding.path}: {finding.message}")
    summary = ", ".join(f"{severity}={counts[severity]}" for severity in sorted(counts))
    return f"Validation findings ({summary}):\n" + "\n".join(lines)


# ─── Search / retrieval ─────────────────────────────────────────────


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN_RE.findall(text or "")]


def _strip_markdown(text: str) -> str:
    """Strip common Markdown markup so snippets are readable plain text."""

    cleaned = text or ""
    cleaned = re.sub(r"```[\s\S]*?```", " ", cleaned)
    cleaned = re.sub(r"`[^`]*`", " ", cleaned)
    cleaned = re.sub(
        r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]",
        lambda match: match.group(2) or match.group(1),
        cleaned,
    )
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[*_~]+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _snippet(body: str, limit: int = 200) -> str:
    return _strip_markdown(body)[:limit]


def _iter_searchable_pages(wiki_path: Path) -> Iterable[Path]:
    if not wiki_path.exists():
        return
    for dirname in SEARCH_DIRS:
        folder = wiki_path / dirname
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.md")):
            if not path.is_file() or path.name in SEARCH_SKIP_NAMES:
                continue
            try:
                rel = path.resolve().relative_to(wiki_path.resolve()).as_posix()
            except ValueError:
                continue
            if rel.startswith("raw/"):
                continue
            yield path


_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "as",
    "do", "does", "did", "done", "we", "he", "she", "it", "they", "you",
    "i", "me", "my", "our", "us", "and", "or", "but", "not", "no", "so",
    "if", "then", "that", "this", "these", "those", "what", "which", "who",
    "how", "when", "where", "why", "can", "could", "would", "should", "will",
    "about", "into", "over", "under", "than", "also", "just", "very", "more",
    "some", "any", "all", "has", "have", "had", "been", "get", "got", "make",
    "made", "let", "say", "said", "one", "two", "up", "down", "out", "now",
})


def _meaningful_tokens(text: str) -> list[str]:
    """Return tokens excluding stop words and tokens shorter than 2 chars."""
    return [t for t in _tokens(text) if len(t) >= 2 and t not in _STOP_WORDS]


def _score_page(query: str, title: str, body: str, aliases: Sequence[str], tags: Sequence[str]) -> float:
    """Score a page against a query using title, body TF, alias, and tag signals."""

    query_text = _safe_str(query)
    if not query_text:
        return 0.0
    query_fold = query_text.casefold()
    query_tokens = _meaningful_tokens(query_text)
    if not query_tokens:
        return 0.0

    score = 0.0

    # Title: match on meaningful tokens only (word-boundary)
    title_fold = _safe_str(title).casefold()
    title_tokens = set(_tokens(title_fold))
    if title_fold and any(t in title_tokens for t in query_tokens):
        score += 3.0

    # Body: TF using meaningful tokens — scaled to compete with title/alias
    body_tokens = _tokens(body)
    if body_tokens:
        hit_count = sum(body_tokens.count(token) for token in query_tokens)
        if hit_count > 0:
            # Log-damped: 1 hit = 1.0, 4 hits = 2.0, 16 hits = 3.0
            score += min(3.0, 1.0 + (hit_count - 1) * 0.25)

    # Alias: exact normalized match only (no substring)
    alias_folds = [_safe_str(alias).casefold() for alias in aliases if _safe_str(alias)]
    if alias_folds:
        alias_set = set(alias_folds)
        alias_token_set = set()
        for a in alias_folds:
            alias_token_set.update(_tokens(a))
        # Exact alias match gets full bonus
        if query_fold in alias_set:
            score += 4.0
        elif any(t in alias_token_set for t in query_tokens if len(t) >= 3):
            score += 2.0  # partial alias token match, lower weight

    # Tag: exact or meaningful token match
    tag_folds = {_safe_str(tag).casefold() for tag in tags if _safe_str(tag)}
    if tag_folds:
        if query_fold in tag_folds:
            score += 2.0
        elif any(t in tag_folds for t in query_tokens):
            score += 1.0

    return score


def search_wiki(
    wiki_path: Path,
    query: str,
    *,
    limit: int = 10,
    page_type: str | None = None,
    tag: str | None = None,
) -> list[dict[str, Any]]:
    """Return scored wiki pages matching ``query``, highest score first."""

    results: list[dict[str, Any]] = []
    type_filter = _safe_str(page_type).casefold() if page_type else ""
    tag_filter = _safe_str(tag).casefold() if tag else ""

    for path in _iter_searchable_pages(wiki_path):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        frontmatter, body, _valid = split_frontmatter(text)
        title = (
            _safe_str(frontmatter.get("title"))
            or WikiCurator._title_from_body(body)
            or path.stem.replace("-", " ").title()
        )
        found_type = _safe_str(frontmatter.get("type"), path.parent.name)
        if type_filter and found_type.casefold() != type_filter:
            continue
        tags = [str(item) for item in _as_list(frontmatter.get("tags"))]
        if tag_filter and tag_filter not in {item.casefold() for item in tags}:
            continue
        aliases = [str(item) for item in _as_list(frontmatter.get("aliases"))]
        score = _score_page(query, title, body, aliases, tags)
        if score <= 0:
            continue
        try:
            rel = path.resolve().relative_to(wiki_path.resolve()).as_posix()
        except ValueError:
            rel = path.name
        results.append(
            {
                "path": rel,
                "title": title,
                "type": found_type,
                "score": round(float(score), 4),
                "snippet": _snippet(body),
                "tags": tags,
            }
        )

    results.sort(key=lambda item: (-item["score"], str(item.get("title") or "")))
    cap = max(0, int(limit)) if limit is not None else 10
    return results[:cap]


def search_command(args: argparse.Namespace) -> int:
    config = _with_wiki_override(
        _load_configuration(getattr(args, "config", None)),
        getattr(args, "wiki", None),
    )
    wiki_path = _wiki_path(config)
    output_format = _safe_str(getattr(args, "format", "text"), "text") or "text"
    limit = getattr(args, "limit", 10)
    try:
        results = search_wiki(
            wiki_path,
            getattr(args, "query", ""),
            limit=10 if limit is None else int(limit),
            page_type=getattr(args, "page_type", None),
            tag=getattr(args, "tag", None),
        )
    except Exception:
        results = []

    if output_format == "json":
        print(json.dumps(results, ensure_ascii=False))
        return 0
    if not results:
        print("No results.")
        return 0
    for item in results:
        snippet = _safe_str(item.get("snippet"))
        print(
            f"[{item['score']:.1f}] {item['title']} ({item['type']}) — {snippet}"
        )
    return 0


# ─── CLI ────────────────────────────────────────────────────────────


def collect_items(config: Mapping[str, Any], since: timedelta) -> tuple[WikiCurator, list[SourceItem]]:
    curator = WikiCurator(config, dry_run=True)
    now = curator.now
    cutoff = now - since
    items = _load_adapter_items(config, curator.wiki_path, cutoff, now)
    return curator, items


def run_command(args: argparse.Namespace, write: bool) -> int:
    config = _with_wiki_override(_load_configuration(args.config), getattr(args, "wiki", None))
    dry_run = bool(args.dry_run or not write)
    curator = WikiCurator(config, dry_run=dry_run)
    since = args.since if isinstance(args.since, timedelta) else parse_since(args.since)
    cutoff = curator.now - since
    items = _load_adapter_items(config, curator.wiki_path, cutoff, curator.now)
    curator.curate_items(items)
    print(curator.report_changes(items))
    if dry_run:
        print("\nDry run: no files were written.")
    return 0


def validate_command(args: argparse.Namespace) -> int:
    config = _with_wiki_override(_load_configuration(args.config), getattr(args, "wiki", None))
    findings = validate_wiki(config)
    print(format_findings(findings))
    return 1 if any(f.severity == "ERROR" for f in findings) else 0


def lint_command(args: argparse.Namespace) -> int:
    """Lint wiki structure (alias for validate, with optional summary mode)."""
    config = _with_wiki_override(_load_configuration(args.config), getattr(args, "wiki", None))
    findings = validate_wiki(config)
    if getattr(args, "summary", False):
        counts: dict[str, int] = {"ERROR": 0, "WARN": 0, "INFO": 0}
        for finding in findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        total = sum(counts.values())
        print(
            f"ERROR: {counts.get('ERROR', 0)}, "
            f"WARN: {counts.get('WARN', 0)}, "
            f"INFO: {counts.get('INFO', 0)}, "
            f"total: {total}"
        )
    else:
        print(format_findings(findings))
    return 1 if any(f.severity == "ERROR" for f in findings) else 0


# Backwards-compatible alias.
cmd_lint = lint_command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Maintain the Markdown wiki from local memory sources.")
    parser.add_argument("--config", help="Path to lumen.yaml (default: shared/config/lumen.yaml or LUMEN_CONFIG)")
    parser.add_argument("--wiki", default=None, help="Override wiki directory path")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Create/update wiki pages from the configured memory source")
    run.add_argument("--since", type=parse_since, default="24h", help="Lookback window such as 24h, 7d, or 90m")
    run.add_argument("--dry-run", action="store_true", help="Report planned changes without writing")
    run.add_argument("--config", dest="sub_config", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    run.add_argument("--wiki", dest="wiki", default=argparse.SUPPRESS, help="Override wiki directory path")

    report = sub.add_parser("report", help="Print planned wiki maintenance summary without writing")
    report.add_argument("--since", type=parse_since, default="24h", help="Lookback window such as 24h, 7d, or 90m")
    report.add_argument("--config", dest="sub_config", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    report.add_argument("--wiki", dest="wiki", default=argparse.SUPPRESS, help="Override wiki directory path")

    validate = sub.add_parser("validate", help="Lint wiki structure")
    validate.add_argument("--config", dest="sub_config", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    validate.add_argument("--wiki", dest="wiki", default=argparse.SUPPRESS, help="Override wiki directory path")

    lint = sub.add_parser("lint", help="Lint wiki structure (alias for validate with summary)")
    lint.add_argument("--summary", action="store_true", help="Print summary counts only")
    lint.add_argument("--config", dest="sub_config", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    lint.add_argument("--wiki", dest="wiki", default=argparse.SUPPRESS, help="Override wiki directory path")

    search = sub.add_parser("search", help="Search wiki pages by keyword, alias, or tag")
    search.add_argument("query", help="Search query text")
    search.add_argument("--format", choices=["json", "text"], default="text", help="Output format")
    search.add_argument("--limit", type=int, default=10, help="Max results")
    search.add_argument("--type", dest="page_type", default=None, help="Filter by page type")
    search.add_argument("--tag", default=None, help="Filter by tag")
    search.add_argument("--config", dest="sub_config", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    search.add_argument("--wiki", dest="wiki", default=argparse.SUPPRESS, help="Override wiki directory path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "sub_config"):
        args.config = args.sub_config
    try:
        if args.command == "run":
            return run_command(args, write=True)
        if args.command == "report":
            args.dry_run = True
            return run_command(args, write=False)
        if args.command == "validate":
            return validate_command(args)
        if args.command == "lint":
            return lint_command(args)
        if args.command == "search":
            return search_command(args)
        parser.error(f"Unknown command: {args.command}")
        return 2
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        # e.g. a symlinked wiki subdirectory tripping the wiki-root write guard.
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
