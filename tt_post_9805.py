import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/abel/clipsdaily")
from post_tiktok_fixed import post_file
from hourly_poster import stage_instagram

HERE = Path("/home/abel/clipsdaily")
QUEUE_FILE = HERE / "queue" / "queue.json"

entries = json.loads(QUEUE_FILE.read_text())
entry = next(e for e in entries if e["id"] == "ishowspeed-2928036561-9805s")
print(f"[tt9805] posting FULL-FRAME {entry['id']} to TikTok", flush=True)
ok, url, detail = post_file(str(entry["clip30"]), entry["caption_tiktok"],
                            label=entry["id"] + "-fullframe")
print(f"[tt9805] ok={ok} url={url} detail={detail}", flush=True)
if ok and url:
    entry["tt_url"] = url
    entry["status"] = "posted"
    entry["history"].append({
        "hour": time.strftime("%Y-%m-%dT%H:00") + " (full-frame tiktok)",
        "yt_url": entry.get("yt_url"), "tt_url": url, "status": "posted",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    try:
        stage_instagram(entry, time.strftime("%Y-%m-%dT%H:00"))
        print("[tt9805] instagram staged", flush=True)
    except Exception as e:
        print(f"[tt9805] outbox refresh failed: {e}", flush=True)
else:
    entry["tt_retries"] = entry.get("tt_retries", 0) + 1
    print(f"[tt9805] FAILED, tt_retries now {entry['tt_retries']}", flush=True)
tmp = QUEUE_FILE.with_suffix(".json.tmp")
tmp.write_text(json.dumps(entries, indent=2))
tmp.replace(QUEUE_FILE)
print(json.dumps({"ok": ok, "tiktok_url": url, "detail": detail,
                  "tt_retries": entry.get("tt_retries", 0),
                  "status": entry["status"]}, indent=2))
