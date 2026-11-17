# Automate campaign discovery

## Status

Accepted — 2026-11-15

## Context

Content Rewards has ~780 live campaigns, and checking them by hand every day doesn't scale. But joining the wrong campaign wastes cuts and risks rejections: a campaign with no footage window, a rate below $1 per 1,000 views, or a streamer nobody on the watchlist is streaming is not worth a clip. There is no public API and no login available to the watcher.

## Decision

`campaign_watcher.py` fetches the Content Rewards discover page as anonymous HTML and parses the Next.js RSC chunks for campaign records (no API, no login). A campaign is joined only when all 7 rules pass: active, budget left, rate >= $1/1K, no application required, a watchlist streamer named, an explicit footage window that parses, and usable platforms. Joining itself stays human: the operator verifies the Joined badge in the browser and writes `join_results.json`. Vyro has no public data, so it is consumed from a parent browser dump (`vyro_dump.json`) or skipped.

## Consequences

- The watcher parses undocumented Next.js HTML. If Content Rewards changes structure, parsing returns 0 records and it fails closed (no joins) — but someone must notice the 0-parse.
- 0 joins is a correct outcome when nothing qualifies (verified on the live discover page: 25 records parsed, Speed present at $1/1K with $7,500.71 available, 0 join requests, 19 needs_review, 6 skipped/known).
- Campaign cuts go to `campaign_queue.json`, never to the hourly `queue.json`, and are gated by the eligibility gate before posting.
- Known gap: the hourly poster does NOT yet prefer `campaign_queue.json` when a campaign is active, so campaign cuts would sit unposted until that wiring lands. That wiring needs my go.
