"""VOD fallback mode: recover clips from a finished stream.

Covers a missed live moment or runner downtime. Uses TwitchDownloaderCLI
(free, open source, installed at /home/abel/.local/bin/TwitchDownloaderCLI)
to download a finished stream's chat as chat.json plus the VOD itself,
runs the SAME 10-second spike detector offline over the chat, and cuts
the same vertical captioned clips with cutter.py.

TwitchDownloader chat.json format: {"comments": [{"created_at": ...,
"content_offset_seconds": float, ...}, ...]} — content_offset_seconds
is seconds from the VOD start, which lines up with cutter.py's
spike_seconds exactly like the live chat log does.

Usage:
  python3 vod.py <vod-url-or-id> [--max-clips N] [--out dir]
  python3 vod.py --chat <chat.json> --video <video-file> [--max-clips N]
      # offline test mode: skip the download, use local files.

Chat download is small (a few MB). The VOD video is big (several GB
per hour at 1080p) — vod.py downloads it only when --video is not
given. Nothing posts automatically in VOD mode unless poster.py is
called with --post; by default clips land in clips/ for the normal
posting path to pick up.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from .paths import runtime_home
HERE = runtime_home()

from .chat import detect_spikes          # noqa: E402
from .cutter import make_clip            # noqa: E402

TDCLI = "/home/abel/.local/bin/TwitchDownloaderCLI"


def vod_id(url_or_id):
    """Accept a full twitch.tv/videos/<id> URL or a bare numeric id."""
    s = str(url_or_id).strip().rstrip("/")
    if "/videos/" in s:
        s = s.split("/videos/")[-1]
    return s.split("?")[0].split("/")[0]


def download_chat(vod, out_path):
    cmd = [TDCLI, "chatdownload", "--id", vod, "-o", str(out_path),
           "--collision", "overwrite"]
    print(f"[vod] downloading chat for VOD {vod}", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"chatdownload failed: {r.stderr[-500:]}")
    return out_path


def download_video(vod, out_path):
    cmd = [TDCLI, "videodownload", "--id", vod, "-o", str(out_path),
           "--quality", "1080p60", "--collision", "overwrite"]
    print(f"[vod] downloading VOD {vod} (this is the slow, big part)",
          flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    if r.returncode != 0:
        raise RuntimeError(f"videodownload failed: {r.stderr[-500:]}")
    return out_path


def chat_counts(chat_json, window_seconds=10):
    """Bucket chat.json comments into per-window counts. Returns
    (counts, window_seconds, duration_seconds)."""
    with open(chat_json) as f:
        data = json.load(f)
    offsets = [c.get("content_offset_seconds", 0)
               for c in data.get("comments", [])]
    if not offsets:
        return [], window_seconds, 0.0
    duration = max(offsets)
    n = int(duration // window_seconds) + 1
    counts = [0] * n
    for o in offsets:
        counts[int(o // window_seconds)] += 1
    return counts, window_seconds, duration


def find_spikes(chat_json, multiplier=3.0, min_messages=20,
                window_seconds=10):
    """Run the live detector offline. Returns spike records with
    seconds_in + intensity, strongest first."""
    counts, _, duration = chat_counts(chat_json, window_seconds)
    idxs = detect_spikes(counts, multiplier, min_messages)
    import statistics
    from collections import deque
    spikes = []
    window = deque(maxlen=30)
    medians = {}
    for i, c in enumerate(counts):
        if len(window) >= 5:
            medians[i] = statistics.median(window)
        window.append(c)
    for i in idxs:
        med = medians.get(i, 0)
        spikes.append({"seconds_in": round(i * window_seconds
                                           + window_seconds / 2, 1),
                       "messages": counts[i], "median": med,
                       "intensity": round(counts[i] / med, 2) if med else 0,
                       "window": i})
    spikes.sort(key=lambda s: s["intensity"], reverse=True)
    print(f"[vod] {len(counts)} windows over {duration:.0f}s, "
          f"{len(spikes)} spikes", flush=True)
    return spikes


def run_vod(vod, max_clips=5, chat_path=None, video_path=None,
            post=False, config=None):
    """Full fallback run. Returns the list of clip Paths cut."""
    work = HERE / "vod"
    work.mkdir(exist_ok=True)
    vid = vod_id(vod) if vod else "local"
    if chat_path is None:
        chat_path = work / f"{vid}_chat.json"
        download_chat(vid, chat_path)
    if video_path is None:
        video_path = work / f"{vid}.mp4"
        download_video(vid, video_path)
    spikes = find_spikes(chat_path)
    clips = []
    cfg = config or {}
    for spike in spikes[:max_clips]:
        try:
            clip = make_clip(Path(video_path), spike["seconds_in"],
                             f"vod_{vid}",
                             clip_seconds=cfg.get("clip_length_seconds", 30),
                             model=cfg.get("whisper_model", "base"))
        except Exception as e:
            print(f"[vod] cut failed @{spike['seconds_in']}s: {e}",
                  flush=True)
            continue
        clips.append(clip)
        print(f"[vod] clip {clip} (intensity {spike['intensity']}x, "
              f"{spike['messages']} msgs)", flush=True)
        if post:
            from .poster import post_all
            post_all(clip, f"vod_{vid}", cfg)
    return clips


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("vod", nargs="?", help="twitch.tv/videos/<id> or id")
    ap.add_argument("--chat", help="local chat.json (skip download)")
    ap.add_argument("--video", help="local video file (skip download)")
    ap.add_argument("--max-clips", type=int, default=5)
    ap.add_argument("--post", action="store_true",
                    help="post clips via poster.py (default: just cut)")
    args = ap.parse_args()
    if not args.vod and not (args.chat and args.video):
        ap.error("give a VOD id/URL, or --chat + --video for offline mode")
    clips = run_vod(args.vod, max_clips=args.max_clips,
                    chat_path=Path(args.chat) if args.chat else None,
                    video_path=Path(args.video) if args.video else None,
                    post=args.post)
    print(f"[vod] done, {len(clips)} clips")
