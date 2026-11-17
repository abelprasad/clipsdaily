"""One-time Instagram login for ClipForge.

Creates .auth/instagram_session.json (mode 0600) so poster.py can post
Reels without a password on disk. Two ways to authenticate:

  1. Session-cookie import (RECOMMENDED — instagrapi password login is
     currently broken against Instagram's login endpoint):
         python3 -m clipsdaily.auth_instagram --cookies cookies.txt
     where cookies.txt is a Netscape-format cookie export from a browser
     signed in to the account (extensions like "Get cookies.txt" work).
     Only the sessionid cookie is read; the file is never copied or
     stored. The session is verified with a read-only account_info()
     call before anything is saved.

  2. Password login (fallback; may fail while Instagram blocks the
     password endpoint):
         CLIPFORGE_IG_USER=<user> CLIPFORGE_IG_PASS='<password>' \\
             python3 -m clipsdaily.auth_instagram
     The password is read from the environment only and is never written
     to disk, to a log, or to the session file (the session file holds
     device ids + the sessionid cookie only). If Instagram asks for a
     two-factor code, the script prompts for it on stdin.

The expected account comes from config.yaml `accounts.instagram`
(username; primary check) and `accounts.instagram_user_id` (numeric id;
checked only when set). A successful login clears the watchdog's
<unit>.auth-dead marker so the IG worker restarts.

After this succeeds, verify with:  python3 -m clipsdaily.poster --check
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

import yaml

from .paths import runtime_home

HERE = runtime_home()
AUTH_DIR = HERE / ".auth"
SESSION_FILE = AUTH_DIR / "instagram_session.json"

IG_USERNAME = "clippedaily31"
IG_USER_ID = 27125641130


def _expected_account():
    try:
        cfg = yaml.safe_load((HERE / "config.yaml").read_text()) or {}
    except Exception:
        cfg = {}
    accounts = cfg.get("accounts") or {}
    return (accounts.get("instagram", IG_USERNAME),
            accounts.get("instagram_user_id"))


def _check_identity(me):
    expected_user, expected_id = _expected_account()
    if expected_user and me.username.lower() != expected_user.lower():
        print(f"ERROR: logged in as @{me.username} (id {me.pk}), "
              f"expected @{expected_user}. Aborting — session NOT saved.",
              file=sys.stderr)
        sys.exit(1)
    if expected_id and int(me.pk) != int(expected_id):
        print(f"ERROR: logged in as @{me.username} (id {me.pk}), "
              f"expected id {expected_id}. Aborting — session NOT saved.",
              file=sys.stderr)
        sys.exit(1)


def _save_session(cl, me):
    AUTH_DIR.mkdir(mode=0o700, exist_ok=True)
    os.chmod(AUTH_DIR, 0o700)
    cl.dump_settings(str(SESSION_FILE))
    os.chmod(SESSION_FILE, 0o600)
    # Clear the watchdog's auth-dead marker so the IG worker restarts.
    marker = HERE / "logs" / "clipforge-ig.auth-dead"
    try:
        marker.unlink()
    except FileNotFoundError:
        pass
    print(f"OK: session saved for @{me.username} "
          f"({SESSION_FILE}, mode 0600)")
    print("Verify with: python3 -m clipsdaily.poster --check")


def _read_sessionid(cookies_file):
    """sessionid from a Netscape-format cookies.txt (instagram.com)."""
    sessionid = None
    for line in Path(cookies_file).read_text(errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            domain, _, _, _, _, name, value = parts[:7]
            if "instagram.com" in domain and name == "sessionid":
                sessionid = value.strip()
    if not sessionid:
        print(f"ERROR: no instagram.com sessionid in {cookies_file} — "
              "export cookies from a browser signed in to the account.",
              file=sys.stderr)
        sys.exit(1)
    return sessionid


def login_with_cookies(cookies_file):
    from instagrapi import Client
    from instagrapi.exceptions import LoginRequired

    cl = Client()
    sessionid = _read_sessionid(cookies_file)
    try:
        cl.login_by_sessionid(sessionid)
        me = cl.account_info()
    except LoginRequired:
        print("ERROR: sessionid rejected by Instagram — export a fresh "
              "cookie from a signed-in browser and retry.",
              file=sys.stderr)
        sys.exit(1)
    _check_identity(me)
    _save_session(cl, me)


def login_with_password():
    username = os.environ.get("CLIPFORGE_IG_USER") or \
        os.environ.get("CLIPSDAILY_IG_USER") or IG_USERNAME
    password = os.environ.get("CLIPFORGE_IG_PASS") or \
        os.environ.get("CLIPSDAILY_IG_PASS")
    if not password:
        password = getpass.getpass(f"Instagram password for @{username}: ")
    from instagrapi import Client
    from instagrapi.exceptions import TwoFactorRequired

    cl = Client()
    code = ""
    try:
        cl.login(username, password)
    except TwoFactorRequired:
        code = input("Two-factor code from the Instagram app/SMS: ").strip()
        cl.login(username, password, verification_code=code)
    me = cl.account_info()
    _check_identity(me)
    _save_session(cl, me)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="clipforge auth instagram",
        description="Create the Instagram session file (.auth/"
                    "instagram_session.json).")
    ap.add_argument("--cookies", metavar="COOKIES.TXT",
                    help="Netscape-format cookie export from a browser "
                         "signed in to the account (recommended)")
    args = ap.parse_args(argv)
    if args.cookies:
        login_with_cookies(args.cookies)
    else:
        login_with_password()


if __name__ == "__main__":
    main()
