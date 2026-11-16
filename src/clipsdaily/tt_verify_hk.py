"""Read-only verification: is the Hong Kong TikTok live, a draft, or nowhere?
Reuses the clipsdaily TikTok Playwright session/cookies. Posts/uploads nothing.
"""
import json, re, sys
from tiktok_uploader.upload import TikTokUploader

COOKIES = "/home/abel/clipsdaily/.auth/tiktok_cookies.txt"

def video_info(page, vid):
    page.goto(f"https://www.tiktok.com/@clips.daily548/video/{vid}")
    page.wait_for_timeout(7000)
    html = page.content()
    m = re.search(r'"desc":"((?:[^"\\]|\\.)*)"', html)
    desc = json.loads('"' + m.group(1) + '"') if m else None
    cm = re.search(r'"createTime":(\d+)', html)
    ct = int(cm.group(1)) if cm else None
    return {"id": vid,
            "url": f"https://www.tiktok.com/@clips.daily548/video/{vid}",
            "description": desc, "create_time_unix": ct}

def main():
    u = TikTokUploader(cookies=COOKIES, browser="chromium", headless=True)
    page = u.page
    print("PAGE READY", flush=True)
    page.goto("https://www.tiktok.com/tiktokstudio/content")
    page.wait_for_timeout(10000)
    html = page.content()
    ids = sorted(set(re.findall(r'/video/(\d{10,})', html)))
    print("STUDIO_VIDEO_IDS: " + json.dumps(ids), flush=True)
    text = page.evaluate("() => document.body.innerText")
    print("STUDIO_TEXT_START\n" + (text or "")[:5000] + "\nSTUDIO_TEXT_END", flush=True)
    infos = [video_info(page, vid) for vid in ids]
    print("VIDEO_INFOS: " + json.dumps(infos, indent=2), flush=True)
    # Draft check: open the upload page read-only, look for draft/resume UI.
    page.goto("https://www.tiktok.com/upload")
    page.wait_for_timeout(8000)
    utext = page.evaluate("() => document.body.innerText")
    print("UPLOAD_TEXT_START\n" + (utext or "")[:3000] + "\nUPLOAD_TEXT_END", flush=True)
    prefilled = page.evaluate("""() => {
      const ed = document.querySelector('div[contenteditable="true"]');
      return ed ? ed.innerText : null;
    }""")
    print("UPLOAD_PREFILLED_DESC: " + json.dumps(prefilled), flush=True)
    u.close()
    print("DONE", flush=True)

if __name__ == "__main__":
    main()
