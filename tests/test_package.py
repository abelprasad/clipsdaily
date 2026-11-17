"""ClipForge package tests: license keys, campaign-queue lock, config
template, and the GUI no-internals boundary.

Run: PYTHONPATH=src python3 -m unittest tests.test_package -v
(These are unit tests; the full installer simulation lives in
tests/test_package_install.py.)
"""
import base64
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey)

from clipsdaily import license as lic_mod


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _sign_key(priv, kid, email, exp, tier="beta"):
    payload = {"kid": kid, "email": email, "exp": exp, "tier": tier}
    payload_bytes = json.dumps(payload, separators=(",", ":"),
                               sort_keys=True).encode()
    sig = priv.sign(payload_bytes)
    return "CF1-%s.%s" % (_b64e(payload_bytes), _b64e(sig))


class LicenseKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.priv = Ed25519PrivateKey.generate()
        cls.pub_pem = cls.priv.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    def test_valid_key_verifies(self):
        key = _sign_key(self.priv, "CF-TEST-0001", "a@example.com",
                        "2027-06-30")
        res = lic_mod.verify_key(key, public_key_pem=self.pub_pem)
        self.assertTrue(res["valid"], res)
        self.assertEqual(res["kid"], "CF-TEST-0001")
        self.assertEqual(res["email"], "a@example.com")

    def test_tampered_signature_rejected(self):
        key = _sign_key(self.priv, "CF-TEST-0001", "a@example.com",
                        "2027-06-30")
        head, sig = key.split(".")
        bad_sig = ("A" if sig[0] != "A" else "B") + sig[1:]
        res = lic_mod.verify_key(head + "." + bad_sig,
                                 public_key_pem=self.pub_pem)
        self.assertFalse(res["valid"])
        self.assertIn("signature", res["error"].lower())

    def test_wrong_issuer_rejected(self):
        other = Ed25519PrivateKey.generate()
        key = _sign_key(other, "CF-TEST-0009", "x@example.com", "2027-06-30")
        res = lic_mod.verify_key(key, public_key_pem=self.pub_pem)
        self.assertFalse(res["valid"])

    def test_expired_key_rejected(self):
        key = _sign_key(self.priv, "CF-TEST-0002", "a@example.com",
                        "2026-01-01")
        res = lic_mod.verify_key(key, public_key_pem=self.pub_pem)
        self.assertFalse(res["valid"])
        self.assertIn("expired", res["error"])

    def test_garbage_rejected(self):
        for bad in ("", "not-a-key", "CF1-xxx", "CF1-aaa.bbb.ccc"):
            res = lic_mod.verify_key(bad, public_key_pem=self.pub_pem)
            self.assertFalse(res["valid"], bad)

    def test_installed_key_vendor_round_trip(self):
        """Sign with the real vendor private key (when present on this
        machine) and verify through load_installed_key + the baked-in
        public key — the exact path the installer uses. Skipped where
        the vendor key is not present (e.g. a contributor's machine)."""
        vendor_key = Path("/home/abel/.config/clipforge/license-private.key")
        if not vendor_key.exists():
            self.skipTest("vendor private key not on this machine")
        from cryptography.hazmat.primitives import serialization as ser
        priv = ser.load_pem_private_key(vendor_key.read_bytes(),
                                        password=None)
        key = _sign_key(priv, "CF-TEST-0003", "b@example.com", "2027-06-30")
        with tempfile.TemporaryDirectory() as home:
            auth = Path(home) / ".auth"
            auth.mkdir()
            (auth / "license.key").write_text(key)
            res = lic_mod.load_installed_key(home)
            self.assertTrue(res["valid"], res)
            self.assertEqual(res["email"], "b@example.com")
            ok, detail = lic_mod.key_status(home)
            self.assertTrue(ok)
            self.assertIn("b@example.com", detail)


class CampaignLockTests(unittest.TestCase):
    def test_concurrent_saves_lose_nothing(self):
        """Two writers appending campaign entries at once (the Nov 16
        queue-race shape) must not lose each other's entries."""
        from clipsdaily import campaign_cut
        with tempfile.TemporaryDirectory() as home:
            campaign_cut.CAMPAIGN_QUEUE_FILE = \
                Path(home) / "campaign_queue.json"
            campaign_cut.CAMPAIGN_QUEUE_LOCK = \
                Path(home) / "campaign_queue.lock"
            errors = []

            def writer(n):
                try:
                    for i in range(10):
                        campaign_cut.save_campaign_entry(
                            {"id": "clip-%d-%d" % (n, i), "status": "pending"})
                except Exception as e:  # noqa: BLE001
                    errors.append(e)

            threads = [threading.Thread(target=writer, args=(n,))
                       for n in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            entries = campaign_cut.load_campaign_queue()
            self.assertEqual(len(entries), 40)
            self.assertEqual(len({e["id"] for e in entries}), 40)


class ConfigTemplateTests(unittest.TestCase):
    def test_template_parses_and_has_package_keys(self):
        import yaml
        repo = Path(__file__).resolve().parents[1]
        tpl = repo / "config" / "config.yaml.example"
        cfg = yaml.safe_load(tpl.read_text())
        for key in ("accounts", "notify", "campaign_automation",
                    "auto_update", "update_channel",
                    "queue_clip_retention_days", "ig_outbox_retention_days",
                    "vod_retention_days", "brand_caption_prefix"):
            self.assertIn(key, cfg, "config template missing %s" % key)
        self.assertEqual(cfg["notify"]["channel"], "none")
        self.assertFalse(cfg["campaign_automation"])
        self.assertFalse(cfg["auto_update"])

    def test_template_does_not_teach_tuning(self):
        repo = Path(__file__).resolve().parents[1]
        text = (repo / "config" / "config.yaml.example").read_text()
        for phrase in ("per 10s window", "floor before a spike",
                       "spike counts", "chat spike"):
            self.assertNotIn(phrase, text)


class DashboardNoInternalsTests(unittest.TestCase):
    def test_dashboard_shows_no_tuning_knobs(self):
        """The GUI must not expose cutter internals or spike tuning."""
        from clipsdaily import dashboard
        home = Path(tempfile.mkdtemp())
        (home / "config.yaml").write_text(
            "streamers: []\nmax_clips_per_day: 20\n"
            "spike_threshold_multiplier: 3.0\n"
            "spike_min_messages: 20\nspike_window_seconds: 10\n"
            "spike_cooldown_seconds: 300\nwhisper_model: base\n"
            "platforms: {youtube: false, tiktok: false, instagram: false}\n")
        html = dashboard.render_dashboard(home)
        for leaked in ("spike_threshold_multiplier", "spike_min_messages",
                       "spike_window_seconds", "spike_cooldown_seconds",
                       "whisper_model"):
            self.assertNotIn(leaked, html,
                             "dashboard leaks tuning knob %s" % leaked)


if __name__ == "__main__":
    unittest.main()
