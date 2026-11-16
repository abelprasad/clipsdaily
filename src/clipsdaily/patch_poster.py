from pathlib import Path

# --- 1. post_tiktok_fixed.py: add importable post_file() ---
p = Path("/home/abel/clipsdaily/post_tiktok_fixed.py")
s = p.read_text()
anchor = "def main():"
add = '''def post_file(clip, caption, label="clip"):
    """Post ONE file with the fixed flow. Returns (ok, url_or_None, detail).

    Creates its own browser session, dismisses the content-checks modal,
    removes joyride overlays, JS-clicks Post, and verifies the video is
    actually on the account via TikTok Studio before returning.
    """
    from tiktok_uploader.upload import TikTokUploader
    u = TikTokUploader(cookies=COOKIES, browser="chromium", headless=True)
    page = u.page
    try:
        before = profile_videos(page)
        try:
            ok, detail = post_one(page, label, str(clip), caption)
        except Exception as e:
            import traceback; traceback.print_exc()
            ok, detail = False, "%s: %s" % (type(e).__name__, e)
        after = profile_videos(page)
        new = [h for h in after if h not in before]
        verified = len(new) > 0
        url = new[0] if new else None
        return (ok and verified), url, "%s | new=%s count=%d" % (detail, new, len(after))
    finally:
        u.close()


'''
assert anchor in s and "def post_file" not in s
p.write_text(s.replace(anchor, add + anchor, 1))
print("post_tiktok_fixed.py: post_file added")

# --- 2. poster.py: fixed TikTok + post_youtube returns video id ---
p = Path("/home/abel/clipsdaily/poster.py")
s = p.read_text()
old_tt = '''    cookies = _tiktok_cookies()
    from tiktok_uploader.upload import upload_video
    if caption is None:
        caption = _caption(channel, platform=platform)
    # upload_video returns the list of FAILED uploads (empty = success).
    # headless chromium via playwright (bundled in ~/.cache/ms-playwright).
    failed = upload_video(str(clip), caption, cookies=cookies,
                          browser="chromium", headless=True)
    if failed:
        raise RuntimeError(f"TikTok upload reported failure: {failed}")
    print(f"[poster] tiktok posted {Path(clip).name}", flush=True)
    return True'''
new_tt = '''    _tiktok_cookies()  # early auth guard: raises if cookies/sessionid missing
    if caption is None:
        caption = _caption(channel, platform=platform)
    # Fixed flow (Nov 15, 2026): stock tiktok-uploader's Post click is
    # broken by TikTok's content-checks TUXModal + joyride overlay.
    # post_tiktok_fixed dismisses the modal, removes the overlays,
    # JS-clicks the Post button, and verifies via Studio. Returns the
    # verified video URL or raises.
    from .post_tiktok_fixed import post_file
    ok, url, detail = post_file(str(clip), caption, label=channel)
    if not ok or not url:
        raise RuntimeError(f"TikTok post failed/not verified: {detail}")
    print(f"[poster] tiktok posted {url}", flush=True)
    return url'''
assert old_tt in s, "old post_tiktok body not found"
s = s.replace(old_tt, new_tt)
old_yt = '''    vid = resp["id"]
    print(f"[poster] youtube posted Short {vid} "
          f"https://youtube.com/shorts/{vid}", flush=True)
    return True'''
new_yt = '''    vid = resp["id"]
    print(f"[poster] youtube posted Short {vid} "
          f"https://youtube.com/shorts/{vid}", flush=True)
    return vid  # video id (truthy); callers build https://youtube.com/shorts/{vid}'''
assert old_yt in s, "old post_youtube return not found"
s = s.replace(old_yt, new_yt)
p.write_text(s)
print("poster.py patched")
