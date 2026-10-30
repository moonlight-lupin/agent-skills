"""Content fingerprints for manifested skills (change tracking).

Stdlib only. No imports from hooks.py. All functions fail open.

Enumeration is lazy and globally sorted: both `quick_signature` and
`content_digest` consume the same canonical file stream
(`_iter_sorted_skill_files`) and stop at `max_files`, so a capped
signature and a capped digest always cover the same file set. Only one
directory is listed at a time; directories past the cap are never opened.

A file larger than `max_file_bytes` is never content-hashed. It still
contributes a deterministic `BIG\\0{relpath}\\0{size}\\n` line to the digest
input and consumes one `max_files` slot, but its size does NOT count toward
`bytes`; the digest is marked `truncated`. File reads use a bounded loop
capped at `max_file_bytes`, so a file growing during the read cannot blow
the cap. `declared_version` reads at most the first 8192 bytes of
`SKILL.md`. Any enumeration failure (`os.scandir`/`stat`, or a link
predicate — `islink`/`realpath`/containment, or the link-target
`os.stat` — that raises `OSError`) or file that cannot be hashed aborts
the whole skill:
the digest is `""` with `error="read"` (a partial digest is never
reported as success). An empty
canonical file set (empty or fully pruned skill dir) yields `digest=""`,
`files=0`, `truncated=False` so callers can treat the skill as not
examined. When the first included file alone exceeds `max_bytes`, its
`BIG` marker is emitted (one file slot, `truncated=True`) instead of
zero files.
"""
from __future__ import annotations

import hashlib
import heapq
import itertools
import os
import re
import stat
from pathlib import Path

_DEPTH_CAP = 12

# Mirrors probe.EXCLUDED_DIR_NAMES for skill discovery.
EXCLUDED_DIR_NAMES = {
    ".archive",
    ".curator_backups",
    "__pycache__",
    ".hub",
    ".pytest_cache",
}

# Directory names never hashed into a content digest.
_CONTENT_PRUNE_DIRS = frozenset({"__pycache__", ".pytest_cache", ".git"})

_FRONT_MATTER_RE = re.compile(
    r"\A[ \t]*---[ \t]*\r?\n(.*?)\r?\n[ \t]*---[ \t]*(?:\r?\n|\Z)",
    re.DOTALL,
)
_VERSION_RE = re.compile(r"^\s*version\s*:\s*(.+?)\s*$", re.MULTILINE)


class _EnumerationFailed(Exception):
    """An os.scandir/stat failure while enumerating a skill. Never swallowed
    into a partial digest: callers abort the skill with error="read"."""


def _pruned(name: str) -> bool:
    return (
        name in EXCLUDED_DIR_NAMES
        or name.startswith(".")
        or name.startswith("retired-")
    )


