# Path assumptions — hardcoded paths in this repo

The pipeline was built to run at `/home/abel/clipsdaily` on
indra. Most core files resolve paths from their own location
(`Path(__file__).resolve().parent`), so they work wherever the
repo is cloned. But several files hardcode `/home/abel/...`
paths, and the helper binaries live at `~/.local/bin/`.

**Do not refactor working code just for this.** Either clone
the repo to `/home/abel/clipsdaily`, or edit the paths listed
below. The table is generated from the code (file:line).

## Helper binaries (expected at ~/.local/bin, first on PATH)

| Binary | Used by | Notes |
|---|---|---|
| `ffmpeg` / `ffprobe` | `cutter.py` (via PATH) | Need >= 6.1. Live route: conda-forge ffmpeg 9.0.2 via micromamba, symlinked to `~/.local/bin/ffmpeg`. System `/usr/bin/ffmpeg` 4.4.2 is too old. |
| `streamlink` | `recorder.py` | Prefers `/home/abel/.local/bin/streamlink` if it exists, else `shutil.which("streamlink")`. pip install streamlink==8.6.3. |
| `yt-dlp` | `chat.py` (YouTube Live chat) | Hardcoded `/home/abel/.local/bin/yt-dlp`, no fallback. pip install yt-dlp or place the binary there. |
| `TwitchDownloaderCLI` | `vod.py` (VOD fallback) | Hardcoded `/home/abel/.local/bin/TwitchDownloaderCLI`. Download the linux-x64 release from github.com/lay295/TwitchDownloader. Live mode does not need it. |

## Hardcoded /home/abel paths in the code

### Files with hardcoded /home/abel paths

| File | Lines | Example |
|---|---|---|
| `auth_instagram.py` | 6 | `cd /home/abel/clipsdaily` |
| `auth_tiktok.py` | 6, 14, 15, 16, 17 | `/home/abel/clipsdaily/.auth/tiktok_cookies.txt  (Netscape format)` |
| `auth_youtube.py` | 8, 14 | `/home/abel/clipsdaily/.auth/youtube_client_secrets.json (mode 0600).` |
| `auth_youtube_manual.py` | 3 | `AUTH_DIR = Path("/home/abel/clipsdaily/.auth")` |
| `chat.py` | 42 | `YT_DLP = "/home/abel/.local/bin/yt-dlp"` |
| `check_tiktok_profile.py` | 4, 6 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `cut_speed_expedia.py` | 11, 14, 15 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `delete_shorts.py` | 3 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `diag_tiktok.py` | 5, 10, 12, 13, 63 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `eligibility_gate.py` | 41, 42 | `FFPROBE = shutil.which("ffprobe") or "/home/abel/.local/bin/ffprobe"` |
| `fail_9805_tt.py` | 6, 9 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `find_tiktok_video.py` | 4, 6 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `framing_test.py` | 2, 6, 7 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `hourly_poster.py` | 11, 25, 27 | `queue.json); never posts while /home/abel/clipsdaily/STOP exists (same` |
| `make_speech.py` | 4 | `gTTS(text, lang="en").save("/home/abel/clipsdaily/recordings/speech.mp3")` |
| `motion_test.py` | 2, 6, 8 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `patch_cadence.py` | 4, 79 | `p = Path("/home/abel/clipsdaily/hourly_poster.py")` |
| `patch_captions.py` | 17 | `BASE = "/home/abel/clipsdaily"` |
| `patch_cutter.py` | 2 | `p = Path("/home/abel/clipsdaily/cutter.py")` |
| `patch_cutter_fullframe.py` | 2 | `p = Path("/home/abel/clipsdaily/cutter.py")` |
| `patch_cutter_hook.py` | 4 | `p = Path("/home/abel/clipsdaily/cutter.py")` |
| `patch_cutter_hook2.py` | 4 | `p = Path("/home/abel/clipsdaily/cutter.py")` |
| `patch_cutter_motion.py` | 2 | `p = Path("/home/abel/clipsdaily/cutter.py")` |
| `patch_hook_gate.py` | 2 | `p = Path("/home/abel/clipsdaily/cutter.py")` |
| `patch_hook_match.py` | 2 | `p = Path("/home/abel/clipsdaily/cutter.py")` |
| `patch_poster.py` | 4, 39 | `p = Path("/home/abel/clipsdaily/post_tiktok_fixed.py")` |
| `patch_poster_failed.py` | 2 | `p = Path("/home/abel/clipsdaily/hourly_poster.py")` |
| `patch_tiktok.py` | 2 | `p = Path("/home/abel/clipsdaily/post_tiktok_fixed.py")` |
| `post_now.py` | 15, 20 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `post_one.py` | 11, 16 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `post_speed.py` | 6, 9 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `post_tiktok_fixed.py` | 16, 21, 23, 25, 148 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `post_tiktok_only.py` | 5, 7 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `post_tt_one.py` | 6 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `post_yt_batch.py` | 8, 13 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `queue_seed.py` | 23, 27, 33 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `recorder.py` | 27, 28 | `STREAMLINK = ("/home/abel/.local/bin/streamlink"` |
| `recover_9805.py` | 6 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `recut_fullframe.py` | 13 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `recut_jynxzi2075.py` | 6, 10, 12 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `restart_maintainer.py` | 5, 29 | `HERE = Path("/home/abel/clipsdaily")` |
| `tt_check.py` | 2 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `tt_post_9805.py` | 6, 10 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `tt_retry.py` | 6, 10 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `tt_verify_hk.py` | 5, 8 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `vod.py` | 4, 38 | `(free, open source, installed at /home/abel/.local/bin/TwitchDownloaderCLI)` |
| `vod_batch.py` | 2, 11 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `vod_cut.py` | 2, 6, 7, 11 | `sys.path.insert(0, "/home/abel/clipsdaily")` |
| `vod_cut_resume.py` | 2, 6, 7, 8 | `sys.path.insert(0, "/home/abel/clipsdaily")` |

