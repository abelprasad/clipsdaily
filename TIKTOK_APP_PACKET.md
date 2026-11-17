# TikTok developer app — registration packet for Clips Daily

Copy-paste values for the form on https://developers.tiktok.com. Fill it
in one pass, no decisions left. The only steps that need me are signing
in and submitting — everything below is already decided.

## Sign-in (my step)

- Sign in at https://developers.tiktok.com **as @clips.daily548 via
  Google (clippedaily31@gmail.com)**.
- Do NOT use the saved tiktok.com password — it was rejected before and
  must never be retried. Google sign-in is the working one.

## App (My apps → Create an app)

| Field | Exact value |
|---|---|
| App name | `Clips Daily` |
| App description | `Personal automation for the owner's own TikTok account. Clips Daily watches the owner's own live streams on Twitch and Kick, cuts short highlight clips, and posts them to the owner's own TikTok account. It posts only the owner's own content, only to the owner's own account.` |
| Website URL | `https://abelprasad.dev/clipsdaily/` |
| Privacy Policy URL | `https://abelprasad.dev/clipsdaily/privacy.html` |
| Terms of Service URL | `https://abelprasad.dev/clipsdaily/terms.html` |
| Redirect URI | `http://localhost:8080/` (exact, including the trailing slash) |

The three URLs are live static pages on abelprasad.dev (portfolio commit
d0d84b6, Nov 16, 2026, verified returning 200 with the full policy text).

## Product and scopes

- Product: **Content Posting API** (add it under the app's Products; this
  is separate from the basic Login Kit).
- Inside the Content Posting API product settings, turn on **Direct Post**.
- Request exactly these three scopes, no more:
  - `user.info.basic` — read the creator profile (needed before every Direct Post).
  - `video.upload` — upload drafts to the creator inbox.
  - `video.publish` — Direct Post to the profile.
- Do not add `user.info.profile`, `user.info.stats`, or `video.list`.
  Extra scopes slow the review down.

## Submit, then the audit (both are my steps)

1. **Submit for app review.** Attach the demo video (see below). Expect
   days to about two weeks; TikTok emails the result either way.
2. **Separately request the Content Posting API audit.** This is a second
   review on top of app review: TikTok checks the posting flow/UI. Until
   it passes, every Direct Post is forced private (`SELF_ONLY`) and the
   account must be private — do not flip @clips.daily548 to private
   lightly, it is public today. Draft mode does not need this audit.

## Demo video (record later — not now)

The review wants at least one demo video of the full flow (up to 50 MB).
It can only be recorded **after** the app exists and OAuth works, so it
is a later step, not part of registration. Record once Part 2–3 of
TIKTOK_API_SETUP.md work:

1. Open the authorize URL from `python3 tiktok_api.py --auth-url` and
   authorize as @clips.daily548.
2. Run a test Direct Post of a real 60–90s clip
   (`--post-direct ... --privacy-level SELF_ONLY` while unaudited).
3. Show the poll output reaching `PUBLISH_COMPLETE` and open the video
   URL on the phone to confirm it is really there.
4. If Direct Post is blocked before the audit, record the draft flow
   instead (`--post-draft`, then publish from the TikTok app inbox).

## ⚠️ Audit risk — do not oversell this

TikTok's docs say **apps for private or personal use are not approved**.
This pipeline serves exactly one account (@clips.daily548), so the
audit may refuse Direct Post and no code can work around that. If it
refuses, the fallbacks are already built: draft mode (free, no audit,
max 5 pending drafts/24h, I tap publish on my phone) or the
cookie path, or a paid scheduler. Second risk: the
`content_preview_confirmed` / `express_consent_given` flags rest on
My standing approval plus the eligibility gate, not a human
reviewing each clip — an auditor may push back on that. Full detail in
TIKTOK_API_SETUP.md ("READ THIS FIRST").

## After the app is approved

Follow TIKTOK_API_SETUP.md Part 2 (authorize @clips.daily548 on indra),
Part 3 (first live test), Part 4 (flip `tiktok_api: true` in
config.yaml). Token lifecycle is automatic after that.
