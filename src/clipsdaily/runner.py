"""Runner: single entry point. Watches the streamer list, records live
streams, watches chat for spikes, cuts captioned vertical clips, posts
them automatically. No human step.

Source platforms: twitch, kick, youtube (chat via yt-dlp), tiktok and
facebook (record-only, no chat spike detection — see chat.py).

Kill switch: create a file named STOP in this directory and all posting
stops immediately (recordings in progress are left alone so nothing is
lost). Delete STOP to resume.

Rate limits: max 1 clip per streamer per 5 min, max 20 clips/day total.
The per-streamer cooldown is shared across platforms: xqc on Twitch
and Kick is one streamer, so the same moment never makes two clips.
"""
import json
import sys
import threading
import time
from pathlib import Path

import yaml

from .paths import runtime_home
HERE = runtime_home()

from .chat import make_monitor      # noqa: E402
from .cleanup import (DISK_GUARD_GB, delete_recording, disk_free_gb,
                     disk_ok, record_posted, run_cleanup)  # noqa: E402
from .cutter import make_clip, make_tiktok_clip  # noqa: E402
from .poster import _caption, post_all  # noqa: E402
from .recorder import is_live, record  # noqa: E402


def load_config():
    with open(HERE / "config.yaml") as f:
        return yaml.safe_load(f)


def normalize_streamers(raw):
    """Accept both the old string list (['xqc']) and the new dict
    list ([{platform: twitch, channel: xqc}]). Returns a list of
    (platform, channel, entry-dict) tuples."""
    out = []
    for item in raw:
        if isinstance(item, str):
            out.append(("twitch", item, {}))
        else:
            out.append((item.get("platform", "twitch"),
                        item["channel"], dict(item)))
    return out


QUEUE_FILE = HERE / "queue" / "queue.json"


def stage_to_queue(clip, tiktok_clip, channel, platform, spike,
                   queue_file=None):
    """Stage a live clip that posted NOWHERE into queue.json so the
    hourly poster retries it next slot instead of losing it.

    Only called when post_all returned no platform (done == []): a
    partial post is NOT staged, because the staged entry starts with
    yt_url/tt_url unset and the hourly poster would re-post a
    platform that already went live (duplicate Short). The overnight
    Kick adinross clip (cut 2026-11-16 05:56, zero platforms posted)
    is the case this fixes.

    Entry shape matches what hourly_poster.post_entry needs
    (id/streamer/platform/clip30/tiktok/title/captions/status/
    retries/urls/history). Campaign safety: no campaign_id and no
    vod_id — auto_submit.write_job requires a campaign_id, and
    eligibility_gate requires clip.vod_id == campaign.vod_id, so a
    live-staged entry can never become a campaign submission.
    Inserted at the FRONT so a fresh live clip posts next slot
    instead of waiting behind the VOD throwback backlog.
    Returns True if staged and verified, False if already present.
    """
    qf = Path(queue_file) if queue_file else QUEUE_FILE
    spike_seconds = float(spike.get("seconds_in", 0))
    entry_id = "live-%s-%s-%ss" % (platform, channel, int(spike_seconds))
    caption = _caption(channel, platform=platform)
    entry = {
        "id": entry_id,
        "streamer": channel,
        "platform": platform,
        "vod_id": None,
        "vod_date": None,
        "spike_seconds": spike_seconds,
        "intensity": spike.get("intensity", 0),
        "phrase": "",
        "clip30": str(clip),
        "tiktok": str(tiktok_clip) if tiktok_clip else None,
        "title": "%s clip | clipsdaily #shorts" % channel,
        "caption_yt": caption,
        "caption_tiktok": caption,
        "caption_ig": caption,
        "status": "pending",
        "yt_retries": 0,
        "tt_retries": 0,
        "yt_url": None,
        "tt_url": None,
        "history": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "live",
        "campaign_eligible": False,
    }
    try:
        entries = json.loads(qf.read_text()) if qf.exists() else []
    except Exception:
        entries = []
    if any(e.get("id") == entry_id for e in entries):
        print(f"[runner] {entry_id} already in queue, not re-staging",
              flush=True)
        return False
    entries.insert(0, entry)
    tmp = qf.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    tmp.replace(qf)
    # Verify the write stuck (the hourly poster also writes this file
    # at slot boundaries; if our entry got clobbered, say so loudly).
    try:
        check = json.loads(qf.read_text())
        stuck = any(e.get("id") == entry_id for e in check)
    except Exception:
        stuck = False
    print(f"[runner] staged {entry_id} at front of queue "
          f"({'verified' if stuck else 'WRITE NOT VERIFIED'})", flush=True)
    return stuck


def stop_requested():
    return (HERE / "STOP").exists()


def cleanup_old_recordings(hours):
    cutoff = time.time() - hours * 3600
    for p in (HERE / "recordings").glob("*.ts"):
        if p.stat().st_mtime < cutoff:
            p.unlink()
            print(f"[runner] deleted old recording {p.name}", flush=True)


class SharedState:
    """Cooldown + daily cap shared across all watcher threads, keyed by
    streamer name (platform-agnostic, so xqc Twitch + Kick dedupe)."""

    def __init__(self, max_clips_per_day):
        self.lock = threading.Lock()
        self.last_clip = {}          # channel -> timestamp of last clip
        self.clips_today = 0
        self.max_clips_per_day = max_clips_per_day

    def claim_clip(self, channel, cooldown_seconds):
        """True if this streamer may cut a clip now (cooldown passed and
        daily cap not hit); reserves the slot."""
        with self.lock:
            now = time.time()
            if self.clips_today >= self.max_clips_per_day:
                return False
            if now - self.last_clip.get(channel, 0) < cooldown_seconds:
                return False
            self.last_clip[channel] = now
            self.clips_today += 1
            return True


