#!/usr/bin/env python3
"""Self-contained tests for organize.py."""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

# Ensure the scripts directory is on sys.path so `import organize` works
# regardless of the pytest invocation directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

import organize  # noqa: E402


class TempDirTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="organize-test-"))

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def write_text(self, relative: str, text: str) -> Path:
        path = self.temp_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def write_plan(self, plan: dict) -> Path:
        path = self.temp_dir / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return path


class ScanTests(TempDirTestCase):
    def test_scan_reads_text_archive_metadata_hidden_and_budget(self) -> None:
        text_file = self.write_text("notes.txt", "alpha" * 200)
        self.write_text(".hidden.txt", "hidden")
        nested_file = self.write_text("nested/deep.md", "nested")
        archive_path = self.temp_dir / "bundle.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("one.txt", "1")
            archive.writestr("two.txt", "2")

        entries = organize.scan_directory(self.temp_dir, depth=1, max_snippet_chars=50, total_snippet_budget=70)
        by_name = {entry["name"]: entry for entry in entries}

        self.assertIn(text_file.name, by_name)
        self.assertIn(archive_path.name, by_name)
        self.assertNotIn(".hidden.txt", by_name)
        self.assertIn(nested_file.name, by_name)
        self.assertEqual(by_name["notes.txt"]["type"], "text")
        self.assertEqual(len(by_name["notes.txt"]["snippet"]), 50)
        self.assertEqual(by_name["bundle.zip"]["type"], "archive")
        self.assertIn("Archive, 2 files", by_name["bundle.zip"]["snippet"])

    def test_scan_total_budget_omits_later_snippets(self) -> None:
        self.write_text("a.txt", "a" * 30)
        self.write_text("b.txt", "b" * 30)
        self.write_text("c.txt", "c" * 30)

        entries = organize.scan_directory(self.temp_dir, max_snippet_chars=30, total_snippet_budget=50)
        total = sum(len(entry["snippet"] or "") for entry in entries)

        self.assertLessEqual(total, 50)
        self.assertTrue(any(entry.get("snippet_omitted") == "total snippet budget exhausted" for entry in entries))

    def test_scan_cli_outputs_json(self) -> None:
        self.write_text("notes.txt", "hello")
        result = subprocess.run(
            [sys.executable, str(Path(organize.__file__)), "scan", "--path", str(self.temp_dir)],
            check=True,
            text=True,
            capture_output=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["name"], "notes.txt")


