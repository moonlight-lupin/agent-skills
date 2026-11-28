"""v0.5.0 system-prompt router hint — registration contract.

Fake-ctx tests for the one thing that makes the orchestrator reachable from a
session: register() adds a SHORT system-prompt section (pointer, not content)
when the host exposes ``ctx.register_system_prompt_section``, and register()
still succeeds — skills and hook wired — when the host does not (older
Hermes). The section body must name the qualified orchestrator skill and must
NOT carry pipeline detail, risk/complexity bands, or model/CLI pins.
"""

import importlib.util
import re
import sys
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]

# Host rule (hermes_cli/plugins_dispatch.py _SYSTEM_PROMPT_SECTION_ID_RE):
# 1-128 chars, a lowercase alnum first char, then lowercase alnum / '.' / '_' / '-'.
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")

# Model/CLI pin strings that must never leak into the always-loaded hint.
PIN_TOKENS = (
    "grok", "opus", "sonnet", "gpt-", "claude", "codex", "cursor",
    "muse", "gemini", "model", "--model",
)

# Stage-chain and risk/complexity content stays in the skills, not the hint.
DETAIL_RES = (
    re.compile(r"\b[SR][0-3]\b"),   # S0-S3 / R0-R3 bands
    re.compile(r"\bT[0-3]\b"),     # T0-T3 tiers
    re.compile(r"\bgrill\b"),
    re.compile(r"\btest-evals\b"),
    re.compile(r"\breview-commit\b"),
)

_PLUGIN = None


def _plugin():
    """Load the plugin module once (plain-module hermes test contract)."""
    global _PLUGIN
    if _PLUGIN is None:
        spec = importlib.util.spec_from_file_location(
            "dev_pipeline_prompt_under_test", PLUGIN_DIR / "__init__.py",
            submodule_search_locations=[str(PLUGIN_DIR)])
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        import sys
        sys.modules[spec.name] = mod  # the relative `.engineering` import needs its parent package registered
        spec.loader.exec_module(mod)
        _PLUGIN = mod
    return _PLUGIN


class _FakeCtx:
    """Host ctx: records register_skill / register_hook / the prompt section."""

    def __init__(self, prompt_api=True, prompt_error=None, tools=True):
        self.skills = []
        self.hooks = []
        self.sections = []
        self.tools = []
        self._prompt_error = prompt_error
        if prompt_api:
            self.register_system_prompt_section = self._register_section
        if tools:
            self.register_tool = self._register_tool

    def _register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def _register_section(self, section_id, content, **kwargs):
        if self._prompt_error is not None:
            raise self._prompt_error
        self.sections.append((section_id, content, kwargs))

    def register_skill(self, name, path):
        self.skills.append((name, path))

    def register_hook(self, event, cb):
        self.hooks.append((event, cb))


def test_section_registered_when_api_exists():
    ctx = _FakeCtx()
    _plugin().register(ctx)
    assert len(ctx.skills) == 10 and len(ctx.hooks) == 1
    assert len(ctx.sections) == 1, "exactly one system-prompt section"
    section_id, content, _kwargs = ctx.sections[0]
    assert section_id == _plugin()._SYSTEM_PROMPT_SECTION_ID
    assert ID_RE.fullmatch(section_id), "id must satisfy the host id rule"
    assert isinstance(content, str) and content
    assert len(content) <= 800, "hint must stay short (aim <= 800 chars)"
    assert "dev-pipeline:orchestrator" in content, "qualified skill name"
    assert 'skill_view("dev-pipeline:orchestrator")' in content
    for verb in ("build", "implement", "add", "fix", "debug", "review"):
        assert verb in content, f"hint must cover the '{verb}' trigger verb"


def test_register_succeeds_when_api_missing():
    """Legacy host (no register_system_prompt_section, no register_tool)."""
    ctx = _FakeCtx(prompt_api=False)
    _plugin().register(ctx)  # must not raise
    assert len(ctx.skills) == 10 and len(ctx.hooks) == 1
    assert ctx.sections == []


def test_registration_error_does_not_break_load(caplog):
    import logging
    ctx = _FakeCtx(prompt_error=ValueError("id already registered"))
    with caplog.at_level(logging.WARNING):
        _plugin().register(ctx)  # must not raise
    assert len(ctx.skills) == 10 and len(ctx.hooks) == 1
    assert ctx.sections == []
    warnings = [r for r in caplog.records
                if "register_system_prompt_section" in r.getMessage()]
    assert warnings, "an unregistered section must warn, not vanish silently"


def test_modern_host_registers_tools_and_section():
    """Modern host: register_tool exists alongside the section API."""
    ctx = _FakeCtx(prompt_api=True, tools=True)
    _plugin().register(ctx)
    assert len(ctx.skills) == 10 and len(ctx.hooks) == 1
    assert len(ctx.tools) == 8, f"expected the 8 engineering tools, got {len(ctx.tools)}"
    assert len(ctx.sections) == 1


def test_tools_present_but_section_api_absent():
    """Fourth combo: modern tools wired, legacy prompt API — zero sections, load succeeds."""
    ctx = _FakeCtx(prompt_api=False, tools=True)
    _plugin().register(ctx)
    assert len(ctx.tools) == 8
    assert ctx.sections == []


def test_hint_carries_no_pins_or_pipeline_detail():
    content = _plugin()._SYSTEM_PROMPT_SECTION_TEXT
    low = content.lower()
    for pin in PIN_TOKENS:
        assert pin not in low, f"hint must not name the pin/CLI token {pin!r}"
    for pattern in DETAIL_RES:
        assert not pattern.search(content), (
            f"hint must not carry pipeline/risk detail matching {pattern.pattern!r}")


def test_hint_id_is_stable_lowercase_identifier():
    section_id = _plugin()._SYSTEM_PROMPT_SECTION_ID
    assert ID_RE.fullmatch(section_id)
    assert section_id.startswith("dev-pipeline")


if __name__ == "__main__":  # direct runner, same contract as test_create_gate
    failed = 0
    for _name, fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {_name}")
            except AssertionError:
                failed += 1
                import traceback
                traceback.print_exc()
                print(f"FAIL {_name}")
    sys.exit(1 if failed else 0)
