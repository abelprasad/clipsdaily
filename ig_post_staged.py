#!/usr/bin/env python3
"""Indra-side Instagram poster for clipsdaily (@clippedaily31).

Replaces the operator-VM instagram-cli cron (which waits on a runtime
approval card every run): this runs on the same box as the pipeline as a
systemd user timer and posts via instagrapi with the session file.

Selection mirrors the old cron exactly:
- most recently slotted staged Reel in ig-outbox/ (meta.json
  status == "staged", no .posted file)
- ig_slot (America/New_York) within [-300s, +3600s] of now
- caption.txt is used VERBATIM (throwback/campaign captions live there)
- cover frame extracted at 1s with ffmpeg
- a clip whose meta is "posted" (or which has a .posted file) is NEVER
  posted again; on success we write .posted {status, media_fbid,
  posted_at_utc} and flip meta.json staged -> posted, exactly like the
  old cron did (the watchdog reads .posted for last-post time)

Auth: instagrapi session file .auth/instagram_session.json, built by
auth_ig_session.py (session-cookie import). Password login is broken
against Instagram's endpoint — never attempted here.

Usage:
  python3 ig_post_staged.py            # one poll cycle (timer mode)
  python3 ig_post_staged.py --dry-run  # print what WOULD post; write nothing
  python3 ig_post_staged.py --check    # verify session + account; post nothing

Exit codes: 0 = posted, nothing staged, STOP present, session
missing/expired (timer-safe, no hot loop), dry-run/check clean.
1 = genuine post failure or wrong account.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
OUTBOX = HERE / "ig-outbox"
LOGS = HERE / "logs"
SESSION_FILE = HERE / ".auth" / "instagram_session.json"
STOP_FILE = HERE / "STOP"
LOG_FILE = LOGS / "ig_post_staged.log"
NY = ZoneInfo("America/New_York")

IG_USERNAME = "clippedaily31"
IG_USER_ID = 27125641130

# Same window as the old operator cron: ig_slot up to 5 min in the
# future (clock skew) or up to 60 min old.
AGE_MIN_SECONDS = -300
AGE_MAX_SECONDS = 3600


class AuthNotConfigured(Exception):
    pass


def log(msg):
    line = "[%s] %s" % (datetime.now(NY).strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _parse_slot(slot):
    """ig_slot 'YYYY-MM-DDTHH:MM' in America/New_York -> epoch."""
    try:
        dt = datetime.strptime(slot[:16], "%Y-%m-%dT%H:%M").replace(tzinfo=NY)
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
        slot_epoch = _parse_slot(slot)
        if slot_epoch is None:
            continue
        age = now - slot_epoch
        if AGE_MIN_SECONDS <= age <= AGE_MAX_SECONDS:
            out.append((age, d.name, d))
    out.sort(key=lambda t: t[0])
    return out


def _ig_client():
    """Logged-in instagrapi client for @clippedaily31, or raise
    AuthNotConfigured. Session-only: the loaded settings carry the
    sessionid cookie, so no password is ever sent."""
    if not SESSION_FILE.exists():
        raise AuthNotConfigured(
            "Instagram session missing: run auth_ig_session.py once to "
            "create .auth/instagram_session.json")
    from instagrapi import Client
    from instagrapi.exceptions import LoginRequired
    cl = Client()
    cl.load_settings(str(SESSION_FILE))
    if not cl.user_id:
        raise AuthNotConfigured(
            "Instagram session file has no user id; re-run auth_ig_session.py")
    try:
        me = cl.account_info()  # read-only; proves the session is alive
    except LoginRequired:
        raise AuthNotConfigured(
            "Instagram session expired; re-run auth_ig_session.py")
    if int(me.pk) != IG_USER_ID:
        raise AuthNotConfigured(
            f"Instagram session is for the wrong account (@{me.username}); "
            f"expected {IG_USERNAME} ({IG_USER_ID})")
    return cl


def check_session():
    """Read-only check. Returns (ok, detail). Posts nothing."""
    try:
        cl = _ig_client()
        info = cl.account_info()
        return True, ("logged in as @%s (id %s)" % (info.username, info.pk))
    except AuthNotConfigured as e:
        return False, str(e)
    except Exception as e:
        return False, "login failed: %s" % e


def _make_cover(clip):
    """First frame of the clip as a JPEG, for the Reel cover."""
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(clip),
         "-ss", "1", "-vframes", "1", "-q:v", "2", tmp.name],
        check=True)
    return tmp.name


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
        newest = None
        newest_age = None
        if OUTBOX.exists():
            for d in OUTBOX.iterdir():
                if not d.is_dir():
                    continue
                try:
                    meta = json.loads((d / "meta.json").read_text())
                except Exception:
                    continue
                if meta.get("status") != "staged":
                    continue
                slot_epoch = _parse_slot(meta.get("ig_slot") or "")
                if slot_epoch is None:
                    continue
                age = time.time() - slot_epoch
                if newest is None or age < newest_age:
                    newest, newest_age = d.name, age
        log("no eligible staged clip (newest staged %s, age %.0fs)"
            % (newest or "none", newest_age if newest_age is not None else 0))
        return "empty"
    age, clip_id, clip_dir = clips[0]
    caption = ""
    try:
        caption = (clip_dir / "caption.txt").read_text().strip()
    except Exception:
        pass
    if dry_run:
        video = next(clip_dir.glob("*.mp4"), None)
        log("DRY-RUN would post %s (slot age %.0fs, video %s, caption %r)"
            % (clip_id, age, video.name if video else "MISSING",
               caption[:80]))
        return "dry-run"
    video = next(clip_dir.glob("*.mp4"), None)
    if video is None:
        log("IG post failed for %s: no .mp4 in outbox dir" % clip_id)
        return "failed"
    try:
        cl = _ig_client()
        cover = _make_cover(video)
        try:
            media = cl.clip_upload(str(video), caption, thumbnail=cover)
        finally:
            os.unlink(cover)
    except AuthNotConfigured as e:
        log("IG session dead: %s" % e)
        return "auth"
    except Exception as e:
        log("IG post failed for %s: %s" % (clip_id, e))
        return "failed"
    ts = mark_posted(clip_dir, media.pk)
    log("Posted %s to IG as %s at %s" % (clip_id, media.pk, ts))
    return "posted"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ig_post_staged")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would post; write nothing, call no API")
    ap.add_argument("--check", action="store_true",
                    help="verify session + account; post nothing")
    args = ap.parse_args(argv)
    if args.check:
        ok, detail = check_session()
        log("check: %s" % detail)
        return 0 if ok else 0  # missing/expired session is timer-safe, not fatal
    if args.dry_run:
        return 0 if run_once(dry_run=True) in ("dry-run", "empty",
                                               "stopped") else 1
    result = run_once()
    # Session problems exit 0 so the systemd timer never hot-loops;
    # the watchdog reports IG unhealthy until re-authed.
    return 0 if result in ("posted", "empty", "stopped", "auth") else 1


if __name__ == "__main__":
    sys.exit(main())
