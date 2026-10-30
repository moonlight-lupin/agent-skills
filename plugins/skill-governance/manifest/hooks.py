"""Lifecycle observer, session drift probe, and pre_llm_call advisory."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_KEY = "v1"
_HANDLED = frozenset({"created", "installed"})
_TARGET_CHARS = 600
_HARD_CAP = 899
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([+.\-][A-Za-z0-9.+_-]+)?$")
_HIDDEN_NAME = "[unusual-name hidden]"
_ADVISORY_ONLY = "Advisory only. Do not act on this unless the user asks."
_CHANGE_REASONS = ("changed", "version-mismatch")
_DEFAULT_MAX_FILES = 400
_DEFAULT_MAX_BYTES = 8_000_000
_DEFAULT_SCAN_BUDGET_S = 5.0
CRON_JOB_NAME = "Skill-manifest drift clearance"
_SESSION_CAP = 1024
_LOCK_WAIT_S = 10.0
_LOCK_POLL_S = 0.1
_LOCK_NAME = "skill-manifest-ensure-cron.lock"
# The scheduled runner is supposed to act. The chat advisory is the opposite.
PROMPT_AUTO_RESOLVE = (
    "Skill-manifest drift clearance.\n"
    "This run is your assigned task. You may act on the drift list. "
    "This is the one context where acting on the advisory is correct.\n"
    "\n"
    "Lint the skills directory against UPSTREAM_MANIFEST.md.\n"
    "If nothing is drifted, reply CLEAN and stop.\n"
    "Otherwise resolve at most 6 skills this run.\n"
    "For a genuine adapted skill, add a manifest row and record provenance.\n"
    "For a throwaway copy, add the skill name to the skill-manifest "
    "plugin dismissed config.\n"
    "Never install, delete, or publish a skill.\n"
    "Never acknowledge changed or version-mismatch findings; report them for human review.\n"
    "Never dismiss, acknowledge, or add to the dismissed config list a changed "
    "or version-mismatch finding; report it for human review.\n"
)

_CTX = None
_probed = False
_disabled_cached = False
_session_signatures: dict[str, dict] = {}
_sessions_loaded = False
_STATE_LOCK = threading.Lock()
_WARN_LOCK = threading.Lock()
_warned: set[str] = set()

manifest_db = None
probe = None
manifest_lint = None
fingerprint = None
acks = None


def _warn_once(key: str, message: str) -> None:
    with _WARN_LOCK:
        if key in _warned:
            return
        _warned.add(key)
    logger.warning(message, exc_info=True)


def _same_file(mod, real: str) -> bool:
    mod_file = getattr(mod, "__file__", None)
    if not isinstance(mod_file, str):
        return False
    try:
        return os.path.realpath(mod_file) == real
    except OSError:
        return False


def _load_by_path(unique_name: str, path: str):
    """Load `path` as `unique_name`, never via a bare `import`.

    The sys.modules key is `unique_name` plus a hash of the resolved path,
    so a second copy cannot replace this file's entry and the module name
    stays a valid identifier. A module already loaded from this exact file
    is reused. A different file sitting on `sys.modules` under the bare name
    (an earlier decoy) is left alone. When the bare name is empty, claim it
    so a later plain import of this same file shares the module object.
    """
    import importlib.util
    import sys

    real = os.path.realpath(path)
    bare = os.path.splitext(os.path.basename(real))[0]
    sys_key = f"{unique_name}_{hashlib.sha1(os.fsencode(real)).hexdigest()[:12]}"
    exact = sys.modules.get(sys_key)
    if exact is not None and _same_file(exact, real):
        return exact
    bare_mod = sys.modules.get(bare)
    if bare_mod is not None and _same_file(bare_mod, real):
        if sys_key in sys.modules and sys.modules[sys_key] is not bare_mod:
            raise ImportError(real)
        sys.modules.setdefault(sys_key, bare_mod)
        sys.modules.setdefault(unique_name, bare_mod)
        return bare_mod
    if sys_key in sys.modules:
        raise ImportError(real)
    spec = importlib.util.spec_from_file_location(sys_key, real)
    if spec is None or spec.loader is None:
        raise ImportError(real)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[sys_key] = mod
    claimed = bare not in sys.modules
    if claimed:
        sys.modules[bare] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(sys_key, None)
        if claimed:
            sys.modules.pop(bare, None)
        raise
    return mod


def _bind_deps():
    global manifest_db, probe, manifest_lint, fingerprint, acks
    try:
        try:
            from . import manifest_db as mdb
        except ImportError:
            siblings = Path(__file__).resolve().parent
            mdb_path = siblings / "manifest_db.py"
            if not mdb_path.is_file():
                raise
            mdb = _load_by_path("skill_manifest_manifest_db", str(mdb_path))
        try:
            from .shared.scripts import manifest_lint as ml
            from .shared.scripts import probe as pb
        except ImportError:
            scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "scripts")
            ml = _load_by_path(
                "skill_manifest_manifest_lint", os.path.join(scripts, "manifest_lint.py")
            )
            pb = _load_by_path("skill_manifest_probe", os.path.join(scripts, "probe.py"))
        manifest_db = mdb
        probe = pb
        manifest_lint = ml
    except Exception:
        _warn_once("bind", "skill-manifest dependency bind failed")
    try:
        try:
            from .shared.scripts import acks as ak
            from .shared.scripts import fingerprint as fp
        except ImportError:
            scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shared", "scripts")
            fp_path = os.path.join(scripts, "fingerprint.py")
            ak_path = os.path.join(scripts, "acks.py")
            fp = (
                _load_by_path("skill_manifest_fingerprint", fp_path)
                if os.path.isfile(fp_path)
                else None
            )
            ak = (
                _load_by_path("skill_manifest_acks", ak_path)
                if os.path.isfile(ak_path)
                else None
            )
        fingerprint = fp
        acks = ak
    except Exception:
        _warn_once("bind-fp", "skill-manifest fingerprint bind failed")


def _deps_ready() -> bool:
    if manifest_db is None:
        _bind_deps()
    return manifest_db is not None and probe is not None and manifest_lint is not None


_bind_deps()


def _reset_runtime() -> None:
    global _probed
    _probed = False


def configure(ctx) -> None:
    global _CTX, _disabled_cached
    _CTX = ctx
    _disabled_cached = False
    if ctx is None:
        return
    try:
        _disabled_cached = _coerce_disabled(ctx.get_config("disabled", False))
    except Exception:
        _disabled_cached = False


def _coerce_disabled(value) -> bool:
    if value is True:
        return True
    if isinstance(value, str) and value.strip().lower() in {"true", "1"}:
        return True
    return False


def _empty_state() -> dict:
    return {
        "baseline": {},
        "pending": [],
        "dismissed": [],
        "first_sweep_done": False,
        "manifest_missing_prompted": False,
        "lint_summary": {},
        "auto_resolve_job_id": "",
        "auto_resolve_user_removed": False,
        "advisory_sessions": {},
        "fingerprints": {},
        "change_baseline_done": False,
        "findings": {},
        "scan": {
            "last_attempt_ts": 0.0,
            "last_ok_ts": 0.0,
            "complete": True,
            "error": "",
            "checked": 0,
            "deferred": 0,
            "skill_errors": {},
            "adoption_retry": [],
            "adoption_cursor": 0,
        },
    }


def _track_changes(ctx) -> bool:
    try:
        value = ctx.get_config("track_changes", True)
    except Exception:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "1"}:
            return True
        if low in {"false", "0"}:
            return False
    return True


def _coerce_positive_int(value, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number >= 1 else default


def _coerce_budget(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _DEFAULT_SCAN_BUDGET_S
    if number != number:  # NaN
        return _DEFAULT_SCAN_BUDGET_S
    return max(0.0, number)


def _max_files_per_skill(ctx) -> int:
    try:
        raw = ctx.get_config("max_files_per_skill", _DEFAULT_MAX_FILES)
    except Exception:
        return _DEFAULT_MAX_FILES
    return _coerce_positive_int(raw, _DEFAULT_MAX_FILES)


def _max_bytes_per_skill(ctx) -> int:
    try:
        raw = ctx.get_config("max_bytes_per_skill", _DEFAULT_MAX_BYTES)
    except Exception:
        return _DEFAULT_MAX_BYTES
    return _coerce_positive_int(raw, _DEFAULT_MAX_BYTES)


def _scan_budget_s(ctx) -> float:
    try:
        raw = ctx.get_config("scan_budget_s", _DEFAULT_SCAN_BUDGET_S)
    except Exception:
        return _DEFAULT_SCAN_BUDGET_S
    return _coerce_budget(raw)


def _clean_fingerprints(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for key, entry in raw.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        quick = entry.get("quick")
        digest = entry.get("digest")
        files = entry.get("files")
        truncated = entry.get("truncated")
        ack = entry.get("ack")
        ack_ts = entry.get("ack_ts")
        first_seen = entry.get("first_seen_ts")
        # K1: backfill the adoption reference digest. Entries predating it
        # carry no `origin`; the stored ack is the only honest reference
        # (a baseline ack equals the adopted digest, a post-baseline ack
        # is ""). Never fabricate: empty ack backfills to "" (no finding).
        clean_ack = ack if isinstance(ack, str) else ""
        origin = entry.get("origin")
        if not isinstance(origin, str) or not origin:
            origin = clean_ack if clean_ack else ""
        out[key] = {
            "quick": quick if isinstance(quick, str) else "",
            "digest": digest if isinstance(digest, str) else "",
            "files": files if isinstance(files, int) and not isinstance(files, bool) else 0,
            "truncated": truncated is True,
            "ack": clean_ack,
            "origin": origin,
            "ack_ts": float(ack_ts)
            if isinstance(ack_ts, (int, float)) and not isinstance(ack_ts, bool)
            else 0.0,
        }
        if isinstance(first_seen, (int, float)) and not isinstance(first_seen, bool):
            out[key]["first_seen_ts"] = float(first_seen)
    return out


def _clean_findings(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for key, entry in raw.items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        name = entry.get("name")
        reason = entry.get("reason")
        digest = entry.get("digest")
        files = entry.get("files")
        first_seen = entry.get("first_seen_ts")
        if not isinstance(name, str) or not name.strip():
            continue
        if reason not in ("untracked", "changed", "version-mismatch"):
            continue
        out[key] = {
            "name": name,
            "reason": reason,
            "digest": digest if isinstance(digest, str) else "",
            "files": files if isinstance(files, int) and not isinstance(files, bool) else 0,
            "truncated": entry.get("truncated") is True,
            "first_seen_ts": float(first_seen)
            if isinstance(first_seen, (int, float)) and not isinstance(first_seen, bool)
            else 0.0,
        }
    return out


def _default_scan() -> dict:
    return {
        "last_attempt_ts": 0.0,
        "last_ok_ts": 0.0,
        "complete": True,
        "error": "",
        "checked": 0,
        "deferred": 0,
        "skill_errors": {},
        "adoption_retry": [],
        "adoption_cursor": 0,
    }


# R7 M4: names only, about 8 KB worst case. Keys beyond 512 persistent
# failures are accepted as out of scope (they read as fresh each pass).
_ADOPTION_RETRY_CAP = 512

# L1/L2/R7-M5: fresh adoptions run first every pass, limited only by
# the adoption slice (40% of the budget, no count cap); examinations run
# to 75%; failed adoptions retry in the final quarter, at most 4
# attempts per pass, rotating from the persistent `scan.adoption_cursor`
# so a healed key sorting after still-failing keys is still attempted.
_ADOPTION_RETRY_ATTEMPTS_CAP = 4


def _coerce_cursor(value) -> int:
    """Persistent retry-rotation cursor: a non-negative int, else 0."""
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number >= 0 else 0


def _clean_adoption_retry(raw) -> list:
    """Lower-case adoption keys still awaiting a retry, bounded to 512."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for key in raw:
        if isinstance(key, str) and key and key not in out:
            out.append(key)
        if len(out) >= _ADOPTION_RETRY_CAP:
            break
    return out


def _clean_skill_errors(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, code in raw.items():
        if not isinstance(key, str) or not isinstance(code, str):
            continue
        out[key] = code
        if len(out) >= 10:
            break
    return out


def _ensure_scan(state: dict) -> dict:
    raw = state.get("scan")
    scan = _default_scan()
    if isinstance(raw, dict):
        for field in ("last_attempt_ts", "last_ok_ts"):
            value = raw.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                scan[field] = float(value)
        if isinstance(raw.get("complete"), bool):
            scan["complete"] = raw["complete"]
        error = raw.get("error")
        scan["error"] = error if isinstance(error, str) else ""
        for field in ("checked", "deferred"):
            value = raw.get(field)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                scan[field] = value
        scan["skill_errors"] = _clean_skill_errors(raw.get("skill_errors"))
        scan["adoption_retry"] = _clean_adoption_retry(raw.get("adoption_retry"))
        scan["adoption_cursor"] = _coerce_cursor(raw.get("adoption_cursor"))
    state["scan"] = scan
    return scan


def _config_dismissed(ctx) -> list[str]:
    try:
        raw = ctx.get_config("dismissed", [])
    except Exception:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str)]


