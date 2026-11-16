import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/abel/clipsdaily")
from hourly_poster import stage_instagram

HERE = Path("/home/abel/clipsdaily")
QUEUE_FILE = HERE / "queue" / "queue.json"

entries = json.loads(QUEUE_FILE.read_text())
entry = next(e for e in entries if e["id"] == "ishowspeed-2928036561-9805s")
# TikTok failed 3x with the identical signature (Post click swallowed,
# no confirmation, Studio count stays 1) — systematic, not transient.
# Mark it FAILED so the 21:00 slot posts a new clip instead of burning
# the slot re-resolving this one. YouTube stays live.
entry["tt_url"] = "FAILED"
entry["status"] = "posted"
entry["history"].append({
    "hour": time.strftime("%Y-%m-%dT%H:00") + " (tiktok failed x3)",
    "yt_url": entry.get("yt_url"), "tt_url": "FAILED", "status": "posted",
    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
})
tmp = QUEUE_FILE.with_suffix(".json.tmp")
tmp.write_text(json.dumps(entries, indent=2))
tmp.replace(QUEUE_FILE)
# Re-stage the IG outbox with the FULL-FRAME 30s (the outbox still had
# the cropped file from 20:25) + refresh meta with the live YT URL.
stage_instagram(entry, time.strftime("%Y-%m-%dT%H:00"))
print(json.dumps({"clip_id": entry["id"], "status": entry["status"],
                  "yt_url": entry.get("yt_url"), "tt_url": "FAILED",
                  "outbox": "ig-outbox/%s/ (full-frame clip30.mp4)"
                            % entry["id"]}, indent=2))
