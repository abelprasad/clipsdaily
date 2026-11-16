# clipsdaily

Fully automatic clip pipeline for Twitch, Kick, and YouTube Live.
Records live streams, finds chat spikes, cuts 30-second vertical
clips, and posts them to YouTube Shorts, TikTok, and Instagram
Reels on an hourly cadence. No review queue, no human step.
General purpose: any stream on the list, any game, any event.

It also joins and submits clipping campaigns (Content Rewards)
behind a strict eligibility gate, because one bad submission bans
the account from every campaign permanently.

> **This repo is a portable copy of the live pipeline.**
> The live pipeline runs at `/home/abel/clipsdaily` on indra.
> Nothing in this repo posts, joins, or submits anything until you
> configure auth and flip a platform on. Do not run it against the
> live accounts without an explicit go.

## Quickstart

```bash
git clone <this-repo> clipsdaily
cd clipsdaily
bash setup.sh            # deps: ffmpeg, streamlink, whisper, posters
cp config/config.yaml.example config.yaml
cp config/campaigns.example.json campaigns.json   # starts empty; watcher fills it
# Auth: see docs/AUTH.md (YouTube OAuth, TikTok cookies, Instagram)
python3 poster.py --check        # read-only, posts nothing
tmux new -s clipsdaily
python3 runner.py                # live recorder + poster
# Ctrl-B then D to detach
```

Queue maintainer (VOD-seeded clips, hourly feed) and hourly poster
run as separate processes — see `docs/OPERATIONS.md`.

## How it works

1. `recorder.py` — streamlink records a channel the moment it goes
   live, 1080p best, to `recordings/`.
2. `chat.py` — counts chat messages in 10-second windows (Twitch
   anonymous IRC / Kick public API + Pusher / YouTube yt-dlp live
   chat). A spike is 3x the recent median with at least 20 messages
   in the window. Intensity = messages / median.
3. `runner.py` — after a stream ends, spikes are processed
   **strongest first**, so when Whisper CPU queues back up the best
   clips go out first under the 20/day cap. Cooldown: max 1 clip per
   streamer per 5 minutes, shared across platforms.
4. `cutter.py` — ffmpeg cuts 30s around each spike (20s before, 10s
   after, because chat reacts after the moment). **Full frame**: the
   16:9 source is scaled to fit a 1080x1920 canvas, top/bottom
   filled with a blurred, darkened copy. Nothing is cropped. One
   big hook line burns in at the start only (~3s, y=300). No
   word captions. Credit `clipsdaily • <streamer>` top-left.
5. `poster.py` — posts each finished clip to enabled platforms.
   TikTok gets only the 60–90s variant (Creator Rewards pays only
   for clips over 60s); Shorts/Reels get the 30s file.
6. `queue_seed.py` — maintainer that seeds the hourly queue from
   recent VODs (chat-spike ranking, throwback labels).
7. `hourly_poster.py` — posts 2 clips/hour at :00 and :30
   (YouTube + TikTok from here; Instagram staged to `ig-outbox/`
   for the operator-machine poster at :05/:35).
8. `vod.py` — VOD fallback: recover clips from a finished stream
   with TwitchDownloaderCLI chat + video.
9. `campaign_watcher.py` / `campaign_cut.py` /
   `eligibility_gate.py` / `auto_submit.py` / `earnings.py` —
   the money loop. See `docs/AUTOMATION.md` and `docs/CAMPAIGNS.md`.

## Watchlist (Nov 15, 2026)

Twitch: kaicenat, ishowspeed, sykkuno, jynxzi, stableronaldo,
zackrawrr, hasanabi, clix. Kick: xqc, adinross. xQc is watched on
both Twitch and Kick with a shared cooldown, so the same moment
never makes two clips. Edit `config.yaml`, restart the runner.
Capacity: 8 concurrent recordings (8 cores, 11 GB RAM; Whisper
on CPU is the bottleneck, ~1 min per 30s clip).

## Cadence

2 clips/hour: slots :00 and :30 (YouTube + TikTok from the
pipeline host), Instagram at :05 and :35 via the operator-machine
script `scripts/ig-post-staged.sh` (needs `instagram-cli`, which
cannot run on indra). Queue targets: seed 24 pending, keep
cutting whenever pending drops below 12. Daily cap: 20 clips
(posting) and a YouTube daily upload limit observed Nov 15
(resets ~03:00 EST).

