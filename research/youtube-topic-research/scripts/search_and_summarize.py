#!/usr/bin/env python3
"""
YouTube Topic Research — Search, qualify, fetch transcripts, summarize.

Uses heuristic scoring by default. LLM hook (call_llm) is available for
qualification and review when an agent runtime provides an LLM endpoint.

Usage:
    python search_and_summarize.py "query" [options]
    python search_and_summarize.py "query" --top 2 --format md
    python search_and_summarize.py "query" --no-freshness --format json
    python search_and_summarize.py "query" --debug
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

import yaml
from jinja2 import Environment, FileSystemLoader

# ── Paths ──────────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
REFERENCES_DIR = SKILL_DIR / "references"
TEMPLATES_DIR = SKILL_DIR / "templates"

# ── LLM Hook ────────────────────────────────────────────────────────────
# Agent runtimes can set this via env var or by patching the module.
# When set, qualification and review use LLM instead of heuristics.
# When None, heuristic scoring is used.
# Example: LLM_ENDPOINT=https://api.openai.com/v1/chat/completions
# The hook function is runtime-specific. Agent runtimes should override
# this function to call their LLM. It must accept a prompt string and
# return a parsed JSON dict, or None on failure.
LLM_CALL: Optional[Callable[[str], dict]] = None

def call_llm(prompt: str) -> Optional[dict]:
    """Call LLM with a prompt and return parsed JSON dict, or None.

    Override this function in agent runtimes (e.g. Hermes, OpenAI, Ollama).
    Default: returns None (heuristic mode).
    """
    if LLM_CALL is not None:
        return LLM_CALL(prompt)
    return None


# ── Transcript Fetcher Resolution ────────────────────────────────────────
def _resolve_transcript_script():
    # 1. Explicit env var
    p = Path(os.environ.get('TRANSCRIPT_SCRIPT', ''))
    if p.exists():
        return p
    # 2. youtube-transcript-api is a pip package — use it directly if installed
    try:
        import youtube_transcript_api
        return None  # signals: use youtube_transcript_api directly
    except ImportError:
        pass
    # 3. Sibling skill layouts
    candidates = [
        SKILL_DIR.parent.parent / "media" / "youtube-content" / "scripts" / "fetch_transcript.py",
        SKILL_DIR.parent / "youtube-content" / "scripts" / "fetch_transcript.py",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None

FETCH_TRANSCRIPT = _resolve_transcript_script()
TRANSCRIPT_API_AVAILABLE = False
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    pass

# ── Data Classes ───────────────────────────────────────────────────────
@dataclass
class VideoCandidate:
    title: str
    url: str
    duration: str
    uploader: str
    view_count: int
    published: str
    description: str
    provider: str = "YouTube"
    publisher: str = "YouTube"
    age_months: float = 0
    stale_months: int = 36
    aging_months: int = 24

@dataclass
class QualifiedVideo:
    candidate: VideoCandidate
    score: int
    reasoning: str
    freshness: str

@dataclass
class ReviewedVideo:
    qualified: QualifiedVideo
    relevance_score: int
    summary_bullets: list
    gaps: list
    audience_level: str
    watch_if: list
    skip_if: list
    transcript_quality: str
    transcript_status: str = "available"
    transcript_error: str = ""
    key_timestamps: list = None
    why_relevant: str = ""


# ── Helpers ────────────────────────────────────────────────────────────

STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on",
    "is", "are", "was", "were", "be", "been", "being", "have", "has",
    "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "must", "shall", "can", "need", "this", "that",
    "these", "those", "it", "its", "as", "at", "by", "with", "from",
    "about", "into", "how", "what", "which", "when", "where", "who",
    "best", "top", "videos", "video", "youtube", "find", "show",
}

def terms(text: str) -> set:
    """Extract meaningful terms from text, removing stopwords and punctuation."""
    raw = set(re.findall(r"[a-z0-9+#.-]+", text.lower()))
    return raw - STOPWORDS


def run_cmd(cmd: list, timeout: int = 30) -> tuple:
    """Run command, return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", f"command not found: {cmd[0]}"


def parse_duration_to_seconds(duration: str) -> int:
    """Parse 'HH:MM:SS' or 'MM:SS' to seconds."""
    try:
        parts = list(map(int, duration.split(":")))
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
    except (ValueError, AttributeError):
        pass
    return 0