def _union_names(existing: list, extra: list) -> list:
    out: list[str] = []
    seen: set[str] = set()
    for name in list(existing) + list(extra):
        if not isinstance(name, str):
            continue
        stripped = name.strip()
        if not stripped:
            continue
        key = stripped.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(stripped)
    return out


def _load(ctx) -> dict:
    raw = ctx.state.get(STATE_KEY, None)
    state = _empty_state()
    if isinstance(raw, dict):
        for key in state:
            if key in raw:
                state[key] = raw[key]
    state["baseline"] = dict(state["baseline"]) if isinstance(state["baseline"], dict) else {}
    state["pending"] = list(state["pending"]) if isinstance(state["pending"], list) else []
    persisted = list(state["dismissed"]) if isinstance(state["dismissed"], list) else []
    persisted = [item for item in persisted if isinstance(item, str)]
    # Config names merge into the working view only. `_save` filters against
    # this load-time snapshot and never re-reads config: a name removed from
    # config between load and save must not be written into state.dismissed.
    cfg = _config_dismissed(ctx)
    state["_state_dismissed"] = persisted
    state["_cfg_dismissed"] = list(cfg)
    state["dismissed"] = _union_names(persisted, cfg)
    state["first_sweep_done"] = state.get("first_sweep_done") is True
    if isinstance(state["lint_summary"], dict):
        state["lint_summary"] = dict(state["lint_summary"])
    else:
        state["lint_summary"] = {}
    if not isinstance(state["manifest_missing_prompted"], bool):
        state["manifest_missing_prompted"] = bool(state["manifest_missing_prompted"])
    job_id = state.get("auto_resolve_job_id")
    state["auto_resolve_job_id"] = job_id.strip() if isinstance(job_id, str) else ""
    state["auto_resolve_user_removed"] = state.get("auto_resolve_user_removed") is True
    state["advisory_sessions"] = _clean_advisory_sessions(state.get("advisory_sessions"))
    state["fingerprints"] = _clean_fingerprints(state.get("fingerprints"))
    state["change_baseline_done"] = state.get("change_baseline_done") is True
    state["findings"] = _clean_findings(state.get("findings"))
    _ensure_scan(state)
    return state


_KEY_HASH_RE = re.compile(r"^[0-9a-f]{16}$")


def _coerce_key(raw) -> str | None:
    """Session dedupe key: 16 hex chars, or None (legacy/missing).

    Legacy list-shaped keys no longer validate: after upgrade they read as
    new exactly once, then the entry is rewritten with the hashed key.
    """
    if isinstance(raw, str) and _KEY_HASH_RE.fullmatch(raw):
        return raw
    return None


def _finding_rows(pending: list, findings) -> dict[str, str]:
    """Live per-name finding rows: `{name: "name|reason|sha8"}`.

    Change-reason findings contribute their row; every other pending name
    contributes an untracked row. The dedupe key hashes these rows; the
    inject decision compares them per surviving name. Session entries
    store only the sha256 digest of each row (see `_stored_rows`).
    """
    rows: dict[str, str] = {}
    change_lows: set[str] = set()
    if isinstance(findings, dict):
        for key, entry in findings.items():
            if not isinstance(entry, dict):
                continue
            if entry.get("reason") not in _CHANGE_REASONS:
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            digest = entry.get("digest")
            sha8 = digest[:8] if isinstance(digest, str) else ""
            if isinstance(key, str):
                change_lows.add(key.lower())
            rows[name] = f"{name}|{entry.get('reason')}|{sha8}"
    for name in pending or []:
        if not isinstance(name, str) or not name.strip():
            continue
        if name.lower() in change_lows:
            continue
        rows.setdefault(name, f"{name}|untracked|")
    return rows


def _finding_key(pending: list, findings) -> str:
    """Dedupe key covering untracked names and (name, reason, digest8) changes.

    Stored as sha256("|".join(sorted rows))[:16] to bound session entry size.
    `pending` is unchanged.
    """
    rows = sorted(_finding_rows(pending, findings).values())
    return hashlib.sha256("|".join(rows).encode("utf-8")).hexdigest()[:16]


def _coerce_rows(raw) -> dict[str, str]:
    """Per-name finding rows as stored in a session entry, or {}."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for name, row in raw.items():
        if isinstance(name, str) and isinstance(row, str):
            out[name] = row
    return out


_ROW_HASH_RE = re.compile(r"^[0-9a-f]{8}$")

_SESSION_ROW_CAP = 64


def _stored_rows(rows) -> dict[str, str]:
    """Bounded stored rows: `{name: sha256(full_row)[:8]}`, capped at 64 names.

    Already-hashed values pass through unchanged, so the normalizer is
    idempotent across load/copy/save; legacy full-row strings are hashed
    on the way in. Total stored size per session stays bounded regardless
    of library size. Names past the cap are dropped in sorted order; a
    name absent from the stored map compares via the full key instead
    (see `_row_moved`).
    """
    full = _coerce_rows(rows)
    out: dict[str, str] = {}
    for name in sorted(full):
        row = full[name]
        if _ROW_HASH_RE.fullmatch(row):
            out[name] = row
        else:
            out[name] = hashlib.sha256(row.encode("utf-8")).hexdigest()[:8]
        if len(out) >= _SESSION_ROW_CAP:
            break
    return out


def _row_moved(stored_rows, name, cur_row, prev_key, current_key) -> bool:
    """Whether a surviving name's row moved since the stored entry.

    Stored rows are 8-hex digests (compare against the digest of the live
    row); legacy full-row strings compare directly. A name absent from
    the stored map is unknown: fall back to the full-key comparison for
    that name.
    """
    stored = stored_rows.get(name)
    if not isinstance(stored, str) or not isinstance(cur_row, str):
        return prev_key != current_key
    if _ROW_HASH_RE.fullmatch(stored):
        return hashlib.sha256(cur_row.encode("utf-8")).hexdigest()[:8] != stored
    return cur_row != stored


def _session_entry(names, missing: bool, ts: float = 0.0, key=None, rows=None) -> dict:
    pending = sorted({name for name in names if isinstance(name, str)})
    coerced = _coerce_key(key)
    return {
        "pending": pending,
        "missing": bool(missing),
        "ts": float(ts),
        "key": coerced if coerced is not None else [],
        "rows": _stored_rows(rows),
    }


def _entry_ts(entry) -> float:
    """Numeric ts, or 0.0 for a legacy entry. Booleans are not timestamps."""
    if not isinstance(entry, dict):
        return 0.0
    ts = entry.get("ts")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return 0.0
    return float(ts)


def _coerce_session_entry(value):
    """Stored shape is pending, missing, ts, and key. A legacy name list is
    not missing and has ts=0. An entry without a valid key keeps key None so
    the next compare treats it as new (one extra advisory after upgrade)."""
    if isinstance(value, dict):
        pending = value.get("pending")
        if not isinstance(pending, list):
            return None
        entry = _session_entry(
            pending,
            value.get("missing") is True,
            _entry_ts(value),
            value.get("key"),
            value.get("rows"),
        )
        if _coerce_key(value.get("key")) is None and value.get("key") != []:
            entry["key"] = None
        return entry
    if isinstance(value, list):
        entry = _session_entry(value, False, 0.0, None)
        entry["key"] = None
        return entry
    return None


def _same_logical(entry, pending, missing: bool) -> bool:
    if not isinstance(entry, dict):
        return False
    prev = entry.get("pending")
    if not isinstance(prev, list):
        return False
    prev_key = tuple(sorted({name for name in prev if isinstance(name, str)}))
    return prev_key == tuple(pending) and (entry.get("missing") is True) == bool(missing)


def _entry_timestamp(stored, pending, missing: bool) -> float:
    """Stamp now only when pending or missing changed. An unchanged entry keeps its ts."""
    if _same_logical(stored, pending, missing):
        return _entry_ts(stored)
    return time.time()


def _evict_oldest(sessions: dict) -> None:
    """Drop the oldest timestamps past the cap. Equal timestamps: drop the earlier insertion first."""
    extra = len(sessions) - _SESSION_CAP
    if extra <= 0:
        return
    ranked = sorted(sessions, key=lambda sid: _entry_ts(sessions[sid]))
    for sid in ranked[:extra]:
        del sessions[sid]


def _clean_advisory_sessions(raw) -> dict[str, dict]:
    """Session id to {pending, missing, ts, key, rows}. Drop the oldest past the cap."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict] = {}
    for sid, value in raw.items():
        if not isinstance(sid, str):
            continue
        entry = _coerce_session_entry(value)
        if entry is None:
            continue
        out[sid] = entry
    _evict_oldest(out)
    return out


def _copy_entry(entry: dict) -> dict:
    copied = _session_entry(
        entry.get("pending") or [],
        entry.get("missing") is True,
        _entry_ts(entry),
        entry.get("key"),
        entry.get("rows"),
    )
    if entry.get("key") is None:
        copied["key"] = None
    return copied


def _fresher_entry(persisted, cached):
    """The newer session entry. Equal timestamps keep the persisted entry."""
    persisted_entry = _coerce_session_entry(persisted)
    cached_entry = _coerce_session_entry(cached)
    if cached_entry is not None and (
        persisted_entry is None
        or _entry_ts(cached_entry) > _entry_ts(persisted_entry)
    ):
        return cached_entry
    return persisted_entry


def _merge_advisory_sessions(persisted, cache, active_sid: str, active_entry: dict) -> dict:
    """Union persisted and cache. The session just saved keeps the entry just computed.

    Other ids present on both sides keep the newer timestamp. Equal timestamps
    keep the persisted entry. Legacy entries coerce to ts=0 and lose to any
    newer stamp. The cap then drops the oldest timestamps, so an evicted entry
    that still sits in a stale cache does not stay.
    """
    if not isinstance(persisted, dict):
        persisted = {}
    if not isinstance(cache, dict):
        cache = {}
    merged: dict[str, dict] = {}
    for sid, value in persisted.items():
        if not isinstance(sid, str):
            continue
        if sid == active_sid:
            merged[sid] = _copy_entry(active_entry)
            continue
        chosen = _fresher_entry(value, cache.get(sid))
        if chosen is None:
            continue
        merged[sid] = chosen
    for sid, value in cache.items():
        if sid == active_sid or sid in merged or not isinstance(sid, str):
            continue
        entry = _coerce_session_entry(value)
        if entry is not None:
            merged[sid] = entry
    if active_sid not in merged:
        merged[active_sid] = _copy_entry(active_entry)
    _evict_oldest(merged)
    return merged


def _save(ctx, state: dict) -> None:
    snapshot = state.get("_cfg_dismissed")
    if not isinstance(snapshot, list):
        snapshot = []
    config_l = {
        item.strip().lower()
        for item in snapshot
        if isinstance(item, str) and item.strip()
    }
    original = state.get("_state_dismissed")
    if not isinstance(original, list):
        original = []
    original_l = {
        item.strip().lower()
        for item in original
        if isinstance(item, str) and item.strip()
    }
    kept: list[str] = []
    seen: set[str] = set()
    for item in state.get("dismissed") or []:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if not stripped:
            continue
        low = stripped.lower()
        if low in seen:
            continue
        # A name that arrived only through config is not part of state.
        if low in config_l and low not in original_l:
            continue
        seen.add(low)
        kept.append(stripped)
    stored = {
        key: value
        for key, value in state.items()
        if key not in ("_state_dismissed", "_cfg_dismissed")
    }
    stored["dismissed"] = kept
    ctx.state.set(STATE_KEY, stored)


def _disabled() -> bool:
    return _disabled_cached


def _auto_resolve_enabled(ctx) -> bool:
    try:
        value = ctx.get_config("auto_resolve", True)
    except Exception:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "1"}:
            return True
        if low in {"false", "0"}:
            return False
    return True


def _auto_resolve_schedule(ctx) -> str:
    try:
        value = ctx.get_config("auto_resolve_schedule", "0 9 * * *")
    except Exception:
        return "0 9 * * *"
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "0 9 * * *"


def _auto_resolve_deliver(ctx) -> str:
    """Empty string means the create call omits deliver entirely."""
    try:
        value = ctx.get_config("auto_resolve_deliver", "telegram")
    except Exception:
        return "telegram"
    if isinstance(value, str):
        return value.strip()
    return "telegram"


