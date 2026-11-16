# FAQ

## Why is TikTok not posting?

TikTok auto-posting is blocked (Nov 15, 2026): the automated session is throttled after the submit burst, and the hourly TikTok path has a Playwright sync/async bug ("It looks like you are using Playwright Sync API inside the asyncio loop"). The account is fine — a manual phone post works. The session cookies are valid to 2027-05-14, so it is not an expiry. Fix = fresh cookie export from the operator's browser + the Playwright fix. **Do not retry repeatedly** — retries deepen the throttle. See [TIKTOK](TIKTOK.md).

## Why did a YouTube upload fail with uploadLimitExceeded?

The channel hit its daily upload limit (~8/day on this channel). Wait until after the reset (~03:00 EST) and post the staged clips then. Do not retry the same day.

## Why is a clip cropped?

It shouldn't be. Every clip must show the full 16:9 frame on a 1080x1920 canvas with a blurred darkened copy behind it. A cropped clip means an old cutter ran (pre-full-frame). Re-cut with the current `cutter.py` and check the frame at t=5/15/25s. The eligibility gate's framing check catches this for campaign clips.

## Why is there no caption on the video?

By design. No burned-in word captions — one big hook overlay at the start only (~3s). The post caption is one line. See the standing rules in [skills/clipsdaily/SKILL.md](../skills/clipsdaily/SKILL.md).

## Do hashtags help?

Barely. Hashtags are a categorization signal now, not a reach driver (Mosseri: they don't drive reach on IG; TikTok For You runs on watch time/saves/shares; YouTube Shorts hashtags are not a ranking factor). Only keep hashtags a campaign requires (`#IShowSpeed`).

## How does the money work?

Campaigns pay ~$1 per 1,000 views, min $10 at 10,000 views (MVR), max $500 per clip per platform. Same clip on all 3 platforms maxes $1,500. Views only count after submission + approval + 10k views. Organic views pay ~$0 (YouTube Shorts RPM $0.03–$0.07/1K; TikTok Creator Rewards $0.40–$1.00/1K for 60s+ videos, needs 10k followers + 100k views/30d; Instagram $0). Reposted stream clips are not original content — TikTok and YouTube can demonetize or take down even with credit. Campaigns are the safer money because the campaign licenses that footage.

## Can I submit a clip again if it didn't get views?

No. Never submit a clip twice, and never submit past 30 minutes after posting. If a job expired, it stays failed.

## How do I stop everything?

`touch STOP` in the runtime home. The runner exits cleanly on the next loop. Remove the STOP file before restarting. Never `kill` the process directly.

## The queue is empty / stuck. What do I check first?

The maintainer log (`logs/` in the runtime home), then `clipsdaily queue status`. **Never run `restart_maintainer.py`** — it wipes `queue.json`. Restart the maintainer with a plain tmux restart.

## Where do I report a bug?

GitHub Issues (once the repo is pushed). Include the command, the log lines, and what you expected. Never paste credentials, tokens, or cookies in an issue.
