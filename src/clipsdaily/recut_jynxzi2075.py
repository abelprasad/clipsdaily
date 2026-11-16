"""Re-cut jynxzi 2075 with the CORRECT hook.
The spike at VOD 2075s is a chess checkmate win ("You Won! By Checkmate"),
not a Worlds teaser reaction. Old files are overwritten in place.
"""
import sys, os
from pathlib import Path
from .cutter import make_clip, make_tiktok_clip

crop = Path("/home/abel/clipsdaily/vod/2928767125_2075_crop.mp4")
assert crop.exists(), "crop missing"
OUT = Path("/home/abel/clipsdaily/clips/vod_batch")
hook = "JYNXZI WINS BY CHECKMATE"

clip = make_clip(crop, 40.0, "jynxzi", clip_seconds=30, model="small", hook=hook, out_dir=OUT)
os.replace(clip, OUT / "jynxzi_2075s.mp4")
print("[recut] 30s done", flush=True)
tt, method = make_tiktok_clip(crop, [{"seconds_in": 40.0, "intensity": 9.12}],
                              "jynxzi", model="small", hook=hook, out_dir=OUT)
os.replace(tt, OUT / "jynxzi_2075s_tiktok.mp4")
print(f"[recut] tiktok done method={method}", flush=True)
