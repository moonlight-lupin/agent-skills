"""Unified Hermes Skill Governance plugin.

One plugin, one hook per event, one optional clearance job. Both underlying
engines are vendored without logic edits to minimize migration risk.

register() touches NO plugin state: migration, the coexistence check and the
first records build run lazily on the first hook call (see _run_bootstrap).
This keeps registration clean for host-side capability probes that stub out
the state facade, and lets a corrupt legacy store fail hooks INERT rather
than kill registration outright.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from . import core
from .contrastive import advisor
from .manifest import hooks as manifest_hooks

log = logging.getLogger("skill-governance")
HERE = Path(__file__).resolve().parent


def register(ctx):
    manifest_ctx = core.ComponentContext(ctx, "manifest")
    advisor_ctx = core.ComponentContext(ctx, "advisor")
    manifest_hooks.configure(manifest_ctx)

    # The vendored first-fire note points at the legacy self-installed
    # "contrastive-advisor fire clearance" job. That job never exists under
    # governance (scheduling is owned by cron.* and the legacy sweeper gate is
    # force-disabled), so the note would tell the model about a cron job it
    # cannot find. Suppressed at the adapter boundary, not in vendored code.
    advisor._first_fire_note = lambda *a, **k: None

    bootstrap = {"done": False, "failed": False}
    bootstrap_lock = threading.Lock()

    def refresh():
        try:
            core.sync_records(ctx, advisor)
        except Exception:
            # Display-summary failure must not drop manifest or probe advisories.
            log.warning("Governance record refresh failed", exc_info=True)

    def _run_bootstrap():
        try:
            core.migrate_legacy_state(ctx)
            core.warn_legacy_coexistence(ctx)
            refresh()
        except Exception:
            bootstrap["failed"] = True
            log.warning("Governance bootstrap failed; hooks stay inert", exc_info=True)
        bootstrap["done"] = True

    def _booted() -> bool:
        if not bootstrap["done"]:
            with bootstrap_lock:
                if not bootstrap["done"]:
                    _run_bootstrap()
        return not bootstrap["failed"]

    def on_session_start(session_id="", **kw):
        # Bootstrap must run BEFORE any engine call: the engines write state
        # through the component namespaces, and an engine write would create
        # the destination that the legacy import (destination-wins) then skips.
        if not _booted():
            return None
        manifest_hooks.on_session_start(session_id=session_id, **kw)
        advisor.on_session_start(advisor_ctx, session_id=session_id, **kw)
        core.ensure_single_cron(ctx)
        refresh()

    def on_skill_lifecycle(**kw):
        if not _booted():
            return None
        outcome = manifest_hooks.on_skill_lifecycle(**kw)
        refresh()
        return outcome

    def on_pre_tool_call(tool_name=None, args=None, **kw):
        if not _booted():
            return None
        outcome = advisor.on_pre_tool_call(advisor_ctx, tool_name=tool_name,
                                           args=args, **kw)
        refresh()
        return outcome

    def on_pre_llm_call(session_id="", user_message="", **kw):
        if not _booted():
            return None
        first = manifest_hooks.on_pre_llm_call(session_id=session_id,
                                               user_message=user_message, **kw)
        second = advisor.on_pre_llm_call(advisor_ctx, session_id=session_id,
                                         user_message=user_message, **kw)
        refresh()
        return core.compose_advisories(first, second)

    ctx.register_skill("contrastive-refinement",
                       HERE / "skills" / "contrastive-refinement" / "SKILL.md")
    ctx.register_hook("on_skill_lifecycle", on_skill_lifecycle)
    ctx.register_hook("on_session_start", on_session_start)
    ctx.register_hook("pre_tool_call", on_pre_tool_call)
    ctx.register_hook("pre_llm_call", on_pre_llm_call)

    # Preserve existing human acknowledgement entrypoints for operators.
    # Do NOT enable the legacy skill-manifest plugin concurrently, as both
    # register the same command names.
    try:
        cli = getattr(ctx, "register_cli_command", None)
        if callable(cli):
            cli("skill-manifest", manifest_hooks.CLI_HELP,
                manifest_hooks.cli_setup, manifest_hooks.cli_handler)
        slash = getattr(ctx, "register_command", None)
        if callable(slash):
            slash("skill-manifest-ack", manifest_hooks.slash_skill_manifest_ack,
                  description="Acknowledge reviewed skill digest",
                  args_hint="<name> <hex>")
    except Exception:
        log.warning("Legacy acknowledgement command registration failed", exc_info=True)