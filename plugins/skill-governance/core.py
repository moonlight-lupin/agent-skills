"""Skill Governance bridge: compose the two maintained engines safely.

The engines are vendored unchanged. This adapter supplies independent state
namespaces and config prefixes, imports legacy state by *copying* once, and
publishes a conservative cross-engine status view. Never writes to the source
plugin state, acknowledgements, or probe evidence.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

try:
    # Engines resolve the home through hermes_constants (honors HERMES_HOME);
    # the adapter must not resolve a different profile than the vendored code.
    from hermes_constants import get_hermes_home as _host_home
except Exception:  # pragma: no cover - host runtime always provides it
    _host_home = None

log = logging.getLogger("skill-governance")
STATE_KEYS = {"manifest": "manifest.v1", "advisor": "advisor.v1"}
LEGACY_IDS = {"manifest": "skill-manifest", "advisor": "contrastive-advisor"}
RECORDS_KEY = "governance.records"
CRON_LOCK_REL = Path("plugin-data") / "skill-governance" / ".clearance-cron.lock"
# In-memory parsed-evidence cache (per process); authoritative data stays on disk.
_EV_CACHE = {"ledger_path": None, "ledger_sig": None, "rows": (),
             "acks_path": None, "acks_sig": None, "acks_doc": {}}
_EV_LOCK = threading.Lock()
_HEX64 = re.compile(r"^[a-fA-F0-9]{64}$")


def _resolve_home(ctx=None) -> Path:
    """Same home the vendored engines resolve (hermes_constants first)."""
    if _host_home is not None:
        try:
            return Path(_host_home()).expanduser()
        except Exception:
            pass
    parts = []
    if ctx is not None:
        parts.append(getattr(ctx, "hermes_home", ""))
    parts.append(os.environ.get("HERMES_HOME"))
    for part in parts:
        if part:
            return Path(part).expanduser()
    return (Path.home() / ".hermes").expanduser()


class ComponentState:
    """Present legacy 'v1' key without state collisions between engines."""
    def __init__(self, parent, component):
        self.parent = parent
        self.component = component

    def _key(self, key):
        if key != "v1":
            raise ValueError("unexpected component state key")
        return STATE_KEYS[self.component]

    def get(self, key, default=None):
        return self.parent.get(self._key(key), default)

    def set(self, key, value):
        return self.parent.set(self._key(key), value)


class ComponentContext:
    """Allowed, plugin-local config and state adapter, not cross-plugin access."""
    def __init__(self, ctx, component):
        self._ctx = ctx
        self._prefix = component

    # ctx.state is resolved lazily: registration must not require the host
    # state facade (capability probes stub it out; bootstrap defers to the
    # first hook call).
    @property
    def state(self):
        return ComponentState(self._ctx.state, self._prefix)

    def get_config(self, key, default=None):
        # Only the composed plugin may create scheduled clearance jobs.
        if (self._prefix, key) in {("manifest", "auto_resolve"), ("advisor", "sweeper")}:
            return False
        return self._ctx.get_config(f"{self._prefix}.{key}", default)

    def __getattr__(self, name):
        if name in {"state", "get_config", "set_config", "_ctx", "_prefix"}:
            raise AttributeError(name)
        return getattr(self._ctx, name)


def _legacy_state_path(home: Path, plugin_id: str) -> Path:
    # Matches hermes_cli.plugins_manifest._portable_data_namespace and
    # plugins_state._plugin_data_namespace for native plugins.
    digest = hashlib.sha256(plugin_id.encode("utf-8")).hexdigest()[:8]
    return home / "plugin-data" / f"agent-plugin-{plugin_id}-{digest}" / "state.json"


def _read_legacy(path: Path):
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError(f"refusing symlinked legacy state: {path}")
    if not path.exists():
        return None
    source = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(source, dict):
        raise ValueError(f"invalid legacy state envelope: {path}")
    value = source.get("v1")
    if value is None:
        # An absent or explicit-null 'v1' is an empty ledger, not corruption:
        # migration treats it as "nothing to migrate".
        return None
    if not isinstance(value, dict):
        raise ValueError(f"invalid legacy state envelope: {path}")
    return value


def migrate_legacy_state(ctx):
    """Idempotent, non-destructive migration.

    Existing destination state always wins. Malformed legacy state aborts
    registration BEFORE hooks run instead of creating an empty replacement.
    Source state.json and the legacy ack/probe stores are never modified.
    """
    home = _resolve_home(ctx)
    # Preflight all legacy files before writing either destination namespace.
    prepared = []
    for component, plugin_id in LEGACY_IDS.items():
        target = STATE_KEYS[component]
        if ctx.state.get(target, None) is not None:
            continue
        value = _read_legacy(_legacy_state_path(home, plugin_id))
        if value is not None:
            prepared.append((component, target, value))
    for component, target, value in prepared:
        ctx.state.set(target, value)
    return [component for component, _, _ in prepared]


def _advice_result(value):
    if isinstance(value, dict):
        context = value.get("context")
        return context if isinstance(context, str) and context.strip() else ""
    return ""


def compose_advisories(*results):
    parts = [_advice_result(value) for value in results]
    text = "\n\n".join(part for part in parts if part)
    return {"context": text} if text else None


def _valid_fingerprint(value):
    return value.lower() if isinstance(value, str) and _HEX64.fullmatch(value) else ""


def build_records(manifest_state, advisor_state, ledger_rows=(), external_acks=None):
    """Conservative combined record: acknowledgment NEVER implies validation.

    Manifest fingerprints are keyed by path hash, while the advisor identifies
    skills by display name. Only join when the manifest has a finding with an
    explicit name; otherwise retain two separate entries rather than guessing.
    Evidence from legacy ledger is not fingerprint-bound: explicitly label it.
    """
    result = {}
    external_acks = external_acks if isinstance(external_acks, dict) else {}
    baseline = manifest_state.get("baseline", {})
    baseline = baseline if isinstance(baseline, dict) else {}
    # The manifest engine stores and compares baseline keys lowercased
    # (hooks.py normalizes with .lower()); lookups must match that.
    baseline_by_lower = {}
    for bl_key, bl_val in baseline.items():
        if isinstance(bl_key, str):
            baseline_by_lower.setdefault(bl_key.lower(), bl_val)
    fingerprints = manifest_state.get("fingerprints", {})
    findings = manifest_state.get("findings", {})
    if not isinstance(fingerprints, dict):
        fingerprints = {}
    if not isinstance(findings, dict):
        findings = {}
    # Basename collisions: findings take their name from Path(skill_dir).name,
    # so two different manifest paths can share one display name. The plain
    # name belongs to the lexicographically smallest manifest key (deterministic
    # regardless of dict order); every other colliding key gets a #suffix ref.
    # Known limitation (documented): advisor pending/ledger rows join by the
    # plain display name only, so probe evidence for a colliding basename
    # attaches to whichever record owns the plain name.
    plain_owner = {}
    name_keys = {}
    for m_key, m_finding in findings.items():
        m_name = m_finding.get("name") if isinstance(m_finding, dict) else None
        if isinstance(m_name, str) and m_name.strip():
            name_keys.setdefault(m_name, []).append(m_key)
    for m_name, m_keys in name_keys.items():
        plain_owner[m_name] = sorted(m_keys)[0]

    def _manifest_ref(name, key):
        if not (isinstance(name, str) and name.strip()):
            return f"manifest:{key}"
        if plain_owner.get(name) == key:
            return f"skill:{name}"
        return f"skill:{name}#{key[:12]}"
    for key, fp in fingerprints.items():
        if not isinstance(key, str) or not isinstance(fp, dict):
            continue
        finding = findings.get(key)
        name = finding.get("name") if isinstance(finding, dict) else None
        ref = _manifest_ref(name, key) if (isinstance(name, str) and name.strip()) else f"manifest:{key}"
        digest = _valid_fingerprint(fp.get("digest"))
        explicit_ack = _valid_fingerprint((external_acks.get(key) or {}).get("digest")) if isinstance(external_acks.get(key), dict) else ""
        stored_ack = _valid_fingerprint(fp.get("ack"))
        issue = finding.get("reason") if isinstance(finding, dict) else None
        result[ref] = {
            "skill_name": name if name else "",
            "manifest_key": key,
            "fingerprint": digest,
            "manifest_status": (
                "review_required" if issue else
                "acknowledged" if digest and digest == explicit_ack else
                "fingerprint_current" if digest and digest == stored_ack else
                "baseline_observed"
            ),
            "manifest_reason": issue if isinstance(issue, str) else "",
            "provenance_status": (
                baseline_by_lower.get(name.lower(), "unknown")
                if isinstance(name, str) and name else "unknown"
            ),
            "validation_status": "not_evaluated",
            "evidence": "",
        }
    for key, finding in findings.items():
        if not isinstance(finding, dict):
            continue
        name = finding.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        ref = _manifest_ref(name, key)
        if ref not in result:
            result[ref] = {
                "skill_name": name, "manifest_key": key,
                "fingerprint": _valid_fingerprint(finding.get("digest")),
                "manifest_status": "review_required",
                "manifest_reason": finding.get("reason") or "",
                "provenance_status": baseline_by_lower.get(name.lower(), "unknown"),
                "validation_status": "not_evaluated", "evidence": "",
            }
    pending = advisor_state.get("pending", [])
    live_pending = set()
    if isinstance(pending, list):
        for entry in pending:
            if not isinstance(entry, dict):
                continue
            name = entry.get("skill")
            if not isinstance(name, str) or not name.strip():
                continue
            live_pending.add(name)
            ref = f"skill:{name}"
            record = result.setdefault(ref, {
                "skill_name": name, "manifest_key": "",
                "fingerprint": "", "manifest_status": "unknown",
                "manifest_reason": "", "provenance_status": baseline_by_lower.get(name.lower(), "unknown"), "validation_status": "not_evaluated",
                "evidence": "",
            })
            record["validation_status"] = "probe_advised"
    if isinstance(ledger_rows, (list, tuple)):
        for entry in ledger_rows:
            if not isinstance(entry, dict):
                continue
            name = entry.get("skill")
            if not isinstance(name, str) or not name.strip():
                continue
            ref = f"skill:{name}"
            record = result.setdefault(ref, {
                "skill_name": name, "manifest_key": "",
                "fingerprint": "", "manifest_status": "unknown",
                "manifest_reason": "", "provenance_status": baseline_by_lower.get(name.lower(), "unknown"),
                "validation_status": "not_evaluated", "evidence": "",
            })
            # A live queued advisory takes priority; otherwise ledger rows
            # are chronological and the last recorded decision wins.
            if name in live_pending:
                continue
            close_ref = entry.get("answered_with") or entry.get("cycle")
            if entry.get("answered_at") and close_ref:
                # Legacy probes have no *digest binding*, so cannot be marked
                # 'validated' for the current fingerprint even if answered.
                # Both closure shapes count: the sweeper path writes
                # answered_with, the record_fire cycle path writes cycle only.
                record["validation_status"] = "answered_unbound"
                record["evidence"] = str(close_ref)[:300]
            elif not entry.get("answered_at"):
                record["validation_status"] = "probe_advised"
    return result


def _path_sig(path):
    """Cheap change signature for an evidence file (or 'missing')."""
    try:
        st = path.stat()
        return f"{st.st_size}:{st.st_mtime_ns}"
    except OSError:
        return "missing"


def sync_records(ctx, advisor_module=None):
    manifest_state = ctx.state.get(STATE_KEYS["manifest"], {}) or {}
    advisor_state = ctx.state.get(STATE_KEYS["advisor"], {}) or {}
    if not isinstance(manifest_state, dict) or not isinstance(advisor_state, dict):
        return
    # Evidence files (probe ledger, external acks) can be large and append-only.
    # Parse them only when their cheap signature changes (signature taken BEFORE
    # the read, so a write racing the parse cannot store stale content under a
    # fresh signature); parsed rows are cached IN MEMORY only (per process) —
    # the authoritative stores stay on disk.
    with _EV_LOCK:
        ledger_path = None
        if advisor_module is not None:
            try:
                settings = advisor_module.load_settings(ComponentContext(ctx, "advisor"))
                if settings.get("enabled") and settings.get("ledger_enabled"):
                    ledger_path = advisor_module._ledger_path(settings)
            except Exception:
                log.warning("Cannot summarize probe ledger", exc_info=True)
        acks_path = _resolve_home(ctx) / "plugin-data" / "skill-manifest" / "acks.json"
        rows = ()
        if ledger_path is not None:
            sig = _path_sig(ledger_path)
            if _EV_CACHE.get("ledger_path") != str(ledger_path) or _EV_CACHE.get("ledger_sig") != sig:
                try:
                    loaded = advisor_module._load_ledger_rows(ledger_path)
                    # Only cache a successful parse: a transient read failure
                    # must not mask the existing evidence until the next write.
                    _EV_CACHE.update({"ledger_path": str(ledger_path),
                                      "ledger_sig": sig,
                                      "rows": loaded[-200:]})  # bounded summary (the original ledger is authoritative)
                except Exception:
                    log.warning("Cannot summarize probe ledger", exc_info=True)
            rows = _EV_CACHE.get("rows", ()) or ()
        acks_sig = _path_sig(acks_path)
        if _EV_CACHE.get("acks_path") != str(acks_path) or _EV_CACHE.get("acks_sig") != acks_sig:
            try:
                from .manifest.shared.scripts.acks import load_acks
                doc = load_acks(acks_path)
                _EV_CACHE.update({"acks_path": str(acks_path),
                                  "acks_sig": acks_sig,
                                  "acks_doc": (doc.get("acks", {}) if isinstance(doc, dict) else {})})
            except Exception:
                log.warning("Cannot summarize external acknowledgements", exc_info=True)
        acks = _EV_CACHE.get("acks_doc", {}) or {}
    records = build_records(manifest_state, advisor_state, rows, acks)
    if ctx.state.get(RECORDS_KEY, None) != records:
        ctx.state.set(RECORDS_KEY, records)


def warn_legacy_coexistence(ctx=None) -> list:
    """Read-only check: warn when legacy plugins are still enabled.

    Duplicate advisories and CLI-name collisions are the realistic failure of
    running both generations together; README documents the migration, this
    adds a runtime signal. Never raises.
    """
    try:
        from hermes_cli.plugins_discovery import _get_enabled_plugins
        enabled = _get_enabled_plugins()
        if not isinstance(enabled, set):
            return []  # None = grandfathered/unknown; cannot judge safely
        active = sorted(set(LEGACY_IDS.values()) & set(enabled))
        if active:
            log.warning(
                "skill-governance: legacy plugins %s are still enabled. "
                "Advisories will be duplicated and the skill-manifest ack CLI "
                "collides. Disable them (see the README migration section).",
                ", ".join(active),
            )
        return active
    except Exception:
        return []


CRON_NAME = "skill-governance clearance"
LEGACY_CRON_NAMES = ("Skill-manifest drift clearance",
                     "contrastive-advisor fire clearance")
# Preserve both existing clearance procedures verbatim in a single scheduled
# prompt, so consolidation cannot silently weaken the operator's checklist.
from .manifest.hooks import PROMPT_AUTO_RESOLVE as _MANIFEST_CRON_PROMPT
from .contrastive.advisor import SWEEPER_PROMPT as _PROBE_CRON_PROMPT

CRON_PROMPT = (
    "Skill Governance unified scheduled clearance. Run BOTH procedures below. "
    "Use the active HERMES_HOME profile for every file path, even where a "
    "legacy procedure mentions ~/.hermes. Never fabricate evidence, alter "
    "unreviewed fingerprints or automatically acknowledge drift.\n\n"
    + _MANIFEST_CRON_PROMPT
    + "\n\n--- PROBE-FIRE CLEARANCE ---\n\n"
    + _PROBE_CRON_PROMPT
)


def ensure_single_cron(ctx):
    """Best-effort one-job scheduler; preserves manual removals and legacy jobs.

    The check-then-create sequence runs under a non-blocking flock with short
    retries (same discipline as the vendored manifest engine's
    _ensure_cron_lock): concurrent session starts must not each observe "no
    job" and each create one, and contention must never stall a session
    start. On non-POSIX hosts (no fcntl) it degrades to the v0.1.0 unlocked
    behavior. A hand-recreated named job opts the operator back in after a
    removal.
    """
    if ctx.get_config("cron.enabled", False) is not True:
        return
    lock_path = _resolve_home(ctx) / CRON_LOCK_REL
    fd = None
    pos_fcntl = True
    try:
        try:
            import fcntl  # noqa: F401
        except ImportError:
            # Non-POSIX host: degrade to the unlocked v0.1.0 behavior.
            pos_fcntl = False
        if pos_fcntl:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
            acquired = False
            for _ in range(3):
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    time.sleep(0.05)
            if acquired:
                try:
                    _ensure_single_cron_locked(ctx)
                finally:
                    fcntl.flock(fd, fcntl.LOCK_UN)
        else:
            _ensure_single_cron_locked(ctx)
    except Exception:
        log.warning("Governance cron setup failed; no hook failure", exc_info=True)
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _ensure_single_cron_locked(ctx):
    try:
        from cron.jobs import load_jobs
        from tools.cronjob_tools import cronjob
    except ImportError:
        return
    state = ctx.state.get("governance.cron", {}) or {}
    jobs = [j for j in (load_jobs() or []) if isinstance(j, dict)]
    named = next((j for j in jobs if j.get("name") == CRON_NAME), None)
    if named:
        # Adopting a named job also opts back in after a manual removal.
        named_id = str(named.get("id") or "")
        if named_id != str(state.get("job_id") or "") or state.get("user_removed"):
            ctx.state.set("governance.cron",
                          {"job_id": named_id, "user_removed": False})
        return
    if any(j.get("name") in LEGACY_CRON_NAMES for j in jobs):
        # Never schedule a duplicate while old clearance jobs are present.
        return
    if state.get("job_id") and not state.get("user_removed"):
        ctx.state.set("governance.cron", {**state, "user_removed": True})
        return
    if state.get("user_removed"):
        return
    payload = {
        "action": "create", "name": CRON_NAME,
        "schedule": ctx.get_config("cron.schedule", "0 9 * * *"),
        "prompt": CRON_PROMPT,
    }
    deliver = ctx.get_config("cron.deliver", "telegram")
    if isinstance(deliver, str) and deliver.strip():
        payload["deliver"] = deliver.strip()
    output = cronjob(**payload)
    if isinstance(output, str):
        output = json.loads(output)
    if isinstance(output, dict):
        job_id = output.get("job_id") or (output.get("job") or {}).get("id")
        if job_id:
            ctx.state.set("governance.cron", {"job_id": str(job_id)})
