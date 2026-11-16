#!/usr/bin/env python3
"""Patch clipsdaily captions (cut down, Nov 15 2026 per Abel) + lower hook.

- queue_seed.build_texts: one-line captions, no hashtags, no boilerplate, no date.
- campaign_cut.build_campaign_texts: one line, required hashtag only, gate-safe.
- poster._caption: one line, no hashtags. post_youtube: no boilerplate append.
- cutter.py hook y: 150 -> 300 (clear the platform top UI).
- post_tiktok_fixed.py: trimmed Speed captions for the pending HK re-upload.
- Regenerate queue.json caption fields + staged ig-outbox caption.txt files.
- Gate-test the new campaign captions with eligibility_gate._check_caption.
Run as abel on indra. Exits 0 only if every replacement + check passed.
"""
import json
import os
import sys

BASE = "/home/abel/clipsdaily"
sys.path.insert(0, BASE)

failures = []


def replace(path, old, new, label):
    with open(path) as f:
        src = f.read()
    n = src.count(old)
    if n != 1:
        failures.append(f"{label}: old block found {n}x (want 1), SKIPPED")
        print(f"FAIL {label}: found {n}x")
        return False
    with open(path, "w") as f:
        f.write(src.replace(old, new))
    print(f"OK {label}")
    return True


# 1. queue_seed.py build_texts
old_qs = r'''def build_texts(channel, phrase, vod_date):
    date = (" (%s)" % vod_date) if vod_date else ""
    title = ("THROWBACK: %s — %s | clipsdaily #shorts" % (channel, phrase)
             if phrase else "THROWBACK: %s clip | clipsdaily #shorts" % channel)
    title = title[:100]
    yt_desc = ("Throwback — %s%s.\n%s\n\nclipsdaily • %s\n"
               "#clipsdaily #throwback #%s #twitchclips\n\n"
               "Best stream moments, clipped daily. "
               "Credit to the streamer in every post."
               % (channel, date, phrase or "", channel, channel))
    tt_cap = ("Throwback — %s: %s #throwback #clipsdaily #%s #twitch"
              % (channel, phrase or "clip", channel))[:200]
    ig_cap = ("Throwback — %s%s. %s\nclipsdaily • %s\n"
              "#throwback #clipsdaily #%s\n\n"
              "Best stream moments, clipped daily. "
              "Credit to the streamer in every post."
              % (channel, date, phrase or "", channel, channel))
    return title, yt_desc, tt_cap, ig_cap'''
new_qs = r'''def build_texts(channel, phrase, vod_date):
    # Captions cut down Nov 15, 2026, per Abel: one line, no hashtags
    # (they don't drive reach), no boilerplate, no date. The streamer
    # name in the line is the credit; the hook overlay credits too.
    title = ("THROWBACK: %s — %s | clipsdaily #shorts" % (channel, phrase)
             if phrase else "THROWBACK: %s clip | clipsdaily #shorts" % channel)
    title = title[:100]
    line = "Throwback — %s: %s" % (channel, phrase or "clip")
    return title, line, line, line'''
replace(os.path.join(BASE, "queue_seed.py"), old_qs, new_qs, "queue_seed.build_texts")

