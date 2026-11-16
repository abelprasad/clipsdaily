"""Cut both Speed Expedia campaign clips from the VOD tail.

Tail = VOD 2921253522, 2:56:29-end (tail-relative offsets = VOD s - 10589).
Uses cutter.py internals for exact windows (not spike-anchored).
TikTok versions get loudness normalized to -14 LUFS after caption burn.
"""
import subprocess
import sys
from pathlib import Path

from . import cutter

REC = Path("/home/abel/clipsdaily/vod/2921253522_expedia_tail.mp4")
OUT = Path("/home/abel/clipsdaily/clips")
CHANNEL = "ishowspeed"

JOBS = [
    # (stem, start_tail_s, length_s, tiktok_normalize)
    ("speed-expedia-japan_30s", 151, 30, False),
    ("speed-expedia-japan_tiktok70s", 146, 70, True),
    ("speed-expedia-hongkong_30s", 311, 30, False),
    ("speed-expedia-hongkong_tiktok90s", 291, 90, True),
]

def loudnorm_14(path):
    tmp = path.with_suffix(".loud.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(path),
        "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", str(tmp),
    ], check=True, capture_output=True)
    tmp.replace(path)
    print(f"[cut] loudnorm -14 LUFS applied: {path}", flush=True)

def main():
    print(f"[cut] source duration: {cutter.probe_duration(REC):.1f}s", flush=True)
    for stem, start, length, norm in JOBS:
        raw = OUT / f"{stem}_raw.mp4"
        print(f"[cut] {stem}: tail {start}s +{length}s", flush=True)
        cutter._cut_segment(REC, start, length, raw)
        final = cutter._caption_and_burn(raw, stem, CHANNEL, "small", OUT)
        raw.unlink(missing_ok=True)
        if norm:
            loudnorm_14(final)
        d = cutter.probe_duration(final)
        print(f"[cut] DONE {final} duration={d:.1f}s size={final.stat().st_size}", flush=True)
    print("[cut] ALL DONE", flush=True)

if __name__ == "__main__":
    main()
