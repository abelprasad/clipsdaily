# Post two clips per hour

## Status

Accepted — 2026-11-15

## Context

Abel wanted a steady posting rhythm, not a flood and not a trickle: "i want a video clip posted on all three accounts every hour", corrected the same evening to "actually do two clips every hour" plus "make one rn first". One clip an hour would have left the queue full and the accounts quiet; more than two an hour risks looking like spam and tripping platform limits.

## Decision

Two clips per hour, every hour, until Abel says stop. Slots are :00 and :30 for YouTube and TikTok (posted from indra by `hourly_poster.py`), and IG at :05 and :35 via `ig-outbox/` staging plus a 30-minute operator cron. The queue maintainer targets a seed of at least 24 pending clips and keeps cutting whenever pending drops below 12. Daily cap is 48 posts.

## Consequences

- At full cadence the dashboard shows posts today against the 48 daily cap.
- A platform marked FAILED is resolved, not retried forever: the entry must not sit "partial" forever and block the queue (a stall bug fixed Nov 15). Failed platforms do not retry indefinitely.
- A partial entry may be re-run at the next slot: 2605s re-ran at 22:30 after its TikTok leg failed (YouTube already posted, so only IG re-staged and TikTok retries were exhausted).
- YouTube's daily upload limit can still block a slot: it was hit on Nov 15 (9th upload of the day failed with `uploadLimitExceeded`), and it resets around 03:00 EST. Two staged Shorts (jynxzi checkmate, stableronaldo Punch-Out) waited for the next day for that reason.
- TikTok is in the cadence but systematically failing since ~20:25 Nov 15 (see `post-tiktok-via-cookie-export.md`); the cadence does not stop for it.
