# Debugging Patterns for youtube-topic-research

## DDG CLI Quirks

### `ddgs videos -o -` doesn't work
The `ddgs` CLI doesn't reliably output to stdout with `-o -`. Always use a temp file:
```python
with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as tmp:
    tmp_path = tmp.name
code, stdout, stderr = run_cmd(["ddgs", "videos", "-q", query, "-m", str(max_results), "-o", tmp_path])
with open(tmp_path) as f:
    data = json.load(f)
os.unlink(tmp_path)
```

### DDG date formats
DDG returns ISO dates with variable fractional seconds:
- `2025-08-20T21:19:31` (no fraction)
- `2025-08-20T21:19:31.123` (3 digits)
- `2025-08-20T21:19:31.123456` (6 digits - standard)
- `2025-08-20T21:19:31.0000000` (7 digits)

**Use `dateutil.parser.isoparse()`** - handles all variants.

## Transcript Cleaning (for heuristic fallback)

When transcript has timestamps embedded (from fetch_transcript.py --timestamps):
```python
import re
lines = transcript.split('\n')
clean_lines = []
for line in lines:
    # Skip timestamp-only lines
    if re.match(r'^\d{1,2}:\d{2}(:\d{2})?\s*$', line.strip()):
        continue
    # Skip lines starting with timestamp
    if re.match(r'^\d{1,2}:\d{2}(:\d{2})?\s', line.strip()):
        line = re.sub(r'^\d{1,2}:\d{2}(:\d{2})?\s*', '', line)
    clean_lines.append(line)
clean_transcript = ' '.join(clean_lines)
```

## VTT Parsing (for yt-dlp fallback)

YouTube timedtext returns VTT format. Key patterns:
```vtt
WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:03.400
Welcome to this tutorial on Python async

00:00:03.400 --> 00:00:05.200
<c>Today we'll cover</c> async and await
```

Parse to entries compatible with youtube_transcript_api format:
```python
def parse_vtt_to_entries(vtt: str) -> list[dict]:
    entries = []
    current_start = 0
    current_text = []
    for line in vtt.strip().split('\n'):
        line = line.strip()
        if not line or line == 'WEBVTT' or line.startswith(('Kind:', 'Language:')):
            continue
        ts_match = re.match(r'^(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})', line)
        if ts_match:
            if current_text:
                entries.append({'start': current_start, 'duration': 0, 'text': ' '.join(current_text)})
            h, m, s = ts_match.group(1).split(':')
            current_start = int(h) * 3600 + int(m) * 60 + float(s)
            current_text = []
        else:
            # Clean VTT tags: <c>, <00:00:00.000>, {styles}
            clean = re.sub(r'<\d{2}:\d{2}:\d{2}\.\d{3}>', '', line)
            clean = re.sub(r'<[^>]+>', '', clean)
            clean = re.sub(r'\{[^}]+\}', '', clean)
            if clean:
                current_text.append(clean)
    if current_text:
        entries.append({'start': current_start, 'duration': 0, 'text': ' '.join(current_text)})
    return entries
```

## Heuristic Fallback for Qualification/Review

When LLM not available, use keyword-based scoring:
```python
query_terms = set(query.lower().split())
title_words = set(candidate.title.lower().split())
overlap = len(query_terms & title_words)
score = 50 + min(overlap * 8, 30)  # topic match
```

Relevance from transcript:
```python
term_hits = sum(1 for t in query_terms if t in transcript_lower)
relevance = min(50 + term_hits * 10, 95)
```

Audience level detection:
```python
if any(w in transcript_lower for w in ['beginner', 'basics', 'introduction', 'from scratch', 'zero to']):
    audience = 'beginner'
elif any(w in transcript_lower for w in ['advanced', 'internals', 'deep dive', 'optimization', 'performance']):
    audience = 'advanced'
else:
    audience = 'intermediate'
```

## Common Test Commands

```bash
# Basic test
python scripts/search_and_summarize.py "python async tutorial" --top 1

# Disable freshness (evergreen topics)
python scripts/search_and_summarize.py "linux basics" --no-freshness --top 2

# JSON output for inspection
python scripts/search_and_summarize.py "rust ownership" --format json

# Require longer transcripts (drop thin/short videos)
python scripts/search_and_summarize.py "python async" --min-transcript 1500 --top 2

# Widen the candidate pool and qualify more before fetching transcripts
python scripts/search_and_summarize.py "python" --max-candidates 40 --qualify-top 12 --transcript-top 5

# Export results into a notebooklm-mode vault
python scripts/search_and_summarize.py "topic" --export-vault /path/to/vault
```

> The script's actual flags are `--top`, `--max-candidates`, `--qualify-top`,
> `--transcript-top`, `--min-transcript`, `--chunk-size`, `--no-freshness`,
> `--format {md,json}`, `--debug`, and `--export-vault`. There are no
> date/duration/channel/CSV filter flags — run `--help` to confirm.