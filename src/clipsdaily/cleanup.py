"""Cleanup: the pipeline cleans up after itself so indra storage
never gets cluttered.

Retention rules (enforced on startup and every hour, plus right
after each cut/post):
  1. Raw stream recordings: deleted IMMEDIATELY after the clips for
     that segment are cut. The 48h sweep below is only a backstop
     for crash leftovers.
  2. Finished clips: once a clip has posted to ALL enabled platforms
     it is recorded in logs/posted.jsonl and deleted by the hourly
     sweep once it is older than 24h (sooner under disk pressure:
     older than 1h when free disk < 100 GB, immediately when the
     disk guard trips). Clips that never posted (no platform enabled
     yet, or a post failed) are kept at most 48h, then deleted.
  3. Temp files, every run: ffmpeg leftovers (clips/*_raw.mp4),
     yt-dlp live-chat temp files (/tmp/ytchat_*), and log files
     older than 7 days. Spike logs ARE the summary and are kept
     7 days; there are no raw chat dumps stored anywhere.
  4. Disk guard: if free disk drops below 50 GB, the runner stops
     starting new recordings, finishes and posts what is queued,
     cleans up aggressively, and logs a warning. The disk never fills.
  5. Queue clips (ClipForge package): files in queue/clips/ that
     belong to posted/failed entries are deleted after
     queue_clip_retention_days (7d). Files referenced by a
     pending/partial entry are NEVER deleted. Unreferenced files
     older than 48h are stale and deleted.
  6. Queue work dirs + IG outbox (ClipForge package): queue/work/<id>
     dirs for entries that are no longer pending/partial are deleted;
     ig-outbox/<id> dirs are deleted 7d after the Reel posted
     (.posted exists). A staged (unposted) outbox dir is NEVER
     deleted — an unposted clip is never thrown away.
  7. VOD downloads (ClipForge package): video files in vod/ older
     than vod_retention_days (7d) are deleted; chat JSONs are kept
     (they are small and the maintainer reuses them).

Usage:
  python3 cleanup.py            # one pass, prints what was freed
  from .cleanup import run_cleanup
  run_cleanup(config)            # called by runner.py on startup + hourly
"""
import json
import shutil
import time
from pathlib import Path

from .paths import runtime_home
HERE = runtime_home()

DISK_GUARD_GB = 50        # below this: stop new recordings
DISK_PRESSURE_GB = 100    # below this: delete posted clips older than 1h
POSTED_MAX_AGE_HOURS = 24
UNPOSTED_MAX_AGE_HOURS = 48
LOG_MAX_AGE_DAYS = 7
QUEUE_CLIP_RETENTION_DAYS = 7   # queue/clips of posted/failed entries
IG_OUTBOX_RETENTION_DAYS = 7    # ig-outbox dirs after the Reel posted
VOD_RETENTION_DAYS = 7          # video files in vod/ (chat JSONs kept)


def disk_free_gb(path=HERE):
    return shutil.disk_usage(path).free / (1024 ** 3)


def disk_ok(path=HERE, threshold_gb=DISK_GUARD_GB):
    """True if there is enough free disk to start a new recording."""
    return disk_free_gb(path) >= threshold_gb


def _age_hours(path):
    return (time.time() - path.stat().st_mtime) / 3600


def _delete(path):
    try:
        size = path.stat().st_size
        path.unlink()
        return size
    except FileNotFoundError:
        return 0
    except OSError as e:
        print(f"[cleanup] could not delete {path}: {e}", flush=True)
        return 0


def delete_recording(path):
    """Rule 1: raw recording goes as soon as its clips are cut."""
    freed = _delete(Path(path))
    if freed:
        print(f"[cleanup] deleted raw recording {Path(path).name} "
              f"({freed / 1024 / 1024:.1f} MB)", flush=True)
    return freed


def record_posted(clip_path):
    """Mark a clip as posted to all enabled platforms."""
    with open(HERE / "logs" / "posted.jsonl", "a") as f:
        f.write(json.dumps({"clip": str(clip_path),
                            "posted_at": time.time()}) + "\n")


