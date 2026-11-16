"""Post the next pending queue clip RIGHT NOW (one-off, extra on top of
the hourly schedule). YouTube Shorts (30s) + TikTok (60-90s variant,
or the 30s as fallback when no variant exists), both verified live.
Stages the Instagram outbox for the parent VM. Updates queue.json.
Prints a JSON result with URLs + post times. Posts nothing to
Content Rewards.
Usage: python3 post_now.py
"""
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, "/home/abel/clipsdaily")
from poster import post_youtube  # noqa: E402
from post_tiktok_fixed import post_file  # noqa: E402
from hourly_poster import verify_youtube, stage_instagram, CONFIG  # noqa: E402

HERE = Path("/home/abel/clipsdaily")
QUEUE_FILE = HERE / "queue" / "queue.json"


def main():
    entries = json.loads(QUEUE_FILE.read_text())
    pending = [e for e in entries if e["status"] in ("pending", "partial")]
    if not pending:
        print(json.dumps({"ok": False, "error": "queue empty"}))
        return
    entry = pending[0]
    hour_label = time.strftime("%Y-%m-%dT%H:00")
    print(f"[now] posting {entry['id']} (extra immediate post)", flush=True)
    try:
        stage_instagram(entry, hour_label)
        print(f"[now] instagram staged in ig-outbox/{entry['id']}/", flush=True)
    except Exception as e:
        print(f"[now] instagram staging FAILED: {e}", flush=True)
    result = {"ok": True, "clip_id": entry["id"],
              "posted_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    # YouTube Shorts (30s)
    try:
        vid = post_youtube(Path(entry["clip30"]), entry["streamer"], CONFIG,
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
        print(f"[now] YOUTUBE LIVE {url} ({detail})", flush=True)
    except Exception as e:
        entry["yt_retries"] = entry.get("yt_retries", 0) + 1
        result["youtube_error"] = str(e)
        print(f"[now] youtube FAILED: {e}", flush=True)
    # TikTok: 60-90s variant if present, else the 30s (fallback per
    # Abel's hourly order — no Creator Rewards on a 30s clip, but the
    # hourly cadence on TikTok is kept).
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
            from poster import post_tiktok
            url = post_tiktok(Path(tt_file), entry["streamer"], CONFIG,
                              entry.get("platform", "twitch"),
                              caption=entry["caption_tiktok"])
        entry["tt_url"] = url
        result["tiktok_url"] = url
        result["tiktok_posted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        result["tiktok_fallback_30s"] = fallback
        print(f"[now] TIKTOK LIVE {url}"
              + (" (30s fallback)" if fallback else ""), flush=True)
    except Exception as e:
        entry["tt_retries"] = entry.get("tt_retries", 0) + 1
        result["tiktok_error"] = str(e)
        print(f"[now] tiktok FAILED: {e}", flush=True)
    yt_done = bool(entry.get("yt_url")) and entry["yt_url"] != "FAILED"
    tt_done = bool(entry.get("tt_url")) and entry["tt_url"] != "FAILED"
    entry["status"] = ("posted" if (yt_done and tt_done)
                       else "partial" if (yt_done or tt_done) else "pending")
    entry["history"].append({
        "hour": hour_label + " (immediate)", "yt_url": entry.get("yt_url"),
        "tt_url": entry.get("tt_url"), "status": entry["status"],
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    # refresh outbox meta with the live URLs
    try:
        stage_instagram(entry, hour_label)
    except Exception:
        pass
    tmp = QUEUE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    tmp.replace(QUEUE_FILE)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