## Captions — one line, no hashtags

Regular clips, all three platforms, one line:

```
Throwback — ishowspeed: gonna be back streaming Skiiiiit
```

No boilerplate, no date, no hashtags. Hashtags do not drive
reach in 2026 (categorization only); the generic ones were
dropped. Campaign clips keep the money line + Expedia +
destination + the one required hashtag (`#IShowSpeed`) and
nothing else. Full rules: `docs/CAPTIONS.md`.

## Campaigns — the gate is the law

Content Rewards pays ~$1 per 1,000 views, min $10 at 10,000 views
(MVR), max $500 per clip per platform, submit within 30 minutes
of posting. One bad submission bans the account from EVERY
campaign permanently. `eligibility_gate.py` checks window +
caption + full-frame before any campaign clip is queued or
submitted; any failure or unverifiable check = BLOCKED.
Borderline = blocked. Never bypass it. Full rules:
`docs/CAMPAIGNS.md`, `docs/AUTOMATION.md`.

## TikTok status (Nov 15, 2026) — auto-posting blocked

TikTok auto-posting is currently blocked session-wide: the Japan
70s clip posted fine at 19:33 EST, then every automated submit
after ~20:25 was silently dropped (upload OK, Post clicked, no
confirmation, video never appears). A manual post from a phone
worked the same evening, so the account is fine — the automation
session is throttled. Cookies are valid to May 2027; do not hammer
retries. Details + the open Playwright bug: `docs/TIKTOK.md`.

## Kill switch

Posting stops immediately when a file named `STOP` exists in the
repo root: `touch STOP` to pause, `rm STOP` to resume.

## Cleanup

`cleanup.py` runs on startup and hourly: raw recordings deleted
after cutting, posted clips deleted after 24h, unposted after
48h, logs older than 7 days deleted. Disk guard: 50 GB free —
below it the runner stops new recordings.

## Repo map

| Path | What it is |
|---|---|
| `*.py` (repo root) | Pipeline code, flat copy of the live dir. Core: `runner.py`, `recorder.py`, `chat.py`, `cutter.py`, `poster.py`, `cleanup.py`, `vod.py`, `queue_seed.py`, `hourly_poster.py`, `campaign_watcher.py`, `campaigns.py`, `campaign_cut.py`, `eligibility_gate.py`, `auto_submit.py`, `earnings.py`, `auth_*.py`, `post_tiktok_fixed.py`. `patch_*.py`, `post_*.py`, `tt_*.py`, `recut_*.py` are historical one-offs, already applied — do not re-run blindly. `restart_maintainer.py` is stale and destructive (wipes `queue.json`) — **never run it**. |
| `config/` | `config.yaml.example`, `campaigns.example.json` (templates; copy to `config.yaml` / `campaigns.json`) |
| `scripts/` | Operator-machine helpers: `ig-post-staged.sh` (Instagram cron), `submit_cron.sh`, `submit_mark.sh` |
| `docs/` | `AUTOMATION.md`, `CAPTIONS.md`, `CAMPAIGNS.md`, `TIKTOK.md`, `AUTH.md`, `OPERATIONS.md`, `PATHS.md`, `SUBMIT_CRON_BODY.md`, `earnings_dump_spec.md`, `youtube-vod-notes.md` |
| `skills/` | `motion-design/` (vendored, MIT) + install notes for `ffmpeg-skill` and `video-editing` |
| `assets/` | `clipsdaily-logo.jpg` (brand logo) |

## Path assumptions

Most core files resolve paths from their own location
(`Path(__file__).resolve().parent`), but several files hardcode
`/home/abel/clipsdaily` and the binaries live at
`~/.local/bin/{streamlink,yt-dlp,TwitchDownloaderCLI,ffmpeg}`.
See `docs/PATHS.md` for the exact list. Either clone to
`/home/abel/clipsdaily` or edit those paths. Do not refactor
working code just for this.

## What this repo is not

- Not the live pipeline. The live one runs on indra; this repo
  lets any coding agent (Claude Code or otherwise) develop,
  test, and run the same pipeline elsewhere.
- Not a credential store. `.auth/` is gitignored. Recreate auth
  per `docs/AUTH.md`.
- The indra `README.md` from launch day is stale (pre-dates the
  full-frame rule and the caption cut-down) and is not included;
  this README supersedes it.
