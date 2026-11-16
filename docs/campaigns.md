# Campaigns — Content Rewards rules, joining, submitting

## The one rule that governs everything

**One strike and you're out.** Botting views, AI-generated
content, or gaming the system removes the account from every
Reach/Content Rewards campaign permanently. A single bad
submission is enough. That is why the eligibility gate exists
and why it is never bypassed.

## Campaign economics (Content Rewards, Nov 15, 2026)

- Rate ~$1 per 1,000 views (10% platform fee already netted in
  the $1/1K figure the watcher uses; other platforms differ —
  Clipster ~$0.95/1K net, Vyro ~$2/1K, Promote.fun ~$2.50/1K
  in USDC).
- Minimum View Requirement (MVR): 10,000 views. Payouts start
  only once a video hits MVR and is approved.
- Per clip per platform: min $10 (at 10,000 views), max $500
  (at 500,000 views). Same clip on all 3 platforms: max $1,500.
- Under 10,000 views = $0. Submit clip links **within 30
  minutes of posting** — the window only starts when the clip
  is actually live, never before.
- A job is complete only when the dashboard shows Pending WITH
  a submission ID. Never mark submitted without that ID.

## The worked example: Expedia x IShowSpeed (Nov 15, 2026)

- Campaign: $8,000 Expedia x IShowSpeed, $1/1K, joined Nov 15
  (verified green Joined badge).
- Eligible footage ONLY: IShowSpeed's Expedia segment from his
  stream on 11.6.26 (Twitch VOD 2921253522). Any footage from
  2:56:29 (10,589s) until the end of that stream is acceptable.
  Content from other streams/videos/posts WILL BE REJECTED.
  Exclude range: the stream-ending spikes (11,030–11,049s) have
  no Expedia content.
- What the segment is: Speed calls two fans live and gives away
  Expedia travel prizes. Hudson (New Jersey) wins a trip to
  Japan. Anthony (New York) wins $10,000 from Expedia to travel
  to Hong Kong.
- Rules: videos MUST mention "Expedia" and Expedia must be a
  major focus; caption/text overlay must mention the destination
  accurately; captions must use hashtag `#IShowSpeed`; audience
  at least 50% native English-speaking countries; participating
  accounts only in the streamer and/or travel niche; Expedia logo
  encouraged but not required; no other logos of any kind; no
  negative portrayal of IShowSpeed or Expedia; no "hate farming";
  no manipulated views/engagement; no NSFW accounts.
- Status Nov 15: 5 of 6 possible submissions Pending (Japan +
  Hong Kong on YouTube and Instagram, Japan on TikTok). The Hong
  Kong TikTok was blocked by the TikTok session issue (see
  `docs/TIKTOK.md`) and was posted manually from a phone on
  Nov 15, 22:53 — submit it within 30 min of that post.

## Join rules (campaign_watcher.py — ALL 7 must hold)

1. Active. 2. Budget remaining. 3. Rate >= $1/1K. 4. No
application required. 5. A watchlist streamer named in the
title/description. 6. An explicit footage window that parses
("2:56:29 until the end" → start 10589s, end None). 7. Usable
platforms. NEVER join a campaign whose window cannot be stated
exactly. Joining is not done by the watcher: it writes
`join_requests.json`; a human/browser step clicks Join, verifies
the green Joined badge, and appends to `join_results.json`,
which the watcher reconciles next run.

## The gate (eligibility_gate.py — before queueing AND submitting)

Three checks; ANY failure or unverifiable check = BLOCKED,
never posted, never submitted. Borderline = blocked.

- (a) Window: clip's VOD id + full [start,end] range inside
  the campaign's stated window, including exclude_ranges.
- (b) Caption: every posted caption (YT/TikTok/IG) contains all
  required mentions + hashtag + destination.
- (c) Full-frame: band-energy profile (see `docs/CAPTIONS.md`).

Exit 0 = PASS, 2 = BLOCKED (JSON verdict on stdout).
`campaign_cut.py` runs the gate in-script and writes entries
to `campaign_queue.json` (never `queue.json`) with status
pending/blocked + the verdict. `auto_submit.py --scan`
re-gates each campaign clip at write time. Legacy clips posted
before the full-frame rule are grandfathered (already posted +
submitted, no action); the gate governs NEW queueing/submission.

## Submit flow (auto_submit.py + operator cron)

`auto_submit.py --scan` reads `queue.json` +
`campaign_queue.json` + ig-outbox meta, re-gates each campaign
clip, and writes `submit-outbox/<clip_id>-<platform>.json`
(status pending). Idempotent: a submitted job is never
rewritten; a pending job is never duplicated. Jobs expire 30
min after posted_at. `--list-pending` prints pure JSON on
stdout. `--mark-submitted <job_id> --submission-id <id>` /
`--mark-failed` are for the operator after the browser submit.
Operator side: `scripts/submit_cron.sh` (every 15 min) +
`scripts/submit_mark.sh` + `docs/SUBMIT_CRON_BODY.md`.
The browser submit itself is human-operated (Content Rewards
needs a logged-in browser session).

## Earnings (earnings.py)

Consumes `earnings_dump.json` (operator browser dump of the
submissions dashboard — see `docs/earnings_dump_spec.md`),
merges per-clip views/status/payout + campaign totals into
`earnings.json`, prints a one-line summary. Pending = projected,
never realized. Daily run: `clipsdaily earnings --update &&
clipsdaily earnings --summary`.

## Watcher limits

The watcher parses undocumented Next.js page HTML. If Content
Rewards changes its discover page structure, parsing returns 0
records and it fails closed (no joins) — but someone must
notice the 0-parse and fix the parser. Vyro has no public
campaign data; it is consumed from an operator browser dump
(`vyro_dump.json`) or skipped. Never pay to join any platform.