def posted_clips():
    manifest = HERE / "logs" / "posted.jsonl"
    if not manifest.exists():
        return {}
    out = {}
    with open(manifest) as f:
        for line in f:
            try:
                rec = json.loads(line)
                out[rec["clip"]] = rec["posted_at"]
            except Exception:
                continue
    return out


def cleanup_clips(aggressive=False):
    """Rule 2: delete posted clips past retention, unposted clips
    past 48h. Returns bytes freed."""
    freed = 0
    free = disk_free_gb()
    posted = posted_clips()
    clips_dir = HERE / "clips"
    if not clips_dir.exists():
        return 0
    for clip in list(clips_dir.glob("*.mp4")):
        posted_at = posted.get(str(clip))
        if posted_at is not None:
            # Age counts from when it was posted, not file creation.
            age = (time.time() - posted_at) / 3600
            is_posted = True
        else:
            age = _age_hours(clip)
            is_posted = False
        if is_posted:
            if aggressive or free < DISK_GUARD_GB:
                limit = 0
            elif free < DISK_PRESSURE_GB:
                limit = 1
            else:
                limit = POSTED_MAX_AGE_HOURS
        else:
            limit = UNPOSTED_MAX_AGE_HOURS
        if age >= limit:
            freed += _delete(clip)
            srt = clip.with_suffix(".srt")
            freed += _delete(srt)
            if is_posted:
                print(f"[cleanup] deleted posted clip {clip.name} "
                      f"(age {age:.1f}h)", flush=True)
            else:
                print(f"[cleanup] deleted unposted stale clip {clip.name} "
                      f"(age {age:.1f}h)", flush=True)
    return freed


def cleanup_recordings_backstop(retention_hours=48):
    """Backstop for crash leftovers: recordings older than 48h."""
    freed = 0
    rec_dir = HERE / "recordings"
    if not rec_dir.exists():
        return 0
    for p in rec_dir.glob("*.ts"):
        if _age_hours(p) >= retention_hours:
            freed += _delete(p)
            print(f"[cleanup] deleted leftover recording {p.name}",
                  flush=True)
    return freed


def cleanup_temps():
    """Rule 3: temp files. ffmpeg leftovers, yt-dlp chat temp files,
    old logs. Returns bytes freed."""
    freed = 0
    clips_dir = HERE / "clips"
    if clips_dir.exists():
        for p in clips_dir.glob("*_raw.mp4"):
            freed += _delete(p)
    for p in Path("/tmp").glob("ytchat_*"):
        try:
            freed += _delete(p)
        except OSError:
            pass
    logs_dir = HERE / "logs"
    if logs_dir.exists():
        for p in logs_dir.iterdir():
            if p.name in ("posted.jsonl", "cleanup.log"):
                continue
            if p.is_file() and _age_hours(p) >= LOG_MAX_AGE_DAYS * 24:
                freed += _delete(p)
                print(f"[cleanup] deleted old log {p.name}", flush=True)
    return freed


def _queue_entries():
    """(entries, protected_paths): queue.json entries + the set of
    clip files a pending/partial entry still needs. Missing or
    unreadable queue.json means nothing is protected (fail open for
    deletion would be wrong — callers treat that as 'delete nothing
    that looks referenced')."""
    qf = HERE / "queue" / "queue.json"
    try:
        entries = json.loads(qf.read_text())
    except Exception:
        return [], set()
    protected = set()
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("status") in ("pending", "partial"):
            for key in ("clip30", "tiktok"):
                v = e.get(key)
                if v:
                    protected.add(str(v))
                    protected.add(str(Path(v).with_suffix(".srt")))
    return entries, protected


def cleanup_queue_clips(config=None):
    """Rule 5: queue/clips retention. Posted/failed entries' files go
    after queue_clip_retention_days; unreferenced files go after 48h;
    files a pending/partial entry needs are never touched."""
    cfg = config or {}
    retention_days = cfg.get("queue_clip_retention_days",
                             QUEUE_CLIP_RETENTION_DAYS)
    freed = 0
    entries, protected = _queue_entries()
    done_ids = {str(e.get("id")) for e in entries
                if isinstance(e, dict)
                and e.get("status") in ("posted", "failed")}
    clips_dir = HERE / "queue" / "clips"
    if not clips_dir.exists():
        return 0
    for clip in list(clips_dir.glob("*.mp4")):
        if str(clip) in protected:
            continue
        # Whose file is this? "<clip_id>_30s.mp4" or "<clip_id>_tiktok.mp4".
        stem = clip.name
        owner_done = any(stem.startswith(i + "_") for i in done_ids)
        age = _age_hours(clip)
        if owner_done:
            if age < retention_days * 24:
                continue
        else:
            if age < UNPOSTED_MAX_AGE_HOURS:
                continue
        freed += _delete(clip)
        freed += _delete(clip.with_suffix(".srt"))
        print(f"[cleanup] deleted queue clip {clip.name} (age {age:.1f}h)",
              flush=True)
    return freed


