import csv
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "convert.py"

spec = importlib.util.spec_from_file_location("document_convert", SCRIPT)
assert spec is not None
convert = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(convert)


def run_cli(args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        text=True,
        capture_output=True,
        check=True,
    )


def test_markdown_to_html(tmp_path):
    src = tmp_path / "input.md"
    out = tmp_path / "output.html"
    src.write_text("# Title\n\nHello **bold** [site](https://example.com)\n", encoding="utf-8")

    run_cli(["--input", str(src), "--from", "markdown", "--to", "html", "--output", str(out)])

    html = out.read_text(encoding="utf-8")
    assert "<h1>Title</h1>" in html
    assert "<strong>bold</strong>" in html
    assert '<a href="https://example.com">site</a>' in html


def test_html_to_markdown(tmp_path):
    src = tmp_path / "input.html"
    out = tmp_path / "output.md"
    src.write_text('<h1>Title</h1><p>Hello <strong>bold</strong> <a href="https://example.com">site</a></p>', encoding="utf-8")

    run_cli(["--input", str(src), "--from", "html", "--to", "markdown", "--output", str(out)])

    md = out.read_text(encoding="utf-8")
    assert "# Title" in md
    assert "Hello **bold** [site](https://example.com)" in md


def test_html_to_text(tmp_path):
    src = tmp_path / "input.html"
    out = tmp_path / "output.txt"
    src.write_text("<h1>Title &amp; More</h1><p>Hello&nbsp;<strong>world</strong></p>", encoding="utf-8")

    run_cli(["--input", str(src), "--from", "html", "--to", "text", "--output", str(out)])

    text = out.read_text(encoding="utf-8")
    assert "Title & More" in text
    assert "Hello world" in text
    assert "<" not in text


def test_csv_to_json(tmp_path):
    src = tmp_path / "people.csv"
    out = tmp_path / "people.json"
    src.write_text("name,age\nAda,36\nGrace,85\n", encoding="utf-8")

    run_cli(["--input", str(src), "--from", "csv", "--to", "json", "--output", str(out)])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == [{"name": "Ada", "age": "36"}, {"name": "Grace", "age": "85"}]


def test_json_to_csv(tmp_path):
    src = tmp_path / "records.json"
    out = tmp_path / "records.csv"
    src.write_text(json.dumps([{"name": "Ada", "address": {"city": "London"}, "tags": ["math"]}]), encoding="utf-8")

    run_cli(["--input", str(src), "--from", "json", "--to", "csv", "--output", str(out)])

    rows = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()))
    assert rows[0]["name"] == "Ada"
    assert rows[0]["address.city"] == "London"
    assert rows[0]["tags"] == '["math"]'


def test_yaml_to_json(tmp_path):
    src = tmp_path / "config.yaml"
    out = tmp_path / "config.json"
    src.write_text("name: Ada\nage: 36\nactive: true\nskills:\n  - math\n  - code\naddress:\n  city: London\n", encoding="utf-8")

    run_cli(["--input", str(src), "--from", "yaml", "--to", "json", "--output", str(out)])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["name"] == "Ada"
    assert data["age"] == 36
    assert data["active"] is True
    assert data["skills"] == ["math", "code"]
    assert data["address"]["city"] == "London"


def test_json_to_yaml(tmp_path):
    src = tmp_path / "config.json"
    out = tmp_path / "config.yaml"
    src.write_text(json.dumps({"name": "Ada", "active": True, "items": [1, 2]}), encoding="utf-8")

    run_cli(["--input", str(src), "--from", "json", "--to", "yaml", "--output", str(out)])

    text = out.read_text(encoding="utf-8")
    assert "name: Ada" in text
    assert "active: true" in text
    assert "items:" in text
    assert "  - 1" in text


def test_toml_to_json(tmp_path):
    src = tmp_path / "config.toml"
    out = tmp_path / "config.json"
    src.write_text('name = "Ada"\nactive = true\n[db]\nport = 5432\n', encoding="utf-8")

    run_cli(["--input", str(src), "--from", "toml", "--to", "json", "--output", str(out)])

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {"name": "Ada", "active": True, "db": {"port": 5432}}


def test_json_to_toml(tmp_path):
    src = tmp_path / "config.json"
    out = tmp_path / "config.toml"
    src.write_text(json.dumps({"name": "Ada", "active": True, "db": {"port": 5432}, "nums": [1, 2]}), encoding="utf-8")

    run_cli(["--input", str(src), "--from", "json", "--to", "toml", "--output", str(out)])

    text = out.read_text(encoding="utf-8")
    assert 'name = "Ada"' in text
    assert "active = true" in text
    assert "nums = [1, 2]" in text
    assert "[db]" in text
    assert "port = 5432" in text


def test_yaml_to_toml(tmp_path):
    src = tmp_path / "config.yaml"
    out = tmp_path / "config.toml"
    src.write_text("name: Ada\nactive: true\ndb:\n  port: 5432\n", encoding="utf-8")

    run_cli(["--input", str(src), "--from", "yaml", "--to", "toml", "--output", str(out)])

    text = out.read_text(encoding="utf-8")
    assert 'name = "Ada"' in text
    assert "active = true" in text
    assert "[db]" in text
    assert "port = 5432" in text


def test_toml_to_yaml(tmp_path):
    src = tmp_path / "config.toml"
    out = tmp_path / "config.yaml"
    src.write_text('name = "Ada"\n[db]\nport = 5432\n', encoding="utf-8")

    run_cli(["--input", str(src), "--from", "toml", "--to", "yaml", "--output", str(out)])

    text = out.read_text(encoding="utf-8")
    assert "name: Ada" in text
    assert "db:" in text
    assert "  port: 5432" in text


def test_csv_to_markdown_table(tmp_path):
    src = tmp_path / "people.csv"
    out = tmp_path / "people.md"
    src.write_text("name,role\nAda,mathematician\n", encoding="utf-8")

    run_cli(["--input", str(src), "--from", "csv", "--to", "markdown", "--output", str(out)])

    table = out.read_text(encoding="utf-8")
    assert "| name | role |" in table
    assert "| --- | --- |" in table
    assert "| Ada | mathematician |" in table


def test_markdown_table_to_csv(tmp_path):
    src = tmp_path / "people.md"
    out = tmp_path / "people.csv"
    src.write_text("| name | role |\n| --- | --- |\n| Ada | mathematician |\n", encoding="utf-8")

    run_cli(["--input", str(src), "--from", "markdown", "--to", "csv", "--output", str(out)])

    assert out.read_text(encoding="utf-8") == "name,role\nAda,mathematician\n"


def test_auto_detect_format(tmp_path):
    src = tmp_path / "input.md"
    out = tmp_path / "output.html"
    src.write_text("# Auto\n", encoding="utf-8")

    run_cli(["--input", str(src), "--to", "html", "--output", str(out)])

    assert "<h1>Auto</h1>" in out.read_text(encoding="utf-8")


def test_yaml_fallback(monkeypatch):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "yaml":
            raise ImportError("PyYAML intentionally unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    data = convert.load_yaml("name: Ada\nactive: true\nitems:\n  - one\n  - 2\n", prefer_pyyaml=True)

    assert data == {"name": "Ada", "active": True, "items": ["one", 2]}


def test_yaml_multidocument_rejected():
    with pytest.raises(convert.ConversionError, match="multi-document"):
        convert.load_yaml("---\na: 1\n---\nb: 2\n", prefer_pyyaml=False)
