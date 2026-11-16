"""Find the posted Japan video URL from the profile page's embedded JSON.
Read-only."""
import json, re, sys
from tiktok_uploader.upload import TikTokUploader
COOKIES = "/home/abel/clipsdaily/.auth/tiktok_cookies.txt"
u = TikTokUploader(cookies=COOKIES, browser="chromium", headless=True)
page = u.page
page.goto("https://www.tiktok.com/@clips.daily548")
page.wait_for_timeout(10000)
html = page.content()
# video ids in embedded state
ids = re.findall(r'/video/(\d{10,})', html)
print("VIDEO IDS IN HTML:", sorted(set(ids)), flush=True)
m = re.search(r'"secUid":"([^"]+)"', html)
print("SECUID:", m.group(1) if m else None, flush=True)
m2 = re.search(r'"desc":"(IShowSpeed[^"]{0,200})', html)
print("DESC SNIPPET:", m2.group(1) if m2 else None, flush=True)
# also try the Studio content page
page.goto("https://www.tiktok.com/tiktokstudio/content")
page.wait_for_timeout(8000)
html2 = page.content()
ids2 = re.findall(r'/video/(\d{10,})', html2)
print("STUDIO VIDEO IDS:", sorted(set(ids2)), flush=True)
u.close()
print("DONE", flush=True)
