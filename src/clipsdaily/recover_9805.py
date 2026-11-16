import json
import sys
import time
from pathlib import Path

from .queue_seed import CLIPS_DIR, WORK_DIR, build_texts, load_queue, save_queue, srt_phrase

clip_id = "ishowspeed-2928036561-9805s"
work = WORK_DIR / clip_id
final = work / "ishowspeed_40s.mp4"
srt = work / "ishowspeed_40s.srt"
assert final.exists(), "final missing"
final30 = CLIPS_DIR / ("%s_30s.mp4" % clip_id)
final.replace(final30)
if srt.exists():
    srt.replace(CLIPS_DIR / ("%s_30s.srt" % clip_id))
for p in work.glob("*"):
    try:
        p.unlink()
    except Exception:
        pass
try:
    work.rmdir()
except Exception:
    pass
phrase = srt_phrase(CLIPS_DIR / ("%s_30s.srt" % clip_id))
title, yt_desc, tt_cap, ig_cap = build_texts("ishowspeed", phrase, "2026-11-13")
entries = load_queue()
entry = next((e for e in entries if e["id"] == clip_id), None)
assert entry is not None, "entry missing"
entry.update({"clip30": str(final30), "tiktok": None, "phrase": phrase,
              "title": title, "caption_yt": yt_desc,
              "caption_tiktok": tt_cap, "caption_ig": ig_cap})
save_queue(entries)
print(json.dumps({"clip_id": clip_id, "status": entry["status"],
                  "yt_url": entry.get("yt_url"), "title": title,
                  "tiktok_caption": tt_cap}, indent=2))
