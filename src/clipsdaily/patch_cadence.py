from pathlib import Path

# ---------- hourly_poster.py: :00 and :30 slots ----------
p = Path("/home/abel/clipsdaily/hourly_poster.py")
s = p.read_text()

s = s.replace(
    '"""Hourly poster for clipsdaily: one clip to YouTube + TikTok (+ staged\n'
    'Instagram) at the top of every hour, from queue/queue.json.',
    '"""Half-hour poster for clipsdaily: one clip to YouTube + TikTok\n'
    '(+ staged Instagram) at :00 and :30 every hour, from queue/queue.json.',
    1)

old_next = '''def next_top_of_hour():
    now = datetime.now()
    nxt = (now.replace(minute=0, second=0, microsecond=0)
           + timedelta(hours=1))
    return nxt'''
new_next = '''def next_slot():
    """Next :00 or :30 boundary (two clips per hour, from Nov 15 21:00)."""
    now = datetime.now()
    if now.minute < 30:
        return now.replace(minute=30, second=0, microsecond=0)
    return (now.replace(minute=0, second=0, microsecond=0)
            + timedelta(hours=1))'''
assert old_next in s
s = s.replace(old_next, new_next, 1)

# stage_instagram: record the IG cron slot (:05 / :35) in meta.json
old_meta = '''    meta = {
        "clip_id": entry["id"], "scheduled_hour": hour_label,
        "streamer": entry["streamer"], "title": entry["title"],
        "youtube_url": entry.get("yt_url"),
        "tiktok_url": entry.get("tt_url"),
        "status": "staged",
    }'''
new_meta = '''    try:
        dt = datetime.strptime(hour_label, "%Y-%m-%dT%H:%M")
        ig_slot = (dt + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
    except Exception:
        ig_slot = hour_label
    meta = {
        "clip_id": entry["id"], "scheduled_hour": hour_label,
        "ig_slot": ig_slot,
        "streamer": entry["streamer"], "title": entry["title"],
        "youtube_url": entry.get("yt_url"),
        "tiktok_url": entry.get("tt_url"),
        "status": "staged",
    }'''
assert old_meta in s
s = s.replace(old_meta, new_meta, 1)

old_main = '''        nxt = next_top_of_hour()
        wait = (nxt - datetime.now()).total_seconds()
        log("next post at %s (in %.0f min)"
            % (nxt.strftime("%H:%M"), wait / 60))
        if wait > 0:
            time.sleep(wait)
        hour_label = time.strftime("%Y-%m-%dT%H:00")'''
new_main = '''        nxt = next_slot()
        wait = (nxt - datetime.now()).total_seconds()
        log("next post at %s (in %.0f min)"
            % (nxt.strftime("%H:%M"), wait / 60))
        if wait > 0:
            time.sleep(wait)
        slot_min = "30" if datetime.now().minute >= 30 else "00"
        hour_label = time.strftime("%Y-%m-%dT%H:") + slot_min'''
assert old_main in s
s = s.replace(old_main, new_main, 1)

s = s.replace('log(f"{entry[\'id\']}: hour done, status={entry[\'status\']}")',
              'log(f"{entry[\'id\']}: slot done, status={entry[\'status\']}")', 1)
s = s.replace('time.sleep(60)  # avoid double-firing within the same hour',
              'time.sleep(60)  # avoid double-firing within the same slot', 1)
p.write_text(s)
print("hourly_poster.py patched: :00/:30 slots, ig_slot in meta")

# ---------- queue_seed.py: TARGET 12 -> 24 ----------
q = Path("/home/abel/clipsdaily/queue_seed.py")
t = q.read_text()
assert "TARGET = 12" in t, "TARGET line not found"
t = t.replace("TARGET = 12", "TARGET = 24", 1)
t = t.replace("TARGET=12", "TARGET=24", 1)
t = t.replace("keeps >=12 pending", "keeps >=24 pending", 1)
t = t.replace("below 6 pending", "below 12 pending", 1)
q.write_text(t)
print("queue_seed.py patched: TARGET 24")
