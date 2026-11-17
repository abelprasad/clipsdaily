import os
from pathlib import Path

from .paths import runtime_home
AUTH_DIR = runtime_home() / ".auth"
SECRETS_FILE = AUTH_DIR / "youtube_client_secrets.json"
TOKEN_FILE = AUTH_DIR / "youtube_token.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
from google_auth_oauthlib.flow import Flow
flow = Flow.from_client_secrets_file(str(SECRETS_FILE), SCOPES,
                                     redirect_uri="http://localhost:8080/")
auth_url, _ = flow.authorization_url(prompt="consent")
print("AUTH_URL:" + auth_url, flush=True)
print("PASTE_CODE_NOW", flush=True)
line = input().strip()
code = line.split("code=")[-1].split("&")[0] if "code=" in line else line
flow.fetch_token(code=code)
creds = flow.credentials
with open(TOKEN_FILE, "w") as f:
    f.write(creds.to_json())
os.chmod(TOKEN_FILE, 0o600)
print("OK: token saved to " + str(TOKEN_FILE), flush=True)