class SkillDirs(dict):
    """Lower-case skill name to the directory holding its SKILL.md.

    A plain dict subclass, so existing mapping call sites keep working, with
    an `errors` list carrying enumeration failure codes. Any entry means the
    walk was partial and the caller must treat the inventory as untrusted.
    """

    def __init__(self, *args, errors=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.errors: list[str] = list(errors)


def list_skill_dirs(skills_root: Path) -> SkillDirs:
    """Map lower-case skill name to the directory holding its SKILL.md.

    Same traversal rules as probe.list_skill_names: prune archived/hidden
    trees, follow symlinks with a visited-realpath ancestor guard and a
    depth cap. First directory in sorted-path order wins a case collision.
    Missing or unreadable roots return an empty mapping (fail-open).

    Every enumeration failure is recorded in the returned mapping's
    `errors` list: an `os.walk` `onerror` callback, a `resolve` failure, or
    an unreadable directory each append a code. A non-empty `errors` list
    means the inventory is partial.
    """
    try:
        root = Path(skills_root)
        if not root.is_dir():
            return SkillDirs()
        if root.name in EXCLUDED_DIR_NAMES:
            return SkillDirs()
        found: dict[str, Path] = {}
        problems: list[str] = []

        def _onerror(exc) -> None:
            problems.append("walk-error")

        stack: list[str] = []
        for dirpath, dirnames, filenames in os.walk(
            root, followlinks=True, onerror=_onerror
        ):
            p = Path(dirpath)
            try:
                depth = len(p.relative_to(root).parts)
            except ValueError:
                dirnames[:] = []
                continue
            try:
                resolved = str(p.resolve())
            except OSError:
                problems.append("resolve-error")
                dirnames[:] = []
                continue
            del stack[depth:]
            if resolved in stack:
                dirnames[:] = []
                continue
            stack.append(resolved)
            dirnames[:] = sorted(d for d in dirnames if not _pruned(d))
            if depth >= _DEPTH_CAP:
                dirnames[:] = []
            if "SKILL.md" in filenames:
                key = p.name.lower()
                if key not in found:
                    found[key] = p
        return SkillDirs(found, errors=problems)
    except Exception:
        return SkillDirs(errors=["walk-error"])


def _content_pruned_dir(name: str) -> bool:
    return name in _CONTENT_PRUNE_DIRS or name.startswith("retired-")


def _content_skipped_file(rel_parts: tuple[str, ...], name: str) -> bool:
    if name == ".DS_Store":
        return True
    if name.endswith(".pyc") or name.endswith(".pyo"):
        return True
    return any(part.startswith("retired-") for part in rel_parts)


def _iter_sorted_skill_files(skill_dir: Path, *, followlinks: bool = True):
    """Yield (rel_posix, path_or_None, is_link) in globally sorted order, lazily.

    One canonical stream for `quick_signature` and `content_digest`: entries
    sort by relpath tuple, directories are listed one at a time (each
    directory's entries are sorted on listing), and directory symlinks that
    resolve inside the skill dir are merged into the same order with a
    per-stream ancestor-realpath cycle guard and the shared depth cap.
    Pruned dirs are never descended, skipped files are never yielded, and
    links escaping the skill dir surface as `("__outside_link__", None,
    True)`. Callers stop pulling at their cap, so unvisited directories are
    never opened.
    """
    try:
        base = skill_dir.resolve()
    except OSError:
        return
    try:
        if not Path(skill_dir).is_dir():
            return
    except OSError:
        return
    counter = itertools.count()
    heap: list = []

    def _push_dir(dir_path: Path, rel_parts: tuple[str, ...], ancestors: tuple):
        try:
            with os.scandir(dir_path) as handle:
                names = sorted(entry.name for entry in handle)
        except OSError as exc:
            raise _EnumerationFailed(str(dir_path)) from exc
        for name in names:
            child = rel_parts + (name,)
            heapq.heappush(
                heap,
                (
                    "/".join(child),
                    next(counter),
                    dir_path,
                    name,
                    ancestors,
                    child,
                ),
            )

    _push_dir(Path(skill_dir), (), (str(base),))
    while heap:
        rel, _, dir_path, name, ancestors, rel_parts = heapq.heappop(heap)
        child_rel = rel_parts
        full = os.path.join(dir_path, name)
        # J3: predicate failures are enumeration errors, not skips. A
        # link whose nature, target, containment, or kind cannot be
        # determined aborts the skill (the caller reports error="read")
        # instead of yielding a partial digest as success. Deliberate
        # non-error skips (pruned names, depth cap, visited ancestors,
        # out-of-tree links) still `continue` below.
        try:
            is_link = os.path.islink(full)
        except OSError as exc:
            raise _EnumerationFailed(full) from exc
        if is_link:
            if not followlinks:
                continue
            try:
                target = Path(os.path.realpath(full))
            except OSError as exc:
                raise _EnumerationFailed(full) from exc
            try:
                inside = target == base or base in target.parents
            except OSError as exc:
                raise _EnumerationFailed(full) from exc
            if not inside:
                yield ("__outside_link__", None, True)
                continue
            # R7 M2: the target kind comes from one stat call. The
            # `is_dir()`/`is_file()` predicates swallow OSError into False
            # on some interpreters, which silently skipped the entry and
            # reported a partial digest as success. Any OSError here aborts
            # the skill instead.
            try:
                target_st = os.stat(target)
            except OSError as exc:
                raise _EnumerationFailed(str(target)) from exc
            if stat.S_ISDIR(target_st.st_mode):
                if len(child_rel) >= _DEPTH_CAP:
                    continue
                real = str(target)
                if real in ancestors:
                    continue
                _push_dir(target, child_rel, ancestors + (real,))
                continue
            if stat.S_ISREG(target_st.st_mode):
                yield (rel, target, True)
            continue
        # K2: the entry type comes from one lstat-style call. Any OSError
        # (including FileNotFoundError for a listed-but-vanished entry, or
        # EACCES) aborts the skill: the digest would otherwise be partial.
        # `os.path.isdir/isfile` swallow OSError into False, which silently
        # dropped whole subtrees as success. Deliberate non-error skips
        # (pruned names/files, depth cap, visited ancestors) still continue.
        try:
            st = os.stat(full, follow_symlinks=False)
        except OSError as exc:
            raise _EnumerationFailed(full) from exc
        if stat.S_ISDIR(st.st_mode):
            if _content_pruned_dir(name):
                continue
            if len(child_rel) >= _DEPTH_CAP:
                continue
            sub = Path(full)
            # L3: a resolve failure on an ordinary subdirectory is an
            # enumeration error, not a silent subtree drop.
            try:
                real = str(sub.resolve())
            except OSError as exc:
                raise _EnumerationFailed(str(sub)) from exc
            if real in ancestors:
                continue
            _push_dir(sub, child_rel, ancestors + (real,))
            continue
        if not stat.S_ISREG(st.st_mode):
            continue
        if _content_skipped_file(child_rel, name):
            continue
        yield (rel, Path(full), False)


# Prefix of the deterministic marker row a stat-failed relpath
# contributes to the quick-signature rows (R14 T3). Any such row makes
# `quick_signature` return `""` (R16 V1), so a marker is never hashed
# into a stored signature.
_FAIL_MARKER_PREFIX = "FAIL\0"


def _quick_signature_rows(
    skill_dir: Path, *, max_files: int = 400, followlinks: bool = True
) -> list[str]:
    """Stat-only rows hashed by `quick_signature` (FAIL markers included)."""
    rows: list[str] = []
    files = 0
    truncated = False
    for rel, path, is_link in _iter_sorted_skill_files(
        skill_dir, followlinks=followlinks
    ):
        if path is None:
            continue
        if files >= max_files:
            truncated = True
            break
        try:
            if followlinks or not is_link:
                st = os.stat(path)
            else:
                st = os.lstat(path)
        except OSError:
            # R14 T3: a stat failure is input, not a skip. The marker
            # moves the signature so the skill is re-examined (the
            # digest's own stat failure then aborts it with
            # error="read") instead of short-circuiting on a stale
            # equal signature while reporting ok.
            rows.append(f"{_FAIL_MARKER_PREFIX}{rel}\n")
            files += 1
            continue
        rows.append(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n")
        files += 1
    rows.sort()
    if truncated:
        rows.append(f"TRUNCATED\0{files}\n")
    return rows


def quick_signature(
    skill_dir: Path, *, max_files: int = 400, followlinks: bool = True
) -> str:
    """Cheap stat-only signature; no file reads.

    A file whose stat fails contributes a deterministic `FAIL` marker
    row (R14 T3), and any such row makes the whole signature the empty
    string `""` (R16 V1): an empty quick signature means "the tree
    could not be fully stat'd; always re-hash". An empty current
    signature never equals a stored non-empty one, so the digest is
    recomputed (this still satisfies T3). Callers must never take the
    short circuit when the current signature is empty, regardless of
    the stored value. Single traversal: the rows are built once and no
    second walk is needed to detect the failure."""
    try:
        rows = _quick_signature_rows(
            skill_dir, max_files=max_files, followlinks=followlinks
        )
        if any(row.startswith(_FAIL_MARKER_PREFIX) for row in rows):
            return ""
        return hashlib.sha256("".join(rows).encode("utf-8")).hexdigest()
    except Exception:
        return ""


_READ_CHUNK = 262144
_VERSION_HEAD_BYTES = 8192


def _bounded_file_hash(path: Path, cap_bytes: int) -> tuple[str | None, bool]:
    """Hash at most `cap_bytes` of `path`. Returns (hex, grew_past_cap)."""
    hasher = hashlib.sha256()
    read_total = 0
    try:
        with open(path, "rb") as handle:
            while True:
                want = min(_READ_CHUNK, cap_bytes + 1 - read_total)
                chunk = handle.read(want)
                if not chunk:
                    return hasher.hexdigest(), False
                hasher.update(chunk)
                read_total += len(chunk)
                if read_total > cap_bytes:
                    return hasher.hexdigest(), True
    except OSError:
        return None, False


def content_digest(
    skill_dir: Path,
    *,
    max_files: int = 400,
    max_bytes: int = 8_000_000,
    max_file_bytes: int = 2_000_000,
) -> dict:
    """Stable content digest over file bytes (no mtimes, no absolute paths).

    Consumes the canonical sorted stream lazily and stops at `max_files`
    (directories past the cap are never opened). `max_bytes` is a running
    total checked BEFORE hashing: once adding another file would exceed it,
    that file is skipped and the digest is marked `truncated` — except the
    first included file, which is emitted as a `BIG` marker (one file slot,
    `truncated=True`) so the skill never ends with zero files. A file
    larger than `max_file_bytes` contributes a
    `BIG\\0{relpath}\\0{size}\\n` line instead of a content hash; it consumes
    a `max_files` slot but not `max_bytes`. Any enumeration failure
    (`os.scandir`/`stat`/subdirectory resolve) or file read failure
    aborts the skill with `digest=""` and `error="read"`. An empty
    canonical file set yields `digest=""` with `error=""`.
    """
    try:
        lines: list[str] = []
        files = 0
        total = 0
        truncated = False
        skipped = 0
        for rel, path, _is_link in _iter_sorted_skill_files(skill_dir):
            if path is None:
                skipped += 1
                continue
            if files >= max_files:
                truncated = True
                break
            try:
                st = path.stat()
            except OSError as exc:
                raise _EnumerationFailed(str(path)) from exc
            # N2: the type comes from the `st` already obtained. A second
            # `is_file()` call here could flip (permission change or race)
            # and silently drop the file from a digest reported as
            # success. A non-regular file (FIFO, socket, device) is a
            # deliberate skip, counted in `skipped`.
            if not stat.S_ISREG(st.st_mode):
                skipped += 1
                continue
            size = st.st_size
            if size > max_file_bytes:
                lines.append(f"BIG\0{rel}\0{size}\n")
                files += 1
                truncated = True
                continue
            if total + size > max_bytes:
                if files == 0:
                    # The first included file alone exceeds the byte
                    # budget: emit its BIG marker (one file slot,
                    # truncated) instead of zero files, which could
                    # never clear.
                    lines.append(f"BIG\0{rel}\0{size}\n")
                    files += 1
                    truncated = True
                    continue
                truncated = True
                break
            file_hex, grew = _bounded_file_hash(path, max_file_bytes)
            if file_hex is None:
                return {
                    "digest": "",
                    "files": 0,
                    "bytes": 0,
                    "truncated": False,
                    "skipped": skipped,
                    "error": "read",
                }
            if grew:
                truncated = True
            lines.append(f"{rel}\0{size}\0{file_hex}\n")
            files += 1
            total += size
        if files == 0:
            # Nothing was hashed (empty set, or every file skipped by the
            # budget): no digest at all, so callers treat the skill as not
            # examined rather than adopting a constant marker-only digest.
            return {
                "digest": "",
                "files": 0,
                "bytes": 0,
                "truncated": False,
                "skipped": skipped,
                "error": "",
            }
        if truncated:
            lines.append(f"TRUNCATED\0{files}\0{total}\n")
        digest = hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()
        return {
            "digest": digest,
            "files": files,
            "bytes": total,
            "truncated": truncated,
            "skipped": skipped,
            "error": "",
        }
    except Exception:
        return {
            "digest": "",
            "files": 0,
            "bytes": 0,
            "truncated": False,
            "skipped": 0,
            "error": "read",
        }


def declared_version(skill_md: Path) -> str:
    """Return the `version:` value from the first front-matter block, or ""."""
    try:
        with open(skill_md, "rb") as handle:
            raw = handle.read(_VERSION_HEAD_BYTES)
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return ""
    match = _FRONT_MATTER_RE.match(text)
    if not match:
        return ""
    version = _VERSION_RE.search(match.group(1))
    if not version:
        return ""
    value = version.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value
