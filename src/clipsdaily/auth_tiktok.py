"""TikTok session check + cookie-export instructions for @clips.daily548.

TikTok has no upload API key for this account, so poster.py uploads
through the web session, using a browser-cookies file:

    /home/abel/clipsdaily/.auth/tiktok_cookies.txt  (Netscape format)

How Abel exports it (in his own browser, signed in as Clips Daily):
  1. Install a cookie-export extension (e.g. "Get cookies.txt LOCALLY")
     or use devtools: Application > Cookies > tiktok.com.
  2. While signed in to tiktok.com as @clips.daily548, export ALL
     cookies for tiktok.com to a cookies.txt file (Netscape format).
  3. Send the file to indra, e.g. scp it to /tmp, then:
         sudo -n -u abel bash -c "mkdir -p /home/abel/clipsdaily/.auth
         && cp /tmp/tiktok_cookies.txt /home/abel/clipsdaily/.auth/
         && chmod 700 /home/abel/clipsdaily/.auth
         && chmod 600 /home/abel/clipsdaily/.auth/tiktok_cookies.txt"
  4. Verify with:  python3 poster.py --check

The file must contain a `sessionid` cookie. Sessions expire: if a post
fails with an auth error, re-export the cookies. Never post the cookie
values in chat, and never store them outside .auth/.

This script only validates the file's format; it posts nothing.
"""
import sys
from pathlib import Path

from .paths import runtime_home
HERE = runtime_home()
COOKIES_FILE = HERE / ".auth" / "tiktok_cookies.txt"


def main():
    if not COOKIES_FILE.exists():
        print(f"NOT READY: {COOKIES_FILE} does not exist.\n"
              "Export cookies from a browser signed in as @clips.daily548\n"
              "(see the instructions at the top of this file).")
        sys.exit(1)
    text = COOKIES_FILE.read_text()
    has_sessionid = "sessionid" in text
    lines = [ln for ln in text.splitlines()
             if ln.strip() and not ln.startswith("#")]
    print(f"cookies file: {COOKIES_FILE}")
    print(f"cookie lines: {len(lines)}")
    print(f"sessionid present: {has_sessionid}")
    if not has_sessionid:
        print("NOT READY: no sessionid — re-export while signed in to "
              "tiktok.com as @clips.daily548.")
        sys.exit(1)
    print("READY (format): sessionid present. The first real upload will "
          "prove the session is still accepted by TikTok.")


if __name__ == "__main__":
    main()
