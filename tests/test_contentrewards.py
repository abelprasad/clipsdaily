"""Unit tests for clipsdaily.contentrewards, against a LOCAL fixture.

The fixture is a tiny HTTP server on 127.0.0.1 that mimics the Content
Rewards campaign page (Join button + green Joined badge + submit form)
and the submissions dashboard (table with submission IDs). No real
credentials, no real site, no network beyond localhost.

Run on indra from the repo checkout:
  CLIPSDAILY_HOME=<tmp> PYTHONPATH=src python3 -m unittest \
      tests.test_contentrewards -v

A gate-PASS clip is built in setUpClass with PIL + ffmpeg: a real
1080x1920 mp4 whose center band is noise (sharp) and whose top/bottom
bands are a smooth gradient (blur-fill-like), so eligibility_gate's
band-energy check passes it. Gate-FAIL clips use a bad caption
instead, so framing never matters for them.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

CAMPAIGN_ID = "11111111-1111-1111-1111-111111111111"
CAMPAIGN_TITLE = "Test Campaign"
CLIP_URL = "https://youtube.com/shorts/TESTCLIP01"
NOW = datetime.now()


def _ts(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


CAMPAIGN_PAGE = """<!doctype html><html><head><title>campaign</title></head>
<body>
<h1>{title}</h1>
<button id="join-btn">Join</button>
<span id="joined-badge" style="display:none;color:green">Joined</span>
<form id="submit-form" onsubmit="return false;">
<input id="clip-url-input" name="clipUrl" type="url"
       placeholder="Paste your clip URL">