class ExecuteTests(TempDirTestCase):
    def test_execute_dry_run_makes_no_changes_and_reports_chunks(self) -> None:
        source = self.write_text("inbox/a.txt", "a")
        destination = self.temp_dir / "out" / "a.txt"
        plan_path = self.write_plan(
            {
                "moves": [{"source": str(source), "destination": str(destination)}],
                "folders_to_create": [str(destination.parent)],
            }
        )

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            summary = organize.execute_plan(plan_path, chunk_size=1, dry_run=True)

        self.assertTrue(source.exists())
        self.assertFalse(destination.exists())
        self.assertFalse(destination.parent.exists())
        self.assertEqual(summary["moved"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertIn("[chunk 1/1]", stderr.getvalue())
        self.assertIn("[dry-run] move", stderr.getvalue())

    def test_execute_moves_files_in_chunks(self) -> None:
        sources = [self.write_text(f"inbox/{index}.txt", str(index)) for index in range(3)]
        moves = [
            {"source": str(source), "destination": str(self.temp_dir / "out" / source.name)}
            for source in sources
        ]
        plan_path = self.write_plan({"moves": moves, "folders_to_create": [str(self.temp_dir / "out")]})

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            summary = organize.execute_plan(plan_path, chunk_size=2)

        self.assertEqual(summary["moved"], 3)
        self.assertEqual(summary["failed"], 0)
        self.assertEqual(summary["skipped"], 0)
        self.assertTrue((self.temp_dir / "out" / "0.txt").exists())
        self.assertTrue((self.temp_dir / "out" / "2.txt").exists())
        self.assertIn("[chunk 1/2] moved 2", stderr.getvalue())
        self.assertIn("[chunk 2/2] moved 1", stderr.getvalue())

    def test_execute_conflict_skips_without_overwrite(self) -> None:
        source = self.write_text("inbox/a.txt", "new")
        destination = self.write_text("out/a.txt", "existing")
        plan_path = self.write_plan(
            {"moves": [{"source": str(source), "destination": str(destination)}], "folders_to_create": []}
        )

        summary = organize.execute_plan(plan_path)

        self.assertEqual(summary["moved"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertTrue(source.exists())
        self.assertEqual(destination.read_text(encoding="utf-8"), "existing")
        self.assertEqual(summary["errors"][0]["error"], "destination already exists")

    def test_execute_handles_missing_source_error(self) -> None:
        missing = self.temp_dir / "missing.txt"
        destination = self.temp_dir / "out" / "missing.txt"
        plan_path = self.write_plan(
            {"moves": [{"source": str(missing), "destination": str(destination)}], "folders_to_create": []}
        )

        summary = organize.execute_plan(plan_path)

        self.assertEqual(summary["moved"], 0)
        self.assertEqual(summary["failed"], 1)
        self.assertFalse(destination.exists())
        self.assertEqual(summary["errors"][0]["error"], "source does not exist")

    def test_execute_cli_outputs_summary_json(self) -> None:
        source = self.write_text("inbox/a.txt", "a")
        destination = self.temp_dir / "out" / "a.txt"
        plan_path = self.write_plan(
            {
                "moves": [{"source": str(source), "destination": str(destination)}],
                "folders_to_create": [str(destination.parent)],
            }
        )

        result = subprocess.run(
            [sys.executable, str(Path(organize.__file__)), "execute", "--plan", str(plan_path), "--chunk-size", "1"],
            check=True,
            text=True,
            capture_output=True,
        )

        summary = json.loads(result.stdout)
        self.assertEqual(summary["moved"], 1)
        self.assertTrue(destination.exists())
        self.assertIn("[chunk 1/1]", result.stderr)


class ParserTests(unittest.TestCase):
    def test_invalid_chunk_size_raises(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="organize-test-"))
        try:
            plan_path = temp_dir / "plan.json"
            plan_path.write_text(json.dumps({"moves": [], "folders_to_create": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                organize.execute_plan(plan_path, chunk_size=0)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class ProposeTests(TempDirTestCase):
    def test_build_propose_prompts_contains_expected_elements(self) -> None:
        scan = [
            {
                "path": str(self.temp_dir / "notes.txt"),
                "relative_path": "notes.txt",
                "name": "notes.txt",
                "type": "text",
                "snippet": "meeting notes",
                "size": 13,
                "mtime": "2026-01-01T00:00:00",
                "mime": "text/plain",
            },
            {
                "path": str(self.temp_dir / "large.bin"),
                "name": "large.bin",
                "type": "other",
                "snippet": None,
                "size": 100,
                "mtime": "2026-01-01T00:00:00",
            },
        ]

        system_prompt, user_prompt = organize.build_propose_prompts(self.temp_dir, scan)

        self.assertIn("file organization assistant", system_prompt)
        self.assertIn('"moves" and "folders_to_create"', system_prompt)
        self.assertIn(f"Source directory: {self.temp_dir}", user_prompt)
        self.assertIn("Organize these files. Return JSON only.", user_prompt)
        self.assertIn("meeting notes", user_prompt)
        self.assertIn("large.bin", user_prompt)
        self.assertNotIn("relative_path", user_prompt)
        self.assertNotIn('"snippet": null', user_prompt)

    def test_extract_json_response_plain_and_markdown_wrapped(self) -> None:
        plain = '{"moves": [], "folders_to_create": []}'
        wrapped = '```json\n{"moves": [], "folders_to_create": []}\n```'

        self.assertEqual(organize.extract_json_response(plain)["moves"], [])
        self.assertEqual(organize.extract_json_response(wrapped)["folders_to_create"], [])

    def test_validate_plan_accepts_valid_plan(self) -> None:
        plan = {
            "moves": [{"source": str(self.temp_dir / "a.txt"), "destination": str(self.temp_dir / "Docs/a.txt")}],
            "folders_to_create": [str(self.temp_dir / "Docs")],
        }

        self.assertIs(organize.validate_plan(plan), plan)

    def test_validate_plan_rejects_missing_moves(self) -> None:
        with self.assertRaisesRegex(ValueError, "moves array"):
            organize.validate_plan({"folders_to_create": []})

    def test_validate_plan_rejects_missing_folders_to_create(self) -> None:
        with self.assertRaisesRegex(ValueError, "folders_to_create array"):
            organize.validate_plan({"moves": []})

    def test_provider_priority_resolution(self) -> None:
        with mock.patch.object(organize, "hermes_env_values", return_value={}):
            self.assertEqual(organize.resolve_provider("ollama", {"DEEPSEEK_API_KEY": "x"}), "ollama")
            self.assertEqual(organize.resolve_provider(None, {"DEEPSEEK_API_KEY": "x"}), "deepseek")
            self.assertEqual(organize.resolve_provider(None, {"OPENAI_API_KEY": "x"}), "openai")
            self.assertEqual(organize.resolve_provider(None, {"OPENROUTER_API_KEY": "x"}), "openrouter")
            self.assertEqual(organize.resolve_provider(None, {"OLLAMA_HOST": "http://localhost:11434"}), "ollama")

    def test_api_key_resolution_from_flag_and_env(self) -> None:
        with mock.patch.object(organize, "hermes_env_values", return_value={}):
            self.assertEqual(organize.resolve_api_key("deepseek", "flag-key", {}), "flag-key")
            self.assertEqual(
                organize.resolve_api_key("openai", None, {"OPENAI_API_KEY": "env-key"}),
                "env-key",
            )

    def test_call_llm_api_uses_urlopen_and_parses_response(self) -> None:
        response_body = json.dumps(
            {
                "choices": [
                    {"message": {"content": '{"moves": [], "folders_to_create": []}'}}
                ]
            }
        ).encode("utf-8")
        response = mock.MagicMock()
        response.read.return_value = response_body
        response.__enter__.return_value = response

        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            content = organize.call_llm_api(
                "deepseek",
                "deepseek-chat",
                "https://example.test/chat",
                "system",
                "user",
                "api-key",
                0.3,
                4096,
            )

        self.assertEqual(content, '{"moves": [], "folders_to_create": []}')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/chat")
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["model"], "deepseek-chat")
        self.assertEqual(body["messages"][0]["content"], "system")
        self.assertEqual(body["temperature"], 0.3)

    def test_propose_plan_mocks_http_call(self) -> None:
        scan_path = self.temp_dir / "scan.json"
        scan_path.write_text(
            json.dumps(
                [
                    {
                        "path": str(self.temp_dir / "notes.txt"),
                        "name": "notes.txt",
                        "type": "text",
                        "snippet": "notes",
                        "size": 5,
                        "mtime": "2026-01-01T00:00:00",
                    }
                ]
            ),
            encoding="utf-8",
        )
        response_body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": '```json\n{"moves": [], "folders_to_create": []}\n```'
                        }
                    }
                ]
            }
        ).encode("utf-8")
        response = mock.MagicMock()
        response.read.return_value = response_body
        response.__enter__.return_value = response

        with mock.patch("urllib.request.urlopen", return_value=response):
            plan = organize.propose_plan(
                scan_path,
                self.temp_dir,
                provider="deepseek",
                api_key="api-key",
                base_url="https://example.test/chat",
            )

        self.assertEqual(plan, {"moves": [], "folders_to_create": []})

    def test_fallback_error_when_no_provider_available(self) -> None:
        with mock.patch.object(organize, "hermes_env_values", return_value={}):
            with self.assertRaisesRegex(ValueError, "no LLM provider"):
                organize.resolve_provider(None, {})


if __name__ == "__main__":
    unittest.main()
