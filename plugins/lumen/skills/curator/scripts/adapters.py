#!/usr/bin/env python3
"""Memory-source adapters for the Lumen wiki curator.

Read-only. Adapters never write to a memory store. ``SourceItem`` is the
curator dataclass (imported from ``wiki_curator``, not duplicated).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from datetime import date, datetime, timezone, tzinfo
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


TEXT_FIELDS = ("summary", "text", "content", "body", "note", "notes", "description", "title", "value")
TIME_FIELDS = ("received_at", "created_at", "updated_at", "timestamp", "time", "date", "ts")
PEOPLE_KEYS = ("people", "persons", "person", "contacts", "participants")
PROJECT_KEYS = ("project", "projects", "deal", "deals", "initiative", "initiatives")
ENTITY_KEYS = (
    "entity",
    "entities",
    "organization",
    "organizations",
    "org",
    "orgs",
    "company",
    "companies",
    "client",
    "clients",
    "vendor",
    "vendors",
)
_TOKEN_NAME_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&.'-]+)(?:\s+(?:[A-Z][A-Za-z0-9&.'-]+)){0,3}\b"
)
_CAP_WORD_RE = re.compile(r"[A-Z][A-Za-z0-9&'-]*")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def _source_item_cls():
    """Return SourceItem from the already-loaded curator module."""

    here = Path(__file__).resolve().parent / "wiki_curator.py"
    for mod in list(sys.modules.values()):
        path = getattr(mod, "__file__", None)
        if not path:
            continue
        try:
            if Path(path).resolve() == here and hasattr(mod, "SourceItem"):
                return mod.SourceItem
        except OSError:
            continue
    wc = sys.modules.get("wiki_curator") or sys.modules.get("wc_contract")
    if wc is not None and hasattr(wc, "SourceItem"):
        return wc.SourceItem
    from wiki_curator import SourceItem  # local import; curator owns the dataclass

    return SourceItem


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(value)


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
        # A plain string is one name: commas occur inside names ("Acme, Inc.",
        # "Doe, Jane"). Pass a list for several names.
        return [value.strip()] if value.strip() else []
    return [value]


def _tag_list(value: Any) -> list[Any]:
    """Tags, unlike names, may be given as one comma-delimited string."""

    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return _as_list(value)


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
            for fmt in (
                "%Y-%m-%d",
                "%Y/%m/%d",
                "%d %b %Y",
                "%d %B %Y",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
            ):
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


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _looks_like_record(value: Mapping[str, Any]) -> bool:
    return any(key in value and value.get(key) not in (None, "", []) for key in TEXT_FIELDS + TIME_FIELDS)


def _iter_record_mappings(data: Any) -> Iterable[Mapping[str, Any]]:
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


def _heuristic_scan_text(record: Mapping[str, Any], title: str, text: str) -> str:
    """Title and text to scan for names, never the ``Untitled`` placeholder."""

    has_title = bool(_safe_str(record.get("title") or record.get("name") or record.get("summary")))
    has_body = any(_safe_str(record.get(field_name)) for field_name in TEXT_FIELDS)
    return "\n".join(part for part, keep in ((title, has_title), (text, has_body)) if keep)


def _record_timestamp(record: Mapping[str, Any], default: datetime) -> datetime:
    for field_name in TIME_FIELDS:
        parsed = _parse_datetime(record.get(field_name), default.tzinfo or timezone.utc)
        if parsed is not None:
            return parsed
    return default


def _normalise_name(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("name", "display_name", "email", "title", "company", "organization"):
            text = _safe_str(value.get(key))
            if text:
                return text
        return _safe_str(value)
    return _safe_str(value)


def _extract_named_values(record: Mapping[str, Any], keys: Sequence[str]) -> list[str]:
    values: list[Any] = []
    for key in keys:
        if key in record:
            values.extend(_as_list(record.get(key)))
    return _unique(_normalise_name(v) for v in values)


def _sentence_initial(text: str, start: int) -> bool:
    """True when position ``start`` begins the text, a line, a joined field
    (`` — ``) or a sentence (after ``.``/``!``/``?`` and whitespace)."""

    before = text[:start]
    stripped = before.rstrip()
    if not stripped or "\n" in before[len(stripped):]:
        return True
    return stripped[-1] in ".!?—" and len(stripped) < len(before)


def _heuristic_entities(text: str) -> list[str]:
    # A capitalised word that starts a sentence ("Met with…", "Sent…") is only
    # evidence of a name when the same word is also capitalised mid-sentence.
    confirmed = {
        m.group(0) for m in _CAP_WORD_RE.finditer(text) if not _sentence_initial(text, m.start())
    }
    candidates: list[str] = []
    for match in _TOKEN_NAME_RE.finditer(text):
        # A run such as "Dana. Sent Proposal" spans two sentences; judge each part.
        offset = match.start()
        for part in _SENTENCE_SPLIT_RE.split(match.group(0)):
            start = text.index(part, offset)
            offset = start + len(part)
            if not _sentence_initial(text, start) or _CAP_WORD_RE.match(part).group(0) in confirmed:
                candidates.append(part)
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


def _digest_source_id(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()[:12]


def _sanitize_source_id(text: str, max_len: int) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", text)[:max_len]


def _content_seed(record: Mapping[str, Any]) -> str:
    """Stable digest seed from a record's timestamp and text fields.

    Never includes the record's position in the store, so inserting a record
    ahead of an already-ingested one does not change the latter's id.
    """

    content = {key: record[key] for key in TIME_FIELDS + TEXT_FIELDS if key in record}
    return _safe_str(content or record)


def _normalise_source_id(prefix: str, record: Mapping[str, Any]) -> str:
    for key in ("id", "event_id", "source_id", "key", "uuid"):
        text = _safe_str(record.get(key))
        if text:
            cleaned = _sanitize_source_id(text, 120)
            if cleaned.strip("_"):
                return cleaned
            return f"{prefix}_{_digest_source_id(text)}"
    return f"{prefix}_{_digest_source_id(_content_seed(record))}"


def _metadata_mapping(record: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = record.get("metadata_json", record.get("metadata"))
    if isinstance(raw, Mapping):
        return raw
    text = _safe_str(raw)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, Mapping) else {}


def _ensure_aware(dt: datetime, fallback: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=fallback.tzinfo or timezone.utc)
    return dt


class MemorySourceAdapter(ABC):
    name: str

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @abstractmethod
    def load_items(self, cutoff: datetime, now: datetime) -> list:
        ...


class JsonFileAdapter(MemorySourceAdapter):
    name = "json-file"

    def __init__(self, wiki_path: str | os.PathLike[str] | None = None) -> None:
        self.wiki_path = Path(wiki_path).expanduser() if wiki_path else None

    def is_available(self) -> bool:
        if self.wiki_path is None:
            return True
        path = self.wiki_path / ".knowledge" / "memory.json"
        if path.is_file():
            return os.access(path, os.R_OK)
        parent = path.parent
        if parent.is_dir():
            return os.access(parent, os.R_OK)
        wiki = self.wiki_path
        if wiki.is_dir():
            return os.access(wiki, os.R_OK)
        return True

    def load_items(self, cutoff: datetime, now: datetime) -> list:
        if self.wiki_path is None:
            return []
        path = self.wiki_path / ".knowledge" / "memory.json"
        data = _read_json(path)
        if data is None:
            return []
        SourceItem = _source_item_cls()
        items = []
        for record in _iter_record_mappings(data):
            timestamp = _ensure_aware(_record_timestamp(record, now), now)
            if timestamp < cutoff:
                continue
            title, text = _extract_text(record)
            source_id = _normalise_source_id("memory", record)
            people = _extract_named_values(record, PEOPLE_KEYS)
            projects = _extract_named_values(record, PROJECT_KEYS)
            entities = _extract_named_values(record, ENTITY_KEYS)
            tags = _unique(_tag_list(record.get("tags")) + ["memory"])
            if not people and not projects and not entities:
                entities = _heuristic_entities(_heuristic_scan_text(record, title, text))[:3]
            items.append(
                SourceItem(
                    source_id=source_id,
                    source_kind="memory",
                    title=title,
                    text=text,
                    timestamp=timestamp,
                    tags=tags,
                    people=people,
                    entities=entities,
                    projects=projects,
                    raw=record,
                )
            )
        return items


def parse_mnemosyne_envelope(envelope: Mapping[str, Any], cutoff: datetime, now: datetime) -> list:
    """Map a mnemosyne export envelope to SourceItems."""

    SourceItem = _source_item_cls()
    records: list[Mapping[str, Any]] = []
    if isinstance(envelope, Mapping):
        for key in ("working_memory", "episodic_memory"):
            child = envelope.get(key)
            if isinstance(child, list):
                for item in child:
                    if isinstance(item, Mapping):
                        records.append(item)

    items = []
    for record in records:
        if record.get("superseded_by"):
            continue
        timestamp = _parse_datetime(record.get("timestamp"), now.tzinfo or timezone.utc)
        if timestamp is None:
            timestamp = _parse_datetime(record.get("created_at"), now.tzinfo or timezone.utc)
        if timestamp is None:
            timestamp = now
        timestamp = _ensure_aware(timestamp, now)
        if timestamp < cutoff:
            continue
        content = _safe_str(record.get("content"))
        title = content[:80] if content else "Untitled"
        meta = _metadata_mapping(record)
        combined: dict[str, Any] = dict(record)
        for key, value in meta.items():
            combined.setdefault(key, value)
        people = _extract_named_values(combined, PEOPLE_KEYS)
        projects = _extract_named_values(combined, PROJECT_KEYS)
        entities = _extract_named_values(combined, ENTITY_KEYS)
        if not people and not projects and not entities:
            entities = _heuristic_entities(content)[:3]
        source_field = _safe_str(record.get("source"))
        tags = _unique(["memory", source_field])
        source_id = _normalise_source_id("memory", record)
        items.append(
            SourceItem(
                source_id=source_id,
                source_kind="memory",
                title=title,
                text=content,
                timestamp=timestamp,
                tags=tags,
                people=people,
                entities=entities,
                projects=projects,
                raw=record,
            )
        )
    return items


_ZERO_RECORDS = "considering 0 records"


def _warn_mnemosyne_failed(reason: str, consequence: str = _ZERO_RECORDS) -> None:
    print(f"warning: mnemosyne export failed ({reason}); {consequence}", file=sys.stderr)


def run_mnemosyne_export(on_failure: str = _ZERO_RECORDS) -> dict[str, Any] | None:
    hermes = shutil.which("hermes")
    if hermes is None:
        return None
    fd, tmp_name = tempfile.mkstemp(prefix="lumen-mnemosyne-", suffix=".json")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        result = subprocess.run(
            [hermes, "mnemosyne", "export", "--output", str(tmp_path)],
            check=False,
            capture_output=True,
            timeout=120,
        )
        if result.returncode != 0:
            _warn_mnemosyne_failed(f"exit {result.returncode}", on_failure)
            return None
        try:
            data = json.loads(tmp_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            _warn_mnemosyne_failed(type(exc).__name__, on_failure)
            return None
        if not isinstance(data, dict):
            _warn_mnemosyne_failed("not a JSON object", on_failure)
            return None
        return data
    except subprocess.TimeoutExpired:
        _warn_mnemosyne_failed("timeout", on_failure)
        return None
    except Exception as exc:
        _warn_mnemosyne_failed(type(exc).__name__, on_failure)
        return None
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


class MnemosyneAdapter(MemorySourceAdapter):
    name = "mnemosyne"

    def is_available(self) -> bool:
        return shutil.which("hermes") is not None

    def _run_export(self) -> dict[str, Any] | None:
        return run_mnemosyne_export()

    def _run_cli(self) -> dict[str, Any] | None:
        return self._run_export()

    def load_items(self, cutoff: datetime, now: datetime) -> list:
        try:
            envelope = self._run_export()
            if not envelope:
                return []
            return parse_mnemosyne_envelope(envelope, cutoff, now)
        except Exception as exc:
            _warn_mnemosyne_failed(type(exc).__name__)
            return []


class NoneAdapter(MemorySourceAdapter):
    name = "none"

    def is_available(self) -> bool:
        return True

    def load_items(self, cutoff: datetime, now: datetime) -> list:
        return []


ADAPTERS: list[type[MemorySourceAdapter]] = [JsonFileAdapter, MnemosyneAdapter, NoneAdapter]
_KNOWN_SOURCES = {"auto", "json-file", "mnemosyne", "none"}


def _memory_source_name(config: Mapping[str, Any] | None) -> str:
    cfg = config if isinstance(config, Mapping) else {}
    curator = cfg.get("curator") if isinstance(cfg.get("curator"), Mapping) else {}
    raw = ""
    if isinstance(curator, Mapping):
        raw = str(curator.get("memory_source") or "").strip().lower()
    if not raw:
        raw = str(cfg.get("memory_source") or "").strip().lower()
    return raw or "auto"


class AutoMnemosyneAdapter(MnemosyneAdapter):
    """``auto`` mode: prefer Mnemosyne, fall back to json-file when the export fails.

    A ``hermes`` binary on PATH does not guarantee the Mnemosyne plugin is
    installed, so a failed export (non-zero exit, timeout, bad JSON) must not
    silently yield zero records. Explicit ``memory_source: mnemosyne`` keeps
    the plain ``MnemosyneAdapter`` behaviour.
    """

    _FALLBACK_NOTE = "falling back to json-file adapter"

    def __init__(self, wiki_path: str | os.PathLike[str] | None = None) -> None:
        self.fallback = JsonFileAdapter(wiki_path=wiki_path)

    def _run_export(self) -> dict[str, Any] | None:
        return run_mnemosyne_export(on_failure=self._FALLBACK_NOTE)

    def load_items(self, cutoff: datetime, now: datetime) -> list:
        try:
            envelope = self._run_export()
        except Exception as exc:
            _warn_mnemosyne_failed(type(exc).__name__, self._FALLBACK_NOTE)
            envelope = None
        if envelope is None:
            return self.fallback.load_items(cutoff, now)
        try:
            return parse_mnemosyne_envelope(envelope, cutoff, now)
        except Exception as exc:
            _warn_mnemosyne_failed(type(exc).__name__, self._FALLBACK_NOTE)
            return self.fallback.load_items(cutoff, now)


def _auto_adapter(wiki_path: str | os.PathLike[str] | None) -> MemorySourceAdapter:
    if MnemosyneAdapter().is_available():
        return AutoMnemosyneAdapter(wiki_path=wiki_path)
    return JsonFileAdapter(wiki_path=wiki_path)


def get_adapter(
    config: Mapping[str, Any] | None,
    wiki_path: str | os.PathLike[str] | None = None,
) -> MemorySourceAdapter:
    source = _memory_source_name(config)
    if source not in _KNOWN_SOURCES:
        print(
            f"warning: unknown curator.memory_source {source!r}; falling back to auto",
            file=sys.stderr,
        )
        source = "auto"
    if source == "none":
        return NoneAdapter()
    if source == "json-file":
        return JsonFileAdapter(wiki_path=wiki_path)
    if source == "mnemosyne":
        return MnemosyneAdapter()
    return _auto_adapter(wiki_path)