def parse_iso_date(date_str: str) -> Optional[datetime]:
    """Parse ISO date string to datetime."""
    if not date_str:
        return None
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        if "." in date_str and "T" in date_str:
            base, frac = date_str.split(".", 1)
            frac = frac.rstrip("Z")
            frac = (frac + "000000")[:6]
            return datetime.strptime(f"{base}.{frac}", "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=timezone.utc)
    except:
        pass
    return None


def months_since(published: str) -> float:
    dt = parse_iso_date(published)
    if not dt:
        return 999
    now = datetime.now(timezone.utc)
    delta = now - dt
    return delta.days / 30.44


def load_fast_moving_domains() -> dict:
    path = REFERENCES_DIR / "fast_moving_domains.yaml"
    if not path.exists():
        return {"domains": [], "defaults": {"stale_months": 36, "aging_months": 24}}
    with open(path) as f:
        return yaml.safe_load(f)


def match_domain(query: str, domains_config: dict) -> Optional[dict]:
    query_lower = query.lower()
    best_match = None
    best_len = 0
    for domain in domains_config.get("domains", []):
        for kw in domain.get("keywords", []):
            if kw.lower() in query_lower and len(kw) > best_len:
                best_match = domain
                best_len = len(kw)
    return best_match


# ── Step 1: Search ────────────────────────────────────────────────────

def search_videos(query: str, max_results: int = 8, debug: bool = False) -> list:
    """Run ddgs videos search and parse JSON output."""
    print(f"🔍 Searching DDG videos for: '{query}'...", file=sys.stderr)

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp:
        tmp_path = tmp.name

    try:
        code, stdout, stderr = run_cmd(["ddgs", "videos", "-q", query, "-m", str(max_results), "-o", tmp_path])
        if code != 0:
            print(f"⚠️  DDG search failed (code {code}): {stderr}", file=sys.stderr)
            return []

        with open(tmp_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"⚠️  Failed to parse DDG JSON: {e}", file=sys.stderr)
        return []
    finally:
        try:
            os.unlink(tmp_path)
        except:
            pass

    # Debug: dump raw result shape when no YouTube candidates found
    if debug and data:
        print(f"\n[DEBUG] Raw DDG result[0] keys: {list(data[0].keys())}", file=sys.stderr)
        print(f"[DEBUG] Raw DDG result[0]: {json.dumps(data[0], indent=2)[:500]}", file=sys.stderr)

    candidates = []
    for item in data:
        publisher = item.get("publisher", "").lower()
        if "youtube" not in publisher:
            continue

        # View count: try multiple schema shapes
        view_count = 0
        stats = item.get("statistics", {})
        if isinstance(stats, dict):
            view_count = stats.get("viewCount", 0) or 0
        elif isinstance(stats, (int, str)):
            try:
                view_count = int(stats)
            except (ValueError, TypeError):
                pass
        # Some DDG results put views directly on the item
        if not view_count:
            view_count = item.get("viewCount", 0) or 0

        # URL: DDG uses "content" for the video URL
        url = item.get("content", "") or item.get("url", "")

        candidate = VideoCandidate(
            title=item.get("title", "Untitled"),
            url=url,
            duration=item.get("duration", "?"),
            uploader=item.get("uploader", "Unknown"),
            view_count=view_count,
            published=item.get("published", ""),
            description=item.get("description", ""),
            provider=item.get("provider", "YouTube"),
            publisher=item.get("publisher", "YouTube"),
        )
        candidates.append(candidate)

    if not candidates and debug and data:
        print(f"\n[DEBUG] Found {len(data)} results but 0 YouTube candidates.", file=sys.stderr)
        print(f"[DEBUG] Publishers found: {[item.get('publisher', 'N/A') for item in data[:5]]}", file=sys.stderr)

    print(f"✅ Found {len(candidates)} YouTube candidates", file=sys.stderr)
    return candidates


# ── Step 2: Qualify ─────────────────────────────────────────────────────

def load_prompt(path: Path) -> str:
    with open(path) as f:
        return f.read()


def qualify_videos(query: str, candidates: list, enable_freshness: bool) -> list:
    """Score candidates. Tries LLM first, falls back to heuristic."""
    if not candidates:
        return []

    print(f"🧠 Qualifying {len(candidates)} candidates...", file=sys.stderr)

    # Calculate ages and freshness thresholds
    domains_config = load_fast_moving_domains()
    matched_domain = match_domain(query, domains_config) if enable_freshness else None

    defaults = domains_config.get("defaults", {"stale_months": 36, "aging_months": 24})
    stale_months = matched_domain.get("stale_months", defaults["stale_months"]) if matched_domain else defaults["stale_months"]
    aging_months = matched_domain.get("aging_months", defaults["aging_months"]) if matched_domain else defaults["aging_months"]

    for c in candidates:
        c.age_months = months_since(c.published)
        c.stale_months = stale_months
        c.aging_months = aging_months

    # Try LLM qualification — render prompt with Jinja2
    prompt_template = load_prompt(REFERENCES_DIR / "qualify_prompt.md")

    # Build freshness_info as a dict for Jinja (or None)
    freshness_info_obj = None
    if matched_domain:
        matched_keywords = [kw for kw in matched_domain["keywords"] if kw.lower() in query.lower()]
        freshness_info_obj = {
            "domain": matched_domain.get("display_name", matched_domain.get("name", "Unknown")),
            "matched_keywords": matched_keywords,
            "stale_months": stale_months,
            "aging_months": aging_months,
        }

    # Render with Jinja2
    from jinja2 import Template
    template = Template(prompt_template)
    prompt = template.render(
        query=query,
        videos=[{
            "title": c.title,
            "url": c.url,
            "duration": c.duration,
            "uploader": c.uploader,
            "view_count": c.view_count,
            "published": c.published[:10] if c.published else "Unknown",
            "description": c.description or "",
            "age_months": f"{c.age_months:.1f}",
        } for c in candidates],
        freshness_info=freshness_info_obj,
    )

    llm_result = call_llm(prompt)
    if llm_result and "scores" in llm_result:
        return _parse_llm_qualification(candidates, llm_result)

    # Heuristic fallback
    print("  → Using heuristic scoring (no LLM available)", file=sys.stderr)
    return _heuristic_qualify(candidates, query, enable_freshness)


def _parse_llm_qualification(candidates: list, llm_result: dict) -> list:
    """Parse LLM JSON response into QualifiedVideo list."""
    results = []
    for score_entry in llm_result.get("scores", []):
        idx = score_entry.get("index", 0) - 1
        if 0 <= idx < len(candidates):
            c = candidates[idx]
            results.append(QualifiedVideo(
                candidate=c,
                score=score_entry.get("score", 50),
                reasoning=score_entry.get("reasoning", ""),
                freshness=score_entry.get("freshness", "fresh"),
            ))
    results.sort(key=lambda x: x.score, reverse=True)
    return results


def _heuristic_qualify(candidates: list, query: str, enable_freshness: bool) -> list:
    """Heuristic scoring when LLM not available."""
    results = []
    query_terms = terms(query)

    for i, c in enumerate(candidates):
        score = 50

        # Topic match: improved keyword overlap
        title_terms = terms(c.title)
        overlap = len(query_terms & title_terms)
        score += min(overlap * 8, 30)

        # Duration signal
        secs = parse_duration_to_seconds(c.duration)
        if 300 <= secs <= 3600:
            score += 15
        elif 180 <= secs <= 7200:
            score += 5

        # Authority: view count
        if c.view_count > 1_000_000:
            score += 15
        elif c.view_count > 100_000:
            score += 10
        elif c.view_count > 10_000:
            score += 5

        # Freshness
        if enable_freshness:
            if c.age_months <= c.aging_months:
                score += 15
            elif c.age_months <= c.stale_months:
                score += 5
            else:
                score -= 10

        score = max(0, min(100, score))

        if c.age_months <= c.aging_months:
            freshness = "fresh"
        elif c.age_months <= c.stale_months:
            freshness = "aging"
        else:
            freshness = "stale"

        results.append(QualifiedVideo(
            candidate=c,
            score=score,
            reasoning=f"Heuristic: topic_match={overlap}, duration={secs//60}min, views={c.view_count:,}, age={c.age_months:.1f}mo",
            freshness=freshness
        ))

    results.sort(key=lambda x: x.score, reverse=True)
    return results


# ── Step 3: Fetch Transcripts ──────────────────────────────────────────

def fetch_transcript(url: str) -> Optional[str]:
    """Fetch transcript for a YouTube video URL.

    Tries: 1) youtube_transcript_api directly, 2) external script, 3) returns None.
    Falls back to any available transcript language if English fails.
    """
    # Method 1: youtube_transcript_api directly
    if TRANSCRIPT_API_AVAILABLE:
        try:
            vid_match = re.search(r'(?:youtu\.be/|watch\?v=|embed/|v/)([\w-]{11})', url)
            if vid_match:
                video_id = vid_match.group(1)

                # Try preferred languages, then fall back to any available
                preferred_langs = ['en', 'en-US', 'en-GB']
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=preferred_langs)
                except Exception:
                    # Fallback: list available transcripts and pick first
                    try:
                        available = YouTubeTranscriptApi.list_transcripts(video_id)
                        first_transcript = next(iter(available))
                        transcript_list = first_transcript.fetch()
                        print(f"  → Fallback to {first_transcript.language} transcript", file=sys.stderr)
                    except Exception:
                        raise

                text = ' '.join(entry['text'] for entry in transcript_list)
                if len(text) > 100:
                    return text
        except Exception as e:
            print(f"⚠️  youtube_transcript_api failed for {url}: {e}", file=sys.stderr)

    # Method 2: external fetch_transcript.py script
    if FETCH_TRANSCRIPT and FETCH_TRANSCRIPT.exists():
        code, stdout, stderr = run_cmd([
            sys.executable, str(FETCH_TRANSCRIPT), url, "--text-only", "--timestamps"
        ], timeout=60)

        if code == 0 and stdout and len(stdout) > 100:
            return stdout

        print(f"⚠️  Transcript script failed for {url}: {stderr or 'empty'}", file=sys.stderr)
        return None

    print(f"⚠️  No transcript method available for {url}", file=sys.stderr)
    print(f"    Install: pip install youtube-transcript-api", file=sys.stderr)
    return None


