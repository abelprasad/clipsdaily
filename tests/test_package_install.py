"""ClipForge installer simulation tests (slow, subprocess).

Runs the real install.sh against scratch homes on this machine.
Requires: bash, git, python3.10+, ffmpeg>=6.1, network for the pip
upgrade step (deps are skipped with CLIPFORGE_PIP_NO_DEPS=1).

Run: PYTHONPATH=src python3 -m unittest tests.test_package_install -v
"""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey)

REPO = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO / "packaging" / "install.sh"


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.priv = Ed25519PrivateKey.generate()
        cls.pub_pem = cls.priv.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo)
        cls.tmp = Path(tempfile.mkdtemp(prefix="clipforge-install-test-"))
        (cls.tmp / "test-pub.pem").write_bytes(cls.pub_pem)
        payload = {"kid": "CF-TEST-100", "email": "test@clipforge.local",
                   "exp": "2027-06-30", "tier": "beta"}
        payload_bytes = json.dumps(payload, separators=(",", ":"),
                                   sort_keys=True).encode()
        sig = cls.priv.sign(payload_bytes)
        cls.good_key = "CF1-%s.%s" % (_b64e(payload_bytes), _b64e(sig))
        (cls.tmp / "good.key").write_text(cls.good_key)
        (cls.tmp / "bad.key").write_text(cls.good_key[:-4] + "AAAA")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _env(self, home):
        # NOTE: HOME stays the real home so the installer can find the
        # user's ffmpeg in ~/.local/bin. Only the venv, release
        # checkout, and runtime home are redirected into scratch dirs.
        env = dict(os.environ)
        env["CLIPFORGE_VENV_DIR"] = str(self.tmp / "venv")
        env["CLIPFORGE_RELEASE_HOME"] = str(self.tmp / "release")
        env["CLIPFORGE_LICENSE_PUBLIC_KEY"] = str(self.tmp / "test-pub.pem")
        env["CLIPFORGE_PIP_NO_DEPS"] = "1"
        env["CLIPFORGE_VENV_SYSTEM_SITE"] = "1"
        env["CLIPFORGE_SKIP_PLAYWRIGHT"] = "1"
        env["CLIPFORGE_SKIP_PREWARM"] = "1"
        return env

    def _run_install(self, home, *args, stdin=subprocess.DEVNULL):
        cmd = ["bash", str(INSTALL_SH), "--home", str(home),
               "--no-systemd", "--accept-license", *args]
        r = subprocess.run(cmd, env=self._env(home),
                           stdin=stdin, capture_output=True, text=True,
                           timeout=600)
        return r

    def _scratch_home(self):
        return Path(tempfile.mkdtemp(prefix="cf-home-",
                                     dir=str(self.tmp)))

    def test_refuses_live_directory(self):
        home = self._scratch_home()
        r = subprocess.run(
            ["bash", str(INSTALL_SH), "--home", "/home/abel/clipsdaily",
             "--no-systemd", "--accept-license", "--license",
             str(self.tmp / "good.key")],
            env=self._env(home), stdin=subprocess.DEVNULL,
            capture_output=True, text=True, timeout=120)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("refusing", r.stdout + r.stderr)
        shutil.rmtree(home, ignore_errors=True)

    def test_refuses_without_key(self):
        home = self._scratch_home()
        r = self._run_install(home)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("no license key", r.stdout + r.stderr)
        shutil.rmtree(home, ignore_errors=True)

    def test_refuses_bad_key_and_creates_no_home_state(self):
        home = self._scratch_home()
        r = self._run_install(home, "--license", str(self.tmp / "bad.key"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("license key invalid", r.stdout + r.stderr)
        # Key validation happens before the runtime home is created.
        self.assertFalse((home / "queue").exists())
        self.assertFalse((home / ".auth" / "license.key").exists())
        shutil.rmtree(home, ignore_errors=True)

    def test_full_install_and_smoke(self):
        home = self._scratch_home()
        r = self._run_install(home, "--license", str(self.tmp / "good.key"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        try:
            self.assertTrue((home / ".clipforge-home").exists())
            self.assertTrue((home / "config.yaml").exists())
            key_file = home / ".auth" / "license.key"
            self.assertTrue(key_file.exists())
            self.assertEqual(oct(key_file.stat().st_mode & 0o777), "0o600")
            self.assertTrue((home / "LICENSE").exists())
            self.assertTrue((home / "BETA_TERMS.md").exists())
            self.assertTrue((home / ".accepted-terms").exists())
            for d in ("queue/clips", "queue/work", "ig-outbox", "clips",
                      "vod", "recordings", "logs"):
                self.assertTrue((home / d).is_dir(), d)
            venv_python = self.tmp / "venv" / "bin" / "python"
            self.assertTrue(venv_python.exists())
            # The good ffmpeg (micromamba 9) is linked into the venv.
            self.assertTrue((self.tmp / "venv" / "bin" / "ffmpeg").exists())
            env = self._env(home)
            env["CLIPFORGE_HOME"] = str(home)
            clipforge = self.tmp / "venv" / "bin" / "clipforge"
            # License status (ungated command) reports the test key.
            r = subprocess.run([str(clipforge), "license", "status"],
                               env=env, capture_output=True, text=True,
                               timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("test@clipforge.local", r.stdout)
            # setup --yes writes the watchlist from the env, skips auth
            # (all platforms off by default), and returns 0.
            env["CLIPFORGE_WATCHLIST"] = "twitch:kaicenat,kick:adinross"
            r = subprocess.run([str(clipforge), "setup", "--yes"],
                               env=env, capture_output=True, text=True,
                               timeout=300)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            import yaml
            cfg = yaml.safe_load((home / "config.yaml").read_text())
            self.assertEqual(
                cfg["streamers"],
                [{"platform": "twitch", "channel": "kaicenat"},
                 {"platform": "kick", "channel": "adinross"}])
            # IG worker dry-run in an empty home: nothing staged, exit 0.
            r = subprocess.run([str(clipforge), "ig", "--once", "--dry-run"],
                               env=env, capture_output=True, text=True,
                               timeout=120)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        finally:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
