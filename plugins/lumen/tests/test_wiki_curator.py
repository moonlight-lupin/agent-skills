#!/usr/bin/env python3
"""Ported wiki curator tests (ingest + lint). Memory comes from JsonFileAdapter."""

from __future__ import annotations

import ast
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import yaml
import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PLUGIN_ROOT / "skills" / "curator" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

FORBIDDEN_IMPORTS = {
    "requests",
    "httpx",
    "urllib.request",
    "socket",
    "smtplib",
    "openai",
    "anthropic",
}


def _write_config(project: Path, wiki: Path, memory_source: str = "json-file") -> tuple[dict, Path]:
    config = {
        "paths": {"wiki_path": str(wiki)},
        "curator": {
            "timezone": "Asia/Singapore",
            "max_write_pages": 20,
            "memory_source": memory_source,
        },
    }
    config_path = project / "lumen.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return config, config_path


def _seed_memory(wiki: Path) -> None:
    knowledge = wiki / ".knowledge"
    knowledge.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "version": 0,
        "records": {
            "mem_001": {
                "id": "mem_001",
                "timestamp": now,
                "text": "Dana from Acme Logistics asked about the quarterly pricing review timeline.",
                "people": ["Dana"],
                "entities": ["Acme Logistics"],
                "projects": ["pricing-review"],
                "tags": ["pricing"],
            }
        },
    }
    (knowledge / "memory.json").write_text(json.dumps(payload), encoding="utf-8")


def _make_wiki_page(
    path: Path,
    title: str,
    page_type: str = "entity",
    updated: str = "2026-07-10",
    confidence: float | None = None,
    status: str = "draft",
    body: str = "",
) -> None:
    fm = f"---\ntype: {page_type}\ntitle: {title}\nupdated: {updated}\nstatus: {status}\n"
    if confidence is not None:
        fm += f"confidence: {confidence}\n"
    fm += f"---\n\n# {title}\n\n{body}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(fm, encoding="utf-8")


