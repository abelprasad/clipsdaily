"""Fixed TikTok poster for @clips.daily548.

Diagnosed Nov 15, 2026: tiktok-uploader 1.2.0 fails at _post_video because
TikTok Studio now shows a "Turn on automatic content checks?" TUXModal
whose overlay intercepts the Post click, and the library fallback
document.querySelector(".TUXButton--primary") is null on the current DOM
(buttons are now Button__root--type-primary). Fix: dismiss the modal
(Cancel = decline the checks), then JS-click button[data-e2e=
'post_video_button'] directly, wait for the upload confirmation, then
verify the video is actually on the profile.

Usage: python3 post_tiktok_fixed.py japan|hongkong|both
Posts NOTHING to any other platform. Verifies each post on the profile.
"""
import json, sys, time
sys.path.insert(0, "/home/abel/clipsdaily")
from pathlib import Path
from tiktok_uploader.upload import TikTokUploader
import tiktok_uploader.upload as up

COOKIES = "/home/abel/clipsdaily/.auth/tiktok_cookies.txt"
CLIPS = {
    "japan": ("/home/abel/clipsdaily/clips/speed-expedia-japan_tiktok70s.mp4",
              "IShowSpeed gives Hudson a trip to Japan with Expedia #IShowSpeed"),
    "hongkong": ("/home/abel/clipsdaily/clips/speed-expedia-hongkong_tiktok90s.mp4",
                 "IShowSpeed gives Anthony $10,000 from Expedia to travel to Hong Kong #IShowSpeed"),
}
PROFILE = "https://www.tiktok.com/@clips.daily548"

def dismiss_modals(page, label):
    """Dismiss any visible TUXModal (content-checks prompt etc).
    Clicks its Cancel button, else the close X, else Escape. Returns
    True if a modal was found and dismissed."""
    dismissed = False
    for _ in range(4):
        found = page.evaluate("""() => {
          const m = document.querySelector('.TUXModal');
          if (!m) return null;
          const r = m.getBoundingClientRect();
          if (r.width === 0) return null;
          return {title: (m.querySelector('.modal-title')||{}).innerText || (m.innerText||'').slice(0,80)};
        }""")
        if not found:
            return dismissed
        print(f"[{label}] modal present: {found['title']!r} — dismissing", flush=True)
        # Prefer the Cancel button in the modal footer.
        clicked = page.evaluate("""() => {
          const m = document.querySelector('.TUXModal');
          if (!m) return 'gone';
          const btns = [...m.querySelectorAll('button')];
          const cancel = btns.find(b => (b.innerText||'').trim() === 'Cancel');
          if (cancel) { cancel.click(); return 'cancel'; }
          const close = m.querySelector('.common-modal-close');
          if (close) { close.click(); return 'close-x'; }
          return 'none';
        }""")
        if clicked == 'none':
            page.keyboard.press("Escape")
            print(f"[{label}] no Cancel/close found, pressed Escape", flush=True)
        else:
            print(f"[{label}] clicked {clicked}", flush=True)
        dismissed = True
        time.sleep(2)
    return dismissed

def kill_overlays(page, label):
    """Remove tour/overlay DOM that intercepts clicks. The react-joyride
    guided tour overlay blocks the description editor and interactivity
    toggles; removing those nodes is safe (tour UI only)."""
    removed = page.evaluate("""() => {
      let n = 0;
      document.querySelectorAll('.react-joyride__overlay, #react-joyride-portal, [class*="joyride"]').forEach(el => { el.remove(); n++; });
      return n;
    }""")
    if removed:
        print(f"[{label}] removed {removed} joyride overlay node(s)", flush=True)

