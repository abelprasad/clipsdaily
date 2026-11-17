"""Queue maintainer for clipsdaily hourly posting.

Cuts clips from completed Twitch VODs (chat-spike moments, throwback
labels) and from each watchlist channel's top clips by view count
(famous clips, no THROWBACK label), with the CURRENT cutter.py
framing, and registers them in queue/queue.json for hourly_poster.py.
Runs forever in tmux `clipsdaily-queue`: keeps >= TARGET pending
clips, cutting one at a time. Never touches the live runner,
config.yaml, or the VOD batch's files (it re-cuts the same spikes
into queue/clips/ with the NEW framing instead of importing the
batch's old-framing clips).

Famous clips insert at the front of the pending queue, so the FIFO
poster picks one next with no poster change; the maintainer keeps
>= FAMOUS_TARGET famous clips pending. Throwbacks keep running
behind them — famous mixes in, it does not replace throwbacks.

Usage:
  python3 queue_seed.py --seed N     # cut until N pending, then exit
  python3 queue_seed.py --seed-famous N  # cut until N famous pending
  python3 queue_seed.py --maintain   # loop forever, TARGET=24
"""
import fcntl
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .vod import download_chat, find_spikes  # noqa: E402
from .cutter import make_clip, make_tiktok_clip, probe_duration  # noqa: E402

from .paths import runtime_home
HERE = runtime_home()
QUEUE_DIR = HERE / "queue"
CLIPS_DIR = QUEUE_DIR / "clips"
WORK_DIR = QUEUE_DIR / "work"
QUEUE_FILE = QUEUE_DIR / "queue.json"
STATE_FILE = QUEUE_DIR / "state.json"
TDCLI = "/home/abel/.local/bin/TwitchDownloaderCLI"
TARGET = 24
CHANNELS = ["kaicenat", "ishowspeed", "xqc", "buddha", "sykkuno",
            "jynxzi", "stableronaldo", "zackrawrr", "hasanabi", "clix"]
# Seed VODs (channel, vod id). Spike lists come from /tmp/spikes_<ch>.json
# (written by vod_batch.py) or are downloaded on demand. The Speed
# Expedia VOD 2921253522 is EXCLUDED — campaign footage, never queued.
SEED_VODS = [("ishowspeed", "2928036561"),
             ("jynxzi", "2928767125"),
             ("stableronaldo", "2929115707")]
GQL = "https://gql.twitch.tv/gql"
CID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
QUEUE_LOCK = QUEUE_FILE.with_suffix(".lock")

# --- Famous clips (Nov 17, 2026, per Abel: "don't just do throwbacks,
# it should be famous clips") -------------------------------------------
# Top clips by view count per watchlist Twitch channel, via the same
# GQL path. No `criteria` means the clips connection comes back in
# views-descending order (verified live Nov 17, 2026: kaicenat's top
# clip 2.7M views, stableronaldo's 17.7M). `sort: VIEWS` does not
# exist in the ClipsSort enum and `sort: TRENDING` returns recent
# low-view clips instead — do not use either.
FAMOUS_CHANNELS = ["kaicenat", "ishowspeed", "sykkuno", "jynxzi",
                   "stableronaldo", "zackrawrr", "hasanabi", "clix"]
FAMOUS_PER_FETCH = 30   # top clips per channel per GQL fetch
FAMOUS_TARGET = 8       # keep >= 8 famous clips pending
MIN_FAMOUS_SECONDS = 10  # skip clips shorter than this
FAMOUS_CACHE_TTL = 6 * 3600  # refetch top lists at most every 6h
# Speed Expedia stream day (VOD 2921253522) — campaign footage, never
# queued. Clips carry no source-VOD id via GQL, so guard by date +
# title instead (see is_campaign_clip).
CAMPAIGN_STREAM_DATE = "2026-11-06"


def log(msg):
    print(f"[seed {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_queue():
    if not QUEUE_FILE.exists():
        return []
    try:
        return json.loads(QUEUE_FILE.read_text())
    except Exception:
        return []


def save_queue(entries):
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    tmp.replace(QUEUE_FILE)


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"vods": [], "done_spikes": []}


