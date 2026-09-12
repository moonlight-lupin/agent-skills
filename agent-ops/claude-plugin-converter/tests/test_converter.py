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


class TestHookCommandPreserved:
    """Long hook commands must not be truncated during analyze → convert."""

    def test_analyze_keeps_long_hook_command(self, tmp_path):
        import importlib.util

        plugin = tmp_path / "hook-plugin"
        hooks_dir = plugin / "hooks"
        hooks_dir.mkdir(parents=True)
        long_cmd = "python3 -c " + repr("x" * 600)
        assert len(long_cmd) > 500
        (hooks_dir / "hooks.json").write_text(json.dumps({
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": long_cmd}],
                    }
                ]
            }
        }))

        spec = importlib.util.spec_from_file_location("analyze_cpc", ANALYZE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        hooks = mod.analyze_hook(json.loads((hooks_dir / "hooks.json").read_text()))
        assert len(hooks) == 1
        assert hooks[0]["command"] == long_cmd
        assert len(hooks[0]["command"]) > 500

    def test_convert_mcp_rewrites_plugin_root_in_args(self, tmp_path):
        import importlib.util

        spec = importlib.util.spec_from_file_location("convert_cpc", CONVERT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        plugin_dir = tmp_path / "out-plugin"
        plugin_dir.mkdir()
        yaml_snip, infos = mod.convert_mcp(
            [{
                "name": "demo",
                "command": "${CLAUDE_PLUGIN_ROOT}/bin/server",
                "args": ["--config", "${CLAUDE_PLUGIN_ROOT}/cfg.json"],
                "env_vars": [],
            }],
            plugin_dir,
        )
        assert str(plugin_dir) in infos[0]["command"]
        assert "${CLAUDE_PLUGIN_ROOT}" not in yaml_snip
        assert f"{plugin_dir}/cfg.json" in yaml_snip


def _load_convert():
    import importlib.util
    spec = importlib.util.spec_from_file_location("convert_cpc", CONVERT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestApMcpValidation:
    """F1/F2/F4: MCP conversion rejects credentials, escapes, and malformed configs."""

    def test_rejects_authorization_header_without_echoing_secret(self):
        mod = _load_convert()
        secret = "super-secret-token-xyz"
        with pytest.raises(ValueError) as ei:
            mod.convert_ap_mcp_server({
                "type": "streamable-http",
                "url": "https://example.com/mcp",
                "headers": {"Authorization": f"Bearer {secret}"},
            })
        msg = str(ei.value)
        assert "Authorization" in msg
        assert secret not in msg
        assert "Bearer" not in msg

    def test_rejects_cookie_and_token_prefix_headers(self):
        mod = _load_convert()
        with pytest.raises(ValueError) as ei:
            mod.convert_ap_mcp_server({
                "type": "streamable-http",
                "url": "https://example.com/mcp",
                "headers": {"Cookie": "session=abc"},
            })
        assert "Cookie" in str(ei.value)
        assert "session=abc" not in str(ei.value)
        with pytest.raises(ValueError) as ei:
            mod.convert_ap_mcp_server({
                "type": "streamable-http",
                "url": "https://example.com/mcp",
                "headers": {"X-Token": "Bearer abc"},
            })
        assert "X-Token" in str(ei.value)
        assert "Bearer abc" not in str(ei.value)

    def test_keeps_non_credential_headers(self):
        mod = _load_convert()
        out = mod.convert_ap_mcp_server({
            "type": "streamable-http",
            "url": "https://example.com/mcp",
            "headers": {"Accept": "application/json"},
        })
        assert out["headers"] == {"Accept": "application/json"}

    def test_rejects_userinfo_query_fragment_and_non_http_scheme(self):
        mod = _load_convert()
        with pytest.raises(ValueError, match="userinfo"):
            mod.convert_ap_mcp_server({
                "type": "streamable-http",
                "url": "https://user:pass@example.com/mcp",
            })
        with pytest.raises(ValueError, match="query"):
            mod.convert_ap_mcp_server({
                "type": "streamable-http",
                "url": "https://example.com/mcp?api_key=secret",
            })
        with pytest.raises(ValueError, match="fragment"):
            mod.convert_ap_mcp_server({
                "type": "streamable-http",
                "url": "https://example.com/mcp#frag",
            })
        with pytest.raises(ValueError, match="scheme"):
            mod.convert_ap_mcp_server({
                "type": "streamable-http",
                "url": "ftp://example.com/mcp",
            })

    def test_plain_http_non_loopback_warns_but_allows(self):
        mod = _load_convert()
        warns: list[str] = []
        out = mod.convert_ap_mcp_server({
            "type": "streamable-http",
            "url": "http://example.com/mcp",
        }, warnings=warns)
        assert out["url"] == "http://example.com/mcp"
        assert warns and "example.com" in warns[0]
        assert "loopback" in warns[0]
        loop_warns: list[str] = []
        mod.convert_ap_mcp_server({
            "type": "streamable-http",
            "url": "http://127.0.0.1:8080/mcp",
        }, warnings=loop_warns)
        assert loop_warns == []

    def test_rejects_stdio_command_and_cwd_escapes(self):
        mod = _load_convert()
        with pytest.raises(ValueError, match="command"):
            mod.convert_ap_mcp_server({"command": "bin/server"})
        with pytest.raises(ValueError, match="command"):
            mod.convert_ap_mcp_server({"command": "./../outside"})
        out_tab = mod.convert_ap_mcp_server({"command": "node\t-S"})
        assert out_tab["command"] == "node"
        assert out_tab["args"] == ["-S"]
        with pytest.raises(ValueError, match="cwd"):
            mod.convert_ap_mcp_server({"command": "node", "cwd": "../outside"})
        out = mod.convert_ap_mcp_server({"command": "node", "cwd": "./outside"})
        assert out["cwd"] == "./outside"
        with pytest.raises(ValueError, match="args"):
            mod.convert_ap_mcp_server({"command": "node", "args": ["./../escape"]})

    def test_malformed_mcp_json_is_named_error_not_fallback(self, tmp_path):
        mod = _load_convert()
        mcp = tmp_path / ".mcp.json"
        mcp.write_text('{"mcpServers": []}')
        with pytest.raises(ValueError, match="mcpServers must be an object") as ei:
            mod.load_claude_mcp_servers(tmp_path, {})
        assert str(mcp) in str(ei.value)
        mcp.write_text("{not json")
        with pytest.raises(ValueError, match="invalid JSON") as ei:
            mod.load_claude_mcp_servers(tmp_path, {})
        assert str(mcp) in str(ei.value)
        assert "JSONDecodeError" not in type(ei.value).__name__

    def test_absent_mcp_json_is_fine(self, tmp_path):
        mod = _load_convert()
        assert mod.load_claude_mcp_servers(tmp_path, {}) == {}

    def test_validate_ap_mcp_json_rejects_escaped_cwd(self):
        mod = _load_convert()
        doc = {
            "$schema": mod.MCP_SCHEMA_URL,
            "mcpServers": {
                "bad": {
                    "type": "stdio",
                    "command": "node",
                    "cwd": "./../outside",
                }
            },
        }
        with pytest.raises(ValueError, match="cwd"):
            mod.validate_ap_mcp_json(doc)

    def test_http_warning_lands_in_conversion_report(self):
        mod = _load_convert()
        report = mod.generate_ap_report(
            {"summary": {"convertible": 0, "partial": 0, "skipped": 0, "total": 0},
             "components": {}},
            {"mcp_servers": [{
                "name": "remote",
                "status": "converted",
                "warnings": ["plain HTTP url host 'example.com' is not loopback; allowed with warning"],
            }]},
            "demo",
        )
        assert "### Warnings" in report
        assert "example.com" in report
        assert "remote" in report

    def test_splits_node_plugin_root_command(self):
        """O3: node ${CLAUDE_PLUGIN_ROOT}/bin/x.js becomes command + args."""
        mod = _load_convert()
        out = mod.convert_ap_mcp_server({"command": "node ${CLAUDE_PLUGIN_ROOT}/bin/x.js"})
        assert out["command"] == "node"
        assert out["args"] == ["${PLUGIN_ROOT}/bin/x.js"]

    def test_rejects_bare_plugin_root_command(self):
        """O19: ${CLAUDE_PLUGIN_ROOT} alone is a directory, not an executable."""
        mod = _load_convert()
        with pytest.raises(ValueError, match="directory"):
            mod.convert_ap_mcp_server({"command": "${CLAUDE_PLUGIN_ROOT}"})

    def test_rejects_non_string_args(self):
        """O20: numeric/None args are rejected rather than stringified."""
        mod = _load_convert()
        with pytest.raises(ValueError, match="strings"):
            mod.convert_ap_mcp_server({"command": "node", "args": [3]})
        with pytest.raises(ValueError, match="strings"):
            mod.convert_ap_mcp_server({"command": "node", "args": [None]})

    def test_env_credential_keys_are_redacted(self):
        """O15: API_TOKEN is replaced with ${API_TOKEN}; the secret is not echoed."""
        mod = _load_convert()
        secret = "sk-secret-value-xyz"
        warns: list[str] = []
        out = mod.convert_ap_mcp_server(
            {"command": "node", "env": {"API_TOKEN": secret, "ACME_MODE": "strict"}},
            warnings=warns,
        )
        assert out["env"]["API_TOKEN"] == "${API_TOKEN}"
        assert out["env"]["ACME_MODE"] == "strict"
        assert secret not in json.dumps(out)
        assert secret not in "".join(warns)
        assert warns and "API_TOKEN" in warns[0]

    def test_ap_skill_slug_and_plugin_root_rewrite(self, tmp_path):
        """O12/O13: AP mode slugifies My_Skill and rewrites to ${PLUGIN_ROOT}."""
        mod = _load_convert()
        skill_src = tmp_path / "src" / "My_Skill"
        skill_src.mkdir(parents=True)
        (skill_src / "SKILL.md").write_text(
            "---\nname: My_Skill\ndescription: \"\"\n---\n\n"
            "Body ${CLAUDE_PLUGIN_ROOT}/bin/validator.js\n"
        )
        dest = tmp_path / "skills"
        dest.mkdir()
        result = mod.convert_skill(
            {"name": "My_Skill", "path": str(skill_src)},
            tmp_path / "src",
            dest,
            flavour="agent-plugins",
        )
        assert result["name"] == "my-skill"
        assert (dest / "my-skill" / "SKILL.md").is_file()
        md = (dest / "my-skill" / "SKILL.md").read_text()
        assert "name: my-skill" in md
        assert "${PLUGIN_ROOT}/bin/validator.js" in md
        assert "../bin" not in md
        assert any("description" in i for i in result["issues"])

    def test_ap_copies_license_and_writes_reports_beside(self, tmp_path):
        """O21/O22/O23: LICENSE is copied; reports sit beside the package; one name."""
        mod = _load_convert()
        plugin = tmp_path / "srcplug"
        plugin.mkdir()
        (plugin / ".claude-plugin").mkdir()
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({
            "name": "Acme_Sample",
            "version": "1.0.0",
            "description": "d",
        }))
        (plugin / "LICENSE").write_text("MIT license text\n")
        (plugin / "skills" / "greet").mkdir(parents=True)
        (plugin / "skills" / "greet" / "SKILL.md").write_text(
            "---\nname: greet\ndescription: hi\n---\n\nHi.\n"
        )
        pkg = tmp_path / "pkg"
        analysis = {
            "manifest": {"name": "Acme_Sample", "version": "1.0.0", "description": "d"},
            "summary": {"convertible": 1, "partial": 0, "skipped": 0, "total": 1},
            "components": {
                "skills": [{"name": "greet", "path": str(plugin / "skills" / "greet")}],
            },
        }
        results = mod.convert_plugin_agent_plugins(plugin, analysis, pkg)
        assert (pkg / "LICENSE").is_file()
        assert not (pkg / "CONVERSION_REPORT.md").is_file()
        assert (pkg.parent / "CONVERSION_REPORT.md").is_file()
        assert results["plugin_name"] == "acme-sample"
        pjson = json.loads((pkg / "plugin.json").read_text())
        assert pjson["name"] == "acme-sample"
        assert results["results_dir"] == str(pkg.parent)

    def test_schemas_shipped_beside_script(self):
        """O17: schemas live in scripts/schemas/ next to convert.py."""
        schemas = SCRIPTS_DIR / "schemas"
        assert (schemas / "plugin.schema.json").is_file()
        assert (schemas / "mcp.schema.json").is_file()


class TestRound3Regressions:
    """R1/R5: source-root overwrite and slug-collision rejection."""

    def test_root_plugin_and_mcp_json_do_not_overwrite_generated(self, tmp_path):
        """R1: source-root plugin.json/mcp.json must not replace validated output."""
        mod = _load_convert()
        plugin = tmp_path / "srcplug"
        plugin.mkdir()
        (plugin / ".claude-plugin").mkdir()
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({
            "name": "r1-plugin",
            "version": "1.0.0",
            "description": "valid source",
        }))
        (plugin / "plugin.json").write_text(json.dumps({
            "name": "INVALID",
            "unknown": True,
        }))
        secret = "super-secret-live-token"
        (plugin / ".mcp.json").write_text(json.dumps({
            "mcpServers": {
                "demo": {
                    "command": "python3",
                    "args": ["-m", "demo"],
                    "env": {"API_TOKEN": secret},
                }
            }
        }))
        (plugin / "mcp.json").write_text(json.dumps({
            "mcpServers": {
                "leaked": {
                    "command": "python3",
                    "env": {"API_TOKEN": secret},
                }
            }
        }))
        (plugin / "LICENSE").write_text("MIT license text\n")
        (plugin / "skills" / "greet").mkdir(parents=True)
        (plugin / "skills" / "greet" / "SKILL.md").write_text(
            "---\nname: greet\ndescription: hi\n---\n\nHi.\n"
        )
        pkg = tmp_path / "pkg"
        analysis = {
            "manifest": {"name": "r1-plugin", "version": "1.0.0", "description": "valid source"},
            "summary": {"convertible": 1, "partial": 0, "skipped": 0, "total": 1},
            "components": {
                "skills": [{"name": "greet", "path": str(plugin / "skills" / "greet")}],
            },
        }
        results = mod.convert_plugin_agent_plugins(plugin, analysis, pkg)
        pjson = json.loads((pkg / "plugin.json").read_text())
        assert pjson["name"] == "r1-plugin"
        assert "unknown" not in pjson
        mcp_raw = (pkg / "mcp.json").read_text()
        mcp = json.loads(mcp_raw)
        assert secret not in mcp_raw
        assert mcp["mcpServers"]["demo"]["env"]["API_TOKEN"] == "${API_TOKEN}"
        assert "leaked" not in mcp["mcpServers"]
        assert (pkg / "LICENSE").is_file()
        assert "plugin.json" in results["ignored_source_files"]
        assert "mcp.json" in results["ignored_source_files"]
        report = (pkg.parent / "CONVERSION_REPORT.md").read_text()
        assert "plugin.json" in report
        assert "Ignored source files" in report

    def test_slug_collision_exits_nonzero_with_named_error(self, tmp_path):
        """R5: a_b and a-b must not silently overwrite; CLI exits non-zero."""
        plugin = tmp_path / "srcplug"
        plugin.mkdir()
        (plugin / ".claude-plugin").mkdir()
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({
            "name": "r5-plugin",
            "version": "1.0.0",
            "description": "collision",
        }))
        for name, body in (("a_b", "skill underscore"), ("a-b", "skill hyphen")):
            d = plugin / "skills" / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {body}\n---\n\n{body}\n"
            )
        analysis = tmp_path / "analysis.json"
        proc = subprocess.run(
            [sys.executable, str(ANALYZE), str(plugin), "-o", str(analysis)],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        out = tmp_path / "pkg"
        proc = subprocess.run(
            [sys.executable, str(CONVERT), str(plugin),
             "--analysis", str(analysis), "--output", str(out),
             "--format", "agent-plugins"],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode != 0
        err = proc.stderr
        assert "Error:" in err
        assert "duplicate skill name after slugification: a-b" in err
        assert "a_b" in err
        results_path = tmp_path / "conversion_results.json"
        assert not results_path.is_file()
        skills_dir = out / "skills"
        assert not skills_dir.exists()


class TestRound4Fixes:
    """N3 residual, N7, N9, N10, N13, N15, N16."""

    def test_placeholder_mid_arg_dotdot_is_rejected(self):
        """N7: ${PLUGIN_ROOT} in the middle of an arg still validates the tail."""
        mod = _load_convert()
        with pytest.raises(ValueError, match="args"):
            mod.convert_ap_mcp_server({
                "command": "node",
                "args": ["--config=${CLAUDE_PLUGIN_ROOT}/../../etc/passwd"],
            })
        with pytest.raises(ValueError, match="args"):
            mod.convert_ap_mcp_server({
                "command": "node",
                "args": ["--config=${PLUGIN_DATA}/../../secret"],
            })
        ok = mod.convert_ap_mcp_server({
            "command": "node",
            "args": ["--config=${CLAUDE_PLUGIN_ROOT}/config.json"],
        })
        assert ok["args"] == ["--config=${PLUGIN_ROOT}/config.json"]

    def test_env_placeholder_normalizes_non_alnum(self):
        """N10: X-Api-Key becomes ${X_API_KEY}."""
        mod = _load_convert()
        warns: list[str] = []
        out = mod.convert_ap_mcp_server(
            {"command": "node", "env": {"X-Api-Key": "sk-live-secret"}},
            warnings=warns,
        )
        assert out["env"]["X-Api-Key"] == "${X_API_KEY}"
        assert "sk-live-secret" not in json.dumps(out)
        assert "X-Api-Key" not in out["env"]["X-Api-Key"]

    def test_credential_heuristic_skips_monkey_mode_and_key_file(self):
        """N13: whole-segment match; path-looking values are left alone."""
        mod = _load_convert()
        warns: list[str] = []
        out = mod.convert_ap_mcp_server(
            {
                "command": "node",
                "env": {
                    "MONKEY_MODE": "on",
                    "API_KEY_FILE": "/etc/keys/api.pem",
                    "API_TOKEN": "sk-live-secret",
                    "DB_PASSWORD": "hunter2",
                },
            },
            warnings=warns,
        )
        assert out["env"]["MONKEY_MODE"] == "on"
        assert out["env"]["API_KEY_FILE"] == "/etc/keys/api.pem"
        assert out["env"]["API_TOKEN"] == "${API_TOKEN}"
        assert out["env"]["DB_PASSWORD"] == "${DB_PASSWORD}"
        dumped = json.dumps(out)
        assert "sk-live-secret" not in dumped
        assert "hunter2" not in dumped

    def test_url_and_command_discards_url_with_warning(self):
        """N16: both url and command → stdio, warn that url is discarded."""
        mod = _load_convert()
        warns: list[str] = []
        out = mod.convert_ap_mcp_server(
            {
                "url": "https://example.com/mcp",
                "command": "node",
                "args": ["server.js"],
            },
            warnings=warns,
        )
        assert out["type"] == "stdio"
        assert out["command"] == "node"
        assert "url" not in out
        assert warns and "url" in warns[0].lower() and "discard" in warns[0].lower()

    def test_malformed_plugin_json_is_named_error_exit_1(self, tmp_path):
        """N15: malformed .claude-plugin/plugin.json names the file and exits 1."""
        plugin = tmp_path / "badplug"
        plugin.mkdir()
        manifest_dir = plugin / ".claude-plugin"
        manifest_dir.mkdir()
        path = manifest_dir / "plugin.json"
        path.write_text("{not json")
        analysis = tmp_path / "analysis.json"
        proc = subprocess.run(
            [sys.executable, str(ANALYZE), str(plugin), "-o", str(analysis)],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 1
        err = proc.stderr
        assert "malformed plugin manifest" in err
        assert str(path) in err
        mod = _load_convert()
        with pytest.raises(ValueError, match="malformed plugin manifest") as ei:
            mod.load_source_manifest(plugin, {})
        assert str(path) in str(ei.value)

    def test_nonconforming_mcp_server_is_skipped(self, tmp_path):
        """N9: one bad MCP server is skipped; skills and a good server still convert."""
        mod = _load_convert()
        plugin = tmp_path / "srcplug"
        plugin.mkdir()
        (plugin / ".claude-plugin").mkdir()
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({
            "name": "n9-plugin",
            "version": "1.0.0",
            "description": "skip one mcp",
        }))
        (plugin / ".mcp.json").write_text(json.dumps({
            "mcpServers": {
                "good": {"command": "python3", "args": ["-m", "demo"]},
                "bad": {"command": "node", "args": ["./../escape"]},
            }
        }))
        (plugin / "skills" / "greet").mkdir(parents=True)
        (plugin / "skills" / "greet" / "SKILL.md").write_text(
            "---\nname: greet\ndescription: hi\n---\n\nHi.\n"
        )
        pkg = tmp_path / "pkg"
        analysis = {
            "manifest": {"name": "n9-plugin", "version": "1.0.0", "description": "d"},
            "summary": {"convertible": 1, "partial": 0, "skipped": 0, "total": 1},
            "components": {
                "skills": [{"name": "greet", "path": str(plugin / "skills" / "greet")}],
            },
        }
        results = mod.convert_plugin_agent_plugins(plugin, analysis, pkg)
        assert (pkg / "skills" / "greet" / "SKILL.md").is_file()
        mcp = json.loads((pkg / "mcp.json").read_text())
        assert "good" in mcp["mcpServers"]
        assert "bad" not in mcp["mcpServers"]
        skipped_names = [s["name"] for s in results["skipped_mcp_servers"]]
        assert skipped_names == ["bad"]
        report = (pkg.parent / "CONVERSION_REPORT.md").read_text()
        assert "### Skipped" in report
        assert "bad" in report

    def test_owned_report_files_at_source_root_are_ignored(self, tmp_path):
        """N3 residual: CONVERSION_REPORT.md and conversion_results.json are not copied."""
        mod = _load_convert()
        plugin = tmp_path / "srcplug"
        plugin.mkdir()
        (plugin / ".claude-plugin").mkdir()
        (plugin / ".claude-plugin" / "plugin.json").write_text(json.dumps({
            "name": "n3-plugin",
            "version": "1.0.0",
            "description": "reserved names",
        }))
        (plugin / "CONVERSION_REPORT.md").write_text("# leaked source report\n")
        (plugin / "conversion_results.json").write_text("{\"leaked\": true}\n")
        (plugin / "skills" / "greet").mkdir(parents=True)
        (plugin / "skills" / "greet" / "SKILL.md").write_text(
            "---\nname: greet\ndescription: hi\n---\n\nHi.\n"
        )
        pkg = tmp_path / "pkg"
        analysis = {
            "manifest": {"name": "n3-plugin", "version": "1.0.0", "description": "d"},
            "summary": {"convertible": 1, "partial": 0, "skipped": 0, "total": 1},
            "components": {
                "skills": [{"name": "greet", "path": str(plugin / "skills" / "greet")}],
            },
        }
        results = mod.convert_plugin_agent_plugins(plugin, analysis, pkg)
        assert "CONVERSION_REPORT.md" in results["ignored_source_files"]
        assert "conversion_results.json" in results["ignored_source_files"]
        assert (pkg / "plugin.json").is_file()
        assert not (pkg / "CONVERSION_REPORT.md").is_file()
        assert not (pkg / "conversion_results.json").is_file()
        report = (pkg.parent / "CONVERSION_REPORT.md").read_text()
        assert "leaked source report" not in report
        assert "CONVERSION_REPORT.md" in report
        assert "conversion_results.json" in report
        assert "Ignored source files" in report



