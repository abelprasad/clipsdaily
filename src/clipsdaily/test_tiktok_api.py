"""Mocked unit tests for tiktok_api.py — no real TikTok calls.

Run:  python3 -m unittest test_tiktok_api -v
Everything HTTP is mocked (requests.post / requests.put); the only
real I/O is temp files under tempfile.gettempdir().

Covers: OAuth exchange + refresh rotation, token expiry, creator
info + privacy validation, Direct Post init/upload/poll success,
FAILED status, unaudited-client errors, draft flow, caps (15/day
direct, 5 pending drafts), PULL_FROM_URL, chunk math, 401 retry.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tiktok_api as tt

FAKE_CLIENT = {
    "client_key": "awtestkey123",
    "client_secret": "testsecret",
    "redirect_uri": "http://localhost:8080/",
}
FAKE_TOKEN = {
    "access_token": "act-1",
    "refresh_token": "ref-1",
    "open_id": "open-1",
    "scope": "user.info.basic,video.upload,video.publish",
    "token_type": "Bearer",
    "expires_at": int(__import__("time").time()) + 7200,
    "refresh_expires_at": int(__import__("time").time()) + 180 * 86400,
}
CREATOR_INFO = {
    "creator_username": "clips.daily548",
    "creator_nickname": "Clips Daily",
    "creator_avatar_url": "https://example.com/a.jpg",
    "privacy_level_options": ["PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS",
                              "SELF_ONLY"],
    "comment_disabled": False,
    "duet_disabled": False,
    "stitch_disabled": False,
    "max_video_post_duration_sec": 600,
}
CREATOR_INFO_PRIVATE = dict(
    CREATOR_INFO,
    privacy_level_options=["SELF_ONLY"],
    comment_disabled=True, duet_disabled=True, stitch_disabled=True)


def _resp(status=200, body=None):
    r = mock.Mock()
    r.status_code = status
    r.json.return_value = body if body is not None else {
        "data": {}, "error": {"code": "ok", "message": "", "log_id": "x"}}
    return r


def _ok(body):
    return _resp(200, {"data": body, "error": {"code": "ok", "message": "",
                                               "log_id": "x"}})


def _err(code, message, status=403):
    return _resp(status, {"data": {}, "error": {"code": code,
                                                "message": message,
                                                "log_id": "x"}})


class TikTokApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tt-test-"))
        # Point the module's .auth dir at the temp dir.
        self._orig_auth = tt.AUTH_DIR
        self._orig_client = tt.CLIENT_FILE
        self._orig_token = tt.TOKEN_FILE
        self._orig_state = tt.AUTH_STATE_FILE
        self._orig_usage = tt.USAGE_FILE
        tt.AUTH_DIR = self.tmp
        tt.CLIENT_FILE = self.tmp / "tiktok_api_client.json"
        tt.TOKEN_FILE = self.tmp / "tiktok_api_token.json"
        tt.AUTH_STATE_FILE = self.tmp / "tiktok_api_auth_state.json"
        tt.USAGE_FILE = self.tmp / "tiktok_api_usage.json"
        tt.CLIENT_FILE.write_text(json.dumps(FAKE_CLIENT))
        tt.TOKEN_FILE.write_text(json.dumps(FAKE_TOKEN))
        # A 25 MB fake video (25,000,000 bytes -> 3 chunks at 10 MB).
        self.clip = self.tmp / "clip.mp4"
        with open(self.clip, "wb") as f:
            f.write(b"\x00" * 25_000_000)
        # ffprobe is not available in the test env (and would fail on a
        # zero-filled file anyway): pretend the clip is 75s.
        self._probe = mock.patch.object(
            tt, "_probe_duration_seconds", return_value=75.0)
        self._probe.start()

    def tearDown(self):
        self._probe.stop()
        tt.AUTH_DIR = self._orig_auth
        tt.CLIENT_FILE = self._orig_client
        tt.TOKEN_FILE = self._orig_token
        tt.AUTH_STATE_FILE = self._orig_state
        tt.USAGE_FILE = self._orig_usage
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- OAuth
    def test_exchange_code_saves_token(self):
        body = {"access_token": "act-2", "refresh_token": "ref-2",
                "open_id": "open-1",
                "scope": "user.info.basic,video.upload,video.publish",
                "token_type": "Bearer", "expires_in": 7200,
                "refresh_expires_in": 180 * 86400}
        with mock.patch.object(tt.requests, "post",
                               return_value=_resp(200, body)) as post:
            token = tt.exchange_code("AUTHCODE123")
        self.assertEqual(token["access_token"], "act-2")
        self.assertEqual(token["refresh_token"], "ref-2")
        self.assertGreater(token["expires_at"], token["refresh_expires_at"]
                           - 181 * 86400)
        saved = json.loads(tt.TOKEN_FILE.read_text())
        self.assertEqual(saved["access_token"], "act-2")
        self.assertEqual(post.call_args[0][0], tt.TOKEN_URL)
        sent = post.call_args[1]["data"]
        self.assertEqual(sent["grant_type"], "authorization_code")
        self.assertEqual(sent["code"], "AUTHCODE123")

    def test_exchange_code_from_callback_url_verifies_state(self):
        tt.AUTH_STATE_FILE.write_text(json.dumps(
            {"code_verifier": "v123", "state": "s123",
             "redirect_uri": "http://localhost:8080/"}))
        body = {"access_token": "act-2", "refresh_token": "ref-2",
                "open_id": "open-1", "scope": "x", "token_type": "Bearer",
                "expires_in": 7200, "refresh_expires_in": 15552000}
        with mock.patch.object(tt.requests, "post",
                               return_value=_resp(200, body)) as post:
            tt.exchange_code(
                "http://localhost:8080/?code=CODE9&state=s123")
        self.assertEqual(post.call_args[1]["data"]["code_verifier"], "v123")
        with self.assertRaises(tt.TikTokAPIError):
            tt.exchange_code(
                "http://localhost:8080/?code=CODE9&state=WRONG")

    def test_refresh_rotates_refresh_token(self):
        body = {"access_token": "act-new", "refresh_token": "ref-new",
                "open_id": "open-1", "scope": "x", "token_type": "Bearer",
                "expires_in": 7200, "refresh_expires_in": 15552000}
        with mock.patch.object(tt.requests, "post",
                               return_value=_resp(200, body)):
            new = tt.refresh_access_token()
        self.assertEqual(new["refresh_token"], "ref-new")
        saved = json.loads(tt.TOKEN_FILE.read_text())
        self.assertEqual(saved["refresh_token"], "ref-new")
        self.assertNotEqual(saved["refresh_token"], "ref-1")

    def test_get_access_token_refreshes_when_expiring(self):
        dying = dict(FAKE_TOKEN, expires_at=int(__import__("time").time())
                     + 60)
        tt.TOKEN_FILE.write_text(json.dumps(dying))
        body = {"access_token": "act-fresh", "refresh_token": "ref-fresh",
                "open_id": "open-1", "scope": "x", "token_type": "Bearer",
                "expires_in": 7200, "refresh_expires_in": 15552000}
        with mock.patch.object(tt.requests, "post",
                               return_value=_resp(200, body)):
            tok = tt.get_access_token()
        self.assertEqual(tok, "act-fresh")

    def test_get_access_token_no_refresh_when_fresh(self):
        with mock.patch.object(tt.requests, "post") as post:
            self.assertEqual(tt.get_access_token(), "act-1")
        post.assert_not_called()

    # ---------------------------------------------------------- creator info
    def test_privacy_must_be_in_creator_options(self):
        with mock.patch.object(tt.requests, "post",
                               return_value=_ok(CREATOR_INFO)):
            with self.assertRaises(tt.TikTokAPIError) as ctx:
                tt.post_video_direct(str(self.clip), "cap",
                                     privacy_level="FRIENDS_ONLY")
        self.assertIn("privacy_level_option_mismatch", str(ctx.exception))

    def test_creator_disabled_flags_force_disable(self):
        seen = {}

        def fake_post(url, headers=None, json=None, **kw):
            if "creator_info" in url:
                return _ok(CREATOR_INFO_PRIVATE)
            if "video/init" in url:
                seen["post_info"] = json["post_info"]
                return _ok({"publish_id": "pub-1",
                            "upload_url": "https://up.example/x"})
            if "status" in url:
                return _ok({"status": "PUBLISH_COMPLETE",
                            "publicaly_available_post_id": [123]})
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            with mock.patch.object(tt.requests, "put",
                                   return_value=_resp(200, {})):
                with mock.patch.object(tt, "_poll_status",
                                       return_value={"status":
                                                     "PUBLISH_COMPLETE",
                                                     "publicaly_available_post_id":
                                                     [123]}):
                    res = tt.post_video_direct(
                        str(self.clip), "cap", privacy_level="SELF_ONLY",
                        allow_comment=True, allow_duet=True,
                        allow_stitch=True)
        # Creator disabled everything, so all three must be disabled
        # even though allow_* were True.
        self.assertTrue(seen["post_info"]["disable_comment"])
        self.assertTrue(seen["post_info"]["disable_duet"])
        self.assertTrue(seen["post_info"]["disable_stitch"])
        self.assertEqual(res["url"],
                         "https://www.tiktok.com/@clips.daily548/video/123")

    # --------------------------------------------------------- direct post
    def _run_direct(self, post_side_effect, status_payloads):
        """Drive post_video_direct with a canned post() side effect."""
        calls = {"puts": []}

        def fake_put(url, data=None, headers=None, **kw):
            calls["puts"].append((url, headers))
            return _resp(200, {})

        with mock.patch.object(tt.requests, "post",
                               side_effect=post_side_effect):
            with mock.patch.object(tt.requests, "put", side_effect=fake_put):
                with mock.patch.object(
                        tt, "_poll_status",
                        side_effect=[{"status": s,
                                      "publicaly_available_post_id": [777]}
                                     if s == "PUBLISH_COMPLETE" else
                                     {"status": s}
                                     for s in status_payloads]):
                    res = tt.post_video_direct(str(self.clip), "Test caption")
        return res, calls

    def test_direct_post_happy_path(self):
        inits = []

        def fake_post(url, headers=None, json=None, **kw):
            if "creator_info" in url:
                return _ok(CREATOR_INFO)
            if "video/init" in url:
                inits.append(json)
                return _ok({"publish_id": "v_pub_file~v2-1.999",
                            "upload_url": "https://open-upload.x/up"})
            raise AssertionError(url)

        res, calls = self._run_direct(fake_post, ["PUBLISH_COMPLETE"])
        self.assertEqual(
            res["url"], "https://www.tiktok.com/@clips.daily548/video/777")
        self.assertEqual(res["publish_id"], "v_pub_file~v2-1.999")
        # Init body: consent flags, brand toggles, is_aigc, privacy.
        info = inits[0]["post_info"]
        self.assertEqual(info["title"], "Test caption")
        self.assertEqual(info["privacy_level"], "PUBLIC_TO_EVERYONE")
        self.assertTrue(info["content_preview_confirmed"])
        self.assertTrue(info["express_consent_given"])
        self.assertFalse(info["brand_content_toggle"])
        self.assertFalse(info["brand_organic_toggle"])
        self.assertFalse(info["is_aigc"])
        # Chunk math: 25 MB at 10 MB -> 3 chunks, correct ranges.
        src = inits[0]["source_info"]
        self.assertEqual(src["source"], "FILE_UPLOAD")
        self.assertEqual(src["video_size"], 25_000_000)
        self.assertEqual(src["chunk_size"], 10_000_000)
        self.assertEqual(src["total_chunk_count"], 3)
        ranges = [h["Content-Range"] for _, h in calls["puts"]]
        self.assertEqual(ranges, ["bytes 0-9999999/25000000",
                                  "bytes 10000000-19999999/25000000",
                                  "bytes 20000000-24999999/25000000"])
        self.assertEqual(calls["puts"][0][1]["Content-Type"], "video/mp4")
        # Usage recorded.
        usage = json.loads(tt.USAGE_FILE.read_text())
        self.assertEqual(len(usage["direct_posts"]), 1)

    def test_direct_post_pull_from_url_skips_upload(self):
        def fake_post(url, headers=None, json=None, **kw):
            if "creator_info" in url:
                return _ok(CREATOR_INFO)
            if "video/init" in url:
                self.assertEqual(json["source_info"]["source"],
                                 "PULL_FROM_URL")
                return _ok({"publish_id": "v_pub_url~v2.1"})
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            with mock.patch.object(tt.requests, "put") as put:
                with mock.patch.object(
                        tt, "_poll_status",
                        return_value={"status": "PUBLISH_COMPLETE",
                                      "publicaly_available_post_id": [5]}):
                    res = tt.post_video_direct(
                        str(self.clip), "cap",
                        video_url="https://example.com/v.mp4")
        put.assert_not_called()
        self.assertEqual(res["publish_id"], "v_pub_url~v2.1")

    def test_direct_post_failed_status(self):
        def fake_post(url, headers=None, json=None, **kw):
            if "creator_info" in url:
                return _ok(CREATOR_INFO)
            if "video/init" in url:
                return _ok({"publish_id": "pub-f",
                            "upload_url": "https://up.example/x"})
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            with mock.patch.object(tt.requests, "put",
                                   return_value=_resp(200, {})):
                with mock.patch.object(
                        tt, "_poll_status",
                        return_value={"status": "FAILED",
                                      "fail_reason": "duration_check_failed"}):
                    with self.assertRaises(tt.TikTokAPIError) as ctx:
                        tt.post_video_direct(str(self.clip), "cap")
        self.assertIn("duration_check_failed", str(ctx.exception))

    def test_direct_post_pending_raises_not_retry(self):
        def fake_post(url, headers=None, json=None, **kw):
            if "creator_info" in url:
                return _ok(CREATOR_INFO)
            if "video/init" in url:
                return _ok({"publish_id": "pub-p",
                            "upload_url": "https://up.example/x"})
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            with mock.patch.object(tt.requests, "put",
                                   return_value=_resp(200, {})):
                with mock.patch.object(
                        tt, "_poll_status",
                        side_effect=tt.TikTokUploadPending("pub-p")):
                    with self.assertRaises(tt.TikTokUploadPending) as ctx:
                        tt.post_video_direct(str(self.clip), "cap")
        self.assertEqual(ctx.exception.publish_id, "pub-p")
        # Still counted toward the cap (bytes are on TikTok).
        usage = json.loads(tt.USAGE_FILE.read_text())
        self.assertEqual(len(usage["direct_posts"]), 1)

    def test_unaudited_client_error_is_plain_language(self):
        def fake_post(url, headers=None, json=None, **kw):
            if "creator_info" in url:
                return _ok(CREATOR_INFO_PRIVATE)
            if "video/init" in url:
                return _err(
                    "unaudited_client_can_only_post_to_private_accounts",
                    "Unaudited clients can only post to a private account.",
                    403)
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            with self.assertRaises(tt.TikTokAPIError) as ctx:
                tt.post_video_direct(str(self.clip), "cap",
                                     privacy_level="PUBLIC_TO_EVERYONE")
        # Privacy validation fires first (PUBLIC not in private options).
        self.assertIn("privacy_level_option_mismatch", str(ctx.exception))
        # And the unaudited hint text exists on the error class path:
        err = tt.TikTokAPIError(
            "unaudited_client_can_only_post_to_private_accounts", "x")
        self.assertIn("SELF_ONLY", str(err))
        self.assertIn("audit", str(err))

    def test_401_on_init_refreshes_once_and_retries(self):
        calls = {"n": 0}

        def fake_post(url, headers=None, json=None, data=None, **kw):
            if "oauth/token" in url:
                return _resp(200, {"access_token": "act-2",
                                   "refresh_token": "ref-2",
                                   "open_id": "open-1", "scope": "x",
                                   "token_type": "Bearer",
                                   "expires_in": 7200,
                                   "refresh_expires_in": 15552000})
            if "creator_info" in url:
                return _ok(CREATOR_INFO)
            if "video/init" in url:
                calls["n"] += 1
                if calls["n"] == 1:
                    return _err("access_token_invalid",
                                "The access_token is invalid.", 401)
                return _ok({"publish_id": "pub-r",
                            "upload_url": "https://up.example/x"})
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            with mock.patch.object(tt.requests, "put",
                                   return_value=_resp(200, {})):
                with mock.patch.object(
                        tt, "_poll_status",
                        return_value={"status": "PUBLISH_COMPLETE",
                                      "publicaly_available_post_id": [9]}):
                    res = tt.post_video_direct(str(self.clip), "cap")
        self.assertEqual(calls["n"], 2)
        self.assertIn("/video/9", res["url"])

    def test_chunk_plan_math(self):
        self.assertEqual(tt._chunk_plan(25_000_000), (10_000_000, 3))
        self.assertEqual(tt._chunk_plan(10_000_000), (10_000_000, 1))
        self.assertEqual(tt._chunk_plan(3_000_000), (3_000_000, 1))
        self.assertEqual(tt._chunk_plan(20_000_001), (10_000_000, 3))
        with self.assertRaises(tt.TikTokAPIError):
            tt._chunk_plan(100, chunk_size=1_000_000)

    def test_validate_rejects_bad_files(self):
        with self.assertRaises(tt.TikTokAPIError):
            tt._validate_video(self.tmp / "nope.mp4")
        bad = self.tmp / "clip.txt"
        bad.write_text("not a video")
        with self.assertRaises(tt.TikTokAPIError):
            tt._validate_video(bad)
        empty = self.tmp / "empty.mp4"
        empty.write_bytes(b"")
        with self.assertRaises(tt.TikTokAPIError):
            tt._validate_video(empty)

    # ------------------------------------------------------------------ caps
    def _seed_direct_posts(self, n, hours_ago=1):
        now = datetime.now(timezone.utc)
        usage = {"direct_posts": [
            {"at": (now - timedelta(hours=hours_ago)).isoformat(),
             "publish_id": f"p{i}"} for i in range(n)],
            "drafts": []}
        tt.USAGE_FILE.write_text(json.dumps(usage))

    def test_direct_cap_blocks_before_any_http(self):
        self._seed_direct_posts(15)
        with mock.patch.object(tt.requests, "post") as post:
            with self.assertRaises(tt.TikTokCapReached):
                tt.post_video_direct(str(self.clip), "cap")
        post.assert_not_called()

    def test_direct_cap_rolls_off_after_24h(self):
        self._seed_direct_posts(15, hours_ago=25)
        self.assertEqual(len(tt.direct_posts_last_24h()), 0)
        # 14 recent + this one = fine.
        self._seed_direct_posts(14)
        with mock.patch.object(tt.requests, "post") as post:
            with mock.patch.object(tt, "query_creator_info",
                                   return_value=CREATOR_INFO):
                with mock.patch.object(
                        tt, "_init_with_token_refresh",
                        return_value={"publish_id": "pub-ok",
                                      "upload_url": "https://up.example/x"}):
                    with mock.patch.object(tt.requests, "put",
                                           return_value=_resp(200, {})):
                        with mock.patch.object(
                                tt, "_poll_status",
                                return_value={"status": "PUBLISH_COMPLETE",
                                              "publicaly_available_post_id":
                                              [1]}):
                            res = tt.post_video_direct(str(self.clip), "cap")
        self.assertIn("/video/1", res["url"])

    def test_draft_cap_blocks_at_five_pending(self):
        now = datetime.now(timezone.utc).isoformat()
        usage = {"direct_posts": [],
                 "drafts": [{"publish_id": f"d{i}", "at": now,
                             "status": "pending"} for i in range(5)]}
        tt.USAGE_FILE.write_text(json.dumps(usage))

        def fake_post(url, headers=None, json=None, **kw):
            if "status" in url:
                # Refresh poll: drafts are still in the inbox.
                return _ok({"status": "SEND_TO_USER_INBOX"})
            raise AssertionError(
                f"no upload should start when the cap is hit: {url}")

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            with self.assertRaises(tt.TikTokCapReached):
                tt.post_video_draft(str(self.clip))

    def test_draft_flow_happy_path(self):
        def fake_post(url, headers=None, json=None, **kw):
            if "video/init" in url:
                # Draft init must NOT carry post_info.
                self.assertNotIn("post_info", json)
                return _ok({"publish_id": "d_pub",
                            "upload_url": "https://up.example/x"})
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            with mock.patch.object(tt.requests, "put",
                                   return_value=_resp(200, {})):
                with mock.patch.object(
                        tt, "_poll_status",
                        return_value={"status": "SEND_TO_USER_INBOX"}):
                    res = tt.post_video_draft(str(self.clip))
        self.assertEqual(res, {"publish_id": "d_pub", "status": "draft"})
        usage = json.loads(tt.USAGE_FILE.read_text())
        self.assertEqual(usage["drafts"][0]["status"], "pending")

    def test_pending_drafts_refresh_clears_published(self):
        now = datetime.now(timezone.utc).isoformat()
        usage = {"direct_posts": [],
                 "drafts": [{"publish_id": "d1", "at": now,
                             "status": "pending"},
                            {"publish_id": "d2", "at": now,
                             "status": "pending"}]}
        tt.USAGE_FILE.write_text(json.dumps(usage))

        def fake_post(url, headers=None, json=None, **kw):
            if "status" in url:
                pid = json["publish_id"]
                if pid == "d1":
                    return _ok({"status": "PUBLISH_COMPLETE",
                                "publicaly_available_post_id": [42]})
                return _ok({"status": "SEND_TO_USER_INBOX"})
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            pending = tt.pending_drafts(refresh=True)
        self.assertEqual([d["publish_id"] for d in pending], ["d2"])
        usage = json.loads(tt.USAGE_FILE.read_text())
        self.assertEqual(usage["drafts"][0]["status"], "published")

    # ------------------------------------------------------------- reconcile
    def test_reconcile_pending_to_url(self):
        now = datetime.now(timezone.utc).isoformat()
        usage = {"direct_posts": [],
                 "drafts": [{"publish_id": "pub-p", "at": now,
                             "status": "pending"}]}
        tt.USAGE_FILE.write_text(json.dumps(usage))

        def fake_post(url, headers=None, json=None, **kw):
            if "status" in url:
                return _ok({"status": "PUBLISH_COMPLETE",
                            "publicaly_available_post_id": [555]})
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            out = tt.reconcile_pending("pub-p")
        self.assertEqual(
            out[0]["url"], "https://www.tiktok.com/@clips.daily548/video/555")
        self.assertEqual(out[0]["status"], "published")

    # ------------------------------------------------------------ check fn
    def test_check_api_ok_when_audited(self):
        def fake_post(url, headers=None, json=None, **kw):
            if "creator_info" in url:
                return _ok(CREATOR_INFO)
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            ok, detail = tt.check_tiktok_api()
        self.assertTrue(ok)
        self.assertIn("audited", detail)
        self.assertIn("0/15", detail)

    def test_check_api_flags_unaudited(self):
        def fake_post(url, headers=None, json=None, **kw):
            if "creator_info" in url:
                return _ok(CREATOR_INFO_PRIVATE)
            raise AssertionError(url)

        with mock.patch.object(tt.requests, "post", side_effect=fake_post):
            ok, detail = tt.check_tiktok_api()
        self.assertTrue(ok)  # token works; the audit state is in the text
        self.assertIn("UNAUDITED", detail)

    def test_check_api_missing_client(self):
        tt.CLIENT_FILE.unlink()
        ok, detail = tt.check_tiktok_api()
        self.assertFalse(ok)
        self.assertIn("client file missing", detail)


if __name__ == "__main__":
    unittest.main()