def _snapshot_tree(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def _frontmatter(content: str) -> dict:
    assert content.startswith("---"), "expected YAML frontmatter"
    end = content.find("\n---", 3)
    assert end != -1, "expected closing frontmatter marker"
    data = yaml.safe_load(content[4:end])
    assert isinstance(data, dict), "frontmatter must be a mapping"
    return data


@pytest.fixture
def temp_with_config(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    wiki = project / "wiki"
    wiki.mkdir()
    for name in ("raw", "daily", "projects", "entities", "people", "decisions"):
        (wiki / name).mkdir()
    config, config_path = _write_config(project, wiki)
    return config, project, config_path


@pytest.fixture
def temp_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    wiki = project / "wiki"
    config, config_path = _write_config(project, wiki)
    return config, project, config_path


class TestWikiCurator:
    def test_wiki_curator_run_creates_daily_log(self, temp_with_config):
        """Wiki curator creates daily log pages."""
        config, project, config_path = temp_with_config
        wiki = project / "wiki"
        _seed_memory(wiki)

        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki_curator.main(["run", "--since", "24h", "--config", str(config_path)])

        daily_files = list((wiki / "daily").glob("*.md"))
        assert daily_files, "expected a daily log page"
        content = daily_files[0].read_text(encoding="utf-8")
        assert "## " in content
        assert rc == 0

    def test_wiki_curator_run_dry_run(self, temp_with_config):
        """Dry-run reports without writing."""
        config, project, config_path = temp_with_config
        wiki = project / "wiki"
        _seed_memory(wiki)
        sandbox = project.parent
        before = _snapshot_tree(sandbox)

        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki_curator.main(
                ["run", "--since", "24h", "--dry-run", "--config", str(config_path)]
            )

        assert _snapshot_tree(sandbox) == before
        assert rc == 0

    def test_wiki_curator_no_provider_calls(self):
        """Wiki curator must not import network or provider clients."""
        hits = []
        for path in PLUGIN_ROOT.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            for name in imported:
                for forbidden in FORBIDDEN_IMPORTS:
                    if name == forbidden or name.startswith(forbidden + "."):
                        hits.append(f"{path.relative_to(PLUGIN_ROOT)}: {name}")
        assert hits == [], "forbidden imports:\n" + "\n".join(hits)

    def test_wiki_curator_creates_frontmatter(self, temp_with_config):
        """Created pages have valid YAML frontmatter."""
        config, project, config_path = temp_with_config
        _seed_memory(project / "wiki")

        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            wiki_curator.main(["run", "--since", "24h", "--config", str(config_path)])

        wiki = project / "wiki"
        pages = list(wiki.rglob("*.md"))
        assert pages, "expected curated markdown pages"
        for md_file in pages:
            content = md_file.read_text(encoding="utf-8")
            fm = _frontmatter(content)
            assert str(fm.get("type") or "").strip(), f"{md_file} missing non-empty type"

    def test_wiki_curator_updates_log(self, temp_with_config):
        """Wiki curator appends to log.md."""
        config, project, config_path = temp_with_config
        _seed_memory(project / "wiki")
        log_path = project / "wiki" / "log.md"
        before = log_path.read_text(encoding="utf-8") if log_path.exists() else ""

        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            wiki_curator.main(["run", "--since", "24h", "--config", str(config_path)])

        assert log_path.is_file()
        after = log_path.read_text(encoding="utf-8")
        assert len(after) > len(before)

    def test_wiki_curator_validate(self, temp_with_config):
        """Validate command succeeds on a well-formed tree."""
        config, project, config_path = temp_with_config
        wiki = project / "wiki"
        _make_wiki_page(
            wiki / "index.md",
            "Index",
            page_type="index",
            body="- [Alpha](entities/alpha.md)",
        )
        _make_wiki_page(wiki / "entities" / "alpha.md", "Alpha", body="See the index.")

        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki_curator.main(["validate", "--config", str(config_path)])

        assert rc == 0, buf.getvalue()

    def test_wiki_curator_empty_state(self, temp_with_config):
        """Empty wiki with no memory items should not crash."""
        config, project, config_path = temp_with_config
        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki_curator.main(["run", "--since", "24h", "--config", str(config_path)])
        assert rc == 0

    def test_wiki_curator_malformed_pages(self, temp_with_config):
        """Malformed wiki pages should degrade gracefully."""
        config, project, config_path = temp_with_config
        wiki = project / "wiki"
        (wiki / "entities" / "broken.md").write_text(
            "---\ninvalid: yaml: content: [\n---\n# Broken\n", encoding="utf-8"
        )
        (wiki / "entities" / "no-fm.md").write_text("# No frontmatter at all\n", encoding="utf-8")

        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki_curator.main(["validate", "--config", str(config_path)])
        output = buf.getvalue()
        assert rc == 1
        assert "ERROR" in output

    def test_wiki_curator_no_destructive_ops(self, temp_with_config):
        """Wiki curator must not delete files."""
        config, project, config_path = temp_with_config
        wiki = project / "wiki"
        test_file = wiki / "entities" / "existing.md"
        original = "# Existing\n\nThis should not be deleted.\n"
        test_file.write_text(original, encoding="utf-8")
        _seed_memory(wiki)

        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            wiki_curator.main(["run", "--since", "24h", "--config", str(config_path)])

        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == original

    def test_max_write_pages_caps_and_zero_disables(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)

        def make_items():
            return [
                wiki_curator.SourceItem(
                    source_id=f"s{i}",
                    source_kind="memory",
                    title=f"Title {i}",
                    text=f"Body {i}",
                    timestamp=now,
                    people=[f"Person{i}"],
                )
                for i in range(5)
            ]

        def people_count(wiki: Path) -> int:
            folder = wiki / "people"
            if not folder.is_dir():
                return 0
            return len(list(folder.glob("*.md")))

        wiki_cap = tmp_path / "wiki-cap"
        wiki_cap.mkdir()
        curator = wiki_curator.WikiCurator(
            {
                "paths": {"wiki_path": str(wiki_cap)},
                "curator": {"max_write_pages": 2, "memory_source": "none"},
            }
        )
        curator.curate_items(make_items())
        assert people_count(wiki_cap) == 2

        wiki_all = tmp_path / "wiki-all"
        wiki_all.mkdir()
        curator = wiki_curator.WikiCurator(
            {
                "paths": {"wiki_path": str(wiki_all)},
                "curator": {"max_write_pages": 0, "memory_source": "none"},
            }
        )
        curator.curate_items(make_items())
        assert people_count(wiki_all) == 5

    def test_max_write_pages_applies_to_outstanding_work(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)
        items = [
            wiki_curator.SourceItem(
                source_id=f"s{i}",
                source_kind="memory",
                title=f"Title {i}",
                text=f"Body {i}",
                timestamp=now,
                people=[f"Person{i}"],
            )
            for i in range(3)
        ]
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 2, "memory_source": "none"},
        }

        def people_stems() -> set[str]:
            folder = wiki / "people"
            if not folder.is_dir():
                return set()
            return {path.stem for path in folder.glob("*.md")}

        def observation_bullets() -> list[str]:
            folder = wiki / "people"
            if not folder.is_dir():
                return []
            found = []
            for path in sorted(folder.glob("*.md")):
                text = path.read_text(encoding="utf-8")
                start = text.find("## Source-backed observations")
                if start < 0:
                    continue
                rest = text[start:]
                nxt = rest.find("\n## ", 1)
                section = rest if nxt < 0 else rest[:nxt]
                for line in section.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("- ") and "[source:" in stripped:
                        found.append(stripped)
            return found

        wiki_curator.WikiCurator(cfg).curate_items(items)
        assert people_stems() == {"person0", "person1"}
        first = observation_bullets()
        assert len(first) == 2

        wiki_curator.WikiCurator(cfg).curate_items(items)
        assert people_stems() == {"person0", "person1", "person2"}
        second = observation_bullets()
        assert len(second) == 3
        assert len(set(second)) == 3

        wiki_curator.WikiCurator(cfg).curate_items(items)
        assert people_stems() == {"person0", "person1", "person2"}
        third = observation_bullets()
        assert third == second

    def test_backup_skips_symlinked_lumen(self, tmp_path, capsys):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        (wiki / "index.md").write_text("# Index\n", encoding="utf-8")
        outside = tmp_path / "outside"
        outside.mkdir()
        (wiki / ".lumen").symlink_to(outside)
        items = [
            wiki_curator.SourceItem(
                source_id=f"s{i}",
                source_kind="memory",
                title=f"Title {i}",
                text=f"Body {i}",
                timestamp=now,
                people=[f"Person{i}"],
            )
            for i in range(6)
        ]
        before_outside = _snapshot_tree(outside)
        curator = wiki_curator.WikiCurator(
            {
                "paths": {"wiki_path": str(wiki)},
                "curator": {"max_write_pages": 0, "memory_source": "none"},
            }
        )
        curator.curate_items(items)
        err = capsys.readouterr().err
        assert "warning: skipping backup: .lumen is not a trusted directory" in err
        assert _snapshot_tree(outside) == before_outside
        assert not any(path.is_file() for path in outside.rglob("*"))
        details = [change.detail for change in curator.changes]
        assert any("skipping backup" in detail for detail in details)
        people = wiki / "people"
        assert people.is_dir()
        assert len(list(people.glob("*.md"))) == 6

    def test_partial_daily_source_is_not_a_tombstone(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        daily = wiki / "daily"
        daily.mkdir(parents=True)
        day = now.date().isoformat()
        (daily / f"{day}.md").write_text(
            f"""---
type: daily
title: {day}
sources:
  - person0
---

# {day}

## Recent activity

- [12:00] Body v1 [source: person0]

## Related pages

- [[person0]]
""",
            encoding="utf-8",
        )
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        item = wiki_curator.SourceItem(
            source_id="person0",
            source_kind="memory",
            title="Body v1",
            text="Body v1",
            timestamp=now,
            entities=["person0"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([item])
        assert (wiki / "entities" / "person0.md").is_file()

    def test_changed_source_rerenders_and_logs_update(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        v1 = wiki_curator.SourceItem(
            source_id="s1",
            source_kind="memory",
            title="Title v1",
            text="Body v1",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([v1])
        person = wiki / "people" / "dana.md"
        assert "Body v1" in person.read_text(encoding="utf-8")
        v2 = wiki_curator.SourceItem(
            source_id="s1",
            source_kind="memory",
            title="Title v2",
            text="Body v2 changed",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([v2])
        after = person.read_text(encoding="utf-8")
        assert "Body v2 changed" in after
        log = (wiki / "log.md").read_text(encoding="utf-8")
        assert "update:" in log

    def test_identical_source_is_skipped_silently(self, tmp_path, capsys):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        item = wiki_curator.SourceItem(
            source_id="s1",
            source_kind="memory",
            title="Title v1",
            text="Body v1",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([item])
        before = (wiki / "people" / "dana.md").read_text(encoding="utf-8")
        capsys.readouterr()
        wiki_curator.WikiCurator(cfg).curate_items([item])
        after = (wiki / "people" / "dana.md").read_text(encoding="utf-8")
        err = capsys.readouterr().err
        assert after == before
        assert "warning: source s1 changed" not in err

    def test_merged_page_change_emits_warning(self, tmp_path, capsys):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        a = wiki_curator.SourceItem(
            source_id="s1",
            source_kind="memory",
            title="Title 1",
            text="Body v1",
            timestamp=now,
            people=["Dana"],
        )
        b = wiki_curator.SourceItem(
            source_id="s2",
            source_kind="memory",
            title="Title 2",
            text="Other body",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([a, b])
        capsys.readouterr()
        a2 = wiki_curator.SourceItem(
            source_id="s1",
            source_kind="memory",
            title="Title 1",
            text="Body v2 changed",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([a2])
        err = capsys.readouterr().err
        assert "warning: source s1 changed but shares a merged page; manual review needed" in err
        text = (wiki / "people" / "dana.md").read_text(encoding="utf-8")
        assert "Body v2 changed" in text

    def test_backup_skips_noop_rerun_of_processed_items(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        (wiki / "seed.md").write_text("# seed\n", encoding="utf-8")
        items = [
            wiki_curator.SourceItem(
                source_id=f"s{i}",
                source_kind="memory",
                title=f"Title {i}",
                text=f"Body {i}",
                timestamp=now,
                people=[f"Person{i}"],
            )
            for i in range(6)
        ]
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 0, "memory_source": "none"},
        }
        wiki_curator.WikiCurator(cfg).curate_items(items)
        backup_root = wiki / ".lumen" / "backup"
        first = {p.name for p in backup_root.iterdir()} if backup_root.is_dir() else set()
        wiki_curator.WikiCurator(cfg).curate_items(items)
        second = {p.name for p in backup_root.iterdir()} if backup_root.is_dir() else set()
        assert second == first

    def test_changed_source_cap_defers_without_stripping(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 1, "memory_source": "none"},
        }
        v1 = [
            wiki_curator.SourceItem(
                source_id="s1",
                source_kind="memory",
                title="Title 1",
                text="Body s1 v1",
                timestamp=now,
                people=["Ada"],
            ),
            wiki_curator.SourceItem(
                source_id="s2",
                source_kind="memory",
                title="Title 2",
                text="Body s2 v1",
                timestamp=now,
                people=["Bea"],
            ),
        ]
        wiki_curator.WikiCurator(cfg).curate_items(v1)
        wiki_curator.WikiCurator({**cfg, "curator": {"max_write_pages": 20, "memory_source": "none"}}).curate_items(v1)
        ada = wiki / "people" / "ada.md"
        bea = wiki / "people" / "bea.md"
        assert "Body s1 v1" in ada.read_text(encoding="utf-8")
        assert "Body s2 v1" in bea.read_text(encoding="utf-8")
        v2 = [
            wiki_curator.SourceItem(
                source_id="s1",
                source_kind="memory",
                title="Title 1",
                text="Body s1 v2",
                timestamp=now,
                people=["Ada"],
            ),
            wiki_curator.SourceItem(
                source_id="s2",
                source_kind="memory",
                title="Title 2",
                text="Body s2 v2",
                timestamp=now,
                people=["Bea"],
            ),
        ]
        wiki_curator.WikiCurator(cfg).curate_items(v2)
        ada_text = ada.read_text(encoding="utf-8")
        bea_text = bea.read_text(encoding="utf-8")
        assert "Body s1 v2" in ada_text
        assert "Body s1 v1" not in ada_text
        assert "Body s2 v1" in bea_text
        assert "Body s2 v2" not in bea_text
        assert "[source: s2]" in bea_text
        wiki_curator.WikiCurator(cfg).curate_items(v2)
        bea_after = bea.read_text(encoding="utf-8")
        assert "Body s2 v2" in bea_after
        assert "Body s2 v1" not in bea_after

    def test_changed_source_backup_is_pre_mutation(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 1, "memory_source": "none"},
        }
        v1 = [
            wiki_curator.SourceItem(
                source_id=f"s{i}",
                source_kind="memory",
                title=f"Title {i}",
                text=f"Body {i} old",
                timestamp=now,
                people=[f"Person{i}"],
            )
            for i in range(6)
        ]
        first = wiki_curator.WikiCurator(
            {
                "paths": {"wiki_path": str(wiki)},
                "curator": {"max_write_pages": 0, "memory_source": "none"},
            }
        )
        first.curate_items(v1)
        v2 = [
            wiki_curator.SourceItem(
                source_id=f"s{i}",
                source_kind="memory",
                title=f"Title {i}",
                text=f"Body {i} new",
                timestamp=now,
                people=[f"Person{i}"],
            )
            for i in range(6)
        ]
        second = wiki_curator.WikiCurator(cfg)
        second.now = first.now + timedelta(seconds=5)
        second.today = second.now.date().isoformat()
        second.curate_items(v2)
        backup = wiki / ".lumen" / "backup" / second.now.strftime("%Y%m%dT%H%M%S")
        assert backup.is_dir()
        for i in range(6):
            backed = backup / "people" / f"person{i}.md"
            assert backed.is_file()
            text = backed.read_text(encoding="utf-8")
            assert f"Body {i} old" in text
            assert f"Body {i} new" not in text
        live0 = (wiki / "people" / "person0.md").read_text(encoding="utf-8")
        live1 = (wiki / "people" / "person1.md").read_text(encoding="utf-8")
        assert "Body 0 new" in live0
        assert "Body 1 old" in live1
        assert "Body 1 new" not in live1

    def test_multiline_unchanged_source_is_not_rewritten(self, tmp_path, capsys):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 1, "memory_source": "none"},
        }
        items = [
            wiki_curator.SourceItem(
                source_id="s1",
                source_kind="memory",
                title="Title 1",
                text="Line one of observation\nLine two of observation",
                timestamp=now,
                people=["Alex"],
            ),
            wiki_curator.SourceItem(
                source_id="s2",
                source_kind="memory",
                title="Title 2",
                text="Single line body",
                timestamp=now,
                people=["Blair"],
            ),
        ]
        wiki_curator.WikiCurator(cfg).curate_items(items)
        alex = wiki / "people" / "alex.md"
        before = alex.read_text(encoding="utf-8")
        assert "Line one of observation" in before
        assert "Line two of observation" in before
        capsys.readouterr()
        second = wiki_curator.WikiCurator(cfg)
        second.curate_items(items)
        after = alex.read_text(encoding="utf-8")
        assert after == before
        assert after.count("Line one of observation") == 1
        assert after.count("Line two of observation") == 1
        blair = wiki / "people" / "blair.md"
        assert blair.is_file()
        assert "Single line body" in blair.read_text(encoding="utf-8")
        log = (wiki / "log.md").read_text(encoding="utf-8")
        update_lines = [line for line in log.splitlines() if line.startswith("- update:") and "s1" in line]
        assert update_lines == []
        assert not any(
            change.action == "update" and "s1" in change.detail for change in second.changes
        )

    def test_partial_second_person_is_retried(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        item = wiki_curator.SourceItem(
            source_id="pair",
            source_kind="memory",
            title="Two people",
            text="Shared observation",
            timestamp=now,
            people=["Alice", "Bob"],
        )
        original = wiki_curator.WikiCurator.maybe_write

        def boom(self, path, content, action, detail):
            if path.name == "bob.md":
                raise RuntimeError("synthetic bob write failure")
            return original(self, path, content, action, detail)

        curator = wiki_curator.WikiCurator(cfg)
        with patch.object(wiki_curator.WikiCurator, "maybe_write", boom):
            try:
                curator.curate_items([item])
            except RuntimeError:
                pass
        alice = wiki / "people" / "alice.md"
        bob = wiki / "people" / "bob.md"
        assert alice.is_file()
        assert not bob.exists()
        wiki_curator.WikiCurator(cfg).curate_items([item])
        assert bob.is_file()
        alice_text = alice.read_text(encoding="utf-8")
        assert alice_text.count("Shared observation") == 1
        assert "Shared observation" in bob.read_text(encoding="utf-8")

    def test_operator_confirmed_facts_are_not_stripped(self, tmp_path, capsys):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        v1 = wiki_curator.SourceItem(
            source_id="s0",
            source_kind="memory",
            title="Title v1",
            text="Body v1",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([v1])
        person = wiki / "people" / "dana.md"
        seeded = person.read_text(encoding="utf-8")
        updated = seeded.replace(
            "(None yet)",
            "- Approved budget is 42.\n  Evidence: [source: s0]",
            1,
        )
        assert updated != seeded
        person.write_text(updated, encoding="utf-8")
        capsys.readouterr()
        v2 = wiki_curator.SourceItem(
            source_id="s0",
            source_kind="memory",
            title="Title v2",
            text="Body v2",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([v2])
        after = person.read_text(encoding="utf-8")
        assert "Approved budget is 42." in after
        assert "Evidence: [source: s0]" in after
        assert "Body v2" in after
        assert "Body v1" not in after
        err = capsys.readouterr().err
        assert err.count("\n") >= 1 or err
        assert "warning:" in err
        assert "s0" in err
        warning_lines = [line for line in err.splitlines() if line.startswith("warning:")]
        assert warning_lines, err
        assert len(warning_lines) == 1

    @pytest.mark.parametrize(
        "body",
        [
            "First paragraph\n\nSecond paragraph",
            "First paragraph\n- nested bullet\nSecond paragraph",
            "First paragraph\n# heading\nSecond paragraph",
        ],
    )
    def test_multiline_unchanged_source_spans_continuations(self, tmp_path, capsys, body):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 1, "memory_source": "none"},
        }
        items = [
            wiki_curator.SourceItem(
                source_id="s1",
                source_kind="memory",
                title="Title 1",
                text=body,
                timestamp=now,
                people=["Alex"],
            ),
            wiki_curator.SourceItem(
                source_id="s2",
                source_kind="memory",
                title="Title 2",
                text="Sibling body",
                timestamp=now,
                people=["Blair"],
            ),
        ]
        first = wiki_curator.WikiCurator(cfg)
        first.curate_items(items)
        alex = wiki / "people" / "alex.md"
        before = alex.read_text(encoding="utf-8")
        opening = body.splitlines()[0]
        assert opening in before
        assert before.count(opening) == 1
        capsys.readouterr()
        for _ in range(2):
            later = wiki_curator.WikiCurator(cfg)
            later.curate_items(items)
            after = alex.read_text(encoding="utf-8")
            assert after == before
            assert after.count(opening) == 1
            assert not any(
                change.action == "update" and "s1" in change.detail for change in later.changes
            )
        blair = wiki / "people" / "blair.md"
        assert blair.is_file()
        assert "Sibling body" in blair.read_text(encoding="utf-8")

    def test_precreated_second_person_partial_write_is_retried(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        earlier = wiki_curator.SourceItem(
            source_id="earlier",
            source_kind="memory",
            title="Earlier bob",
            text="Old bob fact",
            timestamp=now,
            people=["Bob"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([earlier])
        bob = wiki / "people" / "bob.md"
        assert bob.is_file()
        item = wiki_curator.SourceItem(
            source_id="pair",
            source_kind="memory",
            title="Two people",
            text="Shared observation",
            timestamp=now,
            people=["Alice", "Bob"],
        )
        original = wiki_curator.WikiCurator.maybe_write

        def boom(self, path, content, action, detail):
            if path.name == "bob.md":
                raise RuntimeError("synthetic bob write failure")
            return original(self, path, content, action, detail)

        curator = wiki_curator.WikiCurator(cfg)
        with patch.object(wiki_curator.WikiCurator, "maybe_write", boom):
            try:
                curator.curate_items([item])
            except RuntimeError:
                pass
        alice = wiki / "people" / "alice.md"
        assert alice.is_file()
        assert "Shared observation" in alice.read_text(encoding="utf-8")
        assert "Shared observation" not in bob.read_text(encoding="utf-8")
        wiki_curator.WikiCurator(cfg).curate_items([item])
        alice_text = alice.read_text(encoding="utf-8")
        bob_text = bob.read_text(encoding="utf-8")
        assert alice_text.count("Shared observation") == 1
        assert "Shared observation" in bob_text
        assert "Old bob fact" in bob_text

    def test_star_plus_ordered_markers_are_block_starts(self):
        import wiki_curator

        intro = "Some intro para worth keeping"
        cases = [
            [intro, "* item body [source: s1]"],
            [intro, "+ item body [source: s1]"],
            [intro, "1. item body [source: s1]"],
            [intro, "12. item body [source: s1]"],
            [intro, "- item body [source: s1]"],
            [intro, "# Heading body [source: s1]"],
        ]
        for lines in cases:
            assert wiki_curator._attributed_block_spans(lines, "s1") == [(1, 2)], lines
        assert wiki_curator._is_markdown_block_start("* item")
        assert wiki_curator._is_markdown_block_start("+ item")
        assert wiki_curator._is_markdown_block_start("1. item")
        assert wiki_curator._is_markdown_block_start("# Heading")
        assert wiki_curator._is_markdown_block_start("- bullet")
        assert not wiki_curator._is_markdown_block_start("*item")
        assert not wiki_curator._is_markdown_block_start("plain text")

    def test_star_bullet_strip_preserves_intro(self, tmp_path, capsys):
        import wiki_curator

        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        text = """---
type: person
title: Dana
sources:
  - s1
---

# Dana

## Source-backed observations

Some intro para worth keeping
* item body [source: s1]

## Recent activity

(None yet)
"""
        curator = wiki_curator.WikiCurator(cfg)
        stripped = curator._strip_source_from_text(text, "s1")
        assert "Some intro para worth keeping" in stripped
        assert "* item body [source: s1]" not in stripped
        assert "item body" not in stripped

    def test_strip_preserves_trailing_unattributed_operator_note(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        v1 = wiki_curator.SourceItem(
            source_id="c1",
            source_kind="memory",
            title="Title c1",
            text="Observation",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([v1])
        person = wiki / "people" / "dana.md"
        seeded = person.read_text(encoding="utf-8")
        lines = seeded.splitlines()
        out: list[str] = []
        inserted = False
        for line in lines:
            out.append(line)
            if (
                not inserted
                and "[source: c1]" in line
                and line.lstrip().startswith("- [")
                and "Mentioned in" not in line
            ):
                out.append("")
                out.append("- Operator note: approved budget is 42.")
                inserted = True
        assert inserted, seeded
        person.write_text("\n".join(out) + "\n", encoding="utf-8")
        v2 = wiki_curator.SourceItem(
            source_id="c1",
            source_kind="memory",
            title="Title c1",
            text="Revised observation",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([v2])
        after = person.read_text(encoding="utf-8")
        assert "Operator note: approved budget is 42." in after
        assert "Revised observation" in after
        assert not any(
            "[source: c1]" in line and "Observation" in line and "Revised" not in line
            for line in after.splitlines()
        )

    def test_strip_preserves_trailing_unattributed_paragraph(self, tmp_path):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        v1 = wiki_curator.SourceItem(
            source_id="c1",
            source_kind="memory",
            title="Title c1",
            text="Observation",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([v1])
        person = wiki / "people" / "dana.md"
        seeded = person.read_text(encoding="utf-8")
        lines = seeded.splitlines()
        out: list[str] = []
        inserted = False
        for line in lines:
            out.append(line)
            if (
                not inserted
                and "[source: c1]" in line
                and line.lstrip().startswith("- [")
                and "Mentioned in" not in line
            ):
                out.append("")
                out.append("Operator paragraph note: keep this sentence.")
                inserted = True
        assert inserted, seeded
        person.write_text("\n".join(out) + "\n", encoding="utf-8")
        v2 = wiki_curator.SourceItem(
            source_id="c1",
            source_kind="memory",
            title="Title c1",
            text="Revised observation",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([v2])
        after = person.read_text(encoding="utf-8")
        assert "Operator paragraph note: keep this sentence." in after
        assert "Revised observation" in after

    @pytest.mark.parametrize(
        "body",
        [
            "Intro sentence\n- bullet one",
            "Intro sentence\n* bullet one",
            "Intro sentence\n+ bullet one",
            "Intro sentence\n1. bullet one",
            "Intro sentence\n# heading one",
        ],
    )
    def test_block_start_marker_line_discovers_generated_prefix(self, tmp_path, capsys, body):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 1, "memory_source": "none"},
        }
        items = [
            wiki_curator.SourceItem(
                source_id="c1",
                source_kind="memory",
                title="Title 1",
                text=body,
                timestamp=now,
                people=["Alex"],
            ),
            wiki_curator.SourceItem(
                source_id="c2",
                source_kind="memory",
                title="Title 2",
                text="Sibling body",
                timestamp=now,
                people=["Blair"],
            ),
        ]
        wiki_curator.WikiCurator(cfg).curate_items(items)
        alex = wiki / "people" / "alex.md"
        before = alex.read_text(encoding="utf-8")
        opening = body.splitlines()[0]
        assert opening in before
        assert before.count(opening) == 1
        capsys.readouterr()
        for _ in range(2):
            later = wiki_curator.WikiCurator(cfg)
            later.curate_items(items)
            after = alex.read_text(encoding="utf-8")
            assert after == before
            assert after.count(opening) == 1
            assert not any(
                change.action == "update" and "c1" in change.detail for change in later.changes
            )
        blair = wiki / "people" / "blair.md"
        assert blair.is_file()
        assert "Sibling body" in blair.read_text(encoding="utf-8")

    def test_generated_prefix_span_includes_block_start_marker_line(self):
        import wiki_curator

        cases = [
            ["- [2026-09-26] Intro sentence", "- bullet one [source: c1]"],
            ["- [2026-09-26] Intro sentence", "* bullet one [source: c1]"],
            ["- [2026-09-26] Intro sentence", "+ bullet one [source: c1]"],
            ["- [2026-09-26] Intro sentence", "1. bullet one [source: c1]"],
            ["- [2026-09-26] Intro sentence", "# heading one [source: c1]"],
        ]
        for lines in cases:
            assert wiki_curator._attributed_block_spans(lines, "c1") == [(0, 2)], lines

    def test_markerless_paragraph_is_not_absorbed_into_span(self):
        import wiki_curator

        forward = [
            "- obs one [source: s1]",
            "",
            "unrelated hand note without marker",
            "",
            "- other [source: s2]",
        ]
        assert wiki_curator._attributed_block_spans(forward, "s1") == [(0, 1)]
        backward = [
            "intro para no marker",
            "",
            "detail continuation [source: s9]",
        ]
        assert wiki_curator._attributed_block_spans(backward, "s9") == [(2, 3)]

    def test_backup_refuses_symlinked_dest(self, tmp_path, capsys):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        people = wiki / "people"
        people.mkdir()
        (people / "seed.txt").write_text("seed-secret\n", encoding="utf-8")
        outside = tmp_path / "outside"
        outside.mkdir()
        before_outside = _snapshot_tree(outside)
        items = [
            wiki_curator.SourceItem(
                source_id=f"s{i}",
                source_kind="memory",
                title=f"Title {i}",
                text=f"Body {i}",
                timestamp=now,
                people=[f"Person{i}"],
            )
            for i in range(6)
        ]
        curator = wiki_curator.WikiCurator(
            {
                "paths": {"wiki_path": str(wiki)},
                "curator": {"max_write_pages": 0, "memory_source": "none"},
            }
        )
        stamp = curator.now.strftime("%Y%m%dT%H%M%S")
        link = wiki / ".lumen" / "backup" / stamp / "people"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside)
        curator.curate_items(items)
        err = capsys.readouterr().err
        assert "warning: skipping backup: destination is not a trusted directory" in err
        assert _snapshot_tree(outside) == before_outside
        assert not (outside / "seed.txt").exists()
        assert not any(path.is_file() for path in outside.rglob("*"))

    def test_empty_markdown_destination_does_not_crash(self, tmp_path, capsys, monkeypatch):
        import wiki_curator

        now = datetime.now(timezone.utc)
        project = tmp_path / "project"
        project.mkdir()
        wiki = project / "wiki"
        wiki.mkdir()
        config, config_path = _write_config(project, wiki, memory_source="none")
        item = wiki_curator.SourceItem(
            source_id="s1",
            source_kind="memory",
            title="Title v1",
            text="Body v1",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(config).curate_items([item])
        daily = next((wiki / "daily").glob("*.md"))
        daily.write_text(daily.read_text(encoding="utf-8") + "\n[empty destination]( )\n", encoding="utf-8")
        monkeypatch.chdir(project)
        monkeypatch.delenv("LUMEN_CONFIG", raising=False)
        rc = wiki_curator.main(["run", "--since", "24h", "--config", str(config_path), "--wiki", str(wiki)])
        assert rc == 0
        err = capsys.readouterr().err
        assert "IndexError" not in err

    def test_sibling_daily_share_does_not_warn_on_clean_entity_update(self, tmp_path, capsys):
        import wiki_curator

        now = datetime.now(timezone.utc)
        wiki = tmp_path / "wiki"
        wiki.mkdir()
        cfg = {
            "paths": {"wiki_path": str(wiki)},
            "curator": {"max_write_pages": 20, "memory_source": "none"},
        }
        s1 = wiki_curator.SourceItem(
            source_id="s1",
            source_kind="memory",
            title="Title 1",
            text="Dana body v1",
            timestamp=now,
            people=["Dana"],
        )
        s2 = wiki_curator.SourceItem(
            source_id="s2",
            source_kind="memory",
            title="Title 2",
            text="Eve body",
            timestamp=now,
            people=["Eve"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([s1, s2])
        capsys.readouterr()
        s1b = wiki_curator.SourceItem(
            source_id="s1",
            source_kind="memory",
            title="Title 1",
            text="Dana body v2",
            timestamp=now,
            people=["Dana"],
        )
        wiki_curator.WikiCurator(cfg).curate_items([s1b])
        err = capsys.readouterr().err
        assert "warning: source s1 changed but shares a merged page; manual review needed" not in err
        dana = (wiki / "people" / "dana.md").read_text(encoding="utf-8")
        assert "Dana body v2" in dana
        assert "Dana body v1" not in dana

    def test_config_precedence_wiki_path_and_max_write_pages(self, tmp_path, monkeypatch):
        import config_loader

        explicit_wiki = tmp_path / "explicit-wiki"
        env_wiki = tmp_path / "env-wiki"
        lumen_wiki = tmp_path / "lumen-config-wiki"
        explicit_wiki.mkdir()
        env_wiki.mkdir()
        lumen_wiki.mkdir()
        env_cfg = tmp_path / "from-env.yaml"
        env_cfg.write_text(
            yaml.safe_dump(
                {
                    "paths": {"wiki_path": str(lumen_wiki)},
                    "curator": {"max_write_pages": 7},
                }
            ),
            encoding="utf-8",
        )
        explicit_cfg = tmp_path / "explicit.yaml"
        explicit_cfg.write_text(
            yaml.safe_dump(
                {
                    "paths": {"wiki_path": str(explicit_wiki)},
                    "curator": {"max_write_pages": 3},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("LUMEN_CONFIG", str(env_cfg))
        monkeypatch.setenv("WIKI_PATH", str(env_wiki))
        loaded_explicit = config_loader.load_config(str(explicit_cfg))
        assert Path(loaded_explicit["paths"]["wiki_path"]).resolve() == explicit_wiki.resolve()
        assert config_loader.get_wiki_path(loaded_explicit) == explicit_wiki.resolve()
        assert int(loaded_explicit["curator"]["max_write_pages"]) == 3
        assert config_loader.get_max_write_pages(loaded_explicit) == 3

        loaded_env = config_loader.load_config(None)
        assert Path(loaded_env["paths"]["wiki_path"]).resolve() == lumen_wiki.resolve()
        assert config_loader.get_wiki_path(loaded_env) == lumen_wiki.resolve()
        assert int(loaded_env["curator"]["max_write_pages"]) == 7
        assert config_loader.get_max_write_pages(loaded_env) == 7

        monkeypatch.delenv("LUMEN_CONFIG", raising=False)
        loaded_wiki_env = config_loader.load_config(None)
        assert config_loader.get_wiki_path(loaded_wiki_env) == env_wiki.resolve()
        assert config_loader.get_max_write_pages(loaded_wiki_env) == 20

        monkeypatch.delenv("WIKI_PATH", raising=False)
        loaded_default = config_loader.load_config(None)
        assert config_loader.get_wiki_path(loaded_default) == (Path.home() / "wiki").resolve()
        assert int(loaded_default["curator"]["max_write_pages"]) == 20
        assert config_loader.get_max_write_pages(loaded_default) == 20

    def test_mapping_wiki_path_explicit_config_exits_2(self, tmp_path, capsys, monkeypatch):
        import wiki_curator

        monkeypatch.delenv("LUMEN_CONFIG", raising=False)
        monkeypatch.chdir(tmp_path)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        wiki = sandbox / "wiki"
        wiki.mkdir()
        bad = sandbox / "typed.yaml"
        bad.write_text("paths:\n  wiki_path: {}\n", encoding="utf-8")
        before = _snapshot_tree(tmp_path)
        rc = wiki_curator.main(
            ["run", "--since", "24h", "--config", str(bad), "--wiki", str(wiki)]
        )
        err = capsys.readouterr().err
        assert rc == 2
        assert "error:" in err
        assert "paths.wiki_path" in err
        assert len([line for line in err.splitlines() if line]) == 1
        assert _snapshot_tree(tmp_path) == before

    def test_mapping_wiki_path_default_config_is_error(self, tmp_path, monkeypatch):
        import config_loader

        monkeypatch.delenv("LUMEN_CONFIG", raising=False)
        bad = tmp_path / "lumen.yaml"
        bad.write_text("paths:\n  wiki_path: {}\n", encoding="utf-8")
        monkeypatch.setattr(config_loader, "DEFAULT_CONFIG_PATH", bad)
        with pytest.raises(config_loader.ConfigError) as caught:
            config_loader.load_config()
        assert "paths.wiki_path" in str(caught.value)


class TestWikiCli:
    def test_wiki_flag_before_and_after_subcommand(self):
        import wiki_curator

        parser = wiki_curator.build_parser()
        before = parser.parse_args(["--wiki", "/tmp/lumen-wiki", "lint"])
        after = parser.parse_args(["lint", "--wiki", "/tmp/lumen-wiki"])
        assert before.wiki == after.wiki == "/tmp/lumen-wiki"

    def test_config_parse_error_warns(self, tmp_path, capsys):
        import config_loader

        bad = tmp_path / "bad.yaml"
        bad.write_text("{not: yaml", encoding="utf-8")
        data = config_loader._read_yaml(bad)
        assert data == {}
        err = capsys.readouterr().err
        assert f"warning: {bad}:" in err
        assert "using defaults" in err

    def test_config_non_mapping_warns(self, tmp_path, capsys):
        import config_loader

        bad = tmp_path / "list.yaml"
        bad.write_text("- just a list\n", encoding="utf-8")
        data = config_loader._read_yaml(bad)
        assert data == {}
        err = capsys.readouterr().err
        assert f"warning: {bad}:" in err
        assert "using defaults" in err

    def test_missing_config_is_silent(self, tmp_path, capsys):
        import config_loader

        missing = tmp_path / "absent.yaml"
        data = config_loader._read_yaml(missing)
        assert data == {}
        assert capsys.readouterr().err == ""

    def test_config_yaml_error_is_single_line_without_values(self, tmp_path, capsys):
        import config_loader

        secret = "super-secret-token-value"
        bad = tmp_path / "bad.yaml"
        bad.write_text(f"paths:\n  wiki_path: [{secret}\n", encoding="utf-8")
        data = config_loader._read_yaml(bad)
        assert data == {}
        err = capsys.readouterr().err
        lines = [line for line in err.splitlines() if line]
        assert len(lines) == 1
        assert lines[0].startswith(f"warning: {bad}: yaml parse error at line")
        assert lines[0].endswith("; using defaults")
        assert secret not in err

    def test_malformed_explicit_config_exits_2_without_writes(self, tmp_path, capsys, monkeypatch):
        import wiki_curator

        monkeypatch.delenv("LUMEN_CONFIG", raising=False)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        wiki = sandbox / "wiki"
        wiki.mkdir()
        bad = sandbox / "bad.yaml"
        bad.write_text("{not: yaml", encoding="utf-8")
        before = _snapshot_tree(tmp_path)
        rc = wiki_curator.main(
            ["run", "--since", "24h", "--config", str(bad), "--wiki", str(wiki)]
        )
        err = capsys.readouterr().err
        assert rc == 2
        assert err.startswith("error:")
        assert "yaml parse error" in err
        assert _snapshot_tree(tmp_path) == before

    def test_wrong_typed_explicit_config_exits_2(self, tmp_path, capsys, monkeypatch):
        import wiki_curator

        monkeypatch.delenv("LUMEN_CONFIG", raising=False)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        wiki = sandbox / "wiki"
        wiki.mkdir()
        bad = sandbox / "typed.yaml"
        bad.write_text("paths: not-a-mapping\n", encoding="utf-8")
        before = _snapshot_tree(tmp_path)
        rc = wiki_curator.main(
            ["run", "--since", "24h", "--config", str(bad), "--wiki", str(wiki)]
        )
        err = capsys.readouterr().err
        assert rc == 2
        assert "error:" in err
        assert "paths is not a mapping" in err
        assert _snapshot_tree(tmp_path) == before

    def test_default_config_type_error_warns_and_defaults(self, tmp_path, capsys, monkeypatch):
        import config_loader

        monkeypatch.delenv("LUMEN_CONFIG", raising=False)
        bad = tmp_path / "lumen.yaml"
        bad.write_text("paths: not-a-mapping\n", encoding="utf-8")
        monkeypatch.setattr(config_loader, "DEFAULT_CONFIG_PATH", bad)
        data = config_loader.load_config()
        err = capsys.readouterr().err
        assert "warning:" in err
        assert "paths is not a mapping" in err
        assert "using defaults" in err
        assert isinstance(data.get("paths"), dict)
        assert data["curator"]["memory_source"] == "auto"

    def test_default_config_yaml_error_warns_and_defaults(self, tmp_path, capsys, monkeypatch):
        import config_loader

        monkeypatch.delenv("LUMEN_CONFIG", raising=False)
        bad = tmp_path / "lumen.yaml"
        bad.write_text("{not: yaml", encoding="utf-8")
        monkeypatch.setattr(config_loader, "DEFAULT_CONFIG_PATH", bad)
        data = config_loader.load_config()
        err = capsys.readouterr().err
        assert "warning:" in err
        assert "yaml parse error" in err
        assert "using defaults" in err
        assert isinstance(data.get("paths"), dict)

    def test_explicit_invalid_utf8_exits_2(self, tmp_path, capsys, monkeypatch):
        import wiki_curator

        monkeypatch.delenv("LUMEN_CONFIG", raising=False)
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        wiki = sandbox / "wiki"
        wiki.mkdir()
        bad = sandbox / "bad.yaml"
        bad.write_bytes(b"\xff\xfe\x00not-utf8")
        before = _snapshot_tree(tmp_path)
        rc = wiki_curator.main(
            ["run", "--since", "24h", "--config", str(bad), "--wiki", str(wiki)]
        )
        err = capsys.readouterr().err
        assert rc == 2
        assert err.startswith("error:")
        assert "invalid UTF-8" in err
        assert _snapshot_tree(tmp_path) == before


class TestWikiLint:
    def test_lint_detects_broken_links(self, temp_project):
        config, project, config_path = temp_project
        wiki = project / "wiki"
        wiki.mkdir()
        _make_wiki_page(wiki / "index.md", "Index", page_type="index", body="[[NonExistent]]")
        _make_wiki_page(wiki / "entities" / "alpha.md", "Alpha", body="[[$NonExistent]]")
        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki_curator.main(["--config", str(config_path), "lint"])
        assert rc == 0
        output = buf.getvalue()
        assert "broken" in output.lower() or "Broken" in output or "WARN" in output

    def test_lint_detects_missing_frontmatter(self, temp_project):
        config, project, config_path = temp_project
        wiki = project / "wiki"
        wiki.mkdir()
        _make_wiki_page(wiki / "index.md", "Index", page_type="index")
        (wiki / "entities" / "bad.md").parent.mkdir(parents=True, exist_ok=True)
        (wiki / "entities" / "bad.md").write_text("# No frontmatter\n\nJust body.\n", encoding="utf-8")
        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki_curator.main(["--config", str(config_path), "lint"])
        assert rc == 1
        output = buf.getvalue()
        assert "frontmatter" in output.lower() or "ERROR" in output

    def test_lint_summary_prints_counts(self, temp_project):
        config, project, config_path = temp_project
        wiki = project / "wiki"
        wiki.mkdir()
        _make_wiki_page(wiki / "index.md", "Index", page_type="index")
        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki_curator.main(["--config", str(config_path), "lint", "--summary"])
        assert rc == 0
        output = buf.getvalue()
        assert "ERROR" in output or "WARN" in output or "0" in output

    def test_lint_empty_wiki(self, temp_project):
        """Empty wiki should degrade gracefully."""
        config, project, config_path = temp_project
        import wiki_curator

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wiki_curator.main(["--config", str(config_path), "lint"])
        assert rc == 1
        assert "ERROR" in buf.getvalue()
