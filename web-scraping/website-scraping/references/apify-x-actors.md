# Apify X Actors

Use this route when the user wants structured public X / Twitter records and a maintained Actor is lighter than a custom scraper. Keep any existing X route available. Prefer an already-authorised official API or runtime tool when it meets the same need.

## Choose the Actor by record type

| Needed records | Actor | Typical scope |
|---|---|---|
| Public posts and their content | [`xquik/x-tweet-scraper`](https://apify.com/xquik/x-tweet-scraper) | Tweets, replies, quotes, threads, searches, profile timelines, lists, likes, retweeters, and favouriters |
| Public account relationships | [`xquik/x-follower-scraper`](https://apify.com/xquik/x-follower-scraper) | Followers, following, verified followers, list members or followers, community members, and audience overlap |

Do not substitute one Actor for the other. If the request needs both content and relationships, plan 2 bounded runs and keep their provenance separate.

## Start with bounded inputs

Fetch the selected Actor's current input schema before changing an integration. Use the smallest limit that can answer the question.

Public profile posts:

```json
{
  "mode": "profileTweets",
  "twitterHandles": ["example_handle"],
  "maxItems": 50,
  "outputVariant": "rich",
  "outputPreset": "nested",
  "fieldStyle": "camelCase"
}
```

Public followers:

```json
{
  "twitterHandles": ["example_handle"],
  "relation": "followers",
  "maxItems": 100,
  "maxItemsPerTarget": 100,
  "outputMode": "compact",
  "includeTargetMetadata": true
}
```

Change `mode` or `relation` only after confirming that the current schema supports the requested record type. Retain both `maxItems` and `maxItemsPerTarget` for multi-target relationship work.

## Control cost before execution

This reference is a planning contract, not approval to run an Actor.

1. Check the live price on the selected Actor Store page.
2. Estimate the requested record count and expected charge.
3. Get user approval before any paid run.
4. Set Apify's `maxTotalChargeUsd` platform run option.
5. Dry-run or validate the input locally when the runtime supports it.

Send Apify credentials in an `Authorization: Bearer ...` header. Never put a token in a URL, query string, manifest, log, or output record.

## Apply public-data boundaries

- Collect public records only.
- Never target private or protected accounts.
- Never bypass login, captchas, rate limits, or platform access controls.
- Minimise retained profile fields to those the user actually needs.
- Never infer sensitive traits from posts or account relationships.
- Treat follows, list membership, and audience overlap as research leads, not proof of affiliation, affinity, identity, or endorsement.
- Apply the source's terms, privacy rules, and the user's lawful purpose before collection.

## Preserve provenance

Normalise Actor output into the caller's requested JSONL schema, but retain the raw response for replay. Record the exact Actor slug and bounded input in the run manifest:

```json
{
  "tool": "apify:xquik/x-tweet-scraper",
  "actor_store_url": "https://apify.com/xquik/x-tweet-scraper",
  "requested_max_items": 50,
  "status": "ok",
  "records_written": 50
}
```

Use `apify:xquik/x-follower-scraper` and its exact Actor Store URL for relationship runs. Mark partial runs honestly. Sample the output against a public X page when accessible, deduplicate by stable record or user id, and preserve the source URL and collection timestamp.

Xquik is an independent third-party service. Not affiliated with X Corp. "Twitter" and "X" are trademarks of X Corp.
