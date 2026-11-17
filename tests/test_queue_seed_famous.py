"""Famous-clips source for queue_seed: GQL top clips, captions, dedupe.

Run: PYTHONPATH=src python3 -m unittest tests.test_queue_seed_famous -v
No network: gql is stubbed. Runtime home is a temp dir.
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="qs-famous-test-")
_OLD_HOME = os.environ.get("CLIPSDAILY_HOME")
os.environ["CLIPSDAILY_HOME"] = _TMP

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from clipsdaily import queue_seed as qs


def tearDownModule():
    if _OLD_HOME is None:
        os.environ.pop("CLIPSDAILY_HOME", None)
    else:
        os.environ["CLIPSDAILY_HOME"] = _OLD_HOME


def _fake_gql_payload(clips):
    return {"data": {"user": {"clips": {"edges": [
        {"node": {"slug": c["slug"], "title": c["title"],
                  "viewCount": c["views"], "durationSeconds": c["duration"],
                  "createdAt": c["created"] + "T00:00:00Z"}}
        for c in clips]}}}}


class TestFamousTexts(unittest.TestCase):
    def test_clean_clip_title_strips_hashtags(self):
        self.assertEqual(
            qs.clean_clip_title("Big Smoke in real life #KaiCenat #GTA"),
            "Big Smoke in real life")

    def test_clean_clip_title_junk(self):
        self.assertEqual(qs.clean_clip_title("///"), "")
        self.assertEqual(qs.clean_clip_title("gg"), "")
        self.assertEqual(qs.clean_clip_title(""), "")

    def test_build_famous_texts_no_throwback_no_caption_hashtags(self):
        title, yt, tt, ig = qs.build_famous_texts(
            "kaicenat", "Kevin Hart gets drenched")
        self.assertNotIn("THROWBACK", title)
        self.assertEqual(yt, "kaicenat: Kevin Hart gets drenched")
        self.assertNotIn("#", yt)
        self.assertNotIn("#", tt)
        self.assertNotIn("#", ig)
        self.assertIn("kaicenat", title)

    def test_famous_clip_id_sanitizes(self):
        self.assertEqual(
            qs.famous_clip_id("kaicenat",
                              "SillyTubularOilYee-GTZ5PXa-rOA8pYoA"),
            "famous-kaicenat-SillyTubularOilYee-GTZ5PXa-rOA8pYoA")

    def test_is_campaign_clip(self):
        speed_nov6 = {"slug": "x", "title": "Hudson flies to Japan",
                      "views": 1, "duration": 30, "created": "2026-11-06"}
        self.assertTrue(qs.is_campaign_clip("ishowspeed", speed_nov6))
        speed_other = dict(speed_nov6, created="2026-11-05")
        self.assertFalse(qs.is_campaign_clip("ishowspeed", speed_other))
        expedia = dict(speed_other, title="Expedia sent us to Tokyo")
        self.assertTrue(qs.is_campaign_clip("ishowspeed", expedia))
        self.assertFalse(qs.is_campaign_clip("kaicenat", speed_nov6))


class TestNextFamousClip(unittest.TestCase):
    def setUp(self):
        qs._famous_cache.clear()
        qs._famous_cache_at = 0
        qs._famous_next_channel = 0
        qs.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
        self._orig_gql = qs.gql

    def tearDown(self):
        qs.gql = self._orig_gql
        qs._famous_cache.clear()
        qs._famous_cache_at = 0
        qs._famous_next_channel = 0

    def _write_queue(self, entries):
        qs.QUEUE_FILE.write_text(json.dumps(entries))

    def _write_state(self, state):
        qs.STATE_FILE.write_text(json.dumps(state))

    def test_fetch_top_clips_parses_views_order(self):
        clips = [
            {"slug": "a", "title": "A", "views": 2718390,
             "duration": 17, "created": "2024-06-11"},
            {"slug": "b", "title": "B", "views": 1469211,
             "duration": 30, "created": "2024-06-23"},
        ]
        qs.gql = lambda q: _fake_gql_payload(clips)
        got = qs.fetch_top_clips("kaicenat")
        self.assertEqual([c["views"] for c in got], [2718390, 1469211])
        self.assertEqual(got[0]["slug"], "a")

    def test_picks_top_unseen_skips_queued_and_short(self):
        clips = [
            {"slug": "top-one", "title": "Top clip ever", "views": 5000000,
             "duration": 30, "created": "2024-06-11"},
            {"slug": "short-one", "title": "Too short", "views": 4000000,
             "duration": 5, "created": "2024-06-11"},
            {"slug": "second-one", "title": "Second best", "views": 3000000,
             "duration": 45, "created": "2024-06-11"},
        ]
        qs.gql = lambda q: _fake_gql_payload(clips)
        self._write_queue([{"id": "famous-kaicenat-top-one",
                            "status": "pending"}])
        self._write_state({"vods": [], "done_spikes": [], "done_famous": []})
        job = qs.next_famous_clip()
        self.assertIsNotNone(job)
        ch, clip = job
        self.assertEqual(ch, "kaicenat")
        self.assertEqual(clip["slug"], "second-one")

    def test_none_when_all_seen(self):
        clips = [
            {"slug": "only-one", "title": "Only", "views": 100,
             "duration": 30, "created": "2024-06-11"},
        ]
        qs.gql = lambda q: _fake_gql_payload(clips)
        self._write_queue([])
        done = ["famous-%s-only-one" % ch for ch in qs.FAMOUS_CHANNELS]
        self._write_state({"vods": [], "done_spikes": [],
                           "done_famous": done})
        self.assertIsNone(qs.next_famous_clip())

    def test_round_robin_across_channels(self):
        clips = [
            {"slug": "clip-a", "title": "Clip A", "views": 900,
             "duration": 30, "created": "2024-06-11"},
        ]
        qs.gql = lambda q: _fake_gql_payload(clips)
        self._write_queue([])
        self._write_state({"vods": [], "done_spikes": [], "done_famous": []})
        ch1, _ = qs.next_famous_clip()
        self.assertEqual(ch1, "kaicenat")
        # claim kaicenat's clip; the next call must move on to the
        # next channel instead of re-offering kaicenat.
        state = json.loads(qs.STATE_FILE.read_text())
        state.setdefault("done_famous", []).append("famous-kaicenat-clip-a")
        qs.STATE_FILE.write_text(json.dumps(state))
        ch2, _ = qs.next_famous_clip()
        self.assertEqual(ch2, "ishowspeed")

    def test_insert_at_front_of_pending(self):
        entries = [
            {"id": "old-posted", "status": "posted"},
            {"id": "tb-1", "status": "pending"},
            {"id": "tb-2", "status": "pending"},
        ]
        out = qs.insert_at_front_of_pending(
            entries, {"id": "famous-x", "status": "pending"})
        self.assertEqual([e["id"] for e in out],
                         ["old-posted", "famous-x", "tb-1", "tb-2"])

    def test_famous_pending_filters(self):
        entries = [
            {"id": "a", "status": "pending", "source": "famous"},
            {"id": "b", "status": "pending"},
            {"id": "c", "status": "posted", "source": "famous"},
        ]
        self.assertEqual([e["id"] for e in qs.famous_pending(entries)],
                         ["a"])


if __name__ == "__main__":
    unittest.main()
