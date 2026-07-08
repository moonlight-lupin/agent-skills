#!/usr/bin/env python3
"""Validate the routing/output-contract eval fixtures.

Prompt-only skills (deep-research, news-monitoring, website-scraping) ship
`evals/routing-fixtures.json`: sample request -> expected routing + required
output fields + forbidden output patterns. These are specs, not run against a
live model in CI. This test keeps them well-formed and self-consistent:

- every fixture file parses and has the right shape
- `skill_name` and every routed `skill` refer to a real skill in the repo
- each fixture has a non-trivial request, a routing reason, required output
  fields, and forbidden patterns that are valid regular expressions

Pure stdlib + pytest. Add a fixture file under any skill's evals/ and it's
picked up automatically.
"""

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Skill names = the directory each SKILL.md lives in.
VALID_SKILLS = {p.parent.name for p in REPO_ROOT.glob("**/SKILL.md")}

FIXTURE_FILES = sorted(REPO_ROOT.glob("**/evals/routing-fixtures.json"))

# Skills that are expected to ship routing fixtures — guards against silent loss.
EXPECTED_FIXTURE_SKILLS = {"deep-research", "news-monitoring", "website-scraping"}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_skills_were_discovered():
    # Sanity: the SKILL.md glob found the known skills.
    assert EXPECTED_FIXTURE_SKILLS <= VALID_SKILLS, VALID_SKILLS


def test_expected_skills_have_fixture_files():
    have = {p.parent.parent.name for p in FIXTURE_FILES}
    missing = EXPECTED_FIXTURE_SKILLS - have
    assert not missing, f"missing routing-fixtures.json for: {sorted(missing)}"


@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.parent.parent.name)
def test_fixture_file_is_well_formed(path: Path):
    data = _load(path)
    skill_dir = path.parent.parent.name

    assert data.get("skill_name") == skill_dir, (
        f"{path}: skill_name '{data.get('skill_name')}' != containing dir '{skill_dir}'"
    )
    assert skill_dir in VALID_SKILLS, f"{path}: not under a real skill"

    fixtures = data.get("fixtures")
    assert isinstance(fixtures, list) and fixtures, f"{path}: 'fixtures' must be a non-empty list"

    seen_ids = set()
    for fx in fixtures:
        fid = fx.get("id")
        assert isinstance(fid, str) and fid, f"{path}: every fixture needs a string id"
        assert fid not in seen_ids, f"{path}: duplicate fixture id '{fid}'"
        seen_ids.add(fid)

        assert isinstance(fx.get("request"), str) and len(fx["request"]) >= 20, (
            f"{path}:{fid}: 'request' must be a non-trivial string"
        )

        routing = fx.get("expected_routing")
        assert isinstance(routing, dict), f"{path}:{fid}: 'expected_routing' must be an object"
        assert routing.get("skill") in VALID_SKILLS, (
            f"{path}:{fid}: routes to unknown skill '{routing.get('skill')}'"
        )
        assert isinstance(routing.get("reason"), str) and routing["reason"], (
            f"{path}:{fid}: routing needs a 'reason'"
        )
        for other in routing.get("not", []):
            assert other in VALID_SKILLS, f"{path}:{fid}: 'not' lists unknown skill '{other}'"
            assert other != routing["skill"], f"{path}:{fid}: 'not' repeats the routed skill"

        fields = fx.get("required_output_fields")
        assert isinstance(fields, list) and fields, (
            f"{path}:{fid}: 'required_output_fields' must be a non-empty list"
        )
        assert all(isinstance(f, str) and f for f in fields), (
            f"{path}:{fid}: required_output_fields must be non-empty strings"
        )

        patterns = fx.get("forbidden_patterns")
        assert isinstance(patterns, list), f"{path}:{fid}: 'forbidden_patterns' must be a list"
        for pat in patterns:
            assert isinstance(pat, str) and pat, f"{path}:{fid}: forbidden pattern must be a string"
            try:
                re.compile(pat)
            except re.error as e:
                pytest.fail(f"{path}:{fid}: forbidden pattern '{pat}' is not valid regex: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