### Files that resolve paths from their own location (portable)

These use `Path(__file__).resolve().parent` and work wherever the repo is cloned:

- `auth_instagram.py`
- `auth_tiktok.py`
- `auth_youtube.py`
- `auto_submit.py`
- `campaign_cut.py`
- `campaign_watcher.py`
- `campaigns.py`
- `chat.py`
- `cleanup.py`
- `cutter.py`
- `earnings.py`
- `eligibility_gate.py`
- `poster.py`
- `recorder.py`
- `runner.py`
- `vod.py`

Full detail (every matching line):

```
auth_instagram.py:6: cd /home/abel/clipsdaily
auth_tiktok.py:6: /home/abel/clipsdaily/.auth/tiktok_cookies.txt  (Netscape format)
auth_tiktok.py:14: sudo -n -u abel bash -c "mkdir -p /home/abel/clipsdaily/.auth
auth_tiktok.py:15: && cp /tmp/tiktok_cookies.txt /home/abel/clipsdaily/.auth/
auth_tiktok.py:16: && chmod 700 /home/abel/clipsdaily/.auth
auth_tiktok.py:17: && chmod 600 /home/abel/clipsdaily/.auth/tiktok_cookies.txt"
auth_youtube.py:8: /home/abel/clipsdaily/.auth/youtube_client_secrets.json (mode 0600).
auth_youtube.py:14: cd /home/abel/clipsdaily && python3 auth_youtube.py
auth_youtube_manual.py:3: AUTH_DIR = Path("/home/abel/clipsdaily/.auth")
chat.py:42: YT_DLP = "/home/abel/.local/bin/yt-dlp"
check_tiktok_profile.py:4: sys.path.insert(0, "/home/abel/clipsdaily")
check_tiktok_profile.py:6: COOKIES = "/home/abel/clipsdaily/.auth/tiktok_cookies.txt"
cut_speed_expedia.py:11: sys.path.insert(0, "/home/abel/clipsdaily")
cut_speed_expedia.py:14: REC = Path("/home/abel/clipsdaily/vod/2921253522_expedia_tail.mp4")
cut_speed_expedia.py:15: OUT = Path("/home/abel/clipsdaily/clips")
delete_shorts.py:3: sys.path.insert(0, "/home/abel/clipsdaily")
diag_tiktok.py:5: sys.path.insert(0, "/home/abel/clipsdaily")
diag_tiktok.py:10: CLIP = "/home/abel/clipsdaily/clips/speed-expedia-japan_tiktok70s.mp4"
diag_tiktok.py:12: COOKIES = "/home/abel/clipsdaily/.auth/tiktok_cookies.txt"
diag_tiktok.py:13: OUT = Path("/home/abel/clipsdaily/diag_tiktok.json")
diag_tiktok.py:63: page.screenshot(path="/home/abel/clipsdaily/diag_tiktok.png", full_page=False)
eligibility_gate.py:41: FFPROBE = shutil.which("ffprobe") or "/home/abel/.local/bin/ffprobe"
eligibility_gate.py:42: FFMPEG = shutil.which("ffmpeg") or "/home/abel/.local/bin/ffmpeg"
fail_9805_tt.py:6: sys.path.insert(0, "/home/abel/clipsdaily")
fail_9805_tt.py:9: HERE = Path("/home/abel/clipsdaily")
find_tiktok_video.py:4: sys.path.insert(0, "/home/abel/clipsdaily")
find_tiktok_video.py:6: COOKIES = "/home/abel/clipsdaily/.auth/tiktok_cookies.txt"
framing_test.py:2: sys.path.insert(0, "/home/abel/clipsdaily")
framing_test.py:6: Path("/home/abel/clipsdaily/vod/2921253522_expedia_tail.mp4"),
framing_test.py:7: 151, 10, Path("/home/abel/clipsdaily/clips/framing-test.mp4"))
hourly_poster.py:11: queue.json); never posts while /home/abel/clipsdaily/STOP exists (same
hourly_poster.py:25: sys.path.insert(0, "/home/abel/clipsdaily")
hourly_poster.py:27: HERE = Path("/home/abel/clipsdaily")
make_speech.py:4: gTTS(text, lang="en").save("/home/abel/clipsdaily/recordings/speech.mp3")
motion_test.py:2: sys.path.insert(0, "/home/abel/clipsdaily")
motion_test.py:6: Path("/home/abel/clipsdaily/clips/framing-test.mp4"),
motion_test.py:8: Path("/home/abel/clipsdaily/clips"),
patch_cadence.py:4: p = Path("/home/abel/clipsdaily/hourly_poster.py")
patch_cadence.py:79: q = Path("/home/abel/clipsdaily/queue_seed.py")
patch_captions.py:17: BASE = "/home/abel/clipsdaily"
patch_cutter.py:2: p = Path("/home/abel/clipsdaily/cutter.py")
patch_cutter_fullframe.py:2: p = Path("/home/abel/clipsdaily/cutter.py")
patch_cutter_hook.py:4: p = Path("/home/abel/clipsdaily/cutter.py")
patch_cutter_hook2.py:4: p = Path("/home/abel/clipsdaily/cutter.py")
patch_cutter_motion.py:2: p = Path("/home/abel/clipsdaily/cutter.py")
patch_hook_gate.py:2: p = Path("/home/abel/clipsdaily/cutter.py")
patch_hook_match.py:2: p = Path("/home/abel/clipsdaily/cutter.py")
patch_poster.py:4: p = Path("/home/abel/clipsdaily/post_tiktok_fixed.py")
patch_poster.py:39: p = Path("/home/abel/clipsdaily/poster.py")
patch_poster_failed.py:2: p = Path("/home/abel/clipsdaily/hourly_poster.py")
patch_tiktok.py:2: p = Path("/home/abel/clipsdaily/post_tiktok_fixed.py")
post_now.py:15: sys.path.insert(0, "/home/abel/clipsdaily")
post_now.py:20: HERE = Path("/home/abel/clipsdaily")
post_one.py:11: sys.path.insert(0, "/home/abel/clipsdaily")
post_one.py:16: HERE = Path("/home/abel/clipsdaily")
post_speed.py:6: sys.path.insert(0, "/home/abel/clipsdaily")
post_speed.py:9: CLIPS = Path("/home/abel/clipsdaily/clips")
post_tiktok_fixed.py:16: sys.path.insert(0, "/home/abel/clipsdaily")
post_tiktok_fixed.py:21: COOKIES = "/home/abel/clipsdaily/.auth/tiktok_cookies.txt"
post_tiktok_fixed.py:23: "japan": ("/home/abel/clipsdaily/clips/speed-expedia-japan_tiktok70s.mp4",
post_tiktok_fixed.py:25: "hongkong": ("/home/abel/clipsdaily/clips/speed-expedia-hongkong_tiktok90s.mp4",
post_tiktok_fixed.py:148: page.screenshot(path=f"/home/abel/clipsdaily/tt_{label}_noconfirm.png")
post_tiktok_only.py:5: sys.path.insert(0, "/home/abel/clipsdaily")
post_tiktok_only.py:7: CLIPS = Path("/home/abel/clipsdaily/clips")
post_tt_one.py:6: sys.path.insert(0, "/home/abel/clipsdaily")
post_yt_batch.py:8: sys.path.insert(0, "/home/abel/clipsdaily")
post_yt_batch.py:13: cfg = yaml.safe_load(open("/home/abel/clipsdaily/config.yaml"))
queue_seed.py:23: sys.path.insert(0, "/home/abel/clipsdaily")
queue_seed.py:27: HERE = Path("/home/abel/clipsdaily")
queue_seed.py:33: TDCLI = "/home/abel/.local/bin/TwitchDownloaderCLI"
recorder.py:27: STREAMLINK = ("/home/abel/.local/bin/streamlink"
recorder.py:28: if Path("/home/abel/.local/bin/streamlink").exists()
recover_9805.py:6: sys.path.insert(0, "/home/abel/clipsdaily")
recut_fullframe.py:13: sys.path.insert(0, "/home/abel/clipsdaily")
recut_jynxzi2075.py:6: sys.path.insert(0, "/home/abel/clipsdaily")
recut_jynxzi2075.py:10: crop = Path("/home/abel/clipsdaily/vod/2928767125_2075_crop.mp4")
recut_jynxzi2075.py:12: OUT = Path("/home/abel/clipsdaily/clips/vod_batch")
restart_maintainer.py:5: HERE = Path("/home/abel/clipsdaily")
restart_maintainer.py:29: "cd /home/abel/clipsdaily && python3 queue_seed.py --maintain "
tt_check.py:2: sys.path.insert(0, "/home/abel/clipsdaily")
tt_post_9805.py:6: sys.path.insert(0, "/home/abel/clipsdaily")
tt_post_9805.py:10: HERE = Path("/home/abel/clipsdaily")
tt_retry.py:6: sys.path.insert(0, "/home/abel/clipsdaily")
tt_retry.py:10: HERE = Path("/home/abel/clipsdaily")
tt_verify_hk.py:5: sys.path.insert(0, "/home/abel/clipsdaily")
tt_verify_hk.py:8: COOKIES = "/home/abel/clipsdaily/.auth/tiktok_cookies.txt"
vod.py:4: (free, open source, installed at /home/abel/.local/bin/TwitchDownloaderCLI)
vod.py:38: TDCLI = "/home/abel/.local/bin/TwitchDownloaderCLI"
vod_batch.py:2: sys.path.insert(0, "/home/abel/clipsdaily")
vod_batch.py:11: work = Path("/home/abel/clipsdaily/vod")
vod_cut.py:2: sys.path.insert(0, "/home/abel/clipsdaily")
vod_cut.py:6: TDCLI = "/home/abel/.local/bin/TwitchDownloaderCLI"
vod_cut.py:7: WORK = Path("/home/abel/clipsdaily/vod")
vod_cut.py:11: OUT = Path("/home/abel/clipsdaily/clips/vod_batch")
vod_cut_resume.py:2: sys.path.insert(0, "/home/abel/clipsdaily")
vod_cut_resume.py:6: TDCLI = "/home/abel/.local/bin/TwitchDownloaderCLI"
vod_cut_resume.py:7: WORK = Path("/home/abel/clipsdaily/vod")
vod_cut_resume.py:8: OUT = Path("/home/abel/clipsdaily/clips/vod_batch")
```
