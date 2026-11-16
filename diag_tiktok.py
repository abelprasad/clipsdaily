"""Diagnose the TikTok Post-button modal. Drives the uploader up to the
Post step with the Japan 70s clip, then dumps modal DOM + screenshot.
Posts NOTHING. Run as abel: python3 diag_tiktok.py"""
import json, sys, time
sys.path.insert(0, "/home/abel/clipsdaily")
from pathlib import Path
from tiktok_uploader.upload import TikTokUploader
import tiktok_uploader.upload as up

CLIP = "/home/abel/clipsdaily/clips/speed-expedia-japan_tiktok70s.mp4"
CAPTION = "IShowSpeed surprises Hudson with a trip to Japan, thanks to Expedia #IShowSpeed #Expedia #ishowspeed #clipsdaily"
COOKIES = "/home/abel/clipsdaily/.auth/tiktok_cookies.txt"
OUT = Path("/home/abel/clipsdaily/diag_tiktok.json")

u = TikTokUploader(cookies=COOKIES, browser="chromium", headless=True)
page = u.page
print("PAGE READY url=", page.url, flush=True)
up._go_to_upload(page)
up._remove_cookies_window(page)
print("UPLOADING FILE...", flush=True)
up._set_video(page, path=CLIP)
print("FILE UPLOADED, processing done", flush=True)
time.sleep(5)
up._remove_split_window(page)
up._set_description(page, CAPTION)
print("DESCRIPTION SET", flush=True)
time.sleep(3)

state = page.evaluate("""() => {
  const out = {};
  out.url = location.href;
  out.title = document.title;
  // all modal-ish elements
  const mods = [];
  document.querySelectorAll('[class*="TUXModal"], [class*="Modal"], [class*="modal"]').forEach(el => {
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.height > 0) {
      mods.push({cls: el.className.slice(0,120), text: (el.innerText||'').slice(0,300), x: r.x, y: r.y, w: r.width, h: r.height});
    }
  });
  out.modals = mods;
  // post button state
  const btn = document.querySelector("button[data-e2e='post_video_button']");
  if (btn) {
    const r = btn.getBoundingClientRect();
    out.postBtn = {disabled: btn.getAttribute('data-disabled'), cls: btn.className.slice(0,150),
                   visible: r.width > 0 && r.height > 0, x: r.x, y: r.y, w: r.width, h: r.height,
                   text: (btn.innerText||'').slice(0,100)};
    const cx = r.x + r.width/2, cy = r.y + r.height/2;
    const top = document.elementFromPoint(cx, cy);
    out.elementAtPostCenter = top ? {tag: top.tagName, cls: (top.className||'').toString().slice(0,150), text: (top.innerText||'').slice(0,120)} : null;
  } else {
    out.postBtn = null;
  }
  // primary buttons present
  out.primaryBtns = [...document.querySelectorAll('.TUXButton--primary')].map(b => ({text:(b.innerText||'').slice(0,60), disabled: b.getAttribute('data-disabled'), e2e: b.getAttribute('data-e2e')}));
  // dialogs / overlays
  out.overlays = [...document.querySelectorAll('[class*="overlay"], [class*="Overlay"]')].map(el => ({cls: el.className.slice(0,120), text:(el.innerText||'').slice(0,200)})).slice(0,10);
  return out;
}""")
print(json.dumps(state, indent=2), flush=True)
OUT.write_text(json.dumps(state, indent=2))
page.screenshot(path="/home/abel/clipsdaily/diag_tiktok.png", full_page=False)
print("SCREENSHOT SAVED", flush=True)
u.close()
print("DIAG DONE — posted nothing", flush=True)
