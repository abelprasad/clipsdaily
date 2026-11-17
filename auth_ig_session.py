#!/usr/bin/env python3
"""One-time Instagram session import for clipsdaily (@clippedaily31).

Creates .auth/instagram_session.json (mode 0600) so ig_post_staged.py
can post Reels without a password on disk. Session-cookie import ONLY —
instagrapi password login is broken against Instagram's login endpoint
and is never attempted here.

Usage (run once, from indra, as abel):

    python3 auth_ig_session.py /path/to/cookies.txt

where cookies.txt is a Netscape-format cookie export from a browser
signed in to @clippedaily31 (extensions like "Get cookies.txt" work).
Only the sessionid cookie is read; the cookies file is never copied,
moved, or stored, and the sessionid is never printed or logged.
The session is verified with a read-only account_info() call (must be
@clippedaily31, id 27125641130) before anything is saved.

After this succeeds, verify with:  python3 ig_post_staged.py --check
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTH_DIR = HERE / ".auth"
SESSION_FILE = AUTH_DIR / "instagram_session.json"

IG_USERNAME = "clippedaily31"
IG_USER_ID = 27125641130


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
        print("ERROR: no instagram.com sessionid in %s — export cookies "
              "from a browser signed in to the account." % cookies_file,
              file=sys.stderr)
        sys.exit(1)
    return sessionid


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print("usage: python3 auth_ig_session.py /path/to/cookies.txt",
              file=sys.stderr)
        sys.exit(2)
    cookies_file = argv[0]
    if not Path(cookies_file).is_file():
        print("ERROR: cookies file not found: %s" % cookies_file,
              file=sys.stderr)
        sys.exit(1)

    from instagrapi import Client
    from instagrapi.exceptions import LoginRequired

    cl = Client()
    sessionid = _read_sessionid(cookies_file)
    try:
        cl.login_by_sessionid(sessionid)
        me = cl.account_info()
    except LoginRequired:
        print("ERROR: sessionid rejected by Instagram — export a fresh "
              "cookie from a signed-in browser and retry.", file=sys.stderr)
        sys.exit(1)
    if me.username.lower() != IG_USERNAME.lower() or int(me.pk) != IG_USER_ID:
        print("ERROR: logged in as @%s (id %s), expected @%s (%s). "
              "Aborting — session NOT saved."
              % (me.username, me.pk, IG_USERNAME, IG_USER_ID),
              file=sys.stderr)
        sys.exit(1)

    AUTH_DIR.mkdir(mode=0o700, exist_ok=True)
    import os
    os.chmod(AUTH_DIR, 0o700)
    cl.dump_settings(str(SESSION_FILE))
    os.chmod(SESSION_FILE, 0o600)
    print("OK: session saved for @%s (%s, mode 0600)"
          % (me.username, SESSION_FILE))
    print("Verify with: python3 ig_post_staged.py --check")


if __name__ == "__main__":
    main()
