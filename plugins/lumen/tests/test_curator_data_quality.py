#!/usr/bin/env python3
"""Regression tests for the 0.1.2 curator data-quality fixes (slugs, name
splitting, stable fallback ids, heuristic entities, file modes, malformed
frontmatter, clean CLI errors)."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "skills" / "curator" / "scripts"
CURATOR = SCRIPTS / "wiki_curator.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import adapters  # noqa: E402
import wiki_curator  # noqa: E402


def _cfg(wiki: Path, memory_source: str = "json-file") -> dict:
    return {
        "paths": {"wiki_path": str(wiki)},
        "curator": {"timezone": "UTC", "max_write_pages": 20, "memory_source": memory_source},
    }


def _write_memory(wiki: Path, records: list[dict]) -> None:
    knowledge = wiki / ".knowledge"
    knowledge.mkdir(parents=True, exist_ok=True)
    (knowledge / "memory.json").write_text(json.dumps({"records": records}), encoding="utf-8")


def _run(cfg: dict) -> wiki_curator.WikiCurator:
    curator = wiki_curator.WikiCurator(cfg)
    items = wiki_curator._load_adapter_items(
        cfg, curator.wiki_path, curator.now - timedelta(days=1), curator.now
    )
    curator.curate_items(items)
    return curator


def _load(wiki: Path, records: list[dict]) -> list:
    _write_memory(wiki, records)
    now = datetime.now(timezone.utc)
    return adapters.JsonFileAdapter(wiki_path=wiki).load_items(now - timedelta(days=1), now)


def _ts(minutes_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _write_config_file(tmp_path: Path, wiki: Path) -> Path:
    path = tmp_path / "lumen.yaml"
    path.write_text(
        f"paths:\n  wiki_path: {wiki}\ncurator:\n  memory_source: json-file\n  timezone: UTC\n",
        encoding="utf-8",
    )
    return path


# ─── 1. Non-ASCII slugs ─────────────────────────────────────────────


class TestNonAsciiSlugs:
    def test_accented_name_is_transliterated(self):
        assert wiki_curator._slugify("Zoë") == "zoe"
        assert wiki_curator._slugify("José Núñez") == "jose-nunez"

    def test_ascii_slugs_unchanged(self):
        assert wiki_curator._slugify("Acme Logistics") == "acme-logistics"
        assert wiki_curator._slugify("") == "untitled"

    def test_non_latin_names_get_distinct_stable_slugs(self):
        first = wiki_curator._slugify("张伟")
        second = wiki_curator._slugify("李娜")
        assert first != second
        assert first == wiki_curator._slugify("张伟")
        digest = hashlib.sha256("张伟".encode("utf-8")).hexdigest()[:8]
        assert first == f"untitled-{digest}"

    def test_non_latin_people_land_on_distinct_pages(self, tmp_path):
        wiki = tmp_path / "wiki"
        _write_memory(
            wiki,
            [
                {"id": "c1", "timestamp": _ts(2), "text": "met zhang", "people": ["张伟"]},
                {"id": "c2", "timestamp": _ts(1), "text": "met li", "people": ["李娜"]},
                {"id": "c3", "timestamp": _ts(0), "text": "met zoe", "people": ["Zoë"]},
            ],
        )
        _run(_cfg(wiki))
        people = sorted(p.name for p in (wiki / "people").glob("*.md"))
        assert "untitled.md" not in people
        assert "zoe.md" in people
        zhang = wiki / "people" / f"{wiki_curator._slugify('张伟')}.md"
        li = wiki / "people" / f"{wiki_curator._slugify('李娜')}.md"
        assert zhang != li
        assert "met zhang" in zhang.read_text(encoding="utf-8")
        assert "met li" in li.read_text(encoding="utf-8")
        assert "met zhang" not in li.read_text(encoding="utf-8")

        # Second run with a new record for the same person reuses the page.
        _write_memory(
            wiki,
            [{"id": "c4", "timestamp": _ts(0), "text": "zhang again", "people": ["张伟"]}],
        )
        _run(_cfg(wiki))
        assert len(list((wiki / "people").glob("*.md"))) == 3
        assert "zhang again" in zhang.read_text(encoding="utf-8")


# ─── 2. String values are one name ─────────────────────────────────


class TestNameSplitting:
    def test_string_entity_with_comma_is_one_name(self, tmp_path):
        items = _load(
            tmp_path / "wiki",
            [{"id": "n1", "timestamp": _ts(), "text": "deal", "entities": "Acme, Inc."}],
        )
        assert items[0].entities == ["Acme, Inc."]

    def test_string_person_with_comma_is_one_name(self, tmp_path):
        items = _load(
            tmp_path / "wiki",
            [{"id": "n2", "timestamp": _ts(), "text": "call", "people": "Doe, Jane"}],
        )
        assert items[0].people == ["Doe, Jane"]

    def test_list_values_still_yield_multiple_names(self, tmp_path):
        items = _load(
            tmp_path / "wiki",
            [{"id": "n3", "timestamp": _ts(), "text": "call", "people": ["Ann", "Bob"]}],
        )
        assert items[0].people == ["Ann", "Bob"]


# ─── 3. Position-independent fallback ids ───────────────────────────


class TestStableFallbackIds:
    def test_fallback_id_ignores_list_position(self, tmp_path):
        wiki = tmp_path / "wiki"
        a = {"timestamp": _ts(5), "text": "Dana confirmed the pricing", "people": ["Dana"]}
        x = {"timestamp": _ts(10), "text": "unrelated note", "people": ["Xavier"]}
        first = _load(wiki, [a])
        second = _load(wiki, [x, a])
        ids = {item.text: item.source_id for item in second}
        assert ids["Dana confirmed the pricing"] == first[0].source_id

    def test_inserting_record_ahead_does_not_duplicate_observation(self, tmp_path):
        wiki = tmp_path / "wiki"
        a = {"timestamp": _ts(5), "text": "Dana confirmed the pricing", "people": ["Dana"]}
        x = {"timestamp": _ts(10), "text": "unrelated note", "people": ["Xavier"]}
        _write_memory(wiki, [a])
        _run(_cfg(wiki))
        _write_memory(wiki, [x, a])
        _run(_cfg(wiki))
        page = (wiki / "people" / "dana.md").read_text(encoding="utf-8")
        body = page.split("## Source-backed observations", 1)[1].split("\n## ", 1)[0]
        assert body.count("Dana confirmed the pricing") == 1


# ─── 4. Capitalised-word heuristic ──────────────────────────────────


class TestHeuristicEntities:
    TEXT = "Met with Dana yesterday. Sent Proposal v2 to Jane."

    def test_sentence_initial_words_are_not_entities(self, tmp_path):
        items = _load(tmp_path / "wiki", [{"id": "h1", "timestamp": _ts(), "text": self.TEXT}])
        assert items[0].entities == ["Dana", "Jane"]

    def test_run_creates_no_junk_pages(self, tmp_path):
        wiki = tmp_path / "wiki"
        _write_memory(wiki, [{"id": "h2", "timestamp": _ts(), "text": self.TEXT}])
        _run(_cfg(wiki))
        names = {p.name for p in (wiki / "entities").glob("*.md")}
        assert {"dana.md", "jane.md"} <= names
        for junk in ("untitled-met.md", "sent-proposal.md", "met.md", "untitled.md"):
            assert junk not in names

    def test_name_run_does_not_cross_sentence_boundary(self):
        assert adapters._heuristic_entities("Met with Dana. Sent Proposal v2 to Jane.") == ["Dana", "Jane"]

    def test_placeholder_title_is_not_scanned(self, tmp_path):
        items = _load(tmp_path / "wiki", [{"id": "h3", "timestamp": _ts(), "text": "call back later"}])
        assert items[0].title == "Untitled"
        assert items[0].entities == []

    def test_sentence_initial_word_kept_when_seen_mid_sentence(self, tmp_path):
        items = _load(
            tmp_path / "wiki",
            [{"id": "h4", "timestamp": _ts(), "text": "Acme signed today. Dana thanked Acme for it."}],
        )
        assert "Acme" in items[0].entities
        assert "Dana" not in items[0].entities

    def test_mnemosyne_content_uses_same_rule(self):
        now = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
        items = adapters.parse_mnemosyne_envelope(
            {"working_memory": [{"id": "m1", "content": self.TEXT, "timestamp": now.isoformat()}]},
            cutoff=now - timedelta(days=1),
            now=now,
        )
        assert items[0].entities == ["Dana", "Jane"]


# ─── 5. File modes preserved by atomic writes ───────────────────────


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
class TestAtomicWriteMode:
    def test_existing_file_mode_is_preserved(self, tmp_path):
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        page = wiki / "page.md"
        page.write_text("old\n", encoding="utf-8")
        os.chmod(page, 0o644)
        wiki_curator._atomic_write(page, "new\n", wiki)
        assert page.read_text(encoding="utf-8") == "new\n"
        assert stat.S_IMODE(page.stat().st_mode) == 0o644

    def test_new_file_honours_umask(self, tmp_path):
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        page = wiki / "fresh.md"
        current = os.umask(0)
        os.umask(current)
        wiki_curator._atomic_write(page, "hello\n", wiki)
        assert stat.S_IMODE(page.stat().st_mode) == 0o666 & ~current

    def test_curated_page_keeps_mode(self, tmp_path):
        wiki = tmp_path / "wiki"
        _write_memory(wiki, [{"id": "p1", "timestamp": _ts(1), "text": "one", "people": ["Ann"]}])
        _run(_cfg(wiki))
        page = wiki / "people" / "ann.md"
        os.chmod(page, 0o644)
        _write_memory(wiki, [{"id": "p2", "timestamp": _ts(0), "text": "two", "people": ["Ann"]}])
        _run(_cfg(wiki))
        assert "two" in page.read_text(encoding="utf-8")
        assert stat.S_IMODE(page.stat().st_mode) == 0o644


# ─── 6. Malformed frontmatter is never overwritten ──────────────────


class TestMalformedFrontmatter:
    PAGE = "---\ntitle: Mal: the great\naliases: [M]\n---\n\n# Mal\n\nHand-written notes.\n"

    def test_malformed_page_is_left_untouched_and_reported(self, tmp_path, capsys):
        wiki = tmp_path / "wiki"
        page = wiki / "people" / "mal.md"
        page.parent.mkdir(parents=True)
        page.write_bytes(self.PAGE.encode("utf-8"))
        _write_memory(wiki, [{"id": "f1", "timestamp": _ts(), "text": "Mal called", "people": ["Mal"]}])
        curator = _run(_cfg(wiki))
        assert page.read_bytes() == self.PAGE.encode("utf-8")
        report = curator.report_changes([])
        assert "people/mal.md" in report
        assert "frontmatter" in report
        assert "people/mal.md" in capsys.readouterr().err
        # Other pages for the item are still written.
        assert any((wiki / "daily").glob("*.md"))

    def test_malformed_page_stays_untouched_on_rerun(self, tmp_path):
        wiki = tmp_path / "wiki"
        page = wiki / "people" / "mal.md"
        page.parent.mkdir(parents=True)
        page.write_bytes(self.PAGE.encode("utf-8"))
        _write_memory(wiki, [{"id": "f2", "timestamp": _ts(), "text": "Mal called", "people": ["Mal"]}])
        _run(_cfg(wiki))
        curator = _run(_cfg(wiki))
        assert page.read_bytes() == self.PAGE.encode("utf-8")
        assert "people/mal.md" in curator.report_changes([])


# ─── 7. Clean CLI errors ────────────────────────────────────────────


class TestCleanCliErrors:
    def test_bad_since_is_a_clean_usage_error(self, tmp_path):
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        config = _write_config_file(tmp_path, wiki)
        result = subprocess.run(
            [sys.executable, str(CURATOR), "--config", str(config), "run", "--since", "1y"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "Traceback" not in result.stderr
        assert "--since" in result.stderr

    def test_bad_since_via_main_exits_2(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            wiki_curator.main(["report", "--since", "1y", "--wiki", str(tmp_path)])
        assert exc.value.code == 2
        assert "Traceback" not in capsys.readouterr().err

    @pytest.mark.skipif(os.name == "nt", reason="symlinks")
    def test_symlinked_wiki_subdir_is_a_clean_error(self, tmp_path, capsys):
        wiki = tmp_path / "wiki"
        outside = tmp_path / "outside"
        outside.mkdir()
        wiki.mkdir()
        (wiki / "people").symlink_to(outside, target_is_directory=True)
        _write_memory(wiki, [{"id": "s1", "timestamp": _ts(), "text": "t", "people": ["Ann"]}])
        config = _write_config_file(tmp_path, wiki)
        rc = wiki_curator.main(["--config", str(config), "run", "--since", "1d"])
        err = capsys.readouterr().err
        assert rc != 0
        assert err.startswith("error: ")
        assert "Traceback" not in err
        assert not any(outside.iterdir())
