"""Re-cut one queue clip in FULL FRAME (no cropping) with the current
cutter (motion hook, no word captions). Re-downloads the VOD crop,
cuts 30s + TikTok variant, replaces the files in queue/clips/, and
creates/updates the queue entry (preserving post status + URLs).
Usage: python3 recut_fullframe.py <clip_id> <channel> <vod> <spike_s>
       <intensity> <vod_date>
"""
import json
import sys
import time
from pathlib import Path

from .cutter import make_clip, make_tiktok_clip  # noqa: E402
from .queue_seed import (CLIPS_DIR, WORK_DIR, build_texts, download_crop,  # noqa: E402
                        load_queue, save_queue, srt_phrase)


def main():
    clip_id, channel, vid, sec, inten, vod_date = (
        sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]),
        float(sys.argv[5]), sys.argv[6])
    work = WORK_DIR / clip_id
    work.mkdir(parents=True, exist_ok=True)
    crop = work / "crop.mp4"
    print(f"[recut] {clip_id}: downloading crop {vid} {sec - 40:.0f}-"
          f"{sec + 120:.0f}", flush=True)
    download_crop(vid, sec - 40, sec + 120, crop)
    print(f"[recut] {clip_id}: cutting 30s (full frame)", flush=True)
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
            print(f"[recut] {clip_id}: tiktok variant ({method})", flush=True)
    except Exception as e:
        print(f"[recut] {clip_id}: tiktok variant failed: {e}", flush=True)
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
    entries = load_queue()
    entry = next((e for e in entries if e["id"] == clip_id), None)
    if entry is None:
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
        entries.append(entry)
        print(f"[recut] {clip_id}: entry created", flush=True)
    else:
        entry.update({"clip30": str(final30),
                      "tiktok": str(tiktok) if tiktok else None,
                      "phrase": phrase, "title": title,
                      "caption_yt": yt_desc, "caption_tiktok": tt_cap,
                      "caption_ig": ig_cap})
        print(f"[recut] {clip_id}: entry updated (status={entry['status']})",
              flush=True)
    save_queue(entries)
    print(json.dumps({"clip_id": clip_id, "status": entry["status"],
                      "tiktok": bool(tiktok), "title": title,
                      "yt_url": entry.get("yt_url"),
                      "tt_url": entry.get("tt_url")}, indent=2))


if __name__ == "__main__":
    main()
