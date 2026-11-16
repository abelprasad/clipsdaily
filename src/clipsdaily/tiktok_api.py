"""TikTok Content Posting API client for clipsdaily.

Replaces the Playwright/browser-cookie TikTok leg (poster.py +
post_tiktok_fixed.py) with TikTok's official API at
https://open.tiktokapis.com. No cookies, no headless browser, no
automation signals for TikTok to flag: posts go through an approved
developer app with a user access token.

Docs read live Nov 16, 2026 (developers.tiktok.com):
- Get Started - Direct Post
- Direct Post video reference (/v2/post/publish/video/init/)
- Upload video to inbox (/v2/post/publish/inbox/video/init/)
- Get Post Status (/v2/post/publish/status/fetch/)
- Manage OAuth Access Tokens (token lifetimes, refresh rotation)
- Get a User Access Token (/v2/oauth/token/)

How it works
------------
1. One-time setup (Abel, see TIKTOK_API_SETUP.md): create a developer
   app, add the Content Posting API product, enable Direct Post,
   request scopes user.info.basic + video.upload + video.publish,
   authorize @clips.daily548, save the client key/secret to
   .auth/tiktok_api_client.json (0600).
2. This module exchanges the authorization code for tokens, stores
   them in .auth/tiktok_api_token.json (0600), and refreshes the
   access token automatically (2h lifetime; refresh token 180 days,
   rotated on every refresh — the stored value is replaced each time).
3. post_video_direct() does the full flow: cap check -> creator info
   -> init -> chunked FILE_UPLOAD -> poll status -> video URL.
   post_video_draft() sends the clip to the creator inbox instead
   (no audit needed, but Abel must finish each post in the TikTok app).

Caps enforced in code (TikTok's own limits, not ours):
- Direct Post: about 15 posts/day per creator, shared across apps.
  Counted on a rolling 24h window from local usage records; once
  hit, post_video_direct() raises TikTokCapReached WITHOUT calling
  TikTok, so the hourly poster can retry tomorrow instead of
  burning retries or double-posting.
- Draft mode: max 5 pending shares per 24h. Pending drafts are
  tracked in the usage file and refreshed by polling their status;
  a draft leaves "pending" once the creator posts it (or it fails).

Audit warning (read this before enabling)
------------------------------------------
Until the app passes TikTok's Content Posting API audit, every Direct
Post is forced to private viewing (SELF_ONLY) and the posting account
must itself be private. The audit checks the posting screen/UI of
your app. Two honest risks for this pipeline:
1. TikTok's docs say apps for private or personal use are not
   approved. This pipeline serves exactly one account
   (@clips.daily548), so the audit may refuse.
2. The Direct Post request must attest content_preview_confirmed and
   express_consent_given. In this pipeline those attestations rest on
   Abel's standing approval of the automated pipeline and its
   eligibility gate (the automated "preview"), NOT on a human
   previewing each clip. The audit may object to a headless poster.
If the audit refuses, the fallbacks are draft mode (no audit, but
Abel taps publish on his phone, 5/day) or a paid scheduler that
already passed the audit. See TIKTOK_API_SETUP.md.

This module posts NOTHING on import. It only talks to TikTok when
one of the post_* functions is called, and only after the app exists
and tokens are on disk.
"""

import base64
import hashlib
import json
import os
import secrets
import subprocess
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
AUTH_DIR = HERE / ".auth"
CLIENT_FILE = AUTH_DIR / "tiktok_api_client.json"
TOKEN_FILE = AUTH_DIR / "tiktok_api_token.json"
AUTH_STATE_FILE = AUTH_DIR / "tiktok_api_auth_state.json"
USAGE_FILE = AUTH_DIR / "tiktok_api_usage.json"

API_BASE = "https://open.tiktokapis.com"
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = API_BASE + "/v2/oauth/token/"
REVOKE_URL = API_BASE + "/v2/oauth/revoke/"
CREATOR_INFO_URL = API_BASE + "/v2/post/publish/creator_info/query/"
DIRECT_POST_INIT_URL = API_BASE + "/v2/post/publish/video/init/"
DRAFT_INIT_URL = API_BASE + "/v2/post/publish/inbox/video/init/"
STATUS_URL = API_BASE + "/v2/post/publish/status/fetch/"

SCOPES = ["user.info.basic", "video.upload", "video.publish"]
TIKTOK_USERNAME = "clips.daily548"