<button id="submit-clip-btn" type="button">Submit clip</button>
</form>
<div id="submit-confirmation" style="display:none">
Your clip submitted successfully.</div>
<script>
document.getElementById('join-btn').addEventListener('click', function() {{
  {join_js}
}});
document.getElementById('submit-clip-btn').addEventListener('click',
function() {{
  var url = document.getElementById('clip-url-input').value;
  fetch('/_fixture/submit', {{method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{campaign_id: '{cid}', clip_url: url}})}})
  .then(function(r) {{ return r.json(); }})
  .then(function(d) {{
    if (d.ok) {{
      document.getElementById('submit-confirmation').style.display = 'block';
    }}
  }});
}});
</script></body></html>"""

DASHBOARD_PAGE = """<!doctype html><html><head><title>submissions</title></head>
<body><h1>Submissions</h1>
<table id="submissions-table"><thead><tr>
<th>ID</th><th>Clip URL</th><th>Platform</th><th>Campaign</th>
<th>Status</th><th>Views</th><th>Payout</th><th>Submitted</th>
</tr></thead><tbody>
{rows}
</tbody></table></body></html>"""

ROW = ('<tr data-submission-id="{sid}" data-clip-url="{url}" '
       'data-platform="{platform}" data-campaign-id="{cid}" '
       'data-campaign-title="{title}" data-status="{status}" '
       'data-views="{views}" data-payout-cents="{payout}" '
       'data-submitted-at="{at}">'
       '<td>{sid}</td><td>{url}</td><td>{platform}</td><td>{title}</td>'
       '<td>{status}</td><td>{views}</td><td>{payout}</td><td>{at}</td>'
       '</tr>')


def make_fixture_server():
    """Return (server, state). state: {'submissions': [...], 'hits': n}."""
    state = {"submissions": [], "hits": 0, "next_id": 1}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="text/html"):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            state["hits"] += 1
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/c/campaigns/" + CAMPAIGN_ID:
                nobadge = q.get("mode", [""])[0] == "nobadge"
                join_js = ("/* broken: badge never appears */"
                           if nobadge else
                           "document.getElementById('joined-badge')"
                           ".style.display='inline';")
                self._send(200, CAMPAIGN_PAGE.format(
                    title=CAMPAIGN_TITLE, cid=CAMPAIGN_ID, join_js=join_js))
            elif u.path == "/dashboard/submissions":
                rows = "".join(ROW.format(**s) for s in state["submissions"])
                self._send(200, DASHBOARD_PAGE.format(rows=rows))
            else:
                self._send(404, "not found")

        def do_POST(self):
            state["hits"] += 1
            if urlparse(self.path).path != "/_fixture/submit":
                self._send(404, "not found")
                return
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            sid = "SUB-%04d" % state["next_id"]
            state["next_id"] += 1
            state["submissions"].append({
                "sid": sid, "url": body.get("clip_url", ""),
                "platform": "youtube", "cid": body.get("campaign_id", ""),
                "title": CAMPAIGN_TITLE, "status": "Pending",
                "views": 0, "payout": 0, "at": _ts(datetime.now())})
            self._send(200, json.dumps({"ok": True, "submission_id": sid}),
                       "application/json")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    return server, state


def build_gate_pass_clip(path):
    """1080x1920 mp4: noisy center band, smooth top/bottom bands.

    Built with PIL (one frame) + ffmpeg loop. Raises if ffmpeg/PIL
    are unavailable.
    """
    from PIL import Image
    import random
    random.seed(7)
    w, h = 1080, 1920
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        if 656 <= y < 1264:
            for x in range(w):
                v = random.randint(0, 255)
                px[x, y] = (v, (v * 7) % 256, (v * 13) % 256)
        else:
            v = int(40 + 60.0 * y / h)
            for x in range(w):
                px[x, y] = (v, v, v)
    frame = str(path.with_suffix(".png"))
    img.save(frame)
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", frame,
         "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "18", "-preset", "veryfast", str(path)],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed: %s" % r.stderr[-500:])


def good_entry(clip_file):
    return {
        "id": "clip-good-1",
        "vod_id": "2921253522",
        "vod_start_s": 10725,
        "vod_end_s": 10755,
        "destination": "Japan",
        "caption_yt": "Speed goes to Japan! Expedia #IShowSpeed",
        "caption_tiktok": "Speed goes to Japan! Expedia #IShowSpeed",
        "caption_ig": "Speed goes to Japan! Expedia #IShowSpeed",
        "clip30": str(clip_file),
    }


GOOD_CAMPAIGN = {
    "id": CAMPAIGN_ID,
    "title": CAMPAIGN_TITLE,
    "vod_id": "2921253522",
    "window_start_s": 10589,
    "window_end_s": None,
    "required_mentions": ["Expedia"],
    "required_hashtag": "#IShowSpeed",
    "exclude_ranges": [],
}


class ContentRewardsFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="cr-test-"))
        cls.clip = cls.tmp / "clip-good.mp4"
        build_gate_pass_clip(cls.clip)
        # Sanity: the built clip really passes the gate.
        from clipsdaily.eligibility_gate import gate_clip
        verdict = gate_clip(good_entry(cls.clip), GOOD_CAMPAIGN)
        assert verdict["ok"], "fixture clip must pass gate: %s" % verdict

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.server, self.state = make_fixture_server()
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.home = Path(tempfile.mkdtemp(prefix="cr-home-"))
        (self.home / "logs").mkdir()
        (self.home / ".auth").mkdir()
        (self.home / "submit-outbox").mkdir()
        (self.home / "queue").mkdir()
        # Opt-in + dummy session (fixture needs no real auth).
        (self.home / "config.yaml").write_text("campaign_automation: true\n")
        (self.home / ".auth" / "contentrewards_state.json").write_text(
            '{"cookies": [], "origins": []}')
        os.chmod(self.home / ".auth" / "contentrewards_state.json", 0o600)
        (self.home / "campaigns.json").write_text(
            json.dumps({"campaigns": {CAMPAIGN_ID: GOOD_CAMPAIGN}}))
        (self.home / "campaign_queue.json").write_text(
            json.dumps([good_entry(self.clip)]))
        (self.home / "queue" / "queue.json").write_text("[]")
        os.environ["CLIPSDAILY_HOME"] = str(self.home)
        from clipsdaily import contentrewards as cr
        self.cr = cr

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.home, ignore_errors=True)
        os.environ.pop("CLIPSDAILY_HOME", None)

    # helpers
    def _job(self, clip_id="clip-good-1", minutes_ago=5, platform="youtube"):
        job = {
            "job_id": "%s-%s" % (clip_id, platform),
            "clip_id": clip_id, "platform": platform,
            "clip_url": CLIP_URL, "campaign_id": CAMPAIGN_ID,
            "campaign_title": CAMPAIGN_TITLE,
            "posted_at": _ts(NOW - timedelta(minutes=minutes_ago)),
            "created_at": _ts(NOW), "status": "pending", "attempts": 0,
            "submission_id": None, "submitted_at": None, "notes": "",
            "history": []}
        (self.home / "submit-outbox" / ("%s-%s.json" % (clip_id, platform))
         ).write_text(json.dumps(job, indent=2))
        return job

    def _read_job(self, clip_id="clip-good-1", platform="youtube"):
        return json.loads((self.home / "submit-outbox"
                           / ("%s-%s.json" % (clip_id, platform))).read_text())

    # 1. join
    def test_join_marks_joined(self):
        (self.home / "join_requests.json").write_text(json.dumps([{
            "campaign_id": CAMPAIGN_ID, "title": CAMPAIGN_TITLE,
            "url": "%s/c/campaigns/%s" % (self.base, CAMPAIGN_ID),
            "status": "requested"}]))
        res = self.cr.join_campaigns(self.home, base=self.base)
        self.assertEqual(res["joined"], 1)
        results = json.loads((self.home / "join_results.json").read_text())
        self.assertEqual(results[0]["status"], "joined")
        self.assertEqual(results[0]["campaign_id"], CAMPAIGN_ID)

    def test_join_badge_missing_is_failed_not_joined(self):
        (self.home / "join_requests.json").write_text(json.dumps([{
            "campaign_id": CAMPAIGN_ID, "title": CAMPAIGN_TITLE,
            "url": "%s/c/campaigns/%s?mode=nobadge"
                   % (self.base, CAMPAIGN_ID),
            "status": "requested"}]))
        res = self.cr.join_campaigns(self.home, base=self.base)
        self.assertEqual(res["failed"], 1)
        results = json.loads((self.home / "join_results.json").read_text())
        self.assertEqual(results[0]["status"], "failed")
        self.assertIn("badge", results[0]["reason"].lower())

    def test_join_second_run_skips_already_joined(self):
        (self.home / "join_requests.json").write_text(json.dumps([{
            "campaign_id": CAMPAIGN_ID, "title": CAMPAIGN_TITLE,
            "url": "%s/c/campaigns/%s" % (self.base, CAMPAIGN_ID),
            "status": "requested"}]))
        self.cr.join_campaigns(self.home, base=self.base)
        hits_after_first = self.state["hits"]
        res = self.cr.join_campaigns(self.home, base=self.base)
        self.assertEqual(res["skipped"], 1)
        self.assertEqual(self.state["hits"], hits_after_first,
                         "second join run must not touch the site")

    # 2. submit
    def test_submit_marks_submitted_with_fixture_id(self):
        self._job()
        res = self.cr.submit_pending(self.home, base=self.base)
        self.assertEqual(res["submitted"], 1, res)
        job = self._read_job()
        self.assertEqual(job["status"], "submitted")
        self.assertEqual(job["submission_id"], "SUB-0001")
        self.assertEqual(len(self.state["submissions"]), 1)

    def test_submit_second_run_does_not_resubmit(self):
        self._job()
        self.cr.submit_pending(self.home, base=self.base)
        res = self.cr.submit_pending(self.home, base=self.base)
        self.assertEqual(res["submitted"], 0)
        self.assertEqual(res["pending"], 0)
        self.assertEqual(len(self.state["submissions"]), 1,
                         "must never file the same clip twice")

    def test_gate_failing_clip_is_not_submitted(self):
        bad = good_entry(self.clip)
        bad["id"] = "clip-bad-1"
        bad["caption_yt"] = "Speed goes to Japan!"  # no Expedia, no hashtag
        bad["caption_tiktok"] = bad["caption_yt"]
        bad["caption_ig"] = bad["caption_yt"]
        queue = json.loads((self.home / "campaign_queue.json").read_text())
        queue.append(bad)
        (self.home / "campaign_queue.json").write_text(json.dumps(queue))
        self._job(clip_id="clip-bad-1")
        res = self.cr.submit_pending(self.home, base=self.base)
        self.assertEqual(res["failed"], 1, res)
        job = self._read_job(clip_id="clip-bad-1")
        self.assertEqual(job["status"], "failed")
        self.assertIn("gate", job["notes"].lower())
        self.assertEqual(len(self.state["submissions"]), 0,
                         "gate-failing clip must never reach the site")

    def test_expired_job_is_never_submitted(self):
        self._job(minutes_ago=40)
        res = self.cr.submit_pending(self.home, base=self.base)
        job = self._read_job()
        self.assertIn(job["status"], ("expired", "failed"))
        self.assertEqual(len(self.state["submissions"]), 0,
                         "expired job must never reach the site")

    # 3. earnings
    def test_earnings_dump_matches_fixture_table(self):
        self._job()
        self.cr.submit_pending(self.home, base=self.base)
        res = self.cr.dump_earnings(self.home, base=self.base)
        self.assertEqual(res["submissions"], 1)
        dump = json.loads((self.home / "earnings_dump.json").read_text())
        sub = dump["submissions"][0]
        self.assertEqual(sub["submission_id"], "SUB-0001")
        self.assertEqual(sub["clip_url"], CLIP_URL)
        self.assertEqual(sub["status"], "Pending")
        self.assertEqual(sub["campaign_id"], CAMPAIGN_ID)
        self.assertEqual(sub["views"], 0)
        self.assertEqual(sub["payout_cents"], 0)

    def test_earnings_dump_unreachable_writes_nothing(self):
        with self.assertRaises(Exception):
            self.cr.dump_earnings(self.home,
                                  base="http://127.0.0.1:1")
        self.assertFalse((self.home / "earnings_dump.json").exists())

    # 4. dry-run + flag-off + session
    def test_dry_run_writes_nothing_and_touches_no_browser(self):
        self._job()
        hits_before = self.state["hits"]
        before = sorted(p.read_text() for p in
                        (self.home / "submit-outbox").glob("*.json"))
        out = subprocess.run(
            [sys.executable, "-m", "clipsdaily.contentrewards",
             "--home", str(self.home), "--base-url", self.base,
             "--dry-run", "submit"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "CLIPSDAILY_HOME": str(self.home),
                 "PYTHONPATH": str(Path(__file__).resolve().parents[1]
                                   / "src")})
        self.assertEqual(out.returncode, 0, out.stderr[-1000:])
        self.assertIn("WOULD submit", out.stdout)
        after = sorted(p.read_text() for p in
                       (self.home / "submit-outbox").glob("*.json"))
        self.assertEqual(before, after, "dry-run must not touch the outbox")
        self.assertEqual(self.state["hits"], hits_before,
                         "dry-run must make zero HTTP requests")

    def test_flag_off_refuses_everything(self):
        (self.home / "config.yaml").write_text(
            "campaign_automation: false\n")
        self._job()
        (self.home / "join_requests.json").write_text(json.dumps([{
            "campaign_id": CAMPAIGN_ID,
            "url": "%s/c/campaigns/%s" % (self.base, CAMPAIGN_ID)}]))
        hits_before = self.state["hits"]
        for cmd in ("join", "submit", "earnings-dump"):
            rc = self.cr.main(["--home", str(self.home),
                               "--base-url", self.base, cmd])
            self.assertEqual(rc, 2, cmd)
        self.assertEqual(self._read_job()["status"], "pending")
        self.assertFalse((self.home / "join_results.json").exists())
        self.assertFalse((self.home / "earnings_dump.json").exists())
        self.assertEqual(self.state["hits"], hits_before,
                         "flag-off must make zero HTTP requests")

    def test_missing_session_refuses(self):
        (self.home / ".auth" / "contentrewards_state.json").unlink()
        self._job()
        rc = self.cr.main(["--home", str(self.home),
                           "--base-url", self.base, "submit"])
        self.assertEqual(rc, 2)
        self.assertEqual(self._read_job()["status"], "pending")
        self.assertEqual(len(self.state["submissions"]), 0)


if __name__ == "__main__":
    unittest.main()
