from pathlib import Path
p = Path("/home/abel/clipsdaily/hourly_poster.py")
s = p.read_text()
old = '''    yt_done = bool(entry.get("yt_url")) and entry["yt_url"] != "FAILED"
    tt_done = bool(entry.get("tt_url")) and entry["tt_url"] != "FAILED"
    yt_dead = entry.get("yt_url") == "FAILED"
    tt_dead = entry.get("tt_url") == "FAILED"
    if yt_done and tt_done:
        entry["status"] = "posted"
    elif yt_dead and tt_dead:
        entry["status"] = "failed"
    elif yt_done or tt_done:
        entry["status"] = "partial"
    else:
        entry["status"] = "pending"'''
new = '''    yt_done = bool(entry.get("yt_url")) and entry["yt_url"] != "FAILED"
    tt_done = bool(entry.get("tt_url")) and entry["tt_url"] != "FAILED"
    yt_dead = entry.get("yt_url") == "FAILED"
    tt_dead = entry.get("tt_url") == "FAILED"
    # A platform marked FAILED is resolved: the entry must not sit
    # "partial" forever and block the queue. If at least one platform
    # is live, the clip counts as posted (the failed one is done
    # retrying); if both failed, it is failed.
    if (yt_done or yt_dead) and (tt_done or tt_dead):
        entry["status"] = "posted" if (yt_done or tt_done) else "failed"
    elif yt_done or tt_done:
        entry["status"] = "partial"
    else:
        entry["status"] = "pending"'''
assert old in s
s = s.replace(old, new, 1)
p.write_text(s)
print("hourly_poster.py patched: FAILED platform no longer stalls the queue")
