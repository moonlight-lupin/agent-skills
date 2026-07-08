# Self-Hosting & Homelab — Digest Configuration

## Topic Definition

Self-hosting, homelab setups, and open-source infrastructure tools. Objective: **learning** — keeping up with new tools, projects, and techniques for personal homelab and automation.

## Search Methods

### Primary: SearXNG Discovery Searches

```bash
# Self-hosting tools & projects
curl -sL "$SEARXNG_URL/search?q=self+hosted+tool+project+release+2025&format=json&categories=news&language=en&time_range=month"

# Homelab setups & guides
curl -sL "$SEARXNG_URL/search?q=homelab+home+server+setup+guide+2025&format=json&categories=news&language=en&time_range=month"

# Open source alternatives & infrastructure
curl -sL "$SEARXNG_URL/search?q=open+source+self+hosted+alternative+new+2025&format=json&categories=news&language=en&time_range=month"
```

### Must-Track RSS Sources (Always Include)

These 3 sites consistently produce high-quality self-hosting content:

```bash
curl -sL "https://selfh.st/rss/"
curl -sL "https://mariushosting.com/feed/"
curl -sL "https://noted.lol/rss/"
```

### Fallback: DDGS

If SearXNG is down:
```bash
ddgs news -q "self-hosted homelab new tool 2025" -m 15 -o json
```

Or via Python:
```python
from ddgs import DDGS
import json
with DDGS() as d:
    results = list(d.news('self-hosted homelab new tool', region='wt-t', max_results=15))
    print(json.dumps(results, ensure_ascii=False))
```

## Source Priority

### Must-Include (from RSS):
- selfh.st — high-signal curated self-hosting articles
- mariushosting.com — tutorials, setup guides
- noted.lol — self-hosted app reviews

### Nice-to-Include (from SearXNG):
- New tool releases (Docker, n8n, Home Assistant, NGINX, etc.)
- Interesting homelab setups and guides
- Security advisories for popular self-hosted apps
- awesome-selfhosted updates

### Exclude:
- Generic Linux distro news (unless directly self-hosting related)
- Pure cloud/SaaS (not self-hosted)
- Mobile apps
- Gaming (unless homelab/game server related)
- Crypto/blockchain

## Digest Quotas

- 📰 New & Noteworthy (SearXNG + RSS extras): up to 5 items
- 📚 From the Feeds (selfh.st · mariushosting · noted.lol): up to 5 items

**RSS allocation rule (MANDATORY):** If any of the 3 RSS feeds have new articles in the last 3 months, the "From the Feeds" section MUST include at least 1 item from each source that has new content. Do not drop a source just because its articles seem less exciting — include the most recent article from each active source. Only skip a source if it truly has zero new articles in the past 3 months.

## Delivery Configuration

- **Delivery channel**: Telegram (`telegram:<CHAT_ID>` — replace with your own chat ID)
- **Frequency**: Every 3 days (`0 3 */3 * *`), but consider weekly for learning-focused digests
- **Format**: Top 5 items per section max, headline + 1-2 line summary + direct link + source
- **Cron job ID**: `<CRON_JOB_ID>` (assigned when the job is created)
- **Emoji**: 🔧 (self-hosting), 🆕 for articles in last 7 days

## Key Themes to Watch

1. **New self-hosted tools**: Fresh alternatives to SaaS, new Docker images, new projects
2. **Homelab setups**: Interesting configurations, hardware choices, networking
3. **Security updates**: Vulnerabilities in popular self-hosted apps, best practices
4. **Major releases**: n8n, Docker, Home Assistant, NGINX, Traefik, Portainer, etc.
5. **Community highlights**: r/selfhosted trends, awesome-selfhosted additions