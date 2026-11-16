"""One-time YouTube OAuth for the Clips Daily channel (@Clippedaily31).

Prerequisites (Abel, in Google Cloud Console as clippedaily31@gmail.com):
  1. Create a project (any name, e.g. "clipsdaily").
  2. Enable the YouTube Data API v3 for it.
  3. Create an OAuth client ID of type "Desktop app".
  4. Download the client JSON and save it on indra as
     /home/abel/clipsdaily/.auth/youtube_client_secrets.json (mode 0600).

Then run this from indra as abel, with an SSH tunnel so Google's
localhost redirect reaches this machine:

    ssh -L 8080:localhost:8080 friday@100.78.151.90
    cd /home/abel/clipsdaily && python3 auth_youtube.py

It prints a Google URL: open it in a browser (signed in as
clippedaily31@gmail.com), approve YouTube upload access, and the
browser redirects to localhost:8080, which the tunnel forwards to
indra. The token is saved to .auth/youtube_token.json (mode 0600).

After this succeeds, verify with:  python3 poster.py --check
"""
import os
import sys
from pathlib import Path

from .paths import runtime_home
HERE = runtime_home()
AUTH_DIR = HERE / ".auth"
SECRETS_FILE = AUTH_DIR / "youtube_client_secrets.json"
TOKEN_FILE = AUTH_DIR / "youtube_token.json"

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def main():
    if not SECRETS_FILE.exists():
        print(f"ERROR: {SECRETS_FILE} not found.\n"
              "Create a Desktop-app OAuth client in Google Cloud Console\n"
              "(project with YouTube Data API v3 enabled, signed in as\n"
              "clippedaily31@gmail.com) and save its JSON there first.",
              file=sys.stderr)
        sys.exit(1)
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(str(SECRETS_FILE), SCOPES,
                                         redirect_uri="http://localhost:8080/")
    auth_url, _ = flow.authorization_url(prompt="consent")
    print("\nOpen this URL in a browser (as clippedaily31@gmail.com):\n")
    print(auth_url)
    print("\nWaiting for the localhost redirect "
          "(run this with ssh -L 8080:localhost:8080)...")
    flow.run_local_server(port=8080, open_browser=False)
    creds = flow.credentials
    AUTH_DIR.mkdir(mode=0o700, exist_ok=True)
    os.chmod(AUTH_DIR, 0o700)
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    os.chmod(TOKEN_FILE, 0o600)
    print(f"OK: token saved to {TOKEN_FILE} (mode 0600)")
    print("Verify with: python3 poster.py --check")


if __name__ == "__main__":
    main()
