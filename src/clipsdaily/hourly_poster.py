"""Half-hour poster for clipsdaily: one clip to TikTok (+ staged
Instagram) at :00 and :30 every hour, and to YouTube on 8 slots/day
only (:00 of 00, 03, 06, 09, 12, 15, 18, 21), from queue/queue.json.

Runs in tmux `clipsdaily-hourly`. Takes the next pending entry, stages
the Instagram outbox first, posts YouTube Shorts (30s) and TikTok
(60-90s variant, or the 30s as a fallback per Abel's hourly order),
verifies EACH post is actually live before marking it posted, and
logs everything to logs/hourly-YYYYMMDD.log.

YouTube 8/day (Nov 16, 2026): the channel hit YouTube's daily upload
limit at 9 posts on Nov 15, so 2/hour (48/day) re-hits the limit
within hours. A YouTube uploadLimitExceeded never burns a retry.
Instagram meta rule: ig-outbox/meta.json status is IG state only —
"staged" until the IG cron posts it, "posted" after — YouTube/TikTok
outcomes must never flip it (that bug silently killed the IG leg on
Nov 16: failed YT/TT slots wrote "failed"/"pending" into the meta and
the IG cron only posts "staged").

Safety: never posts the same clip twice (status transitions in
queue.json); never posts while /home/abel/clipsdaily/STOP exists (same
kill switch as the runner); a failed platform is retried next hour
(max 2 retries, then marked failed and the queue moves on). Posts
nothing to Content Rewards. Instagram is staged only — the parent VM
posts Reels from ig-outbox/ via instagram-cli.
"""
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, "/home/abel/clipsdaily")

