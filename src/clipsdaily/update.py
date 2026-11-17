#!/usr/bin/env python3
"""ClipForge auto-update with rollback.

Opt-in (config.yaml `auto_update: false` by default). When enabled, the
updater pulls versioned releases from the release channel (a git remote
— the public repo once it exists; a local path works too, which is how
the installer tests it) and:

  1. Records the current version + checkout in update-state.json.
  2. Fetches the channel, picks the newest v* tag (or --to TAG).
  3. Checks the new checkout out into a staging dir and runs the test
     suite there. A test failure aborts before anything is touched.
  4. Installs the new version into the venv and restarts the units.
  5. Health-checks for 10 minutes (units active + health.json fresh).
     On failure it automatically rolls back: reinstall the previous
     version, restart the units, verify, and log.

Nothing is ever auto-updated without a rollback path, and an update
never deletes runtime state (queue/, .auth/, config.yaml, logs/ are
untouched — only the installed code moves).

The release channel does not exist yet (the repo has no remote). Until
it does, `clipforge update` refuses with "no release channel
configured" — which is the safe default.

Usage:
  python3 -m clipsdaily.update --check        # show current vs latest
  python3 -m clipsdaily.update [--to vX.Y.Z]  # update (opt-in only)
  python3 -m clipsdaily.update --rollback     # restore previous version
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

from . import __version__
from .branding import BRAND_SLUG
from .paths import runtime_home

HERE = runtime_home()
STATE_FILE = HERE / "update-state.json"
UNITS = ["%s-runner" % BRAND_SLUG, "%s-hourly" % BRAND_SLUG,
         "%s-queue" % BRAND_SLUG, "%s-ig" % BRAND_SLUG,
         "%s-dashboard" % BRAND_SLUG, "%s-watchdog" % BRAND_SLUG]
HEALTH_TIMEOUT_SECONDS = 600


def _run(cmd, cwd=None, timeout=600):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _load_config():
    try:
        return yaml.safe_load((HERE / "config.yaml").read_text()) or {}
    except Exception:
        return {}


def _load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state):
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(STATE_FILE)


def _release_dir():
    """Where the installed checkout lives (created by the installer)."""
    return Path.home() / ("%s-release" % BRAND_SLUG)


def _venv_python():
    venv = Path.home() / (".%s-venv" % BRAND_SLUG) / "bin" / "python"
    if venv.exists():
        return str(venv)
    return sys.executable


def latest_tag(channel):
    """Newest v* tag on the channel (git remote or local path)."""
    rc, out, err = _run(["git", "ls-remote", "--tags", "--sort=-v:refname",
                         channel])
    if rc != 0:
        raise RuntimeError("cannot reach release channel %r: %s"
                           % (channel, err))
    for line in out.splitlines():
        ref = line.split()[-1]
        if ref.startswith("refs/tags/v") and not ref.endswith("^{}"):
            return ref.split("/")[-1]
    return None


def run_tests(checkout):
    """The repo test suite, in the new checkout. Returns (ok, output)."""
    test_dir = Path(checkout) / "tests"
    if not test_dir.exists():
        return True, "no tests/ in checkout, skipping"
    rc, out, err = _run([_venv_python(), "-m", "pytest", "-q", "tests"],
                        cwd=checkout, timeout=1200)
    return rc == 0, (out + "\n" + err)[-2000:]


def install_checkout(checkout):
    rc, out, err = _run([_venv_python(), "-m", "pip", "install",
                         "--force-reinstall", "--no-deps", "."],
                        cwd=checkout, timeout=900)
    if rc != 0:
        raise RuntimeError("pip install failed: %s" % err[-1000:])


def restart_units():
    for unit in UNITS:
        _run(["systemctl", "--user", "restart", unit], timeout=60)


def units_active():
    for unit in UNITS:
        rc, out, _ = _run(["systemctl", "--user", "is-active", unit])
        if rc != 0 or out.strip() != "active":
            return False, unit
    return True, ""


def health_fresh(max_age_seconds=1800):
    try:
        health = json.loads((HERE / "health.json").read_text())
        checked = health.get("checked_at", "")
        from datetime import datetime
        ts = datetime.fromisoformat(checked)
        age = (datetime.now(ts.tzinfo) - ts).total_seconds()
        return age <= max_age_seconds, "health.json age %.0fs" % age
    except Exception as e:
        return False, "health.json unreadable: %s" % e


def health_check(timeout=HEALTH_TIMEOUT_SECONDS):
    """Wait up to timeout for all units active + fresh health.json."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ok, bad = units_active()
        if ok:
            fresh, detail = health_fresh()
            if fresh:
                return True, "all units active, %s" % detail
        time.sleep(30)
    ok, bad = units_active()
    if not ok:
        return False, "unit not active: %s" % bad
    return False, "health.json not fresh after %ds" % timeout


