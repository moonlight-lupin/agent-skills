#!/usr/bin/env python3
"""Unit tests for research_validation.py — gates, evidence store, support scoring.

Run:  python -m pytest research/deep-research/tests/test_research_validation.py -q

No network required. Stdlib-only module under test.
"""

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import research_validation as rv  # noqa: E402


class TestSupportScoring:
    def test_identical_text_supported(self):
        assert rv.support_score("Acme revenue grew 40 percent in 2024",
                                 ["Acme revenue grew 40 percent in 2024"]) >= rv.SUPPORTED_THRESHOLD

    def test_comma_normalization(self):
        assert rv.support_score("Sales were 1,200 units", ["Sales were 1200 units"]) >= rv.SUPPORTED_THRESHOLD

    def test_contradicting_figure_capped(self):
        assert rv.support_score("Revenue was 40 billion USD",
                                ["Revenue was 45 billion USD"]) < rv.SUPPORTED_THRESHOLD

    def test_contradicting_year_capped(self):
        assert rv.support_score("Acme opened 2000 stores in 2024",
                                ["Acme opened 1950 stores in 2024"]) < rv.SUPPORTED_THRESHOLD

    def test_embedded_yearlike_model_numbers_contradict(self):
        # 'v2000' vs 'v2001' — digit runs inside tokens are figures, not years,
        # and the year-boundary check is occurrence-level, not whole-text.
        assert rv.support_score("Acme v2000 sales grew steadily worldwide in 2024",
                                ["Acme v2001 sales grew steadily worldwide in 2024"]) < rv.SUPPORTED_THRESHOLD
        assert rv.support_score("Acme v2000 sales grew steadily worldwide in 2024",
                                ["Acme v2000 sales grew steadily worldwide in 2024"]) >= rv.SUPPORTED_THRESHOLD
        # A bare ' in 2000' in the same text must not excuse the embedded '2000'
        # inside 'v2000' (review round 4).
        assert rv.support_score("Acme v2000 sales grew steadily worldwide in 2000",
                                ["Acme v2001 sales grew steadily worldwide in 2000"]) < rv.SUPPORTED_THRESHOLD

    def test_product_name_digits_are_figures(self):
        assert rv.support_score("Apple iPhone15 sales grew steadily worldwide",
                                ["Apple iPhone16 sales grew steadily worldwide"]) < rv.SUPPORTED_THRESHOLD

    def test_bare_year_is_year_not_figure(self):
        assert rv._figures("Acme opened 2000 stores in 2024") == set()
        assert rv._figures("2,000 units") == set()
        assert rv._figures("Report (2000) says") == set()
        assert rv._figures("Acme v2000 sales grew steadily worldwide in 2000") == {"2000"}
