# Post Instagram via operator CLI

## Status

Accepted — 2026-11-15

## Context

Instagram posting needed a route that works without a password. The instagrapi 3.1.0 login to @clippedaily31 failed inside the library: `password_publickeys` got no `ig-set-password-encryption-key-id` header, so login never reached 2FA. The account itself is fine: it is linked via Meta Accounts Center, and the Instagram app session on the operator VM can post.

## Decision

Instagram Reels post via `instagram-cli` from the operator VM (the Muse VM), using the Accounts Center link, no password: `instagram-cli post-feed --account-id 17841427153900705 --file <video> --cover <cover> --caption <caption>`. The CLI needs glibc 2.39 plus a local privsep socket that only exists on the operator machine, so it runs there and not on indra. The runner's instagram path stays off (`config.yaml` instagram is false); IG posts go through the `ig-outbox/` staging directory plus a 30-minute operator cron that posts staged clips.

## Consequences

- IG posting cannot run on indra. Any agent working on the pipeline must keep the IG leg on the operator machine or fix the instagrapi route.
- A Claude Code user must run the IG leg on their own operator machine with their own SSH route to indra, or fix `auth_instagram.py`.
- Every `instagram-cli` post triggers a runtime approval card on the Instagram connector (content.publish). Abel has given standing permission to post without per-post approval, but the card itself is a system prompt, not Friday asking; if it ever offers an always-allow option, tapping it once stops the cards for good.
- Posts go ONLY to @clippedaily31, never to Abel's personal account (@abelprasad_), which is linked separately.