def _import_cron():
    """Lazy import. A process without the Hermes cron modules skips with no error."""
    try:
        from cron.jobs import load_jobs
        from tools.cronjob_tools import cronjob
    except Exception:
        return None
    return load_jobs, cronjob


def _cron_create_kwargs(ctx) -> dict:
    # Unpinned on purpose: the job follows cron.model / cron.model_provider.
    payload = {
        "action": "create",
        "schedule": _auto_resolve_schedule(ctx),
        "prompt": PROMPT_AUTO_RESOLVE,
        "name": CRON_JOB_NAME,
    }
    deliver = _auto_resolve_deliver(ctx)
    if deliver:
        payload["deliver"] = deliver
    return payload


def _cron_result_id(raw) -> str:
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return ""
    if not isinstance(data, dict) or data.get("success") is False:
        return ""
    job_id = data.get("job_id")
    if job_id:
        return str(job_id)
    job = data.get("job")
    if isinstance(job, dict) and job.get("id"):
        return str(job["id"])
    return ""


def _named_job_id(jobs: list) -> str:
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if job.get("name") == CRON_JOB_NAME and job.get("id"):
            return str(job["id"])
    return ""


def _preview(raw) -> str:
    text = repr(raw)
    if len(text) > 200:
        return text[:200]
    return text


def _acquire_flock(fd) -> None:
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_flock(fd) -> None:
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


def _ensure_cron_lock_path(ctx) -> Path:
    """Lock lives beside the skills tree, never inside it and never via HERMES_HOME."""
    return _skills_root(ctx).parent / ".skills-locks" / _LOCK_NAME


@contextmanager
def _ensure_cron_lock(ctx):
    """Exclusive flock. Yields False on deadline. Yields True with no flock when setup fails."""
    try:
        path = _ensure_cron_lock_path(ctx)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
    except OSError:
        _warn_once("cron-lock", "cross-process locking unavailable")
        yield True
        return
    acquired = False
    degraded = False
    try:
        try:
            os.fchmod(fd, 0o644)
        except OSError:
            pass
        deadline = time.monotonic() + _LOCK_WAIT_S
        while True:
            try:
                _acquire_flock(fd)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    logger.warning(
                        "skill-manifest ensure-cron lock timed out after %s seconds: %s",
                        _LOCK_WAIT_S,
                        path,
                    )
                    break
                time.sleep(_LOCK_POLL_S)
            except (ImportError, OSError):
                _warn_once("cron-lock", "cross-process locking unavailable")
                degraded = True
                break
        yield True if degraded else acquired
    finally:
        if acquired:
            try:
                _release_flock(fd)
            except (ImportError, OSError):
                pass
        os.close(fd)


def _write_cron_fields(ctx, *, job_id=None, user_removed=None, only_if_unset=False) -> bool:
    """Reload under the state lock so a concurrent advisory save is not overwritten."""
    with _STATE_LOCK:
        state = _load(ctx)
        if only_if_unset and (
            state.get("auto_resolve_user_removed") or state.get("auto_resolve_job_id")
        ):
            return False
        if job_id is not None:
            state["auto_resolve_job_id"] = job_id
        if user_removed is not None:
            state["auto_resolve_user_removed"] = user_removed
        _save(ctx, state)
        return True


def ensure_cron(ctx=None) -> None:
    """Register one drift-clearance cron, once, unless the user removed it."""
    ctx = _CTX if ctx is None else ctx
    if ctx is None or _disabled():
        return
    try:
        if not _auto_resolve_enabled(ctx):
            return
        with _ensure_cron_lock(ctx) as acquired:
            if not acquired:
                return
            _ensure_cron_locked(ctx)
    except Exception:
        _warn_once("ensure-cron", "skill-manifest ensure cron failed")


def _ensure_cron_locked(ctx) -> None:
    with _STATE_LOCK:
        state = _load(ctx)
        removed = state.get("auto_resolve_user_removed") is True
        job_id = state.get("auto_resolve_job_id") or ""
    api = _import_cron()
    if api is None:
        return
    load_jobs, cronjob = api
    try:
        listed = load_jobs()
        jobs = [job for job in (listed or []) if isinstance(job, dict)]
    except Exception:
        _warn_once("cron-list", "skill-manifest cron list failed")
        return
    if removed:
        # A hand-recreated same-name job means the user wants auto-resolve again.
        existing = _named_job_id(jobs)
        if existing:
            _write_cron_fields(ctx, job_id=existing, user_removed=False)
        return
    if job_id and any(str(job.get("id")) == job_id for job in jobs):
        return
    existing = _named_job_id(jobs)
    if existing:
        _write_cron_fields(ctx, job_id=existing)
        return
    if not jobs:
        if job_id:
            return
    elif job_id:
        _write_cron_fields(ctx, user_removed=True)
        return
    try:
        raw = cronjob(**_cron_create_kwargs(ctx))
    except Exception as exc:
        logger.warning("skill-manifest cron create failed: %s", _preview(exc))
        return
    created = _cron_result_id(raw)
    if not created:
        logger.warning("skill-manifest cron create failed: %s", _preview(raw))
        return
    _write_cron_fields(ctx, job_id=created, only_if_unset=True)


def _manifest_filename(ctx) -> str:
    try:
        raw = ctx.get_config("manifest_filename", "UPSTREAM_MANIFEST.md")
    except Exception:
        return "UPSTREAM_MANIFEST.md"
    if isinstance(raw, str) and raw.strip():
        return raw
    return "UPSTREAM_MANIFEST.md"


def _max_reported(ctx) -> int:
    try:
        n = int(ctx.get_config("max_reported", 6))
    except (TypeError, ValueError):
        return 6
    return n if n >= 1 else 6


def _skills_root(ctx) -> Path:
    raw = ""
    try:
        raw = ctx.get_config("skills_root", "")
    except Exception:
        raw = ""
    if isinstance(raw, Path):
        return raw.expanduser()
    if isinstance(raw, str) and raw.strip():
        return Path(raw).expanduser()
    try:
        import hermes_constants
        home = hermes_constants.get_hermes_home()
    except ImportError:
        env = os.environ.get("HERMES_HOME", "").strip()
        home = Path(env).expanduser() if env else Path.home() / ".hermes"
    return Path(home) / "skills"


def _resolve_skill_status(skill_name: str, *_a, **_k) -> str:
    ctx = _CTX
    root = _skills_root(ctx)
    doc = manifest_db.load_manifest(root / _manifest_filename(ctx))
    if manifest_db.is_manifested(doc, skill_name):
        return "manifested"
    return "untracked"


def _enqueue(name: str) -> None:
    ctx = _CTX
    with _STATE_LOCK:
        state = _load(ctx)
        dismissed = {d.lower() for d in state["dismissed"] if isinstance(d, str)}
        if name.lower() in dismissed:
            return
        if any(isinstance(p, str) and p.lower() == name.lower() for p in state["pending"]):
            return
        state["pending"].append(name)
        _save(ctx, state)


def on_skill_lifecycle(action: str = "", **kw) -> None:
    try:
        if not _deps_ready():
            return None
        if _disabled():
            return None
        if action not in _HANDLED:
            return None
        name = kw.get("skill_name") or ""
        if not isinstance(name, str) or not name.strip() or ":" in name:
            return None
        if _resolve_skill_status(name) == "manifested":
            return None
        _enqueue(name.strip())
    except Exception:
        _warn_once("on_skill_lifecycle", "on_skill_lifecycle failed")
    return None


def _summarize(report) -> dict:
    counts: dict[str, int] = {}
    errors = 0
    findings = list(getattr(report, "findings", []) or [])
    for finding in findings:
        counts[finding.check_id] = counts.get(finding.check_id, 0) + 1
        if finding.severity == "error":
            errors += 1
    return {
        "counts": counts,
        "findings": len(findings),
        "errors": errors,
        "manifest_missing": False,
    }


def _seed_baseline(
    current: set[str],
    manifested: set[str],
    state_dismissed: list[str],
    config_dismissed: list[str],
) -> dict:
    man = {m.lower() for m in manifested}
    state_l = {d.lower() for d in state_dismissed}
    config_l = {d.lower() for d in config_dismissed}
    baseline = {}
    for name in current:
        low = name.lower()
        if low in man:
            baseline[name] = "manifest"
        elif low in state_l:
            baseline[name] = "dismissed"
        elif low in config_l:
            baseline[name] = "dismissed-config"
        else:
            baseline[name] = "untracked-snapshot"
    return baseline


def _dismissal_sets(state: dict) -> tuple[list[str], list[str]]:
    """Split the working dismissed list into state-path names and config-only names."""
    merged = [
        item.strip()
        for item in state.get("dismissed") or []
        if isinstance(item, str) and item.strip()
    ]
    raw = state.get("_state_dismissed")
    if isinstance(raw, list):
        state_names = [item.strip() for item in raw if isinstance(item, str) and item.strip()]
    else:
        state_names = list(merged)
    state_l = {item.lower() for item in state_names}
    config_names: list[str] = []
    seen = set(state_l)
    for name in merged:
        low = name.lower()
        if low in seen:
            continue
        seen.add(low)
        config_names.append(name)
    return state_names, config_names


def reconcile(state: dict, current: set[str], manifested: set[str], summary: dict) -> dict:
    """Fold one inventory sweep into the state document.

    The first sweep snapshots every name on disk and does not pend that corpus.
    A pending name that is not on disk is kept. Later sweeps append only
    names that were not in that snapshot.
    Pending, baseline, and dismissed are compared case-insensitively.
    A name gone from disk leaves baseline, pending, and dismissed.
    A config dismissal is baseline "dismissed-config". When that config entry
    is gone and the name is not state-dismissed or manifested, the next sweep
    rewrites the mark to "untracked-snapshot" and the name pends. A
    manifested skill that loses its manifest row is released the same way
    while it is still on disk and not dismissed: the mark becomes
    "untracked-snapshot" and the name pends as untracked.
    """
    state_dismissed, config_dismissed = _dismissal_sets(state)
    dismissed = [d for d in state["dismissed"] if isinstance(d, str)]
    pending = [p for p in state["pending"] if isinstance(p, str)]
    baseline = {k: v for k, v in state["baseline"].items() if isinstance(k, str)}
    man = {m.lower() for m in manifested}
    current_l = {n.lower() for n in current}
    state_l = {d.lower() for d in state_dismissed}
    config_l = {d.lower() for d in config_dismissed}
    # Dropped config dismissals must leave `known`, or the old baseline entry
    # keeps the skill quiet on this arrival check.
    released = {
        key.lower()
        for key, mark in baseline.items()
        if mark == "dismissed-config"
        and key.lower() in current_l
        and key.lower() not in man
        and key.lower() not in state_l
        and key.lower() not in config_l
    }
    # A manifested skill that loses its manifest row is released the same
    # way: still on disk and not dismissed, it pends again as untracked so
    # the change-tracking pass can drop its stale change finding (H10) while
    # the fingerprint survives for a later re-added row.
    unmanifested = {
        key.lower()
        for key, mark in baseline.items()
        if mark == "manifest"
        and key.lower() in current_l
        and key.lower() not in man
        and key.lower() not in state_l
        and key.lower() not in config_l
    }
    known = {
        k.lower()
        for k in baseline
        if k.lower() not in released and k.lower() not in unmanifested
    } | {p.lower() for p in pending}
    gone_l = known - current_l
    dismissed = [d for d in dismissed if d.lower() not in gone_l]
    dis = {d.lower() for d in dismissed}
    if state.get("first_sweep_done") is not True:
        # Names already on disk are the corpus, so they leave pending.
        # Names not on disk stay: the observer may have recorded them, and
        # this sweep has no evidence they vanished from a previous baseline.
        state["baseline"] = _seed_baseline(
            current, manifested, state_dismissed, config_dismissed
        )
        state["pending"] = [
            p
            for p in pending
            if p.lower() not in current_l and p.lower() not in man and p.lower() not in dis
        ]
        state["dismissed"] = dismissed
        state["first_sweep_done"] = True
        state["lint_summary"] = summary
        return state
    new_pending, gone = probe.compute_pending(set(current), man, dis, known)
    gone_l = {g.lower() for g in gone}
    dismissed = [d for d in dismissed if d.lower() not in gone_l]
    dis = {d.lower() for d in dismissed}
    pending = [
        p
        for p in pending
        if p.lower() not in gone_l and p.lower() not in man and p.lower() not in dis
    ]
    baseline = {k: v for k, v in baseline.items() if k.lower() not in gone_l}
    by_lower: dict[str, str] = {}
    for name in current:
        by_lower.setdefault(name.lower(), name)
    have = {p.lower() for p in pending}
    for name in sorted(new_pending):
        if name in have:
            continue
        pending.append(by_lower.get(name, name))
        have.add(name)
    for name in current:
        low = name.lower()
        if low in man:
            mark = "manifest"
        elif low in state_l:
            mark = "dismissed"
        elif low in config_l:
            mark = "dismissed-config"
        elif low in released or low in unmanifested:
            mark = "untracked-snapshot"
        else:
            continue
        baseline = {k: v for k, v in baseline.items() if k.lower() != low}
        baseline[name] = mark
    state["pending"] = pending
    state["baseline"] = baseline
    state["dismissed"] = dismissed
    state["lint_summary"] = summary
    return state