def cleanup_queue_work(config=None):
    """Rule 6a: queue/work/<clip_id> dirs for entries that are no
    longer pending/partial (their cut is done or abandoned)."""
    _, protected = _queue_entries()
    entries, _ = _queue_entries()
    live_ids = {str(e.get("id")) for e in entries
                if isinstance(e, dict)
                and e.get("status") in ("pending", "partial")}
    work_dir = HERE / "queue" / "work"
    if not work_dir.exists():
        return 0
    freed = 0
    for d in list(work_dir.iterdir()):
        if not d.is_dir():
            continue
        if d.name in live_ids:
            continue
        for p in d.rglob("*"):
            if p.is_file():
                freed += _delete(p)
        try:
            d.rmdir()
        except OSError:
            pass
    return freed


def cleanup_ig_outbox(config=None):
    """Rule 6b: ig-outbox/<clip_id> dirs 7d after the Reel posted
    (.posted exists and is old). A staged (unposted) dir is NEVER
    deleted — an unposted clip is never thrown away."""
    cfg = config or {}
    retention_days = cfg.get("ig_outbox_retention_days",
                             IG_OUTBOX_RETENTION_DAYS)
    outbox = HERE / "ig-outbox"
    if not outbox.exists():
        return 0
    freed = 0
    for d in list(outbox.iterdir()):
        if not d.is_dir():
            continue
        posted = d / ".posted"
        if not posted.exists():
            continue
        if _age_hours(posted) < retention_days * 24:
            continue
        for p in d.rglob("*"):
            if p.is_file():
                freed += _delete(p)
        try:
            d.rmdir()
        except OSError:
            pass
        print(f"[cleanup] deleted posted ig-outbox {d.name}", flush=True)
    return freed


def cleanup_vod(config=None):
    """Rule 7: video files in vod/ older than vod_retention_days.
    Chat JSONs are kept (small, reused by the maintainer)."""
    cfg = config or {}
    retention_days = cfg.get("vod_retention_days", VOD_RETENTION_DAYS)
    vod_dir = HERE / "vod"
    if not vod_dir.exists():
        return 0
    freed = 0
    for p in list(vod_dir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".mp4", ".ts", ".mkv", ".webm"):
            continue
        if _age_hours(p) < retention_days * 24:
            continue
        freed += _delete(p)
        print(f"[cleanup] deleted old VOD file {p.name}", flush=True)
    return freed


def run_cleanup(config=None, aggressive=False):
    """One full pass. Returns (bytes freed, free GB after). Logs a
    summary line to logs/cleanup.log."""
    cfg = config or {}
    retention = cfg.get("recording_retention_hours", 48)
    freed = 0
    freed += cleanup_clips(aggressive=aggressive)
    freed += cleanup_recordings_backstop(retention)
    freed += cleanup_temps()
    freed += cleanup_queue_clips(cfg)
    freed += cleanup_queue_work(cfg)
    freed += cleanup_ig_outbox(cfg)
    freed += cleanup_vod(cfg)
    free = disk_free_gb()
    msg = (f"{time.strftime('%Y-%m-%dT%H:%M:%S')} freed "
           f"{freed / 1024 / 1024:.1f} MB, free disk now {free:.1f} GB"
           + (" (AGGRESSIVE)" if aggressive else ""))
    print(f"[cleanup] {msg}", flush=True)
    with open(HERE / "logs" / "cleanup.log", "a") as f:
        f.write(msg + "\n")
    return freed, free


if __name__ == "__main__":
    freed, free = run_cleanup()
    print(f"freed {freed / 1024 / 1024:.2f} MB; free disk {free:.1f} GB")
