# CLAUDE.md — agent instructions for clipsdaily

You are working on the clipsdaily clip pipeline. This repo is a
portable copy of a LIVE pipeline (live dir: `/home/abel/clipsdaily`
on indra). The live pipeline posts to real accounts with real
money on the line. Treat this repo as the dev copy: develop and
test here, never post/join/submit anything live without an
explicit go from Abel, and never touch the live dir.

## Standing rules (never break these)

1. **Full frame, never crop.** Every clip is 1080x1920: the whole
   16:9 source scaled to fit width, top/bottom filled with a
   blurred, darkened copy of the same video. Nothing cut off the
   sides. The eligibility gate proves this with band energies
   (top < 0.4 AND bottom < 1.0 AND center > 2.0); a center-crop
   clip fails it.
2. **One-line captions, no hashtags (except campaign-required).**
   Regular: `Throwback — <streamer>: <moment>`. No boilerplate
   ("Best stream moments..."), no date, no hashtags. Campaign:
   money line + Expedia + destination + `#IShowSpeed` only.
   Hashtags do not drive reach (2026 consensus: categorization
   only). The streamer name in the caption is the credit.
   Titles are unchanged (`THROWBACK: <streamer> — <moment> |
   clipsdaily #shorts`). Full rules: `docs/CAPTIONS.md`.
3. **Hook: one big line at the start only.** First ~3s, big bold
   centered text at y=300 (lowered Nov 15 to clear the platform
   top UI), 250ms ease-out-expo slide+fade in, 170ms ease-in
   fade out (motion-design skill). No burned-in word captions
   ever. Whisper may run internally to find the moment; nothing
   burns in except the hook. See `docs/CAPTIONS.md`.
4. **The eligibility gate is strict and is never bypassed.**
   `eligibility_gate.py`: window + caption + full-frame. Any
   failure or unverifiable check = BLOCKED, never posted, never
   submitted. Borderline = blocked. Re-validate the framing
   detector against both ground truths if `cutter.py`'s filter
   chain ever changes (it false-passed a center-crop clip once).
   See `docs/AUTOMATION.md`.
5. **TikTok auto-posting is blocked (Nov 15, 2026).** Automated
   submits are silently dropped; a manual phone post works. Do
   NOT hammer retries — it risks deepening a throttle. See
   `docs/TIKTOK.md`. There is also an open Playwright bug in
   the hourly TikTok path (sync API inside an asyncio loop).
6. **Never submit without the gate passing, never submit the
   same clip+platform twice, never submit later than 30 minutes
   after posting.** A submit job is complete only when the
   Content Rewards dashboard shows Pending WITH a submission ID.
7. **Credit the streamer in every post.** Caption names the
   streamer; the video overlay carries `clipsdaily • <streamer>`.
8. **Clipsdaily accounts only, never Abel's personal accounts.**
   Instagram @clippedaily31, TikTok @clips.daily548, YouTube
   Clips Daily @Clippedaily31.
9. **No credentials in the repo, ever.** `.auth/` is gitignored.
   Passwords/tokens/cookies are never written to files, logs,
   or chat. Auth is recreated per `docs/AUTH.md`.
10. **Never run `restart_maintainer.py`.** It is a stale one-off
    that wipes `queue.json` and resets maintainer state.
    Restart the maintainer with tmux (see `docs/OPERATIONS.md`).
11. **Long ffmpeg jobs run detached** (nohup/tmux), never over a
    bare SSH pipe — the pipe breaks and kills the burn.
12. **One-strike rule:** a single bad Content Rewards submission
    bans the account from EVERY campaign permanently. That is
    why rules 4 and 6 exist.

## How to run

```bash
bash setup.sh                    # deps + runtime dirs
cp config/config.yaml.example config.yaml
# campaigns.json starts empty: {"campaigns": {}} — the watcher fills it
python3 poster.py --check        # read-only auth check, posts nothing
tmux new -s clipsdaily && python3 runner.py        # live loop
tmux new -s clipsdaily-queue && python3 queue_seed.py --maintain
tmux new -s clipsdaily-hourly && python3 hourly_poster.py
```

