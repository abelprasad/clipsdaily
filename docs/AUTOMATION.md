> **Repo note (Nov 16, 2026):** status below is as of the Nov 15
> build. Since then: the three crons (auto-submit every 15 min,
> campaign-watch daily, earnings daily) were installed and are
> live; the Instagram 30-min cron is live; the hourly_poster ↔
> campaign_queue wiring is still pending approval; the Hong Kong
> TikTok 90s was posted manually from a phone on Nov 15, 22:53
> (the TikTok automation session is blocked — see
> `docs/TIKTOK.md`). The rest of this file is unchanged from the
> Nov 15 build.
>
# Clipsdaily monetization automation

Built Nov 15, 2026. Goal: the money loop runs with no human in it —
campaign discovery + join, campaign-mode cutting, auto-submit of clip
links within 30 min of posting, earnings tracking — behind a strict
eligibility gate, because Content Rewards bans an account from EVERY
campaign permanently for one bad submission ("one strike and you're out").

Status: **built + dry-run tested. NOT live.** The parent activates live
auto-join / auto-submit only after verifying this build. Nothing here
posts, joins, or submits anything on its own.

## The four pieces

### 1. campaign_watcher.py + campaigns.py + campaigns.json
Discovers campaigns on Content Rewards by fetching the discover page
(https://contentrewards.com/c/discover) as anonymous HTML and parsing
the Next.js RSC flight chunks (`self.__next_f.push([1,"..."])`) for
`{"campaign": {...}}` records. No API key, no login needed for discover.
Detail pages (status, payouts[] per platform, budget) are fetched ONLY
for records that pass the discover screen, to keep runs fast (~5s).

Join rules — ALL 7 must hold, else skipped/needs_review with a reason:
active, budget remaining, rate >= $1/1K, no application required,
a watchlist streamer named in title/description, an explicit footage
window that parses ("2:56:29 until the end" -> start 10589s, end None),
usable platforms. NEVER joins a campaign whose window cannot be
stated exactly. Joining itself is NOT done here: the watcher writes
join_requests.json; the parent's browser task clicks Join + verifies
the green Joined badge, then appends to join_results.json, which the
watcher reconciles next run (joined / needs_review).

Vyro has no public campaign data (homepage embeds none) — consumed
from a parent browser dump `vyro_dump.json` when present, else skipped.

Run: `clipsdaily campaign watch --check` (daily cron, indra).
Dry-run: `--dry-run` (fetch + evaluate, write nothing).
Logs: `campaigns.log`. State: `campaigns.json`, `join_requests.json`,
`join_results.json` (parent-written).

### 2. campaign_cut.py (campaign mode)
Given a joined campaign in campaigns.json (streamer, VOD id, eligible
window, destination/prize facts, curated moments), picks the moments
(or ranked in-window chat spikes), cuts 30s + TikTok variant in full
frame with the big hook caption via cutter.py, builds campaign
captions, runs the eligibility gate, and writes entries to
**campaign_queue.json (never queue.json)** with status pending/blocked
+ the gate verdict. `--dry-run` cuts to `campaign_work/dryrun_<clip_id>/`
and writes nothing. Reuses vod.py/chat.py/cutter.py — no duplication.
The TikTok variant is cut from the same window (70-90s); the 30s is
the YT/IG file.

Run: `clipsdaily campaign cut --campaign <id> [--dry-run] [--max-clips N]`.
Logs: `campaign_cut.log`.

### 3. eligibility_gate.py (HARD GATE — runs before queueing AND before submitting)
Three checks; ANY failure or unverifiable check = BLOCKED, never posted,
never submitted, logged for human review. Borderline = blocked.
- (a) Window: clip's VOD id + full [start,end] range inside the
  campaign's stated window (incl. exclude_ranges, e.g. stream-ending
  spikes with no campaign content).
- (b) Caption: every posted caption (YT/TikTok/IG) contains all required
  mentions + hashtag + destination.
- (c) Full-frame: 1080x1920 + blur-fill proven by band-energy profile.
  Samples frames at t=5/15/25s (after the 3s hook caption disappears),
  measures mean gradient energy in three bands: top rows 150-550,
  center rows 800-1200, bottom rows 1400-1800. PASS only if
  top < 0.4 AND bottom < 1.0 AND center > 2.0.
  Calibrated Nov 16, 2026 on real clips of the same Speed footage:
  true blur-fill scores top ~0.03-0.08, bottom ~0.5-0.6, center ~4.6;
  center-crop scores top ~1.6-2.3, bottom ~3.2-6.7, center ~2.5-4.7.
  (The first version used a top-vs-center ratio and FALSE-PASSED a
  center-crop clip, because the footage's dark top area is naturally
  low-energy. Absolute band energies are the fix; verified against
  both ground truths.)
