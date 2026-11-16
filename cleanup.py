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

Usage:
  python3 cleanup.py            # one pass, prints what was freed
  from cleanup import run_cleanup
  run_cleanup(config)            # called by runner.py on startup + hourly
"""
import json
import shutil
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

DISK_GUARD_GB = 50        # below this: stop new recordings
DISK_PRESSURE_GB = 100    # below this: delete posted clips older than 1h
POSTED_MAX_AGE_HOURS = 24
UNPOSTED_MAX_AGE_HOURS = 48
LOG_MAX_AGE_DAYS = 7


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


def run_cleanup(config=None, aggressive=False):
    """One full pass. Returns (bytes freed, free GB after). Logs a
    summary line to logs/cleanup.log."""
    cfg = config or {}
    retention = cfg.get("recording_retention_hours", 48)
    freed = 0
    freed += cleanup_clips(aggressive=aggressive)
    freed += cleanup_recordings_backstop(retention)
    freed += cleanup_temps()
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
