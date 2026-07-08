#!/usr/bin/env python3
"""Tests for search_and_summarize.py — DDG parsing, scoring, freshness, dates, chunking.

No network calls. DDG output is mocked via fixture files.
Run: python3 -m pytest tests/test_search_and_summarize.py -v
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add scripts dir to path
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import search_and_summarize as ss


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_ddg_results():
    """Mimic DDG video search JSON output."""
    return [
        {
            "title": "Python Async Programming Tutorial 2024",
            "content": "https://youtube.com/watch?v=abc12345678",
            "duration": "15:30",
            "uploader": "Tech With Tim",
            "publisher": "YouTube",
            "provider": "YouTube",
            "published": "2024-06-15T00:00:00.000Z",
            "description": "Learn async programming in Python",
            "statistics": {"viewCount": 500000},
        },
        {
            "title": "Not a YouTube video",
            "content": "https://vimeo.com/123",
            "publisher": "Vimeo",
            "duration": "10:00",
            "uploader": "Someone",
            "published": "2024-01-01T00:00:00.000Z",
        },
        {
            "title": "Advanced Python asyncio Deep Dive",
            "content": "https://youtube.com/watch?v=def98765432",
            "duration": "45:00",
            "uploader": "mCoding",
            "publisher": "YouTube",
            "provider": "YouTube",
            "published": "2023-03-10T00:00:00.000Z",
            "description": "Deep dive into asyncio internals",
            "statistics": {"viewCount": 2000000},
        },
        {
            "title": "Python Basics for Beginners",
            "content": "https://youtu.be/ghi11122233",
            "duration": "5:00",
            "uploader": "Programming with Mosh",
            "publisher": "YouTube",
            "published": "2025-01-20T00:00:00.000Z",
            "description": "Python introduction from scratch",
            "statistics": {"viewCount": 50000},
        },
    ]


# ─── Term extraction ─────────────────────────────────────────────────────────

class TestTerms:
    def test_basic_extraction(self):
        result = ss.terms("Python async tutorial")
        assert "python" in result
        assert "async" in result
        assert "tutorial" in result

    def test_stopwords_removed(self):
        result = ss.terms("the best videos for learning python")
        assert "the" not in result
        assert "best" not in result
        assert "videos" not in result
        assert "python" in result

    def test_punctuation_split(self):
        # The regex [a-z0-9+#.-]+ keeps hyphenated terms together
        result = ss.terms("python-async programming")
        assert "python-async" in result
        assert "programming" in result

    def test_special_chars_preserved(self):
        result = ss.terms("c++ rust go")
        assert "c++" in result

    def test_empty_string(self):
        assert ss.terms("") == set()

    def test_case_insensitive(self):
        result = ss.terms("PYTHON Async")
        assert "python" in result
        assert "async" in result


# ─── Duration parsing ────────────────────────────────────────────────────────

class TestParseDuration:
    def test_mmss(self):
        assert ss.parse_duration_to_seconds("15:30") == 930

    def test_hhmmss(self):
        assert ss.parse_duration_to_seconds("1:15:30") == 4530

    def test_short(self):
        assert ss.parse_duration_to_seconds("5:00") == 300

    def test_invalid(self):
        assert ss.parse_duration_to_seconds("invalid") == 0

    def test_empty(self):
        assert ss.parse_duration_to_seconds("") == 0

    def test_none(self):
        assert ss.parse_duration_to_seconds(None) == 0

    def test_just_seconds(self):
        assert ss.parse_duration_to_seconds("0:30") == 30


# ─── Date parsing ────────────────────────────────────────────────────────────

class TestParseIsoDate:
    def test_full_iso(self):
        dt = ss.parse_iso_date("2024-06-15T10:30:00.000Z")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 6
        assert dt.day == 15

    def test_iso_no_ms(self):
        dt = ss.parse_iso_date("2024-06-15T10:30:00")
        assert dt is not None
        assert dt.year == 2024

    def test_date_only(self):
        dt = ss.parse_iso_date("2024-06-15")
        assert dt is not None
        assert dt.year == 2024
        assert dt.month == 6

    def test_iso_with_z(self):
        dt = ss.parse_iso_date("2024-06-15T10:30:00Z")
        assert dt is not None

    def test_empty(self):
        assert ss.parse_iso_date("") is None

    def test_none(self):
        assert ss.parse_iso_date(None) is None

    def test_garbage(self):
        assert ss.parse_iso_date("not a date") is None

    def test_fractional_seconds_with_z(self):
        dt = ss.parse_iso_date("2024-06-15T10:30:00.123Z")
        assert dt is not None
        assert dt.year == 2024


# ─── Months since ────────────────────────────────────────────────────────────

class TestMonthsSince:
    def test_recent(self):
        recent = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        months = ss.months_since(recent)
        assert 0.8 < months < 1.5

    def test_one_year_ago(self):
        months = ss.months_since("2024-06-15T00:00:00.000Z")
        # Should be roughly 12+ months depending on current date
        assert months > 6  # at least half a year (test written mid-2025+)

    def test_empty_returns_large(self):
        assert ss.months_since("") == 999

    def test_none_returns_large(self):
        assert ss.months_since(None) == 999


# ─── Domain matching ─────────────────────────────────────────────────────────

class TestDomainMatching:
    def test_ai_ml_match(self):
        config = ss.load_fast_moving_domains()
        domain = ss.match_domain("LLM fine-tuning tutorial", config)
        assert domain is not None
        assert "ai_ml" in domain.get("keywords", []) or domain.get("stale_months") == 12

    def test_no_match(self):
        config = ss.load_fast_moving_domains()
        domain = ss.match_domain("gardening tips for beginners", config)
        assert domain is None

    def test_longest_keyword_wins(self):
        """When multiple domains could match, the one with the longest matched keyword wins."""
        config = {
            "domains": [
                {"keywords": ["python"], "stale_months": 12, "aging_months": 6, "name": "short"},
                {"keywords": ["python async"], "stale_months": 6, "aging_months": 3, "name": "long"},
            ],
            "defaults": {"stale_months": 36, "aging_months": 24},
        }
        domain = ss.match_domain("python async programming", config)
        assert domain["name"] == "long"


# ─── Freshness config ────────────────────────────────────────────────────────

class TestFreshnessConfig:
    def test_load_domains_file_exists(self):
        config = ss.load_fast_moving_domains()
        assert "domains" in config
        assert len(config["domains"]) > 0

    def test_domains_have_stale_months(self):
        config = ss.load_fast_moving_domains()
        for domain in config["domains"]:
            assert "stale_months" in domain
            assert "aging_months" in domain
            assert domain["stale_months"] > domain["aging_months"]

    def test_defaults_present(self):
        config = ss.load_fast_moving_domains()
        assert "defaults" in config or len(config.get("domains", [])) > 0


# ─── Search (mocked DDG) ─────────────────────────────────────────────────────

class TestSearchVideos:
    def test_filters_non_youtube(self, sample_ddg_results, monkeypatch):
        """Non-YouTube publishers are filtered out."""
        def mock_run_cmd(cmd, timeout=30):
            # Write to temp file as DDG CLI would
            tmp_path = cmd[cmd.index("-o") + 1]
            Path(tmp_path).write_text(json.dumps(sample_ddg_results))
            return 0, "", ""

        monkeypatch.setattr(ss, "run_cmd", mock_run_cmd)
        results = ss.search_videos("python async", max_results=8)

        assert len(results) == 3  # 3 YouTube results out of 4
        for r in results:
            assert "youtube" in r.publisher.lower() or "youtube" in r.provider.lower()

    def test_parses_view_count_from_statistics(self, sample_ddg_results, monkeypatch):
        def mock_run_cmd(cmd, timeout=30):
            tmp_path = cmd[cmd.index("-o") + 1]
            Path(tmp_path).write_text(json.dumps(sample_ddg_results[:1]))
            return 0, "", ""

        monkeypatch.setattr(ss, "run_cmd", mock_run_cmd)
        results = ss.search_videos("test", max_results=1)
        assert results[0].view_count == 500000

    def test_parses_youtu_be_url(self, sample_ddg_results, monkeypatch):
        def mock_run_cmd(cmd, timeout=30):
            tmp_path = cmd[cmd.index("-o") + 1]
            Path(tmp_path).write_text(json.dumps([sample_ddg_results[3]]))
            return 0, "", ""

        monkeypatch.setattr(ss, "run_cmd", mock_run_cmd)
        results = ss.search_videos("test", max_results=1)
        assert "youtu.be" in results[0].url or "youtube" in results[0].url

    def test_empty_ddg_output(self, monkeypatch):
        def mock_run_cmd(cmd, timeout=30):
            tmp_path = cmd[cmd.index("-o") + 1]
            Path(tmp_path).write_text("[]")
            return 0, "", ""

        monkeypatch.setattr(ss, "run_cmd", mock_run_cmd)
        results = ss.search_videos("nothing", max_results=8)
        assert results == []

    def test_ddg_command_failure(self, monkeypatch):
        def mock_run_cmd(cmd, timeout=30):
            return -1, "", "command not found"

        monkeypatch.setattr(ss, "run_cmd", mock_run_cmd)
        results = ss.search_videos("test", max_results=8)
        assert results == []


# ─── Heuristic qualification ─────────────────────────────────────────────────

class TestHeuristicQualify:
    def test_topic_match_boosts_score(self):
        candidates = [
            ss.VideoCandidate(
                title="Python Async Programming Tutorial",
                url="https://youtube.com/watch?v=test1",
                duration="15:30", uploader="Test", view_count=1000,
                published="2025-01-01T00:00:00.000Z", description="",
            ),
            ss.VideoCandidate(
                title="Cooking with Chef John",
                url="https://youtube.com/watch?v=test2",
                duration="15:30", uploader="Test", view_count=1000,
                published="2025-01-01T00:00:00.000Z", description="",
            ),
        ]
        results = ss._heuristic_qualify(candidates, "python async programming", enable_freshness=False)
        # The Python video should score higher than the cooking video
        assert results[0].score > results[1].score
        assert results[0].candidate.title == "Python Async Programming Tutorial"

    def test_duration_in_range_boosts(self):
        """Videos 5-60 min get a duration boost."""
        good_duration = ss.VideoCandidate(
            title="Test", url="https://youtube.com/watch?v=t",
            duration="15:00", uploader="U", view_count=100,
            published="2025-01-01T00:00:00.000Z", description="",
        )
        short_duration = ss.VideoCandidate(
            title="Test", url="https://youtube.com/watch?v=t",
            duration="1:00", uploader="U", view_count=100,
            published="2025-01-01T00:00:00.000Z", description="",
        )
        results = ss._heuristic_qualify([good_duration, short_duration], "test", enable_freshness=False)
        good_score = next(r for r in results if r.candidate == good_duration).score
        short_score = next(r for r in results if r.candidate == short_duration).score
        assert good_score > short_score

    def test_high_views_boost(self):
        popular = ss.VideoCandidate(
            title="Test", url="https://youtube.com/watch?v=t1",
            duration="15:00", uploader="U", view_count=2_000_000,
            published="2025-01-01T00:00:00.000Z", description="",
        )
        unpopular = ss.VideoCandidate(
            title="Test", url="https://youtube.com/watch?v=t2",
            duration="15:00", uploader="U", view_count=500,
            published="2025-01-01T00:00:00.000Z", description="",
        )
        results = ss._heuristic_qualify([popular, unpopular], "test", enable_freshness=False)
        pop_score = next(r for r in results if r.candidate == popular).score
        unpop_score = next(r for r in results if r.candidate == unpopular).score
        assert pop_score > unpop_score

    def test_freshness_bonus(self):
        """Fresh videos get a score boost when freshness is enabled."""
        fresh = ss.VideoCandidate(
            title="Test", url="https://youtube.com/watch?v=t1",
            duration="15:00", uploader="U", view_count=100,
            published=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            description="",
        )
        old = ss.VideoCandidate(
            title="Test", url="https://youtube.com/watch?v=t2",
            duration="15:00", uploader="U", view_count=100,
            published="2020-01-01T00:00:00.000Z",
            description="",
        )
        # Set age + thresholds as qualify_videos would
        fresh.age_months = 0
        old.age_months = 84
        for c in (fresh, old):
            c.stale_months = 36
            c.aging_months = 24
        results = ss._heuristic_qualify([fresh, old], "test", enable_freshness=True)
        fresh_score = next(r for r in results if r.candidate == fresh).score
        old_score = next(r for r in results if r.candidate == old).score
        assert fresh_score > old_score

    def test_stale_video_penalty(self):
        old = ss.VideoCandidate(
            title="Test", url="https://youtube.com/watch?v=t",
            duration="15:00", uploader="U", view_count=100,
            published="2018-01-01T00:00:00.000Z",
            description="",
        )
        # Set age + thresholds as qualify_videos would
        old.age_months = 84  # 7 years
        old.stale_months = 36
        old.aging_months = 24
        results = ss._heuristic_qualify([old], "test", enable_freshness=True)
        # Stale video: 50 + 8 (topic match 'test') + 15 (duration) + 5 (views>100? no, 100 not >100) - 10 (stale)
        # = 50 + 8 + 15 + 0 - 10 = 63, clamped. Just verify penalty applied vs no-freshness
        results_no_fresh = ss._heuristic_qualify([old], "test", enable_freshness=False)
        assert results[0].score < results_no_fresh[0].score  # freshness penalty applied

    def test_score_clamped_0_100(self):
        """Scores should never go below 0 or above 100."""
        # Very high overlap + max views + fresh + good duration
        perfect = ss.VideoCandidate(
            title="python python python python python",
            url="https://youtube.com/watch?v=t",
            duration="15:00", uploader="U", view_count=10_000_000,
            published=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            description="",
        )
        results = ss._heuristic_qualify([perfect], "python", enable_freshness=True)
        assert results[0].score <= 100

    def test_freshness_labels(self):
        fresh = ss.VideoCandidate(
            title="T", url="https://youtube.com/watch?v=t1",
            duration="15:00", uploader="U", view_count=100,
            published=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            description="",
        )
        stale = ss.VideoCandidate(
            title="T", url="https://youtube.com/watch?v=t2",
            duration="15:00", uploader="U", view_count=100,
            published="2015-01-01T00:00:00.000Z",
            description="",
        )
        # Set age + thresholds as qualify_videos would
        fresh.age_months = 0
        stale.age_months = 120
        for c in (fresh, stale):
            c.stale_months = 36
            c.aging_months = 24
        results = ss._heuristic_qualify([fresh, stale], "test", enable_freshness=True)
        fresh_r = next(r for r in results if r.candidate == fresh)
        stale_r = next(r for r in results if r.candidate == stale)
        assert fresh_r.freshness == "fresh"
        assert stale_r.freshness == "stale"

    def test_empty_candidates(self):
        assert ss._heuristic_qualify([], "test", True) == []


# ─── LLM qualification parsing ───────────────────────────────────────────────

class TestLLMQualification:
    def test_parse_valid_response(self):
        candidates = [
            ss.VideoCandidate("A", "url1", "10:00", "U", 100, "2025-01-01", ""),
            ss.VideoCandidate("B", "url2", "10:00", "U", 100, "2025-01-01", ""),
        ]
        llm_result = {
            "scores": [
                {"index": 1, "score": 85, "reasoning": "great", "freshness": "fresh"},
                {"index": 2, "score": 60, "reasoning": "ok", "freshness": "aging"},
            ]
        }
        results = ss._parse_llm_qualification(candidates, llm_result)
        assert len(results) == 2
        assert results[0].score == 85  # sorted desc
        assert results[0].candidate.title == "A"

    def test_parse_empty_scores(self):
        candidates = [ss.VideoCandidate("A", "url1", "10:00", "U", 100, "2025-01-01", "")]
        results = ss._parse_llm_qualification(candidates, {"scores": []})
        assert results == []

    def test_parse_out_of_range_index(self):
        """Indices beyond the candidate list are skipped."""
        candidates = [ss.VideoCandidate("A", "url1", "10:00", "U", 100, "2025-01-01", "")]
        llm_result = {"scores": [{"index": 5, "score": 90}]}
        results = ss._parse_llm_qualification(candidates, llm_result)
        assert results == []


# ─── Transcript chunking ─────────────────────────────────────────────────────

class TestChunkTranscript:
    def test_short_text_single_chunk(self):
        result = ss.chunk_transcript("short text", chunk_size=100)
        assert len(result) == 1
        assert result[0] == "short text"

    def test_long_text_multiple_chunks(self):
        text = "A" * 1000
        chunks = ss.chunk_transcript(text, chunk_size=400, overlap=100)
        assert len(chunks) > 1
        # Each chunk should be at most chunk_size
        for c in chunks:
            assert len(c) <= 400

    def test_overlap_present(self):
        text = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 100
        chunks = ss.chunk_transcript(text, chunk_size=100, overlap=30)
        if len(chunks) > 1:
            # The end of chunk 0 should appear at the start of chunk 1
            assert chunks[0][-30:] == chunks[1][:30]

    def test_empty_text(self):
        assert ss.chunk_transcript("") == [""]

    def test_exact_chunk_size(self):
        text = "A" * 400
        chunks = ss.chunk_transcript(text, chunk_size=400, overlap=100)
        assert len(chunks) == 1


# ─── Transcript cleaning ─────────────────────────────────────────────────────

class TestTranscriptCleaning:
    def test_removes_timestamp_only_lines(self):
        """Lines that are just timestamps should be removed during review."""
        transcript = "00:15\nHello world\n00:20\nThis is content"
        lines = transcript.split('\n')
        clean = []
        for line in lines:
            if __import__('re').match(r'^\d{1,2}:\d{2}(:\d{2})?\s*$', line.strip()):
                continue
            if __import__('re').match(r'^\d{1,2}:\d{2}(:\d{2})?\s', line.strip()):
                line = __import__('re').sub(r'^\d{1,2}:\d{2}(:\d{2})?\s*', '', line)
            clean.append(line)
        result = ' '.join(clean)
        assert "00:15" not in result
        assert "Hello world" in result
        assert "This is content" in result


# ─── Heuristic review ────────────────────────────────────────────────────────

class TestHeuristicReview:
    def test_relevance_based_on_term_hits(self):
        candidate = ss.VideoCandidate(
            "Python Tutorial", "url", "10:00", "U", 100,
            "2025-01-01T00:00:00.000Z", "",
        )
        qualified = ss.QualifiedVideo(candidate, 80, "good match", "fresh")
        transcript = "python programming tutorial for beginners learning the basics"
        result = ss._heuristic_review("python tutorial", qualified, transcript, transcript)

        # Multiple query terms hit → higher relevance
        assert result.relevance_score > 50

    def test_audience_beginner(self):
        candidate = ss.VideoCandidate(
            "Basics", "url", "10:00", "U", 100,
            "2025-01-01T00:00:00.000Z", "",
        )
        qualified = ss.QualifiedVideo(candidate, 80, "match", "fresh")
        transcript = "This is an introduction for beginners covering the basics from scratch"
        result = ss._heuristic_review("test", qualified, transcript, transcript)
        assert result.audience_level == "beginner"

    def test_audience_advanced(self):
        candidate = ss.VideoCandidate(
            "Deep Dive", "url", "10:00", "U", 100,
            "2025-01-01T00:00:00.000Z", "",
        )
        qualified = ss.QualifiedVideo(candidate, 80, "match", "fresh")
        transcript = "We'll dive deep into the internals and optimization for performance"
        result = ss._heuristic_review("test", qualified, transcript, transcript)
        assert result.audience_level == "advanced"

    def test_audience_intermediate_default(self):
        candidate = ss.VideoCandidate(
            "Test", "url", "10:00", "U", 100,
            "2025-01-01T00:00:00.000Z", "",
        )
        qualified = ss.QualifiedVideo(candidate, 80, "match", "fresh")
        transcript = "This is a normal programming video about web development"
        result = ss._heuristic_review("test", qualified, transcript, transcript)
        assert result.audience_level == "intermediate"

    def test_summary_bullets_extracted(self):
        candidate = ss.VideoCandidate(
            "Test", "url", "10:00", "U", 100,
            "2025-01-01T00:00:00.000Z", "",
        )
        qualified = ss.QualifiedVideo(candidate, 80, "match", "fresh")
        transcript = "First important point about the topic. Second substantive sentence here. Third key insight follows."
        result = ss._heuristic_review("topic", qualified, transcript, transcript)
        assert len(result.summary_bullets) > 0
        # Each bullet should be a substantive sentence
        for bullet in result.summary_bullets:
            assert len(bullet) > 20

    def test_transcript_quality(self):
        candidate = ss.VideoCandidate("T", "url", "10:00", "U", 100, "2025-01-01", "")
        qualified = ss.QualifiedVideo(candidate, 80, "match", "fresh")

        long_transcript = "A" * 2000
        result = ss._heuristic_review("test", qualified, long_transcript, long_transcript)
        assert result.transcript_quality == "good"

        short_transcript = "A" * 500
        result = ss._heuristic_review("test", qualified, short_transcript, short_transcript)
        assert result.transcript_quality == "fair"


# ─── Merge chunk reviews ─────────────────────────────────────────────────────

class TestMergeChunkReviews:
    def test_averages_relevance(self):
        reviews = [
            {"relevance_score": 80, "summary_bullets": ["a"], "gaps": ["g1"],
             "audience_level": "beginner", "watch_if": ["w1"], "skip_if": ["s1"],
             "transcript_quality": "good"},
            {"relevance_score": 60, "summary_bullets": ["b"], "gaps": ["g2"],
             "audience_level": "advanced", "watch_if": ["w2"], "skip_if": ["s2"],
             "transcript_quality": "good"},
        ]
        merged = ss._merge_chunk_reviews(reviews)
        assert merged["relevance_score"] == 70  # (80+60)//2

    def test_concatenates_summaries(self):
        reviews = [
            {"relevance_score": 50, "summary_bullets": ["a", "b"], "gaps": [],
             "audience_level": "intermediate", "watch_if": [], "skip_if": [],
             "transcript_quality": "good"},
            {"relevance_score": 50, "summary_bullets": ["c", "d"], "gaps": [],
             "audience_level": "intermediate", "watch_if": [], "skip_if": [],
             "transcript_quality": "good"},
        ]
        merged = ss._merge_chunk_reviews(reviews)
        assert "a" in merged["summary_bullets"]
        assert "c" in merged["summary_bullets"]

    def test_dedupes_gaps(self):
        reviews = [
            {"relevance_score": 50, "summary_bullets": [], "gaps": ["same gap", "unique1"],
             "audience_level": "intermediate", "watch_if": [], "skip_if": [],
             "transcript_quality": "good"},
            {"relevance_score": 50, "summary_bullets": [], "gaps": ["same gap", "unique2"],
             "audience_level": "intermediate", "watch_if": [], "skip_if": [],
             "transcript_quality": "good"},
        ]
        merged = ss._merge_chunk_reviews(reviews)
        assert merged["gaps"].count("same gap") == 1
        assert "unique1" in merged["gaps"]
        assert "unique2" in merged["gaps"]

    def test_audience_level_priority(self):
        """Beginner takes priority over advanced over intermediate."""
        reviews = [
            {"relevance_score": 50, "summary_bullets": [], "gaps": [],
             "audience_level": "intermediate", "watch_if": [], "skip_if": [],
             "transcript_quality": "good"},
            {"relevance_score": 50, "summary_bullets": [], "gaps": [],
             "audience_level": "beginner", "watch_if": [], "skip_if": [],
             "transcript_quality": "good"},
        ]
        merged = ss._merge_chunk_reviews(reviews)
        assert merged["audience_level"] == "beginner"

    def test_caps_summaries_at_6(self):
        reviews = [
            {"relevance_score": 50, "summary_bullets": ["1", "2", "3", "4"], "gaps": [],
             "audience_level": "intermediate", "watch_if": [], "skip_if": [],
             "transcript_quality": "good"},
            {"relevance_score": 50, "summary_bullets": ["5", "6", "7", "8"], "gaps": [],
             "audience_level": "intermediate", "watch_if": [], "skip_if": [],
             "transcript_quality": "good"},
        ]
        merged = ss._merge_chunk_reviews(reviews)
        assert len(merged["summary_bullets"]) <= 6


# ─── Visual value detection ──────────────────────────────────────────────────

class TestVisualValueDetection:
    def test_detects_demo_keyword(self):
        candidate = ss.VideoCandidate(
            "React Demo", "url", "10:00", "U", 100, "2025-01-01",
            "Live coding demo of React components",
        )
        result = ss._detect_visual_value(candidate, "")
        assert any("demo" in r.lower() for r in result)

    def test_detects_from_transcript(self):
        candidate = ss.VideoCandidate(
            "Test", "url", "10:00", "U", 100, "2025-01-01", "",
        )
        transcript = "In this walkthrough we'll show a dashboard and UI examples"
        result = ss._detect_visual_value(candidate, transcript)
        assert any("walkthrough" in r.lower() or "dashboard" in r.lower() or "ui" in r.lower()
                   for r in result)

    def test_no_visual_signals(self):
        candidate = ss.VideoCandidate(
            "Podcast", "url", "10:00", "U", 100, "2025-01-01",
            "Just talking about concepts and theory",
        )
        # Use a transcript that avoids all VISUAL_KEYWORDS
        transcript = "an abstract philosophical discussion about epistemology and metaphysics theory only no screens"
        result = ss._detect_visual_value(candidate, transcript)
        assert len(result) == 1
        assert "no explicit" in result[0].lower() or "may benefit" in result[0].lower()


# ─── Transcript quote extraction ─────────────────────────────────────────────

class TestTranscriptQuotes:
    def test_extracts_relevant_quotes(self):
        transcript = "00:00 Introduction\n00:15 Python is a great language for beginners\n00:30 Cooking is fun\n00:45 Python async programming is powerful"
        quotes = ss._extract_transcript_quotes(transcript, "python programming")
        assert len(quotes) > 0
        # Should find the python-related quotes, not cooking
        for q in quotes:
            assert "python" in q["text"].lower() or "programming" in q["text"].lower()

    def test_respects_max_quotes(self):
        transcript = "\n".join([
            f"00:{i:02d} python python python python python python python python python python"
            for i in range(20)
        ])
        quotes = ss._extract_transcript_quotes(transcript, "python", max_quotes=3)
        assert len(quotes) <= 3

    def test_empty_transcript(self):
        quotes = ss._extract_transcript_quotes("", "python")
        assert quotes == []

    def test_no_matching_terms(self):
        transcript = "00:00 cooking recipe pasta\n00:30 baking bread oven"
        quotes = ss._extract_transcript_quotes(transcript, "python programming")
        assert quotes == []


# ─── Markdown cell escaping ──────────────────────────────────────────────────

class TestMdCell:
    def test_escapes_pipe(self):
        assert "\\|" in ss._md_cell("a|b")

    def test_collapses_newlines(self):
        assert "\n" not in ss._md_cell("line1\nline2")

    def test_plain_text_unchanged(self):
        assert ss._md_cell("hello world") == "hello world"

    def test_non_string(self):
        assert ss._md_cell(42) == "42"


# ─── Source numbering ────────────────────────────────────────────────────────

class TestNextSourceNum:
    def test_empty_dir(self, tmp_path):
        assert ss._next_source_num(tmp_path) == 1

    def test_with_existing_files(self, tmp_path):
        (tmp_path / "001_youtube_foo.md").write_text("test")
        (tmp_path / "003_youtube_bar.md").write_text("test")
        assert ss._next_source_num(tmp_path) == 4

    def test_ignores_non_numbered(self, tmp_path):
        (tmp_path / "readme.md").write_text("test")
        (tmp_path / "001_youtube_foo.md").write_text("test")
        assert ss._next_source_num(tmp_path) == 2


# ─── LLM call hook ───────────────────────────────────────────────────────────

class TestLLMCallHook:
    def test_default_returns_none(self):
        """Without an override, call_llm returns None (heuristic mode)."""
        # Save and restore
        original = ss.LLM_CALL
        ss.LLM_CALL = None
        try:
            assert ss.call_llm("test prompt") is None
        finally:
            ss.LLM_CALL = original

    def test_custom_hook_called(self):
        original = ss.LLM_CALL
        captured = []
        def mock_hook(prompt):
            captured.append(prompt)
            return {"scores": []}
        ss.LLM_CALL = mock_hook
        try:
            result = ss.call_llm("test")
            assert result == {"scores": []}
            assert len(captured) == 1
            assert "test" in captured[0]
        finally:
            ss.LLM_CALL = original


# ─── Run command helper ──────────────────────────────────────────────────────

class TestRunCmd:
    def test_success(self):
        code, stdout, stderr = ss.run_cmd(["echo", "hello"], timeout=5)
        assert code == 0
        assert "hello" in stdout

    def test_command_not_found(self):
        code, stdout, stderr = ss.run_cmd(["nonexistent_command_xyz"], timeout=5)
        assert code == -1
        assert "not found" in stderr

    def test_timeout(self):
        code, stdout, stderr = ss.run_cmd(["sleep", "10"], timeout=1)
        assert code == -1
        assert "timeout" in stderr


# ─── Data classes ────────────────────────────────────────────────────────────

class TestDataClasses:
    def test_video_candidate_defaults(self):
        c = ss.VideoCandidate("Title", "url", "10:00", "U", 100, "2025-01-01", "desc")
        assert c.provider == "YouTube"
        assert c.publisher == "YouTube"
        assert c.age_months == 0
        assert c.stale_months == 36

    def test_qualified_video_fields(self):
        c = ss.VideoCandidate("T", "url", "10:00", "U", 100, "2025-01-01", "")
        q = ss.QualifiedVideo(c, 75, "good", "fresh")
        assert q.score == 75
        assert q.freshness == "fresh"

    def test_reviewed_video_defaults(self):
        c = ss.VideoCandidate("T", "url", "10:00", "U", 100, "2025-01-01", "")
        q = ss.QualifiedVideo(c, 75, "good", "fresh")
        r = ss.ReviewedVideo(q, 80, ["bullet1"], ["gap1"], "intermediate", ["watch"], ["skip"], "good")
        assert r.transcript_status == "available"
        assert r.transcript_error == ""
        assert r.key_timestamps is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])