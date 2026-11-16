# Post TikTok via cookie export

## Status

Accepted — 2026-11-15

## Context

TikTok posting needed a sign-in route that automation can actually use. The saved Vault TikTok password was rejected by TikTok, and Abel signed in with Google as Clips Daily instead. TikTok's pages render in the cloud browser but their JavaScript does not run, so automation cannot complete any TikTok OAuth authorization there; every control on the page is inert.

## Decision

TikTok posts via `tiktok-uploader` plus a Netscape cookies file (`.auth/tiktok_cookies.txt`) exported from Abel's browser. The cookie file is the working sign-in route. Sessions expire, so if a post fails on auth, re-export the cookies from Abel's browser and replace the file.

## Consequences

- The cookies file is mode 0600, owned by abel, and never in git (see `keep-live-state-out-of-git.md`).
- Nov 15 session block: the Japan 70s clip posted fine at 19:33, then every automation submit after 20:25 was silently dropped (upload and processing went through, the Post click registered, but no confirmation appeared within 120s and the video never showed in Studio), while a manual phone post worked at ~22:53. The cookies were verified valid to May 2027, so the block is a session throttle, not expiry. The unblock path is time or a fresh cookie export.
- The TikTok poster also carries a known bug: the 22:00 attempt failed with "It looks like you are using Playwright Sync API inside the asyncio loop. Please use the Async API instead." The fixed poster (`post_tiktok_fixed.py`) dismisses the "Turn on automatic content checks?" modal and removes the guided-tour overlay before clicking Post; that logic must be wired into `poster.py` before relying on runner TikTok auto-posts.
- Further retries during a block risk deepening the throttle; stop and diagnose instead.
