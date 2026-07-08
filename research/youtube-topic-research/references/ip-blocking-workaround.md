# YouTube IP Blocking Workarounds

## The Problem

YouTube blocks requests from known cloud provider IP ranges (AWS, GCP, Azure, DigitalOcean, Linode, etc.). This affects:
- `youtube_transcript_api` direct calls
- `yt-dlp` timedtext endpoint fetches
- Direct requests to `www.youtube.com/api/timedtext`

**Error signatures:**
- `youtube_transcript_api`: `TranscriptsDisabled`, `NoTranscriptFound`, or generic `IpBlocked`
- `yt-dlp`: 429 Too Many Requests on timedtext URL, or "Unable to extract" errors
- Direct HTTP: 403/429 responses

## Workarounds (Ranked by Practicality)

### 1. Run on Residential IP (Best Success Rate) ✅
**Use your local machine or a residential proxy.**

```bash
# On your laptop/desktop (residential IP)
git clone <skill-repo>
cd youtube-topic-research
pip install ddgs "youtube-transcript-api<1.0" jinja2 pyyaml
python scripts/search_and_summarize.py "your topic" --top 2
```

### 2. Residential Proxy (Bright Data, Oxylabs, Smartproxy, etc.) ✅
Set `YOUTUBE_PROXY` environment variable:

```bash
export YOUTUBE_PROXY="http://user:pass@proxy-host:port"
python scripts/search_and_summarize.py "topic"
```

```python
# In fetch_transcript(), use proxy with httpx client
import os, httpx
from youtube_transcript_api import YouTubeTranscriptApi

proxy = os.environ.get("YOUTUBE_PROXY")
if proxy:
    client = httpx.Client(proxy=proxy)
    YouTubeTranscriptApi.http_client = client
```

### 3. yt-dlp with Browser Cookies (Good for Authenticated Access) ✅
```bash
# Extract cookies from Chrome/Firefox
yt-dlp --cookies-from-browser chrome --skip-download --write-auto-sub --sub-lang en "https://youtube.com/watch?v=VIDEO_ID"

# In Python
ydl_opts = {
    'cookies_from_browser': ('chrome',),  # or 'firefox', 'safari', 'edge'
    'writesubtitles': True,
    'writeautomaticsub': True,
    'subtitleslangs': ['en'],
}
```

**Note:** Requires browser installed and logged into YouTube.

### 4. Self-Hosted Invidious Instance + Proxy ✅
Run Invidious on a VPS with residential proxy:
- More complex setup
- Full control over instance
- Public instances exist but churn constantly and are often down/rate-limited —
  pick a live one from the official list at https://docs.invidious.io/instances/

```python
# Invidious captions endpoint (substitute a live instance)
import requests
r = requests.get(f"https://<invidious-instance>/api/v1/captions/{video_id}?format=json")
```

### 5. YouTube Data API v3 (Limited) ⚠️
**Only works for manually uploaded captions (not auto-generated).**
- Requires OAuth 2.0 (not just API key)
- Quota: 10,000 units/day
- `captions.list` + `captions.download` endpoints
- Most tutorial videos use auto-captions → won't work

### 6. Piped/Alternate Frontend Instances ⚠️
- Same IP blocking issue typically
- Unreliable for programmatic access

## Skill Integration

`search_and_summarize.py` fetches transcripts via `youtube_transcript_api`
(`fetch_transcript()`), and, if present, falls back to an external
`fetch_transcript.py` helper resolved from a sibling `youtube-content/scripts/`
directory. **The script has no built-in yt-dlp fallback and no `YOUTUBE_PROXY`
support** — the workarounds below are applied at the environment level (run from
a residential IP, route the whole process through a proxy/VPN, or point the
optional external helper at a proxy-aware fetcher), not via a flag.

If you want an automatic in-process fallback (yt-dlp or proxy-aware HTTP), it
has to be added to the transcript-fetch path first — it is not implemented
today.

## Testing IP Blocking

```bash
# Quick test - should return WEBVTT if working
curl -s "https://www.youtube.com/api/timedtext?v=6bHDQtVfsCM&lang=en&fmt=vtt" | head -5

# Test yt-dlp directly
yt-dlp --skip-download --write-auto-sub --sub-lang en --sub-format vtt "https://youtube.com/watch?v=6bHDQtVfsCM" -o /dev/null 2>&1 | head -20
```

## Recommendation for This Setup

**Run the skill on your local machine** (Mac/PC with a residential IP) for full transcript access. A cloud/datacenter VM is best reserved for:
- Scheduling/cron jobs
- Telegram/Webhook gateway
- API server
- Tasks NOT requiring YouTube transcripts

Run searches from a machine with a residential IP when you need transcript access, and keep transcript-free tasks on the VM.