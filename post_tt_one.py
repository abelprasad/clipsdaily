"""Post ONE arbitrary clip to TikTok via the fixed poster flow.
Usage: python3 post_tt_one.py <clip.mp4> "<caption>" <label>
Prints ok/url/detail. Verifies via TikTok Studio before returning.
"""
import sys
sys.path.insert(0, "/home/abel/clipsdaily")
from post_tiktok_fixed import post_file

clip, caption, label = sys.argv[1], sys.argv[2], sys.argv[3]
ok, url, detail = post_file(clip, caption, label)
print(f"[tt] {label} ok={ok} url={url} detail={detail}", flush=True)
