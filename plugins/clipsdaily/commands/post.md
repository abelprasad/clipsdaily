---
description: Post clips now — one pending clip, one clip by id, or start the hourly poster loop
---

Post clips from the queue. Three modes:

## Post the next pending clip now

```bash
clipsdaily post now
```

Posts the next pending queue clip to YouTube + TikTok, stages Instagram, prints a JSON result with URLs + post times. One-off, extra on top of the hourly schedule.

## Post one clip by id

```bash
clipsdaily post one <clip-id> [slot]
```

Example: `clipsdaily post one jynxzi-2928767125-12505s`.

## Hourly poster loop (2 clips/hour, slots :00/:30)

```bash
clipsdaily post hourly
```

Run detached in tmux:

```bash
tmux new -s clipsdaily-hourly
cd /home/abel/clipsdaily && clipsdaily post hourly
```

## Rules

- **TikTok auto-posting is blocked** (throttled session + Playwright sync/async bug). A TikTok failure on `post now` / `post hourly` is expected — do NOT retry it repeatedly; retries deepen the throttle. See docs/TIKTOK.md.
- Instagram is staged to `ig-outbox/` and posted from the operator machine by the 30-min cron (`scripts/ig-post-staged.sh`) — the poster never posts to Instagram directly.
- Verify a post is live via the platform (profile/Studio/shorts URL) before claiming it posted. Never infer success from a missing Post button.
- YouTube has a daily upload limit (~8/day on this channel). A `uploadLimitExceeded` failure means wait until after the reset (~03:00 EST), not retry.