# TikTok's own limits (docs, Nov 2026).
DIRECT_POST_DAILY_CAP = 15       # posts/day per creator, shared across apps
DRAFT_PENDING_CAP = 5            # pending inbox shares per 24h
MAX_VIDEO_BYTES = 4_000_000_000  # 4 GB
MIN_VIDEO_SECONDS = 3
MAX_VIDEO_SECONDS = 600          # 10 minutes
CHUNK_SIZE = 10_000_000          # 10 MB; TikTok allows 5-64 MB per chunk
MIN_CHUNK_SIZE = 5_000_000
MAX_CHUNK_SIZE = 64_000_000
MAX_CHUNKS = 1000
VIDEO_EXTS = {".mp4", ".mov", ".webm"}
VIDEO_CONTENT_TYPES = {".mp4": "video/mp4", ".mov": "video/quicktime",
                       ".webm": "video/webm"}
TOKEN_REFRESH_LEEWAY_S = 300     # refresh when <5 min of access-token life left

# Terminal status values from the Get Post Status reference.
STATUS_PROCESSING_UPLOAD = "PROCESSING_UPLOAD"
STATUS_PROCESSING_DOWNLOAD = "PROCESSING_DOWNLOAD"
STATUS_SEND_TO_USER_INBOX = "SEND_TO_USER_INBOX"
STATUS_PUBLISH_COMPLETE = "PUBLISH_COMPLETE"
STATUS_FAILED = "FAILED"

# Error codes worth a plain-language hint (Direct Post + status refs).
_ERROR_HINTS = {
    "unaudited_client_can_only_post_to_private_accounts": (
        "App not audited: TikTok only lets unaudited clients post to a "
        "private account, and only as SELF_ONLY. Either set the account "
        "private and privacy_level SELF_ONLY to test, or complete the "
        "Content Posting API audit (see TIKTOK_API_SETUP.md)."),
    "spam_risk_too_many_posts": (
        "TikTok daily post cap reached for this creator (~15 posts/day "
        "via the API, shared across apps). Wait until tomorrow."),
    "spam_risk_too_many_pending_share": (
        "Draft cap reached: at most 5 pending inbox shares per 24h. "
        "Finish the pending drafts in the TikTok app first."),
    "spam_risk_user_banned_from_posting": (
        "TikTok has banned this creator from posting. Do not retry."),
    "reached_active_user_cap": (
        "Daily active-user quota for this developer app is reached."),
    "access_token_invalid": (
        "Access token invalid or expired. Refresh it (automatic on the "
        "next call) or re-authorize the app."),
    "scope_not_authorized": (
        "Token lacks the needed scope. Re-authorize with all three "
        "scopes: user.info.basic, video.upload, video.publish."),
    "privacy_level_option_mismatch": (
        "privacy_level is not one of the creator's options from "
        "creator_info/query. Use a level the creator actually allows."),
    "url_ownership_unverified": (
        "PULL_FROM_URL needs the video domain/prefix verified in the "
        "developer portal first."),
    "rate_limit_exceeded": (
        "TikTok rate limit hit. Do not retry immediately; the hourly "
        "poster tries again next slot."),
}


class TikTokAPIError(Exception):
    """A TikTok API call failed. .code is TikTok's error.code."""

    def __init__(self, code, message, http_status=None):
        self.code = code
        self.message = message
        self.http_status = http_status
        hint = _ERROR_HINTS.get(code, "")
        text = f"TikTok API error [{code}]: {message}"
        if hint:
            text += f" ({hint})"
        super().__init__(text)


class TikTokCapReached(Exception):
    """Local cap hit (15 direct posts / 24h, or 5 pending drafts).

    Raised BEFORE any TikTok call, so the hourly poster can skip the
    slot without burning a retry or risking a duplicate.
    """


class TikTokUploadPending(Exception):
    """Bytes are on TikTok but no public URL yet (moderation still
    running when polling timed out). .publish_id lets a later
    reconcile turn it into a URL. Never retry the upload."""

    def __init__(self, publish_id, message=None):
        self.publish_id = publish_id
        super().__init__(message or
                         f"TikTok upload {publish_id} still processing; "
                         f"reconcile later, do not re-upload")


class AuthNotConfigured(Exception):
    """Raised when the API client/token files are missing."""


