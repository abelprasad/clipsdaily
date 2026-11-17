# AGENTS.md — agent instructions for clipsdaily (compact)

Full instructions live in `CLAUDE.md`. This file is the short
version for agents that only read AGENTS.md.

## What this is

Fully automatic Twitch/Kick/YouTube Live clip pipeline. Records
live streams, finds chat spikes, cuts 30s vertical clips, posts
to YouTube Shorts, TikTok, Instagram Reels (2/hour). Campaign
join/submit automation for Content Rewards behind a strict gate.
This repo is a portable copy of the LIVE pipeline on indra
(`/home/abel/clipsdaily`). Never post/join/submit live without
an explicit go. Never touch the live dir.

## Rules (never break)

1. **Full frame, never crop.** 1080x1920: whole 16:9 source
   scaled to fit, blurred darkened copy top/bottom.
2. **One-line captions.** `Throwback — <streamer>: <moment>`.
   No hashtags except campaign-required `#IShowSpeed`. No
   boilerplate, no date. Campaign: money line + Expedia +
   destination + `#IShowSpeed` only.
3. **Hook: one big line, first ~3s only, y=300.** No burned-in
   word captions ever.
4. **Eligibility gate is never bypassed.** Window + caption +
   full-frame; any failure = BLOCKED. Borderline = blocked.
5. **TikTok auto-posting is blocked (Nov 15, 2026).** Do not
   hammer retries. Manual phone post works.
6. **Never submit without the gate passing; never submit the
   same clip+platform twice; never submit more than 30 min
   after posting.** Complete only with a dashboard submission ID.
7. **Credit the streamer in every post.** Clipsdaily accounts
   only, never my personal accounts.
8. **No credentials in the repo, ever.** `.auth/` is gitignored.
9. **Never run `restart_maintainer.py`** (stale, wipes queue).
10. **Long ffmpeg jobs run detached** (nohup/tmux), never over a
    bare SSH pipe.

## Run

```bash
bash setup.sh
cp config/config.yaml.example config.yaml
clipsdaily auth check
tmux new -s clipsdaily && clipsdaily run
tmux new -s clipsdaily-queue && clipsdaily queue maintain
tmux new -s clipsdaily-hourly && clipsdaily post hourly
```

Kill switch: `touch STOP`. Daily cap 20. Disk guard 50 GB.
Docs: `docs/` (`CAPTIONS.md`, `campaigns.md`, `TIKTOK.md`,
`AUTH.md`, `operations.md`, `PATHS.md`, `AUTOMATION.md`).