def chunk_transcript(text: str, chunk_size: int = 40000, overlap: int = 2000) -> list:
    """Split long transcript into overlapping chunks."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks


# ── Step 4: Review Transcripts ─────────────────────────────────────────

def review_transcript(query: str, qualified: QualifiedVideo, transcript: str, chunk_size: int = 40000) -> ReviewedVideo:
    """Review transcript and produce summary. Tries LLM, falls back to heuristic.

    For long transcripts (>chunk_size), chunks are reviewed individually
    and merged — the full transcript is never passed to LLM in one call.
    """
    c = qualified.candidate

    # Clean transcript
    lines = transcript.split('\n')
    clean_lines = []
    for line in lines:
        if re.match(r'^\d{1,2}:\d{2}(:\d{2})?\s*$', line.strip()):
            continue
        if re.match(r'^\d{1,2}:\d{2}(:\d{2})?\s', line.strip()):
            line = re.sub(r'^\d{1,2}:\d{2}(:\d{2})?\s*', '', line)
        clean_lines.append(line)
    clean_transcript = ' '.join(clean_lines)

    # Chunk if needed
    chunks = chunk_transcript(clean_transcript, chunk_size)
    if len(chunks) > 1:
        print(f"  📝 Transcript split into {len(chunks)} chunks", file=sys.stderr)

    # Try LLM review — render prompt with Jinja2
    review_prompt_template = load_prompt(REFERENCES_DIR / "review_prompt.md")
    from jinja2 import Template
    review_template = Template(review_prompt_template)

    render_ctx = dict(
        query=query,
        title=c.title,
        url=c.url,
        duration=c.duration,
        uploader=c.uploader,
        published=c.published,
        view_count=c.view_count,
    )

    if len(chunks) == 1:
        prompt = review_template.render(
            transcript_length=len(clean_transcript),
            transcript=clean_transcript[:chunk_size],
            **render_ctx,
        )

        llm_result = call_llm(prompt)
        if llm_result and "relevance_score" in llm_result:
            return _parse_llm_review(qualified, llm_result, transcript_status="available")

    elif len(chunks) > 1:
        # Review each chunk and merge
        chunk_reviews = []
        for i, chunk in enumerate(chunks):
            prompt = review_template.render(
                transcript_length=len(chunk),
                transcript=chunk,
                **render_ctx,
            )

            llm_result = call_llm(prompt)
            if llm_result and "relevance_score" in llm_result:
                chunk_reviews.append(llm_result)

        if chunk_reviews:
            merged = _merge_chunk_reviews(chunk_reviews)
            return _parse_llm_review(qualified, merged, transcript_status="available")

    # Heuristic fallback
    print("  → Using heuristic review (no LLM available)", file=sys.stderr)
    return _heuristic_review(query, qualified, clean_transcript, transcript)


def _parse_llm_review(qualified: QualifiedVideo, llm_result: dict, transcript_status: str = "available") -> ReviewedVideo:
    """Parse LLM JSON response into ReviewedVideo."""
    return ReviewedVideo(
        qualified=qualified,
        relevance_score=llm_result.get("relevance_score", 50),
        summary_bullets=llm_result.get("summary_bullets", []),
        gaps=llm_result.get("gaps", []),
        audience_level=llm_result.get("audience_level", "intermediate"),
        watch_if=llm_result.get("watch_if", []),
        skip_if=llm_result.get("skip_if", []),
        transcript_quality=llm_result.get("transcript_quality", "good"),
        transcript_status=transcript_status,
        transcript_error="",
        key_timestamps=[],
        why_relevant=qualified.reasoning,
    )


def _merge_chunk_reviews(chunk_reviews: list) -> dict:
    """Merge multiple chunk review dicts into one."""
    # Average relevance scores
    avg_relevance = sum(r.get("relevance_score", 50) for r in chunk_reviews) // len(chunk_reviews)

    # Concatenate summaries, dedupe gaps
    all_summaries = []
    all_gaps = []
    for r in chunk_reviews:
        all_summaries.extend(r.get("summary_bullets", []))
        for g in r.get("gaps", []):
            if g not in all_gaps:
                all_gaps.append(g)

    # Best audience level (prefer more specific)
    levels = [r.get("audience_level", "intermediate") for r in chunk_reviews]
    audience = "beginner" if "beginner" in levels else ("advanced" if "advanced" in levels else "intermediate")

    # Merge watch/skip
    all_watch = []
    all_skip = []
    for r in chunk_reviews:
        for w in r.get("watch_if", []):
            if w not in all_watch:
                all_watch.append(w)
        for s in r.get("skip_if", []):
            if s not in all_skip:
                all_skip.append(s)

    return {
        "relevance_score": avg_relevance,
        "summary_bullets": all_summaries[:6],
        "gaps": all_gaps[:4],
        "audience_level": audience,
        "watch_if": all_watch[:3],
        "skip_if": all_skip[:3],
        "transcript_quality": "good",
    }


def _heuristic_review(query: str, qualified: QualifiedVideo, clean_transcript: str, raw_transcript: str) -> ReviewedVideo:
    """Heuristic review when LLM not available."""
    c = qualified.candidate

    # Extract substantive sentences
    sentences = re.split(r'[.!?]\s+', clean_transcript)
    substantive = [s.strip() for s in sentences if len(s.strip()) > 50 and not s.strip().startswith(('[Music]', 'Music', '>>>'))]

    summary_bullets = [s[:200] + ("..." if len(s) > 200 else "") for s in substantive[:4]] if substantive else ["Content summary unavailable - transcript may be timestamped"]

    # Keyword-based relevance with improved term extraction
    query_terms = terms(query)
    transcript_lower = clean_transcript.lower()
    term_hits = sum(1 for t in query_terms if t in transcript_lower)
    relevance = min(50 + term_hits * 10, 95)

    # Audience level
    audience = "intermediate"
    if any(w in transcript_lower for w in ["beginner", "basics", "introduction", "from scratch", "zero to"]):
        audience = "beginner"
    elif any(w in transcript_lower for w in ["advanced", "internals", "deep dive", "optimization", "performance"]):
        audience = "advanced"

    return ReviewedVideo(
        qualified=qualified,
        relevance_score=relevance,
        summary_bullets=summary_bullets,
        gaps=["Heuristic review — LLM review not available"],
        audience_level=audience,
        watch_if=[f"Relevance: {relevance}/100", f"Duration: {c.duration}"],
        skip_if=["Heuristic summary — may miss nuance"],
        transcript_quality="good" if len(raw_transcript) > 1000 else "fair",
        transcript_status="available",
        transcript_error="",
        key_timestamps=[],
        why_relevant=qualified.reasoning,
    )


# ── Step 5: Format Output ──────────────────────────────────────────────

def format_output(query: str, results: list, raw_candidates: list, issues: list, format_type: str = "md") -> str:
    """Render output."""
    if format_type == "json":
        return json.dumps({
            "query": query,
            "results": [
                {
                    "title": r.qualified.candidate.title,
                    "url": r.qualified.candidate.url,
                    "duration": r.qualified.candidate.duration,
                    "uploader": r.qualified.candidate.uploader,
                    "views": r.qualified.candidate.view_count,
                    "published": r.qualified.candidate.published,
                    "age_months": r.qualified.candidate.age_months,
                    "freshness": r.qualified.freshness,
                    "relevance_score": r.relevance_score,
                    "summary": r.summary_bullets,
                    "gaps": r.gaps,
                    "audience_level": r.audience_level,
                    "watch_if": r.watch_if,
                    "skip_if": r.skip_if,
                    "why_relevant": r.why_relevant,
                    "transcript_status": r.transcript_status,
                }
                for r in results
            ],
            "issues": issues,
            "raw_count": len(raw_candidates)
        }, indent=2)

    # Markdown via Jinja2
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    template = env.get_template("output.md.j2")

    template_results = []
    for r in results:
        c = r.qualified.candidate
        template_results.append({
            "title": c.title,
            "url": c.url,
            "duration": c.duration,
            "uploader": c.uploader,
            "view_count": c.view_count,
            "published": c.published,
            "age_months": c.age_months,
            "stale_months": c.stale_months,
            "aging_months": c.aging_months,
            "why_relevant": r.why_relevant,
            "summary_bullets": r.summary_bullets,
            "watch_if": r.watch_if,
            "skip_if": r.skip_if,
            "transcript_status": r.transcript_status or "available",
            "transcript_error": r.transcript_error or "",
            "key_timestamps": r.key_timestamps or [],
        })

    return template.render(
        query=query,
        results=template_results,
        raw_count=len(raw_candidates),
        issues=issues,
        raw_videos=raw_candidates
    )


# ── Feeder Mode: Export to notebooklm-mode vault ────────────────────────────

VISUAL_KEYWORDS = {
    "demo", "walkthrough", "tutorial", "live coding", "screen recording",
    "dashboard", "ui", "diagram", "visual", "hands-on", "practical",
    "crash course", "step by step", "from scratch", "build",
}


def _detect_visual_value(candidate: VideoCandidate, transcript: str) -> list:
    """Detect likely visual/demo value from metadata + transcript."""
    visual_hits = []
    combined = (candidate.title + " " + candidate.description + " " + transcript[:5000]).lower()
    for kw in VISUAL_KEYWORDS:
        if kw in combined:
            visual_hits.append(kw)
    if not visual_hits:
        return ["Topic may benefit from visual explanation, but no explicit demo/walkthrough signals detected in metadata."]
    return [f"Likely contains: {', '.join(visual_hits)}"]


def _extract_transcript_quotes(transcript: str, query: str, max_quotes: int = 5) -> list:
    """Extract relevant transcript quotes with approximate timestamps."""
    lines = transcript.split('\n')
    quotes = []
    query_terms_set = terms(query)

    current_ts = ""
    current_text = []

    for line in lines:
        ts_match = re.match(r'^(\d{1,2}:\d{2}(?::\d{2})?)\s*(.*)', line.strip())
        if ts_match:
            if current_text and current_ts:
                full_text = ' '.join(current_text)
                text_lower = full_text.lower()
                if any(t in text_lower for t in query_terms_set) and len(full_text) > 30:
                    quotes.append({
                        'text': full_text[:300] + ("..." if len(full_text) > 300 else ""),
                        'timestamp': current_ts,
                    })
                    if len(quotes) >= max_quotes:
                        return quotes
            current_ts = ts_match.group(1)
            current_text = [ts_match.group(2)] if ts_match.group(2) else []
        else:
            if current_ts:
                current_text.append(line.strip())

    # Last segment
    if current_text and current_ts:
        full_text = ' '.join(current_text)
        text_lower = full_text.lower()
        if any(t in text_lower for t in query_terms_set) and len(full_text) > 30:
            quotes.append({
                'text': full_text[:300] + ("..." if len(full_text) > 300 else ""),
                'timestamp': current_ts,
            })

    return quotes


def _md_cell(value) -> str:
    """Escape markdown table cell: escape pipes, collapse newlines."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _next_source_num(sources_dir: Path) -> int:
    """Find the next sequential source number by scanning existing files."""
    nums = []
    for f in sources_dir.glob("[0-9][0-9][0-9]_*.md"):
        try:
            nums.append(int(f.name[:3]))
        except ValueError:
            pass
    return max(nums, default=0) + 1


