"""Tests for hourly_poster.save_entry (merge-save) — the fix for the
2026-11-16 queue race that lost live-kick-adinross-72s.

Race: the poster loaded the queue at slot start and save_queue()
rewrote the whole list at slot end. A clip staged mid-slot by
runner.stage_to_queue() was silently wiped (31 pending at 13:30:25,
30 pending at 13:35:25, poster save ~13:34).

save_entry() re-reads disk and persists only the one processed
entry, so mid-slot stagings survive. This test replays the exact
sequence against temp files. No network, no posting, no live state.

Run:  python3 test_poster_merge_save.py
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
try:
    from clipsdaily import hourly_poster
    from clipsdaily import runner
except ImportError:
    import hourly_poster
    import runner


def _vod_entry(eid):
    return {"id": eid, "streamer": "jynxzi", "platform": "twitch",
            "vod_id": "2928767125", "vod_date": "2026-11-15",
            "spike_seconds": 12505.0, "intensity": 5.0, "phrase": "x",
            "clip30": "/tmp/%s_30s.mp4" % eid, "tiktok": None,
            "title": "t", "caption_yt": "c", "caption_tiktok": "c",
            "caption_ig": "c", "status": "pending",
            "yt_retries": 0, "tt_retries": 0, "yt_url": None,
            "tt_url": None, "history": []}


def _stage_live(qf, td):
    clip = td / "kick_adinross_72s.mp4"
    tiktok = td / "kick_adinross_72s_tiktok.mp4"
    clip.write_bytes(b"")
    tiktok.write_bytes(b"")
    spike = {"seconds_in": 72.6, "messages": 141, "median": 26,
             "intensity": 5.42}
    ok = runner.stage_to_queue(clip, tiktok, "adinross", "kick",
                               spike, queue_file=qf)
    assert ok is True, "stage_to_queue should return True"
    return "live-kick-adinross-72s"


def main():
    passed = 0
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        qf = td / "queue.json"
        hourly_poster.QUEUE_FILE = qf
        hourly_poster.QUEUE_LOCK = qf.with_suffix(".lock")

        # 1. Merge-save preserves a mid-slot staging (the 2026-11-16 bug).
        qf.write_text(json.dumps([_vod_entry("vod-a"),
                                  _vod_entry("vod-b")]))
        snapshot = hourly_poster.load_queue()  # poster loads at slot start
        picked = snapshot[0]
        picked["status"] = "posted"  # post_entry mutates the one entry
        picked["yt_url"] = "https://youtube.com/shorts/TEST"
        live_id = _stage_live(qf, td)  # staged mid-slot, after the load
        hourly_poster.save_entry(picked)  # poster saves at slot end
        after = json.loads(qf.read_text())
        assert [e["id"] for e in after] == [live_id, "vod-a", "vod-b"], after
        assert after[1]["status"] == "posted", after[1]
        assert after[1]["yt_url"] == "https://youtube.com/shorts/TEST"
        assert after[2]["status"] == "pending"
        passed += 1
        print("1. merge-save keeps mid-slot staging: PASS")

        # 2. The old wholesale save drops it (proves the test catches
        #    a regression to save_queue).
        qf.write_text(json.dumps([_vod_entry("vod-a"),
                                  _vod_entry("vod-b")]))
        snapshot = hourly_poster.load_queue()
        picked = snapshot[0]
        picked["status"] = "posted"
        live_id = _stage_live(qf, td)
        hourly_poster.save_queue(snapshot)  # old behavior
        after = json.loads(qf.read_text())
        assert live_id not in [e["id"] for e in after], after
        passed += 1
        print("2. wholesale save drops mid-slot staging (old bug): PASS")

        # 3. save_entry for an entry missing from disk re-appends it.
        qf.write_text(json.dumps([_vod_entry("vod-b")]))
        ghost = _vod_entry("vod-ghost")
        ghost["status"] = "posted"
        hourly_poster.save_entry(ghost)
        after = json.loads(qf.read_text())
        assert [e["id"] for e in after] == ["vod-b", "vod-ghost"], after
        passed += 1
        print("3. save_entry re-appends a missing entry: PASS")

    print(f"{passed}/3 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
