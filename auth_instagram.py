"""One-time Instagram login for @clippedaily31.

Creates .auth/instagram_session.json (mode 0600) so poster.py can post
Reels without a password on disk. Run once, from indra, as abel:

    cd /home/abel/clipsdaily
    CLIPSDAILY_IG_USER=clippedaily31 CLIPSDAILY_IG_PASS='<password>' \\
        python3 auth_instagram.py

The password is read from the environment only and is never written to
disk, to a log, or to the session file (the session file holds device
ids + the sessionid cookie only). If Instagram asks for a two-factor
code, the script prompts for it on stdin. If the login needs approval
in the Instagram app, approve it there and re-run.

After this succeeds, verify with:  python3 poster.py --check
"""
import getpass
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTH_DIR = HERE / ".auth"
SESSION_FILE = AUTH_DIR / "instagram_session.json"

IG_USERNAME = "clippedaily31"
IG_USER_ID = 27125641130


def main():
    username = os.environ.get("CLIPSDAILY_IG_USER", IG_USERNAME)
    password = os.environ.get("CLIPSDAILY_IG_PASS")
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
    if int(me.pk) != IG_USER_ID:
        print(f"ERROR: logged in as @{me.username} (id {me.pk}), "
              f"expected @{IG_USERNAME} ({IG_USER_ID}). Aborting — "
              "session NOT saved.", file=sys.stderr)
        sys.exit(1)
    AUTH_DIR.mkdir(mode=0o700, exist_ok=True)
    os.chmod(AUTH_DIR, 0o700)
    cl.dump_settings(str(SESSION_FILE))
    os.chmod(SESSION_FILE, 0o600)
    print(f"OK: session saved for @{me.username} "
          f"({SESSION_FILE}, mode 0600)")
    print("Verify with: python3 poster.py --check")


if __name__ == "__main__":
    main()
