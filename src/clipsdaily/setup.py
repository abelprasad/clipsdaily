"""ClipForge one-time setup wizard: `clipforge setup`.

Walks a new customer through the one-time human steps — accounts,
watchlist, platforms, notifier, campaign opt-in, auth — then enables
and starts the systemd units. Re-runnable: it never overwrites an
existing config.yaml or auth file without asking.

  clipforge setup            # interactive prompts
  clipforge setup --yes      # non-interactive: defaults + env vars,
                             # auth steps printed as manual instructions

Env vars honored by --yes:
  CLIPFORGE_WATCHLIST   "twitch:kaicenat,kick:adinross"
  CLIPFORGE_IG_USER     CLIPFORGE_YT_HANDLE  CLIPFORGE_TIKTOK_USER
  CLIPFORGE_NOTIFY      none|email|discord

Passwords and tokens are NEVER written to config.yaml, logs, or the
console. Auth flows run the same modules the services use
(auth_youtube / auth_instagram / tiktok_api / auth_tiktok), so a
successful wizard run means the services can post.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

from .branding import BRAND_NAME, BRAND_SLUG
from .paths import runtime_home

HERE = runtime_home()
CONFIG_FILE = HERE / "config.yaml"
TEMPLATE = Path(__file__).resolve().parent.parent / "config" / "config.yaml.example"
UNITS = ["%s-runner" % BRAND_SLUG, "%s-hourly" % BRAND_SLUG,
         "%s-queue" % BRAND_SLUG, "%s-ig" % BRAND_SLUG,
         "%s-watchdog" % BRAND_SLUG, "%s-dashboard" % BRAND_SLUG]
TIMERS = ["%s-campaign-watch.timer" % BRAND_SLUG,
          "%s-submit.timer" % BRAND_SLUG,
          "%s-earnings.timer" % BRAND_SLUG,
          "%s-cleanup.timer" % BRAND_SLUG]


def _prompt(text, default="", yes=False):
    if yes:
        return default
    ans = input("%s [%s]: " % (text, default)).strip() if default \
        else input("%s: " % text).strip()
    return ans or default


def _yes_no(text, default=False, yes=False):
    if yes:
        return default
    d = "Y/n" if default else "y/N"
    ans = input("%s [%s]: " % (text, d)).strip().lower()
    if not ans:
        return default
    return ans in ("y", "yes")


def _load_config():
    if CONFIG_FILE.exists():
        return yaml.safe_load(CONFIG_FILE.read_text()) or {}
    if TEMPLATE.exists():
        return yaml.safe_load(TEMPLATE.read_text()) or {}
    return {}


def _save_config(cfg):
    tmp = CONFIG_FILE.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(cfg, sort_keys=False))
    tmp.replace(CONFIG_FILE)
    os.chmod(CONFIG_FILE, 0o600)
    print("wrote %s" % CONFIG_FILE)


def _parse_watchlist(raw):
    out = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            platform, channel = item.split(":", 1)
        else:
            platform, channel = "twitch", item
        platform = platform.strip().lower()
        channel = channel.strip().lower()
        if platform not in ("twitch", "kick"):
            print("  skipping %r: platform must be twitch or kick" % item)
            continue
        out.append({"platform": platform, "channel": channel})
    return out


def _run_module(module, *args):
    """Run a package module as a subprocess (its own argv/env)."""
    cmd = [sys.executable, "-m", "clipsdaily.%s" % module, *args]
    print("  running: %s" % " ".join(cmd))
    return subprocess.run(cmd).returncode


def _auth_steps(cfg, yes=False):
    """Per-platform auth. Returns True if every enabled platform is
    authenticated (or skipped by the user on purpose)."""
    platforms = cfg.get("platforms", {})
    ok = True
    if platforms.get("youtube"):
        print("\nYouTube OAuth:")
        print("  You need a Google Cloud project with the YouTube Data API")
        print("  v3 enabled and a Desktop OAuth client. IMPORTANT: publish")
        print("  the OAuth app to Production — in Testing mode the refresh")
        print("  token expires after 7 days and posting stops.")
        if _yes_no("Run the YouTube OAuth flow now?", True, yes):
            rc = _run_module("auth_youtube")
            if rc != 0:
                print("  YouTube auth did not complete — run "
                      "`clipforge auth youtube` later.")
                ok = False
        else:
            print("  Skipped — run `clipforge auth youtube` later.")
    if platforms.get("instagram"):
        print("\nInstagram session:")
        print("  Recommended: export a session cookie from a browser")
        print("  signed in to the account (Netscape cookies.txt format).")
        print("  Password login is the fallback and may be blocked by")
        print("  Instagram's login endpoint.")
        if _yes_no("Set up Instagram now?", True, yes):
            cookies = _prompt("Path to cookies.txt (blank = password "
                              "login)", "", yes)
            rc = _run_module("auth_instagram",
                             * (["--cookies", cookies] if cookies else []))
            if rc != 0:
                print("  Instagram auth did not complete — run "
                      "`clipforge auth instagram --cookies cookies.txt` "
                      "later.")
                ok = False
        else:
            print("  Skipped — run `clipforge auth instagram` later.")
    if platforms.get("tiktok"):
        print("\nTikTok:")
        print("  Official API (recommended): create a developer app at")
        print("  developers.tiktok.com, request the Content Posting API")
        print("  audit, then run `clipforge auth tiktok` (API flow).")
        print("  Cookie fallback: `clipforge auth tiktok` with cookies")
        print("  (may be blocked — TikTok rejects cookie uploads today).")
        if _yes_no("Run the TikTok API auth flow now?", False, yes):
            rc = _run_module("tiktok_api", "--auth-url")
            if rc != 0:
                print("  TikTok API auth did not complete — see "
                      "docs/TIKTOK_API_SETUP.md.")
                ok = False
        else:
            print("  Skipped — run `clipforge auth tiktok` later.")
    if cfg.get("campaign_automation"):
        print("\nContent Rewards:")
        print("  Campaign automation is ON. Run `clipforge auth")
        print("  contentrewards` and log in in the headed browser when")
        print("  ready. Read docs/CONTENTREWARDS_AUTO.md first —")
        print("  campaigns have a one-strike rule.")
    return ok


def _enable_units():
    print("\nEnabling systemd units...")
    rc, _, err = _run(["systemctl", "--user", "daemon-reload"])
    if rc != 0:
        print("  systemctl --user failed (%s) — is systemd running as "
              "your user? Enable the units by hand:\n"
              "    systemctl --user enable --now clipforge-runner ..."
              % (err or "unknown error"))
        return False
    _run(["systemctl", "--user", "enable", *UNITS, *TIMERS])
    rc, out, _ = _run(["loginctl", "show-user", os.environ.get("USER", ""),
                       "-p", "Linger"])
    if "Linger=yes" not in out:
        print("  NOTE: user linger is OFF — services stop at logout.")
        print("  Enable it with: loginctl enable-linger $USER")
    rc, _, err = _run(["systemctl", "--user", "start", *UNITS, *TIMERS])
    if rc != 0:
        print("  some units failed to start (%s) — check with "
              "`systemctl --user status clipforge-runner`" % err)
        return False
    print("  all units enabled + started")
    return True


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def setup(yes=False):
    print("%s setup — one-time configuration\n" % BRAND_NAME)
    cfg = _load_config()
    if CONFIG_FILE.exists():
        print("config.yaml already exists — answers below update it in "
              "place (auth files are never touched).")

    # --- accounts
    accounts = cfg.setdefault("accounts", {})
    print("Accounts (these are checked against your logins; a mismatch")
    print("refuses to post, so a wrong login can never post elsewhere):")
    accounts["instagram"] = _prompt(
        "Instagram username (no @)", accounts.get("instagram") or "", yes) \
        or accounts.get("instagram") or ""
    accounts["youtube"] = _prompt(
        "YouTube handle (e.g. @MyClips)", accounts.get("youtube") or "", yes) \
        or accounts.get("youtube") or ""
    accounts["tiktok"] = _prompt(
        "TikTok username (no @)", accounts.get("tiktok") or "", yes) \
        or accounts.get("tiktok") or ""

    # --- watchlist
    raw = os.environ.get("CLIPFORGE_WATCHLIST", "")
    if not yes or raw:
        raw = _prompt("Watchlist (comma-separated, e.g. "
                      "twitch:kaicenat,kick:adinross)",
                      raw, yes)
    cfg["streamers"] = _parse_watchlist(raw)
    print("  %d streamers" % len(cfg["streamers"]))

    # --- platforms
    platforms = cfg.setdefault("platforms", {})
    for name in ("youtube", "instagram", "tiktok"):
        platforms[name] = _yes_no("Post to %s?" % name.capitalize(),
                                  bool(platforms.get(name)), yes)

    # --- campaign opt-in (default OFF, with the warning)
    current = bool(cfg.get("campaign_automation"))
    if not current:
        print("\nCampaign automation (Content Rewards) is OFF by default.")
        print("Campaigns have a ONE-STRIKE rule: a wrong clip can get")
        print("the account banned from the program.")
    cfg["campaign_automation"] = _yes_no(
        "Enable campaign automation?", current, yes)

    # --- notifier
    notify = cfg.setdefault("notify", {})
    channel = _prompt("Health alerts (none/email/discord)",
                      os.environ.get("CLIPFORGE_NOTIFY")
                      or notify.get("channel") or "none", yes).lower()
    if channel not in ("none", "email", "discord"):
        print("  unknown channel %r — using none" % channel)
        channel = "none"
    notify["channel"] = channel
    if channel == "email":
        em = notify.setdefault("email", {})
        em["host"] = _prompt("SMTP host", em.get("host") or "", yes)
        em["port"] = int(_prompt("SMTP port", str(em.get("port") or 587), yes))
        em["from"] = _prompt("From address", em.get("from") or "", yes)
        em["to"] = _prompt("Alert recipient", em.get("to") or "", yes)
        em["user"] = _prompt("SMTP user", em.get("user") or "", yes)
        print("  Set CLIPFORGE_SMTP_PASS in the environment — the "
              "password is never stored in config.")
    if channel == "discord":
        d = notify.setdefault("discord", {})
        d["webhook_url"] = _prompt("Discord webhook URL",
                                   d.get("webhook_url") or "", yes)

    _save_config(cfg)
    _auth_steps(cfg, yes=yes)
    _enable_units()
    print("\nDone. Dashboard: http://127.0.0.1:8787")
    print("Status any time: clipforge status")
    print("Auth check:      clipforge auth check")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="clipforge setup")
    ap.add_argument("--yes", action="store_true",
                    help="non-interactive: defaults + env vars, auth "
                         "steps printed as manual instructions")
    args = ap.parse_args(argv)
    return setup(yes=args.yes)


if __name__ == "__main__":
    sys.exit(main())
