"""Advisory linter for UPSTREAM_MANIFEST.md. Reports; never rewrites."""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
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

_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


@dataclass
class LintFinding:
    check_id: str
    severity: str
    line: int
    message: str


@dataclass
class LintReport:
    findings: list[LintFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)


def lint_manifest(manifest: str, on_disk: set[str] | None = None) -> LintReport:
    try:
        return _lint(manifest, on_disk)
    except Exception as exc:
        return LintReport(
            findings=[
                LintFinding("L1-structure", "error", 0, f"lint failed: {exc}"),
            ]
        )


def _lint(manifest: str, on_disk: set[str] | None) -> LintReport:
    if not isinstance(manifest, str):
        return LintReport(
            findings=[
                LintFinding(
                    "L1-structure",
                    "error",
                    0,
                    "manifest text is not a string",
                )
            ]
        )
    findings: list[LintFinding] = []
    scan = manifest_db.scan_tables(manifest)

    for ln, _cells in scan.unpaired:
        findings.append(
            LintFinding(
                "L1-structure",
                "error",
                ln,
                "table line with no header/separator pairing",
            )
        )

    manifested: dict[str, list[int]] = {}
    for table in scan.tables:
        header_norm = [
            manifest_db._normalize_header_cell(c) for c in table.header
        ]
        n_header = len(table.header)
        is_skill = "Skill" in header_norm
        is_l6 = (
            is_skill
            and len(header_norm) >= 2
            and header_norm[1].lower() == "source repo"
        )
        sync_idxs = [
            i for i, h in enumerate(header_norm) if h.lower().endswith("sync")
        ]
        if not table.data:
            findings.append(
                LintFinding(
                    "L1-structure",
                    "warn",
                    table.header_line,
                    "table has a header but zero data rows",
                )
            )

        seen_keys: dict[str, int] = {}
        for row, rln in zip(table.data, table.data_lines):
            if manifest_db._is_separator_row(row):
                findings.append(
                    LintFinding(
                        "L1-structure",
                        "error",
                        rln,
                        "all-separator row in table data",
                    )
                )
                continue
            if len(row) != n_header:
                delta = len(row) - n_header
                findings.append(
                    LintFinding(
                        "L2-columns",
                        "warn",
                        rln,
                        f"row has {len(row)} cells, header has {n_header} "
                        f"(delta {delta:+d})",
                    )
                )
            else:
                for i in sync_idxs:
                    if i < len(row) and not _ok_sync_date(row[i]):
                        findings.append(
                            LintFinding(
                                "L5-date-format",
                                "warn",
                                rln,
                                f"cell {i} ({header_norm[i]!r}) is not YYYY-MM-DD, "
                                f"YYYY-MM, empty, '-', or 'never': {row[i]!r}",
                            )
                        )
            if is_l6:
                first = row[0].strip() if row else ""
                second = row[1].strip() if len(row) > 1 else ""
                if not first or not second:
                    findings.append(
                        LintFinding(
                            "L6-empty-required",
                            "warn",
                            rln,
                            "empty Skill or Source repo cell",
                        )
                    )
            if not is_skill or not row:
                continue
            raw = row[0]
            if not raw.strip():
                continue
            name = manifest_db._normalize_key(raw)
            if not name:
                continue
            if name in seen_keys:
                findings.append(
                    LintFinding(
                        "L3-duplicate",
                        "warn",
                        rln,
                        f"duplicate key {name!r} (first at line {seen_keys[name]})",
                    )
                )
            else:
                seen_keys[name] = rln
            manifested.setdefault(name, []).append(rln)

    if on_disk is not None:
        disk_l = {n.lower() for n in on_disk}
        for name, lns in manifested.items():
            if name not in disk_l:
                for ln in lns:
                    findings.append(
                        LintFinding(
                            "L4-stale-disk",
                            "warn",
                            ln,
                            f"manifest key {name!r} is not on disk",
                        )
                    )
        man_keys = set(manifested)
        for n in on_disk:
            if n.lower() not in man_keys:
                findings.append(
                    LintFinding(
                        "L4-untracked",
                        "info",
                        0,
                        f"{n!r} on disk is referenced in no manifest table",
                    )
                )

    return LintReport(findings=findings)


def _ok_sync_date(val: str) -> bool:
    v = val.strip()
    if not v or v == "-" or v.lower() == "never":
        return True
    if not _DATE.fullmatch(v):
        return False
    fmt = "%Y-%m-%d" if v.count("-") == 2 else "%Y-%m"
    try:
        datetime.strptime(v, fmt)
    except ValueError:
        return False
    return True