# ------------------------------------------------------------------ storage
def _save_json_0600(path, data):
    AUTH_DIR.mkdir(mode=0o700, exist_ok=True)
    os.chmod(AUTH_DIR, 0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def _load_json(path):
    return json.loads(Path(path).read_text())


def load_client():
    """Client key/secret/redirect_uri from .auth/tiktok_api_client.json.

    Abel creates this file from the TikTok developer portal (see
    TIKTOK_API_SETUP.md). It is never committed (see .gitignore).
    """
    if not CLIENT_FILE.exists():
        raise AuthNotConfigured(
            "TikTok API client file missing: create the developer app at "
            "developers.tiktok.com and save client_key, client_secret and "
            "redirect_uri to .auth/tiktok_api_client.json (0600). "
            "See TIKTOK_API_SETUP.md.")
    cfg = _load_json(CLIENT_FILE)
    for key in ("client_key", "client_secret", "redirect_uri"):
        if not cfg.get(key):
            raise AuthNotConfigured(
                f"TikTok API client file is missing {key!r}. "
                "See TIKTOK_API_SETUP.md.")
    return cfg


def load_token():
    if not TOKEN_FILE.exists():
        raise AuthNotConfigured(
            "TikTok API token missing: run `python3 tiktok_api.py "
            "--auth-url`, authorize in a browser, then "
            "`python3 tiktok_api.py --exchange <code-or-callback-url>`.")
    return _load_json(TOKEN_FILE)


def _save_token(token):
    _save_json_0600(TOKEN_FILE, token)


# -------------------------------------------------------------------- OAuth
def build_authorize_url(client_key, redirect_uri, scopes=SCOPES):
    """Authorization URL + PKCE verifier for the one-time login.

    Returns (url, code_verifier). The verifier is saved to
    .auth/tiktok_api_auth_state.json so --exchange can read it back.
    Open the URL in a browser signed in as @clips.daily548.
    """
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    params = {
        "client_key": client_key,
        "scope": ",".join(scopes),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)
    _save_json_0600(AUTH_STATE_FILE,
                    {"code_verifier": verifier, "state": state,
                     "redirect_uri": redirect_uri})
    return url, verifier


def exchange_code(code_or_callback_url, client=None):
    """Swap an authorization code for tokens and save them.

    Accepts a bare code or the full redirect callback URL (the state
    is verified against the saved auth state when a URL is given).
    """
    if client is None:
        client = load_client()
    code = code_or_callback_url.strip()
    verifier = None
    if code.startswith("http"):
        parsed = urllib.parse.urlparse(code)
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        returned_state = qs.get("state", [None])[0]
        if not code:
            raise TikTokAPIError(
                "invalid_request",
                "Callback URL has no ?code= parameter. Did TikTok deny "
                "the authorization?")
        if AUTH_STATE_FILE.exists():
            saved = _load_json(AUTH_STATE_FILE)
            verifier = saved.get("code_verifier")
            if saved.get("state") and returned_state != saved["state"]:
                raise TikTokAPIError(
                    "invalid_request",
                    "State mismatch on the callback URL. Start the "
                    "authorization again with --auth-url.")
    elif AUTH_STATE_FILE.exists():
        verifier = _load_json(AUTH_STATE_FILE).get("code_verifier")
    if not code:
        raise TikTokAPIError("invalid_request", "No authorization code given.")
    data = {
        "client_key": client["client_key"],
        "client_secret": client["client_secret"],
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": client["redirect_uri"],
    }
    if verifier:
        data["code_verifier"] = verifier
    resp = requests.post(TOKEN_URL, data=data, timeout=30)
    token = _token_response(resp)
    _save_token(token)
    return token


def _token_response(resp):
    """Parse a /v2/oauth/token response into our stored token shape."""
    try:
        body = resp.json()
    except Exception:
        raise TikTokAPIError("bad_response",
                            f"Token endpoint returned HTTP {resp.status_code} "
                            f"with an unreadable body.")
    if resp.status_code != 200 or "access_token" not in body:
        raise TikTokAPIError(
            body.get("error", "token_exchange_failed"),
            body.get("error_description", f"HTTP {resp.status_code}"),
            http_status=resp.status_code)
    now = int(time.time())
    return {
        "access_token": body["access_token"],
        "refresh_token": body["refresh_token"],
        "open_id": body.get("open_id", ""),
        "scope": body.get("scope", ""),
        "token_type": body.get("token_type", "Bearer"),
        # Lifetimes from TikTok's token docs: access 2h, refresh 180d.
        # Use the returned values when present, never hard-code them.
        "expires_at": now + int(body.get("expires_in", 7200)),
        "refresh_expires_at": now + int(body.get("refresh_expires_in",
                                                 180 * 86400)),
    }


def refresh_access_token(token=None, client=None):
    """Refresh the access token. TikTok rotates the refresh token on
    every refresh: the stored value is replaced, and the old one
    stops working immediately. Raises AuthNotConfigured if the
    refresh token itself is expired (re-authorization needed)."""
    if token is None:
        token = load_token()
    if client is None:
        client = load_client()
    if token.get("refresh_expires_at", 0) <= int(time.time()):
        raise AuthNotConfigured(
            "TikTok refresh token expired (180 days). Re-authorize: "
            "`python3 tiktok_api.py --auth-url` then --exchange.")
    data = {
        "client_key": client["client_key"],
        "client_secret": client["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
    }
    resp = requests.post(TOKEN_URL, data=data, timeout=30)
    new_token = _token_response(resp)
    _save_token(new_token)
    return new_token


def get_access_token():
    """Valid access token, refreshing first when <5 min of life left."""
    token = load_token()
    if token.get("expires_at", 0) - int(time.time()) <= TOKEN_REFRESH_LEEWAY_S:
        token = refresh_access_token(token)
    return token["access_token"]


def revoke_token(token=None):
    """Revoke the stored tokens (call when disconnecting the app)."""
    if token is None:
        token = load_token()
    data = {
        "client_key": load_client()["client_key"],
        "client_secret": load_client()["client_secret"],
        "token": token["access_token"],
    }
    resp = requests.post(REVOKE_URL, data=data, timeout=30)
    if resp.status_code == 200:
        TOKEN_FILE.unlink(missing_ok=True)
        return True
    return False


# ------------------------------------------------------------ API plumbing
def _api_post(url, access_token, body):
    """POST JSON to open.tiktokapis.com. Raises TikTokAPIError unless
    error.code is "ok". Never retries an init: a retried init could
    double-post, so callers decide what a failure means."""
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {access_token}",
                     "Content-Type": "application/json; charset=UTF-8"},
            json=body, timeout=30)
    except requests.RequestException as e:
        raise TikTokAPIError("network_error",
                             f"Could not reach TikTok ({e}).")
    try:
        payload = resp.json()
    except Exception:
        raise TikTokAPIError("bad_response",
                             f"TikTok returned HTTP {resp.status_code} with "
                             f"an unreadable body.",
                             http_status=resp.status_code)
    err = payload.get("error", {}) or {}
    code = err.get("code", "ok")
    if resp.status_code != 200 or code != "ok":
        raise TikTokAPIError(
            code if code != "ok" else f"http_{resp.status_code}",
            err.get("message", f"HTTP {resp.status_code}"),
            http_status=resp.status_code)
    return payload.get("data", {}) or {}


