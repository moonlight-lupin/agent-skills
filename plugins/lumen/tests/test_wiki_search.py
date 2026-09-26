#!/usr/bin/env python3
"""Ported wiki_curator.py search subcommand tests."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CURATOR = PLUGIN_ROOT / "skills" / "curator" / "scripts" / "wiki_curator.py"


class TestWikiSearchSubcommand:
    """wiki_curator.py must have a search subcommand for retrieval."""

    def test_search_subcommand_exists(self):
        """wiki_curator.py must accept 'search' as a subcommand."""
        result = subprocess.run(
            [sys.executable, str(CURATOR), "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, f"wiki_curator --help failed: {result.stderr}"
        assert "search" in result.stdout, "wiki_curator.py must have a 'search' subcommand"

    def test_search_returns_json(self):
        """search --format json must return valid JSON."""
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            wiki.mkdir()
            (wiki / "index.md").write_text("---\ntype: index\n---\n# Index\n", encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(CURATOR),
                    "search",
                    "test",
                    "--format",
                    "json",
                    "--wiki",
                    str(wiki),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"search failed: {result.stderr}"
            data = json.loads(result.stdout)
            assert isinstance(data, list), "search --format json must return a list"

    def test_search_returns_results(self):
        """search must find pages matching the query."""
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            (wiki / "entities").mkdir(parents=True)
            (wiki / "concepts").mkdir(parents=True)
            (wiki / "index.md").write_text("---\ntype: index\n---\n# Index\n", encoding="utf-8")

            (wiki / "entities" / "acme-corp.md").write_text(
                "---\ntype: entity\ntitle: ACME Corporation\ntags: [clients]\n"
                "aliases: [ACME, Acme Corp]\n---\n"
                "# ACME Corporation\nACME is a key client in manufacturing.\n",
                encoding="utf-8",
            )
            (wiki / "concepts" / "supply-chain.md").write_text(
                "---\ntype: concept\ntitle: Supply Chain\ntags: [operations]\n---\n"
                "# Supply Chain\nManaging logistics and suppliers.\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CURATOR),
                    "search",
                    "ACME",
                    "--format",
                    "json",
                    "--wiki",
                    str(wiki),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"search failed: {result.stderr}"
            data = json.loads(result.stdout)
            assert len(data) >= 1, "search for 'ACME' must find the acme-corp page"
            first = data[0]
            assert "path" in first or "title" in first, (
                "search results must have at least path or title field"
            )

    def test_search_alias_match(self):
        """search must match aliases in frontmatter."""
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            (wiki / "entities").mkdir(parents=True)
            (wiki / "index.md").write_text("---\ntype: index\n---\n# Index\n", encoding="utf-8")

            (wiki / "entities" / "acme-corp.md").write_text(
                "---\ntype: entity\ntitle: ACME Corporation\n"
                "aliases: [ACME, Acme Corp]\n---\n"
                "# ACME Corporation\nA client.\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CURATOR),
                    "search",
                    "Acme Corp",
                    "--format",
                    "json",
                    "--wiki",
                    str(wiki),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"search failed: {result.stderr}"
            data = json.loads(result.stdout)
            assert len(data) >= 1, (
                "search must match aliases in frontmatter — 'Acme Corp' is an alias"
            )

    def test_search_text_format(self):
        """search --format text must return human-readable output."""
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            (wiki / "entities").mkdir(parents=True)
            (wiki / "index.md").write_text("---\ntype: index\n---\n# Index\n", encoding="utf-8")

            (wiki / "entities" / "acme-corp.md").write_text(
                "---\ntype: entity\ntitle: ACME Corporation\n---\n"
                "# ACME Corporation\nA client.\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CURATOR),
                    "search",
                    "ACME",
                    "--format",
                    "text",
                    "--wiki",
                    str(wiki),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"search failed: {result.stderr}"
            assert "ACME" in result.stdout, "search --format text must show matching page title"

    def test_search_limit_flag(self):
        """search --limit N must cap the number of results."""
        with tempfile.TemporaryDirectory() as tmp:
            wiki = Path(tmp) / "wiki"
            (wiki / "concepts").mkdir(parents=True)
            (wiki / "index.md").write_text("---\ntype: index\n---\n# Index\n", encoding="utf-8")

            for i in range(10):
                (wiki / "concepts" / f"concept-{i}.md").write_text(
                    f"---\ntype: concept\ntitle: Concept {i}\n---\n"
                    f"# Concept {i}\nA test concept about testing.\n",
                    encoding="utf-8",
                )

            result = subprocess.run(
                [
                    sys.executable,
                    str(CURATOR),
                    "search",
                    "concept",
                    "--format",
                    "json",
                    "--limit",
                    "3",
                    "--wiki",
                    str(wiki),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert result.returncode == 0, f"search failed: {result.stderr}"
            data = json.loads(result.stdout)
            assert len(data) <= 3, f"search --limit 3 must cap results, got {len(data)}"
