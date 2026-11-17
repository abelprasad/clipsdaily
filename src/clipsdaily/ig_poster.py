#!/usr/bin/env python3
"""ClipForge IG worker: posts staged Reels from ig-outbox/ via instagrapi.

Replaces the operator-VM instagram-cli cron: this runs on the same box
as the pipeline, polls ig-outbox/ every 5 minutes, and posts the most
recently staged Reel whose ig_slot is within [-300s, +3600s] of now
(same window the old cron used).

Safety (read the operator script's invariants — they are preserved):
- A clip whose meta is "posted" (or which has a .posted file) is NEVER
  posted again.
- On success the worker writes .posted {status, media_fbid,
  posted_at_utc} and flips meta.json staged -> posted, exactly like
  the old cron did.
- On a dead session (AuthNotConfigured) the worker writes
  logs/clipforge-ig.auth-dead, logs the failure, and exits 0 so
  systemd does NOT hot-loop it; the watchdog sees the marker and
  reports the unit as failed-without-restarting. Re-run the IG auth
  flow (which clears the marker) to resume. A transient error retries
  next cycle; a failed clip stays staged and is never lost.
- STOP file pauses posting, like the runner and the hourly poster.
- The staged caption.txt is the caption (throwback/campaign captions
  live there); the generic one-line caption is NOT substituted.

Auth ladder (see docs/AUTH.md):
  1. instagrapi session file .auth/instagram_session.json, built by
     `clipforge auth instagram` — either password login (auth_instagram.py,
     currently fails on Meta's side for new logins) or session-cookie
     import from a browser export (the working route).
  2. Official Meta Content Publishing API (documented, not implemented).
  3. Manual: the staged files in ig-outbox/ are a complete Reel
     (video + caption + cover) a human can post from the phone.

Usage:
  python3 -m clipsdaily.ig_poster [--once] [--dry-run] [--interval S]
  --dry-run validates files + meta and prints what it WOULD post;
  it writes nothing and calls no API.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .branding import BRAND_SLUG
from .paths import runtime_home

HERE = runtime_home()
OUTBOX = HERE / "ig-outbox"
LOGS = HERE / "logs"
STOP_FILE = HERE / "STOP"
AUTH_DEAD_FILE = LOGS / ("%s-ig.auth-dead" % BRAND_SLUG)
NY = ZoneInfo("America/New_York")

# Same window as the old operator cron: ig_slot up to 5 min in the
# future (clock skew) or up to 60 min old.
AGE_MIN_SECONDS = -300
AGE_MAX_SECONDS = 3600


def log(msg):
    line = "[%s] %s" % (datetime.now(NY).strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with open(LOGS / ("ig-%s.log" % datetime.now(NY).strftime("%Y%m%d")),
                  "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _parse_slot(slot):
    """ig_slot 'YYYY-MM-DDTHH:MM' in America/New_York -> epoch."""
    try:
        dt = datetime.strptime(slot, "%Y-%m-%dT%H:%M").replace(tzinfo=NY)
        return dt.timestamp()
    except Exception:
        return None


def eligible_clips(now_epoch=None):
    """Staged clips whose ig_slot is in the window. Returns a list of
    (age_seconds, clip_id, dir_path) sorted by age ascending (most
    recently slotted first)."""
    now = now_epoch if now_epoch is not None else time.time()
    out = []
    if not OUTBOX.exists():
        return out
    for d in OUTBOX.iterdir():
        if not d.is_dir():
            continue
        meta_path = d / "meta.json"
        try:
            meta = json.loads(meta_path.read_text())
        except Exception:
            continue
        if meta.get("status") != "staged":
            continue
        if (d / ".posted").exists():
            continue
        slot = meta.get("ig_slot") or ""
        slot_epoch = _parse_slot(slot[:16])
        if slot_epoch is None:
            continue
        age = now - slot_epoch
        if AGE_MIN_SECONDS <= age <= AGE_MAX_SECONDS:
            out.append((age, d.name, d))
    out.sort(key=lambda t: t[0])
    return out


def post_one(clip_dir, caption):
    """Upload one Reel via instagrapi. Returns the media pk."""
    from .poster import _ig_client, _make_cover
    clip = next(clip_dir.glob("*.mp4"), None)
    if clip is None:
        raise FileNotFoundError("no .mp4 in %s" % clip_dir)
    cl = _ig_client()
    cover = _make_cover(clip)
    try:
        media = cl.clip_upload(str(clip), caption, thumbnail=cover)
        return media.pk
    finally:
        os.unlink(cover)


def mark_posted(clip_dir, media_pk):
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (clip_dir / ".posted").write_text(json.dumps({
        "status": "posted", "media_fbid": str(media_pk),
        "posted_at_utc": ts}))
    meta_path = clip_dir / "meta.json"
    try:
        meta = json.loads(meta_path.read_text())
        meta["status"] = "posted"
        meta_path.write_text(json.dumps(meta, indent=2))
    except Exception:
        pass
    return ts


def run_once(dry_run=False):
    """One poll cycle. Returns posted|empty|stopped|auth|failed|dry-run."""
    if STOP_FILE.exists():
        log("STOP file present, skipping IG post")
        return "stopped"
    clips = eligible_clips()
    if not clips:
        log("no eligible staged clip")
        return "empty"
    age, clip_id, clip_dir = clips[0]
    caption = ""
    try:
        caption = (clip_dir / "caption.txt").read_text().strip()
    except Exception:
        pass
    if dry_run:
        log("DRY-RUN would post %s (slot age %.0fs, caption %r)"
            % (clip_id, age, caption[:80]))
        return "dry-run"
    try:
        media_pk = post_one(clip_dir, caption)
    except Exception as e:
        from .poster import AuthNotConfigured
        if isinstance(e, AuthNotConfigured):
            log("IG session dead: %s" % e)
            try:
                LOGS.mkdir(parents=True, exist_ok=True)
                AUTH_DEAD_FILE.write_text(
                    "%s session dead: %s\n"
                    % (time.strftime("%Y-%m-%dT%H:%M:%S"), e))
            except Exception:
                pass
            return "auth"
        log("IG post failed for %s: %s" % (clip_id, e))
        return "failed"
    ts = mark_posted(clip_dir, media_pk)
    log("Posted %s to IG as %s at %s" % (clip_id, media_pk, ts))
    return "posted"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clipforge-ig")
    ap.add_argument("--once", action="store_true",
                    help="one poll cycle, then exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate and print what would post; write nothing")
    ap.add_argument("--interval", type=int, default=300,
                    help="seconds between polls (default 300)")
    args = ap.parse_args(argv)
    if args.dry_run:
        return 0 if run_once(dry_run=True) in ("dry-run", "empty",
                                               "stopped") else 1
    if args.once:
        return 0 if run_once() in ("posted", "empty", "stopped") else 1
    log("IG worker starting (poll every %ds)" % args.interval)
    while True:
        result = run_once()
        if result == "auth":
            # Dead session: exit 0 so systemd does not hot-loop us.
            # The watchdog reports the unit failed (auth-dead marker);
            # re-run the IG auth flow to resume.
            log("IG worker stopping until the session is re-authed")
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
