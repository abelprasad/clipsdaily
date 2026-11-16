"""Post specific clips to YouTube Shorts with explicit titles/captions.
Usage: python3 post_yt_batch.py jobs.json
jobs.json: [{"clip": "/abs/path.mp4", "channel": "ishowspeed",
             "title": "...", "caption": "..."}]
Prints the Shorts URL per job. Verifies nothing itself — caller checks live.
"""
import sys, json
import yaml
from pathlib import Path
from .poster import post_youtube

cfg = yaml.safe_load(open("/home/abel/clipsdaily/config.yaml"))
jobs = json.load(open(sys.argv[1]))
for j in jobs:
    clip = Path(j["clip"])
    assert clip.exists(), f"missing {clip}"
    vid = post_youtube(clip, j["channel"], cfg, caption=j["caption"], title=j["title"])
    print(f"[yt] {clip.name} -> https://youtube.com/shorts/{vid}", flush=True)
print("[yt] ALL DONE", flush=True)
