---
name: clipsdaily
description: Fully automatic stream clip pipeline — record Twitch/Kick/YouTube Live, cut 30s vertical clips, post to YouTube Shorts / TikTok / Instagram Reels, join and submit clipping campaigns behind a strict eligibility gate. Use when working on the clipsdaily repo or operating the live pipeline.
---

# clipsdaily

## What it is

Fully automatic clip pipeline for Twitch, Kick, and YouTube Live. Records live streams, finds the moments chat erupts, cuts 30-second vertical clips, and posts them to YouTube Shorts, TikTok, and Instagram Reels on an hourly cadence (2 clips/hour) — no review queue, no human step. General purpose: any streamer on the watchlist, any game, any event. It also joins and submits clipping campaigns (Content Rewards) behind a strict eligibility gate.

## Repo vs live

- **This repo is the canonical dev copy.** All work happens here.
- The live pipeline runs at `/home/abel/clipsdaily` on indra. **Never edit the live dir by hand** — deploy with `bash deploy.sh` (dry-run first: `make deploy`).
- Runtime state (`queue/`, `ig-outbox/`, `clips/`, `vod/`, `recordings/`, `logs/`, `campaign_queue.json`, `campaigns.json`, `earnings.json`, `.auth/`) is gitignored and lives only in the runtime home. A fresh clone generates its own state by running the pipeline.
- Runtime home resolution: `$CLIPSDAILY_HOME` when set, else the current working directory. Run the CLI from the runtime home, or pass `--home`.

## CLI

```bash
clipsdaily run                          # live runner (record + spikes + cut + post)
clipsdaily post now                     # post the next pending queue clip now
clipsdaily post one <clip-id> [slot]    # post one queue clip by id
clipsdaily post hourly                  # hourly poster loop (slots :00/:30)
clipsdaily queue status                 # queue counts + next clip
clipsdaily queue maintain               # maintainer loop (seed >= 24)
clipsdaily queue seed [N]               # cut until N pending, then exit
clipsdaily campaign watch --check       # watch Content Rewards for campaigns
clipsdaily campaign cut --campaign <id> [--max-clips N] [--dry-run]
clipsdaily submit scan                  # scan queue for submittable clips
clipsdaily submit list-pending          # pending submit jobs (JSON)
clipsdaily submit mark-submitted <job> --submission-id <id>
clipsdaily submit mark-failed <job> [--reason "<why>"]
clipsdaily earnings [--update|--summary]
clipsdaily auth check                   # read-only auth check (posts nothing)
clipsdaily auth youtube|tiktok|instagram  # setup flows (human steps)
```

Every module also runs directly: `python -m clipsdaily.runner`, `python -m clipsdaily.cutter recordings/x.mp4 45 channel`.

## Standing rules — never break these

1. **Full frame, no cropping.** Every clip shows the whole 16:9 source frame: 1080x1920 vertical canvas, whole frame scaled to fit width, top/bottom filled with a blurred, darkened copy of the same video. Nothing cut off the sides.
2. **One-line post captions.** Regular: `Throwback — <streamer>: <moment>`. Live: `clipsdaily • <streamer>`. Campaign: money line + Expedia + destination + `#IShowSpeed` only. No boilerplate, no date, no hashtags except campaign-required ones. Hashtags don't drive reach (2026 consensus: categorization only).
3. **No burned-in word captions.** Whisper may run internally to find the moment; nothing burns in except ONE big hook text overlay at the start (~3s, big bold, max ~8 words, true to the moment). Hook at y=300 (lower, clear of platform top UI). Hook entrance: 250ms ease-out-expo slide+fade, 170ms ease-in exit (motion-design skill).
4. **Strict eligibility gate.** `eligibility_gate.py` must PASS before any campaign clip posts or submits — window check, caption check, framing check (top < 0.4, bottom < 1.0, center > 2.0 gradient energy). Borderline = blocked. Never bypass for speed.
5. **Never submit a clip twice, or past 30 minutes after posting.** A job is complete ONLY when the dashboard shows Pending WITH a submission ID.
6. **Audit before submitting.** Watch/read the actual clip, check captions, credit, titles, and that the post is really live — before any link goes to a campaign.
7. **Credit the streamer** in every post.
8. **Clipsdaily accounts only** — Instagram @clippedaily31, TikTok @clips.daily548, YouTube Clips Daily @Clippedaily31. Never point this at a personal account.
9. **TikTok auto-posting is blocked** (throttled session + Playwright sync/async bug in the hourly TikTok path). Manual phone post works; the account is fine. Do NOT retry repeatedly — retries deepen the throttle. Fix = fresh cookie export + Playwright fix (see docs/TIKTOK.md).
10. **YouTube daily upload limit** (~8/day on this channel). `uploadLimitExceeded` means wait until after the reset (~03:00 EST), not retry.
11. **Never run `restart_maintainer.py`.** It wipes `queue.json` and resets state. Restart the maintainer with a plain tmux restart.
12. **Long ffmpeg jobs run detached** (nohup/tmux), never over a bare SSH pipe.
13. **Never pay to join any clipping platform.** Never automate Whop payout setup/withdrawals (maintainer's job by hand).
14. **One-strike rule:** one bad campaign submission bans the account from every campaign permanently. That is why the gate exists.

## Cut rules (from the reels)

- Cut **20 seconds BEFORE the chat spike** (the spike lags the moment), 30s total.
- **Rank clips by spike intensity**, not just spike size.
- **Label old-VOD clips as throwbacks** ("THROWBACK: <moment>", caption leads "Throwback — <moment>" + stream date when known). Old footage is a feature.
- Cut SHORT: viral clips are 5–17s. 30s is the Shorts/Reels default; 60–90s only for TikTok Creator Rewards pay.
- Rank by saves+shares rate, not just chat spike size.
- Chat spikes can mislabel the moment — always frame-check the cut before posting.

## Known gaps (do not "fix" by hand)

- Hourly poster does NOT yet prefer `campaign_queue.json` — campaign cuts sit unposted (ROADMAP.md item 1).
- Runner's clips ship hook-less (hook=None default).
- YouTube token lacks delete scope — flawed Shorts are deleted from Studio, or after an OAuth re-run with full `youtube` scope.

## Before you push

```bash
make lint    # compile all .py + secret scan
make check   # VERSION matches the package version
make test    # full e2e smoke test (needs network)
```

See also: `docs/OPERATIONS.md`, `docs/CAMPAIGNS.md`, `docs/TIKTOK.md`, `docs/adr/`.
