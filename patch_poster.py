"""Patch poster.py + hourly_poster.py + config.yaml on indra to wire in
the TikTok Content Posting API route (tiktok_api.py).

Run ON indra as abel:  python3 patch_poster.py
Every replacement is exact-match and asserted (must match exactly
once). Backups are written next to the originals (*.bak-20261116-ttapi).
No tmux session is touched; nothing is posted.
"""
import shutil
from pathlib import Path

HERE = Path("/home/abel/clipsdaily")


def replace(path, old, new, name):
    text = path.read_text()
    n = text.count(old)
    assert n == 1, f"{path.name} :: {name}: matched {n}x (expected 1)"
    path.write_text(text.replace(old, new))
    print(f"patched {path.name}: {name}")


def main():
    poster = HERE / "poster.py"
    hourly = HERE / "hourly_poster.py"
    config = HERE / "config.yaml"
    for p in (poster, hourly, config):
        shutil.copy2(p, str(p) + ".bak-20261116-ttapi")

    # ---------------------------------------------------------------- poster
    replace(poster, '''- TikTok @clips.daily548 — browser cookies file
  .auth/tiktok_cookies.txt in Netscape format (exported from Abel's
  browser while signed in as Clips Daily; must contain sessionid).''',
            '''- TikTok @clips.daily548 — two routes. OFFICIAL API (tiktok_api.py,
  enabled by `tiktok_api: true` in config.yaml): OAuth token
  .auth/tiktok_api_token.json, no cookies, no browser. COOKIE FALLBACK
  (default while the developer app is unaudited): browser cookies file
  .auth/tiktok_cookies.txt in Netscape format (exported from Abel's
  browser while signed in as Clips Daily; must contain sessionid).
  The API route is capped at ~15 Direct Posts/day per creator and
  5 pending drafts/24h (enforced in tiktok_api.py).''',
            "docstring: TikTok two routes")

    replace(poster, '''def check_tiktok():
    """Checks the cookies file only. Returns (ok, detail).

    A full login check needs an upload attempt, so this is partial:
    it proves a sessionid is on disk, not that TikTok still accepts it.
    """
    try:
        path = _tiktok_cookies()
        return False, (f"cookies file present at {path} but upload is "
                       "untested — first real post will prove the session")
    except AuthNotConfigured as e:
        return False, str(e)''',
            '''def check_tiktok():
    """Checks the TikTok route. Returns (ok, detail).

    If the API client file exists, the API token is checked (read-only
    creator-info call) — that is the live route once configured. The
    cookie check below is the fallback; it proves a sessionid is on
    disk, not that TikTok still accepts it (a full login check needs
    an upload attempt).
    """
    try:
        import tiktok_api
        if tiktok_api.CLIENT_FILE.exists():
            ok, detail = tiktok_api.check_tiktok_api()
            return ok, "API: " + detail
    except Exception:
        pass
    try:
        path = _tiktok_cookies()
        return False, (f"cookies file present at {path} but upload is "
                       "untested — first real post will prove the session")
    except AuthNotConfigured as e:
        return False, str(e)''',
            "check_tiktok: API-aware")

    replace(poster, '''def post_tiktok(clip, channel, config, platform="twitch", caption=None):
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
        caption = _caption(channel, platform=platform)''',
            '''def _post_tiktok_api(clip, caption, config):
    """TikTok via the official Content Posting API (tiktok_api.py).

    Returns the public video URL, or "PENDING:<publish_id>" /
    "DRAFT:<publish_id>" when the video is on TikTok but not public
    yet (callers reconcile the publish_id later instead of
    re-uploading). Returns False when the daily cap is hit (no retry
    burned — the cap resets with time). Raises AuthNotConfigured when
    the API client/token files are missing, and TikTokUploadPending
    when the bytes landed but moderation is still running.
    """
    import tiktok_api
    if not tiktok_api.CLIENT_FILE.exists():
        raise AuthNotConfigured(
            "TikTok API client missing: create the developer app and "
            "run tiktok_api.py --auth-url (see TIKTOK_API_SETUP.md)")
    mode = config.get("tiktok_api_mode", "direct")
    try:
        if mode == "draft":
            res = tiktok_api.post_video_draft(str(clip))
            print(f"[poster] tiktok API draft staged {res['publish_id']} "
                  f"(publish it from the TikTok app)", flush=True)
            return f"DRAFT:{res['publish_id']}"
        res = tiktok_api.post_video_direct(str(clip), caption)
        print(f"[poster] tiktok API posted {res['url']}", flush=True)
        return res["url"]
    except tiktok_api.TikTokCapReached as e:
        print(f"[poster] tiktok API cap reached, skipping (no retry "
              f"burned): {e}", flush=True)
        return False
    except tiktok_api.TikTokUploadPending:
        raise  # callers reconcile the publish_id; never re-upload


def post_tiktok(clip, channel, config, platform="twitch", caption=None,
                allow_short=False):
    if not config.get("platforms", {}).get("tiktok"):
        print("[poster] tiktok OFF, skipping", flush=True)
        return False
    # Hard guard: TikTok only pays for clips over 60s. Refuse anything
    # shorter — a 30s clip must never go to TikTok, except the hourly
    # poster's explicit 30s fallback (allow_short), which keeps the
    # hourly cadence but earns no Creator Rewards.
    try:
        dur = _duration_seconds(clip)
    except Exception as e:
        print(f"[poster] tiktok: could not probe {clip}: {e}", flush=True)
        return False
    if dur < TIKTOK_MIN_SECONDS and not allow_short:
        print(f"[poster] tiktok REFUSED {Path(clip).name}: {dur:.0f}s, "
              f"needs {TIKTOK_MIN_SECONDS}s+ for Creator Rewards",
              flush=True)
        return False
    if caption is None:
        caption = _caption(channel, platform=platform)
    if config.get("tiktok_api"):
        return _post_tiktok_api(clip, caption, config)
    _tiktok_cookies()  # early auth guard: raises if cookies/sessionid missing''',
            "post_tiktok: API route + allow_short")

    replace(poster, '''            try:
                if post_tiktok(Path(tiktok_clip), channel, config, platform,
                               caption=caption):
                    done.append("tiktok")''',
            '''            try:
                res = post_tiktok(Path(tiktok_clip), channel, config,
                                  platform, caption=caption)
                if res and isinstance(res, str) and res.startswith("http"):
                    done.append("tiktok")
                elif res:
                    print(f"[poster] tiktok: {res} (on TikTok, not public "
                          f"yet — reconcile the publish_id later)",
                          flush=True)''',
            "post_all: only count http URLs as posted")

    # ------------------------------------------------------------- hourly
    replace(hourly, '''CONFIG = {"platforms": {"youtube": True, "tiktok": True, "instagram": False}}''',
            '''CONFIG = {"platforms": {"youtube": True, "tiktok": True, "instagram": False},
          "tiktok_api": False, "tiktok_api_mode": "direct"}


def refresh_config():
    """Merge tiktok_api flags from config.yaml into CONFIG.

    Read every slot so flipping `tiktok_api: true` in config.yaml
    takes effect without restarting this poster.
    """
    try:
        import yaml
        cfg = yaml.safe_load((HERE / "config.yaml").read_text()) or {}
        CONFIG["tiktok_api"] = bool(cfg.get("tiktok_api", False))
        CONFIG["tiktok_api_mode"] = cfg.get("tiktok_api_mode", "direct")
    except Exception:
        pass''',
            "CONFIG: tiktok_api flags + refresh_config()")

    replace(hourly, '''Instagram meta rule: ig-outbox/meta.json status is IG state only —''',
            '''TikTok API route (Nov 16, 2026): when config.yaml sets
`tiktok_api: true`, TikTok posts go through the official Content
Posting API (tiktok_api.py) instead of the Playwright cookie
session — no cookies, no browser, capped at ~15 Direct Posts/day
and 5 pending drafts/24h (enforced in tiktok_api.py; a cap hit
never burns a retry). A post that is on TikTok but not public yet
comes back as PENDING:<publish_id> (still processing) or
DRAFT:<publish_id> (waiting in the creator inbox); the next slot
reconciles it instead of re-uploading.

Instagram meta rule: ig-outbox/meta.json status is IG state only —''',
            "docstring: API route note")

    replace(hourly, '''    if not entry.get("tt_url"):
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
                    f"{entry['tt_retries']}): {e}")''',
            '''    tt_url = entry.get("tt_url") or ""
    if isinstance(tt_url, str) and tt_url.startswith(("PENDING:", "DRAFT:")):
        # A previous slot put the video on TikTok but it is not public
        # yet: reconcile the publish_id instead of re-uploading.
        pid = tt_url.split(":", 1)[1]
        kind = "DRAFT" if tt_url.startswith("DRAFT:") else "PENDING"
        try:
            from tiktok_api import reconcile_pending
            out = reconcile_pending(pid)
            res = out[0] if out else {}
            if res.get("url"):
                entry["tt_url"] = res["url"]
                log(f"{entry['id']}: TIKTOK LIVE (reconciled {kind}) "
                    f"{res['url']}")
            elif res.get("status") == "failed":
                entry["tt_url"] = None
                entry["tt_retries"] = entry.get("tt_retries", 0) + 1
                log(f"{entry['id']}: tiktok {kind} FAILED on TikTok "
                    f"({res.get('fail_reason', '')}) — retry "
                    f"{entry['tt_retries']}")
            else:
                log(f"{entry['id']}: tiktok still {kind.lower()} "
                    f"({res.get('status', 'unknown')}) — waiting, no retry")
        except Exception as e:
            log(f"{entry['id']}: tiktok reconcile failed: {e} — waiting")
    if not entry.get("tt_url"):
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
                    from tiktok_api import TikTokUploadPending
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
                        f"{entry['tt_retries']}): {e}")''',
            "post_entry: reconcile PENDING/DRAFT + one post_tiktok call")

    replace(hourly, '''    tt_done = bool(entry.get("tt_url")) and entry["tt_url"] != "FAILED"''',
            '''    tt_done = (bool(entry.get("tt_url"))
               and entry["tt_url"] != "FAILED"
               and not str(entry.get("tt_url")).startswith(
                   ("PENDING:", "DRAFT:")))''',
            "tt_done: PENDING/DRAFT is not live")

    replace(hourly, '''            need_tt = [e for e in pending if not e.get("tt_url")]''',
            '''            need_tt = [e for e in pending
                       if not e.get("tt_url")
                       or str(e.get("tt_url")).startswith(
                           ("PENDING:", "DRAFT:"))]''',
            "slot picker: reconcile PENDING/DRAFT promptly")

    replace(hourly, '''        entries = load_queue()
        pending = [e for e in entries if e["status"] in ("pending", "partial")]''',
            '''        refresh_config()
        entries = load_queue()
        pending = [e for e in entries if e["status"] in ("pending", "partial")]''',
            "main loop: refresh_config() each slot")

    # ------------------------------------------------------------- config
    replace(config, '''platforms:
  instagram: false
  tiktok: true
  youtube: true''',
            '''platforms:
  instagram: false
  tiktok: true
  youtube: true

# TikTok Content Posting API (official, no cookies/Playwright).
# tiktok_api: false until the developer app is created, authorized,
# and audited (see TIKTOK_API_SETUP.md). Flip to true only then.
# tiktok_api_mode: direct (publish straight to the profile) or draft
# (lands in the creator inbox; Abel taps publish on his phone).
# Caps are enforced in code: ~15 Direct Posts/day, 5 pending drafts/24h.
tiktok_api: false
tiktok_api_mode: direct''',
            "config.yaml: tiktok_api flags (default false)")

    print("ALL PATCHES APPLIED")


if __name__ == "__main__":
    main()
