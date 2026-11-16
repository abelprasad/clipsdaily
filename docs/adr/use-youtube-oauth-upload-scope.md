# Use YouTube OAuth upload scope

## Status

Accepted — 2026-11-15

## Context

YouTube uploads needed API auth for the Clips Daily channel (@Clippedaily31). Abel walked through the Google Cloud setup step by step: project `clipsdaily`, YouTube Data API v3 enabled, an OAuth consent screen (External, app name Clips Daily), and a Desktop-app OAuth client. The first consent attempt hit 403 access_denied (testing mode, "has not completed the Google verification process"); the fix was confirming clippedaily31@gmail.com was already listed as a test user, then re-opening the approval link. The token was exchanged with a manual-code flow (`auth_youtube_manual.py`).

## Decision

YouTube uploads use the OAuth Desktop-app token with `youtube.upload` + `youtube.readonly` scopes only. The token lives in `.auth/youtube_token.json` (mode 0600), the client secrets in `.auth/youtube_client_secrets.json` (mode 0600). Neither is ever in git.

## Consequences

- Uploads work; `poster.py --check` reports youtube OK, authenticated as channel 'Clips Daily' (@Clippedaily31).
- API delete returns 403 (insufficient authentication scopes), so the token cannot delete videos. The two flawed Shorts from the morning (UTEfAl0SGt0 and mqp_YZ-Eah8, broken burned-in captions) stay live until Abel deletes them from YouTube Studio, or until he grants wider token access later (he said he will) and the OAuth flow is re-run with the full `youtube` scope.
- A wider scope is a deliberate, human-approved step, not something to slip in silently: delete access on the channel is powerful and Abel decides when to grant it.
