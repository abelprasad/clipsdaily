"""Tests for runner.stage_to_queue (live-clip rescue staging).

No network, no posting, no live state touched: everything runs
against temp files. Works in both layouts:
  - live flat layout (/home/abel/clipsdaily): `import runner`
  - packaged layout (src/clipsdaily): `from clipsdaily import runner`

Run:  python3 test_live_staging.py
"""
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
try:
    from clipsdaily import eligibility_gate as gate_mod
    from clipsdaily import runner
except ImportError:
    import eligibility_gate as gate_mod
    import runner

# Hourly poster hard-requires these keys on every entry it touches.
REQUIRED_KEYS = ["id", "streamer", "platform", "clip30", "tiktok",
                 "title", "caption_ig", "caption_yt", "caption_tiktok",
                 "status", "yt_retries", "tt_retries", "yt_url", "tt_url",
                 "history"]


def main():
    passed = 0

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        qf = td / "queue.json"
        # One pre-existing VOD entry, like the real queue.
        qf.write_text(json.dumps([{"id": "vod-entry-1",
                                   "status": "pending"}]))
        # Dummy clip files (staging stores paths; it never reads them).
        clip = td / "kick_adinross_72s.mp4"
        tiktok = td / "kick_adinross_72s_tiktok.mp4"
        clip.write_bytes(b"")
        tiktok.write_bytes(b"")
        spike = {"seconds_in": 72.6, "messages": 141, "median": 26,
                 "intensity": 5.42}

        # 1. Stage a Kick live clip: front of queue, full shape.
        ok = runner.stage_to_queue(clip, tiktok, "adinross", "kick",
                                   spike, queue_file=qf)
        assert ok is True, "stage_to_queue should return True"
        entries = json.loads(qf.read_text())
        assert len(entries) == 2, entries
        e = entries[0]
        assert e["id"] == "live-kick-adinross-72s", e["id"]
        assert e["platform"] == "kick" and e["streamer"] == "adinross"
        assert e["status"] == "pending"
        assert e["vod_id"] is None and e["vod_date"] is None
        assert e["campaign_eligible"] is False
        assert e["source"] == "live"
        assert e["clip30"] == str(clip) and e["tiktok"] == str(tiktok)
        assert e["title"] == "adinross clip | clipsdaily #shorts"
        assert e["caption_ig"] == "clipsdaily \u2022 adinross"
        assert e["caption_yt"] == e["caption_tiktok"] == e["caption_ig"]
        assert e["spike_seconds"] == 72.6 and e["intensity"] == 5.42
        for k in REQUIRED_KEYS:
            assert k in e, f"missing hourly-poster key: {k}"
        print("1. kick live clip staged at front, full shape: PASS")
        passed += 1

        # 2. Dedup: staging the same clip again changes nothing.
        ok2 = runner.stage_to_queue(clip, tiktok, "adinross", "kick",
                                    spike, queue_file=qf)
        assert ok2 is False, "second stage should return False"
        entries = json.loads(qf.read_text())
        assert len(entries) == 2, "dedup failed: duplicate entry"
        assert sum(1 for x in entries
                   if x["id"] == "live-kick-adinross-72s") == 1
        print("2. dedup on re-stage: PASS")
        passed += 1

        # 3. A Twitch live clip stages the same way (platform-agnostic).
        ok3 = runner.stage_to_queue(
            clip, None, "xqc", "twitch",
            {"seconds_in": 123.0, "intensity": 4.0}, queue_file=qf)
        assert ok3 is True
        entries = json.loads(qf.read_text())
        e3 = entries[0]
        assert e3["id"] == "live-twitch-xqc-123s"
        assert e3["tiktok"] is None  # no 60-90s version: hourly falls back
        print("3. twitch live clip stages, tiktok=None fallback: PASS")
        passed += 1

        # 4. Campaign gate BLOCKS a staged live entry (no vod_id, no
        # campaign_id): it can never become a campaign submission.
        camp = {"id": "test-speed", "vod_id": "2921253522",
                "window_start_s": 10500, "window_end_s": None,
                "required_mentions": ["Expedia"],
                "required_hashtag": "#IShowSpeed"}
        verdict = gate_mod.gate_clip(entries[1], camp)
        assert verdict["ok"] is False, verdict
        assert verdict["checks"]["window"]["ok"] is False
        assert "vod mismatch" in verdict["checks"]["window"]["detail"]
        print("4. eligibility gate BLOCKS staged live entry "
              "(campaign test-speed): PASS")
        passed += 1

    print(f"ALL {passed}/4 live-staging tests PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