def _row_local_version(rows, key: str) -> str:
    if not isinstance(rows, dict):
        return ""
    row = rows.get(key)
    if not isinstance(row, dict):
        return ""
    for header, cell in row.items():
        if isinstance(header, str) and header.strip().lower() == "local ver":
            return cell.strip() if isinstance(cell, str) else ""
    return ""


_FULL_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _effective_ack(ext_acks, key: str, entry) -> str:
    """Ack digest for comparison: a 64-hex digest from the external map wins.

    Only a full 64-hex digest is accepted from the external map (a bare
    string is ignored); otherwise the stored fingerprint entry's ack applies.
    """
    if isinstance(ext_acks, dict):
        raw = ext_acks.get(key)
        if isinstance(raw, dict):
            digest = raw.get("digest")
            if isinstance(digest, str) and _FULL_HEX_RE.fullmatch(digest.strip()):
                return digest.strip().lower()
    ack = entry.get("ack") if isinstance(entry, dict) else ""
    return ack if isinstance(ack, str) else ""


def _set_change_finding(state, key, skill_dir, reason, digest, entry, now) -> None:
    findings = state.get("findings")
    if not isinstance(findings, dict):
        findings = {}
        state["findings"] = findings
    first_seen = now
    prev = findings.get(key)
    if isinstance(prev, dict):
        seen = prev.get("first_seen_ts")
        if isinstance(seen, (int, float)) and not isinstance(seen, bool):
            first_seen = float(seen)
    try:
        name = Path(skill_dir).name
    except Exception:
        name = ""
    if not isinstance(name, str) or not name:
        name = key
    files = entry.get("files") if isinstance(entry, dict) else 0
    findings[key] = {
        "name": name,
        "reason": reason,
        "digest": digest if isinstance(digest, str) else "",
        "files": files if isinstance(files, int) and not isinstance(files, bool) else 0,
        "truncated": bool(entry.get("truncated")) if isinstance(entry, dict) else False,
        "first_seen_ts": float(first_seen),
    }


def _adopt_baseline(state, key, skill_dir, max_files, max_bytes, now) -> bool:
    """First-run adoption: store the live fingerprint. No findings.

    While the upgrade baseline is still open (`change_baseline_done` false)
    the live digest is its own ack. A skill adopted after the baseline gets
    `ack = ""` (plus `first_seen_ts`): no human made that acknowledgment,
    so its first real move is reported. The pass right after such an
    adoption still reports nothing (`moved` is false because the stored
    digest equals the live one).

    Returns True when the key now has an entry. An empty live digest means
    the skill could not be examined: nothing is stored (a later pass retries)
    and the caller records a skill-read-error.

    Every adoption stores `origin = digest`, the reference the skill is
    compared against when its ack is empty (K1). Examination never modifies
    `origin`, so a change observed while unacknowledged survives finding
    drops (row removal, track_changes toggle) and is reported on restore.
    """
    fps = state.get("fingerprints")
    if not isinstance(fps, dict):
        fps = {}
        state["fingerprints"] = fps
    try:
        quick = fingerprint.quick_signature(Path(skill_dir), max_files=max_files)
    except Exception:
        quick = ""
    if not isinstance(quick, str):
        quick = ""
    # R16 V1: `quick_signature` returns "" whenever a stat fails (single
    # traversal), so a FAIL-derived signature is already empty here and
    # is stored as "" — the next pass hashes unconditionally instead of
    # comparing markers. No second walk is needed.
    try:
        dig = fingerprint.content_digest(
            Path(skill_dir), max_files=max_files, max_bytes=max_bytes
        )
    except Exception:
        dig = {}
    if not isinstance(dig, dict):
        dig = {}
    digest = dig.get("digest")
    if not isinstance(digest, str):
        digest = ""
    if not digest:
        return False
    files = dig.get("files")
    baseline_open = not bool(state.get("change_baseline_done"))
    fps[key] = {
        "quick": quick if isinstance(quick, str) else "",
        "digest": digest,
        "files": files if isinstance(files, int) and not isinstance(files, bool) else 0,
        "truncated": bool(dig.get("truncated")),
        "ack": digest if baseline_open else "",
        "origin": digest,
        "ack_ts": float(now) if baseline_open else 0.0,
        "first_seen_ts": float(now),
    }
    return True


def _evaluate_digest(state, key, skill_dir, rows, ext_acks, digest, moved, now) -> None:
    """File a `changed`/`version-mismatch` finding or clear a stale one.

    `digest` is the skill's current digest; `moved` says whether it differs
    from the previously stored one. A skill that was never acknowledged
    (`ack == ""`) reports only a real move, so the first observation stays
    silent. When the effective ack is empty but the adoption reference
    `origin` is a non-empty digest (K1), the live digest is compared
    against `origin` instead: a difference reports `changed` even when
    `moved` is false (the stored digest was already overwritten while a
    finding was dropped), and equality clears a stale finding.
    """
    findings = state.get("findings")
    if not isinstance(findings, dict):
        findings = {}
        state["findings"] = findings
    fps = state.get("fingerprints")
    entry = fps.get(key) if isinstance(fps, dict) else None
    if not isinstance(digest, str) or not digest:
        return
    effective = _effective_ack(ext_acks, key, entry)
    if digest == effective:
        declared = ""
        try:
            declared = fingerprint.declared_version(Path(skill_dir) / "SKILL.md")
        except Exception:
            declared = ""
        row_ver = _row_local_version(rows, key)
        if (
            isinstance(declared, str)
            and isinstance(row_ver, str)
            and _VERSION_RE.match(declared)
            and _VERSION_RE.match(row_ver)
            and declared != row_ver
        ):
            _set_change_finding(
                state, key, skill_dir, "version-mismatch", digest, entry, now
            )
            return
        current = findings.get(key)
        if isinstance(current, dict) and current.get("reason") in _CHANGE_REASONS:
            del findings[key]
        return
    if not effective:
        # K1: unacknowledged skill with an adoption reference. The stored
        # digest may already reflect the edit (overwritten by _examine_skill
        # while the finding was dropped), so `moved` is unreliable here.
        origin = entry.get("origin") if isinstance(entry, dict) else ""
        if isinstance(origin, str) and origin:
            if digest != origin:
                _set_change_finding(
                    state, key, skill_dir, "changed", digest, entry, now
                )
            else:
                current = findings.get(key)
                if (
                    isinstance(current, dict)
                    and current.get("reason") in _CHANGE_REASONS
                ):
                    del findings[key]
            return
    if effective:
        _set_change_finding(state, key, skill_dir, "changed", digest, entry, now)
        return
    if moved:
        _set_change_finding(state, key, skill_dir, "changed", digest, entry, now)


def _examine_skill(state, key, skill_dir, rows, ext_acks, max_files, max_bytes, now) -> str:
    """Reconcile one manifested skill. Never raises.

    Returns "ok" or "error". An empty live digest (unreadable or fully
    pruned skill dir) is not examined: no fingerprint write, no finding, no
    clearing — the caller records a `skill-read-error` for the pass.

    R16 V1: `quick_signature` keeps a single traversal. If any row is a
    `FAIL` marker it returns `""` ("the tree could not be fully stat'd;
    always re-hash"), so an empty current signature never takes the
    short circuit, regardless of the stored value, and an empty result
    is stored as `""` (never a non-empty signature produced from a
    `FAIL` row). An empty current signature never equals a stored
    non-empty one, so the digest is recomputed.
    """
    try:
        fps = state.get("fingerprints")
        if not isinstance(fps, dict):
            fps = {}
            state["fingerprints"] = fps
        sdir = Path(skill_dir)
        try:
            cur_quick = fingerprint.quick_signature(sdir, max_files=max_files)
        except Exception:
            cur_quick = ""
        if not isinstance(cur_quick, str):
            cur_quick = ""
        entry = fps.get(key)
        if not isinstance(entry, dict):
            # Manifest row added later: store the digest, ack stays empty,
            # no finding yet. The next real move will be reported.
            try:
                dig = fingerprint.content_digest(
                    sdir, max_files=max_files, max_bytes=max_bytes
                )
            except Exception:
                dig = {}
            if not isinstance(dig, dict):
                dig = {}
            digest = dig.get("digest")
            if not isinstance(digest, str):
                digest = ""
            if not digest:
                return "error"
            files = dig.get("files")
            fps[key] = {
                "quick": cur_quick,
                "digest": digest,
                "files": files
                if isinstance(files, int) and not isinstance(files, bool)
                else 0,
                "truncated": bool(dig.get("truncated")),
                "ack": "",
                "origin": digest,
                "ack_ts": 0.0,
                "first_seen_ts": float(now),
            }
            return "ok"
        old_digest = entry.get("digest")
        if not isinstance(old_digest, str):
            old_digest = ""
        stored_quick = entry.get("quick")
        if not isinstance(stored_quick, str):
            stored_quick = ""
        if cur_quick and cur_quick == stored_quick:
            _evaluate_digest(
                state, key, sdir, rows, ext_acks, old_digest, False, now
            )
            return "ok"
        try:
            dig = fingerprint.content_digest(
                sdir, max_files=max_files, max_bytes=max_bytes
            )
        except Exception:
            dig = {}
        if not isinstance(dig, dict):
            dig = {}
        new_digest = dig.get("digest")
        if not isinstance(new_digest, str) or not new_digest:
            return "error"
        entry["quick"] = cur_quick
        entry["digest"] = new_digest
        files = dig.get("files")
        entry["files"] = (
            files if isinstance(files, int) and not isinstance(files, bool) else 0
        )
        entry["truncated"] = bool(dig.get("truncated"))
        _evaluate_digest(
            state, key, sdir, rows, ext_acks, new_digest, new_digest != old_digest, now
        )
        return "ok"
    except Exception:
        _warn_once("examine", "skill-manifest skill examine failed")
        return "error"


def _sync_missing(state, dirs_l, dismissed) -> None:
    """Drop fingerprints and change findings for gone-from-disk/dismissed skills.

    A skill that merely loses its manifest row keeps its fingerprint (the
    name reconcile reports it as untracked, and re-adding the row resumes
    comparison against the pre-existing ack).
    """
    fps = state.get("fingerprints")
    if isinstance(fps, dict):
        for key in [k for k in fps if k not in dirs_l or k in dismissed]:
            del fps[key]
    findings = state.get("findings")
    if isinstance(findings, dict):
        for key in [
            k
            for k, entry in findings.items()
            if isinstance(entry, dict)
            and entry.get("reason") in _CHANGE_REASONS
            and (k not in dirs_l or k in dismissed)
        ]:
            del findings[key]


def _is_unreviewable_change(state, key) -> bool:
    """True when a change finding can never be reconstructed once dropped.

    A fingerprint with an empty `ack` and an empty `origin` predates the K1
    adoption reference: no reviewed digest exists for the key, so a dropped
    finding regenerates as nothing (the stored digest already reflects the
    edit and `moved` is false on row return). Such a finding is an
    unreviewed change that stays until acknowledged or resolved.
    """
    fps = state.get("fingerprints")
    entry = fps.get(key) if isinstance(fps, dict) else None
    return (
        isinstance(entry, dict)
        and not entry.get("ack")
        and not entry.get("origin")
    )


def _drop_unmanifested_findings(state, man_l) -> None:
    """Drop change-reason findings for keys absent from the manifest.

    A `changed` finding on an unmanifested skill can never clear by
    re-examination (only manifested skills are examined), so a trusted scan
    drops it; the fingerprint is kept, so re-adding the row resumes against
    the old ack and the finding regenerates when the digest still differs.
    Exception (R7 M3): a finding whose fingerprint has an empty `ack` and
    an empty `origin` is kept — it is an unreviewed change that cannot be
    reconstructed once dropped, so it stays until acknowledged or resolved.
    """
    findings = state.get("findings")
    if isinstance(findings, dict):
        for key in [
            k
            for k, entry in findings.items()
            if isinstance(entry, dict)
            and entry.get("reason") in _CHANGE_REASONS
            and k not in man_l
            and not _is_unreviewable_change(state, k)
        ]:
            del findings[key]


