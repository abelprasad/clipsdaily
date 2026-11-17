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
TikTok API route (Nov 16, 2026): when config.yaml sets
`tiktok_api: true`, TikTok posts go through the official Content
Posting API (tiktok_api.py) instead of the Playwright cookie
session — no cookies, no browser, capped at ~15 Direct Posts/day
and 5 pending drafts/24h (enforced in tiktok_api.py; a cap hit
never burns a retry). A post that is on TikTok but not public yet
comes back as PENDING:<publish_id> (still processing) or
DRAFT:<publish_id> (waiting in the creator inbox); the next slot
reconciles it instead of re-uploading.

Instagram meta rule: ig-outbox/meta.json status is IG state only —
"staged" until the IG cron posts it, "posted" after — YouTube/TikTok
outcomes must never flip it (that bug silently killed the IG leg on
Nov 16: failed YT/TT slots wrote "failed"/"pending" into the meta and
the IG cron only posts "staged").

Safety: never posts the same clip twice (status transitions in
queue.json); never posts while STOP exists in the runtime home (same
kill switch as the runner); a failed platform is retried next hour
(max 2 retries, then marked failed and the queue moves on). Posts
nothing to Content Rewards. Instagram is staged only — the IG worker
posts Reels from ig-outbox/.

Campaigns (ClipForge package): when a campaign is active (joined in
campaigns.json), the poster prefers campaign_queue.json entries and
re-runs the eligibility gate at post time. A gate failure blocks the
entry — it is never posted, never submitted.
"""
import fcntl
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from .paths import runtime_home

HERE = runtime_home()
QUEUE_DIR = HERE / "queue"
QUEUE_FILE = QUEUE_DIR / "queue.json"
OUTBOX = HERE / "ig-outbox"
STOP_FILE = HERE / "STOP"
LOGS = HERE / "logs"
CONFIG = {"platforms": {"youtube": True, "tiktok": True, "instagram": False},
          "tiktok_api": False, "tiktok_api_mode": "direct"}


def refresh_config():
    """Merge config.yaml into CONFIG.

    Read every slot so flipping `tiktok_api: true` (or toggling a
    platform) in config.yaml takes effect without restarting this
    poster. Platforms default to on; a customer who disables one in
    config.yaml stops that leg here too.
    """
    try:
        import yaml
        cfg = yaml.safe_load((HERE / "config.yaml").read_text()) or {}
        CONFIG["tiktok_api"] = bool(cfg.get("tiktok_api", False))
        CONFIG["tiktok_api_mode"] = cfg.get("tiktok_api_mode", "direct")
        platforms = cfg.get("platforms") or {}
        for name in ("youtube", "tiktok", "instagram"):
            if name in platforms:
                CONFIG["platforms"][name] = bool(platforms[name])
    except Exception:
        pass


# ------------------------------------------------------------------ campaigns
CAMPAIGN_QUEUE_FILE = HERE / "campaign_queue.json"
CAMPAIGN_QUEUE_LOCK = CAMPAIGN_QUEUE_FILE.with_suffix(".lock")
CAMPAIGNS_FILE = HERE / "campaigns.json"


def load_campaign_queue():
    if not CAMPAIGN_QUEUE_FILE.exists():
        return []
    try:
        return json.loads(CAMPAIGN_QUEUE_FILE.read_text())
    except Exception:
        return []


def save_campaign_queue(entries):
    tmp = CAMPAIGN_QUEUE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    tmp.replace(CAMPAIGN_QUEUE_FILE)


def save_campaign_entry(entry):
    """Persist ONE campaign entry, merging onto current disk state
    (same race protection as save_entry)."""
    with open(CAMPAIGN_QUEUE_LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        fresh = load_campaign_queue()
        for i, fe in enumerate(fresh):
            if fe.get("id") == entry.get("id"):
                fresh[i] = entry
                break
        else:
            fresh.append(entry)
        save_campaign_queue(fresh)


def load_campaigns():
    try:
        data = json.loads(CAMPAIGNS_FILE.read_text())
    except Exception:
        return {}
    if isinstance(data, dict):
        return data.get("campaigns", {}) or {}
    return {}


def active_campaigns():
    """Joined, active campaigns with budget left (dict id -> campaign)."""
    out = {}
    for cid, c in load_campaigns().items():
        if not isinstance(c, dict):
            continue
        if c.get("state") != "joined":
            continue
        if c.get("status") not in (None, "active"):
            continue
        avail = c.get("budget_available_cents")
        if avail is not None and avail <= 0:
            continue
        out[cid] = c
    return out


def gate_campaign_entry(entry, campaign):
    """Re-run the eligibility gate at post time. Returns (ok, reason).
    A failure blocks the entry: never posted, never submitted."""
    try:
        from .eligibility_gate import gate_clip
        verdict = gate_clip(entry, campaign)
    except Exception as e:
        return False, "gate error: %s" % e
    if verdict.get("ok"):
        return True, ""
    return False, verdict.get("block_reason", "gate blocked") or "gate blocked"
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


QUEUE_LOCK = QUEUE_FILE.with_suffix(".lock")


def save_entry(entry):
    """Persist ONE entry's updated fields, merging onto the CURRENT
    disk state instead of rewriting the whole in-memory snapshot.

    Root cause (2026-11-16): main() loaded the queue at slot start
    and save_queue() rewrote the whole list at slot end. Anything
    staged mid-slot by runner.stage_to_queue() was silently wiped —
    that is how live-kick-adinross-72s vanished between 13:30:25 and
    13:35:25 (poster loaded 34 entries at 13:30:00, staging added the
    35th, poster saved its stale 34 at ~13:34). Re-reading disk here
    preserves mid-slot stagings. The lock serializes this
    read-modify-write against runner.stage_to_queue(), which takes
    the same lock file.
    """
    with open(QUEUE_LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        fresh = load_queue()
        for i, fe in enumerate(fresh):
            if fe.get("id") == entry.get("id"):
                fresh[i] = entry
                break
        else:
            fresh.append(entry)
        save_queue(fresh)


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
        from .poster import _yt_service
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
    from .poster import post_youtube, post_tiktok
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
    tt_url = entry.get("tt_url") or ""
    reconciled_failed = False
    if isinstance(tt_url, str) and tt_url.startswith(("PENDING:", "DRAFT:")):
        # A previous slot put the video on TikTok but it is not public
        # yet: reconcile the publish_id instead of re-uploading.
        pid = tt_url.split(":", 1)[1]
        kind = "DRAFT" if tt_url.startswith("DRAFT:") else "PENDING"
        try:
            from .tiktok_api import reconcile_pending
            out = reconcile_pending(pid)
            res = out[0] if out else {}
            if res.get("url"):
                entry["tt_url"] = res["url"]
                log(f"{entry['id']}: TIKTOK LIVE (reconciled {kind}) "
                    f"{res['url']}")
            elif res.get("status") == "failed":
                entry["tt_url"] = None
                entry["tt_retries"] = entry.get("tt_retries", 0) + 1
                # Do NOT re-upload in this same slot: the identical
                # file would fail the same way on TikTok's side.
                reconciled_failed = True
                log(f"{entry['id']}: tiktok {kind} FAILED on TikTok "
                    f"({res.get('fail_reason', '')}) — retry "
                    f"{entry['tt_retries']} next slot")
            else:
                log(f"{entry['id']}: tiktok still {kind.lower()} "
                    f"({res.get('status', 'unknown')}) — waiting, no retry")
        except Exception as e:
            log(f"{entry['id']}: tiktok reconcile failed: {e} — waiting")
    if not entry.get("tt_url") and not reconciled_failed:
        if entry.get("tt_retries", 0) >= MAX_RETRIES:
            log(f"{entry['id']}: tiktok retries exhausted, giving up")
            entry["tt_url"] = "FAILED"
        else:
            tt_file = entry.get("tiktok") or entry["clip30"]
            fallback = not entry.get("tiktok")
            try:
                # One call for both paths: post_tiktok routes to the
                # official API when CONFIG["tiktok_api"] is on, else
                # the Playwright cookie session. allow_short keeps the
                # 30s fallback (Abel's hourly order) — it earns no
                # Creator Rewards but keeps the hourly cadence.
                url = post_tiktok(Path(tt_file), channel, CONFIG,
                                  entry.get("platform", "twitch"),
                                  caption=entry["caption_tiktok"],
                                  allow_short=fallback)
                if url is False:
                    # API cap hit (or platform off): nothing posted,
                    # nothing to retry — the cap resets with time.
                    log(f"{entry['id']}: tiktok skipped (API cap) — "
                        f"will retry next slot, no retry burned")
                else:
                    entry["tt_url"] = url
                    if isinstance(url, str) and url.startswith(
                            ("PENDING:", "DRAFT:")):
                        log(f"{entry['id']}: tiktok {url.split(':')[0]} "
                            f"{url} — will reconcile next slot, no retry")
                    else:
                        log(f"{entry['id']}: TIKTOK LIVE {url}"
                            + (" (30s fallback)" if fallback else ""))
            except Exception as e:
                # TikTokUploadPending (poll timed out after the bytes
                # landed): record the publish_id, do NOT burn a retry
                # and do NOT re-upload — next slot reconciles it.
                try:
                    from .tiktok_api import TikTokUploadPending
                    pending = isinstance(e, TikTokUploadPending)
                except Exception:
                    pending = False
                if pending:
                    entry["tt_url"] = f"PENDING:{e.publish_id}"
                    log(f"{entry['id']}: tiktok PENDING {e.publish_id} "
                        f"— will reconcile next slot, no retry")
                else:
                    entry["tt_retries"] = entry.get("tt_retries", 0) + 1
                    log(f"{entry['id']}: tiktok FAILED (try "
                        f"{entry['tt_retries']}): {e}")
    yt_done = bool(entry.get("yt_url")) and entry["yt_url"] != "FAILED"
    tt_done = (bool(entry.get("tt_url"))
               and entry["tt_url"] != "FAILED"
               and not str(entry.get("tt_url")).startswith(
                   ("PENDING:", "DRAFT:")))
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


def pick_entry(hour_label):
    """Next entry to post: a campaign entry first when a campaign is
    active (gate re-checked at post time; a blocked entry is marked
    blocked and the next one is tried), else the normal queue pick.
    Returns (entry, is_campaign) or (None, False)."""
    active = active_campaigns()
    if active:
        cq = [e for e in load_campaign_queue()
              if e.get("status") in ("pending", "partial")]
        for entry in cq:
            campaign = active.get(entry.get("campaign_id"))
            if campaign is None:
                continue
            ok, reason = gate_campaign_entry(entry, campaign)
            if not ok:
                entry["status"] = "blocked"
                entry["block_reason"] = reason
                entry.setdefault("history", []).append({
                    "hour": hour_label, "status": "blocked",
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "block_reason": reason})
                save_campaign_entry(entry)
                log("%s: campaign gate BLOCKED at post time: %s"
                    % (entry["id"], reason))
                continue
            return entry, True
    entries = load_queue()
    pending = [e for e in entries if e["status"] in ("pending", "partial")]
    if not pending:
        return None, False
    if is_youtube_slot(hour_label):
        return pending[0], False
    need_tt = [e for e in pending
               if not e.get("tt_url")
               or str(e.get("tt_url")).startswith(("PENDING:", "DRAFT:"))]
    return (need_tt[0] if need_tt else pending[0]), False


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
        refresh_config()
        entry, is_campaign = pick_entry(hour_label)
        if entry is None:
            log("queue empty at %s — nothing to post" % hour_label)
            time.sleep(60)
            continue
        log("posting %s at %s (streamer %s)%s%s"
            % (entry["id"], hour_label, entry["streamer"],
               " [campaign]" if is_campaign else "",
               "" if is_youtube_slot(hour_label) else " [non-YouTube slot]"))
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
        if is_campaign:
            save_campaign_entry(entry)
        else:
            save_entry(entry)
        log(f"{entry['id']}: slot done, status={entry['status']}")
        time.sleep(60)  # avoid double-firing within the same slot


if __name__ == "__main__":
    main()