def query_creator_info(access_token):
    """Creator info — required before any Direct Post (privacy options
    and interaction flags come from here, not from guesses)."""
    return _api_post(CREATOR_INFO_URL, access_token, {})


def fetch_status(access_token, publish_id):
    return _api_post(STATUS_URL, access_token, {"publish_id": publish_id})


# -------------------------------------------------------------------- caps
def _load_usage():
    try:
        usage = _load_json(USAGE_FILE)
    except Exception:
        usage = {}
    usage.setdefault("direct_posts", [])
    usage.setdefault("drafts", [])
    return usage


def _save_usage(usage):
    _save_json_0600(USAGE_FILE, usage)


def _within_24h(iso_ts):
    try:
        at = datetime.fromisoformat(iso_ts)
    except Exception:
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - at).total_seconds() < 86400


def direct_posts_last_24h(usage=None):
    """Direct posts in the rolling 24h window (TikTok counts 24h,
    not calendar days)."""
    usage = usage or _load_usage()
    return [p for p in usage["direct_posts"] if _within_24h(p.get("at", ""))]


def check_direct_cap():
    """Raise TikTokCapReached if the ~15/day Direct Post cap is hit.
    Called BEFORE any TikTok request."""
    recent = direct_posts_last_24h()
    if len(recent) >= DIRECT_POST_DAILY_CAP:
        raise TikTokCapReached(
            f"TikTok Direct Post cap reached: {len(recent)} posts in the "
            f"last 24h (TikTok allows about {DIRECT_POST_DAILY_CAP}/day "
            f"per creator). Next post is possible once the oldest of "
            f"them ages past 24h.")
    return len(recent)


def _refresh_draft_statuses(access_token, usage):
    """Poll stored pending drafts; a draft leaves 'pending' once the
    creator posts it (PUBLISH_COMPLETE) or it fails."""
    changed = False
    for draft in usage["drafts"]:
        if draft.get("status") != "pending":
            continue
        try:
            data = fetch_status(access_token, draft["publish_id"])
        except TikTokAPIError:
            continue  # status check failed; keep it pending, retry later
        status = data.get("status")
        if status == STATUS_PUBLISH_COMPLETE:
            draft["status"] = "published"
            changed = True
        elif status == STATUS_FAILED:
            draft["status"] = "failed"
            draft["fail_reason"] = data.get("fail_reason", "")
            changed = True
        # SEND_TO_USER_INBOX / PROCESSING_* stay pending.
    if changed:
        _save_usage(usage)
    return usage


def pending_drafts(refresh=False, access_token=None):
    """Pending inbox drafts. With refresh=True, polls TikTok first so
    drafts the creator already posted stop counting against the cap."""
    usage = _load_usage()
    if refresh:
        if access_token is None:
            access_token = get_access_token()
        usage = _refresh_draft_statuses(access_token, usage)
    return [d for d in usage["drafts"] if d.get("status") == "pending"]


