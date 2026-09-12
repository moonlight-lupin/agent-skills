"""Parser-based yaml_quote roundtrip. Unprotected (not a contract file)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

CONVERT = (
    Path(__file__).resolve().parent.parent
    / "agent-ops"
    / "claude-plugin-converter"
    / "scripts"
    / "convert.py"
)

ADVERSARIAL = [
    "no",
    "yes",
    "- x\t",
    "true",
    "2026-01-01",
    "1.5",
    'says "hi"',
    "line\nbreak",
    "null",
    "0x10",
    "- greets\tthe user",
    "false",
    "~",
    "",
    "a: b",
    "'quoted'",
]


def _load_convert():
    spec = importlib.util.spec_from_file_location("convert_yaml_quote", CONVERT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_yaml_quote_roundtrips_adversarial_values():
    mod = _load_convert()
    for value in ADVERSARIAL:
        quoted = mod.yaml_quote(value)
        parsed = yaml.safe_load(quoted)
        assert parsed == value, (value, quoted, parsed)