def _update_vault_index(vault_path: Path, query: str, saved_files: list, results: list):
    """Append source entries to vault_index.md, creating it if absent."""
    vault_index = vault_path / "vault_index.md"
    today = datetime.now().strftime('%Y-%m-%d')

    # Build new source rows
    new_rows = []
    for i, (fpath, r) in enumerate(zip(saved_files, results)):
        c = r.qualified.candidate
        fname = Path(fpath).name
        title = _md_cell(f"YouTube: {c.title}")
        new_rows.append(f"| {fname[:3]} | {fname} | youtube | {title} | {today} |")

    if vault_index.exists():
        # Append to existing
        content = vault_index.read_text(encoding='utf-8')
        # Find the Sources table and append rows
        lines = content.split('\n')
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('|') and '---' in line and i > 0 and 'Retrieved' in lines[i-1]:
                # Found the separator line after Sources header — append after last table row
                j = i + 1
                while j < len(lines) and lines[j].startswith('|'):
                    j += 1
                # Insert new rows before the first non-table line
                for row in new_rows:
                    lines.insert(j, row)
                    j += 1
                updated = True
                break
        if updated:
            # Update source count in header: **Sources:** N
            new_content = '\n'.join(lines)
            # Recalculate total sources by counting data rows in Sources table
            source_count = 0
            counting = False
            for line in new_content.split('\n'):
                if line.startswith('|') and 'Retrieved' in line:
                    counting = True
                    continue
                if counting and line.startswith('|') and '---' in line:
                    continue
                if counting and line.startswith('|'):
                    source_count += 1
                elif counting and not line.startswith('|'):
                    counting = False
            new_content = re.sub(r'\*\*Sources:\*\* \d+', f'**Sources:** {source_count}', new_content)
            vault_index.write_text(new_content, encoding='utf-8')
        else:
            # Couldn't find table — append at end
            vault_index.write_text(content + '\n' + '\n'.join(new_rows) + '\n', encoding='utf-8')
    else:
        # Create new vault_index.md
        content = f"""# Workspace Vault Index
**Topic:** {query} | **Created:** {today} | **Sources:** {len(saved_files)} | **Mode:** strict

## Sources
| # | File | Type | Title | Retrieved |
|---|------|------|-------|-----------|
"""
        for row in new_rows:
            content += row + '\n'
        content += """
## Coverage Notes
- Well covered: [pending] | Gaps: [pending]

## Outputs
| File | Type | Created |
|------|------|---------|
"""
        vault_index.write_text(content, encoding='utf-8')