HERE = Path("/home/abel/clipsdaily")
QUEUE_DIR = HERE / "queue"
QUEUE_FILE = QUEUE_DIR / "queue.json"
OUTBOX = HERE / "ig-outbox"
STOP_FILE = HERE / "STOP"
LOGS = HERE / "logs"
CONFIG = {"platforms": {"youtube": True, "tiktok": True, "instagram": False}}
MAX_RETRIES = 2
YT_HOURS = {0, 3, 6, 9, 12, 15, 18, 21}  # YouTube slots: 8/day


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with open(LOGS / ("hourly-%s.log" % time.strftime("%Y%m%d")), "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_queue():
    if not QUEUE_FILE.exists():
        return []
    try:
        return json.loads(QUEUE_FILE.read_text())
    except Exception:
        return []


def save_queue(entries):
    tmp = QUEUE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    tmp.replace(QUEUE_FILE)


def next_slot():
    """Next :00 or :30 boundary (two clips per hour, from Nov 15 21:00)."""
    now = datetime.now()
    if now.minute < 30:
        return now.replace(minute=30, second=0, microsecond=0)
    return (now.replace(minute=0, second=0, microsecond=0)
            + timedelta(hours=1))


def is_youtube_slot(hour_label):
    """True only on YouTube slots: :00 of 00, 03, 06, 09, 12, 15, 18,
    21 (8/day). hour_label looks like "2026-11-16T09:00"."""
    try:
        return hour_label[14:16] == "00" and int(hour_label[11:13]) in YT_HOURS
    except Exception:
        return False


def verify_youtube(vid):
    """Confirm a YouTube video id exists and is public."""
    try:
        from poster import _yt_service
        yt = _yt_service()
        resp = yt.videos().list(part="status,snippet", id=vid).execute()
        items = resp.get("items", [])
        if not items:
            return False, "video id not found via API"
        st = items[0].get("status", {})
        title = items[0].get("snippet", {}).get("title", "")
        return st.get("privacyStatus") == "public", (
            "privacy=%s title=%r" % (st.get("privacyStatus"), title))
    except Exception as e:
        return False, "verify error: %s" % e


def stage_instagram(entry, hour_label):
    """Stage 30s + caption + meta for the parent VM's IG post."""
    out = OUTBOX / entry["id"]
    out.mkdir(parents=True, exist_ok=True)
    src = Path(entry["clip30"])
    if src.exists():
        shutil.copy2(src, out / "clip30.mp4")
    (out / "caption.txt").write_text(entry["caption_ig"])
    try:
        dt = datetime.strptime(hour_label, "%Y-%m-%dT%H:%M")
        ig_slot = (dt + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
    except Exception:
        ig_slot = hour_label
    meta = {
        "clip_id": entry["id"], "scheduled_hour": hour_label,
        "ig_slot": ig_slot,
        "streamer": entry["streamer"], "title": entry["title"],
        "youtube_url": entry.get("yt_url"),
        "tiktok_url": entry.get("tt_url"),
        "status": "staged",
    }
    # Never un-stage a clip Instagram already posted: the IG cron flips
    # meta to "posted" (and writes .posted); a retry re-staging the same
    # clip must keep it "posted" or IG would post it twice.
    try:
        old = json.loads((out / "meta.json").read_text())
        ig_done = (out / ".posted").exists() or old.get("status") == "posted"
    except Exception:
        ig_done = (out / ".posted").exists()
    if ig_done:
        meta["status"] = "posted"
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    return out


def update_outbox_meta(entry):
    out = OUTBOX / entry["id"] / "meta.json"
    if not out.exists():
        return
    try:
        meta = json.loads(out.read_text())
    except Exception:
        meta = {}
    # IG state lives in this file alone: "staged" until the IG cron
    # posts it, "posted" after. YouTube/TikTok outcomes must never flip
    # it — writing entry["status"] ("failed"/"pending") here is what
    # silently killed the IG leg on Nov 16.
    ig_done = ((OUTBOX / entry["id"] / ".posted").exists()
               or meta.get("status") == "posted")
    meta.update({"youtube_url": entry.get("yt_url"),
                 "tiktok_url": entry.get("tt_url"),
                 "status": "posted" if ig_done else "staged"})
    out.write_text(json.dumps(meta, indent=2))


def post_entry(entry, hour_label):
    """Post missing platforms for one entry. Returns True if fully done."""
    from poster import post_youtube, post_tiktok
    channel = entry["streamer"]
    yt_slot = is_youtube_slot(hour_label)
    if not entry.get("yt_url"):
        if not yt_slot:
            log(f"{entry['id']}: youtube skipped (not a YouTube slot; "
                f"next at 00/03/06/09/12/15/18/21)")
        elif entry.get("yt_retries", 0) >= MAX_RETRIES:
            log(f"{entry['id']}: youtube retries exhausted, giving up")
            entry["yt_url"] = "FAILED"
        else:
            try:
                vid = post_youtube(Path(entry["clip30"]), channel, CONFIG,
                                   entry.get("platform", "twitch"),
                                   caption=entry["caption_yt"],
                                   title=entry["title"])
                url = "https://youtube.com/shorts/%s" % vid
                ok, detail = verify_youtube(vid)
                if not ok:
                    raise RuntimeError("youtube verify failed: %s" % detail)
                entry["yt_url"] = url
                log(f"{entry['id']}: YOUTUBE LIVE {url} ({detail})")
            except Exception as e:
                if "uploadLimitExceeded" in str(e):
                    # The daily limit is a quota, not a clip failure:
                    # do not burn a retry; try again on the next
                    # YouTube slot.
                    log(f"{entry['id']}: youtube LIMIT (uploadLimitExceeded) "
                        f"— will retry next YouTube slot, retries unchanged "
                        f"({entry.get('yt_retries', 0)})")
                else:
                    entry["yt_retries"] = entry.get("yt_retries", 0) + 1
                    log(f"{entry['id']}: youtube FAILED (try "
                        f"{entry['yt_retries']}): {e}")
    if not entry.get("tt_url"):
        if entry.get("tt_retries", 0) >= MAX_RETRIES:
            log(f"{entry['id']}: tiktok retries exhausted, giving up")
            entry["tt_url"] = "FAILED"
        else:
            tt_file = entry.get("tiktok") or entry["clip30"]
            fallback = not entry.get("tiktok")
            try:
                if fallback:
                    # No 60-90s variant yet: post the 30s anyway per
                    # Abel's hourly order (earns no Creator Rewards,
                    # but keeps the hourly cadence on TikTok).
                    # Subprocess (Nov 16, 2026): in-process TikTok
                    # leaks its Playwright loop; see post_file_subprocess.
                    from post_tiktok_fixed import post_file_subprocess
                    ok, url, detail = post_file_subprocess(
                        str(tt_file), entry["caption_tiktok"],
                        label=entry["id"])
                    if not ok or not url:
                        raise RuntimeError("tiktok post failed: %s" % detail)
                else:
                    url = post_tiktok(Path(tt_file), channel, CONFIG,
                                      entry.get("platform", "twitch"),
                                      caption=entry["caption_tiktok"])
                entry["tt_url"] = url
                log(f"{entry['id']}: TIKTOK LIVE {url}"
                    + (" (30s fallback)" if fallback else ""))
            except Exception as e:
                entry["tt_retries"] = entry.get("tt_retries", 0) + 1
                log(f"{entry['id']}: tiktok FAILED (try "
                    f"{entry['tt_retries']}): {e}")
    yt_done = bool(entry.get("yt_url")) and entry["yt_url"] != "FAILED"
    tt_done = bool(entry.get("tt_url")) and entry["tt_url"] != "FAILED"
    yt_dead = entry.get("yt_url") == "FAILED"
    tt_dead = entry.get("tt_url") == "FAILED"
    # A platform marked FAILED is resolved: the entry must not sit
    # "partial" forever and block the queue. If at least one platform
    # is live, the clip counts as posted (the failed one is done
    # retrying); if both failed, it is failed.
    if (yt_done or yt_dead) and (tt_done or tt_dead):
        entry["status"] = "posted" if (yt_done or tt_done) else "failed"
    elif yt_done or tt_done:
        entry["status"] = "partial"
    else:
        entry["status"] = "pending"
    entry["history"].append({
        "hour": hour_label, "yt_url": entry.get("yt_url"),
        "tt_url": entry.get("tt_url"), "status": entry["status"],
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    update_outbox_meta(entry)
    return entry["status"] in ("posted", "failed")


def main():
    log("hourly poster starting (tz check: local %s)"
        % time.strftime("%Y-%m-%d %H:%M:%S %Z"))
    while True:
        nxt = next_slot()
        wait = (nxt - datetime.now()).total_seconds()
        log("next post at %s (in %.0f min)"
            % (nxt.strftime("%H:%M"), wait / 60))
        if wait > 0:
            time.sleep(wait)
        slot_min = "30" if datetime.now().minute >= 30 else "00"
        hour_label = time.strftime("%Y-%m-%dT%H:") + slot_min
        if STOP_FILE.exists():
            log("STOP file present, skipping %s" % hour_label)
            time.sleep(60)
            continue
        entries = load_queue()
        pending = [e for e in entries if e["status"] in ("pending", "partial")]
        if not pending:
            log("queue empty at %s — nothing to post" % hour_label)
            time.sleep(60)
            continue
        yt_slot = is_youtube_slot(hour_label)
        if yt_slot:
            entry = pending[0]
        else:
            # Non-YouTube slots keep TikTok/IG at 2/hour: take the first
            # entry that still needs a TikTok post, instead of sitting
            # behind an entry that is only waiting on its YouTube slot.
            need_tt = [e for e in pending if not e.get("tt_url")]
            entry = need_tt[0] if need_tt else pending[0]
        log("posting %s at %s (streamer %s)%s"
            % (entry["id"], hour_label, entry["streamer"],
               "" if yt_slot else " [non-YouTube slot]"))
        try:
            stage_instagram(entry, hour_label)
            log(f"{entry['id']}: instagram staged in ig-outbox/")
        except Exception as e:
            log(f"{entry['id']}: instagram staging FAILED: {e}")
        try:
            done = post_entry(entry, hour_label)
        except Exception as e:
            log(f"{entry['id']}: unexpected post error: {e}")
            done = False
        save_queue(entries)
        log(f"{entry['id']}: slot done, status={entry['status']}")
        time.sleep(60)  # avoid double-firing within the same slot


if __name__ == "__main__":
    main()
