# TikTok Content Posting API — setup checklist for Abel

**Status: code is built, tested with mocks, and wired in. Nothing is
live yet.** The TikTok leg still runs on the Playwright cookie session
until you finish the steps below and flip one flag. No post has been
made through the API, and no TikTok account or app has been created
by anyone but you.

## What this replaces, and why

Since Nov 15 the automated browser session is flagged: TikTok Studio
lets it log in, upload, and set a caption, then answers "Something
went wrong — Please try again" at the Post click. Your phone posts
fine, so the account is healthy — the *automation session* is what's
blocked. The official Content Posting API posts server-to-server with
an OAuth token: no cookies, no browser, no Playwright. That is the
durable fix.

## ⚠️ READ THIS FIRST — the audit may refuse this pipeline

TikTok's own docs say **apps for private or personal use are not
approved**. This pipeline serves exactly one account,
@clips.daily548. There is a real chance TikTok refuses the Direct
Post audit on those grounds, and no code can work around that.

What that means in plain language:

- **If the audit passes:** Direct Post publishes straight to the
  public profile, up to ~15 posts/day, no cookies, no browser.
  This is the end state the code is built for.
- **If the audit refuses:** Direct Post stays locked. Two fallbacks,
  both already built into the same module:
  1. **Draft mode (free, no audit needed).** The API drops each clip
     into the creator inbox as a draft; you tap publish on your phone
     (max 5 pending drafts per 24h). Semi-automatic, not full — but
     it kills the cookie problem completely, and a draft never posts
     anything you didn't tap.
  2. **Keep the cookie session (free, works today, will flag again).**
     The Playwright path is still in the code as the fallback.
     It got flagged after one day of rapid-fire uploads; slower
     cadence + fresh cookies buys time, not a fix.
  3. **Paid scheduler (post2all $9/mo, Buffer, Later).** Instant,
     no review, no cookies — but monthly cost, a third party holds
     your posting, and the ~15/day cap still applies.

**Do not flip the account to private lightly.** Until the audit
passes, every Direct Post is forced private (`SELF_ONLY`) and the
account itself must be private. @clips.daily548 is public today;
making it private hides its existing public posts from non-followers.
Draft mode has no such requirement — the account stays public.

