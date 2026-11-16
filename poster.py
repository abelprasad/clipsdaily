"""Poster: takes finished clips and posts them automatically.

Length routing (hard rule): TikTok gets ONLY the 60-90s version —
TikTok Creator Rewards pays only for clips over 60 seconds. YouTube
Shorts and Instagram Reels get the 30s version. A 30s clip is NEVER
posted to TikTok; post_tiktok refuses any file under 60s.

Auth lives in .auth/ (mode 0700, never committed, never copied off
indra). Each platform reads its own credential file there:

- Instagram @clippedaily31 — instagrapi session file
  .auth/instagram_session.json (created by auth_instagram.py; one-time
  login with the account password, session only — the password is
  never stored). Verified by reading the account's own id.
- YouTube @Clippedaily31 — OAuth token .auth/youtube_token.json
  (created by auth_youtube.py from .auth/youtube_client_secrets.json,
  a Desktop-app OAuth client for clippedaily31@gmail.com).
- TikTok @clips.daily548 — browser cookies file
  .auth/tiktok_cookies.txt in Netscape format (exported from Abel's
  browser while signed in as Clips Daily; must contain sessionid).

This module NEVER posts to Abel's personal accounts. Each function
raises until its platform is explicitly enabled in config.yaml.

Run `python3 poster.py --check` to verify auth without posting
anything: it does read-only checks only (own-profile/channel reads).
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTH_DIR = HERE / ".auth"

TIKTOK_MIN_SECONDS = 60

# Clipsdaily accounts — NEVER point these at Abel's personal accounts.
IG_USERNAME = "clippedaily31"
IG_USER_ID = 27125641130          # user_igid for @clippedaily31
YT_HANDLE = "@Clippedaily31"
TIKTOK_USERNAME = "clips.daily548"

IG_SESSION_FILE = AUTH_DIR / "instagram_session.json"
YT_TOKEN_FILE = AUTH_DIR / "youtube_token.json"
YT_SECRETS_FILE = AUTH_DIR / "youtube_client_secrets.json"
TIKTOK_COOKIES_FILE = AUTH_DIR / "tiktok_cookies.txt"


class AuthNotConfigured(Exception):
    """Raised when a platform's auth file is missing or invalid."""


def _duration_seconds(clip):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(clip)], capture_output=True, text=True)
    return float(r.stdout.strip())


def _caption(channel, game="", platform="twitch"):
    # Cut down Nov 15, 2026, per Abel: one line, no hashtags. The
    # streamer name is the credit; the hook overlay carries the moment.
    return f"clipsdaily • {channel}"


def _make_cover(clip):
    """First frame of the clip as a JPEG, for platforms that need a cover."""
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp.close()
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(clip),
         "-ss", "1", "-vframes", "1", "-q:v", "2", tmp.name],
        check=True)
    return tmp.name


# ---------------------------------------------------------------- Instagram
def _ig_client():
    """Logged-in instagrapi client for @clippedaily31, or raise."""
    if not IG_SESSION_FILE.exists():
        raise AuthNotConfigured(
            "Instagram session missing: run auth_instagram.py once to "
            "create .auth/instagram_session.json")
    from instagrapi import Client
    from instagrapi.exceptions import LoginRequired
    cl = Client()
    cl.load_settings(str(IG_SESSION_FILE))
    # Session-only use: the loaded settings carry the sessionid cookie,
    # so no password is sent. login() would re-authenticate.
    if not cl.user_id:
        raise AuthNotConfigured(
            "Instagram session file has no user id; re-run auth_instagram.py")
    try:
        me = cl.account_info()  # read-only; proves the session is alive
    except LoginRequired:
        raise AuthNotConfigured(
            "Instagram session expired; re-run auth_instagram.py")
    if int(me.pk) != IG_USER_ID:
        raise AuthNotConfigured(
            f"Instagram session is for the wrong account (@{me.username}); "
            f"expected {IG_USERNAME} ({IG_USER_ID})")
    return cl


