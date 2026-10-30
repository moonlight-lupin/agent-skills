"""Inventory SKILL.md directories and compute pending/gone arrivals."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path


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
    stays a valid identifier.
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


# Package load shares the plugin manifest_db via the relative import. A
# path-loaded module has no parent, so load this plugin's file under one
# canonical name keyed by its resolved path. A bare `import manifest_db`
# would bind a decoy that an earlier sys.path entry already imported.
try:
    from ... import manifest_db
except ImportError:
    _siblings = Path(__file__).resolve().parent
    _mdb_path = _siblings.parent.parent / "manifest_db.py"
    if _mdb_path.is_file():
        manifest_db = _load_by_path("skill_manifest_manifest_db", str(_mdb_path))
    else:
        raise

# Sibling content-fingerprint module. Package load shares it via the
# relative import; a path-loaded module falls back to loading the sibling
# file by path. Either failure leaves the name for a legacy inline walk so
# `import probe` and list_skill_names keep working without it.
try:
    from . import fingerprint as fingerprint_mod
except ImportError:
    try:
        _fp_path = Path(__file__).resolve().parent / "fingerprint.py"
        if _fp_path.is_file():
            fingerprint_mod = _load_by_path(
                "skill_manifest_fingerprint", str(_fp_path)
            )
        else:
            fingerprint_mod = None
    except Exception:
        fingerprint_mod = None

EXCLUDED_DIR_NAMES = {
    ".archive",
    ".curator_backups",
    "__pycache__",
    ".hub",
    ".pytest_cache",
}


def list_skill_names_report(skills_root: Path) -> tuple[set[str], list[str]]:
    """Return original-case skill names plus the walk error list.

    Names come from `fingerprint.list_skill_dirs` (original-case leaf names
    of directories that contain SKILL.md); the error list is that listing's
    `.errors`. A non-empty error list means the inventory is partial and the
    name set must not drive `gone` cleanups. When the fingerprint module is
    unavailable the legacy inline walk is used and the error list is empty.
    Missing or unreadable roots return an empty set (fail-open). A root whose
    name is in EXCLUDED_DIR_NAMES is treated as empty; other names, including
    a leading-dot root, are walked. The leading-dot prune applies only to
    child directories.

    Phase 2 must guard `gone` with an explicit `root.is_dir()` check before
    acting: a silent empty inventory must not clear pending.
    """
    try:
        if fingerprint_mod is not None:
            listed = fingerprint_mod.list_skill_dirs(Path(skills_root))
            try:
                names = {p.name for p in listed.values()}
            except Exception:
                names = set()
            try:
                errors = list(getattr(listed, "errors", None) or [])
            except Exception:
                errors = []
            return names, errors
        return _legacy_list_skill_names(skills_root), []
    except Exception:
        return set(), []


def list_skill_names(skills_root: Path) -> set[str]:
    """Return original-case leaf names of directories that contain SKILL.md.

    Thin wrapper over `list_skill_names_report` for existing callers; the
    walk error list is discarded. Same fail-open contract: any failure
    returns an empty set.
    """
    try:
        names, _errors = list_skill_names_report(skills_root)
        return names
    except Exception:
        return set()


def _legacy_list_skill_names(skills_root: Path) -> set[str]:
    """Inline inventory used only when the fingerprint module is unavailable."""
    try:
        root = Path(skills_root)
        if not root.is_dir():
            return set()
        if root.name in EXCLUDED_DIR_NAMES:
            return set()
        found: dict[str, str] = {}
        stack: list[str] = []
        for dirpath, dirnames, filenames in os.walk(
            root, followlinks=True, onerror=lambda _exc: None
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
                dirnames[:] = []
                continue
            del stack[depth:]
            if resolved in stack:
                dirnames[:] = []
                continue
            stack.append(resolved)
            dirnames[:] = sorted(d for d in dirnames if not _pruned(d))
            if "SKILL.md" in filenames:
                name = p.name
                key = name.lower()
                if key not in found:
                    found[key] = name
        return set(found.values())
    except Exception:
        return set()


def compute_pending(
    current: set[str],
    manifested: set[str],
    dismissed: set[str],
    known: set[str],
) -> tuple[set[str], set[str]]:
    cur = {n.lower() for n in current}
    man = {n.lower() for n in manifested}
    dis = {n.lower() for n in dismissed}
    kno = {n.lower() for n in known}
    new_pending = cur - (man | dis | kno)
    gone = kno - cur
    return new_pending, gone


def _pruned(name: str) -> bool:
    # "retired-" dirs hold ARCHIVED non-skill copies (pre-split SKILL.md
    # snapshots under references/) — the no-trim archive convention. A dir
    # named retired-* cannot itself be a live skill.
    return (
        name in EXCLUDED_DIR_NAMES
        or name.startswith(".")
        or name.startswith("retired-")
    )
