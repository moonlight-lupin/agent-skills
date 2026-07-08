---
name: youtube-topic-research
description: >
  Find and summarize YouTube videos for topics where visual explanation,
  demos, tutorials, talks, walkthroughs, or screen recordings are useful.
  Can run standalone, or export transcript-backed video source notes into
  notebooklm-mode vaults for grounded research.
version: 2.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
---

# YouTube Topic Research Skill

## When to Use

Use when the user wants to **find and summarize YouTube videos on a specific
topic** — not when they already have a URL (use a transcript extraction skill
for that). This skill searches, filters, fetches transcripts, and returns the
top relevant videos with summaries.

**Examples:**
- "Find YouTube videos on Python async programming"
- "Show me recent videos about LLM fine-tuning"
- "What are the best tutorials for React Server Components?"
- "Research this topic through YouTube, then build a vault" → feeder mode

## Two Modes

### Standalone mode (default)

Search YouTube, fetch transcripts, rank videos, and return the top
recommendations with summaries, freshness indicators, and watch/skip guidance.

### NotebookLM feeder mode

After the user approves videos, save each selected video as a source file
compatible with `notebooklm-mode`, including metadata, URL, transcript
extracts, visual/demo notes, summary, and freshness status.

**Trigger phrases for feeder mode:**
- "add these to notebooklm"
- "make a source vault from these videos"
- "research this through YouTube first, then build a vault"
- "use videos as sources"

```bash
# Feeder mode — export selected videos as notebooklm-mode source files
python scripts/search_and_summarize.py "docker networking" --export-vault /path/to/vault
```

This generates source files in `sources/` inside the vault, formatted for
`notebooklm-mode` ingestion. The agent can then run `notebooklm-mode` for
grounded Q&A, notes, reports, or slides built on the video sources.

### Architecture

```
youtube-topic-research
        │
        ├── standalone recommendation output (default)
        │
        └── --export-vault: selected videos as source files
                    │
                    ▼
             notebooklm-mode vault
                    │
                    ▼
          grounded Q&A / notes / reports / slides
```

## Relationship to notebooklm-mode

This skill can be used standalone or as a feeder into `notebooklm-mode`:

| Use case | Mode |
|----------|------|
| "Find me good YouTube tutorials on Docker networking" | Standalone |
| "Find recent visual demos of Godot 4 agent workflows" | Standalone |
| "Research this topic using YouTube and save sources" | Feeder → notebooklm-mode |
| "Build me a grounded brief from videos and articles" | youtube-topic-research + notebooklm-mode |
| "Summarize this one YouTube URL" | Separate transcript extraction skill |

Most users asking for videos just want recommendations. Feeder mode is for
real research — when video sources should ground further Q&A and deliverables.

## Prerequisites

```bash
pip install ddgs "youtube-transcript-api<1.0" jinja2 pyyaml
```

The `ddgs` CLI (DuckDuckGo search) is the primary search backend.
`youtube-transcript-api` is used for transcript fetching. **Pin to `<1.0`:**
the script uses the `get_transcript()` / `list_transcripts()` static-method
API, which was removed in `youtube-transcript-api` 1.0 (renamed to instance
methods `.fetch()` / `.list()`). An unpinned install pulls 1.x and transcript
fetching silently returns nothing.

## Quick Start

```bash
# Standalone — returns top 2 videos with summaries
python scripts/search_and_summarize.py "python async tutorial"

# Custom top-k
python scripts/search_and_summarize.py "LLM fine-tuning 2024" --top 3

# Disable freshness flags (for evergreen topics)
python scripts/search_and_summarize.py "linux basics" --no-freshness

# JSON output for programmatic use
python scripts/search_and_summarize.py "rust ownership" --format json

# Feeder mode — export to a notebooklm-mode vault
python scripts/search_and_summarize.py "docker networking" --export-vault /path/to/vault
```

## Pipeline

```
User Query
    │
    ▼
┌─────────────────────────────────────┐
│ 1. SEARCH (ddgs videos)             │
│    -q "query" -m 8 -o json           │
│    Filter: publisher == "YouTube"   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 2. QUALIFY (heuristic or LLM)       │
│    Score 0-100 per candidate        │
│    Criteria: topic_match, authority,│
│    duration_signal, freshness       │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 3. FETCH TRANSCRIPTS (top 3-4)      │
│    youtube_transcript_api direct    │
│    OR external fetch_transcript.py  │
│    Health check: len > 500 chars    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 4. REVIEW (heuristic or LLM)        │
│    Relevance score + summary bullets│
│    Chunk if > 40K chars             │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 5. FORMAT & OUTPUT                  │
│    Standalone: output.md.j2         │
│    Feeder: notebooklm source files   │
└─────────────────────────────────────┘
```

### LLM Integration

Steps 2 and 4 have LLM prompt templates (`references/qualify_prompt.md` and
`references/review_prompt.md`). The script uses heuristic scoring by default.
To enable LLM qualification/review, an agent runtime overrides `call_llm()`:

```python
import search_and_summarize

def my_llm_call(prompt: str) -> dict | None:
    # Call your LLM API (OpenAI, Ollama, Hermes, etc.)
    # Must return a parsed JSON dict matching the prompt's output schema
    response = my_llm_api.chat(prompt)
    return json.loads(response)

search_and_summarize.LLM_CALL = my_llm_call
```