# 2. campaign_cut.py build_campaign_texts
old_cc = r'''def build_campaign_texts(campaign, streamer, destination, phrase, hook):
    """Captions that satisfy the campaign's mention/hashtag rules."""
    brand = campaign.get("brand") or ""
    hashtag = campaign.get("required_hashtag") or ""
    mentions = campaign.get("required_mentions") or []
    mention_str = " ".join(mentions)
    dest = (" — %s" % destination) if destination else ""
    hook_title = (hook or "").strip().rstrip("!").title()
    title = ("%s | %s x %s %s" % (hook_title or "Clip", streamer,
                                  brand, hashtag)).strip()[:100]
    yt_desc = (
        "%s\n%s x %s%s.\n%s\n\nclipsdaily • %s\n%s %s #clipsdaily\n\n"
        "Best stream moments, clipped daily. "
        "Credit to the streamer in every post."
        % (hook or "", streamer, brand, dest, phrase or "",
           streamer, hashtag, ("#" + mention_str.lower().replace(" ", " #")
                               if mention_str else "")))
    tt_cap = ("%s — %s x %s%s %s %s #clipsdaily"
              % (phrase or hook or "clip", streamer, brand, dest,
                 hashtag, ("#" + mention_str if mention_str else "")))
    tt_cap = " ".join(tt_cap.split())[:200]
    ig_cap = (
        "%s\n%s x %s%s.\nclipsdaily • %s\n%s %s #clipsdaily\n\n"
        "Best stream moments, clipped daily. "
        "Credit to the streamer in every post."
        % (hook or "", streamer, brand, dest, streamer, hashtag,
           ("#" + mention_str if mention_str else "")))
    return title, yt_desc, tt_cap, ig_cap'''
new_cc = r'''def build_campaign_texts(campaign, streamer, destination, phrase, hook):
    """Captions that satisfy the campaign's mention/hashtag rules.

    Cut down Nov 15, 2026, per Abel: one line. The required hashtag is
    the ONLY hashtag (campaigns require it; generic tags don't help
    reach). Brand, destination, and required mentions are appended
    only if the money line doesn't already name them, so the gate
    (mentions + hashtag + destination in every caption) still passes.
    """
    brand = campaign.get("brand") or ""
    hashtag = campaign.get("required_hashtag") or ""
    mentions = campaign.get("required_mentions") or []
    hook_title = (hook or "").strip().rstrip("!").title()
    title = ("%s | %s x %s %s" % (hook_title or "Clip", streamer,
                                  brand, hashtag)).strip()[:100]
    base = (phrase or hook or "clip").strip()
    parts = [base]
    for token in [brand, destination] + list(mentions):
        if token and token.lower() not in " ".join(parts).lower():
            parts.append(token)
    if hashtag:
        parts.append(hashtag)
    line = " ".join(" ".join(parts).split())
    return title, line, line, line'''
replace(os.path.join(BASE, "campaign_cut.py"), old_cc, new_cc, "campaign_cut.build_campaign_texts")

# 3. poster.py _caption + post_youtube description
old_cap = r'''def _caption(channel, game="", platform="twitch"):
    tag = f" #{game}" if game else ""
    src = {"twitch": "#twitch #twitchclips", "kick": "#kick #kickclips",
           "youtube": "#youtube #youtubelive"}.get(platform, "#livestream")
    return (f"clipsdaily - {channel}{tag}\n"
            f"#clipsdaily {src} #gaming")'''
new_cap = r'''def _caption(channel, game="", platform="twitch"):
    # Cut down Nov 15, 2026, per Abel: one line, no hashtags. The
    # streamer name is the credit; the hook overlay carries the moment.
    return f"clipsdaily • {channel}"'''
replace(os.path.join(BASE, "poster.py"), old_cap, new_cap, "poster._caption")

old_desc = r'''    description = (caption + "\n\n"
                   "Best stream moments, clipped daily. "
                   "Credit to the streamer in every post.")'''
new_desc = r'''    description = caption'''
replace(os.path.join(BASE, "poster.py"), old_desc, new_desc, "poster.post_youtube description")

# 4. cutter.py hook y 150 -> 300
old_y = r'''"y='150-40*pow(2,-10*min(t/0.25,1))':"'''
new_y = r'''"y='300-40*pow(2,-10*min(t/0.25,1))':"'''
replace(os.path.join(BASE, "cutter.py"), old_y, new_y, "cutter hook y 150->300")

old_cmt = "# first ~3 seconds, big bold centered text near the top. hook is the"
new_cmt = "# first ~3 seconds, big bold centered text, set lower (y=300) to clear\n    # the platform top UI. hook is the"
replace(os.path.join(BASE, "cutter.py"), old_cmt, new_cmt, "cutter hook comment")