One more audit risk to know: the API requires the flags
`content_preview_confirmed` and `express_consent_given` on every
post. In this pipeline those rest on your standing approval ("post
without approval") plus the eligibility gate — **not** a human
reviewing each clip. An auditor may ask how a human previews each
post; the honest answer is that they don't. That is a second reason
the audit could push back.

## The website gap (read before you start the app)

App review requires **a working website with a Privacy Policy and
Terms of Service**. Clipsdaily has no website today.

Cheapest honest option: a single static page on a domain you already
own (e.g. a page under abelprasad.dev) with the product name, what it
does, a Privacy Policy, and Terms. Nothing to buy, nothing to build
beyond one page — but the app cannot be submitted until that page
exists and is reachable. **Do not create or buy anything for this
until you decide the audit is worth attempting; this is just the
recommendation.**

## Part 1 — Create the developer app (your step, ~20 min)

Do this in your own browser at https://developers.tiktok.com
(log in as Clips Daily / clippedaily31@gmail.com).

1. **Register the app.** My apps → Create an app. Name it something
   plain like `Clips Daily`. This creates a **client key** and
   **client secret** — treat the secret like a password.
2. **Add the Content Posting API product.** In the app's Products
   (or "Add products") section, add **Content Posting API**. This is
   separate from the basic Login Kit.
3. **Enable Direct Post.** Inside the Content Posting API product
   settings, turn on **Direct Post**. (Draft/inbox upload is the
   same product; Direct Post is the toggle that needs the audit.)
4. **Request the three scopes.** In the app's scopes/permissions,
   request exactly:
   - `user.info.basic` — read the creator profile (needed before
     every Direct Post; also how the code checks the token).
   - `video.upload` — upload drafts to the creator inbox.
   - `video.publish` — Direct Post to the profile.
   Approval of scopes is part of app review; you cannot post until
   they are granted.
5. **Set the redirect URI.** Add exactly this URI in the app's
   redirect-URI list:
   `http://localhost:8080/`
   The authorize step below runs a loopback server on your laptop on
   port 8080 and TikTok sends the code there. The URI must match
   character for character, including the trailing slash.
6. **Fill in the app details for review.** App description (what it
   does, in plain words), the website URL from the section above,
   Privacy Policy URL, Terms of Service URL, and **at least one demo
   video of the full flow, up to 50 MB** — record the authorize →
   upload → publish flow once it works (see Part 3) and attach it.
7. **Submit for app review.** Expect days to two weeks. You will get
   an email either way.
8. **Separately, request the Content Posting API audit.** This is a
   second review on top of app review: TikTok checks the posting
   screen/UI (they want to see the creator preview the post and
   consent — that's what the `content_preview_confirmed` /
   `express_consent_given` flags attest). **Until it passes, every
   Direct Post is private (`SELF_ONLY`) and the account must be
   private.** Draft mode does not need this audit.

## Part 2 — Authorize @clips.daily548 (your step, ~5 min)

On indra, in `/home/abel/clipsdaily/`:

1. Save the client credentials (from Part 1) as
   `.auth/tiktok_api_client.json`, mode 0600:
   ```json
   {"client_key": "aw...your key...",
    "client_secret": "your secret...",
    "redirect_uri": "http://localhost:8080/"}
   ```
   Never commit this file, never copy it off indra. (`.gitignore`
   already excludes `.auth/`.)
2. Print the authorize URL (nothing is posted, nothing is sent):
   ```
   python3 tiktok_api.py --auth-url
   ```
   Open the printed URL in your browser while signed in as
   @clips.daily548, click Authorize.
3. TikTok redirects to `http://localhost:8080/?code=...&state=...`.
   Your browser will show an error page — that is expected if no
   local server is listening. Copy the **whole redirect URL** from
   the address bar and run:
   ```
   python3 tiktok_api.py --exchange "http://localhost:8080/?code=...&state=..."
   ```
   The state value is verified against the one the module generated;
   a mismatch refuses the exchange.
4. Verify (read-only, posts nothing):
   ```
   python3 tiktok_api.py --check
   python3 poster.py --check
   ```
   Expect `API token valid for @clips.daily548` plus either
   `audited (public posting open)` or `UNAUDITED: Direct Posts will
   be SELF_ONLY only`.

### Token lifecycle (you don't have to manage this)

- Access token lasts **2 hours**; the module refreshes it
  automatically whenever it is within 10 minutes of expiring.
- The **refresh token rotates on every refresh** (the old one stops
  working immediately) and is valid **180 days**. The module saves
  the new one each time, so as long as the poster runs regularly the
  token stays alive. If the pipeline sits idle for 180+ days, repeat
  Part 2.
- Revoke any time from TikTok's authorized-apps page, or:
  `python3 tiktok_api.py --revoke`.

## Part 3 — Sandbox / first live test (your step, ~10 min)

There is no true sandbox for this API — the test is a real post.
While unaudited it is forced private, so a test post is invisible.

1. Make sure `tiktok_api: false` is still set in `config.yaml`
   (it is the default — the hourly poster keeps using cookies).
2. Post one throwaway clip by hand through the API:
   ```
   python3 tiktok_api.py --post-direct clips/<a-75s-clip>.mp4 \
       --caption "test — delete me" --privacy-level SELF_ONLY
   ```
   (Use any real 60–90s clip file. `--privacy-level` must be one
   of the account's options; the module prints them in `--check`.)
   While unaudited this is SELF_ONLY no matter what you pass.
3. Watch the poll output: `PROCESSING_UPLOAD` → `PUBLISH_COMPLETE`
   with a video URL. If it stays processing past 10 minutes, the
   command exits with the publish_id — reconcile it:
   ```
   python3 tiktok_api.py --reconcile <publish_id>
   ```
4. Open the URL on your phone to confirm the video is really there,
   then delete it from the TikTok app (the API token deliberately
   has no delete scope).
5. Record the flow for the audit demo video (Part 1, step 6).

If the test post fails with
`unaudited_client_can_only_post_to_private_accounts`, the account is
not private — switch it to private for the test, or use draft mode
instead (step 6), which needs no privacy change:
```
python3 tiktok_api.py --post-draft clips/<a-75s-clip>.mp4
```
then publish it from the TikTok app's inbox.

## Part 4 — Flip the pipeline over (your step, 1 min)

Only after Part 3 works **and** the audit has passed (or you have
consciously chosen draft mode):

1. In `/home/abel/clipsdaily/config.yaml`, set:
   ```yaml
   tiktok_api: true
   tiktok_api_mode: direct   # or: draft
   ```
   No tmux restart needed — the hourly poster re-reads `config.yaml`
   every slot.
2. Watch the next two slots in `logs/hourly-YYYYMMDD.log` for
   `tiktok API posted https://www.tiktok.com/...` (or `tiktok API
   draft staged ...` in draft mode).
3. To go back at any time: set `tiktok_api: false` again. The
   Playwright cookie path is untouched and takes over next slot.

## Caps — enforced in code, not just documented

- **Direct Post: ~15 posts/day per creator**, shared across apps.
  `tiktok_api.py` keeps a rolling-24h counter in
  `.auth/tiktok_api_usage.json`. The 16th attempt raises
  `TikTokCapReached` **before any TikTok call** and the hourly
  poster skips the slot without burning a retry. The poster tries
  2/hour, so it will hit this cap most days — that is expected, and
  the queue just waits. (The old Playwright path had no cap, which
  is part of why the session got flagged.)
- **Draft mode: max 5 pending shares/24h.** The module polls stored
  drafts first, so drafts you already published from your phone
  stop counting. The 6th draft raises `TikTokCapReached`.
- **Init rate limit:** 6 init calls/min per token (the poster makes
  at most 2/hour — nowhere near it).
- **Chunk upload:** 10 MB chunks (TikTok allows 5–64 MB, last chunk
  up to 128 MB); videos up to 4 GB, 3s–10 min.

## Files

| File | What it is |
|---|---|
| `tiktok_api.py` | The API module (OAuth, upload, poll, draft, caps, CLI). |
| `test_tiktok_api.py` | 24 mocked unit tests (no live calls). |
| `test_poster_tiktok_api.py` | 12 mocked wiring tests for poster/hourly_poster. |
| `poster.py` | `post_tiktok` routes to the API when `tiktok_api: true`, else cookies. |
| `hourly_poster.py` | Reconciles `PENDING:`/`DRAFT:` publish_ids instead of re-uploading; cap hits never burn a retry. |
| `config.yaml` | `tiktok_api: false`, `tiktok_api_mode: direct` (defaults). |
| `.auth/tiktok_api_client.json` | **You create this** (client key/secret). 0600, never committed. |
| `.auth/tiktok_api_token.json` | Created by `--exchange`. 0600, never committed. |
| `.auth/tiktok_api_usage.json` | Rolling cap counter. Local state, never committed. |

## What the code was tested on

- `python3 -m unittest test_tiktok_api` — **24/24 pass** locally
  and on indra (Python 3.10.12): token exchange + refresh rotation,
  creator info + privacy validation, Direct Post init/upload/poll
  happy path, FAILED status, unaudited-client errors, 401 retry,
  draft flow, both caps (15/day direct, 5 pending drafts), chunk
  math, PULL_FROM_URL.
- `python3 -m unittest test_poster_tiktok_api` — **12/12 pass** on
  indra: API on/off routing, 30s-fallback `allow_short`, PENDING /
  DRAFT markers (no retry burned, no re-upload), reconcile to live /
  still-pending / failed, cap-False handling.
- `python3 poster.py --check` — read-only; YouTube OK, TikTok
  correctly reports the cookie route until a client file exists.
- **Not tested (cannot be, without the app):** any live TikTok call.
  The first real post is Part 3 above.
