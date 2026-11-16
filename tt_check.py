import sys
sys.path.insert(0, "/home/abel/clipsdaily")
from post_tiktok_fixed import profile_videos, COOKIES
from tiktok_uploader.upload import TikTokUploader
u = TikTokUploader(cookies=COOKIES, browser="chromium", headless=True)
try:
    vids = profile_videos(u.page)
    print("studio count:", len(vids))
    for v in vids:
        print(v)
finally:
    u.close()