def export_to_vault(query: str, results: list, vault_path: str, raw_transcripts: dict = None) -> list:
    """Export reviewed videos as notebooklm-mode source files.

    Args:
        query: The original search query
        results: List of ReviewedVideo objects
        vault_path: Path to the notebooklm-mode vault
        raw_transcripts: Dict mapping URL → raw transcript text (optional)

    Returns:
        List of saved file paths
    """
    vault = Path(vault_path)
    sources_dir = vault / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    next_num = _next_source_num(sources_dir)

    saved_files = []
    raw_transcripts = raw_transcripts or {}

    for r in results:
        c = r.qualified.candidate
        slug = re.sub(r'[^a-z0-9]+', '-', c.title.lower()).strip('-')[:40]
        filename = f"{next_num:03d}_youtube_{slug}.md"
        next_num += 1

        # Extract transcript quotes if we have the raw transcript
        transcript = raw_transcripts.get(c.url, "")
        quotes = _extract_transcript_quotes(transcript, query) if transcript else []

        # Detect visual value
        visual_notes = _detect_visual_value(c, transcript) if transcript else _detect_visual_value(c, "")

        # Build freshness label
        if c.age_months <= c.aging_months:
            freshness = "fresh"
        elif c.age_months <= c.stale_months:
            freshness = "aging"
        else:
            freshness = "stale"

        # Format views
        if c.view_count >= 1_000_000:
            views_str = f"{c.view_count / 1_000_000:.1f}M"
        elif c.view_count >= 1_000:
            views_str = f"{c.view_count / 1_000:.1f}K"
        else:
            views_str = str(c.view_count)

        # Build source file with escaped table cells
        content = f"""# YouTube Source: {c.title}

| Field | Value |
|------|-------|
| URL | {_md_cell(c.url)} |
| Uploader | {_md_cell(c.uploader)} |
| Published | {c.published[:10] if c.published else 'Unknown'} |
| Duration | {_md_cell(c.duration)} |
| Views | {views_str} |
| Retrieved | {datetime.now().strftime('%Y-%m-%d')} |
| Type | youtube |
| Transcript Quality | {_md_cell(r.transcript_quality)} |
| Freshness | {freshness} |

## Why Selected

{r.why_relevant or 'Selected based on heuristic scoring of topic match, authority, duration, and freshness.'}

## Visual / Demo Value

"""
        for note in visual_notes:
            content += f"- {_md_cell(note)}\n"

        content += "\n## Transcript Extracts\n\n"
        if quotes:
            for q in quotes:
                content += f'> "{_md_cell(q["text"])}"\n> — approx. timestamp: {q["timestamp"]}\n\n'
        else:
            content += "> [No timestamped transcript quotes extracted — transcript may lack timestamp markers]\n\n"

        content += "## Summary\n\n"
        for bullet in r.summary_bullets:
            content += f"- {_md_cell(bullet)}\n"

        content += "\n## Gaps\n\n"
        for gap in r.gaps:
            content += f"- {_md_cell(gap)}\n"

        file_path = sources_dir / filename
        file_path.write_text(content, encoding='utf-8')
        saved_files.append(str(file_path))
        print(f"  ✅ Saved: {filename}", file=sys.stderr)

    # Update vault_index.md
    _update_vault_index(vault, query, saved_files, results)
    print(f"  📋 Updated vault_index.md", file=sys.stderr)

    return saved_files