def check_draft_cap():
    """Raise TikTokCapReached if 5 drafts are already pending."""
    pending = pending_drafts(refresh=True)
    if len(pending) >= DRAFT_PENDING_CAP:
        raise TikTokCapReached(
            f"TikTok draft cap reached: {len(pending)} pending inbox "
            f"shares (max {DRAFT_PENDING_CAP} per 24h). Finish them in "
            f"the TikTok app first.")
    return len(pending)


def _record_direct_post(publish_id):
    usage = _load_usage()
    usage["direct_posts"].append(
        {"at": datetime.now(timezone.utc).isoformat(),
         "publish_id": publish_id})
    _save_usage(usage)


def _record_draft(publish_id):
    usage = _load_usage()
    usage["drafts"].append(
        {"publish_id": publish_id,
         "at": datetime.now(timezone.utc).isoformat(),
         "status": "pending"})
    _save_usage(usage)


# ------------------------------------------------------------------- upload
def _probe_duration_seconds(path):
    """Video duration via ffprobe (same tool poster.py already uses).
    Returns None when ffprobe is unavailable or fails."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return None


def _validate_video(path):
    """Size/format/duration checks from TikTok's video restrictions."""
    p = Path(path)
    if not p.exists():
        raise TikTokAPIError("invalid_param", f"Video file not found: {p}")
    if p.suffix.lower() not in VIDEO_EXTS:
        raise TikTokAPIError(
            "invalid_param",
            f"Unsupported video format {p.suffix!r}: TikTok accepts "
            f"MP4, MOV, WebM.")
    size = p.stat().st_size
    if size <= 0:
        raise TikTokAPIError("invalid_param", f"Video file is empty: {p}")
    if size > MAX_VIDEO_BYTES:
        raise TikTokAPIError(
            "invalid_param",
            f"Video is {size} bytes; TikTok's limit is 4 GB.")
    dur = _probe_duration_seconds(p)
    if dur is not None and not (MIN_VIDEO_SECONDS <= dur <= MAX_VIDEO_SECONDS):
        raise TikTokAPIError(
            "invalid_param",
            f"Video is {dur:.1f}s; TikTok accepts 3s to 10 minutes.")
    return size