def _drop_dismissed(state, dismissed) -> None:
    """Drop fingerprints and change findings for dismissed skills, every pass."""
    fps = state.get("fingerprints")
    if isinstance(fps, dict):
        for key in [k for k in fps if k in dismissed]:
            del fps[key]
    findings = state.get("findings")
    if isinstance(findings, dict):
        for key in [
            k
            for k, entry in findings.items()
            if isinstance(entry, dict)
            and entry.get("reason") in _CHANGE_REASONS
            and k in dismissed
        ]:
            del findings[key]


def _drop_change_findings(state) -> None:
    findings = state.get("findings")
    if isinstance(findings, dict):
        for key in [
            k
            for k, entry in findings.items()
            if isinstance(entry, dict) and entry.get("reason") in _CHANGE_REASONS
        ]:
            del findings[key]


def reconcile_changes(state, dirs, manifested, *, options) -> None:
    """Fingerprint manifested skills and maintain change findings.

    Fingerprints ONLY manifested skills on disk. There is no global baseline
    gate: in a single pass each manifested, on-disk, non-dismissed key is
    adopted when it has no fingerprint entry and otherwise examined, so one
    unexaminable skill never blocks the others. A skill that cannot be
    fingerprinted is retried on every pass and recorded in
    `scan.skill_errors` (`{name: code}`, bounded to 10 entries).
    `scan.checked` counts keys actually visited, `scan.deferred` counts keys
    not reached because of the budget. The pass is split into three slices
    from the pass start (R7 M5, R8 N4): adoption until 40% of
    `scan_budget_s`, examination until 75% (100% when nothing is queued
    for retry), retries until 100%. Fresh missing keys are
    adopted first (the adoption slice), then keys that already have entries
    are examined (the examination slice), so early churn never starves
    later adoption and adoption never starves examination. First-time
    adoption is limited only by the adoption slice (L2: no count cap),
    fresh keys first (sorted), so a large library closes its upgrade
    baseline in one pass. Keys whose adoption failed on an earlier pass
    (`scan.adoption_retry`, bounded to 512) retry last in their own final
    quarter, at most 4 attempts per pass rotating from the persistent
    `scan.adoption_cursor` (L1) — in retry-list order, not sorted
    order — so a persistently failing skill can neither pre-empt a newly
    appeared one nor take the first budget slot forever, a full
    examination slice can no longer starve retries (the cursor always
    advances by the attempts made), and every retry key is attempted
    within ceil(len / 4) passes; a retry entry clears on success.
    `change_baseline_done`
    flips when every such key has an entry
    on a complete-inventory pass — never on a partial pass. Baseline adoption stores the
    live digest as its own ack only while the upgrade baseline is still
    open; a skill adopted after that gets `ack = ""` (zero findings either
    way) and never overwrites an existing entry. Never writes `ack` outside
    adoption. An incomplete scan (budget or error) never clears findings;
    only an examined skill may clear its own, except that every trusted
    pass with a complete inventory drops change findings for keys absent
    from the manifest (they can never be re-examined; the fingerprint is
    kept) and syncs gone-from-disk/dismissed keys — independent of
    per-skill errors and of the budget. Dismissed skills drop their
    fingerprints and change findings on every pass, complete or not —
    including untrusted passes, since that edit touches no
    inventory-derived state. A partial inventory (`options["partial"]`)
    still adopts and examines the skills that were listed, but skips both
    cleanups (they need complete inventory knowledge) and stays
    `complete=False` with `error="inventory-partial"`. The manifest and
    dismissal releases that need no absence evidence run separately on the
    partial name pass via `_apply_partial_releases` (R12).

    Trust gate: when `options["trust_error"]` carries a stable code (or the
    on-disk inventory is empty while fingerprints exist), the inventory is
    untrustworthy — record `complete=False` + the code and return without
    advancing `last_ok_ts`, syncing, adopting, examining, or clearing
    (dismissed keys are still dropped first).
    """
    opts = options if isinstance(options, dict) else {}
    now = opts.get("now")
    if not isinstance(now, (int, float)) or isinstance(now, bool):
        now = time.time()
    else:
        now = float(now)
    max_files = _coerce_positive_int(opts.get("max_files"), _DEFAULT_MAX_FILES)
    max_bytes = _coerce_positive_int(opts.get("max_bytes"), _DEFAULT_MAX_BYTES)
    budget = _coerce_budget(opts.get("scan_budget_s", _DEFAULT_SCAN_BUDGET_S))
    rows = opts.get("rows")
    if not isinstance(rows, dict):
        rows = {}
    ext_acks = opts.get("acks")
    if not isinstance(ext_acks, dict):
        ext_acks = {}
    scan = _ensure_scan(state)
    scan["last_attempt_ts"] = now
    scan["skill_errors"] = {}
    if fingerprint is None:
        scan["error"] = "fingerprint-unavailable"
        scan["complete"] = False
        return
    try:
        raw_dirs = list((dirs or {}).items())
    except Exception:
        raw_dirs = []
    dirs_l: dict = {}
    for name, path in raw_dirs:
        if isinstance(name, str) and name.strip():
            dirs_l[name.strip().lower()] = path
    try:
        man_l = {
            m.strip().lower()
            for m in (manifested or set())
            if isinstance(m, str) and m.strip()
        }
    except Exception:
        man_l = set()
    dismissed = {
        d.lower()
        for d in (state.get("dismissed") or [])
        if isinstance(d, str)
    }
    _drop_dismissed(state, dismissed)
    trust_error = opts.get("trust_error")
    if not isinstance(trust_error, str):
        trust_error = ""
    if not trust_error and not dirs_l:
        fps_now = state.get("fingerprints")
        if isinstance(fps_now, dict) and fps_now:
            trust_error = "inventory-empty"
    if trust_error:
        scan["error"] = trust_error
        scan["complete"] = False
        return
    scan["error"] = ""
    names = sorted(k for k in dirs_l if k in man_l and k not in dismissed)
    scan["checked"] = 0
    scan["deferred"] = 0
    try:
        partial = bool(opts.get("partial"))
        start = time.monotonic()
        # J2/R7-M5: split the budget into three slices from the pass
        # start. Fresh adoptions run first but may consume at most 40% of
        # `scan_budget_s`; examinations get the next slice (until 75%,
        # or 100% when nothing is queued for retry — R8 N4).
        # Previously failed adoptions retry last in their own final
        # quarter, so a full examination slice can no longer starve them.
        adopt_deadline = start + budget * 0.4
        exam_deadline = start + budget * 0.75
        retry_deadline = start + budget
        fps = state.get("fingerprints")
        if not isinstance(fps, dict):
            fps = {}
            state["fingerprints"] = fps
        skill_errors: dict[str, str] = {}
        visited = 0
        failures: list[str] = []
        retry_set = set(scan.get("adoption_retry") or [])
        missing = [k for k in names if k not in fps]
        fresh = [k for k in missing if k not in retry_set]
        # L1: the retry list runs in retry-list (stored) order, not
        # sorted order, so rotation — not the sort position — decides
        # which keys are attempted each pass.
        missing_set = set(missing)
        retry_list = [
            k for k in (scan.get("adoption_retry") or []) if k in missing_set
        ]
        # N4: with nothing queued for retry the examination phase keeps
        # the full budget (`exam_deadline = retry_deadline`); otherwise a
        # normal pass loses a quarter of its examination time for no
        # benefit. Retry-phase behaviour is unchanged when non-empty.
        if not retry_list:
            exam_deadline = retry_deadline
        cursor = scan.get("adoption_cursor")
        if isinstance(cursor, bool) or not isinstance(cursor, int):
            cursor = _coerce_cursor(cursor)
        elif cursor < 0:
            cursor = 0
        present = [k for k in names if k in fps]
        # Fresh missing keys first (I8: early churn never starves later
        # adoption), bounded only by the adoption slice of the budget
        # (L2: no count cap — `fresh` is sorted since `names` is sorted
        # and `missing` preserves that order).
        for key in fresh:
            if time.monotonic() >= adopt_deadline:
                break
            visited += 1
            if not _adopt_baseline(
                state, key, dirs_l[key], max_files, max_bytes, now
            ):
                failures.append(key)
                if len(skill_errors) < 10:
                    skill_errors[key] = "skill-read-error"
        # Then keys that already have entries (J2: the examination slice
        # always gets its share, so adoption cannot starve it).
        # `present` is fixed up front: keys adopted by this very pass are
        # not re-examined until the next pass.
        for key in present:
            if time.monotonic() >= exam_deadline:
                break
            visited += 1
            status = _examine_skill(
                state, key, dirs_l[key], rows, ext_acks, max_files, max_bytes, now
            )
            if status == "error" and len(skill_errors) < 10:
                skill_errors[key] = "skill-read-error"
        # Failed adoptions retry last in their own final quarter (R7 M5:
        # J2 backoff with a reserved slice): a persistently failing
        # skill cannot pre-empt a newly appeared one or take the first
        # budget slot forever. L1 rotates the retry slice: at most 4
        # attempts per pass, starting at `cursor mod len(list)` and
        # wrapping, so every retry key is attempted within
        # ceil(len / 4) passes. The cursor advances by the number of
        # attempts actually made.
        retry_attempts: list[str] = []
        if retry_list:
            start_idx = cursor % len(retry_list)
            for i in range(
                min(_ADOPTION_RETRY_ATTEMPTS_CAP, len(retry_list))
            ):
                retry_attempts.append(
                    retry_list[(start_idx + i) % len(retry_list)]
                )
        made = 0
        for key in retry_attempts:
            if time.monotonic() >= retry_deadline:
                break
            visited += 1
            made += 1
            if not _adopt_baseline(
                state, key, dirs_l[key], max_files, max_bytes, now
            ):
                failures.append(key)
                if len(skill_errors) < 10:
                    skill_errors[key] = "skill-read-error"
        cursor += made
        scan["checked"] = visited
        scan["deferred"] = len(names) - visited
        scan["skill_errors"] = skill_errors
        # A retry entry clears on success (the key now has an entry);
        # keys that left the adoption set (deleted, dismissed,
        # unmanifested) are pruned so the bounded list keeps live keys.
        # The cursor clamps to the pruned list.
        missing_now = set(names) - set(fps)
        new_retry: list = []
        for key in list(scan.get("adoption_retry") or []) + failures:
            if key in missing_now and key not in new_retry:
                new_retry.append(key)
            if len(new_retry) >= _ADOPTION_RETRY_CAP:
                break
        scan["adoption_retry"] = new_retry
        scan["adoption_cursor"] = cursor % len(new_retry) if new_retry else 0
        # J1: never close the upgrade baseline on a partial pass. `names`
        # holds only the skills that were listed; closing here would adopt
        # a hidden skill later with `ack=""` instead of `ack=digest`.
        if not partial and all(k in fps for k in names):
            state["change_baseline_done"] = True
        if not partial:
            _sync_missing(state, dirs_l, dismissed)
            _drop_unmanifested_findings(state, man_l)
        if partial:
            scan["complete"] = False
            scan["error"] = "inventory-partial"
        elif scan["deferred"] <= 0 and not skill_errors:
            scan["complete"] = True
            scan["last_ok_ts"] = now
        else:
            scan["complete"] = False
            if skill_errors:
                scan["error"] = "skill-read-error"
    except Exception as exc:
        scan["error"] = type(exc).__name__
        scan["complete"] = False
        _warn_once("reconcile-changes", "skill-manifest reconcile_changes failed")


def _sync_untracked_findings(state, now: float) -> None:
    """Mirror the name-reconcile pending list into untracked findings entries.

    Dismissed names are skipped: a dismissed skill must never gain (or
    regain) a finding through the mirror (R12, SPEC section 4).
    """
    findings = state.get("findings")
    if not isinstance(findings, dict):
        findings = {}
        state["findings"] = findings
    dismissed = {
        d.lower() for d in (state.get("dismissed") or []) if isinstance(d, str)
    }
    pending = state.get("pending")
    names = (
        [p for p in pending if isinstance(p, str) and p.strip()]
        if isinstance(pending, list)
        else []
    )
    have = {name.lower() for name in names}
    for name in names:
        key = name.lower()
        if key in dismissed:
            continue
        entry = findings.get(key)
        if isinstance(entry, dict) and entry.get("reason") == "untracked":
            entry["name"] = name
            continue
        if key not in findings:
            findings[key] = {
                "name": name,
                "reason": "untracked",
                "digest": "",
                "files": 0,
                "truncated": False,
                "first_seen_ts": float(now),
            }
    for key in [
        k
        for k, entry in findings.items()
        if isinstance(entry, dict)
        and entry.get("reason") == "untracked"
        and k not in have
    ]:
        del findings[key]