def watch_streamer(platform, channel, entry, config, shared):
    """One thread per (platform, channel): record while live, monitor
    chat, cut+post. Record-only platforms (no chat monitor) record
    but cut nothing."""
    tag = f"{platform}_{channel}"
    while True:
        # Disk guard: below 50 GB free, stop starting new recordings.
        # Finish/post what is queued, clean up, log a warning, retry.
        if not disk_ok():
            print(f"[runner] WARNING free disk {disk_free_gb():.1f} GB "
                  f"< {DISK_GUARD_GB} GB — not starting new recordings",
                  flush=True)
            run_cleanup(config, aggressive=True)
            time.sleep(600)
            continue
        if not is_live(platform, channel):
            time.sleep(60)
            continue
        stamp = time.strftime("%Y%m%d_%H%M%S")
        rec = HERE / "recordings" / f"{tag}_{stamp}.ts"

        monitor = make_monitor(platform, channel, entry)
        rec_start = time.time()
        is_recording = [True]
        chat_thread = None
        if monitor is not None:
            chat_thread = threading.Thread(
                target=monitor.run,
                kwargs={"stop_check": lambda: not is_recording[0]},
                daemon=True)
            chat_thread.start()
        else:
            print(f"[runner] {tag}: record-only, no chat monitor",
                  flush=True)
        record(platform, channel, rec, quality=config["record_quality"])
        is_recording[0] = False
        if chat_thread is not None:
            chat_thread.join(timeout=10)

        # Cut one clip per spike, STRONGEST FIRST: when Whisper CPU
        # queues back up, the best clips go out first under the 20/day
        # cap. Intensity = spike-window messages / median.
        spike_lines = []
        if monitor is not None and monitor.log.exists():
            with open(monitor.log) as f:
                spike_lines = f.readlines()
        spikes = []
        for line in spike_lines:
            spike = json.loads(line)
            spike["intensity"] = (spike["messages"] / spike["median"]
                                  if spike.get("median") else 0)
            spikes.append(spike)
        spikes.sort(key=lambda s: s["intensity"], reverse=True)
        # TikTok needs a 60-90s version: build it once per stream from
        # the strongest spike (single extended moment, or stitched
        # compilation if one moment is too short). Only built when
        # TikTok is enabled — it costs a second Whisper pass.
        tiktok_clip = None
        tiktok_enabled = bool(config.get("platforms", {}).get("tiktok"))
        if tiktok_enabled and spikes:
            try:
                tiktok_clip, method = make_tiktok_clip(
                    rec, spikes, tag, model=config["whisper_model"])
                print(f"[runner] TikTok version ({method}): {tiktok_clip}",
                      flush=True)
            except Exception as e:
                print(f"[runner] TikTok version failed: {e}", flush=True)
                tiktok_clip = None
        for spike in spikes:
            if not shared.claim_clip(channel,
                                     config["spike_cooldown_seconds"]):
                continue
            if stop_requested():
                print("[runner] STOP file present, not posting", flush=True)
                continue
            try:
                clip = make_clip(rec, spike["seconds_in"], tag,
                                 clip_seconds=config["clip_length_seconds"],
                                 model=config["whisper_model"])
            except Exception as e:
                print(f"[runner] cut failed: {e}", flush=True)
                continue
            done = post_all(clip, channel, config, platform,
                            tiktok_clip=tiktok_clip)
            enabled = [p for p, on in
                       config.get("platforms", {}).items() if on]
            if enabled and set(done) >= set(enabled):
                # Posted everywhere it needed to go: eligible for the
                # 24h posted-clip retention (cleanup deletes it later).
                record_posted(clip)
                if tiktok_clip is not None:
                    record_posted(tiktok_clip)
            elif enabled and not done:
                # Posted NOWHERE (all platforms failed/off): stage it
                # for the hourly poster instead of losing the clip.
                # Partial posts are NOT staged (would double-post the
                # platform that already went live).
                stage_to_queue(clip, tiktok_clip, channel, platform,
                               spike)
        # Rule 1: raw recording goes immediately once its clips are cut.
        delete_recording(rec)
        cleanup_old_recordings(config["recording_retention_hours"])


def main():
    config = load_config()
    entries = normalize_streamers(config["streamers"])
    print(f"[runner] clipsdaily starting, {len(entries)} watches: "
          + ", ".join(f"{p}/{c}" for p, c, _ in entries), flush=True)
    print("[runner] STOP file pauses posting: touch STOP to pause, "
          "rm STOP to resume", flush=True)
    # Cleanup on startup, then every hour in the background.
    run_cleanup(config)
    stop_hourly = threading.Event()

    def hourly():
        while not stop_hourly.wait(3600):
            run_cleanup(config)

    threading.Thread(target=hourly, daemon=True).start()
    shared = SharedState(config["max_clips_per_day"])
    threads = []
    for platform, channel, entry in entries:
        t = threading.Thread(target=watch_streamer,
                             args=(platform, channel, entry, config, shared),
                             daemon=True)
        t.start()
        threads.append(t)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("[runner] shutting down", flush=True)


if __name__ == "__main__":
    main()
