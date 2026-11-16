# Auth — how to recreate each credential

All auth files live in `.auth/` (mode 0700). That directory is
gitignored and is NEVER copied off the host. Recreate each auth
on the machine that will run the pipeline; nothing here works
without at least one platform wired.

Check status any time (read-only, posts nothing):

```bash
clipsdaily auth check
```

## Files in .auth/

| File | What it is | Recreate with |
|---|---|---|
| `youtube_client_secrets.json` (0600) | Google OAuth Desktop-app client for the Clips Daily Google account | Google Cloud Console (below) |
| `youtube_token.json` (0600) | YouTube OAuth token (upload + readonly scopes) | `auth_youtube.py` / `auth_youtube_manual.py` |
| `tiktok_cookies.txt` (0600) | TikTok browser cookies, Netscape format, must contain `sessionid` | Export from operator's browser |
| `instagram_session.json` | instagrapi session (does NOT exist on the live host — see Instagram) | `auth_instagram.py` (currently fails; live route is instagram-cli) |

## YouTube (@Clippedaily31)

1. Google Cloud Console: create project `clipsdaily`, enable
   YouTube Data API v3.
2. OAuth consent screen: External, app name Clips Daily,
   contact clippedaily31@gmail.com. Add clippedaily31@gmail.com
   as a test user (testing mode blocks anyone not listed — the
   first consent attempt fails with 403 access_denied until the
   test user is added).
3. Create an OAuth client (Desktop app), download the client
   JSON to `.auth/youtube_client_secrets.json` (0600).
4. Run `auth_youtube.py` (or `auth_youtube_manual.py`, which
   uses a manual-code exchange: it prints the auth URL, the
   operator approves in their browser, pastes the redirect URL
   back, the script exchanges the code). If the OAuth flow uses
   a localhost redirect, run with
   `ssh -L 8080:localhost:8080` so the redirect reaches the host.
5. Token saves to `.auth/youtube_token.json`. Verify with
   `poster.py --check` (should report authenticated as
   channel 'Clips Daily').

**Delete-scope limitation:** the token has only
`youtube.upload` + `youtube.readonly` scopes. API delete
returns 403 insufficient authentication scopes. To delete
videos via the API, re-run OAuth with the full `youtube`
scope (operator grants it in their browser). Until then,
delete from YouTube Studio by hand.

## TikTok (@clips.daily548)

1. Sign in to TikTok in the operator's browser as Clips Daily
   (Google sign-in works; the saved password was rejected by
   TikTok — do not retry it).
2. Export cookies (Netscape format) while signed in, filter to
   TikTok lines, save as `.auth/tiktok_cookies.txt` (0600).
   It must contain a `sessionid` cookie.
3. Verify format with `auth_tiktok.py` (checks sessionid is
   present; the first real upload proves the session end to end).
4. Sessions expire: if a post fails on auth, re-export.
   See `docs/TIKTOK.md` for the current blocked status — the
   cookies are valid to May 2027; the block is a throttle, not
   expiry.

## Instagram (@clippedaily31)

Two routes exist. Only the second is live.

- **instagrapi (in-repo, `poster.py:post_instagram`):**
  `auth_instagram.py` logs in with a password from the
  environment only (`CLIPSDAILY_IG_PASS`, never stored) and
  writes `.auth/instagram_session.json`. Currently FAILS:
  instagrapi 3.1.0 errors before 2FA
  (`password_publickeys` gets no
  `ig-set-password-encryption-key-id` header). `poster.py`
  reports Instagram NOT READY and `config.yaml` keeps
  instagram false. Fix or replace this route before using it.
- **instagram-cli (live route, operator machine only):** the
  CLI runs on the operator's machine, not the pipeline host
  (it needs glibc 2.39 + a local privsep socket that only
  exists there). It posts via the Meta Accounts Center link —
  no password needed:
  `instagram-cli post-feed --account-id 17841427153900705
  --file <video> --cover <cover> --caption <caption>`.
  The hourly poster stages Reels into `ig-outbox/<clip-id>/`
  (clip30.mp4 + caption.txt + meta.json, status "staged");
  `scripts/ig-post-staged.sh` (every 30 min, :05/:35) posts
  the most recently staged one and flips it to "posted".
  Post ONLY to @clippedaily31, never a personal account.

## General rules

- Never paste a password, token, or cookie into chat, a file
  outside `.auth/`, or a log. Passwords come from the
  environment or the operator's browser, transiently.
- Re-auths cannot be automated: TikTok cookies and the YouTube
  token expire, and only the operator can re-approve them in
  their browser.
- The YouTube OAuth client JSON for the live project is tied
  to the Clips Daily Google account; a new deployment needs its
  own GCP project + client.