def _chunk_plan(size, chunk_size=CHUNK_SIZE):
    """(chunk_size, total_chunks) for a file of `size` bytes.

    Chunks are 5-64 MB; the last may run to 128 MB, which a fixed
    10 MB chunk size never approaches."""
    if not (MIN_CHUNK_SIZE <= chunk_size <= MAX_CHUNK_SIZE):
        raise TikTokAPIError(
            "invalid_param",
            f"chunk_size {chunk_size} is outside TikTok's 5-64 MB range.")
    if size <= chunk_size:
        return size, 1
    total = -(-size // chunk_size)  # ceil
    if total > MAX_CHUNKS:
        raise TikTokAPIError(
            "invalid_param",
            f"Video needs {total} chunks; TikTok's limit is {MAX_CHUNKS}.")
    return chunk_size, total


def _upload_chunks(upload_url, path, chunk_size, total_chunks):
    """PUT each chunk to TikTok's upload_url with Content-Range."""
    p = Path(path)
    content_type = VIDEO_CONTENT_TYPES[p.suffix.lower()]
    size = p.stat().st_size
    with open(p, "rb") as f:
        for index in range(total_chunks):
            start = index * chunk_size
            chunk = f.read(chunk_size)
            end = start + len(chunk) - 1
            headers = {
                "Content-Type": content_type,
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{size}",
            }
            try:
                resp = requests.put(upload_url, data=chunk,
                                    headers=headers, timeout=300)
            except requests.RequestException as e:
                raise TikTokAPIError(
                    "network_error",
                    f"Chunk {index + 1}/{total_chunks} upload failed: {e}. "
                    f"The upload_url is valid for 1 hour; retry the "
                    f"whole post, do not resume mid-file.")
            if resp.status_code not in (200, 201, 204):
                raise TikTokAPIError(
                    f"http_{resp.status_code}",
                    f"Chunk {index + 1}/{total_chunks} upload rejected "
                    f"(HTTP {resp.status_code}).",
                    http_status=resp.status_code)


def _poll_status(access_token, publish_id, timeout_s=600):
    """Poll until a terminal status or the timeout. Backoff 10s -> 30s.

    Terminal: PUBLISH_COMPLETE, SEND_TO_USER_INBOX (drafts),
    FAILED. On timeout raises TikTokUploadPending (bytes are already
    on TikTok — never re-upload).
    """
    deadline = time.time() + timeout_s
    interval = 10
    last = {}
    while True:
        last = fetch_status(access_token, publish_id)
        status = last.get("status")
        if status in (STATUS_PUBLISH_COMPLETE, STATUS_SEND_TO_USER_INBOX,
                      STATUS_FAILED):
            return last
        if time.time() + interval > deadline:
            raise TikTokUploadPending(publish_id)
        time.sleep(interval)
        interval = min(30, interval * 2)


def video_url_for(post_id, username=TIKTOK_USERNAME):
    return f"https://www.tiktok.com/@{username}/video/{post_id}"


def _resolve_privacy(creator_info, preferred):
    options = creator_info.get("privacy_level_options") or []
    if preferred not in options:
        raise TikTokAPIError(
            "privacy_level_option_mismatch",
            f"privacy_level {preferred!r} is not one of this creator's "
            f"options {options}. Pick one of the options, or pass "
            f"privacy_level explicitly.")
    return preferred


def _init_direct(access_token, *, title, video_size, chunk_size,
                 total_chunks, privacy_level, disable_comment,
                 disable_duet, disable_stitch, is_aigc,
                 video_cover_timestamp_ms, video_url=None):
    """Init a Direct Post. PULL_FROM_URL when video_url is given,
    FILE_UPLOAD otherwise. See the consent note on the two flags."""
    post_info = {
        "title": title,
        "privacy_level": privacy_level,
        "disable_comment": disable_comment,
        "disable_duet": disable_duet,
        "disable_stitch": disable_stitch,
        "video_cover_timestamp_ms": video_cover_timestamp_ms,
        # Commercial disclosure: both must be sent explicitly, even
        # for non-commercial content.
        "brand_content_toggle": False,
        "brand_organic_toggle": False,
        "is_aigc": is_aigc,
        # Consent attestations (TikTok requires both to be true).
        # In this pipeline they rest on Abel's standing approval of
        # the automated pipeline and its eligibility gate (the
        # automated "preview"), NOT on a human previewing each clip.
        # The audit may object to a headless poster attesting these.
        "content_preview_confirmed": True,
        "express_consent_given": True,
    }
    if video_url:
        source_info = {"source": "PULL_FROM_URL", "video_url": video_url}
    else:
        source_info = {"source": "FILE_UPLOAD", "video_size": video_size,
                       "chunk_size": chunk_size,
                       "total_chunk_count": total_chunks}
    return _api_post(DIRECT_POST_INIT_URL, access_token,
                     {"post_info": post_info, "source_info": source_info})


def _init_draft(access_token, *, video_size, chunk_size, total_chunks,
                video_url=None):
    """Init an inbox draft. No post_info: the creator sets caption and
    privacy in the TikTok app."""
    if video_url:
        source_info = {"source": "PULL_FROM_URL", "video_url": video_url}
    else:
        source_info = {"source": "FILE_UPLOAD", "video_size": video_size,
                       "chunk_size": chunk_size,
                       "total_chunk_count": total_chunks}
    return _api_post(DRAFT_INIT_URL, access_token,
                     {"source_info": source_info})


def _init_with_token_refresh(init_fn, access_token):
    """Run an init; on an expired-token 401, refresh once and retry.
    Inits are the one call where a retry is safe (no bytes have been
    sent yet, so no duplicate can exist)."""
    try:
        return init_fn(access_token)
    except TikTokAPIError as e:
        if e.code == "access_token_invalid":
            fresh = refresh_access_token()
            return init_fn(fresh["access_token"])
        raise


# ------------------------------------------------------------- public posts
def post_video_direct(clip, caption, *, privacy_level="PUBLIC_TO_EVERYONE",
                      allow_comment=True, allow_duet=True,
                      allow_stitch=True, is_aigc=False,
                      video_cover_timestamp_ms=1000, video_url=None,
                      poll_timeout_s=600, chunk_size=CHUNK_SIZE):
    """Direct Post a clip to @clips.daily548 via the official API.

    Returns {"publish_id", "post_id", "url", "status": "published"}.
    Raises TikTokUploadPending when the bytes are on TikTok but no
    public URL exists yet (moderation still running) — the caller
    must NOT re-upload; reconcile with the publish_id later.
    Raises TikTokCapReached before any TikTok call when the ~15/day
    cap is already hit.
    """
    if caption is not None and len(caption.encode("utf-16-le")) // 2 > 2200:
        raise TikTokAPIError(
            "invalid_param", "Caption exceeds TikTok's 2200-character limit.")
    size = _validate_video(clip)
    check_direct_cap()
    chunk, total = _chunk_plan(size, chunk_size)
    access_token = get_access_token()
    creator = query_creator_info(access_token)
    privacy = _resolve_privacy(creator, privacy_level)
    # The creator's own disabled flags win over our allow_* asks:
    # TikTok disables the interaction server-side for those accounts.
    disable_comment = (not allow_comment) or bool(
        creator.get("comment_disabled"))
    disable_duet = (not allow_duet) or bool(creator.get("duet_disabled"))
    disable_stitch = (not allow_stitch) or bool(
        creator.get("stitch_disabled"))
    # Duration guard from the creator's own ceiling.
    max_dur = creator.get("max_video_post_duration_sec")
    if max_dur:
        dur = _probe_duration_seconds(clip)
        if dur is not None and dur > max_dur:
            raise TikTokAPIError(
                "invalid_param",
                f"Video is {dur:.1f}s but this creator's ceiling is "
                f"{max_dur}s.")
    init = _init_with_token_refresh(
        lambda tok: _init_direct(
            tok, title=caption or "", video_size=size, chunk_size=chunk,
            total_chunks=total, privacy_level=privacy,
            disable_comment=disable_comment, disable_duet=disable_duet,
            disable_stitch=disable_stitch, is_aigc=is_aigc,
            video_cover_timestamp_ms=video_cover_timestamp_ms,
            video_url=video_url),
        access_token)
    publish_id = init.get("publish_id")
    if not publish_id:
        raise TikTokAPIError("bad_response",
                            "Init succeeded but TikTok returned no publish_id.")
    if not video_url:
        _upload_chunks(init["upload_url"], clip, chunk, total)
    # Count the post now: the bytes are on TikTok, so it exists even
    # if moderation is slow. Counting late would let a retry
    # double-post past the cap.
    _record_direct_post(publish_id)
    final = _poll_status(access_token, publish_id, timeout_s=poll_timeout_s)
    return _direct_result(publish_id, final)


def _direct_result(publish_id, final):
    status = final.get("status")
    if status == STATUS_FAILED:
        raise TikTokAPIError(
            "publish_failed",
            f"TikTok failed the publish: "
            f"{final.get('fail_reason', 'no reason given')}.")
    if status != STATUS_PUBLISH_COMPLETE:
        raise TikTokUploadPending(
            publish_id,
            f"TikTok status is {status}; no public URL yet.")
    post_ids = final.get("publicaly_available_post_id") or []
    post_id = post_ids[0] if post_ids else None
    if not post_id:
        # Published, but moderation has not released the public id
        # yet. Do not re-upload; reconcile by publish_id.
        raise TikTokUploadPending(
            publish_id,
            "TikTok published the video but moderation has not released "
            "the public post id yet.")
    return {"publish_id": publish_id, "post_id": str(post_id),
            "url": video_url_for(str(post_id)), "status": "published"}


def post_video_draft(clip, *, video_url=None, poll_timeout_s=300,
                     chunk_size=CHUNK_SIZE):
    """Send a clip to the creator inbox as a draft (video.upload).

    Returns {"publish_id", "status": "draft"}. Nothing goes live:
    Abel opens the inbox notification in the TikTok app and finishes
    the post there. No audit needed for this mode.
    """
    size = _validate_video(clip)
    check_draft_cap()
    chunk, total = _chunk_plan(size, chunk_size)
    access_token = get_access_token()
    init = _init_with_token_refresh(
        lambda tok: _init_draft(
            tok, video_size=size, chunk_size=chunk, total_chunks=total,
            video_url=video_url),
        access_token)
    publish_id = init.get("publish_id")
    if not publish_id:
        raise TikTokAPIError("bad_response",
                            "Init succeeded but TikTok returned no publish_id.")
    if not video_url:
        _upload_chunks(init["upload_url"], clip, chunk, total)
    _record_draft(publish_id)
    final = _poll_status(access_token, publish_id, timeout_s=poll_timeout_s)
    status = final.get("status")
    if status == STATUS_FAILED:
        raise TikTokAPIError(
            "publish_failed",
            f"TikTok failed the draft upload: "
            f"{final.get('fail_reason', 'no reason given')}.")
    if status != STATUS_SEND_TO_USER_INBOX:
        raise TikTokUploadPending(
            publish_id,
            f"Draft status is {status}; the inbox notification has not "
            f"landed yet.")
    return {"publish_id": publish_id, "status": "draft"}


def reconcile_pending(publish_id=None):
    """Turn PENDING publish_ids into URLs. With no argument,
    reconciles every draft recorded as pending. Returns a list of
    {"publish_id", "status", "url" (when published)}."""
    access_token = get_access_token()
    usage = _load_usage()
    targets = []
    if publish_id:
        targets = [publish_id]
    else:
        targets = [d["publish_id"] for d in usage["drafts"]
                   if d.get("status") == "pending"]
    out = []
    for pid in targets:
        try:
            data = fetch_status(access_token, pid)
        except TikTokAPIError as e:
            out.append({"publish_id": pid, "status": "error",
                        "detail": str(e)})
            continue
        status = data.get("status")
        if status == STATUS_PUBLISH_COMPLETE:
            post_ids = data.get("publicaly_available_post_id") or []
            url = (video_url_for(str(post_ids[0])) if post_ids else None)
            out.append({"publish_id": pid, "status": "published",
                        "url": url})
            for d in usage["drafts"]:
                if d["publish_id"] == pid:
                    d["status"] = "published"
        elif status == STATUS_FAILED:
            out.append({"publish_id": pid, "status": "failed",
                        "fail_reason": data.get("fail_reason", "")})
            for d in usage["drafts"]:
                if d["publish_id"] == pid:
                    d["status"] = "failed"
        else:
            out.append({"publish_id": pid, "status": status.lower()})
    _save_usage(usage)
    return out


def check_tiktok_api():
    """Read-only check for `poster.py --check`. Returns (ok, detail).
    Posts nothing. A creator_info query proves the token is alive."""
    try:
        client = load_client()
    except AuthNotConfigured as e:
        return False, str(e)
    try:
        token = load_token()
    except AuthNotConfigured as e:
        return False, str(e)
    try:
        access_token = get_access_token()
        creator = query_creator_info(access_token)
        username = creator.get("creator_username", "?")
        options = creator.get("privacy_level_options") or []
        audited = "PUBLIC_TO_EVERYONE" in options
        audit_note = ("audited (public posting open)" if audited
                      else "UNAUDITED: Direct Posts will be SELF_ONLY only")
        return True, (
            f"API token valid for @{username} "
            f"(scopes: {token.get('scope', '?')}; {audit_note}; "
            f"direct posts in last 24h: "
            f"{len(direct_posts_last_24h())}/{DIRECT_POST_DAILY_CAP}; "
            f"pending drafts: {len(pending_drafts())}/{DRAFT_PENDING_CAP})")
    except TikTokAPIError as e:
        return False, f"API check failed: {e}"
    except AuthNotConfigured as e:
        return False, str(e)


# ---------------------------------------------------------------------- CLI
def _cli(argv):
    import argparse
    p = argparse.ArgumentParser(
        description="TikTok Content Posting API client for clipsdaily. "
                    "Posts nothing unless --post-direct/--post-draft is given "
                    "with a real token on disk.")
    p.add_argument("--auth-url", action="store_true",
                   help="Print the authorization URL; open it as "
                        "@clips.daily548.")
    p.add_argument("--exchange", metavar="CODE_OR_URL",
                   help="Exchange an authorization code (or full callback "
                        "URL) for tokens and save them.")
    p.add_argument("--check", action="store_true",
                   help="Read-only auth check (no posting).")
    p.add_argument("--reconcile", metavar="PUBLISH_ID", nargs="?",
                   const="", default=None,
                   help="Resolve a pending publish_id to a URL (or all "
                        "pending drafts when no id is given).")
    p.add_argument("--post-direct", metavar="FILE",
                   help="Direct Post a video file (needs a saved token).")
    p.add_argument("--post-draft", metavar="FILE",
                   help="Send a video file to the creator inbox as a draft.")
    p.add_argument("--caption", default="",
                   help="Caption for --post-direct.")
    p.add_argument("--privacy-level", default="PUBLIC_TO_EVERYONE",
                   help="Privacy for --post-direct (must be one of the "
                        "creator's options; SELF_ONLY while unaudited).")
    args = p.parse_args(argv)
    if args.auth_url:
        client = load_client()
        url, _verifier = build_authorize_url(
            client["client_key"], client["redirect_uri"])
        print("Open this URL in a browser (signed in as @clips.daily548):\n")
        print(url)
        print("\nAfter TikTok redirects, copy the ?code= value (or the "
              "whole callback URL) and run:\n"
              "  python3 tiktok_api.py --exchange <code-or-callback-url>")
        return 0
    if args.exchange:
        token = exchange_code(args.exchange)
        print(f"OK: token saved for open_id {token.get('open_id', '?')} "
              f"(scopes: {token.get('scope', '?')})")
        print("Verify with: python3 tiktok_api.py --check")
        return 0
    if args.check:
        ok, detail = check_tiktok_api()
        print(f"tiktok api: {'OK' if ok else 'NOT READY'} — {detail}")
        return 0 if ok else 1
    if args.reconcile is not None:
        results = reconcile_pending(args.reconcile or None)
        for r in results:
            print(r)
        return 0
    if args.post_direct:
        res = post_video_direct(args.post_direct, args.caption,
                                privacy_level=args.privacy_level)
        print(f"POSTED: {res['url']} (publish_id {res['publish_id']})")
        return 0
    if args.post_draft:
        res = post_video_draft(args.post_draft)
        print(f"DRAFT SENT: publish_id {res['publish_id']} — finish it in "
              f"the TikTok app (inbox notification).")
        return 0
    p.print_help()
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
