"""Integration tests for the TikTok API wiring in poster.py /
hourly_poster.py — no real posts, all TikTok calls mocked.

Run on indra as abel:  python3 -m unittest test_poster_tiktok_api -v
Covers: API on/off routing, allow_short fallback, PENDING/DRAFT
markers (no retry burned, no re-upload), reconcile to live / still
pending / failed, cap-False handling, config defaults.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, "/home/abel/clipsdaily")

import hourly_poster
import poster
import tiktok_api


def _entry(**over):
    e = {"id": "test-entry-1", "streamer": "ishowspeed",
         "platform": "twitch", "title": "TEST",
         "clip30": "/tmp/does-not-exist-30.mp4",
         "tiktok": "/tmp/does-not-exist-75.mp4",
         "caption_yt": "cap yt", "caption_tiktok": "cap tt",
         "caption_ig": "cap ig", "yt_url": None, "tt_url": None,
         "yt_retries": 0, "tt_retries": 0, "status": "pending",
         "history": []}
    e.update(over)
    return e


class WiringTest(unittest.TestCase):
    def setUp(self):
        # Keep test log lines out of the live hourly logs.
        self._logs = hourly_poster.LOGS
        hourly_poster.LOGS = Path(tempfile.mkdtemp(prefix="tt-wiring-"))

    def tearDown(self):
        hourly_poster.LOGS = self._logs

    def test_config_defaults_api_off(self):
        hourly_poster.refresh_config()
        self.assertFalse(hourly_poster.CONFIG["tiktok_api"])
        self.assertEqual(hourly_poster.CONFIG["tiktok_api_mode"], "direct")

    def test_pending_return_no_retry(self):
        e = _entry()
        with mock.patch.object(poster, "post_tiktok",
                               return_value="PENDING:pub-1") as pt:
            hourly_poster.post_entry(e, "2026-11-16T10:30")
        self.assertEqual(e["tt_url"], "PENDING:pub-1")
        self.assertEqual(e["tt_retries"], 0)
        self.assertEqual(e["status"], "pending")
        pt.assert_called_once()
        self.assertFalse(pt.call_args[1].get("allow_short"))

    def test_cap_false_no_retry(self):
        e = _entry()
        with mock.patch.object(poster, "post_tiktok", return_value=False):
            hourly_poster.post_entry(e, "2026-11-16T10:30")
        self.assertFalse(e["tt_url"])
        self.assertEqual(e["tt_retries"], 0)
        self.assertEqual(e["status"], "pending")

    def test_upload_pending_exception_no_retry_no_reupload(self):
        e = _entry()
        with mock.patch.object(
                poster, "post_tiktok",
                side_effect=tiktok_api.TikTokUploadPending("pub-9")):
            hourly_poster.post_entry(e, "2026-11-16T10:30")
        self.assertEqual(e["tt_url"], "PENDING:pub-9")
        self.assertEqual(e["tt_retries"], 0)

    def test_reconcile_pending_to_live(self):
        e = _entry(tt_url="PENDING:pub-1")
        with mock.patch.object(
                tiktok_api, "reconcile_pending",
                return_value=[{"publish_id": "pub-1", "status": "published",
                               "url": "https://www.tiktok.com/"
                                      "@clips.daily548/video/123"}]):
            with mock.patch.object(poster, "post_tiktok") as pt:
                hourly_poster.post_entry(e, "2026-11-16T11:00")
        pt.assert_not_called()  # no re-upload
        self.assertEqual(
            e["tt_url"],
            "https://www.tiktok.com/@clips.daily548/video/123")
        self.assertEqual(e["tt_retries"], 0)

    def test_reconcile_still_pending_waits(self):
        e = _entry(tt_url="DRAFT:d-1")
        with mock.patch.object(
                tiktok_api, "reconcile_pending",
                return_value=[{"publish_id": "d-1",
                               "status": "send_to_user_inbox"}]):
            with mock.patch.object(poster, "post_tiktok") as pt:
                hourly_poster.post_entry(e, "2026-11-16T11:00")
        pt.assert_not_called()
        self.assertEqual(e["tt_url"], "DRAFT:d-1")
        self.assertEqual(e["tt_retries"], 0)

    def test_reconcile_failed_burns_one_retry(self):
        e = _entry(tt_url="PENDING:pub-2")
        with mock.patch.object(
                tiktok_api, "reconcile_pending",
                return_value=[{"publish_id": "pub-2", "status": "failed",
                               "fail_reason": "spam_risk"}]):
            with mock.patch.object(poster, "post_tiktok") as pt:
                hourly_poster.post_entry(e, "2026-11-16T11:00")
        pt.assert_not_called()
        self.assertIsNone(e["tt_url"])
        self.assertEqual(e["tt_retries"], 1)

    def test_fallback_uses_allow_short(self):
        e = _entry(tiktok=None)  # no 60-90s variant -> 30s fallback
        with mock.patch.object(
                poster, "post_tiktok",
                return_value="https://www.tiktok.com/@x/video/1") as pt:
            hourly_poster.post_entry(e, "2026-11-16T10:30")
        self.assertTrue(pt.call_args[1].get("allow_short"))
        self.assertEqual(e["status"], "partial")  # yt not done yet

    def test_post_tiktok_routes_to_api_when_flag_on(self):
        cfg = {"platforms": {"tiktok": True}, "tiktok_api": True,
               "tiktok_api_mode": "direct"}
        with mock.patch.object(poster, "_duration_seconds",
                               return_value=65.0):
            with mock.patch.object(
                    poster, "_post_tiktok_api",
                    return_value="https://www.tiktok.com/@x/video/2") as api:
                with mock.patch.object(poster, "_tiktok_cookies") as ck:
                    url = poster.post_tiktok(Path("/tmp/fake75.mp4"),
                                             "ishowspeed", cfg, caption="cap")
        self.assertEqual(url, "https://www.tiktok.com/@x/video/2")
        api.assert_called_once()
        ck.assert_not_called()  # cookie path never touched

    def test_post_tiktok_routes_to_cookies_when_flag_off(self):
        cfg = {"platforms": {"tiktok": True}}  # no tiktok_api key
        fake = mock.Mock()
        fake.post_file_subprocess.return_value = (
            True, "https://www.tiktok.com/@x/video/3", "ok")
        with mock.patch.object(poster, "_duration_seconds",
                               return_value=65.0):
            with mock.patch.object(poster, "_post_tiktok_api") as api:
                with mock.patch.object(poster, "_tiktok_cookies",
                                       return_value="/x/cookies.txt"):
                    with mock.patch.dict(sys.modules,
                                        {"post_tiktok_fixed": fake}):
                        url = poster.post_tiktok(Path("/tmp/fake75.mp4"),
                                                 "ishowspeed", cfg,
                                                 caption="cap")
        self.assertEqual(url, "https://www.tiktok.com/@x/video/3")
        api.assert_not_called()
        fake.post_file_subprocess.assert_called_once()

    def test_post_tiktok_refuses_short_without_allow_short(self):
        cfg = {"platforms": {"tiktok": True}, "tiktok_api": True}
        with mock.patch.object(poster, "_duration_seconds",
                               return_value=30.0):
            with mock.patch.object(poster, "_post_tiktok_api") as api:
                self.assertFalse(poster.post_tiktok(
                    Path("/tmp/fake30.mp4"), "ishowspeed", cfg,
                    caption="cap"))
        api.assert_not_called()

    def test_post_tiktok_allows_short_with_flag(self):
        cfg = {"platforms": {"tiktok": True}, "tiktok_api": True}
        with mock.patch.object(poster, "_duration_seconds",
                               return_value=30.0):
            with mock.patch.object(
                    poster, "_post_tiktok_api",
                    return_value="https://www.tiktok.com/@x/video/4") as api:
                url = poster.post_tiktok(Path("/tmp/fake30.mp4"),
                                         "ishowspeed", cfg, caption="cap",
                                         allow_short=True)
        self.assertEqual(url, "https://www.tiktok.com/@x/video/4")
        api.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
