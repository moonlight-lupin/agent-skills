#!/usr/bin/env python3
"""Unit tests for pexels-stock-photos SKILL.md structure and routing contract.

Run:  python -m pytest creative/pexels-stock-photos/tests/test_skill.py -v
  or:  python creative/pexels-stock-photos/tests/test_skill.py
"""

import re
import unittest
from pathlib import Path

SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.md"


class TestFrontmatter(unittest.TestCase):
    """Validate SKILL.md frontmatter matches repo conventions."""

    @classmethod
    def setUpClass(cls):
        cls.content = SKILL_MD.read_text()
        # Extract frontmatter between --- markers
        match = re.match(r"^---\n(.*?)\n---\n", cls.content, re.DOTALL)
        cls.fm_text = match.group(1) if match else ""

    def test_file_starts_with_frontmatter(self):
        self.assertTrue(
            self.content.startswith("---\n"),
            "SKILL.md must start with --- frontmatter delimiter",
        )

    def test_name_field(self):
        self.assertIn("name: pexels-stock-photos", self.fm_text)

    def test_description_field(self):
        self.assertIn("description:", self.fm_text)

    def test_version_field(self):
        self.assertIn("version:", self.fm_text)

    def test_author_field(self):
        self.assertIn("author: moonlight-lupin", self.fm_text)

    def test_license_field(self):
        self.assertIn("license: MIT", self.fm_text)

    def test_platforms_field(self):
        self.assertIn("platforms:", self.fm_text)

    def test_description_mentions_real_photo(self):
        """Description must signal 'real photo' to distinguish from AI generation."""
        self.assertIn("REAL photo", self.content)

    def test_description_mentions_pexels(self):
        self.assertIn("Pexels", self.content)

    def test_description_discourages_ai_art(self):
        """Description must redirect AI art requests away from this skill."""
        # Check the description or body mentions not using for AI generation
        self.assertTrue(
            "generate" in self.content.lower() and "do not" in self.content.lower(),
            "SKILL.md should mention it's not for AI-generated art",
        )


class TestRoutingContract(unittest.TestCase):
    """Validate the routing table distinguishes Pexels from AI generation."""

    @classmethod
    def setUpClass(cls):
        cls.content = SKILL_MD.read_text()

    def test_has_routing_table(self):
        self.assertIn("Routing:", self.content)

    def test_routing_mentions_photo_keyword(self):
        """Routing must route 'photo' requests to Pexels."""
        self.assertIn("photo", self.content.lower())

    def test_routing_mentions_generate_keyword(self):
        """Routing must route 'generate' requests to AI generation, not Pexels."""
        self.assertIn("generate", self.content.lower())

    def test_has_key_word_test(self):
        """The keyword test helps the agent distinguish photo vs generate."""
        self.assertIn("key word test", self.content.lower())

    def test_has_attribution_section(self):
        """Attribution is required by Pexels guidelines."""
        self.assertIn("Attribution", self.content)

    def test_has_api_reference(self):
        """API reference section must exist for agent to construct calls."""
        self.assertIn("API Reference", self.content)

    def test_has_search_endpoint(self):
        self.assertIn("/search", self.content)

    def test_has_download_workflow(self):
        """Workflow must include a download step."""
        self.assertIn("Download", self.content)

    def test_has_pitfalls_section(self):
        self.assertIn("Pitfalls", self.content)

    def test_has_verification_checklist(self):
        self.assertIn("Verification Checklist", self.content)

    def test_mentions_rate_limit(self):
        """Rate limit info must be present so the agent can manage quotas."""
        self.assertIn("200", self.content)

    def test_mentions_env_var(self):
        """PEXELS_API_KEY env var must be documented."""
        self.assertIn("PEXELS_API_KEY", self.content)


class TestNoHardcodedPaths(unittest.TestCase):
    """Ensure the skill is portable — no absolute paths to specific machines."""

    @classmethod
    def setUpClass(cls):
        cls.content = SKILL_MD.read_text()

    def test_no_machine_specific_paths(self):
        """No absolute paths into a specific user's home directory (e.g. /root/... or /home/<user>/...)."""
        hits = re.findall(r"(?:/root|/home/\w+)/\S*", self.content)
        self.assertEqual(hits, [], f"SKILL.md contains machine-specific paths: {hits}")

    def test_no_secrets(self):
        """No actual API keys in the skill file."""
        # Check there's no string that looks like a Pexels API key (56-char alphanumeric)
        suspicious = re.findall(r"[A-Za-z0-9]{50,}", self.content)
        # Filter out things that are clearly not keys (like long descriptions)
        for match in suspicious:
            # Pexels keys are 56 chars of alphanumeric
            if len(match) >= 50 and re.match(r"^[A-Za-z0-9]+$", match):
                self.fail(f"Possible API key found in SKILL.md: {match[:10]}...")


if __name__ == "__main__":
    unittest.main()