# ── Main Orchestrator ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="YouTube Topic Research — find & summarize videos")
    parser.add_argument("query", help="Search topic")
    parser.add_argument("--top", type=int, default=2, help="Final results to return (default: 2)")
    parser.add_argument("--max-candidates", type=int, default=8, help="Initial DDG results (default: 8)")
    parser.add_argument("--qualify-top", type=int, default=4, help="Top candidates to qualify (default: 4)")
    parser.add_argument("--transcript-top", type=int, default=3, help="Top qualified to fetch transcripts (default: 3)")
    parser.add_argument("--min-transcript", type=int, default=500, help="Min transcript chars (default: 500)")
    parser.add_argument("--chunk-size", type=int, default=40000, help="Transcript chunk size (default: 40000)")
    parser.add_argument("--no-freshness", action="store_true", help="Disable freshness flags")
    parser.add_argument("--format", choices=["md", "json"], default="md", help="Output format")
    parser.add_argument("--debug", action="store_true", help="Verbose debug output (dumps raw DDG results)")
    parser.add_argument("--export-vault", type=str, default=None, metavar="PATH",
                        help="Export selected videos as notebooklm-mode source files into the given vault path")

    args = parser.parse_args()

    enable_freshness = not args.no_freshness
    issues = []

    # 1. Search
    candidates = search_videos(args.query, args.max_candidates, debug=args.debug)
    if not candidates:
        issues.append("No YouTube videos found in DDG results")
        print(format_output(args.query, [], candidates, issues, args.format))
        return

    # 2. Qualify
    qualified = qualify_videos(args.query, candidates, enable_freshness)
    qualified = qualified[:args.qualify_top]

    # 3. Fetch transcripts and review
    reviewed = []
    raw_transcripts = {}  # URL → raw transcript, for feeder mode
    for qv in qualified[:args.transcript_top]:
        print(f"📥 Fetching transcript: {qv.candidate.title[:60]}...", file=sys.stderr)
        transcript = fetch_transcript(qv.candidate.url)

        if transcript and len(transcript) >= args.min_transcript:
            raw_transcripts[qv.candidate.url] = transcript
            rv = review_transcript(args.query, qv, transcript, args.chunk_size)
            reviewed.append(rv)
        else:
            issues.append(f"Transcript unavailable/insufficient: {qv.candidate.title[:50]}")

    # Sort reviewed by relevance
    reviewed.sort(key=lambda x: x.relevance_score, reverse=True)

    # 4. Output top results
    final_results = reviewed[:args.top]

    if not final_results:
        issues.append("No videos passed transcript + relevance threshold")

    # 5a. Feeder mode: export to vault
    if args.export_vault:
        if not final_results:
            print("No reviewed videos to export.", file=sys.stderr)
            print(format_output(args.query, final_results, candidates, issues, args.format))
            return

        print(f"\n📦 Exporting {len(final_results)} videos to vault: {args.export_vault}", file=sys.stderr)
        saved = export_to_vault(args.query, final_results, args.export_vault, raw_transcripts)
        print(f"\n✅ Exported {len(saved)} source files to {args.export_vault}/sources/", file=sys.stderr)
        for f in saved:
            print(f"   {f}", file=sys.stderr)

        # If JSON format, include exported files in the JSON output
        if args.format == "json":
            import json as _json
            output_json = _json.loads(format_output(args.query, final_results, candidates, issues, args.format))
            output_json["exported_files"] = saved
            print(_json.dumps(output_json, indent=2))
        else:
            print(format_output(args.query, final_results, candidates, issues, args.format))
        return

    # 5b. Standalone mode: print output
    output = format_output(args.query, final_results, candidates, issues, args.format)
    print(output)


if __name__ == "__main__":
    main()