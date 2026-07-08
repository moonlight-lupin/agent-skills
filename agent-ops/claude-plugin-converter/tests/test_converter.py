"""Smoke tests for claude-plugin-converter scripts.

Creates a tiny fake Claude plugin in a temp dir, runs analyze.py and convert.py
on it, and asserts the output is valid.
"""

import json
import os
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
ANALYZE = SCRIPTS_DIR / "analyze.py"
CONVERT = SCRIPTS_DIR / "convert.py"


# ── Fixtures ───────────────────────────────────────────────────────────

def _make_fake_plugin(tmp: Path) -> Path:
    """Create a minimal Claude plugin directory and return its path."""
    plugin = tmp / "fake-plugin"
    plugin.mkdir()

    # Manifest
    manifest_dir = plugin / ".claude-plugin"
    manifest_dir.mkdir()
    (manifest_dir / "plugin.json").write_text(json.dumps({
        "name": "fake-plugin",
        "version": "1.0.0",
        "description": "A tiny test plugin",
        "author": {"name": "Tester"},
    }))

    # One skill with $ARGUMENTS
    skill_dir = plugin / "skills" / "greet"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: greet\n"
        'description: "Greet the user"\n'
        "---\n\n"
        "# Greet\n\n"
        "Greet $ARGUMENTS warmly and ask how you can help.\n"
    )

    # One skill without $ARGUMENTS
    skill2_dir = plugin / "skills" / "ping"
    skill2_dir.mkdir(parents=True)
    (skill2_dir / "SKILL.md").write_text(
        "---\n"
        "name: ping\n"
        'description: "Respond with pong"\n'
        "---\n\n"
        "# Ping\n\nRespond with pong.\n"
    )

    return plugin


# ── Tests ──────────────────────────────────────────────────────────────