When `call_llm()` returns a valid JSON dict, the script uses LLM scoring. When
it returns `None`, the script falls back to heuristic scoring. The heuristic
uses keyword overlap (with stopwords removed), view count, duration, and age.

For long transcripts (>40K chars), the script chunks the transcript and reviews
each chunk individually via LLM, then merges the results.

### Visual Analysis Caveat

This skill can identify likely visual/demo-rich videos from metadata, titles,
descriptions, and transcripts, but **unless the runtime supports frame/image
inspection, it does not truly inspect the video visuals**. Transcript-grounded
summary is not the same as visual analysis. The skill flags videos that likely
contain demos, walkthroughs, or visual explanations based on title/description
keywords, but cannot confirm what the viewer will actually see on screen.

## Feeder Mode Source File Format

When `--export-vault` is used, each video is saved as a source file compatible
with `notebooklm-mode`:

```markdown
# YouTube Source: [Video Title]

| Field | Value |
|------|-------|
| URL | https://youtube.com/watch?v=... |
| Uploader | Channel Name |
| Published | YYYY-MM-DD |
| Duration | 18:42 |
| Views | 1.2M |
| Retrieved | YYYY-MM-DD |
| Type | youtube |
| Transcript Quality | good |
| Freshness | fresh |

## Why Selected

[Short reason based on query fit, authority, freshness, and transcript relevance.]

## Visual / Demo Value

- Shows live coding / dashboard / product walkthrough / diagrams / UI demo.
- Useful because this topic benefits from visual explanation.

## Transcript Extracts

> "Relevant transcript quote..."
> — approx. timestamp: 04:12

> "Another relevant quote..."
> — approx. timestamp: 09:45

## Summary

- Key point 1
- Key point 2
- Key point 3

## Gaps

- Does not cover X
- Assumes Y
```

## Configuration

### Fast-Moving Domains (`references/fast_moving_domains.yaml`)

Defines freshness thresholds for topics where recent content matters more:

```yaml
domains:
  - name: ai_ml
    keywords: ["ai", "llm", "fine-tuning", "gpt", "claude", ...]
    stale_months: 12
    aging_months: 6
  # ... web_frameworks, cloud_devops, programming_languages, databases
```

Unmatched topics use defaults (stale > 36mo, aging > 24mo).

### Defaults

| Parameter | Default | Override |
|-----------|---------|----------|
| `max_candidates` | 8 | `--max-candidates` |
| `qualify_top_k` | 4 | `--qualify-top` |
| `transcript_top_k` | 3 | `--transcript-top` |
| `final_top_k` | 2 | `--top` |
| `min_transcript_chars` | 500 | `--min-transcript` |
| `chunk_size` | 40000 | `--chunk-size` |
| `enable_freshness` | true | `--no-freshness` |

## Error Handling

| Failure Point | Behavior |
|---------------|----------|
| `ddgs` not installed | Exit with install instruction |
| `ddgs videos` returns empty | Retry once with broader query; report if still empty |
| No YouTube results in DDG | Report "no YouTube videos found for query" |
| All transcripts fail/disabled | Return raw DDG list + "could not fetch transcripts" |
| LLM qualification fails | Fallback: heuristic scoring |
| Transcript > chunk_size | Auto-chunk with 2K overlap, review each, merge |
| Output formatting fails | Fallback to plain text summary |
| IP blocked (cloud VM) | See `references/ip-blocking-workaround.md` |

## Limitations

- **No YouTube API** — relies on DuckDuckGo video index (may miss very new/unindexed videos)
- **Transcript availability** ~50-70% of videos; auto-captions may have errors
- **Rate limits** — DDG may throttle rapid requests; skill adds 1-2s delay between calls
- **Token cost** — Full transcript review via LLM uses ~5-15K tokens per video
- **Language** — Prefers English; falls back to any available transcript
- **IP blocking** — Cloud provider IPs may be blocked by YouTube; see workaround reference
- **No visual inspection** — identifies likely visual/demo videos from metadata, not frame analysis

## Extending

- Add domains to `references/fast_moving_domains.yaml`
- Customize `references/qualify_prompt.md` / `references/review_prompt.md`
- Modify `templates/output.md.j2` for different output formats (Discord, Slack)
- Set `TRANSCRIPT_SCRIPT` env var to point at an alternative transcript fetcher
- Override `call_llm()` for LLM-driven qualification and review

### Files

```text
youtube-topic-research/
├── SKILL.md                      # This file
├── scripts/
│   └── search_and_summarize.py   # Main entry point
├── references/
│   ├── qualify_prompt.md         # LLM prompt for metadata qualification
│   ├── review_prompt.md          # LLM prompt for transcript review
│   ├── fast_moving_domains.yaml  # Freshness thresholds by domain
│   ├── debugging-patterns.md     # DDG CLI quirks, date parsing, transcript cleaning
│   └── ip-blocking-workaround.md # YouTube IP blocking workarounds (cloud VMs)
└── templates/
    └── output.md.j2              # Jinja2 template for standalone output
```