# 5. post_tiktok_fixed.py Speed captions (pending HK re-upload)
old_jp = ("IShowSpeed surprises Hudson with a trip to Japan, thanks to Expedia "
          "#IShowSpeed #Expedia #ishowspeed #clipsdaily")
new_jp = "IShowSpeed gives Hudson a trip to Japan with Expedia #IShowSpeed"
replace(os.path.join(BASE, "post_tiktok_fixed.py"), old_jp, new_jp, "post_tiktok_fixed Japan caption")
old_hk = ("IShowSpeed gives Anthony $10,000 from Expedia to travel to Hong Kong "
          "#IShowSpeed #Expedia #ishowspeed #clipsdaily")
new_hk = "IShowSpeed gives Anthony $10,000 from Expedia to travel to Hong Kong #IShowSpeed"
replace(os.path.join(BASE, "post_tiktok_fixed.py"), old_hk, new_hk, "post_tiktok_fixed HK caption")

# Syntax check all edited files.
import py_compile
for fn in ("queue_seed.py", "campaign_cut.py", "poster.py", "cutter.py",
           "post_tiktok_fixed.py"):
    try:
        py_compile.compile(os.path.join(BASE, fn), doraise=True)
        print(f"OK compile {fn}")
    except Exception as e:
        failures.append(f"compile {fn}: {e}")
        print(f"FAIL compile {fn}: {e}")

# 6. Regenerate queue.json caption fields with the new builder.
from queue_seed import build_texts
qpath = os.path.join(BASE, "queue", "queue.json")
with open(qpath) as f:
    entries = json.load(f)
for e in entries:
    title, yt, tt, ig = build_texts(e["streamer"], e.get("phrase") or "",
                                    e.get("vod_date"))
    e["caption_yt"], e["caption_tiktok"], e["caption_ig"] = yt, tt, ig
    print(f"QUEUE {e['id']}: {yt!r}")
tmp = qpath + ".tmp"
with open(tmp, "w") as f:
    json.dump(entries, f, indent=2)
os.replace(tmp, qpath)
print("OK queue.json regenerated")

# 7. Update staged ig-outbox caption.txt files from queue.json.
outbox = os.path.join(BASE, "ig-outbox")
by_id = {e["id"]: e for e in entries}
for d in sorted(os.listdir(outbox)):
    mpath = os.path.join(outbox, d, "meta.json")
    if not os.path.exists(mpath):
        continue
    with open(mpath) as f:
        meta = json.load(f)
    if meta.get("status") != "staged":
        continue
    e = by_id.get(d)
    if not e:
        print(f"OUTBOX {d}: staged but no queue entry, left alone")
        continue
    with open(os.path.join(outbox, d, "caption.txt"), "w") as f:
        f.write(e["caption_ig"])
    print(f"OUTBOX {d}: caption.txt updated to {e['caption_ig']!r}")

# 8. Gate-test the new campaign captions.
from campaign_cut import build_campaign_texts
from eligibility_gate import _check_caption
campaign = {"brand": "Expedia", "required_hashtag": "#IShowSpeed",
            "required_mentions": ["Expedia"]}
for dest, phrase, hook in [
        ("Japan", "You're going to Japan", "HE JUST WON A TRIP TO JAPAN"),
        ("Hong Kong", "Expedia is giving you 10 thousand dollars",
         "SPEED GAVE HIM $10,000")]:
    title, yt, tt, ig = build_campaign_texts(campaign, "ishowspeed", dest,
                                             phrase, hook)
    clip = {"caption_yt": yt, "caption_tiktok": tt, "caption_ig": ig,
            "destination": dest}
    ok, detail = _check_caption(clip, campaign)
    print(f"GATE {dest}: ok={ok} caption={yt!r} detail={detail}")
    if not ok:
        failures.append(f"gate {dest}: {detail}")

print("FAILURES:" if failures else "ALL OK")
for f in failures:
    print(" -", f)
sys.exit(1 if failures else 0)
