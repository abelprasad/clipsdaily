"""Campaign-mode cutter: cut clips ONLY from a campaign's eligible
footage window, gate them, and register them in campaign_queue.json.

Never writes queue/queue.json (owned by the hourly poster + queue
maintainer while they run) and never posts anything. The hourly
poster integration (prefer campaign_queue entries when a campaign is
active) is a separate, parent-approved step — see README section in
the report.

Flow per campaign:
  1. Load the campaign from campaigns.json. Refuse unless state is
     "joined", vod_id is set, and window_start_s is parsed.
  2. Pick moments: curated campaign["moments"] if present (each has
     spike_s, destination, hook, phrase), else rank chat spikes from
     the VOD chat file and keep only spikes whose whole clip range
     fits inside the window (and outside exclude_ranges).
  3. Video: campaign["local_video"] (+ local_video_offset_s) when set,
     else download a 160s crop around the spike via TwitchDownloaderCLI
     (same download_crop as queue_seed).
  4. Cut 30s + TikTok variant with cutter.py (full frame, one big hook
     at the start, no word captions). The TikTok variant is skipped
     when its 75s range would run past the window end.
  5. Build campaign captions (required mentions + hashtag + destination).
  6. Run eligibility_gate.gate_clip on the cut files. Gate fail ->
     entry status "blocked" with the reason (file kept for review).
     Gate pass -> entry status "pending" in campaign_queue.json.
  7. A clip is never queued twice (clip_id dedup).

Usage:
  python3 campaign_cut.py --campaign <id> [--max-clips N]
  python3 campaign_cut.py --campaign <id> --dry-run [--max-clips 1]
      dry-run cuts to campaign_work/dryrun_<clip_id>/, gates it,
      prints the verdict, and writes nothing to campaign_queue.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaigns import CAMPAIGNS_FILE, load_campaigns  # noqa: E402
from eligibility_gate import gate_clip  # noqa: E402

HERE = Path(__file__).resolve().parent
CAMPAIGN_QUEUE_FILE = HERE / "campaign_queue.json"
CAMPAIGN_CLIPS_DIR = HERE / "campaign_clips"
CAMPAIGN_WORK_DIR = HERE / "campaign_work"
LOG_FILE = HERE / "campaign_cut.log"


def log(msg):
    # Logs go to stderr: stdout stays pure JSON for machine consumers.
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True, file=sys.stderr)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


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


def build_campaign_texts(campaign, streamer, destination, phrase, hook):
    """Captions that satisfy the campaign's mention/hashtag rules.

    Cut down Nov 15, 2026, per Abel: one line. The required hashtag is
    the ONLY hashtag (campaigns require it; generic tags don't help
    reach). Brand, destination, and required mentions are appended
    only if the money line doesn't already name them, so the gate
    (mentions + hashtag + destination in every caption) still passes.
    """
    brand = campaign.get("brand") or ""
    hashtag = campaign.get("required_hashtag") or ""
    mentions = campaign.get("required_mentions") or []
    hook_title = (hook or "").strip().rstrip("!").title()
    title = ("%s | %s x %s %s" % (hook_title or "Clip", streamer,
                                  brand, hashtag)).strip()[:100]
    base = (phrase or hook or "clip").strip()
    parts = [base]
    for token in [brand, destination] + list(mentions):
        if token and token.lower() not in " ".join(parts).lower():
            parts.append(token)
    if hashtag:
        parts.append(hashtag)
    line = " ".join(" ".join(parts).split())
    return title, line, line, line


def pick_moments(campaign, max_clips):
    """Moments to cut: curated list, else ranked in-window chat spikes."""
    moments = campaign.get("moments") or []
    if moments:
        return [{
            "spike_s": float(m["spike_s"]),
            "intensity": float(m.get("intensity", 0)),
            "destination": m.get("destination"),
            "hook": m.get("hook"),
            "phrase": m.get("phrase", ""),
        } for m in moments[:max_clips]]
    from vod import download_chat, find_spikes
    vid = campaign["vod_id"]
    chat = HERE / "vod" / ("%s_chat.json" % vid)
    if not chat.exists():
        download_chat(vid, chat)
    spikes = find_spikes(chat)
    w_start = float(campaign["window_start_s"])
    w_end = campaign.get("window_end_s")
    w_end_f = float(w_end) if w_end is not None else None
    kept = []
    for s in sorted(spikes, key=lambda x: x.get("intensity", 0),
                    reverse=True):
        sec = float(s["seconds_in"])
        # Whole 30s clip (spike-20 .. spike+10) must fit in the window.
        if sec - 20 < w_start:
            continue
        if w_end_f is not None and sec + 10 > w_end_f:
            continue
        excluded = False
        for ex0, ex1 in campaign.get("exclude_ranges") or []:
            if sec - 20 < float(ex1) and sec + 10 > float(ex0):
                excluded = True
        if excluded:
            continue
        if all(abs(sec - k["spike_s"]) >= 120 for k in kept):
            kept.append({"spike_s": sec,
                         "intensity": float(s.get("intensity", 0)),
                         "destination": None, "hook": None, "phrase": ""})
        if len(kept) >= max_clips:
            break
    return kept


def cut_moment(campaign, moment, work_dir, out_dir, dry_run=False):
    """Cut 30s (+TikTok variant when it fits the window). Returns the
    entry dict (gate verdict included) or None on cut failure."""
    from cutter import make_clip, make_tiktok_clip
    from queue_seed import download_crop
    streamer = campaign["streamer"]
    vid = campaign["vod_id"]
    spike = float(moment["spike_s"])
    clip_id = "%s-%s-%ds" % (streamer, vid, int(spike))
    w_end = campaign.get("window_end_s")
    w_end_f = float(w_end) if w_end is not None else None
    # Video source: local window file when the campaign pins one.
    if campaign.get("local_video"):
        video = Path(campaign["local_video"])
        offset = float(campaign.get("local_video_offset_s") or 0)
        local = spike - offset
        crop = video
        cleanup_crop = False
    else:
        work_dir.mkdir(parents=True, exist_ok=True)
        crop = work_dir / "crop.mp4"
        download_crop(vid, spike - 40, spike + 120, crop)
        local = 40.0
        cleanup_crop = True
    out_dir.mkdir(parents=True, exist_ok=True)
    hook = moment.get("hook")
    try:
        clip30 = make_clip(crop, local, streamer, clip_seconds=30,
                           model="small", hook=hook, out_dir=work_dir)
    except Exception as e:
        log("%s: 30s cut FAILED: %s" % (clip_id, e))
        return None
    final30 = out_dir / ("%s_30s.mp4" % clip_id)
    clip30.replace(final30)
    tiktok = None
    # TikTok variant needs spike-20 .. spike+55 inside the window.
    if w_end_f is None or spike + 55 <= w_end_f:
        try:
            tt, method = make_tiktok_clip(
                crop, [{"seconds_in": local,
                        "intensity": moment.get("intensity", 0)}],
                streamer, model="small", hook=hook, out_dir=work_dir)
            if tt:
                tiktok = out_dir / ("%s_tiktok.mp4" % clip_id)
                tt.replace(tiktok)
                log("%s: tiktok variant (%s)" % (clip_id, method))
        except Exception as e:
            log("%s: tiktok variant failed: %s" % (clip_id, e))
    else:
        log("%s: tiktok variant skipped (75s would pass window end)"
            % clip_id)
    if cleanup_crop:
        try:
            crop.unlink(missing_ok=True)
        except Exception:
            pass
    vod_start = spike - 20
    vod_end = spike + 55 if tiktok else spike + 10
    phrase = moment.get("phrase") or ""
    title, yt_desc, tt_cap, ig_cap = build_campaign_texts(
        campaign, streamer, moment.get("destination"), phrase, hook)
    entry = {
        "id": clip_id, "streamer": streamer, "platform": "twitch",
        "vod_id": str(vid),
        "vod_date": campaign.get("vod_date") or "",
        "spike_seconds": spike, "intensity": moment.get("intensity", 0),
        "phrase": phrase, "destination": moment.get("destination"),
        "clip30": str(final30),
        "tiktok": str(tiktok) if tiktok else None,
        "title": title, "caption_yt": yt_desc,
        "caption_tiktok": tt_cap, "caption_ig": ig_cap,
        "campaign_id": campaign["id"],
        "campaign_title": campaign.get("title"),
        "vod_start_s": vod_start, "vod_end_s": vod_end,
        "framing": "full-frame",
        "status": "pending", "yt_retries": 0, "tt_retries": 0,
        "yt_url": None, "tt_url": None, "history": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    verdict = gate_clip(entry, campaign)
    entry["gate"] = verdict
    if verdict["ok"]:
        entry["status"] = "pending"
        log("%s: GATE PASS (%s)" % (clip_id, verdict["checks"]["window"]["detail"]))
    else:
        entry["status"] = "blocked"
        entry["block_reason"] = verdict["block_reason"]
        log("%s: GATE BLOCKED: %s" % (clip_id, verdict["block_reason"]))
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--campaign", required=True)
    ap.add_argument("--max-clips", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    campaigns = load_campaigns()
    campaign = campaigns.get(args.campaign)
    if not campaign:
        print(json.dumps({"ok": False, "error": "campaign not found"}))
        return 1
    if campaign.get("state") != "joined":
        print(json.dumps({"ok": False,
                          "error": "campaign state is %s, not joined"
                          % campaign.get("state")}))
        return 1
    if not campaign.get("vod_id"):
        print(json.dumps({"ok": False,
                          "error": "campaign has no resolved vod_id"}))
        return 1
    if campaign.get("window_start_s") is None:
        print(json.dumps({"ok": False,
                          "error": "campaign has no parsed window"}))
        return 1
    moments = pick_moments(campaign, args.max_clips)
    log("campaign %s: %d moment(s) to cut" % (campaign["id"], len(moments)))
    entries = [] if args.dry_run else load_campaign_queue()
    done = []
    for moment in moments:
        clip_id = "%s-%s-%ds" % (campaign["streamer"], campaign["vod_id"],
                                 int(float(moment["spike_s"])))
        if any(e["id"] == clip_id for e in entries):
            log("%s already in campaign queue, skipping" % clip_id)
            continue
        work_dir = (CAMPAIGN_WORK_DIR / ("dryrun_%s" % clip_id)
                    if args.dry_run else CAMPAIGN_WORK_DIR / clip_id)
        out_dir = (CAMPAIGN_WORK_DIR / ("dryrun_%s" % clip_id)
                   if args.dry_run else CAMPAIGN_CLIPS_DIR)
        entry = cut_moment(campaign, moment, work_dir, out_dir,
                           dry_run=args.dry_run)
        if entry is None:
            continue
        done.append(entry)
        if not args.dry_run:
            entries.append(entry)
            save_campaign_queue(entries)
    print(json.dumps({"ok": True, "campaign": campaign["id"],
                      "cut": len(done),
                      "entries": [{k: e[k] for k in
                                   ("id", "status", "destination", "clip30",
                                    "tiktok", "vod_start_s", "vod_end_s")
                                   if k in e} | {"gate_ok": e["gate"]["ok"],
                                                "block_reason":
                                                e["gate"]["block_reason"]}
                                  for e in done]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
