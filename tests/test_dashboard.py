"""Tests for clipsdaily.dashboard (ClipForge web GUI).

Run from the repo checkout on indra (needs fastapi + uvicorn installed):
    CLIPSDAILY_HOME=<scratch> python3 -m unittest tests.test_dashboard -v
or simply:  python3 tests/test_dashboard.py

Covers, with a real HTTP server on 127.0.0.1 and a real runner:
  1. Dashboard loads (200); queue shows all entries with correct
     statuses; health shows health.json values; history shows LIVE
     lines + the IG post.
  2. Settings change via HTTP POST: adding a streamer is picked up by
     the branch runner (logs/runner-state.json) within 90s, no restart.
  3. Safety: no code path writes queue.json (source grep), and POSTs
     to nonexistent queue endpoints return 404 without mutating it.
  4. Pure-function unit tests (config validation, atomic write,
     queue grouping, history parsing, log escaping).

Only stdlib is used here (urllib + subprocess); no httpx/TestClient.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC))

from clipsdaily import dashboard as dash  # noqa: E402

PORT = int(os.environ.get("CLIPFORGE_TEST_PORT", "18787"))
BASE = "http://127.0.0.1:%d" % PORT


def make_scratch_home(root):
    """Scratch runtime home: 2 streamers, 3 queue entries, health,
    one hourly log with 2 LIVE lines, one IG .posted entry."""
    home = Path(root)
    (home / "queue").mkdir(parents=True)
    (home / "logs").mkdir()
    (home / "ig-outbox" / "clip-ig-1").mkdir(parents=True)
    (home / "config.yaml").write_text(
        "streamers:\n"
        "  - platform: twitch\n    channel: fakeone\n"
        "  - platform: kick\n    channel: faketwo\n"
        "max_clips_per_day: 20\n"
        "spike_cooldown_seconds: 300\n"
        "platforms:\n  youtube: true\n  tiktok: false\n  instagram: false\n")
    (home / "queue" / "queue.json").write_text(json.dumps([
        {"id": "q-pending-1", "streamer": "fakeone", "platform": "twitch",
         "status": "pending", "created_at": "2026-11-16T10:00:00",
         "yt_url": None, "tt_url": None, "yt_retries": 0, "tt_retries": 0},
        {"id": "q-posted-1", "streamer": "faketwo", "platform": "kick",
         "status": "posted", "created_at": "2026-11-16T09:00:00",
         "yt_url": "https://youtube.com/shorts/abc123",
         "tt_url": "https://tiktok.com/@x/video/1",
         "yt_retries": 0, "tt_retries": 1},
        {"id": "q-failed-1", "streamer": "fakeone", "platform": "twitch",
         "status": "failed", "created_at": "2026-11-16T08:00:00",
         "yt_url": "FAILED", "tt_url": None, "yt_retries": 3,
         "tt_retries": 0},
    ], indent=2))
    (home / "health.json").write_text(json.dumps({
        "checked_at": "2026-11-16T20:00:00-05:00",
        "youtube": {"status": "healthy",
                    "last_post": "2026-11-16T18:00:00-05:00",
                    "detail": "last Short 18:00"},
        "instagram": {"status": "idle", "last_post": None,
                      "detail": "no pending clips"},
        "tiktok": {"status": "known_broken", "last_failure": None,
                   "detail": "cookie path blocked (known, no alert)"},
        "queue": {"status": "healthy", "entries": 3, "pending": 1,
                  "detail": "3 entries, 1 pending"},
    }, indent=2))
    (home / "logs" / "hourly-20261116.log").write_text(
        "[2026-11-16 18:00:05] q-posted-1: YOUTUBE LIVE "
        "https://youtube.com/shorts/abc123 (posted)\n"
        "[2026-11-16 18:30:10] q-posted-1: TIKTOK LIVE "
        "https://tiktok.com/@x/video/1 (posted)\n"
        "[2026-11-16 18:31:00] some unrelated log line\n")
    (home / "ig-outbox" / "clip-ig-1" / ".posted").write_text(json.dumps({
        "media_fbid": "123456789", "posted_at_utc": "2026-11-16T19:00:00Z"}))
    (home / "ig-outbox" / "clip-ig-1" / "meta.json").write_text(json.dumps({
        "clip_id": "clip-ig-1", "status": "posted"}))
    return home


def http_get(path, timeout=10):
    req = urllib.request.Request(BASE + path)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def http_post_form(path, fields, timeout=10):
    data = urlencode(fields).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def wait_up(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, _ = http_get("/api/state", timeout=2)
            if status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


class DashboardUnitTests(unittest.TestCase):
    def test_validate_config_rejects_bad_channel(self):
        err = dash.validate_config(
            {"streamers": [{"platform": "twitch", "channel": "bad name!"}]})
        self.assertIn("bad channel", err)

    def test_validate_config_rejects_bad_platform(self):
        err = dash.validate_config(
            {"streamers": [{"platform": "youtube", "channel": "xqc"}]})
        self.assertIn("twitch or kick", err)

    def test_validate_config_rejects_bad_cap(self):
        err = dash.validate_config({"streamers": [], "max_clips_per_day": 0})
        self.assertIn("1-100", err)

    def test_validate_config_accepts_good(self):
        self.assertIsNone(dash.validate_config({
            "streamers": [{"platform": "kick", "channel": "xqc"}],
            "max_clips_per_day": 20, "spike_cooldown_seconds": 300,
            "queue_clip_retention_days": 7,
            "platforms": {"youtube": True, "tiktok": False}}))

    def test_save_config_atomic_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            dash.save_config_atomic(home, {
                "streamers": [{"platform": "twitch", "channel": "xqc"}],
                "max_clips_per_day": 20})
            cfg = dash.load_config(home)
            self.assertEqual(cfg["streamers"][0]["channel"], "xqc")
            # tmp file must not linger after the atomic replace
            self.assertFalse((home / "config.yaml.tmp").exists())

    def test_save_config_atomic_refuses_bad(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            with self.assertRaises(ValueError):
                dash.save_config_atomic(
                    home, {"streamers": [{"platform": "twitch",
                                          "channel": "no spaces!"}]})
            self.assertFalse((home / "config.yaml").exists())

    def test_group_queue(self):
        groups = dash.group_queue([
            {"id": "a", "status": "pending"},
            {"id": "b", "status": "posted", "yt_url": "https://x"},
            {"id": "c", "status": "failed"},
            {"id": "d", "status": "partial"},
            {"id": "e"},  # no status -> pending
        ])
        self.assertEqual([e["id"] for e in groups["pending"]], ["a", "e"])
        self.assertEqual([e["id"] for e in groups["posted"]], ["b"])
        self.assertEqual([e["id"] for e in groups["failed"]], ["c"])
        self.assertEqual([e["id"] for e in groups["partial"]], ["d"])

    def test_post_history_parses_logs_and_ig(self):
        with tempfile.TemporaryDirectory() as d:
            home = make_scratch_home(d)
            posts = dash.post_history(home)
            by_platform = {p["platform"]: p for p in posts}
            self.assertIn("youtube", by_platform)
            self.assertIn("tiktok", by_platform)
            self.assertIn("instagram", by_platform)
            self.assertEqual(by_platform["youtube"]["clip_id"], "q-posted-1")
            self.assertEqual(
                by_platform["youtube"]["url"],
                "https://youtube.com/shorts/abc123")
            self.assertIn("123456789",
                          by_platform["instagram"]["detail"])

    def test_tail_logs_escapes_html(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home / "logs").mkdir()
            (home / "logs" / "hourly-20261116.log").write_text(
                "<script>alert(1)</script>\n")
            page = dash.render_dashboard(home)
            self.assertNotIn("<script>alert(1)</script>", page)
            self.assertIn("&lt;script&gt;", page)


class DashboardLiveTests(unittest.TestCase):
    home = None
    dash_proc = None

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="clipforge-dash-test-")
        cls.home = make_scratch_home(cls._tmp.name)
        env = dict(os.environ, CLIPSDAILY_HOME=str(cls.home),
                   PYTHONPATH=str(SRC))
        cls.dash_proc = subprocess.Popen(
            [sys.executable, "-m", "clipsdaily.dashboard",
             "--port", str(PORT)],
            env=env, cwd=str(cls.home),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if not wait_up(timeout=30):
            out = ""
            try:
                out = cls.dash_proc.communicate(timeout=2)[0]
            except Exception:
                cls.dash_proc.kill()
            raise RuntimeError("dashboard did not come up:\n%s" % out)

    @classmethod
    def tearDownClass(cls):
        if cls.dash_proc is not None:
            cls.dash_proc.terminate()
            try:
                cls.dash_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                cls.dash_proc.kill()
            if cls.dash_proc.stdout is not None:
                cls.dash_proc.stdout.close()
        cls._tmp.cleanup()

    def _queue_hash(self):
        return hashlib.sha256(
            (self.home / "queue" / "queue.json").read_bytes()).hexdigest()

    def test_1_dashboard_loads_queue_health_history(self):
        status, body = http_get("/")
        self.assertEqual(status, 200, body[:500])
        self.assertIn("ClipForge", body)
        # Queue: all 3 entries with correct statuses/sections.
        for entry_id in ("q-pending-1", "q-posted-1", "q-failed-1"):
            self.assertIn(entry_id, body)
        self.assertIn("https://youtube.com/shorts/abc123", body)
        self.assertIn("3 entries: 1 pending, 1 posted, 1 failed, 0 partial",
                      body)
        # Health: values straight from health.json.
        self.assertIn("healthy", body)
        self.assertIn("known_broken", body)
        self.assertIn("last Short 18:00", body)
        # History: 2 LIVE lines + the IG post.
        self.assertIn("q-posted-1", body)
        self.assertIn("2026-11-16 18:00:05", body)
        self.assertIn("2026-11-16 18:30:10", body)
        self.assertIn("clip-ig-1", body)
        # Watchlist from config.yaml.
        self.assertIn("fakeone", body)
        self.assertIn("faketwo", body)

    def test_2_add_streamer_picked_up_by_runner_within_90s(self):
        before = self._queue_hash()
        env = dict(os.environ, CLIPSDAILY_HOME=str(self.home),
                   PYTHONPATH=str(SRC))
        runner = subprocess.Popen(
            [sys.executable, "-m", "clipsdaily.runner"],
            env=env, cwd=str(self.home),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            # Runner writes its first runner-state.json at startup.
            state_path = self.home / "logs" / "runner-state.json"
            deadline = time.time() + 60
            while not state_path.exists() and time.time() < deadline:
                time.sleep(1)
            self.assertTrue(state_path.exists(),
                            "runner never wrote runner-state.json")
            # Dashboard POST adds a streamer to config.yaml.
            status, _ = http_post_form("/api/watchlist/add",
                                       {"platform": "twitch",
                                        "channel": "newstreamer"})
            self.assertIn(status, (200, 303), "add streamer failed")
            cfg = dash.load_config(self.home)
            channels = [c for _, c in dash.normalize_streamers(cfg)]
            self.assertIn("newstreamer", channels)
            # Runner reloads config every 60s: poll up to 90s.
            deadline = time.time() + 90
            seen = False
            while time.time() < deadline:
                state = dash.read_runner_state(self.home)
                if "twitch/newstreamer" in (state.get("watchlist") or []):
                    seen = True
                    break
                time.sleep(2)
            self.assertTrue(
                seen, "runner-state.json did not show twitch/newstreamer "
                      "within 90s; last state: %s" % state)
        finally:
            runner.terminate()
            try:
                runner.wait(timeout=10)
            except subprocess.TimeoutExpired:
                runner.kill()
            if runner.stdout is not None:
                runner.stdout.close()
        # Queue untouched by the whole flow.
        self.assertEqual(before, self._queue_hash())

    def test_3_no_queue_mutation_endpoints(self):
        before = self._queue_hash()
        # Source check: dashboard.py must never write queue.json.
        src = (SRC / "clipsdaily" / "dashboard.py").read_text()
        writes = re.findall(r".{0,60}queue.{0,60}", src)
        for line in writes:
            self.assertNotIn("write", line.lower())
            self.assertNotIn("replace", line.lower())
            self.assertNotIn("unlink", line.lower())
        self.assertNotRegex(src, r"open\([^)]*queue[^)]*,\s*[\"']w")
        # Forbidden endpoints do not exist: 404, no mutation.
        for path in ("/api/queue/delete", "/api/queue/retry",
                     "/api/queue/post", "/api/post"):
            status, _ = http_post_form(path, {"id": "q-pending-1"})
            self.assertEqual(status, 404, path)
        self.assertEqual(before, self._queue_hash())

    def test_5_settings_ignores_spike_tuning(self):
        """IP protection (Nov 16, 2026): the GUI must never accept or
        show spike-tuning knobs. A POST carrying spike_cooldown_seconds
        leaves the value untouched (a legit field still works), and the
        settings section never mentions spikes."""
        import yaml
        before = yaml.safe_load((self.home / "config.yaml").read_text())
        self.assertEqual(before.get("spike_cooldown_seconds"), 300)
        status, _ = http_post_form("/api/settings", {
            "max_clips_per_day": "25",
            "spike_cooldown_seconds": "999",
            "queue_clip_retention_days": "7",
        })
        self.assertIn(status, (200, 303))
        after = yaml.safe_load((self.home / "config.yaml").read_text())
        self.assertEqual(after.get("max_clips_per_day"), 25)
        self.assertEqual(after.get("spike_cooldown_seconds"), 300)
        status, html = http_get("/")
        self.assertEqual(status, 200)
        section = html.split('<section id="settings">')[1].split(
            "</section>")[0]
        self.assertNotIn("spike", section.lower())
        self.assertNotIn("spike_cooldown", html)

    def test_4_stop_toggle_is_reversible(self):
        stop = self.home / "STOP"
        if stop.exists():
            stop.unlink()
        status, _ = http_post_form("/api/stop", {"action": "on"})
        self.assertIn(status, (200, 303))
        self.assertTrue(stop.exists())
        status, _ = http_post_form("/api/stop", {"action": "off"})
        self.assertIn(status, (200, 303))
        self.assertFalse(stop.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