def _derive_pending(state) -> None:
    """Derive the pending name list as the union of findings' original names."""
    findings = state.get("findings")
    names: list[str] = []
    if isinstance(findings, dict):
        for entry in findings.values():
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name)
    seen: set[str] = set()
    out: list[str] = []
    for name in sorted(names):
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    state["pending"] = out


def _inventory_trust_error(ctx, state, root, doc) -> str:
    """Stable code when the change inventory is untrustworthy, else "".

    The gate is narrow on purpose. Per-row `doc.errors` entries (a rejected
    or empty row) are NOT a trust error: healthy rows still track, and the
    advisory already reports lint errors. The inventory cannot be trusted
    only when the skills root is not a directory (`root-unavailable`), the
    manifest could not be read (`manifest-unavailable`), or the manifest
    yields zero parsed rows while reporting errors (`manifest-parse-error`).
    An error-free but rowless document is a legitimate removal only when a
    Skill table header was seen (`doc.has_table`: a header-only table) or
    the parsed bytes are empty (`doc.size == 0`, the parsed byte length); otherwise the tables
    were overwritten with prose and the document is `manifest-parse-error`
    — trusting it would drop `changed` findings and file the whole library
    as `untracked`. An empty on-disk inventory with surviving fingerprints
    (`inventory-empty`) is decided by the caller, which holds the
    enumeration result.

    R16 V2: the verdict comes from the `doc` already loaded in `_probe` —
    the manifest file is never re-read here, so a file appearing or
    vanishing between the load and this gate cannot flip the decision
    for the pass. If the document says the manifest is fine (a non-empty
    skill set), that is the decision for this pass.
    R17: the empty-vs-unparseable distinction also uses the document only
    (`doc.has_table`, `doc.size`); an unknown size fails closed.
    R18: `doc.size` is the parsed byte length (`len(raw)` in
    `manifest_db.load_manifest`), never a later `stat()`.
    """
    try:
        if not Path(root).is_dir():
            return "root-unavailable"
    except Exception:
        return "root-unavailable"
    try:
        skills = set(getattr(doc, "skills", None) or set())
    except Exception:
        skills = set()
    if skills:
        return ""
    try:
        errors = getattr(doc, "errors", None)
    except Exception:
        errors = None
    if isinstance(errors, list) and errors:
        # `manifest_db.load_manifest` reports an unreadable manifest as a
        # "cannot read manifest: ..." error; any other error means the
        # manifest was read but could not be understood.
        if any(
            isinstance(entry, str)
            and entry.startswith("cannot read manifest:")
            for entry in errors
        ):
            return "manifest-unavailable"
        return "manifest-parse-error"
    if errors and not isinstance(errors, list):
        return "manifest-parse-error"
    # R17: error-free but rowless. A Skill table header (even with zero
    # data rows) or empty parsed bytes is a legitimate empty manifest. Anything
    # else has no Skill table at all (e.g. overwritten with prose) and is
    # unparseable. Document-only decision: never re-read the file here, and
    # an unknown size fails closed.
    try:
        has_table = bool(getattr(doc, "has_table", False))
    except Exception:
        has_table = False
    if has_table:
        return ""
    try:
        size = getattr(doc, "size", None)
    except Exception:
        size = None
    if isinstance(size, bool):
        return "manifest-parse-error"
    if size == 0:
        return ""
    return "manifest-parse-error"


def _dismissed_lows(state) -> set:
    return {
        d.lower()
        for d in (state.get("dismissed") or [])
        if isinstance(d, str)
    }


def _run_change_tracking(ctx, state, root, doc) -> None:
    now = time.time()
    scan = _ensure_scan(state)
    scan["last_attempt_ts"] = now
    if fingerprint is None:
        scan["error"] = "fingerprint-unavailable"
        scan["complete"] = False
        return
    trust_error = _inventory_trust_error(ctx, state, root, doc)
    if trust_error:
        # Fail open: keep every fingerprint and finding, freeze last_ok_ts.
        # Dismissed keys are still dropped: that edit is pure state cleanup.
        _drop_dismissed(state, _dismissed_lows(state))
        scan["error"] = trust_error
        scan["complete"] = False
        return
    try:
        listed = fingerprint.list_skill_dirs(root)
    except Exception as exc:
        _drop_dismissed(state, _dismissed_lows(state))
        scan["error"] = type(exc).__name__
        scan["complete"] = False
        return
    dirs = listed
    inv_errors = list(getattr(listed, "errors", None) or [])
    partial = bool(inv_errors)
    if not dict(dirs or {}):
        fps = state.get("fingerprints")
        if isinstance(fps, dict) and fps:
            _drop_dismissed(state, _dismissed_lows(state))
            scan["error"] = "inventory-empty"
            scan["complete"] = False
            return
    rows = getattr(doc, "rows", None)
    if not isinstance(rows, dict):
        rows = {}
    ext: dict = {}
    if acks is not None:
        try:
            loaded = acks.load_acks(acks.default_acks_path())
            if isinstance(loaded, dict) and isinstance(loaded.get("acks"), dict):
                ext = loaded["acks"]
        except Exception:
            ext = {}
    try:
        manifested = set(getattr(doc, "skills", set()) or set())
    except Exception:
        manifested = set()
    options = {
        "max_files": _max_files_per_skill(ctx),
        "max_bytes": _max_bytes_per_skill(ctx),
        "scan_budget_s": _scan_budget_s(ctx),
        "now": now,
        "rows": rows,
        "acks": ext,
        "trust_error": trust_error,
        # Partial enumeration still adopts and examines the skills that
        # were listed; reconcile skips the cleanups (they need complete
        # inventory knowledge) and keeps complete=False + inventory-partial.
        # Manifest/dismissal releases that need no absence evidence run on
        # the partial name pass via _apply_partial_releases (R12).
        "partial": partial,
    }
    reconcile_changes(state, dirs, manifested, options=options)


def _empty_summary() -> dict:
    return {"counts": {}, "findings": 0, "errors": 0, "manifest_missing": False}


def _apply_partial_releases(state: dict, current, manifested, now: float) -> None:
    """Bounded manifest/dismissal releases for a partial pass (R12).

    Uses ONLY the manifest set, the dismissed set, and the partial name
    listing. Absence from the listing is never evidence of deletion, so a
    name is never removed because it is missing from the listing.

    1. Dismissed keys: findings of any reason are deleted and their names
       leave `pending` (SPEC section 4: dismissed skills never produce
       findings; `_drop_dismissed` only drops change-reason findings).
    2. Stale pending: a pending name whose key is manifested and has no
       finding leaves `pending` (otherwise the untracked mirror below
       would file a bogus `untracked` finding for a manifested skill).
    3. Row removed but still on disk: a key present in the partial
       listing that is not manifested and not dismissed, and previously
       known from the manifest (`baseline` mark `"manifest"`, or a
       fingerprint entry), is reported `untracked`: a held
       change-reason finding (`changed` / `version-mismatch`) is
       replaced with an `untracked` finding (`digest=""`, `files=0`,
       `truncated=False`, kept `first_seen_ts` and name); when it holds
       no finding, an `untracked` finding is created (`digest=""`,
       `files=0`, `truncated=False`, `first_seen_ts=now`) and the name
       joins `pending`. A listed key that was never manifested is left
       to `_append_partial_arrivals`. Exception (R14 T1): a held
       change-reason finding whose key matches `_is_unreviewable_change`
       (empty `ack` and empty `origin`) is never converted; the creation
       rule is unaffected.
    """
    try:
        listing = {
            n.lower() for n in current if isinstance(n, str) and n.strip()
        }
    except Exception:
        listing = set()
    try:
        by_lower: dict[str, str] = {}
        for name in current:
            if isinstance(name, str) and name.strip():
                by_lower.setdefault(name.lower(), name)
    except Exception:
        by_lower = {}
    try:
        man = {
            m.lower() for m in manifested if isinstance(m, str) and m.strip()
        }
    except Exception:
        man = set()
    dismissed = {
        d.lower() for d in (state.get("dismissed") or []) if isinstance(d, str)
    }
    findings = state.get("findings")
    if not isinstance(findings, dict):
        findings = {}
        state["findings"] = findings
    pending = state.get("pending")
    if not isinstance(pending, list):
        pending = []
        state["pending"] = pending
    # 1. Dismissed keys: drop findings of any reason, unpend their names.
    if dismissed:
        for key in [
            k
            for k in findings
            if isinstance(k, str) and k.lower() in dismissed
        ]:
            del findings[key]
        pending = [
            p
            for p in pending
            if not (isinstance(p, str) and p.lower() in dismissed)
        ]
        state["pending"] = pending
    # 2. Stale pending: manifested with no finding leaves pending.
    have = {k.lower() for k in findings if isinstance(k, str)}
    pending = [
        p
        for p in pending
        if not (
            isinstance(p, str)
            and p.strip()
            and p.lower() in man
            and p.lower() not in have
        )
    ]
    state["pending"] = pending
    # 3. Row removed but still on disk: listed, unmanifested, not
    # dismissed, previously known from the manifest -> untracked.
    # A held change-reason finding converts; a key with no finding
    # gains a fresh `untracked` finding and joins `pending`. Exception
    # (R14 T1): a finding whose fingerprint has an empty `ack` and an
    # empty `origin` is never converted — it is an unreviewed change
    # that cannot be reconstructed once dropped (the stored digest
    # already equals the live one), so it stays until acknowledged or
    # resolved, mirroring `_drop_unmanifested_findings` (R7 M3).
    for key in list(findings):
        entry = findings.get(key)
        if not isinstance(entry, dict):
            continue
        if entry.get("reason") not in _CHANGE_REASONS:
            continue
        if _is_unreviewable_change(state, key):
            continue
        low = key.lower() if isinstance(key, str) else ""
        if not low or low not in listing or low in man or low in dismissed:
            continue
        seen = entry.get("first_seen_ts")
        if not isinstance(seen, (int, float)) or isinstance(seen, bool):
            seen = now
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            name = by_lower.get(low, key)
        findings[key] = {
            "name": name,
            "reason": "untracked",
            "digest": "",
            "files": 0,
            "truncated": False,
            "first_seen_ts": float(seen),
        }
    try:
        baseline = state.get("baseline")
        manifest_mark = {
            k.lower()
            for k, mark in baseline.items()
            if isinstance(k, str) and mark == "manifest"
        }
    except Exception:
        manifest_mark = set()
    try:
        fps = state.get("fingerprints")
        fingerprinted = {
            k.lower() for k in fps if isinstance(k, str)
        }
        if not isinstance(fps, dict):
            fingerprinted = set()
    except Exception:
        fingerprinted = set()
    have_pending = {
        p.lower() for p in pending if isinstance(p, str) and p.strip()
    }
    for low in sorted(listing):
        if low in man or low in dismissed:
            continue
        if low not in manifest_mark and low not in fingerprinted:
            continue
        if any(
            isinstance(k, str) and k.lower() == low for k in findings
        ):
            continue
        name = by_lower.get(low, low)
        findings[low] = {
            "name": name,
            "reason": "untracked",
            "digest": "",
            "files": 0,
            "truncated": False,
            "first_seen_ts": float(now),
        }
        if low not in have_pending:
            pending.append(name)
            have_pending.add(low)
    state["pending"] = pending


def _append_partial_arrivals(state: dict, current, manifested) -> None:
    """Append name-pass arrivals to pending without removing anything.

    Names present in the (partial) name report that are not in the state's
    known set (`baseline` keys plus `pending`), not manifested, and not
    dismissed are arrivals the reconcile pass would have pended: append
    them so `_sync_untracked_findings` can mirror them into findings.
    Comparisons are case-insensitive; the report's original case is kept.
    Never removes a name: a partial listing may omit skills still on disk.
    """
    try:
        names = sorted(
            {n for n in current if isinstance(n, str) and n.strip()},
            key=str.lower,
        )
    except Exception:
        return
    try:
        man = {m.lower() for m in manifested if isinstance(m, str) and m.strip()}
    except Exception:
        man = set()
    baseline = state.get("baseline")
    if isinstance(baseline, dict):
        known = {k.lower() for k in baseline if isinstance(k, str)}
    else:
        known = set()
    pending = state.get("pending")
    if not isinstance(pending, list):
        pending = []
        state["pending"] = pending
    for entry in pending:
        if isinstance(entry, str) and entry.strip():
            known.add(entry.lower())
    dismissed = {
        d.lower() for d in (state.get("dismissed") or []) if isinstance(d, str)
    }
    have = {p.lower() for p in pending if isinstance(p, str)}
    for name in names:
        low = name.lower()
        if low in known or low in man or low in dismissed or low in have:
            continue
        pending.append(name)
        known.add(low)
        have.add(low)