Cadence: 2 clips/hour, slots :00 and :30 (YouTube + TikTok from
this host), Instagram :05/:35 via `scripts/ig-post-staged.sh`
on the operator machine (needs `instagram-cli`, which cannot run
on indra). Queue targets: seed 24 pending, keep cutting when
pending drops below 12. Daily cap 20 clips. Kill switch: `touch
STOP` in the repo root pauses all posting.

## File map

- Core runtime: `runner.py`, `recorder.py`, `chat.py`,
  `cutter.py`, `poster.py`, `cleanup.py`, `vod.py`.
- Hourly feed: `queue_seed.py` (maintainer, VOD-seeded queue),
  `hourly_poster.py` (posts queue entries, stages IG).
- Money loop: `campaign_watcher.py`, `campaigns.py`,
  `campaign_cut.py`, `eligibility_gate.py`, `auto_submit.py`,
  `earnings.py`. `campaign_cut.py` writes to
  `campaign_queue.json`, never `queue.json`. The hourly poster
  does NOT yet prefer `campaign_queue.json` (wiring pending).
- Auth: `auth_youtube.py`, `auth_youtube_manual.py`,
  `auth_tiktok.py`, `auth_instagram.py` (instagrapi route;
  currently fails at login — the live IG route is
  `instagram-cli` on the operator machine).
- TikTok: `post_tiktok_fixed.py` (fixed poster: dismisses the
  content-checks modal, JS-clicks Post, verifies via Studio).
  `poster.py:post_tiktok` and `hourly_poster.py` call it first,
  falling back to stock `tiktok-uploader`.
- One-offs (historical, already applied, do not re-run blindly):
  `patch_*.py`, `post_speed.py`, `post_tiktok_only.py`,
  `post_now.py`, `post_one.py`, `post_tt_one.py`,
  `post_yt_batch.py`, `tt_*.py`, `fail_9805_tt.py`,
  `diag_tiktok.py`, `check_tiktok_profile.py`,
  `find_tiktok_video.py`, `find_vods.py`, `tt_verify_hk.py`,
  `cut_speed_expedia.py`, `recut_fullframe.py`,
  `recut_jynxzi2075.py`, `recover_9805.py`, `make_speech.py`,
  `motion_test.py`, `framing_test.py`, `delete_shorts.py`,
  `vod_batch.py`, `vod_cut.py`, `vod_cut_resume.py`.
- `test_e2e.sh` — synthetic end-to-end test (no live post).

## Path assumptions

Most core files use `Path(__file__).resolve().parent`, but
several files hardcode `/home/abel/clipsdaily`, and the binaries
resolve to `~/.local/bin/{streamlink,yt-dlp,
TwitchDownloaderCLI,ffmpeg}`. Exact list: `docs/PATHS.md`.
Clone to `/home/abel/clipsdaily` or edit those paths. Do not
refactor working code just for this.

## Skills

- `skills/motion-design/` (vendored, MIT, LottieFiles) — hook
  entrance timing/easing. This is the only skill vendored.
- `ffmpeg-skill` (kajisho5, MIT, 31 MB — not vendored): install
  with `git clone --depth 1
  https://github.com/kajisho5/ffmpeg-skill` into
  `~/.claude/skills/ffmpeg-skill`. Agent guidance for ffmpeg
  filter work; the runtime just shells out to the ffmpeg binary.
- `video-editing` (Moises Melo, MIT — not vendored): only for
  the future YouTube VOD phase (see `docs/youtube-vod-notes.md`).
  Download via blog.moisesmelo.com. Not used by the live pipeline.
- `synced` and `unslop` are unrelated (other projects) and are
  not included.

## Money math (for context, not a promise)

YouTube Shorts RPM ~$0.03–$0.07/1K views; TikTok Creator
Rewards $0.40–$1.00/1K qualified views, only for videos over
60s; Instagram $0/view. Reposted stream clips are not original
content — TikTok requires original, YouTube has a reused-content
rule; both can demonetize or take down even with credit.
Campaigns are the safer money because the campaign licenses
that footage. Realistic: $0 months 1–3.