class TestSafeName:
    """Test the safe_name() helper imported from the scripts."""

    def _get_safe_name(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "analyze_cpc", SCRIPTS_DIR / "analyze.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.safe_name

    def test_normal_name(self):
        safe_name = self._get_safe_name()
        assert safe_name("my-plugin") == "my-plugin"

    def test_path_traversal(self):
        safe_name = self._get_safe_name()
        assert safe_name("../../etc/passwd") == "etc-passwd"
        assert ".." not in safe_name("../../etc")

    def test_empty(self):
        safe_name = self._get_safe_name()
        assert safe_name("") == "unnamed"
        assert safe_name(None) == "unnamed"

    def test_strips_leading_dots(self):
        safe_name = self._get_safe_name()
        assert safe_name(".hidden") == "hidden"
        assert safe_name("./../foo") == "foo"

    def test_special_chars(self):
        safe_name = self._get_safe_name()
        assert safe_name("hello world!") == "hello-world"
        assert safe_name("foo/bar baz") == "foo-bar-baz"

    def test_length_cap(self):
        safe_name = self._get_safe_name()
        long_name = "a" * 100
        assert len(safe_name(long_name)) == 64


class TestAnalyze:
    """Test analyze.py on a fake plugin."""

    def test_analyze_fake_plugin(self, tmp_path):
        plugin = _make_fake_plugin(tmp_path)
        out = tmp_path / "analysis.json"
        report = tmp_path / "report.md"

        result = subprocess.run(
            [sys.executable, str(ANALYZE), str(plugin),
             "--output", str(out), "--report", str(report)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

        data = json.loads(out.read_text())
        assert data["manifest"]["name"] == "fake-plugin"
        assert data["manifest"]["version"] == "1.0.0"
        assert data["summary"]["total"] == 2  # 2 skills
        # greet uses $ARGUMENTS → partial; ping is clean → convertible
        assert data["summary"]["convertible"] == 1
        assert data["summary"]["partial"] == 1
        assert data["summary"]["skipped"] == 0

        # Check skill detection
        skill_names = [s["name"] for s in data["components"]["skills"]]
        assert "greet" in skill_names
        assert "ping" in skill_names

        # Check $ARGUMENTS detection
        greet = next(s for s in data["components"]["skills"] if s["name"] == "greet")
        assert greet["uses_arguments"] is True

        ping = next(s for s in data["components"]["skills"] if s["name"] == "ping")
        assert ping["uses_arguments"] is False

        # Report file exists
        assert report.exists()
        assert "fake-plugin" in report.read_text()


class TestConvert:
    """Test convert.py on a fake plugin."""

    def test_convert_fake_plugin(self, tmp_path):
        plugin = _make_fake_plugin(tmp_path)
        analysis = tmp_path / "analysis.json"
        output = tmp_path / "converted"

        # Phase 1
        subprocess.run(
            [sys.executable, str(ANALYZE), str(plugin), "--output", str(analysis)],
            check=True, capture_output=True,
        )

        # Phase 2
        result = subprocess.run(
            [sys.executable, str(CONVERT), str(plugin),
             "--analysis", str(analysis), "--output", str(output)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr

        dest = output / "fake-plugin"
        assert (dest / "plugin.yaml").exists()
        assert (dest / "__init__.py").exists()
        assert (dest / "skills").is_dir()

        # Check skills were converted
        skill_dirs = list((dest / "skills").iterdir())
        assert len(skill_dirs) == 2

        # Check $ARGUMENTS was replaced
        greet_md = dest / "skills" / "greet" / "SKILL.md"
        assert greet_md.exists()
        content = greet_md.read_text()
        assert "$ARGUMENTS" not in content
        assert "the user's request" in content

        # Check ping skill (no $ARGUMENTS)
        ping_md = dest / "skills" / "ping" / "SKILL.md"
        assert ping_md.exists()

    def test_generated_init_compiles(self, tmp_path):
        """The generated __init__.py must be valid Python."""
        plugin = _make_fake_plugin(tmp_path)
        analysis = tmp_path / "analysis.json"
        output = tmp_path / "converted"

        subprocess.run(
            [sys.executable, str(ANALYZE), str(plugin), "--output", str(analysis)],
            check=True, capture_output=True,
        )
        subprocess.run(
            [sys.executable, str(CONVERT), str(plugin),
             "--analysis", str(analysis), "--output", str(output)],
            check=True, capture_output=True,
        )

        init_path = output / "fake-plugin" / "__init__.py"
        py_compile.compile(str(init_path), doraise=True)

    def test_generated_plugin_yaml_has_name(self, tmp_path):
        """plugin.yaml must contain the plugin name."""
        plugin = _make_fake_plugin(tmp_path)
        analysis = tmp_path / "analysis.json"
        output = tmp_path / "converted"

        subprocess.run(
            [sys.executable, str(ANALYZE), str(plugin), "--output", str(analysis)],
            check=True, capture_output=True,
        )
        subprocess.run(
            [sys.executable, str(CONVERT), str(plugin),
             "--analysis", str(analysis), "--output", str(output)],
            check=True, capture_output=True,
        )

        yaml_content = (output / "fake-plugin" / "plugin.yaml").read_text()
        assert "name: fake-plugin" in yaml_content

    def test_conversion_report_exists(self, tmp_path):
        """CONVERSION_REPORT.md should be generated."""
        plugin = _make_fake_plugin(tmp_path)
        analysis = tmp_path / "analysis.json"
        output = tmp_path / "converted"

        subprocess.run(
            [sys.executable, str(ANALYZE), str(plugin), "--output", str(analysis)],
            check=True, capture_output=True,
        )
        subprocess.run(
            [sys.executable, str(CONVERT), str(plugin),
             "--analysis", str(analysis), "--output", str(output)],
            check=True, capture_output=True,
        )

        report = output / "fake-plugin" / "CONVERSION_REPORT.md"
        assert report.exists()
        assert "fake-plugin" in report.read_text()

    def test_malicious_name_sanitized(self, tmp_path):
        """A plugin name with path traversal should be sanitized in output dir."""
        plugin = tmp_path / "bad-plugin"
        plugin.mkdir()
        manifest_dir = plugin / ".claude-plugin"
        manifest_dir.mkdir()
        (manifest_dir / "plugin.json").write_text(json.dumps({
            "name": "../../etc/evil",
            "version": "1.0.0",
            "description": "Malicious",
        }))

        # Add a dummy skill so analysis has content
        skill_dir = plugin / "skills" / "test"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: test\ndescription: \"test\"\n---\n\nTest.\n"
        )

        analysis = tmp_path / "analysis.json"
        output = tmp_path / "converted"

        subprocess.run(
            [sys.executable, str(ANALYZE), str(plugin), "--output", str(analysis)],
            check=True, capture_output=True,
        )
        subprocess.run(
            [sys.executable, str(CONVERT), str(plugin),
             "--analysis", str(analysis), "--output", str(output)],
            check=True, capture_output=True,
        )

        # The output dir should be sanitized, not "../../etc/evil"
        # Verify no traversal happened — the converted dir name should not contain ".."
        converted_dirs = [d for d in output.iterdir() if d.is_dir()]
        assert len(converted_dirs) == 1
        dirname = converted_dirs[0].name
        assert ".." not in dirname
        assert "evil" in dirname  # "etc-evil" or similar

        # Verify the output is inside the output directory, not escaping it
        assert converted_dirs[0].resolve().parent == output.resolve()