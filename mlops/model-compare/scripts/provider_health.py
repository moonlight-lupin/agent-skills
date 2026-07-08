#!/usr/bin/env python3
"""
Provider health tracker — dead-host cooldown for multi-provider API calls.

Tracks consecutive failures per provider endpoint and marks dead hosts
for a cooldown period. Any success resets the failure counter immediately.

Inspired by Odysseus's _dead_hosts / _host_fails cooldown system.

Usage:
  from provider_health import health

  # Before making a call — check if provider is alive
  if health.is_alive("ollama-cloud"):
      response = call_api(...)
      health.record_success("ollama-cloud")
  else:
      print(f"Skipping ollama-cloud — in cooldown ({health.cooldown_remaining('ollama-cloud')}s left)")

  # On failure
  health.record_failure("ollama-cloud", error="HTTP 503")

  # Get a status report
  print(health.status())

Design:
  - In-memory tracking (no external deps)
  - Optional persistence to ~/.hermes/data/provider_health.json
  - Thread-safe (locks around state mutations)
  - Configurable threshold and cooldown per provider
  - CLI mode: python3 provider_health.py --status
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, Optional


# ─── Defaults ────────────────────────────────────────────────────────────────

DEFAULT_FAIL_THRESHOLD = 2       # 2 consecutive failures → mark dead
DEFAULT_COOLDOWN_SECONDS = 20    # 20s in the penalty box
MAX_COOLDOWN_SECONDS = 300       # cap exponential backoff at 5 minutes

# Per-provider overrides (some providers are flakier than others)
PROVIDER_CONFIG = {
    "ollama-cloud": {
        "fail_threshold": 2,
        "cooldown_seconds": 15,   # shorter — it's usually transient
    },
    "nvidia": {
        "fail_threshold": 2,
        "cooldown_seconds": 30,   # longer — NVIDIA tends to stay down longer
    },
    "openrouter": {
        "fail_threshold": 3,      # more lenient — paid provider, more reliable
        "cooldown_seconds": 20,
    },
}


class ProviderHealth:
    """Thread-safe provider health tracker with dead-host cooldown."""

    def __init__(
        self,
        fail_threshold: int = DEFAULT_FAIL_THRESHOLD,
        cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        persist_path: Optional[str] = None,
    ):
        self._default_threshold = fail_threshold
        self._default_cooldown = cooldown_seconds
        self._persist_path = persist_path
        self._lock = threading.Lock()

        # State: {provider: {"fails": N, "dead_at": timestamp_or_None, "last_error": str}}
        self._state: Dict[str, dict] = {}

        # Load persisted state if available
        self._load()

    def _provider_cfg(self, provider: str) -> dict:
        cfg = PROVIDER_CONFIG.get(provider, {})
        return {
            "fail_threshold": cfg.get("fail_threshold", self._default_threshold),
            "cooldown_seconds": cfg.get("cooldown_seconds", self._default_cooldown),
        }

    def is_alive(self, provider: str) -> bool:
        """Check if a provider is alive (not in cooldown)."""
        with self._lock:
            state = self._state.get(provider)
            if not state or state.get("dead_at") is None:
                return True

            cfg = self._provider_cfg(provider)
            elapsed = time.time() - state["dead_at"]

            if elapsed >= cfg["cooldown_seconds"]:
                # Cooldown expired — give it another chance
                state["dead_at"] = None
                state["fails"] = 0
                self._save()
                return True

            return False

    def cooldown_remaining(self, provider: str) -> float:
        """Seconds remaining in cooldown (0 if alive or expired)."""
        with self._lock:
            state = self._state.get(provider)
            if not state or state.get("dead_at") is None:
                return 0.0

            cfg = self._provider_cfg(provider)
            elapsed = time.time() - state["dead_at"]
            remaining = cfg["cooldown_seconds"] - elapsed
            return max(0.0, round(remaining, 1))

    def record_success(self, provider: str):
        """Record a successful call — resets failure counter immediately."""
        with self._lock:
            state = self._state.get(provider)
            if state and (state.get("fails", 0) > 0 or state.get("dead_at") is not None):
                state["fails"] = 0
                state["dead_at"] = None
                state["last_error"] = None
                self._save()

    def record_failure(self, provider: str, error: str = ""):
        """Record a failed call. After threshold consecutive failures, marks provider dead."""
        with self._lock:
            state = self._state.setdefault(provider, {
                "fails": 0, "dead_at": None, "last_error": None,
            })
            state["fails"] = state.get("fails", 0) + 1
            state["last_error"] = error[:200]

            cfg = self._provider_cfg(provider)
            if state["fails"] >= cfg["fail_threshold"]:
                state["dead_at"] = time.time()
                self._save()
                return True  # newly marked dead

            self._save()
            return False  # not dead yet

    def status(self) -> dict:
        """Return a status snapshot of all tracked providers."""
        with self._lock:
            now = time.time()
            result = {}
            for provider, state in self._state.items():
                cfg = self._provider_cfg(provider)
                dead_at = state.get("dead_at")
                if dead_at is not None and (now - dead_at) >= cfg["cooldown_seconds"]:
                    # Cooldown expired
                    state["dead_at"] = None
                    state["fails"] = 0
                    alive = True
                    cooldown = 0.0
                elif dead_at is not None:
                    alive = False
                    cooldown = max(0.0, round(cfg["cooldown_seconds"] - (now - dead_at), 1))
                else:
                    alive = True
                    cooldown = 0.0
                result[provider] = {
                    "alive": alive,
                    "fails": state.get("fails", 0),
                    "threshold": cfg["fail_threshold"],
                    "cooldown_remaining": cooldown,
                    "last_error": state.get("last_error"),
                }
            self._save()
            return result

    def reset(self, provider: Optional[str] = None):
        """Reset all providers or a specific one."""
        with self._lock:
            if provider:
                self._state.pop(provider, None)
            else:
                self._state.clear()
            self._save()

    def _load(self):
        """Load persisted state from disk."""
        if not self._persist_path:
            return
        path = Path(self._persist_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            # Only load providers that are still in cooldown (skip expired)
            now = time.time()
            for provider, state in data.items():
                if state.get("dead_at") and (now - state["dead_at"]) < MAX_COOLDOWN_SECONDS:
                    self._state[provider] = state
        except Exception:
            pass  # corrupt state — start fresh

    def _save(self):
        """Persist state to disk."""
        if not self._persist_path:
            return
        try:
            path = Path(self._persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self._state, indent=2))
        except Exception:
            pass  # persistence is best-effort


# ─── Singleton ───────────────────────────────────────────────────────────────

_default_instance = None


def get_health() -> ProviderHealth:
    """Get the shared ProviderHealth singleton."""
    global _default_instance
    if _default_instance is None:
        persist = os.path.expanduser("~/.hermes/data/provider_health.json")
        _default_instance = ProviderHealth(persist_path=persist)
    return _default_instance


# Convenience module-level instance
health = get_health()


# ─── CLI ─────────────────────────────────────────────────────────────────────

def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="Provider health tracker")
    parser.add_argument("--status", action="store_true", help="Show provider health status")
    parser.add_argument("--reset", help="Reset a specific provider or 'all'")
    args = parser.parse_args()

    if args.reset:
        if args.reset.lower() == "all":
            health.reset()
            print("Reset all providers.")
        else:
            health.reset(args.reset)
            print(f"Reset {args.reset}.")
        return

    # Default: show status
    status = health.status()
    if not status:
        print("No providers tracked yet.")
        return

    print(f"\n{'Provider':<20s} {'Status':<8s} {'Fails':>5s} {'Threshold':>9s} {'Cooldown':>8s} Last Error")
    print(f"{'-'*80}")
    for provider, info in sorted(status.items()):
        alive = "✅ alive" if info["alive"] else "❌ dead"
        cooldown = f"{info['cooldown_remaining']:.0f}s" if info["cooldown_remaining"] > 0 else "-"
        error = info.get("last_error", "") or ""
        print(f"{provider:<20s} {alive:<8s} {info['fails']:>5d} {info['threshold']:>9d} {cooldown:>8s} {error[:30]}")
    print()


if __name__ == "__main__":
    _cli()