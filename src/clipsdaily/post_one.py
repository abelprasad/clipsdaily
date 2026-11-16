"""Post ONE queue entry by id (YT Shorts 30s + TikTok 60-90s variant or
30s fallback), verify each live, stage the IG outbox, update queue.json.
Usage: python3 post_one.py <clip_id> [slot_label]
slot_label defaults to the current half-hour slot.
"""
import json
import sys
import time
from pathlib import Path

from .poster import post_youtube, post_tiktok  # noqa: E402
from .post_tiktok_fixed import post_file  # noqa: E402
from .hourly_poster import verify_youtube, stage_instagram, CONFIG as HCONFIG  # noqa: E402

from .paths import runtime_home
HERE = runtime_home()
QUEUE_FILE = HERE / "queue" / "queue.json"


def main():
    clip_id = sys.argv[1]
    slot = sys.argv[2] if len(sys.argv) > 2 else None
    if slot is None:
        now = time.localtime()
        slot = time.strftime("%Y-%m-%dT%H:") + ("30" if now.tm_min >= 30
                                                else "00")
    entries = json.loads(QUEUE_FILE.read_text())
    entry = next(e for e in entries if e["id"] == clip_id)
    print(f"[post_one] {clip_id} slot {slot}", flush=True)
    try:
        stage_instagram(entry, slot)
        print(f"[post_one] instagram staged", flush=True)
    except Exception as e:
        print(f"[post_one] instagram staging FAILED: {e}", flush=True)
    result = {"ok": True, "clip_id": clip_id, "slot": slot,
              "posted_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        vid = post_youtube(Path(entry["clip30"]), entry["streamer"], HCONFIG,
                           entry.get("platform", "twitch"),
                           caption=entry["caption_yt"],
                           title=entry["title"])
        url = "https://youtube.com/shorts/%s" % vid
        ok, detail = verify_youtube(vid)
        if not ok:
            raise RuntimeError("youtube verify failed: %s" % detail)
        entry["yt_url"] = url
        result["youtube_url"] = url
        result["youtube_posted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        print(f"[post_one] YOUTUBE LIVE {url} ({detail})", flush=True)
    except Exception as e:
        entry["yt_retries"] = entry.get("yt_retries", 0) + 1
        result["youtube_error"] = str(e)
        print(f"[post_one] youtube FAILED: {e}", flush=True)
    try:
        tt_file = entry.get("tiktok") or entry["clip30"]
        fallback = not entry.get("tiktok")
        if fallback:
            ok, url, detail = post_file(str(tt_file),
                                        entry["caption_tiktok"],
                                        label=entry["id"])
            if not ok or not url:
                raise RuntimeError("tiktok post failed: %s" % detail)
        else:
            url = post_tiktok(Path(tt_file), entry["streamer"], HCONFIG,
                              entry.get("platform", "twitch"),
                              caption=entry["caption_tiktok"])
        entry["tt_url"] = url
        result["tiktok_url"] = url
        result["tiktok_posted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        result["tiktok_fallback_30s"] = fallback
        print(f"[post_one] TIKTOK LIVE {url}"
              + (" (30s fallback)" if fallback else ""), flush=True)
    except Exception as e:
        entry["tt_retries"] = entry.get("tt_retries", 0) + 1
        result["tiktok_error"] = str(e)
        print(f"[post_one] tiktok FAILED: {e}", flush=True)
    yt_done = bool(entry.get("yt_url")) and entry["yt_url"] != "FAILED"
    tt_done = bool(entry.get("tt_url")) and entry["tt_url"] != "FAILED"
    yt_dead = entry.get("yt_url") == "FAILED"
    tt_dead = entry.get("tt_url") == "FAILED"
    if (yt_done or yt_dead) and (tt_done or tt_dead):
        entry["status"] = "posted" if (yt_done or tt_done) else "failed"
    elif yt_done or tt_done:
        entry["status"] = "partial"
    else:
        entry["status"] = "pending"
    entry["history"].append({
        "hour": slot, "yt_url": entry.get("yt_url"),
        "tt_url": entry.get("tt_url"), "status": entry["status"],
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    try:
        stage_instagram(entry, slot)
    except Exception:
        pass
    tmp = QUEUE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    tmp.replace(QUEUE_FILE)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
