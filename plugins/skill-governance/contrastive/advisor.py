#!/usr/bin/env python3
"""contrastive-advisor: advisory hooks for the contrastive-refinement skill.

Advisory-only (skill-manifest convention): observe behavioral skill edits,
remind ONCE per edit via the next pre_llm_call injection, check the
probe-evidence directory, never block, never rewrite arguments, never call a
model, never touch the network. Only stdlib is imported. The enabled path
does one ctx.state read per hook; a disabled config does zero I/O.

Injection shape: pre_llm_call returns {"context": str} (verified core
contract, agent/turn_context.py) — a bare string is silently dropped by core.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys

STATE_KEY = "v1"

BODY_SECTION_MARKERS = (
    "## When to Use",
    "## Procedure",
    "## Pitfalls",
    "## Verification",
    "## Quick Reference",
)
DEFAULT_EXCLUDED = ("contrastive-refinement",)
PENDING_MAX = 3
DEFAULT_TTL_MINUTES = 30
DEFAULT_PROBE_ROOT = "skill-probes"  # relative to the Hermes home
INJECT_HARD_CAP = 900
LEDGER_FILE = "fire-ledger.jsonl"  # inside the probe root
LEDGER_ADVISORY_CAP = 160

SWEEPER_JOB_NAME = "contrastive-advisor fire clearance"
SWEEPER_PROMPT = (
    "contrastive-advisor fire clearance (sweeper).\n"
    "This run is your assigned task; acting on open fire rows here is correct.\n"
    "Read ~/.hermes/skill-probes/fire-ledger.jsonl and collect rows that have "
    "fired_at but no answered_at. If none, reply exactly: CLEAN.\n"
    "Otherwise take the OLDEST 4 (one per skill). For each, reconstruct the edit "
    "from the session store (state.db messages table, tool_calls rows for that "
    "session_id; function.arguments are doubly-encoded JSON), then classify per the "
    "contrastive-refinement skill (agent-ops):\n"
    "(a) mechanical edit with no behavioral claim - close;\n"
    "(b) real-environment execution evidence - the edited procedure ran live against "
    "its real target in the editing session - close;\n"
    "(c) unresolved provenance (file changed, no logged delta) - document the gap, "
    "close with a reopen condition;\n"
    "(d) behavioral edit with no live evidence - LEAVE OPEN; list it in the report "
    "as needing an interactive probe cycle. Never fabricate probe evidence.\n"
    "For each closed fire: create ~/.hermes/skill-probes/<skill>/<tag>/ holding "
    "probe.md (what was edited; why it closes: classification + evidence) and "
    "selection.md (decision + reopen condition); tag = live-exec-<YYYYMMDD>, "
    "mech-<YYYYMMDD>, or prov-gap-<YYYYMMDD>. Then stamp the ledger row: "
    "answered_at=now, answered_with=that dir. Rewrite the JSONL atomically "
    "(tmp file + replace) preserving every other row verbatim.\n"
    "Source rules: harness^2 (arXiv:2610.14224) - KEEP_BASE is a real answer; "
    "lessons without evidence enter no library; library consolidation is its "
    "declared future work (Appendix G) and this sweeper is that work.\n"
    "Report one line per fire: skill | classification | closed or escalated."
)
BEHAVIORAL_MIN_CHARS = 400  # markerless edits below this stay silent
CYCLE_SCAN_DEPTH_GLOBS = ("*/selection.md", "*/*/selection.md")
CYCLE_MAX_COUNT = 10
CYCLE_SCAN_MAX_ENTRIES = 50  # glob-visited bound (never materializes the match set)
CYCLE_RECENT_WINDOW_DAYS = 90

_PLUGIN_NAMESPACED = re.compile(r"^[A-Za-z0-9_-]+:[A-Za-z0-9_-]+$")
_VALID_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def _log(message: str) -> None:
    print(f"⚠️ contrastive-advisor: {message}", file=sys.stderr, flush=True)


# --- config ------------------------------------------------------------------


def load_settings(ctx) -> dict:
    """Read plugin settings through ctx.get_config only (no filesystem I/O).

    Keys are RELATIVE per the live core contract
    (hermes_cli/plugins_state.py: `get_config('endpoint')` reads
    plugins.entries.<id>.settings.<key>): 'enabled', 'probe_root',
    'excluded_skills', 'ttl_minutes', 'markers'. The root 'settings' is a
    RESERVED config path — core raises ValueError on it and logs Rejected
    config path every call cycle, so it is never requested. Each key read is
    individually guarded: one rejected/absent key falls back to None without
    disabling the rest. An absent or explicitly-false 'enabled' DISABLES the
    hook (opt-in; zero I/O) — settings never silently enable.
    """
    raw = {}
    for key in ("enabled", "probe_root", "excluded_skills", "ttl_minutes", "markers",
                "ledger_enabled"):
        try:
            value = ctx.get_config(key)
        except Exception:
            value = None  # reserved/invalid path: treated absent, not fatal
        if value is not None:
            raw[key] = value
    if raw.get("enabled") is not True:
        return {"enabled": False}  # opt-in gate: absent/False/missing entry = disabled
    hermes_home = (
        getattr(ctx, "hermes_home", None)
        or str(pathlib.Path.home() / ".hermes")
    )
    excluded = _as_tuple(raw.get("excluded_skills"))
    ttl_raw = raw.get("ttl_minutes")
    ttl = DEFAULT_TTL_MINUTES
    if isinstance(ttl_raw, (int, float)) and not isinstance(ttl_raw, bool) and ttl_raw > 0:
        ttl = ttl_raw
    markers = _as_tuple(raw.get("markers"))
    return {
        "enabled": True,
        "hermes_home": hermes_home,
        "probe_root": str(raw.get("probe_root") or (pathlib.Path(hermes_home) / DEFAULT_PROBE_ROOT)),
        "excluded_skills": tuple(dict.fromkeys(excluded + DEFAULT_EXCLUDED)),
        "ttl_minutes": int(ttl),
        "markers": markers or BODY_SECTION_MARKERS,
        "ledger_enabled": raw.get("ledger_enabled") is not False,  # default on
    }


def _as_tuple(value) -> tuple:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return ()


# --- detection ----------------------------------------------------------------


def _edit_text_from_skill_manage(args: dict) -> tuple[str, str] | None:
    """(skill_name, text) for skill_manage calls with a behavioral action.

    The tool accepts TWO field-name families for the same edit — alias keys
    (old_text/new_text/content, the op-schema names) and patch-tool keys
    (old_string/new_string, the description's canonical patch shape). Read
    the UNION of both: a detector reading only one family never fires on the
    other, and the most common real edit shape (old_string/new_string)
    extracts "" and stays silent. Same rule for every op in the batch
    `operations` array.
    """
    name = str(args.get("name", "")).strip()
    if not name:
        return None
    parts: list[str] = [
        str(args.get(k) or "")
        for k in ("old_text", "old_string", "new_text", "new_string", "content")
    ]
    ops = args.get("operations")
    if isinstance(ops, list):
        for op in ops:
            if isinstance(op, dict):
                parts.extend(
                    str(op.get(k) or "")
                    for k in ("old_text", "old_string", "new_text", "new_string", "content")
                )
    return name, " ".join(parts)


def _edit_text_from_file_tool(args: dict) -> tuple[str, str] | None:
    """(skill_name, text) for patch/write_file calls on a SKILL.md file.

    The `patch` tool carries old_string/new_string; write_file carries
    content. The basename must be exactly SKILL.md — NOTSKILL.md stays
    silent. Backslash paths normalize (single backslash, also matched).
    """
    for key in ("path", "file_path", "absolute_path"):
        value = args.get(key)
        if not isinstance(value, str):
            continue
        normalized = value.replace("\\", "/")
        parts = normalized.rsplit("/", 1)
        if parts[-1] != "SKILL.md":
            continue
        skill_dir = pathlib.PurePosixPath(parts[0]).name if len(parts) > 1 else ""
        # A SKILL.md under a `plugins/` directory belongs to a namespaced
        # (catalog-tracked) plugin skill — keep the observer silent there.
        if "plugins" in pathlib.PurePosixPath(normalized).parts:
            return None
        text = " ".join(
            str(args.get(k) or "")
            for k in ("old_string", "new_string", "old_text", "new_text", "content")
        )
        return skill_dir, text
    return None


def _skill_manage_candidates(args: dict) -> list[tuple[str, str]]:
    """(skill_name, text) candidates from BOTH accepted skill_manage shapes.

    Top-level shape: `name`+`action` sit at the top level and every op's text
    folds into that one edit (previous behavior, unchanged). Pure batch shape:
    ONLY `operations` exists — each entry carries its own `name`+`action`, so
    a detector reading just the top level returned None and never fired (seen
    live 2026-10-19: a batch create produced no advisory). Walk each op, fold
    same-name ops into one candidate, keep the first-appearance order.
    """
    if str(args.get("action", "")).strip().lower() in ("patch", "create", "edit"):
        hit = _edit_text_from_skill_manage(args)
        return [hit] if hit is not None else []
    candidates: dict[str, list[str]] = {}
    ops = args.get("operations")
    if isinstance(ops, list):
        for op in ops:
            if not isinstance(op, dict):
                continue
            if str(op.get("action", "")).strip().lower() not in ("patch", "create", "edit"):
                continue
            name = str(op.get("name", "")).strip()
            if not name:
                continue
            candidates.setdefault(name, []).append(
                " ".join(
                    str(op.get(k) or "")
                    for k in ("old_text", "old_string", "new_text", "new_string", "content")
                )
            )
    return [(name, " ".join(texts)) for name, texts in candidates.items()]


def _hit_passes_gate(name: str, texts: str, settings: dict) -> tuple[str, str] | None:
    """Shared (name, text) -> (name, probe_dir) gate. None stays silent."""
    excluded = _as_tuple(settings.get("excluded_skills", DEFAULT_EXCLUDED))
    if name in excluded:
        return None
    if _PLUGIN_NAMESPACED.match(name) or not _VALID_SKILL_NAME.match(name):
        return None
    markers = _as_tuple(settings.get("markers", BODY_SECTION_MARKERS))
    if not any(marker in texts for marker in markers):
        if len(texts.strip()) < BEHAVIORAL_MIN_CHARS:
            return None
    probe_root = settings.get("probe_root", "")
    return name, str(pathlib.Path(probe_root) / name)


def behavioral_hits(tool_name, args, settings: dict) -> list[tuple[str, str]]:
    """Every (skill_name, probe_dir) this call wants a cycle reminder for,
    in first-appearance order. The single-hit `is_behavioral_edit` keeps its
    contract as the first hit; the hook observes ALL of them (observe_edit
    still collapses per skill)."""
    if not settings.get("enabled"):
        return []
    if not isinstance(args, dict):
        return []
    tool_name = tool_name or ""
    if tool_name == "skill_manage":
        candidates = _skill_manage_candidates(args)
    elif tool_name in ("patch", "write_file"):
        hit = _edit_text_from_file_tool(args)
        candidates = [hit] if hit is not None else []
    else:
        return []
    hits: list[tuple[str, str]] = []
    for name, texts in candidates:
        resolved = _hit_passes_gate(name, texts, settings)
        if resolved is not None and resolved not in hits:
            hits.append(resolved)
    return hits


def is_behavioral_edit(tool_name, args, settings: dict) -> tuple[str, str] | None:
    """(skill_name, probe_dir) when this call wants a cycle reminder, else
    None. A name that is not a plain lowercase skill name is ignored: the
    observer runs before the tool validates its own arguments, so traversal
    names and odd values must never reach the probe scan."""
    hits = behavioral_hits(tool_name, args, settings)
    return hits[0] if hits else None


# --- probe evidence -------------------------------------------------------------


def probe_evidence(probe_dir: str, *, now_provider=None) -> str:
    """One-line evidence status for a skill's probe root. A cycle is a
    directory holding BOTH probe.md and selection.md, at depth <= 2 (the
    scan is bounded: two glob levels, count-capped). Fails open."""
    root = pathlib.Path(probe_dir)
    try:
        if not root.is_dir():
            return f"missing: create {probe_dir}/<tag>/ with probe.md + selection.md"
        now = (now_provider or datetime.datetime.now)().timestamp()
        window = CYCLE_RECENT_WINDOW_DAYS * 86400
        cycles: list[float] = []
        visited = 0
        stop = False
        # Unsorted generator iteration: the scan never materializes the full
        # glob result (Codex C2). The terminal check runs for EVERY consumed
        # entry: entry 50 is the last one any generator is asked for, and the
        # break fires before entry 51 is consumed. The bound is shared across
        # BOTH glob patterns (Codex C3). Limit: with more fresh cycles than
        # CYCLE_MAX_COUNT, "latest" is from the first ones globs yield.
        for pattern in CYCLE_SCAN_DEPTH_GLOBS:
            if stop:
                break
            for sel in root.glob(pattern):
                visited += 1
                cycle_dir = sel.parent
                if (cycle_dir / "probe.md").is_file():
                    mtime = sel.stat().st_mtime
                    if now - mtime <= window:
                        cycles.append(mtime)
                if len(cycles) >= CYCLE_MAX_COUNT or visited >= CYCLE_SCAN_MAX_ENTRIES:
                    stop = True
                    break
            if stop:
                break
        if not cycles:
            return (
                f"missing (no fresh cycle): create {probe_dir}/<tag>/ "
                "with probe.md + selection.md"
            )
        when = datetime.datetime.fromtimestamp(max(cycles)).strftime("%Y-%m-%d")
        return f"found: {len(cycles)} cycle(s), latest {when}"
    except Exception as exc:
        _log(f"probe evidence unreadable for {probe_dir}: {type(exc).__name__}")
        return f"unknown: could not read {probe_dir}"


# --- fire ledger -----------------------------------------------------------------


def _ledger_path(settings: dict) -> pathlib.Path:
    return pathlib.Path(settings.get("probe_root", "")) / LEDGER_FILE


def _cycle_after(probe_dir: str, since_ts: float) -> str | None:
    """Newest cycle dir (BOTH probe.md and selection.md, depth <= 2) with a
    selection.md mtime >= since_ts, else None. Same bounded-scan rules as
    probe_evidence; fails open (None)."""
    try:
        root = pathlib.Path(probe_dir)
        if not root.is_dir():
            return None
        newest: tuple[float, str] | None = None
        visited = 0
        stop = False
        for pattern in CYCLE_SCAN_DEPTH_GLOBS:
            if stop:
                break
            for sel in root.glob(pattern):
                visited += 1
                cycle_dir = sel.parent
                if (cycle_dir / "probe.md").is_file() and sel.stat().st_mtime >= since_ts:
                    mtime = sel.stat().st_mtime
                    if newest is None or mtime > newest[0]:
                        newest = (mtime, str(cycle_dir))
                if visited >= CYCLE_SCAN_MAX_ENTRIES:
                    stop = True
                    break
        return newest[1] if newest else None
    except Exception:
        return None  # fail open: never break the fire path over bookkeeping


_EVIDENCE_ANSWERED_PREFIXES = ("found",)


def _evidence_is_answered(status: str) -> bool:
    return status.startswith(_EVIDENCE_ANSWERED_PREFIXES) and "no fresh cycle" not in status


def _load_ledger_rows(path: pathlib.Path) -> list[dict]:
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)
            except ValueError:
                continue  # torn/malformed line: skip, never crash the fire path
    except FileNotFoundError:
        pass
    return rows


def _ts(value) -> float | None:
    try:
        return datetime.datetime.fromisoformat(str(value)).timestamp()
    except Exception:
        return None


def record_fire(settings: dict, skill: str, tool: str, session_id,
                evidence_status: str, advisory_text: str) -> None:
    """Append ONE ledger row for a delivered advisory, and close any prior
    open row for the SAME skill whose probe evidence has since appeared.

    This is the fire ledger the trial log references: fires are in-band only
    (no gateway/agent.log line), so without this record each advisory is
    unprovable after its 30-minute TTL. Runs ONLY on an injected advisory —
    zero I/O when the plugin is disabled or nothing fires. All failures are
    logged-and-swallowed: bookkeeping must never break the advisory path."""
    if not settings.get("ledger_enabled", True):
        return
    now = datetime.datetime.now().astimezone()
    now_iso = now.isoformat(timespec="seconds")
    try:
        path = _ledger_path(settings)
        rows = _load_ledger_rows(path)
        probe_dir = str(pathlib.Path(settings.get("probe_root", "")) / skill)
        # Close open rows for this skill: evidence appeared after they fired.
        for row in rows:
            if row.get("skill") != skill or row.get("answered_at"):
                continue
            fired_ts = _ts(row.get("fired_at"))
            if fired_ts is None:
                continue
            cycle = _cycle_after(probe_dir, fired_ts)
            if cycle:
                row["answered_at"] = now_iso
                row["cycle"] = cycle
        rows.append(
            {
                "fired_at": now_iso,
                "skill": skill,
                "tool": tool,
                "session_id": session_id,
                "evidence": evidence_status[:LEDGER_ADVISORY_CAP],
                "answered_at": now_iso if _evidence_is_answered(evidence_status) else None,
                "advisory": advisory_text[:LEDGER_ADVISORY_CAP],
            }
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".jsonl.tmp")
        tmp.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
            encoding="utf-8",
        )
        tmp.replace(path)  # atomic on POSIX; a torn write never survives
    except Exception as exc:
        _log(f"fire ledger write failed ({type(exc).__name__}: {exc})")


# --- pending-state helpers -------------------------------------------------------


def _state(ctx) -> dict:
    try:
        data = ctx.state.get(STATE_KEY)
        if data is None:
            data = {}
        if isinstance(data, dict):
            return dict(data)
    except Exception as exc:
        _log(f"state read failed ({type(exc).__name__}: {exc})")
    return {}


def _set_state(ctx, data: dict) -> None:
    # No try/except here: a store failure must reach the hook wrapper so it
    # LOGS before swallowing (kanban-mirror lesson: silent state failures
    # made production no-ops indistinguishable from healthy behavior).
    ctx.state.set(STATE_KEY, data)


def observe_edit(ctx, skill_name: str, probe_dir: str, tool: str = "", session_id=None) -> None:
    """Store one pending reminder for ONE skill. A fresh edit to the same
    skill replaces the queued one (its next edit carries the reminder, so
    the collapse is per-pending-window, not per-edit). List bounded at
    PENDING_MAX."""
    data = _state(ctx)
    pending = [p for p in data.get("pending", []) if str(p.get("skill")) != skill_name]
    pending.append(
        {
            "skill": skill_name,
            "tool": tool,
            "probe_dir": probe_dir,
            "session_id": session_id,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
    )
    data["pending"] = pending[-PENDING_MAX:]
    _set_state(ctx, data)


def _expired(item: dict, ttl_minutes: int, now: datetime.datetime) -> bool:
    try:
        created = datetime.datetime.fromisoformat(str(item.get("created_at")))
        return (now - created) > datetime.timedelta(minutes=ttl_minutes)
    except Exception:
        return True


def pending_advisory(ctx, settings: dict, *, now=None) -> dict | None:
    """Serve the NEWEST valid pending edit (SPEC: newest wins) and persist
    the trimmed queue even when nothing valid remains. Returns the verified
    pre_llm_call shape {"context": str}, or None."""
    data = _state(ctx)
    pending = data.get("pending", [])
    now = now or datetime.datetime.now()
    ttl = int(settings.get("ttl_minutes", DEFAULT_TTL_MINUTES))
    fresh = [item for item in pending if not _expired(item, ttl, now)]
    item = None
    if fresh:
        item = fresh[-1]  # newest
        fresh = fresh[:-1]  # inject-once: it leaves the queue
    if fresh != pending:  # write only on change (Opus C2: no per-turn churn)
        data["pending"] = fresh  # reclaim storage even when everything expired
        _set_state(ctx, data)
    if item is None:
        return None
    skill = str(item.get("skill", "?"))[:64]
    status = probe_evidence(str(item.get("probe_dir", "")))
    text = render(skill, status, setup_note=_first_fire_note(settings, skill))
    record_fire(
        settings, skill, str(item.get("tool", "")), item.get("session_id"),
        status, text,
    )
    return {"context": text}


def render(skill: str, evidence: str, setup_note: str | None = None) -> str:
    """The advisory text. The skill name is pre-validated (plain lowercase
    token, <= 64 chars) by the detector, so it is safe prompt text.
    setup_note rides along only on a skill's first-ever fire (fire sweeper
    pointer); it must keep the total under INJECT_HARD_CAP like the body."""
    text = (
        "⚠️ contrastive-advisor: behavioral edit to skill "
        f"`{skill}` is in flight. contrastive-refinement expects a probe "
        "cycle for it: fixed probe task, baseline run, INV/DOM candidates "
        "probed, blind selection, composition probe. Probe evidence: "
        f"{evidence}. If the cycle ran, point the patch notes at its dir; "
        "if it did not, run it or fall back to keeping the current skill."
    )
    if setup_note:
        text += setup_note
    if len(text) > INJECT_HARD_CAP:
        # Slice to cap-minus-one so the ellipsis lands the text AT the cap,
        # never one over (Codex C2: slice-to-cap + ellipsis == cap + 1).
        text = text[: INJECT_HARD_CAP - 1].rstrip() + "…"
    return text


# --- fire sweeper (self-installed clearance cron; mirrors skill-manifest) ----------


def _first_fire_note(settings: dict, skill: str) -> str | None:
    """Pointer to the fire sweeper, only on a skill's first-ever fire.
    Fail-open: any ledger read problem returns None (no noise over a hiccup)."""
    try:
        if not settings.get("ledger_enabled"):
            return None
        rows = _load_ledger_rows(_ledger_path(settings))
        if any(str(r.get("skill", "")) == skill for r in rows):
            return None
        return (
            "\n\nNew here? This plugin self-installs a fire-sweeper cron "
            f'("{SWEEPER_JOB_NAME}") that closes stale fires by '
            "classification (see docs/README.md)."
        )
    except Exception:
        return None


def _cfg(ctx, key: str, default):
    try:
        value = ctx.get_config(key)
    except Exception:
        return default
    return default if value is None else value


def _import_cron():
    """Lazy import; a process without the cron modules skips silently."""
    try:
        from cron.jobs import load_jobs
        from tools.cronjob_tools import cronjob
        return load_jobs, cronjob
    except Exception:
        return None


def ensure_sweeper(ctx) -> None:
    """Register the fire-clearance cron once, unless the user removed it.
    Self-installing pattern ported from skill-manifest (named-job adoption,
    user-removal honoring). All failures log-and-swallow."""
    try:
        if _cfg(ctx, "sweeper", True) in (False, "false", "0"):
            return
        data = _state(ctx)
        removed = data.get("sweeper_user_removed") is True
        job_id = str(data.get("sweeper_job_id") or "")
        api = _import_cron()
        if api is None:
            return
        load_jobs, cronjob = api
        jobs = [j for j in (load_jobs() or []) if isinstance(j, dict)]
        named = next((str(j.get("id")) for j in jobs if j.get("name") == SWEEPER_JOB_NAME and j.get("id")), "")
        if removed:
            if named:  # hand-recreated job = opt back in
                data["sweeper_job_id"] = named
                data["sweeper_user_removed"] = False
                _set_state(ctx, data)
            return
        if job_id and any(str(j.get("id")) == job_id for j in jobs):
            return
        if named:
            data["sweeper_job_id"] = named
            _set_state(ctx, data)
            return
        payload = {
            "action": "create",
            "schedule": _cfg(ctx, "sweeper_schedule", "40 8 * * *"),
            "prompt": SWEEPER_PROMPT,
            "name": SWEEPER_JOB_NAME,
        }
        deliver = str(_cfg(ctx, "sweeper_deliver", "telegram") or "").strip()
        if deliver:
            payload["deliver"] = deliver
        raw = cronjob(**payload)
        created = ""
        data_raw = raw
        if isinstance(data_raw, str):
            import json as _json
            try:
                data_raw = _json.loads(data_raw)
            except Exception:
                data_raw = {}
        if isinstance(data_raw, dict):
            created = str(data_raw.get("job_id") or (data_raw.get("job") or {}).get("id") or "")
        if created:
            data = _state(ctx)
            data["sweeper_job_id"] = created
            _set_state(ctx, data)
        else:
            _log(f"fire sweeper cron create failed: {raw!r}"[:220])
    except Exception as exc:
        _log(f"ensure sweeper skipped ({type(exc).__name__}: {exc})")


# --- hook callbacks ----------------------------------------------------------------


def on_pre_tool_call(ctx, tool_name=None, args=None, **kw):
    """Observer: NEVER changes the call (returns None on every path).
    Log-then-swallow on failure."""
    try:
        settings = load_settings(ctx)
        if not isinstance(args, dict):
            args = {}
        for hit in behavioral_hits(tool_name, args, settings):
            observe_edit(
                ctx,
                hit[0],
                hit[1],
                tool=tool_name or "",
                session_id=kw.get("session_id"),
            )
    except Exception as exc:
        _log(f"pre_tool_call skipped ({type(exc).__name__}: {exc})")
    return None


def on_pre_llm_call(ctx, session_id=None, user_message=None, **kw):
    """Injector: one {"context": ...} advisory per stored edit, then the
    item leaves. Turn 1 stays clean: skip when is_first_turn is True, or
    when the gateway passes no is_first_turn and history is empty."""
    try:
        settings = load_settings(ctx)
        if not settings.get("enabled"):
            return None
        if kw.get("is_first_turn") is True:
            return None
        if "is_first_turn" not in kw and not kw.get("conversation_history"):
            return None
        return pending_advisory(ctx, settings)
    except Exception as exc:
        _log(f"pre_llm_call skipped ({type(exc).__name__}: {exc})")
        return None


def on_session_start(ctx=None, session_id="", **kw):
    """Session-start hook: self-install the fire sweeper, once. Never raises."""
    try:
        if ctx is not None:
            ensure_sweeper(ctx)
    except Exception as exc:
        _log(f"session-start skipped ({type(exc).__name__}: {exc})")
    return None