- Exit 0 = PASS, 2 = BLOCKED (JSON verdict on stdout).

Run: `python -m clipsdaily.eligibility_gate --clip <entry.json> --campaign <id>`.

### 4. auto_submit.py + submit-outbox/
Outbox writer for the parent cron. `--scan` reads queue.json +
campaign_queue.json + ig-outbox meta, re-gates each campaign clip at
write time, and writes `submit-outbox/<clip_id>-<platform>.json`
(status pending) for posted clips. Idempotent: a submitted job is
never rewritten; a pending job is never duplicated. Jobs expire 30 min
after posted_at (the campaign submit window) and are marked expired,
never submitted late. `--list-pending` prints pending jobs as pure
JSON on stdout (logs go to stderr, so the parent cron can parse it).
`--mark-submitted <job_id> --submission-id <id>` / `--mark-failed`
are for the parent cron after the browser submit. A job is only
complete when the dashboard shows it Pending WITH a submission ID.

Parent side (local copies in ~/workspace/clipsdaily-build/):
`submit_cron.sh` (every 15 min: scan indra, print pending jobs),
`submit_mark.sh` (mark submitted/failed on indra),
`SUBMIT_CRON_BODY.md` (full install instructions).

### 5. earnings.py + earnings.json
Consumes `earnings_dump.json` (parent browser dump of the Content
Rewards submissions dashboard — see earnings_dump_spec.md), merges
into `earnings.json` (per-clip views/status/payout + campaign totals),
and prints a one-line summary:
`Clipsdaily earnings 2026-11-15: $0.00 realized (0 approved), $0.00
projected (5 pending), 5 clips, 0 views, top clip <url> (0 views)`.
Status normalized pending/approved/rejected. Payout for approved
clips comes from the dump, else estimated views/1000 x rate.
Pending = projected, never realized.

Run daily: `clipsdaily earnings --update && clipsdaily earnings --summary`.

## Dry-run test results (Nov 15, 2026, all dry-run, no real join/post/submit)

- Watcher: live discover page parsed **25 campaign records**; Speed
  campaign present (rate $1, available $7,500.71). Decisions:
  **0 join_requested, 19 needs_review, 6 skipped/known** (Speed =
  already-joined). 0 joins is correct: no new campaign passes all 7
  rules right now. Detail fetch gated to join candidates only
  (run time 57s -> ~5s).
- Gate, legacy Japan clips (posted 14:00, center-crop era):
  window PASS, caption PASS, framing **FAIL** (clip30 top=2.06
  bottom=6.66; tiktok top=1.62 bottom=5.94) -> BLOCKED, exit 2.
  These are already posted + submitted (grandfathered, no action);
  the gate governs NEW queueing/submission. The build spec's
  "gate passes the two already-posted clips" was wrong on framing:
  those files predate the full-frame rule (Nov 15, 20:37).
- Gate, new full-frame dry-run clip: framing **PASS**
  (top=0.03, center=4.63, bottom=0.50 over 3 frames).
- Gate, out-of-window clip (2:00:00 = 7200s): window **FAIL**
  ("clip starts 7200s, before window start 10589s"), caption PASS,
  framing PASS -> BLOCKED, exit 2. Isolated rejection proven.