def _probe() -> None:
    global _probed
    try:
        ctx = _CTX
        root = _skills_root(ctx)
        try:
            root_ok = root.is_dir()
        except Exception:
            root_ok = False
        if not root_ok:
            with _STATE_LOCK:
                state = _load(ctx)
                scan = _ensure_scan(state)
                scan["last_attempt_ts"] = time.time()
                scan["complete"] = False
                scan["error"] = "root-unavailable"
                _save(ctx, state)
            return
        filename = _manifest_filename(ctx)
        path = root / filename
        current, name_errors = probe.list_skill_names_report(root)
        doc = manifest_db.load_manifest(path)
        summary = _empty_summary()
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8-sig", errors="replace")
                summary = _summarize(manifest_lint.lint_manifest(text, on_disk=current))
            else:
                summary["manifest_missing"] = True
        except Exception:
            _warn_once("manifest-lint", "manifest lint failed")
            summary = _empty_summary()
        with _STATE_LOCK:
            state = _load(ctx)
            if name_errors:
                # Partial name pass: the name set may omit skills that are
                # still on disk, so it must not drive `gone` cleanups and
                # `reconcile()` is never called here. Change tracking
                # still runs (partial, as it determines from its own
                # listing); the bounded manifest/dismissal releases run
                # first (R12: dismissed unpended, stale manifested pending
                # cleared, listed row-removed changes converted to
                # untracked — R13: created when finding-free — never by
                # absence from the listing), then
                # arrivals from the name report are appended to
                # pending (never removed), then the untracked mirror and
                # the pending derivation run so this pass's `changed` /
                # `version-mismatch` findings and new arrivals are reported.
                # R15 U2: the release gate consults the trust function
                # directly instead of `scan["error"]` (stale when
                # `track_changes = false`, absent for
                # `fingerprint-unavailable`). R16 V2: the verdict comes
                # from the `doc` already loaded above — the manifest is
                # never re-read for this gate. When the manifest itself
                # is untrusted (`manifest-unavailable`,
                # `root-unavailable`, `manifest-parse-error`) — or
                # fingerprints cannot be computed at all — none of those
                # steps run.
                try:
                    if _track_changes(ctx):
                        _run_change_tracking(ctx, state, root, doc)
                    else:
                        _drop_change_findings(state)
                    if fingerprint is None:
                        gate_error = "fingerprint-unavailable"
                    else:
                        try:
                            gate_error = _inventory_trust_error(
                                ctx, state, root, doc
                            )
                        except Exception:
                            gate_error = ""
                    if gate_error in (
                        "manifest-unavailable",
                        "root-unavailable",
                        "manifest-parse-error",
                    ) or fingerprint is None:
                        # R15 U2: the manifest could not be read (or its
                        # content could not be fingerprinted), so the
                        # manifested set is untrustworthy — run no
                        # release/arrival/mirror step on this pass, but
                        # still derive `pending` so a name whose finding
                        # was dropped by `_drop_dismissed` leaves
                        # `pending` on this same pass.
                        _derive_pending(state)
                        scan = _ensure_scan(state)
                        scan["error"] = gate_error
                        scan["complete"] = False
                    else:
                        try:
                            manifested = set(
                                getattr(doc, "skills", set()) or set()
                            )
                        except Exception:
                            manifested = set()
                        _apply_partial_releases(
                            state, current, manifested, time.time()
                        )
                        _append_partial_arrivals(state, current, manifested)
                        _sync_untracked_findings(state, time.time())
                        _derive_pending(state)
                        scan = _ensure_scan(state)
                        if not scan.get("error"):
                            scan["error"] = "inventory-partial"
                except Exception:
                    _warn_once("changes", "skill-manifest change tracking failed")
            else:
                reconcile(state, current, set(doc.skills), summary)
                try:
                    if _track_changes(ctx):
                        _run_change_tracking(ctx, state, root, doc)
                    else:
                        _drop_change_findings(state)
                    _sync_untracked_findings(state, time.time())
                    _derive_pending(state)
                except Exception:
                    _warn_once("changes", "skill-manifest change tracking failed")
            _save(ctx, state)
    finally:
        _probed = True


def on_session_start(session_id: str = "", **kw) -> None:
    del session_id, kw
    try:
        if not _deps_ready():
            return None
        if _disabled():
            return None
        _reset_runtime()
        _probe()
        ensure_cron()
    except Exception:
        _warn_once("on_session_start", "on_session_start failed")
    return None


def _public_name(name: str) -> str:
    if _NAME_RE.fullmatch(name):
        return name
    return _HIDDEN_NAME


def _compose(names: list[str], shown_n: int, filename: str, lint_summary: dict) -> str:
    shown = [_public_name(str(n)) for n in names[:shown_n]]
    extra = len(names) - shown_n
    body = ", ".join(shown)
    if extra > 0:
        body = f"{body}, +{extra} more"
    label = "skill" if len(names) == 1 else "skills"
    text = (
        f"⚠️ skill-manifest: {len(names)} {label} missing from {filename}: "
        f"{body}. Add a manifest row to {filename}, or add "
        f"the skill to the skill-manifest plugin's dismissed config list."
    )
    note = _lint_note(lint_summary)
    if note:
        text += f"\n{note}"
    return text


def _change_items(findings) -> list[tuple]:
    """Sorted (name, reason, sha8, truncated) for change findings."""
    items: list[tuple] = []
    if isinstance(findings, dict):
        for entry in findings.values():
            if not isinstance(entry, dict):
                continue
            if entry.get("reason") not in _CHANGE_REASONS:
                continue
            name = entry.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            digest = entry.get("digest")
            sha8 = digest[:8] if isinstance(digest, str) else ""
            items.append((name, entry.get("reason"), sha8, entry.get("truncated") is True))
    return sorted(items, key=lambda item: item[0].lower())


_SHA8_RE = re.compile(r"^[0-9a-f]{8}$")


def _display_sha(sha8) -> str:
    """Validated hex prefix for the advisory; invalid/empty shows `????`."""
    if isinstance(sha8, str) and _SHA8_RE.fullmatch(sha8.lower()):
        return sha8
    return "????"


def _lint_note(lint_summary: dict) -> str:
    """The manifest-lint sentence, or "" when there are no lint errors."""
    try:
        errors = int((lint_summary or {}).get("errors") or 0)
        findings = int((lint_summary or {}).get("findings") or 0)
    except (TypeError, ValueError):
        return ""
    if errors > 0:
        return (
            f"Manifest has {findings} lint findings ({errors} errors) — "
            "run the manifest lint."
        )
    return ""


def _changes_block(items: list[tuple], shown_n: int) -> str:
    count = len(items)
    label = "skill" if count == 1 else "skills"
    lines = [
        f"⚠️ skill-manifest: {count} {label} changed since their last acknowledged review:"
    ]
    for name, reason, sha8, truncated in items[:shown_n]:
        extra = " (truncated fingerprint)" if truncated else ""
        lines.append(f"- {_public_name(name)} ({reason}, sha {_display_sha(sha8)}{extra})")
    if count > shown_n:
        lines.append(f"+{count - shown_n} more")
    if any(
        isinstance(sha8, str) and _SHA8_RE.fullmatch(sha8.lower())
        for _name, _reason, sha8, _truncated in items
    ):
        lines.append("After review: hermes skill-manifest ack <name> --expect <sha>")
    return "\n".join(lines)


def _coverage_line(scan) -> str:
    """One short line when coverage is incomplete, else "".

    Reports unreadable skills and a partial inventory independently: a
    partial inventory with no per-skill error still gets a line (R7 M1),
    and both are combined when both are present.
    """
    if not isinstance(scan, dict):
        return ""
    parts: list[str] = []
    errors = scan.get("skill_errors")
    if isinstance(errors, dict) and errors:
        count = len(errors)
        label = "skill" if count == 1 else "skills"
        parts.append(f"{count} {label} unreadable")
    if scan.get("error") == "inventory-partial":
        parts.append("inventory partial")
    if not parts:
        return ""
    return "coverage: " + ", ".join(parts) + ", see status"


def _with_coverage(text: str, scan) -> str:
    """Append the coverage line, keeping it inside the hard cap.

    Room is reserved for `_finish_advisory`'s trailing line as well, so the
    coverage line is never the part that gets cut.
    """
    line = _coverage_line(scan)
    if not line:
        return text
    room = _HARD_CAP - len("\n" + _ADVISORY_ONLY) - len(line) - 1
    if room < 1:
        return line[:_HARD_CAP]
    if len(text) > room:
        text = text[:room]
    return text + "\n" + line


def _advisory_body(
    names: list[str],
    filename: str,
    max_reported: int,
    lint_summary: dict,
    findings=None,
    scan=None,
) -> str:
    items = _change_items(findings)
    if not items:
        shown_n = min(len(names), max_reported)
        text = _compose(names, shown_n, filename, lint_summary)
        while shown_n > 1 and len(text) > _TARGET_CHARS:
            shown_n -= 1
            text = _compose(names, shown_n, filename, lint_summary)
        if len(text) > _HARD_CAP:
            text = text[:_HARD_CAP]
        return _with_coverage(text, scan)
    change_lows: set[str] = set()
    if isinstance(findings, dict):
        for key, entry in findings.items():
            if (
                isinstance(key, str)
                and isinstance(entry, dict)
                and entry.get("reason") in _CHANGE_REASONS
            ):
                change_lows.add(key.lower())
    untracked = [
        n for n in names if isinstance(n, str) and n.lower() not in change_lows
    ]
    shown_u = min(len(untracked), max_reported)
    shown_c = min(len(items), 3)

    def _build() -> str:
        blocks = [_changes_block(items, shown_c)]
        if untracked:
            blocks.append(_compose(untracked, shown_u, filename, lint_summary))
        else:
            note = _lint_note(lint_summary)
            if note:
                blocks.append(note)
        return "\n".join(blocks)

    text = _build()
    while len(text) > _TARGET_CHARS and (shown_u > 1 or shown_c > 1):
        if shown_u > 1:
            shown_u -= 1
        else:
            shown_c -= 1
        text = _build()
    if len(text) > _HARD_CAP:
        text = text[:_HARD_CAP]
    return _with_coverage(text, scan)


def _advisory(
    names: list[str],
    filename: str,
    max_reported: int,
    lint_summary: dict,
    findings=None,
    scan=None,
) -> str:
    return _finish_advisory(
        _advisory_body(names, filename, max_reported, lint_summary, findings, scan)
    )


def _missing_body(filename: str) -> str:
    return (
        f"⚠️ skill-manifest: {filename} is missing. "
        "Create it from the skill-maintainer upstream-manifest template."
    )


def _missing_text(filename: str) -> str:
    return _finish_advisory(_missing_body(filename))


def _finish_advisory(text: str) -> str:
    """Keep the advisory-only line as the last line, inside the hard cap."""
    suffix = "\n" + _ADVISORY_ONLY
    body = text
    if body.endswith(suffix):
        body = body[: -len(suffix)]
    room = _HARD_CAP - len(suffix)
    if room < 1:
        return _ADVISORY_ONLY[:_HARD_CAP]
    if len(body) + len(suffix) > _HARD_CAP:
        body = body[:room]
    return body + suffix


def _ensure_session_cache(state: dict) -> None:
    """Load persisted session entries into the in-run cache on first use."""
    global _sessions_loaded
    if _sessions_loaded:
        return
    stored = state.get("advisory_sessions")
    _session_signatures.clear()
    if isinstance(stored, dict):
        for sid, entry in stored.items():
            if isinstance(sid, str) and isinstance(entry, dict):
                _session_signatures[sid] = entry
    _sessions_loaded = True


def _install_sessions(mapping: dict) -> None:
    global _sessions_loaded
    _session_signatures.clear()
    for sid, entry in mapping.items():
        if isinstance(sid, str) and isinstance(entry, dict):
            _session_signatures[sid] = entry
    _sessions_loaded = True


def _pending_key(pending: list[str]) -> tuple[str, ...]:
    return tuple(sorted({name for name in pending if isinstance(name, str)}))


