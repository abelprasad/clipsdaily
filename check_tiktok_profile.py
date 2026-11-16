"""Check @clips.daily548 profile: video links + open the newest video and
read its full caption. Read-only, posts nothing."""
import json, sys
sys.path.insert(0, "/home/abel/clipsdaily")
from tiktok_uploader.upload import TikTokUploader
COOKIES = "/home/abel/clipsdaily/.auth/tiktok_cookies.txt"
u = TikTokUploader(cookies=COOKIES, browser="chromium", headless=True)
page = u.page
page.goto("https://www.tiktok.com/@clips.daily548")
page.wait_for_timeout(10000)
page.mouse.wheel(0, 1500)
page.wait_for_timeout(5000)
links = page.evaluate("""() => [...document.querySelectorAll('a[href*="/video/"]')].map(a => a.getAttribute('href'))""")
seen, out = set(), []
for h in links:
    if h not in seen:
        seen.add(h); out.append(h)
print("PROFILE VIDEO LINKS:", json.dumps(out, indent=2), flush=True)
print("COUNT:", len(out), flush=True)
if out:
    url = out[0] if out[0].startswith("http") else "https://www.tiktok.com" + out[0]
    print("OPENING NEWEST:", url, flush=True)
    page.goto(url)
    page.wait_for_timeout(8000)
    cap = page.evaluate("""() => {
      const els = [...document.querySelectorAll('[data-e2e="browse-video-desc"], [data-e2e="video-desc"]')];
      if (els.length) return els[0].innerText;
      const m = document.querySelector('meta[name="description"]');
      return m ? m.getAttribute('content') : '(no desc element found)';
    }""")
    print("CAPTION:", cap, flush=True)
    print("VIDEO URL:", page.url, flush=True)
u.close()
print("DONE", flush=True)