- Gate, bad-caption clip (no Expedia, no #IShowSpeed): caption
  **FAIL** (all three captions), window PASS, framing PASS ->
  BLOCKED, exit 2. Isolated rejection proven.
- campaign_cut dry-run: Japan moment (spike 10745, tail 156s) cut
  to campaign_work/dryrun_ishowspeed-2921253522-10745s/:
  30s full-frame clip (1080x1920) + 75s TikTok variant (1080x1920).
  In-script gate verdict at 21:33:49 EST: **GATE PASS (vod 2921253522
  range 10725s-10800s inside window 10589s-end)**, gate_ok true,
  block_reason null. First attempt was killed at the 600s timeout by
  an SSH pipe break mid TikTok burn (CPU contention with the VOD
  agent's ffmpeg); the re-run was detached via nohup and completed
  cleanly in ~12 min. Lesson: run long ffmpeg jobs detached
  (nohup/tmux), never over a bare SSH pipe.
- auto_submit: `--scan` on the real queue wrote **0 jobs** (no
  campaign clips queued) — correct. Synthetic job test: write
  created=true, re-write created=false (idempotent), mark-submitted
  with TEST-SUB-001, re-write after submit created=false (no
  rewrite), backdated 40-min-old job expired on --list-pending
  with correct window note. Test job deleted after. stdout is pure
  JSON (logs moved to stderr) after a fix found by the test.
- earnings: synthetic dump of the 5 known pending submissions
  (HK YT f9ecabc2, HK IG 403f4abe, TikTok Japan e77422fb, Japan YT/IG
  URL-matched, all 0 views) -> summary "$0.00 realized (0 approved),
  $0.00 projected (5 pending), 5 clips, 0 views". Correct.

## What is still missing for live activation

1. Parent installs the submit cron (every 15 min, SUBMIT_CRON_BODY.md)
   + watcher daily cron + earnings dump cron.
2. hourly_poster.py integration: prefer campaign_queue.json entries
   when a campaign is active (parent-approved step, NOT built — the
   hourly builder owns hourly_poster.py).
3. Whop payout setup (Abel's money, his call — not done).
4. The Hong Kong TikTok 90s re-upload is a one-off outside this
   automation (VOD agent re-uploads, parent manually submits within
   30 min) — flag the gap; do not let the outbox write a duplicate.
5. Legacy Speed clips are NOT seeded into campaign_queue.json (they
   live in clips/ + earnings by URL; seeding would duplicate submits).
6. Re-auths cannot be automated: TikTok cookies / YouTube token
   expire and only Abel can re-approve.

## Risks found

- One-strike rule: a single bad submission bans the account from
  EVERY campaign permanently. The gate is the only defense; it must
  stay strict (borderline = blocked) and must never be bypassed for
  speed. The framing detector already failed once (ratio false-pass)
  and was fixed with absolute band energies — re-validate it against
  both ground truths if cutter.py's filter chain ever changes.
- The watcher parses undocumented Next.js page HTML. If Content
  Rewards changes its discover page structure, parsing returns 0
  records and the watcher logs it — it fails closed (no joins),
  but someone must notice the 0-parse and fix the parser.
- TikTok posting still depends on the fixed poster (post_tiktok_fixed.py)
  wired into poster.py; the runner's TikTok path uses stock
  tiktok-uploader until that wiring lands.
- CPU contention: indra runs the live runner + VOD batch + hourly
  builder + this automation. Long ffmpeg burns (TikTok variant) can
  exceed SSH timeouts — run detached (nohup/tmux) for anything over
  ~5 min.

## Nov 16, 2026 — three-leg fix (YouTube 8/day, TikTok subprocess, IG meta invariant)

- YouTube is now 8/day: hourly_poster.py posts to YouTube only on :00 of
  00, 03, 06, 09, 12, 15, 18, 21. The channel hit the daily upload limit
  at 9 posts on Nov 15, so 2/hour (48/day) re-hit it within hours.
  A YouTube uploadLimitExceeded never burns a retry — the clip retries
  on the next YouTube slot instead.
- TikTok posts now run in a fresh subprocess (post_tiktok_fixed.py
  --file/--caption/--label, via post_file_subprocess()). Root cause:
  tiktok-uploader's sync Playwright session leaks its event loop into
  the calling process (close() closes the browser but never stops the
  Playwright context manager), so the next sync_playwright().start() in
  the same long-lived process raised "using Playwright Sync API inside
  the asyncio loop". One-shot scripts kept working; the hourly poster
  and runner failed every TikTok attempt from Nov 15 22:00 on. Session
  itself is valid (dry-run Nov 16 09:33: logged in, Studio reachable,
  1 video on the account) — no fresh cookie export needed.
- IG meta invariant: ig-outbox/meta.json status is IG state only —
  "staged" until the IG cron posts it, "posted" after. YouTube/TikTok
  outcomes must never flip it. Before this fix, failed YT/TT slots
  wrote "failed"/"pending" into the meta and the IG cron (which only
  posts "staged") skipped the clip forever — that silently killed the
  IG leg all day Nov 16.
- Non-YouTube slots keep TikTok/IG at 2/hour: the poster takes the
  first pending entry that still needs a TikTok post instead of sitting
  behind an entry that is only waiting on its YouTube slot.
- Queue: the 6 entries that "failed" on Nov 15-16 (jynxzi 12505s,
  14435s, 20925s, 18295s, 14935s, 1865s) were reset to pending — their
  failures were the YT limit + the TikTok leak, not real post failures
  (verified: no .posted file, no LIVE lines). The two staged Shorts
  (stableronaldo 5115s, jynxzi 2075s) were moved to the front of the
  pending queue.

## Nov 16, 2026 — TikTok Content Posting API route (off by default)

- New module `tiktok_api.py`: official Content Posting API
  (open.tiktokapis.com) — OAuth (user.info.basic + video.upload +
  video.publish), Direct Post + draft mode, chunked FILE_UPLOAD,
  status polling, token refresh with rotation. No cookies, no
  Playwright. No live TikTok call has been made (no developer app
  exists yet); tested with mocks only.
- `poster.py`: `post_tiktok` routes to the API when `tiktok_api: true`
  in config.yaml, else the Playwright cookie path (unchanged). New
  `allow_short` flag keeps the hourly 30s fallback. `check_tiktok`
  reports the API token when a client file exists.
- `hourly_poster.py`: reads `tiktok_api`/`tiktok_api_mode` from
  config.yaml every slot (no restart to flip); PENDING:/DRAFT:
  publish_ids are reconciled next slot instead of re-uploaded; cap
  hits never burn a retry; a failed reconcile waits for next slot.
- Caps enforced in code: ~15 Direct Posts/day per creator (rolling
  24h counter in `.auth/tiktok_api_usage.json`), 5 pending drafts/24h.
- Full checklist + audit risk: `TIKTOK_API_SETUP.md`. Risk: TikTok
  says apps for private/personal use are not approved — the audit
  may refuse a one-account pipeline; fallbacks are draft mode (no
  audit) or a paid scheduler. App review also needs a website with
  Privacy Policy + Terms; clipsdaily has none yet.
- Tests: `test_tiktok_api.py` 24/24, `test_poster_tiktok_api.py`
  12/12 (both mocked, pass on indra).

## Nov 16, 2026 — Kick monitoring verified live + lost-clip rescue staging

- Kick was ALREADY built Nov 15 (not new): `recorder.py` records Kick via
  streamlink (no account), `chat.py` KickChatMonitor via the public Kick
  API + per-channel Pusher config (no auth), `config.yaml` watches
  `kick/xqc` + `kick/adinross`, shared per-streamer cooldown dedupes xqc
  Twitch + Kick. The live runner (started Nov 16 10:45) watches both.
- Proof Nov 16: adinross Kick spike 04:27 (141 msgs, median 26,
  intensity 5.42) → clip `kick_adinross_72s.mp4` (30s, 1080x1920) + 75s
  TikTok version, real transcript, frame-checked. xqc Pusher subscribe
  held 60s idle with no errors (offline, no messages — expected).
- The overnight adinross clip was cut but NEVER posted and never staged
  — the runner posted live clips immediately or lost them. Fix:
  `runner.stage_to_queue()` stages a clip that posted to ZERO platforms
  at the front of `queue/queue.json` (`source: "live"`,
  `campaign_eligible: false`) for the hourly poster to retry. Partial
  posts are NOT staged (would double-post). Dedup by id. The recovered
  05:56 adinross clip was NOT staged (would post next slot; no post
  without Abel's go); cleanup deletes it after 48h unposted (~Nov 18 05:58).
- Campaign safety: staged live entries have no `campaign_id` and no
  `vod_id`; auto_submit requires a campaign_id and the gate requires a
  vod_id match — blocked twice over (test 4).
- Checked, NOT added: stableronaldo (verified, 24,164 followers) and clix
  (verified, 26,714) are dormant on Kick (no recent categories, no VODs);
  kaicenat/ishowspeed/sykkuno/jynxzi/hasanabi are placeholder channels
  (<5K followers); zackrawrr dormant; drake intermittent (already dropped).
- Kick limits vs Twitch: no VOD backfill (live-only), chat rides
  unofficial website endpoints (official api.kick.com needs an OAuth app;
  not created, not needed), smaller chats = rarer spikes, no clips API.
- Open: no runner auto-restart (Nov 15 19:27 instance's log ends 22:01,
  next start Nov 16 10:45); a watchdog is still unbuilt. Staging takes
  effect on the next runner restart (config is read once at startup).
- Full write-up: `KICK.md`. Tests: `test_live_staging.py` 4/4.

## Nov 16, 2026 — live status note

> **Repo note (Nov 16, 2026):** the live code on indra (`/home/abel/clipsdaily/`) matches this branch. The live `queue_seed.py` and `queue_seed_famous.py` differ from the repo in one way: the live files use top-level imports (`import streamlink`, `from clips_api import ...`) and call `load_config()` on each run, and the live `queue_seed.py` has a `kick_stage()` helper that fetches the latest Kick VOD from `vod/` (the repo's `src/clipsdaily/queue_seed.py` has both). The live `README.md` in `/home/abel/clipsdaily/` carries a different top section (quick-start for the live dir) than the repo README; everything else is the same.

This note was preserved verbatim from the live dir during the Nov 17, 2026 shutdown. The famous-clips source it references is ADR 016; the restart guide is `docs/RESTART.md`.