def on_pre_llm_call(session_id: str = "", user_message: str = "", **kw):
    del user_message
    try:
        if kw.get("platform") in {"cron", "subagent"}:
            return None
        if not _deps_ready():
            return None
        if _disabled():
            return None
        if kw.get("is_first_turn"):
            return None
        ctx = _CTX
        if ctx is None:
            return None
        if not _probed:
            _probe()
        sid = session_id if isinstance(session_id, str) else str(session_id)
        with _STATE_LOCK:
            state = _load(ctx)
            pending = [p for p in state["pending"] if isinstance(p, str) and p.strip()]
            summary = state["lint_summary"] if isinstance(state["lint_summary"], dict) else {}
            raw_missing = bool(summary.get("manifest_missing"))
            nag_missing = raw_missing and not state["manifest_missing_prompted"]
            if not pending and not nag_missing:
                return None
            _ensure_session_cache(state)
            current = _pending_key(pending)
            findings = state.get("findings")
            current_key = _finding_key(pending, findings)
            sessions = state.get("advisory_sessions")
            persisted_entry = sessions.get(sid) if isinstance(sessions, dict) else None
            effective = _fresher_entry(persisted_entry, _session_signatures.get(sid))
            if not isinstance(effective, dict):
                inject = True
            else:
                prev_names = effective.get("pending")
                prev_pending = tuple(prev_names) if isinstance(prev_names, list) else ()
                prev_missing = effective.get("missing") is True
                prev_key = effective.get("key")
                if (
                    prev_key is not None
                    and prev_pending == current
                    and prev_missing == raw_missing
                    and prev_key == current_key
                ):
                    return None
                additions = set(current) - set(prev_pending)
                missing_rose = (not prev_missing) and raw_missing
                survivors = set(current) & set(prev_pending)
                if prev_key is None:
                    # Entry predates hashed-key tracking: treat as new (one
                    # extra advisory after upgrade is expected).
                    inject = True
                else:
                    # Re-inject when a name is added, when the
                    # missing-manifest nag newly applies, or when a
                    # surviving name's row moved (digest/reason change or
                    # untracked<->change flip). A pure shrink — names
                    # removed, survivors unchanged — stays silent, as does
                    # a shrink to nothing. Entries that predate per-name
                    # row tracking fall back to the full-key comparison.
                    prev_rows = (
                        effective.get("rows") if isinstance(effective, dict) else None
                    )
                    cur_rows = _finding_rows(list(current), findings)
                    if isinstance(prev_rows, dict) and prev_rows:
                        # Stored rows are 8-hex digests capped at 64 names;
                        # a survivor absent from the map falls back to the
                        # full-key comparison for that name.
                        moved = any(
                            _row_moved(
                                prev_rows,
                                name,
                                cur_rows.get(name),
                                prev_key,
                                current_key,
                            )
                            for name in survivors
                        )
                    else:
                        moved = prev_key != current_key and bool(survivors)
                    inject = (
                        bool(additions)
                        or (missing_rose and nag_missing)
                        or moved
                    )
            text = None
            attempted_missing = False
            delivered_missing = False
            if inject:
                filename = _manifest_filename(ctx)
                if pending:
                    scan_state = state.get("scan")
                    body = _advisory_body(
                        pending,
                        filename,
                        _max_reported(ctx),
                        summary,
                        findings,
                        scan_state,
                    )
                    if nag_missing:
                        body = body + "\n" + _missing_body(filename)
                        attempted_missing = True
                    text = _finish_advisory(body)
                else:
                    text = _missing_text(filename)
                    attempted_missing = True
                if attempted_missing and _missing_body(filename) in text:
                    delivered_missing = True
                    state["manifest_missing_prompted"] = True
            entry_missing = delivered_missing if attempted_missing else raw_missing
            entry = _session_entry(
                current,
                entry_missing,
                _entry_timestamp(effective, current, entry_missing),
                current_key,
                _finding_rows(list(current), findings),
            )
            merged = _merge_advisory_sessions(
                state.get("advisory_sessions"), _session_signatures, sid, entry
            )
            state["advisory_sessions"] = merged
            _save(ctx, state)
            _install_sessions(merged)
            if text is None:
                return None
            return {"context": text}
    except Exception:
        _warn_once("pre_llm_call", "pre_llm_call failed")
        return None


CLI_HELP = "Inspect skill-manifest drift and acknowledge reviewed changes."


def acks_path() -> Path:
    """Location of acks.json. The hook only reads it; only the ack CLI writes it."""
    try:
        if acks is not None:
            return Path(acks.default_acks_path())
    except Exception:
        pass
    env = os.environ.get("HERMES_HOME", "").strip()
    base = Path(env).expanduser() if env else Path.home() / ".hermes"
    return base / "plugin-data" / "skill-manifest" / "acks.json"


def render_status(state: dict, *, manifest_path: str = "", missing: int = 0) -> str:
    """Human-readable status table for `hermes skill-manifest status`."""
    findings = state.get("findings")
    if not isinstance(findings, dict):
        findings = {}
    scan = state.get("scan")
    if not isinstance(scan, dict):
        scan = {}
    dismissed = state.get("dismissed")
    if not isinstance(dismissed, list):
        dismissed = []
    untracked = sum(
        1
        for entry in findings.values()
        if isinstance(entry, dict) and entry.get("reason") == "untracked"
    )
    changed = sum(
        1
        for entry in findings.values()
        if isinstance(entry, dict) and entry.get("reason") == "changed"
    )
    mismatched = sum(
        1
        for entry in findings.values()
        if isinstance(entry, dict) and entry.get("reason") == "version-mismatch"
    )
    skill_errors = scan.get("skill_errors")
    if not isinstance(skill_errors, dict):
        skill_errors = {}
    lines = [
        "skill-manifest status",
        f"manifest: {manifest_path or '(unknown)'}",
        f"last_ok: {scan.get('last_ok_ts', 0.0)}",
        f"last_attempt: {scan.get('last_attempt_ts', 0.0)}",
        f"complete: {bool(scan.get('complete'))}",
        f"deferred: {scan.get('deferred', 0)}",
        f"error: {scan.get('error', '')}",
        f"untracked: {untracked}  changed: {changed}  version-mismatch: {mismatched}",
        f"missing: {missing}  dismissed: {len(dismissed)}",
    ]
    if skill_errors:
        lines.append(f"skill_errors: {len(skill_errors)}")
        for name in sorted(skill_errors)[:5]:
            lines.append(f"  {name}: {skill_errors[name]}")
    for entry in sorted(
        (e for e in findings.values() if isinstance(e, dict)),
        key=lambda e: str(e.get("name") or "").lower(),
    ):
        name = entry.get("name")
        reason = entry.get("reason")
        if not isinstance(name, str) or not name.strip():
            continue
        if reason not in ("untracked", "changed", "version-mismatch"):
            continue
        digest = entry.get("digest")
        sha8 = digest[:8] if isinstance(digest, str) and digest else "-"
        lines.append(f"{name}  {reason}  {sha8}")
    return "\n".join(lines)


def cli_setup(parser):
    """Argparse setup for `hermes skill-manifest ...`. Receives the subparser."""
    subs = parser.add_subparsers(dest="skill_manifest_cmd")
    subs.add_parser("status", help="Show drift status and change findings.")
    ack_parser = subs.add_parser("ack", help="Acknowledge a reviewed skill digest.")
    ack_parser.add_argument("name", help="Skill name.")
    ack_parser.add_argument(
        "--expect", required=True, help="Expected live digest prefix (8-64 hex)."
    )
    ack_parser.add_argument("--note", default="", help="Optional review note.")
    return parser


def _resolve_skill_dir(ctx, name):
    try:
        root = _skills_root(ctx)
    except Exception:
        return None
    if fingerprint is None:
        return None
    try:
        dirs = fingerprint.list_skill_dirs(root)
    except Exception:
        return None
    if not isinstance(dirs, dict):
        return None
    key = str(name or "").strip().lower()
    if not key:
        return None
    for raw_key, path in dirs.items():
        if isinstance(raw_key, str) and raw_key.lower() == key:
            return path
    return None


def _do_ack(name, expect, note=""):
    """Shared ack core for the CLI and slash handlers. Returns (text, rc)."""
    ctx = _CTX
    if ctx is None or acks is None or fingerprint is None:
        return "skill-manifest ack unavailable (plugin not ready).", 1
    clean = str(name or "").strip()
    if not clean:
        return "usage: hermes skill-manifest ack <name> --expect <hex> [--note TEXT]", 1
    skill_dir = _resolve_skill_dir(ctx, clean)
    if skill_dir is None:
        return f"refused: skill {clean} not found on disk.", 1
    try:
        result = acks.acknowledge(
            acks_path(),
            skill_dir,
            clean,
            expect,
            str(note or ""),
            max_files=_max_files_per_skill(ctx),
            max_bytes=_max_bytes_per_skill(ctx),
        )
    except Exception as exc:
        _warn_once("cli-ack", "skill-manifest ack failed")
        return f"refused: ack failed ({type(exc).__name__}).", 1
    if isinstance(result, dict) and result.get("ok"):
        digest = result.get("digest")
        sha8 = digest[:8] if isinstance(digest, str) else ""
        # R9 O1/O2: a successful ack touches only a `changed` finding for
        # its own key. The digest was verified equal to the live digest
        # by `acknowledge`, so the ack is authoritative for content — but
        # a `version-mismatch` finding sits exactly on the acked digest
        # and means the declared version still disagrees with the
        # manifest row, so it stays until versions agree (O1). A
        # `changed` finding for a key with no manifest row must not
        # vanish: the name pass already marked it `untracked-snapshot`,
        # so deletion would silence it forever. It becomes `untracked`
        # instead and `pending` is re-derived (O2). Other keys untouched.
        try:
            with _STATE_LOCK:
                state = _load(ctx)
                findings = state.get("findings")
                key = clean.lower()
                current = (
                    findings.get(key) if isinstance(findings, dict) else None
                )
                if (
                    isinstance(current, dict)
                    and current.get("reason") == "changed"
                ):
                    manifested = False
                    try:
                        if manifest_db is not None:
                            root = _skills_root(ctx)
                            doc = manifest_db.load_manifest(
                                root / _manifest_filename(ctx)
                            )
                            manifested = manifest_db.is_manifested(doc, clean)
                    except Exception:
                        _warn_once(
                            "cli-ack-state",
                            "skill-manifest ack manifest check failed",
                        )
                        manifested = False
                    if manifested:
                        del findings[key]
                    else:
                        seen = current.get("first_seen_ts")
                        if not (
                            isinstance(seen, (int, float))
                            and not isinstance(seen, bool)
                        ):
                            seen = time.time()
                        name = current.get("name")
                        if not (
                            isinstance(name, str) and name.strip()
                        ):
                            name = clean
                        findings[key] = {
                            "name": name,
                            "reason": "untracked",
                            "digest": "",
                            "files": 0,
                            "truncated": False,
                            "first_seen_ts": float(seen),
                        }
                    _derive_pending(state)
                    _save(ctx, state)
        except Exception:
            _warn_once("cli-ack-state", "skill-manifest ack state cleanup failed")
        return f"acked {clean} {sha8}", 0
    message = ""
    if isinstance(result, dict):
        message = result.get("message") or ""
    return str(message or "refused."), 1


def cli_handler(args) -> int:
    """Argparse handler for `hermes skill-manifest ...`. Returns process rc."""
    try:
        cmd = getattr(args, "skill_manifest_cmd", None)
        if cmd == "ack":
            text, rc = _do_ack(
                getattr(args, "name", ""),
                getattr(args, "expect", ""),
                getattr(args, "note", ""),
            )
            print(text)
            return rc
        ctx = _CTX
        if ctx is None:
            print("skill-manifest status unavailable (plugin not ready).")
            return 1
        with _STATE_LOCK:
            state = _load(ctx)
        manifest_path = ""
        missing_count = 0
        try:
            root = _skills_root(ctx)
            manifest_path = str(root / _manifest_filename(ctx))
            if fingerprint is not None and manifest_db is not None:
                dirs = fingerprint.list_skill_dirs(root) or {}
                lows = {
                    k.lower() for k in dirs if isinstance(k, str)
                }
                doc = manifest_db.load_manifest(root / _manifest_filename(ctx))
                man = {m.lower() for m in (doc.skills or set()) if isinstance(m, str)}
                missing_count = len([m for m in man if m not in lows])
        except Exception:
            _warn_once("cli-status", "skill-manifest status inventory failed")
        print(
            render_status(state, manifest_path=manifest_path, missing=missing_count)
        )
        return 0
    except Exception:
        _warn_once("cli", "skill-manifest cli failed")
        print("skill-manifest command failed.")
        return 1


def slash_skill_manifest_ack(raw_args: str):
    """In-session handler for /skill-manifest-ack <name> <hex>. Never raises."""

    def _fail(message: str):
        return message

    try:
        parts = str(raw_args or "").split()
        if len(parts) < 2:
            return _fail("usage: /skill-manifest-ack <name> <hex>")
        name, expect = parts[0], parts[1]
        note = " ".join(parts[2:])
        if note.startswith("--note"):
            note = note[len("--note"):].strip()
        text, _rc = _do_ack(name, expect, note)
        return text
    except Exception:
        _warn_once("slash-ack", "skill-manifest slash ack failed")
        return _fail("skill-manifest ack failed.")
