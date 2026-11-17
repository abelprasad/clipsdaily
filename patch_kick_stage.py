"""One-time patch: stage live clips that posted NOWHERE into queue.json.

Fixes the lost-clip hole that ate the overnight Kick adinross clip
(cut 2026-11-16 05:56, zero platforms posted, never staged, never
retried). Partial posts are NOT staged (would double-post the
platform that already went live).
"""
import shutil
from pathlib import Path

HERE = Path("/home/abel/clipsdaily")
P = HERE / "runner.py"
shutil.copy2(P, str(P) + ".bak-20261116-kickstage")
text = P.read_text()

old_import = "from poster import post_all        # noqa: E402"
new_import = "from poster import _caption, post_all  # noqa: E402"
assert text.count(old_import) == 1
text = text.replace(old_import, new_import)

helper = '''

QUEUE_FILE = HERE / "queue" / "queue.json"


def stage_to_queue(clip, tiktok_clip, channel, platform, spike,
                   queue_file=None):
    """Stage a live clip that posted NOWHERE into queue.json so the
    hourly poster retries it next slot instead of losing it.

    Only called when post_all returned no platform (done == []): a
    partial post is NOT staged, because the staged entry starts with
    yt_url/tt_url unset and the hourly poster would re-post a
    platform that already went live (duplicate Short). The overnight
    Kick adinross clip (cut 2026-11-16 05:56, zero platforms posted)
    is the case this fixes.

    Entry shape matches what hourly_poster.post_entry needs
    (id/streamer/platform/clip30/tiktok/title/captions/status/
    retries/urls/history). Campaign safety: no campaign_id and no
    vod_id — auto_submit.write_job requires a campaign_id, and
    eligibility_gate requires clip.vod_id == campaign.vod_id, so a
    live-staged entry can never become a campaign submission.
    Inserted at the FRONT so a fresh live clip posts next slot
    instead of waiting behind the VOD throwback backlog.
    Returns True if staged and verified, False if already present.
    """
    qf = Path(queue_file) if queue_file else QUEUE_FILE
    spike_seconds = float(spike.get("seconds_in", 0))
    entry_id = "live-%s-%s-%ss" % (platform, channel, int(spike_seconds))
    caption = _caption(channel, platform=platform)
    entry = {
        "id": entry_id,
        "streamer": channel,
        "platform": platform,
        "vod_id": None,
        "vod_date": None,
        "spike_seconds": spike_seconds,
        "intensity": spike.get("intensity", 0),
        "phrase": "",
        "clip30": str(clip),
        "tiktok": str(tiktok_clip) if tiktok_clip else None,
        "title": "%s clip | clipsdaily #shorts" % channel,
        "caption_yt": caption,
        "caption_tiktok": caption,
        "caption_ig": caption,
        "status": "pending",
        "yt_retries": 0,
        "tt_retries": 0,
        "yt_url": None,
        "tt_url": None,
        "history": [],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "live",
        "campaign_eligible": False,
    }
    try:
        entries = json.loads(qf.read_text()) if qf.exists() else []
    except Exception:
        entries = []
    if any(e.get("id") == entry_id for e in entries):
        print(f"[runner] {entry_id} already in queue, not re-staging",
              flush=True)
        return False
    entries.insert(0, entry)
    tmp = qf.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, indent=2))
    tmp.replace(qf)
    # Verify the write stuck (the hourly poster also writes this file
    # at slot boundaries; if our entry got clobbered, say so loudly).
    try:
        check = json.loads(qf.read_text())
        stuck = any(e.get("id") == entry_id for e in check)
    except Exception:
        stuck = False
    print(f"[runner] staged {entry_id} at front of queue "
          f"({'verified' if stuck else 'WRITE NOT VERIFIED'})", flush=True)
    return stuck
'''

anchor = "\n\ndef stop_requested():"
assert text.count(anchor) == 1
text = text.replace(anchor, helper + anchor, 1)

old_post = """            done = post_all(clip, channel, config, platform,
                            tiktok_clip=tiktok_clip)
            enabled = [p for p, on in
                       config.get("platforms", {}).items() if on]
            if enabled and set(done) >= set(enabled):
                # Posted everywhere it needed to go: eligible for the
                # 24h posted-clip retention (cleanup deletes it later).
                record_posted(clip)
                if tiktok_clip is not None:
                    record_posted(tiktok_clip)"""
new_post = """            done = post_all(clip, channel, config, platform,
                            tiktok_clip=tiktok_clip)
            enabled = [p for p, on in
                       config.get("platforms", {}).items() if on]
            if enabled and set(done) >= set(enabled):
                # Posted everywhere it needed to go: eligible for the
                # 24h posted-clip retention (cleanup deletes it later).
                record_posted(clip)
                if tiktok_clip is not None:
                    record_posted(tiktok_clip)
            elif enabled and not done:
                # Posted NOWHERE (all platforms failed/off): stage it
                # for the hourly poster instead of losing the clip.
                # Partial posts are NOT staged (would double-post the
                # platform that already went live).
                stage_to_queue(clip, tiktok_clip, channel, platform,
                               spike)"""
assert text.count(old_post) == 1
text = text.replace(old_post, new_post)

P.write_text(text)
print("runner.py patched OK")
