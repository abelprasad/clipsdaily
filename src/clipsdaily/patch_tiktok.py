from pathlib import Path
p = Path("/home/abel/clipsdaily/post_tiktok_fixed.py")
t = p.read_text()

# 1. Add kill_overlays helper after dismiss_modals
anchor = "def post_one(page, label, clip, caption):"
helper = '''def kill_overlays(page, label):
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

'''
assert anchor in t
t = t.replace(anchor, helper + anchor, 1)

# 2. Call kill_overlays before interactivity + description, and verify caption
old = """    up._remove_split_window(page)
    up._set_interactivity(page)
    up._set_description(page, caption)
    print(f"[{label}] description set", flush=True)"""
new = """    up._remove_split_window(page)
    kill_overlays(page, label)
    up._set_interactivity(page)
    kill_overlays(page, label)
    up._set_description(page, caption)
    # Verify the caption actually landed; the library swallows click
    # failures. If empty, set it via JS focus + typing.
    got = page.evaluate(\"\"\"() => {
      const ed = document.querySelector('div[contenteditable="true"]');
      return ed ? ed.innerText : '';
    }\"\"\")
    if caption[:20] not in (got or ''):
        print(f"[{label}] caption missing after _set_description (got {got[:40]!r}) — typing it directly", flush=True)
        page.evaluate(\"\"\"() => { const ed = document.querySelector('div[contenteditable="true"]'); if (ed) ed.focus(); }\"\"\")
        page.keyboard.type(caption, delay=5)
        time.sleep(1)
        got2 = page.evaluate(\"\"\"() => { const ed = document.querySelector('div[contenteditable="true"]'); return ed ? ed.innerText : ''; }\"\"\")
        print(f"[{label}] caption after direct type: {got2[:60]!r}", flush=True)
    print(f"[{label}] description set", flush=True)"""
assert old in t
t = t.replace(old, new)

# 3. Kill overlays before the Post click too, and lengthen confirmation wait
old2 = """    time.sleep(2)
    dismiss_modals(page, label)
    # Click Post via JS"""
new2 = """    time.sleep(2)
    dismiss_modals(page, label)
    kill_overlays(page, label)
    # Click Post via JS"""
assert old2 in t
t = t.replace(old2, new2)
t = t.replace("timeout=90000)", "timeout=120000)")
t = t.replace("no confirmation text within 90s", "no confirmation text within 120s")

# 4. Verify via Studio content page HTML (profile grid does not render headless)
old3 = '''def profile_videos(page):
    """Return list of /video/ links visible on @clips.daily548 profile."""
    page.goto(PROFILE)
    page.wait_for_timeout(8000)
    hrefs = page.evaluate("""() => [...document.querySelectorAll('a[href*="/video/"]')].map(a => a.getAttribute('href'))""")
    seen, out = set(), []
    for h in hrefs:
        if h not in seen:
            seen.add(h); out.append(h)
    return out'''
new3 = '''def profile_videos(page):
    """Return list of video URLs on the account, via TikTok Studio content
    page HTML (the public profile grid does not render in headless)."""
    import re as _re
    page.goto("https://www.tiktok.com/tiktokstudio/content")
    page.wait_for_timeout(8000)
    html = page.content()
    ids = sorted(set(_re.findall(r'/video/(\\d{10,})', html)))
    return [f"https://www.tiktok.com/@clips.daily548/video/{i}" for i in ids]'''
assert old3 in t
t = t.replace(old3, new3)
p.write_text(t)
print("PATCHED")
