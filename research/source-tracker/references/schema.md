# Source Record Schema

Source Tracker stores records in a SQLite table named `sources`. Each row is one
canonical cited URL. URL variants can be merged by the dedup workflow.

```sql
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL UNIQUE,
    url_normalized TEXT NOT NULL,
    title TEXT,
    topic TEXT NOT NULL,
    source_type TEXT DEFAULT 'web',
    accessed_at TEXT NOT NULL,
    notes TEXT,
    verified INTEGER DEFAULT 1,
    last_checked TEXT,
    session_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_topic ON sources(topic);
CREATE INDEX IF NOT EXISTS idx_normalized ON sources(url_normalized);
```

## Fields

| Field | SQLite type | Required | Constraints | Usage notes |
|---|---:|---:|---|---|
| `id` | `INTEGER` | Yes | Primary key, autoincrement. | Internal stable row identifier. Use for debugging, exports, and update targeting. |
| `url` | `TEXT` | Yes | Unique. Stored as canonical URL. | The visible citation URL. Canonicalization lowercases scheme/host, strips fragments, strips default ports, and trims trailing slash on non-root paths. |
| `url_normalized` | `TEXT` | Yes | Indexed, not unique. | Normalized URL field reserved for lookup/dedup support. Dedup also computes a comparison key that ignores scheme and leading `www.`. |
| `title` | `TEXT` | No | May be `NULL`. | Human-readable source title. Provide explicitly with `--title` for important citations; otherwise the add command tries a best-effort HTML `<title>` fetch. |
| `topic` | `TEXT` | Yes | Indexed. | Topic tag used for search, stats, and export. Keep topic strings consistent across sessions. |
| `source_type` | `TEXT` | No | Defaults to `web`. Expected values: `web`, `pdf`, `api`, `dataset`, `book`, `news`, `report`. | Helps filter source lists and distinguish citation classes. |
| `accessed_at` | `TEXT` | Yes | ISO date (`YYYY-MM-DD`). | Date the source was added/cited. Dedup keeps the earliest date among merged variants. |
| `notes` | `TEXT` | No | May be `NULL`. | Short explanation of why the source matters. Dedup combines unique non-empty notes from merged rows. |
| `verified` | `INTEGER` | No | `1` for alive/verified, `0` for dead/unverified. Defaults to `1`. | Health checker updates this flag. Export includes it for auditability. |
| `last_checked` | `TEXT` | No | ISO date (`YYYY-MM-DD`) or `NULL`. | Last date `url_health.py` checked the URL. `NULL` means never checked after insertion. |
| `session_id` | `TEXT` | No | Free-form string. | Optional research session, vault, project, or run identifier. Useful when one topic spans many sessions. |

## Source Type Values

- `web` — standard web page, documentation, blog post, landing page.
- `pdf` — direct PDF URL or page where the PDF is the source of record.
- `api` — API endpoint or machine-readable service response.
- `dataset` — public data catalog or downloadable data file.
- `book` — online book, chapter, scan, or bibliographic record.
- `news` — news article, wire story, interview, or live blog.
- `report` — white paper, government report, analyst note, or institutional report.

## Normalization Notes

`url` is canonicalized for storage, while dedup computes an additional comparison
key at runtime. The comparison key collapses these variants:

- `http` and `https` versions of the same host/path/query.
- Hosts with and without a leading `www.` prefix.
- URLs that differ only by fragment (`#section`).
- Non-root paths that differ only by a trailing slash.

Query strings are preserved because they can identify distinct documents or API
responses.