def check_instagram():
    """Read-only check. Returns (ok, detail). Posts nothing."""
    try:
        cl = _ig_client()
        info = cl.account_info()
        return True, (f"logged in as @{info.username} "
                      f"(id {info.pk}, professional: {info.is_business})")
    except AuthNotConfigured as e:
        return False, str(e)
    except Exception as e:
        return False, f"login failed: {e}"


def post_instagram(clip, channel, config, platform="twitch"):
    if not config.get("platforms", {}).get("instagram"):
        print("[poster] instagram OFF, skipping", flush=True)
        return False
    cl = _ig_client()
    caption = _caption(channel, platform=platform)
    cover = _make_cover(clip)
    try:
        media = cl.clip_upload(str(clip), caption, thumbnail=cover)
        print(f"[poster] instagram posted reel {media.pk}", flush=True)
        return True
    finally:
        os.unlink(cover)


# ------------------------------------------------------------------- YouTube
def _yt_service():
    """Authenticated YouTube Data API client for @Clippedaily31, or raise."""
    if not YT_TOKEN_FILE.exists():
        raise AuthNotConfigured(
            "YouTube token missing: run auth_youtube.py once to create "
            ".auth/youtube_token.json")
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(
        str(YT_TOKEN_FILE),
        ["https://www.googleapis.com/auth/youtube.upload",
         "https://www.googleapis.com/auth/youtube.readonly"])
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        with open(YT_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        os.chmod(YT_TOKEN_FILE, 0o600)
    return build("youtube", "v3", credentials=creds)


def check_youtube():
    """Read-only check. Returns (ok, detail). Posts nothing."""
    try:
        yt = _yt_service()
        resp = yt.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items", [])
        if not items:
            return False, "token valid but no channel found on this account"
        title = items[0]["snippet"]["title"]
        handle = items[0]["snippet"].get("customUrl", "")
        if (handle.lstrip("@").lower() != YT_HANDLE.lstrip("@").lower()
                and title != "Clips Daily"):
            return False, (f"token is for the wrong channel: "
                           f"{title} ({handle})")
        return True, f"authenticated as channel '{title}' ({handle})"
    except AuthNotConfigured as e:
        return False, str(e)
    except Exception as e:
        return False, f"auth check failed: {e}"


def post_youtube(clip, channel, config, platform="twitch",
                 caption=None, title=None):
    if not config.get("platforms", {}).get("youtube"):
        print("[poster] youtube OFF, skipping", flush=True)
        return False
    from googleapiclient.http import MediaFileUpload
    yt = _yt_service()
    if title is None:
        title = f"{channel} clip | clipsdaily #shorts"
    if caption is None:
        caption = _caption(channel, platform=platform)
    description = caption
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["clipsdaily", channel, "shorts", "gaming",
                     "streamclips"],
            "categoryId": "24",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(clip), chunksize=-1, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    print(f"[poster] youtube posted Short {vid} "
          f"https://youtube.com/shorts/{vid}", flush=True)
    return vid  # video id (truthy); callers build https://youtube.com/shorts/{vid}


# -------------------------------------------------------------------- TikTok
def _tiktok_cookies():
    """Path to the cookies file, or raise. Must contain a sessionid."""
    if not TIKTOK_COOKIES_FILE.exists():
        raise AuthNotConfigured(
            "TikTok cookies missing: export cookies from Abel's browser "
            "while signed in as @clips.daily548 to "
            ".auth/tiktok_cookies.txt (see auth_tiktok.py)")
    text = TIKTOK_COOKIES_FILE.read_text()
    if "sessionid" not in text:
        raise AuthNotConfigured(
            "TikTok cookies file has no sessionid — re-export cookies "
            "from a signed-in browser session for @clips.daily548")
    return str(TIKTOK_COOKIES_FILE)


def check_tiktok():
    """Checks the cookies file only. Returns (ok, detail).

    A full login check needs an upload attempt, so this is partial:
    it proves a sessionid is on disk, not that TikTok still accepts it.
    """
    try:
        path = _tiktok_cookies()
        return False, (f"cookies file present at {path} but upload is "
                       "untested — first real post will prove the session")
    except AuthNotConfigured as e:
        return False, str(e)


def post_tiktok(clip, channel, config, platform="twitch", caption=None):
    if not config.get("platforms", {}).get("tiktok"):
        print("[poster] tiktok OFF, skipping", flush=True)
        return False
    # Hard guard: TikTok only pays for clips over 60s. Refuse anything
    # shorter — a 30s clip must never go to TikTok.
    try:
        dur = _duration_seconds(clip)
    except Exception as e:
        print(f"[poster] tiktok: could not probe {clip}: {e}", flush=True)
        return False
    if dur < TIKTOK_MIN_SECONDS:
        print(f"[poster] tiktok REFUSED {Path(clip).name}: {dur:.0f}s, "
              f"needs {TIKTOK_MIN_SECONDS}s+ for Creator Rewards",
              flush=True)
        return False
    _tiktok_cookies()  # early auth guard: raises if cookies/sessionid missing
    if caption is None:
        caption = _caption(channel, platform=platform)
    # Fixed flow (Nov 15, 2026): stock tiktok-uploader's Post click is
    # broken by TikTok's content-checks TUXModal + joyride overlay.
    # post_tiktok_fixed dismisses the modal, removes the overlays,
    # JS-clicks the Post button, and verifies via Studio. Returns the
    # verified video URL or raises.
    from post_tiktok_fixed import post_file
    ok, url, detail = post_file(str(clip), caption, label=channel)
    if not ok or not url:
        raise RuntimeError(f"TikTok post failed/not verified: {detail}")
    print(f"[poster] tiktok posted {url}", flush=True)
    return url


def post_all(clip, channel, config, platform="twitch", tiktok_clip=None,
             caption=None, title=None):
    """Post to every enabled platform. `clip` is the 30s version for
    Instagram Reels + YouTube Shorts; `tiktok_clip` is the 60-90s
    version for TikTok (built by cutter.make_tiktok_clip). If no
    TikTok version was built, TikTok is skipped with a log line —
    the 30s clip is never sent to TikTok. Returns platforms posted."""
    done = []
    for name, fn in (("instagram", post_instagram),
                     ("youtube", post_youtube)):
        try:
            kwargs = {"caption": caption, "title": title} if name == "youtube" else {}
            if fn(Path(clip), channel, config, platform, **kwargs):
                done.append(name)
        except AuthNotConfigured as e:
            print(f"[poster] {name}: auth not configured: {e}", flush=True)
        except Exception as e:
            print(f"[poster] {name}: post failed: {e}", flush=True)
    if config.get("platforms", {}).get("tiktok"):
        if tiktok_clip is None:
            print("[poster] tiktok: no 60-90s version built, skipping "
                  "(30s clip is never posted to TikTok)", flush=True)
        else:
            try:
                if post_tiktok(Path(tiktok_clip), channel, config, platform,
                               caption=caption):
                    done.append("tiktok")
            except AuthNotConfigured as e:
                print(f"[poster] tiktok: auth not configured: {e}",
                      flush=True)
            except Exception as e:
                print(f"[poster] tiktok: post failed: {e}", flush=True)
    return done


def check_all():
    """Read-only auth check for every platform. Posts nothing."""
    for name, fn in (("instagram", check_instagram),
                     ("youtube", check_youtube),
                     ("tiktok", check_tiktok)):
        ok, detail = fn()
        print(f"[check] {name}: {'OK' if ok else 'NOT READY'} — {detail}",
              flush=True)
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        check_all()
    else:
        print("usage: python3 poster.py --check   "
              "(read-only auth check, posts nothing)")
