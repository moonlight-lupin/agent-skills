---
name: pexels-stock-photos
description: >
  Search and download free real-world stock photos from the Pexels API. Use when
  the user wants a REAL photo — "find a photo of X", "search for pictures of Y",
  "stock image of Z", "I need a photo for this slide/article/presentation".
  Searches the Pexels library (millions of photos) and downloads images in the chosen
  size and orientation. Do NOT use for AI-generated art ("generate an image of",
  "create a picture of", "make me an illustration") — those go to the host's
  image generation tool or an AI image skill. Key distinction: "photo" = real
  stock photography = Pexels; "generate/create/make an image" = AI art = image
  generation tools. Also do not use for editing existing images, screenshots,
  diagrams, or data charts.
version: 1.0.0
author: moonlight-lupin
license: MIT
platforms: [linux, macos, windows]
---

# Pexels Stock Photos

Search and download free stock photos from the Pexels API (200 req/hr, 20k/month
free). All content is free for commercial and non-commercial use; just credit the
photographer and link to Pexels.

## Routing: Pexels vs AI Generation

| User says... | Tool |
|--------------|------|
| "find a photo of Singapore" / "search for office pictures" / "stock image of a desk" | **Pexels** (this skill) |
| "I need a real photo for this slide" / "find pictures for my article" | **Pexels** (this skill) |
| "generate an image of a cat" / "create a picture of..." / "make me an illustration" | Host's image generation tool |
| "upscale this" / "remove background" / "edit: make warmer" | Host's AI image editing skill |
| "production-ready hero image" / "let's do this properly" | Host's multi-stage image generation skill |

**The key word test:** if the user says **photo**, **picture**, **stock image**,
or **find/search** → Pexels. If the user says **generate**, **create**, **make**,
**draw**, or **illustration** → AI generation.

## When to Use

- User asks for a "photo of X" or "stock image of Y"
- Building presentations (PPTX) that need real imagery
- Article/blog illustrations needing authentic photos
- Social media posts requiring professional photography
- Any request for "real" images vs AI-generated

**Don't use for:**
- AI art / creative generation → host's image generation tool
- Editing existing images → host's image editing skill
- Screenshots or diagrams → use appropriate tools

## API Reference

Base URL: `https://api.pexels.com/v1/`
Auth: `Authorization: <PEXELS_API_KEY>` header

### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/search` | GET | Search photos by query |
| `/curated` | GET | Curated trending photos |
| `/photos/:id` | GET | Get a specific photo by ID |

### Search Parameters

| Param | Type | Default | Notes |
|-------|------|---------|-------|
| `query` | string | **required** | e.g. "singapore skyline" |
| `orientation` | string | — | `landscape`, `portrait`, `square` |
| `size` | string | — | `large` (24MP), `medium` (12MP), `small` (4MP) |
| `color` | string | — | `red`, `orange`, `blue`, ... or hex `#ffffff` |
| `locale` | string | `en-US` | `zh-CN`, `ja-JP`, etc. |
| `per_page` | int | 15 | Max 80 |
| `page` | int | 1 | Pagination |

### Photo Resource `src` Sizes

| Size | Dimensions | Use case |
|------|-----------|----------|
| `original` | Full res | Print, high-quality |
| `large2x` | 940×650 @2x | Retina displays |
| `large` | 940×650 | Web, presentations |
| `medium` | ~350px height | Thumbnails, previews |
| `small` | ~130px height | Small thumbnails |
| `portrait` | 800×1200 | Vertical/mobile |
| `landscape` | 1200×627 | Slides, social |
| `tiny` | 280×200 | Placeholders |

## Workflow

### 1. Search for photos

```bash
curl -s -H "Authorization: $PEXELS_API_KEY" \
  "https://api.pexels.com/v1/search?query=singapore+skyline&per_page=5&orientation=landscape"
```

Parse the JSON response to present results to the user: photo ID, photographer,
alt text, dimensions, and Pexels URL.

### 2. Download a photo

Use the **`src` URLs from the search response** — don't hand-construct
`images.pexels.com` URLs (the slug/extension isn't guaranteed; Pexels' docs say
to use `src`). Each photo object carries ready-made size variants (see the
`src` table above).

```bash
# Download the size you need, straight from the photo's src field
# (e.g. the value of photos[0].src.large from the search JSON)
curl -sL -o /tmp/pexels_<id>.jpeg "<photo.src.large>"
```

Deliver the file to the user via the host's file delivery mechanism.

### 3. Present results

When showing search results, format as a table:

```
| # | ID | Photographer | Alt | Dimensions |
|---|-----|-------------|-----|------|
| 1 | 5097071 | Dylan Chan | Singapore skyline at dusk | 6016×3384 |
```

Include the Pexels URL so the user can preview before downloading.

## Attribution

Per Pexels guidelines:
- Credit the photographer: "Photo by [Name] on Pexels"
- Link back to the photo page URL
- Include "Photos provided by Pexels" when displaying multiple

Example attribution block:
```
Photo by Dylan Chan on Pexels
https://www.pexels.com/photo/high-rise-buildings-in-singapore-5097071/
```

## Common Pitfalls

1. **API key not in environment.** `PEXELS_API_KEY` must be set before making
   requests. Load it from your environment or `.env` file before calling curl.

2. **Using spaces in query.** URL-encode spaces as `+` or `%20`.
   `singapore skyline` → `singapore+skyline`.

3. **Downloading original for previews.** Original files can be 10MB+. Use
   `large` or `medium` for previews, `original` only when the user needs full
   resolution.

4. **Rate limit awareness.** 200 req/hr, 20k/month — but only **API calls**
   (search, curated, photo lookup) count. CDN downloads from the `src` URLs on
   `images.pexels.com` (no API key needed) do **not** count. Batch searches
   with `per_page=15-80` to minimize API calls.

5. **Not including attribution.** Pexels requires visible credit to the
   photographer and a link to Pexels. Always include attribution text when
   delivering photos.

6. **Hand-built photo URLs.** Don't construct `images.pexels.com/photos/...`
   URLs yourself — the slug and extension aren't guaranteed across photos.
   Always download via the `src.*` URLs from the API response.

## Verification Checklist

- [ ] `PEXELS_API_KEY` is set in the environment
- [ ] Search query returns results (check `total_results > 0`)
- [ ] Downloaded file exists and is non-empty
- [ ] Attribution text included with delivered photo
- [ ] Rate limit headers checked if making many requests (`X-Ratelimit-Remaining`)