def save_state(state):
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def hms(s):
    s = int(s)
    return "%02d:%02d:%02d" % (s // 3600, (s % 3600) // 60, s % 60)


def gql(query):
    req = urllib.request.Request(
        GQL, data=json.dumps({"query": query}).encode(),
        headers={"Client-ID": CID, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def vod_created_at(channel, vid):
    try:
        q = ('query { user(login: "%s") { videos(first: 5, type: ARCHIVE, '
             'sort: TIME) { edges { node { id createdAt } } } } }' % channel)
        d = gql(q)
        for e in ((d.get("data") or {}).get("user") or {}).get("videos", {}).get("edges", []):
            n = e["node"]
            if str(n["id"]) == str(vid):
                return (n.get("createdAt") or "")[:10]
    except Exception as e:
        log(f"GQL date lookup failed for {channel}/{vid}: {e}")
    return ""


def discover_vods():
    """More recent archives for the watchlist (last 7 days by viewCount)."""
    found = []
    for ch in CHANNELS:
        try:
            q = ('query { user(login: "%s") { videos(first: 5, type: ARCHIVE, '
                 'sort: TIME) { edges { node { id title createdAt '
                 'lengthSeconds viewCount } } } } }' % ch)
            d = gql(q)
            for e in ((d.get("data") or {}).get("user") or {}).get("videos", {}).get("edges", []):
                n = e["node"]
                if str(n["id"]) == "2921253522":
                    continue
                if int(n.get("lengthSeconds") or 0) < 1800:
                    continue
                found.append((ch, str(n["id"]), (n.get("createdAt") or "")[:10],
                              int(n.get("viewCount") or 0)))
        except Exception as e:
            log(f"discover {ch} failed: {e}")
    found.sort(key=lambda t: -t[3])
    return found


# ------------------------------------------------------------------
# Famous clips
# ------------------------------------------------------------------

def fetch_top_clips(channel, first=FAMOUS_PER_FETCH):
    """Top clips for a channel by view count. No criteria = views
    descending (verified live). Returns [{slug, title, views,
    duration, created}, ...] in view order."""
    q = ('query { user(login: "%s") { clips(first: %d) { edges { node '
         '{ slug title viewCount durationSeconds createdAt } } } } }'
         % (channel, first))
    d = gql(q)
    edges = ((d.get("data") or {}).get("user") or {}).get("clips", {}).get("edges", [])
    out = []
    for e in edges:
        n = e.get("node") or {}
        out.append({
            "slug": str(n.get("slug") or ""),
            "title": str(n.get("title") or ""),
            "views": int(n.get("viewCount") or 0),
            "duration": int(n.get("durationSeconds") or 0),
            "created": str(n.get("createdAt") or "")[:10],
        })
    return out


def clean_clip_title(title):
    """Clip title minus hashtags, for captions. '' means junk (too
    short / no letters) — fall back to the transcribed phrase."""
    t = re.sub(r"#\w+", "", str(title or ""))
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) < 4 or not re.search(r"[A-Za-z]", t):
        return ""
    return t


def is_campaign_clip(channel, clip):
    """Never queue Speed Expedia campaign footage (VOD 2921253522,
    streamed 2026-11-06). GQL clips carry no source-VOD id, so guard
    on the stream date + the Expedia name."""
    if channel != "ishowspeed":
        return False
    if clip.get("created") == CAMPAIGN_STREAM_DATE:
        return True
    return "expedia" in (clip.get("title") or "").lower()


def famous_clip_id(channel, slug):
    safe = re.sub(r"[^A-Za-z0-9-]", "", slug)
    return "famous-%s-%s" % (channel, safe)


def build_famous_texts(channel, title):
    """No THROWBACK label. One line, streamer + moment, no hashtags,
    no boilerplate, no date — same caption rules as Nov 15."""
    yt_title = ("%s — %s | clipsdaily #shorts" % (channel, title))[:100]
    line = "%s: %s" % (channel, title)
    return yt_title, line, line, line


def famous_pending(entries):
    return [e for e in entries
            if e.get("status") == "pending" and e.get("source") == "famous"]


_famous_cache = {}
_famous_cache_at = 0
_famous_next_channel = 0


def next_famous_clip():
    """Next unseen famous clip across the watchlist, or None.
    Channels are tried round-robin (one clip per channel per pass)
    so the mix spans channels instead of draining one channel's
    top list first. Each channel's top list is fetched once per
    cache window. A clip is unseen when its id is in neither
    queue.json nor state.json done_famous, is long enough, and is
    not campaign footage."""
    global _famous_cache_at, _famous_next_channel
    now = time.time()
    if now - _famous_cache_at > FAMOUS_CACHE_TTL:
        _famous_cache.clear()
        _famous_cache_at = now
    queue_ids = {e.get("id") for e in load_queue()}
    done_famous = set(load_state().get("done_famous", []))
    n = len(FAMOUS_CHANNELS)
    for k in range(n):
        idx = (_famous_next_channel + k) % n
        channel = FAMOUS_CHANNELS[idx]
        if channel not in _famous_cache:
            try:
                _famous_cache[channel] = fetch_top_clips(channel)
            except Exception as e:
                log(f"famous fetch {channel} failed: {e}")
                _famous_cache[channel] = []
        for clip in _famous_cache[channel]:
            if not clip.get("slug"):
                continue
            if clip.get("duration", 0) < MIN_FAMOUS_SECONDS:
                continue
            if is_campaign_clip(channel, clip):
                continue
            cid = famous_clip_id(channel, clip["slug"])
            if cid in queue_ids or cid in done_famous:
                continue
            _famous_next_channel = (idx + 1) % n
            return channel, clip
    return None


def claim_famous(clip_id):
    """Mark a famous clip id as claimed (done) under the queue lock
    so two seeder processes never cut the same clip. False when the
    id is already queued or claimed."""
    with open(QUEUE_LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        if any(e.get("id") == clip_id for e in load_queue()):
            return False
        state = load_state()
        done = state.setdefault("done_famous", [])
        if clip_id in done:
            return False
        done.append(clip_id)
        save_state(state)
    return True


def unclaim_famous(clip_id):
    """Release a claim (cut failed) so the clip can be retried later."""
    with open(QUEUE_LOCK, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        state = load_state()
        done = state.get("done_famous", [])
        if clip_id in done:
            done.remove(clip_id)
            save_state(state)


def download_famous_clip(slug, channel, out):
    """Download one clip via TwitchDownloaderCLI. Full clip URL
    first (the bare slug fails TDCLI's parser on some suffixes,
    e.g. ones with underscores — cost ~100s before falling back),
    slug as fallback."""
    if out.exists():
        return out
    for clip_ref in ("https://www.twitch.tv/%s/clip/%s" % (channel, slug),
                     slug):
        cmd = [TDCLI, "clipdownload", "--id", clip_ref, "-o", str(out),
               "--collision", "overwrite"]
        log(f"clipdownload {clip_ref}")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode == 0 and out.exists():
            return out
        log(f"clipdownload {clip_ref} failed: {r.stderr[-200:]}")
    raise RuntimeError("clipdownload failed for %s" % slug)


def insert_at_front_of_pending(entries, entry):
    """Famous clips go first among pending so the FIFO poster picks
    one next — no poster change needed. Posted/failed history keeps
    its order ahead of them."""
    for i, e in enumerate(entries):
        if e.get("status") == "pending":
            entries.insert(i, entry)
            return entries
    entries.append(entry)
    return entries


def cut_famous_entry(channel, clip):
    """Download a top clip, cut 30s (+ TikTok variant when the clip
    is long enough) with the current cutter framing, register at the
    front of the pending queue."""
    slug = clip["slug"]
    clip_id = famous_clip_id(channel, slug)
    if not claim_famous(clip_id):
        log(f"{clip_id} already queued/claimed, skipping")
        return None
    try:
        title = clean_clip_title(clip.get("title", ""))
        work = WORK_DIR / clip_id
        work.mkdir(parents=True, exist_ok=True)
        src = work / "clip.mp4"
        download_famous_clip(slug, channel, src)
        duration = probe_duration(src)
        spike = duration / 2.0
        # Good title => it IS the hook, no Whisper run. Junk title =>
        # hook=None transcribes and derives the hook + SRT instead.
        hook = title or None
        CLIPS_DIR.mkdir(parents=True, exist_ok=True)
        clip30 = make_clip(src, spike, channel, clip_seconds=30,
                           model="small", out_dir=work, hook=hook)
        final30 = CLIPS_DIR / ("%s_30s.mp4" % clip_id)
        clip30.replace(final30)
        srt30 = clip30.with_suffix(".srt")
        if srt30.exists():
            srt30.replace(CLIPS_DIR / ("%s_30s.srt" % clip_id))
        tiktok = None
        # TikTok variant needs a 60-90s single moment: the window is
        # 20s before the spike + 55s after, so the clip must be
        # >= 110s for it to fit. Shorter famous clips post via the
        # poster's 30s fallback (allow_short) instead.
        if duration >= 110:
            try:
                tt, method = make_tiktok_clip(
                    src, [{"seconds_in": spike, "intensity": 0}], channel,
                    model="small", out_dir=work, hook=hook)
                if tt:
                    tiktok = CLIPS_DIR / ("%s_tiktok.mp4" % clip_id)
                    tt.replace(tiktok)
                    srt_tt = tt.with_suffix(".srt")
                    if srt_tt.exists():
                        srt_tt.replace(CLIPS_DIR / ("%s_tiktok.srt" % clip_id))
                    log(f"{clip_id}: tiktok variant ({method})")
            except Exception as e:
                log(f"{clip_id}: tiktok variant failed: {e}")
        for p in work.glob("*"):
            try:
                p.unlink()
            except Exception:
                pass
        try:
            work.rmdir()
        except Exception:
            pass
        phrase = title or srt_phrase(CLIPS_DIR / ("%s_30s.srt" % clip_id))
        yt_title, yt_cap, tt_cap, ig_cap = build_famous_texts(
            channel, phrase or "clip")
        entry = {
            "id": clip_id, "streamer": channel, "platform": "twitch",
            "vod_id": None, "vod_date": clip.get("created", ""),
            "spike_seconds": spike, "intensity": 0, "phrase": phrase,
            "clip30": str(final30),
            "tiktok": str(tiktok) if tiktok else None,
            "title": yt_title, "caption_yt": yt_cap,
            "caption_tiktok": tt_cap, "caption_ig": ig_cap,
            "status": "pending", "yt_retries": 0, "tt_retries": 0,
            "yt_url": None, "tt_url": None, "history": [],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source": "famous", "views": clip.get("views", 0),
            "clip_slug": slug,
        }
        with open(QUEUE_LOCK, "w") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            entries = load_queue()
            if any(e.get("id") == clip_id for e in entries):
                log(f"{clip_id} queued by another process, skipping")
                return None
            insert_at_front_of_pending(entries, entry)
            save_queue(entries)
        log(f"QUEUED FAMOUS {clip_id} ({clip.get('views', 0)} views) "
            f"tiktok={'yes' if tiktok else 'no'}")
        return entry
    except Exception:
        unclaim_famous(clip_id)
        raise


def seed_famous(target):
    """Cut famous clips until `target` are pending, then exit."""
    while True:
        pending = famous_pending(load_queue())
        if len(pending) >= target:
            log(f"seed-famous done: {len(pending)} famous pending")
            return
        job = next_famous_clip()
        if job is None:
            log("seed-famous: no unseen famous clips left")
            return
        channel, clip = job
        try:
            cut_famous_entry(channel, clip)
        except Exception as e:
            log(f"FAMOUS CUT FAIL {channel}/{clip.get('slug')}: {e}")
            time.sleep(30)
        time.sleep(5)


def dedup_spikes(spikes, min_gap=120):
    """Strongest-first, drop spikes within min_gap seconds of a kept one."""
    ranked = sorted(spikes, key=lambda s: s.get("intensity", 0), reverse=True)
    kept = []
    for s in ranked:
        sec = float(s["seconds_in"])
        if sec < 120:  # skip stream-start noise
            continue
        if all(abs(sec - float(k["seconds_in"])) >= min_gap for k in kept):
            kept.append(s)
    return kept


def get_spikes(channel, vid):
    """Spike list for a VOD: reuse /tmp/spikes_<ch>.json if present,
    else download chat and run the detector."""
    cached = Path("/tmp/spikes_%s.json" % channel)
    if cached.exists():
        try:
            spikes = json.loads(cached.read_text())
            log(f"{channel}/{vid}: {len(spikes)} spikes from cache")
            return dedup_spikes(spikes)
        except Exception:
            pass
    chat = HERE / "vod" / ("%s_chat.json" % vid)
    if not chat.exists():
        download_chat(vid, chat)
    spikes = find_spikes(chat)
    return dedup_spikes(spikes)


def download_crop(vid, start, end, out):
    if out.exists():
        return out
    cmd = [TDCLI, "videodownload", "--id", str(vid), "-o", str(out),
           "--quality", "1080p60", "--collision", "overwrite",
           "-b", hms(max(0, start)), "-e", hms(end)]
    log(f"crop {vid} {hms(max(0, start))}-{hms(end)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if r.returncode != 0:
        raise RuntimeError("videodownload failed: %s" % r.stderr[-400:])
    return out


def srt_phrase(srt_path):
    """Best short spoken line from an SRT file, for titles/captions."""
    try:
        text = Path(srt_path).read_text(errors="ignore")
    except Exception:
        return ""
    lines = []
    for block in text.split("\n\n"):
        parts = block.strip().split("\n")
        if len(parts) >= 3:
            lines.append(" ".join(parts[2:]).strip())
    best = ""
    for line in lines:
        words = re.findall(r"[A-Za-z0-9'$]+", line)
        if 4 <= len(words) <= 10 and len(line) > len(best):
            clean = re.sub(r"[^A-Za-z0-9 $',!?-]", "", line).strip()
            if clean and "http" not in clean.lower():
                best = clean
    if len(best) > 45:
        best = best[:45].rsplit(" ", 1)[0]
    return best


def build_texts(channel, phrase, vod_date):
    # Captions cut down Nov 15, 2026, per Abel: one line, no hashtags
    # (they don't drive reach), no boilerplate, no date. The streamer
    # name in the line is the credit; the hook overlay credits too.
    title = ("THROWBACK: %s — %s | clipsdaily #shorts" % (channel, phrase)
             if phrase else "THROWBACK: %s clip | clipsdaily #shorts" % channel)
    title = title[:100]
    line = "Throwback — %s: %s" % (channel, phrase or "clip")
    return title, line, line, line


def cut_entry(channel, vid, spike, vod_date):
    """Cut one queue entry (30s + TikTok variant) with the new framing."""
    sec = float(spike["seconds_in"])
    inten = spike.get("intensity", 0)
    clip_id = "%s-%s-%ds" % (channel, vid, int(sec))
    entries = load_queue()
    if any(e["id"] == clip_id for e in entries):
        log(f"{clip_id} already queued, skipping")
        return None
    state = load_state()
    if clip_id in state.get("done_spikes", []):
        return None
    work = WORK_DIR / clip_id
    work.mkdir(parents=True, exist_ok=True)
    crop = work / "crop.mp4"
    download_crop(vid, sec - 40, sec + 120, crop)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    clip30 = make_clip(crop, 40, channel, clip_seconds=30, model="small",
                       out_dir=work)
    final30 = CLIPS_DIR / ("%s_30s.mp4" % clip_id)
    clip30.replace(final30)
    srt30 = clip30.with_suffix(".srt")
    if srt30.exists():
        srt30.replace(CLIPS_DIR / ("%s_30s.srt" % clip_id))
    tiktok = None
    try:
        tt, method = make_tiktok_clip(
            crop, [{"seconds_in": 40, "intensity": inten}], channel,
            model="small", out_dir=work)
        if tt:
            tiktok = CLIPS_DIR / ("%s_tiktok.mp4" % clip_id)
            tt.replace(tiktok)
            srt_tt = tt.with_suffix(".srt")
            if srt_tt.exists():
                srt_tt.replace(CLIPS_DIR / ("%s_tiktok.srt" % clip_id))
            log(f"{clip_id}: tiktok variant ({method})")
    except Exception as e:
        log(f"{clip_id}: tiktok variant failed: {e}")
    for p in work.glob("*"):
        try:
            p.unlink()
        except Exception:
            pass
    try:
        work.rmdir()
    except Exception:
        pass
    phrase = srt_phrase(CLIPS_DIR / ("%s_30s.srt" % clip_id))
    title, yt_desc, tt_cap, ig_cap = build_texts(channel, phrase, vod_date)
    entry = {
        "id": clip_id, "streamer": channel, "platform": "twitch",
        "vod_id": str(vid), "vod_date": vod_date, "spike_seconds": sec,
        "intensity": inten, "phrase": phrase,
        "clip30": str(final30),
        "tiktok": str(tiktok) if tiktok else None,
        "title": title, "caption_yt": yt_desc,
        "caption_tiktok": tt_cap, "caption_ig": ig_cap,
        "status": "pending", "yt_retries": 0, "tt_retries": 0,
        "yt_url": None, "tt_url": None, "history": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    entries = load_queue()
    entries.append(entry)
    save_queue(entries)
    state = load_state()
    state.setdefault("done_spikes", []).append(clip_id)
    save_state(state)
    log(f"QUEUED {clip_id} (intensity {inten}x) tiktok={'yes' if tiktok else 'no'}")
    return entry


def next_job(state):
    """Next (channel, vid, spike, date) to cut, or None."""
    for v in state.get("vods", []):
        idx = v.get("next", 0)
        spikes = v.get("spikes", [])
        if idx < len(spikes):
            v["next"] = idx + 1
            save_state(state)
            return v["channel"], v["vod"], spikes[idx], v.get("date", "")
    return None


def ensure_vods(state):
    if state.get("vods"):
        return
    vods = []
    for channel, vid in SEED_VODS:
        spikes = get_spikes(channel, vid)
        date = vod_created_at(channel, vid)
        vods.append({"channel": channel, "vod": vid, "date": date,
                     "spikes": spikes, "next": 0})
        log(f"seed VOD {channel}/{vid}: {len(spikes)} usable spikes, date {date}")
    state["vods"] = vods
    save_state(state)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--maintain"
    target = TARGET
    if mode == "--seed" and len(sys.argv) > 2:
        target = int(sys.argv[2])
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    if mode == "--seed-famous":
        famous_target = (int(sys.argv[2]) if len(sys.argv) > 2
                         else FAMOUS_TARGET)
        seed_famous(famous_target)
        return
    state = load_state()
    ensure_vods(state)
    while True:
        # Famous top-up runs even when the queue is healthy: famous
        # clips sit at the front of pending, so they post first.
        # No unseen famous clip => fall through to throwbacks.
        entries = load_queue()
        if len(famous_pending(entries)) < FAMOUS_TARGET:
            job = next_famous_clip()
            if job is not None:
                channel, clip = job
                try:
                    cut_famous_entry(channel, clip)
                except Exception as e:
                    log(f"FAMOUS CUT FAIL {channel}/{clip.get('slug')}: {e}")
                time.sleep(5)
                continue
        pending = [e for e in entries if e["status"] == "pending"]
        if len(pending) >= target:
            if mode == "--seed":
                log(f"seed done: {len(pending)} pending")
                return
            log(f"queue healthy: {len(pending)} pending, sleeping 5m")
            time.sleep(300)
            continue
        job = next_job(load_state())
        if job is None:
            log("work list exhausted, discovering more VODs")
            found = discover_vods()
            state = load_state()
            have = {(v["channel"], v["vod"]) for v in state.get("vods", [])}
            added = 0
            for channel, vid, date, views in found:
                if (channel, vid) in have:
                    continue
                try:
                    spikes = get_spikes(channel, vid)
                except Exception as e:
                    log(f"{channel}/{vid}: spikes failed: {e}")
                    continue
                if not spikes:
                    continue
                state.setdefault("vods", []).append(
                    {"channel": channel, "vod": vid, "date": date,
                     "spikes": spikes[:8], "next": 0})
                added += 1
                log(f"discovered VOD {channel}/{vid} ({date}, {views} views, "
                    f"{len(spikes)} spikes)")
                if added >= 3:
                    break
            save_state(state)
            if added == 0:
                log("no new VODs found, sleeping 10m")
                time.sleep(600)
            continue
        channel, vid, spike, date = job
        try:
            cut_entry(channel, vid, spike, date)
        except Exception as e:
            log(f"CUT FAIL {channel}/{vid} @{spike.get('seconds_in')}: {e}")
            time.sleep(30)
        time.sleep(5)


if __name__ == "__main__":
    main()
