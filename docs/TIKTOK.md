# TikTok — session notes, blocked status, known bugs

## Status (Nov 15, 2026): auto-posting blocked, account fine

TikTok auto-posting is blocked session-wide. The Japan 70s clip
posted fine at 19:33 EST Nov 15 via the fixed poster
(`post_tiktok_fixed.py`). Every automated submit after ~20:25
failed. A manual post from a phone worked the same evening
(Nov 15, 22:53), so the account itself is fine — the automation
session is throttled. Do not hammer retries; it risks deepening
the throttle.

## Symptoms

- Upload + processing succeed, the content-checks modal is
  dismissed, the description is set, the Post button is clicked —
  then no confirmation within 120s, and the Studio content page
  still shows only the older videos. The video never appears.
- One attempt returned TikTok's own error directly:
  "Something went wrong — Please try again."
- The block is account-wide, not clip-specific: a diagnostic
  post of a different clip failed identically.
- Failure pattern across attempts (20:25, 20:32, ~20:52, ~21:06,
  21:34, 22:00, 22:30): same silent drop every time.

## What was ruled out

- **Session expiry: no.** Cookies (`.auth/tiktok_cookies.txt`,
  exported Nov 15, 13:34) checked Nov 15, 22:50: `sessionid`
  and `sid_tt` are valid until 2027-05-14. (`tt_csrf_token`
  shows epoch 0 because it is a session cookie, not a real
  expiry.)
- **Indra load: no.** Load hit 25–30 during the evening (runner
  + hourly builder + VOD batch + automation build running at
  once) and TikTok headless rendering breaks first under load,
  but load was 0.41 by 22:50 and the 22:00/22:30 attempts still
  failed.
- **Wrong file / caption: no.** The files are verified 70s/90s
  full-frame clips with the correct trimmed captions.

## Most likely cause

TikTok flagged the automation session after the burst of
automated submits (one success at 19:33, then ~7 submit
attempts in ~2 hours, plus the earlier failed attempts from
the first posting round). TikTok's anti-automation silently
drops submits from a flagged session instead of returning a
clear error. The fix is time, a fresh session (re-export
cookies from the operator's browser), or both.

## What unblocks it

1. Wait it out (throttles usually lift in hours to a day).
2. Fresh cookie export from the operator's browser (see
   `docs/AUTH.md`) and one test post.
3. Diagnostic that settles account-vs-session: one manual post
   from a phone. If it works, the account is fine and it is the
   automation session (done Nov 15, 22:53 — it worked).

## The fixed poster (post_tiktok_fixed.py)

Stock `tiktok-uploader` 1.2.0 fails on the current TikTok
Studio DOM: the "Turn on automatic content checks?" TUXModal
overlay intercepts the Post click, and the library's fallback
selector (`.TUXButton--primary`) is null (buttons are now
`Button__root--type-primary`). The fixed poster dismisses the
modal via Cancel, removes react-joyride guided-tour overlay
nodes, JS-clicks `button[data-e2e='post_video_button']`,
verifies the caption landed, and verifies the video actually
appears via the Studio content page (the public profile grid
does not render headless). Never infer success from a missing
Post button — verify via Studio. It worked at 19:33 with this
code, so the code is proven; the current failures are the
session throttle, not the poster.

## Open bug: Playwright sync/async error (Nov 15, 22:00)

The hourly poster's TikTok attempt at 22:00 failed with a NEW
error, different from the silent drops:

```
It looks like you are using Playwright Sync API inside the asyncio loop.
Please use the Async API instead.
```

`post_tiktok_fixed.py:post_file` creates `TikTokUploader`
(sync API) while the hourly poster process has a running
asyncio event loop. The 22:30 attempt then gave up
("tiktok retries exhausted"). This is a code bug, separate
from the TikTok throttle. Likely fixes: call the TikTok post
from a subprocess (isolating it from the loop), or switch the
poster to the async Playwright API. Not yet fixed. Do not
retry TikTok in a loop until both the throttle and this bug
are addressed.

## TikTok dead-button lesson

TikTok's pages render in cloud browsers but their JavaScript
does not run — every control is inert. Automation cannot
complete any TikTok OAuth authorization in a cloud browser.
The working route is always the operator clicking Continue
in their own browser. Same for the cookie export: it must
come from the operator's signed-in browser session.
