#!/usr/bin/env python3
"""Tests for the media-analyzer rule-based scanner."""

import io
import json
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import analyze  # noqa: E402


def write_temp_article(text: str) -> str:
    """Write article text to a temporary file and return its path."""
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".md")
    with handle:
        handle.write(text)
    return handle.name


def test_scan_loaded_language() -> None:
    """Known loaded words are counted and reported with neutral alternatives."""
    text = "The mayor slammed the shocking report. Officials blasted the plan."
    result = analyze.scan_article(text, source="loaded.md")
    loaded = result["loaded_language"]
    words = {item["word"].lower() for item in loaded["instances"]}
    assert loaded["count"] >= 3
    assert {"slammed", "shocking", "blasted"}.issubset(words)
    assert any(item["neutral_alternative"] == "responded" for item in loaded["instances"])


def test_scan_source_mentions() -> None:
    """Quoted and attributed sources are extracted and categorized."""
    text = (
        '"The bridge is safe," said Transport Department spokesperson Mira Lee.\n\n'
        "According to Professor Alan Chen, the data remains incomplete.\n\n"
        "Local resident Priya Shah stated that the detour adds twenty minutes.\n\n"
        "The River Workers Union reported delays across two terminals."
    )
    result = analyze.scan_article(text)
    sources = result["source_mentions"]
    assert sources["total"] >= 4
    assert sources["by_type"]["official"] >= 1
    assert sources["by_type"]["expert"] >= 1
    assert sources["by_type"]["citizen"] >= 1
    assert sources["by_type"]["organization"] >= 1


def test_scan_emotional_appeals() -> None:
    """Fear, pity, authority, and urgency terms are detected as emotional signals."""
    text = (
        "Experts say the crisis creates a dangerous threat for vulnerable children. "
        "Residents were told immediate action is urgent."
    )
    result = analyze.scan_article(text)
    emotional = result["emotional_appeals"]
    assert emotional["count"] >= 5
    assert "fear" in emotional["patterns"]
    assert "pity" in emotional["patterns"]
    assert "appeal_to_authority" in emotional["patterns"]
    assert "urgency" in emotional["patterns"]


def test_scan_structure() -> None:
    """Paragraph, sentence, question, and exclamation counts are measured."""
    text = "First sentence. Is this a question?\n\nSecond paragraph has two sentences. Yes!"
    result = analyze.scan_article(text)
    structure = result["structure"]
    assert structure["paragraphs"] == 2
    assert structure["sentences"] == 4
    assert structure["questions_asked"] == 1
    assert structure["exclamation_marks"] == 1
    assert structure["avg_sentence_length"] > 0


def test_scan_bias_spectrum() -> None:
    """Technique counts map to the non-directional intensity spectrum."""
    assert analyze.bias_spectrum_score(0) == "Neutral"
    assert analyze.bias_spectrum_score(1) == "Slight lean"
    assert analyze.bias_spectrum_score(2) == "Slight lean"
    assert analyze.bias_spectrum_score(3) == "Clear lean"
    assert analyze.bias_spectrum_score(4) == "Clear lean"
    assert analyze.bias_spectrum_score(5) == "Partisan"

    neutral = analyze.scan_article("The committee met on Tuesday. The agenda included road repairs.")
    assert neutral["bias_spectrum_score"] == "Neutral"

    clear = analyze.scan_article("Experts say a shocking crisis threatens children? Act now!")
    assert clear["bias_spectrum_score"] in {"Clear lean", "Partisan"}


def test_report_generation() -> None:
    """Report generation produces the requested Markdown sections."""
    scan = analyze.scan_article('"We need repairs," said Public Works Department director Lin. The delay is alarming.', source="sample.md")
    report = analyze.build_report(scan)
    assert "# Media Analysis Report" in report
    assert "## Source: sample.md" in report
    assert "## Techniques Detected" in report
    assert "### 1. Loaded Language" in report
    assert "### 2. Source Selection" in report
    assert "### 3. Emotional Appeals" in report
    assert "## Bias Spectrum" in report
    assert "## What's Missing" in report
    assert "Analysis detects techniques, not political positions" in report


def test_wordlist() -> None:
    """The wordlist command exposes all loaded-language entries."""
    assert len(analyze.get_wordlist()) >= 40
    stdout = io.StringIO()
    with redirect_stdout(stdout):
        exit_code = analyze.main(["wordlist", "--format", "json"])
    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert len(payload) == len(analyze.get_wordlist())
    assert {"word", "category", "neutral_alternative"}.issubset(payload[0])


def test_neutral_text() -> None:
    """Plain neutral text has no loaded-language hits and stays Neutral."""
    text = "The board met on Monday. Members reviewed the budget and scheduled another meeting."
    result = analyze.scan_article(text)
    assert result["loaded_language"]["count"] == 0
    assert result["emotional_appeals"]["count"] == 0
    assert result["source_mentions"]["total"] == 0
    assert result["technique_count"] == 0
    assert result["bias_spectrum_score"] == "Neutral"


def test_source_categorization() -> None:
    """Source categorization handles official, expert, citizen, organization, and unknown."""
    assert analyze.categorize_source("Health Department official") == "official"
    assert analyze.categorize_source("Professor Maya Rao") == "expert"
    assert analyze.categorize_source("local resident Jonah Miles") == "citizen"
    assert analyze.categorize_source("Teachers Union representative") == "organization"
    assert analyze.categorize_source("Alex Morgan") == "unknown"


def test_scan_command_writes_json() -> None:
    """The scan CLI reads a file and writes JSON output."""
    article_path = write_temp_article("The shocking report? Experts say children face danger!")
    output_path = tempfile.NamedTemporaryFile(delete=False, suffix=".json").name
    exit_code = analyze.main(["scan", "--input", article_path, "--output", output_path])
    data = json.loads(Path(output_path).read_text(encoding="utf-8"))
    assert exit_code == 0
    assert data["loaded_language"]["count"] >= 1
    assert data["bias_spectrum_score"] in {"Clear lean", "Partisan"}
