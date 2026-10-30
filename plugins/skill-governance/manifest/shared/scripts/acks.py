"""Fingerprint-bound acknowledgments for changed manifested skills.

The hook ONLY reads acks.json. Only the ack CLI writes it. Stdlib only;
no imports from hooks.py (hooks.py imports this module, not vice versa).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

try:
    from . import fingerprint as fingerprint_mod
except ImportError:
    import importlib.util as _ilu
    import sys as _sys

    _fp_file = Path(__file__).resolve().parent / "fingerprint.py"
    fingerprint_mod = None
    try:
        if _fp_file.is_file():
            _fp_key = "skill_manifest_fingerprint_acks"
            _fp_spec = _ilu.spec_from_file_location(_fp_key, str(_fp_file))
            if _fp_spec is not None and _fp_spec.loader is not None:
                _fp_mod = _ilu.module_from_spec(_fp_spec)
                _sys.modules[_fp_key] = _fp_mod
                _fp_spec.loader.exec_module(_fp_mod)
                fingerprint_mod = _fp_mod
    except Exception:
        fingerprint_mod = None

ACKS_VERSION = 1
_EXPECT_RE = re.compile(r"^[0-9a-f]{8,64}$")

# Mirrors the hook's scan caps so acknowledge() fingerprints the same file
# set as the advisory digest. Callers (CLI/slash) must pass the configured
# values through; the defaults here match the hook defaults exactly.
_DEFAULT_MAX_FILES = 400
_DEFAULT_MAX_BYTES = 8_000_000

# Bounded lock retry: a contended acks lock refuses instead of blocking forever.
_ACK_LOCK_TIMEOUT_S = 5.0
_ACK_LOCK_POLL_S = 0.05


def hermes_home() -> Path:
    """Resolve the Hermes home: hermes_constants, HERMES_HOME, then ~/.hermes."""
    try:
        import hermes_constants

        return Path(hermes_constants.get_hermes_home())
    except Exception:
        pass
    env = os.environ.get("HERMES_HOME", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".hermes"


def default_acks_path(home: Path | None = None) -> Path:
    base = Path(home) if home is not None else hermes_home()
    return base / "plugin-data" / "skill-manifest" / "acks.json"


def _empty_doc() -> dict:
    return {"version": ACKS_VERSION, "acks": {}}


def _is_well_formed_entry(entry) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("digest"), str)
        and bool(entry.get("digest"))
    )


def _coerce_doc(raw) -> dict:
    if not isinstance(raw, dict):
        return _empty_doc()
    acks = raw.get("acks")
    if not isinstance(acks, dict):
        return _empty_doc()
    out: dict = {}
    for key, entry in acks.items():
        if not isinstance(key, str):
            continue
        if _is_well_formed_entry(entry):
            low = key.strip().lower()
            if not low:
                continue
            # Preserve the whole entry shape (including unknown fields).
            out[low] = dict(entry)
        else:
            # Not coercible: keep verbatim under the original key so a merge
            # never silently drops it.
            out[key] = entry
    return {"version": ACKS_VERSION, "acks": out}


def load_acks(path) -> dict:
    """Read acks.json; missing/corrupt files (or concurrent replace) yield empty."""
    try:
        raw = Path(path).read_bytes()
    except Exception:
        return _empty_doc()
    try:
        return _coerce_doc(json.loads(raw.decode("utf-8", errors="replace")))
    except Exception:
        return _empty_doc()


def _acquire_with_retry(fd, timeout_s: float = _ACK_LOCK_TIMEOUT_S) -> str:
    """Non-blocking flock with a bounded retry.

    Returns "ok" when the lock is held, "locked" when still contended after
    the timeout, or "unavailable" when flock itself is missing/broken.
    Callers must refuse without writing on anything but "ok": an ack
    written without the lock can silently drop a concurrent ack.
    """
    try:
        import fcntl
    except ImportError:
        return "unavailable"
    try:
        timeout = float(timeout_s)
    except (TypeError, ValueError):
        timeout = _ACK_LOCK_TIMEOUT_S
    if timeout != timeout:  # NaN
        timeout = _ACK_LOCK_TIMEOUT_S
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return "ok"
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return "locked"
            time.sleep(_ACK_LOCK_POLL_S)
        except (ImportError, OSError):
            return "unavailable"


def _release(fd) -> None:
    try:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)
    except Exception:
        pass


class _BackupFailed(Exception):
    """Raised when the corrupt-file backup cannot be written. Never swallowed."""


def _corrupt_backup_path(target: Path) -> Path:
    """Stamped backup path, suffixed when the stamp already exists."""
    candidate = Path(f"{target}.corrupt.{time.time_ns()}")
    suffix = 0
    while candidate.exists():
        suffix += 1
        candidate = Path(f"{candidate}.{suffix}")
    return candidate


def _read_doc_and_recovered(target: Path) -> tuple[dict, bool, str]:
    """Coerce the single read of the current doc. No second read.

    Returns (doc, recovered, backup_path). Only a missing file yields an
    empty doc with recovered False: any other first-read failure raises so
    the caller refuses without writing (merging into an empty doc would
    replace the existing acks). A present-but-unparseable file, or a valid
    JSON document with the wrong shape (not a dict, or `acks` not a dict),
    is copied to `<name>.corrupt.<time_ns>` (numeric suffix on collision)
    and yields an empty doc with recovered True; a backup write failure
    raises `_BackupFailed` so the caller refuses without writing. Once the
    bytes are in hand no further read can fail.
    """
    try:
        raw = target.read_bytes()
    except FileNotFoundError:
        return _empty_doc(), False, ""
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception:
        parsed = None
    if not isinstance(parsed, dict) or not isinstance(parsed.get("acks"), dict):
        backup = _corrupt_backup_path(target)
        try:
            backup.write_bytes(raw)
        except OSError as exc:
            raise _BackupFailed(str(backup)) from exc
        return _empty_doc(), True, str(backup)
    return _coerce_doc(parsed), False, ""


def _atomic_write_json(target: Path, doc: dict) -> None:
    """Same-directory temp file, flush + fsync, os.replace. Cleans up on failure."""
    parent = target.parent
    tmp = parent / f".acks.{os.getpid()}.{hashlib.sha1(os.urandom(8)).hexdigest()[:8]}.tmp"
    try:
        with open(str(tmp), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc, indent=2, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(tmp), str(target))
    except Exception:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def acknowledge(
    path,
    skill_dir,
    name: str,
    expect: str,
    note: str = "",
    now: float | None = None,
    max_files: int = _DEFAULT_MAX_FILES,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> dict:
    """Bind an acknowledgment to the live content digest of a skill.

    The live digest is computed with `max_files`/`max_bytes` so it matches
    the advisory digest produced under the same configured caps. Returns
    {"ok": True, "code": "acked", "digest": live} on success and
    {"ok": False, "code": <stale|invalid|missing|locked|unavailable|read-error|backup-failed|error>, ...}
    otherwise. A refusal never writes. The lock must be held: a missing or
    broken flock refuses with `unavailable`. A read failure other than a
    missing file refuses with `read-error`; a corrupt-backup write failure
    refuses with `backup-failed`. A corrupt existing file is backed up to
    `acks.json.corrupt.<time_ns>` (numeric suffix on collision) and reported
    with `recovered: true`.
    """
    try:
        max_files_n = int(max_files)
    except (TypeError, ValueError):
        max_files_n = _DEFAULT_MAX_FILES
    if max_files_n < 1:
        max_files_n = _DEFAULT_MAX_FILES
    try:
        max_bytes_n = int(max_bytes)
    except (TypeError, ValueError):
        max_bytes_n = _DEFAULT_MAX_BYTES
    if max_bytes_n < 1:
        max_bytes_n = _DEFAULT_MAX_BYTES
    target = Path(path)
    wanted = str(expect or "").strip().lower()
    if not _EXPECT_RE.fullmatch(wanted):
        return {
            "ok": False,
            "code": "invalid",
            "message": f"refused: expect must be 8-64 lowercase hex chars, got {str(expect)!r}",
        }
    live: dict | None = None
    try:
        if fingerprint_mod is None:
            raise RuntimeError("fingerprint module unavailable")
        live = fingerprint_mod.content_digest(
            Path(skill_dir), max_files=max_files_n, max_bytes=max_bytes_n
        )
    except Exception as exc:
        return {
            "ok": False,
            "code": "error",
            "message": f"refused: could not fingerprint {name}: {type(exc).__name__}",
        }
    digest = str((live or {}).get("digest") or "")
    if not digest:
        return {
            "ok": False,
            "code": "missing",
            "message": f"refused: skill {name} has no readable content on disk",
        }
    if not digest.startswith(wanted):
        return {
            "ok": False,
            "code": "stale",
            "digest": digest,
            "message": (
                f"refused: live digest for {name} is {digest} "
                f"(sha {digest[:8]}), which does not start with {wanted}"
            ),
        }
    key = str(name or "").strip().lower()
    if not key:
        return {"ok": False, "code": "invalid", "message": "refused: empty skill name"}
    stamp = float(now) if isinstance(now, (int, float)) else time.time()
    entry = {
        "digest": digest,
        "ts": stamp,
        "note": str(note or ""),
        "files": int((live or {}).get("files") or 0),
        "truncated": bool((live or {}).get("truncated")),
    }
    try:
        parent = target.parent
        parent.mkdir(parents=True, exist_ok=True)
        lock_path = Path(str(target) + ".lock")
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            locked = _acquire_with_retry(fd, _ACK_LOCK_TIMEOUT_S)
            if locked == "locked":
                return {
                    "ok": False,
                    "code": "locked",
                    "message": f"refused: {target} is locked by another ack",
                }
            if locked != "ok":
                return {
                    "ok": False,
                    "code": "unavailable",
                    "message": "refused: ack locking unavailable",
                }
            try:
                doc, recovered, _backup = _read_doc_and_recovered(target)
            except _BackupFailed as exc:
                return {
                    "ok": False,
                    "code": "backup-failed",
                    "message": f"refused: could not back up {target}: {exc}",
                }
            except OSError as exc:
                return {
                    "ok": False,
                    "code": "read-error",
                    "message": f"refused: could not read {target}: {type(exc).__name__}",
                }
            acks_map = doc.get("acks")
            if not isinstance(acks_map, dict):
                acks_map = {}
                doc["acks"] = acks_map
            acks_map[key] = entry
            _atomic_write_json(target, doc)
        finally:
            _release(fd)
            os.close(fd)
    except Exception as exc:
        return {
            "ok": False,
            "code": "error",
            "message": f"refused: could not write {target}: {type(exc).__name__}",
        }
    result: dict = {"ok": True, "code": "acked", "digest": digest}
    if recovered:
        result["recovered"] = True
    return result