def do_update(to_tag=None, channel=None):
    cfg = _load_config()
    if not cfg.get("auto_update", False):
        print("auto_update is off in config.yaml — refusing to update "
              "(opt-in only).")
        return 2
    channel = channel or cfg.get("update_channel") or ""
    if not channel:
        print("no release channel configured (update_channel in "
              "config.yaml) — refusing to update.")
        return 2
    release = _release_dir()
    if not (release / ".git").exists():
        print("no release checkout at %s — reinstall via install.sh."
              % release)
        return 2
    target = to_tag or latest_tag(channel)
    if not target:
        print("no v* tags on channel %s" % channel)
        return 2
    if target.lstrip("v") == __version__:
        print("already on %s" % target)
        return 0
    state = _load_state()
    previous = state.get("version", __version__)
    print("updating %s -> %s (channel %s)" % (previous, target, channel))
    _run(["git", "fetch", "--tags", channel], cwd=release)
    staging = release.parent / ("%s-staging" % BRAND_SLUG)
    if staging.exists():
        import shutil
        shutil.rmtree(staging)
    rc, _, err = _run(["git", "clone", "--quiet", str(release),
                       str(staging)])
    if rc != 0:
        print("staging clone failed: %s" % err)
        return 1
    _run(["git", "checkout", "--quiet", target], cwd=staging)
    ok, output = run_tests(staging)
    if not ok:
        print("tests FAILED on %s — aborting, nothing changed:\n%s"
              % (target, output))
        return 1
    print("tests passed on %s; installing" % target)
    _save_state({"version": previous, "target": target,
                 "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    try:
        install_checkout(staging)
    except Exception as e:
        print("install failed: %s — rolling back" % e)
        return do_rollback()
    _run(["git", "checkout", "--quiet", target], cwd=release)
    restart_units()
    ok, detail = health_check()
    if not ok:
        print("health check FAILED after update (%s) — rolling back"
              % detail)
        return do_rollback()
    _save_state({"version": target.lstrip("v"), "target": target,
                 "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print("updated to %s; %s" % (target, detail))
    return 0


def do_rollback():
    state = _load_state()
    previous = state.get("version")
    if not previous:
        print("no previous version recorded — cannot roll back.")
        return 1
    release = _release_dir()
    print("rolling back to %s" % previous)
    _run(["git", "checkout", "--quiet", "v%s" % previous], cwd=release)
    try:
        install_checkout(release)
    except Exception as e:
        print("rollback install FAILED: %s — manual reinstall needed" % e)
        return 1
    restart_units()
    ok, detail = health_check(timeout=300)
    if not ok:
        print("rollback health check FAILED (%s) — manual intervention "
              "needed" % detail)
        return 1
    _save_state({"version": previous,
                 "rolled_back_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    print("rolled back to %s; %s" % (previous, detail))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="%s update" % BRAND_SLUG)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--to", metavar="TAG")
    ap.add_argument("--rollback", action="store_true")
    ap.add_argument("--channel", metavar="URL-OR-PATH")
    args = ap.parse_args(argv)
    if args.rollback:
        return do_rollback()
    if args.check:
        cfg = _load_config()
        channel = args.channel or cfg.get("update_channel") or ""
        print("current: v%s" % __version__)
        if not channel:
            print("latest: (no release channel configured)")
            return 0
        try:
            print("latest: %s" % (latest_tag(channel) or "(no tags)"))
        except Exception as e:
            print("latest: error: %s" % e)
            return 1
        return 0
    return do_update(to_tag=args.to, channel=args.channel)


if __name__ == "__main__":
    sys.exit(main())