def post_one(page, label, clip, caption):
    print(f"[{label}] uploading {Path(clip).name}", flush=True)
    up._go_to_upload(page)
    up._remove_cookies_window(page)
    dismiss_modals(page, label)  # draft-resume or other prompt, if any
    up._set_video(page, path=clip)
    print(f"[{label}] file uploaded + processed", flush=True)
    time.sleep(3)
    dismiss_modals(page, label)
    up._remove_split_window(page)
    kill_overlays(page, label)
    up._set_interactivity(page)
    kill_overlays(page, label)
    up._set_description(page, caption)
    # Verify the caption actually landed; the library swallows click
    # failures. If empty, set it via JS focus + typing.
    got = page.evaluate("""() => {
      const ed = document.querySelector('div[contenteditable="true"]');
      return ed ? ed.innerText : '';
    }""")
    if caption[:20] not in (got or ''):
        print(f"[{label}] caption missing after _set_description (got {got[:40]!r}) — typing it directly", flush=True)
        page.evaluate("""() => { const ed = document.querySelector('div[contenteditable="true"]'); if (ed) ed.focus(); }""")
        page.keyboard.type(caption, delay=5)
        time.sleep(1)
        got2 = page.evaluate("""() => { const ed = document.querySelector('div[contenteditable="true"]'); return ed ? ed.innerText : ''; }""")
        print(f"[{label}] caption after direct type: {got2[:60]!r}", flush=True)
    print(f"[{label}] description set", flush=True)
    time.sleep(2)
    dismiss_modals(page, label)
    kill_overlays(page, label)
    # Click Post with a REAL mouse click on the visible button. The JS
    # .click() below was a no-op twice in a row (Nov 15, 2026, HK 90s):
    # it returned 'clicked' but the form never submitted and no
    # confirmation appeared, while the same flow posted Japan fine.
    # Real Playwright click drives React's handler; JS click is fallback.
    try:
        post_btn = page.locator("button[data-e2e='post_video_button']:visible")
        post_btn.scroll_into_view_if_needed(timeout=10000)
        post_btn.click(timeout=20000)
        clicked = 'clicked'
        print(f"[{label}] Post click: real Playwright click", flush=True)
    except Exception as e:
        print(f"[{label}] real Post click failed ({e}); falling back to JS click", flush=True)
        clicked = page.evaluate("""() => {
          const btn = document.querySelector("button[data-e2e='post_video_button']");
          if (!btn) return 'no-button';
          if (btn.getAttribute('data-disabled') !== 'false') return 'disabled:' + btn.getAttribute('data-disabled');
          btn.click();
          return 'clicked';
        }""")
    print(f"[{label}] Post click: {clicked}", flush=True)
    if clicked != 'clicked':
        return False, f"post click failed: {clicked}"
    time.sleep(3)
    # 'Post now' confirm (scheduled flow) if it appears.
    try:
        now_btn = page.locator("xpath=//button[.//div[text()='Post now']]")
        if now_btn.is_visible(timeout=5000):
            now_btn.click()
            print(f"[{label}] clicked Post now confirm", flush=True)
    except Exception:
        pass
    # Wait for the published confirmation.
    try:
        page.locator("xpath=//div[contains(text(), 'Your video has been uploaded') or contains(text(), 'Video published')]").wait_for(
            state="attached", timeout=120000)
        print(f"[{label}] confirmation text seen", flush=True)
    except Exception as e:
        print(f"[{label}] WARNING: no confirmation text within 120s: {e}", flush=True)
        page.screenshot(path=f"/home/abel/clipsdaily/tt_{label}_noconfirm.png")
        return False, "no confirmation text"
    return True, "posted (confirmation seen)"

def profile_videos(page):
    """Return list of video URLs on the account, via TikTok Studio content
    page HTML (the public profile grid does not render in headless)."""
    import re as _re
    page.goto("https://www.tiktok.com/tiktokstudio/content")
    page.wait_for_timeout(8000)
    html = page.content()
    ids = sorted(set(_re.findall(r'/video/(\d{10,})', html)))
    return [f"https://www.tiktok.com/@clips.daily548/video/{i}" for i in ids]

def post_file(clip, caption, label="clip"):
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


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    labels = ["japan", "hongkong"] if which == "both" else [which]
    u = TikTokUploader(cookies=COOKIES, browser="chromium", headless=True)
    page = u.page
    print("PAGE READY", flush=True)
    before = profile_videos(page)
    print(f"PROFILE BEFORE: {len(before)} videos: {before}", flush=True)
    results = {}
    for label in labels:
        clip, caption = CLIPS[label]
        try:
            ok, detail = post_one(page, label, clip, caption)
        except Exception as e:
            import traceback; traceback.print_exc()
            ok, detail = False, f"{type(e).__name__}: {e}"
        after = profile_videos(page)
        new = [h for h in after if h not in before]
        verified = len(new) > 0
        results[label] = {"ok": ok, "detail": detail, "profile_count": len(after),
                          "new_links": new, "verified_live": verified}
        print(f"[{label}] RESULT ok={ok} verified_live={verified} new={new} count={len(after)}", flush=True)
        before = after
        if not (ok and verified):
            print(f"[{label}] STOPPING — not verified, will not attempt next clip", flush=True)
            break
        time.sleep(5)
    print(json.dumps(results, indent=2), flush=True)
    u.close()
    print("DONE", flush=True)

if __name__ == "__main__":
    main()
