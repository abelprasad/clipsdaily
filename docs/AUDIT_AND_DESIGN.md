# ClipForge packaging — audit + design (branch: packaging/zero-intervention)

Working brand: **ClipForge** (slug `clipforge`). The live system stays **ClipsDaily**
(`/home/abel/clipsdaily/`, its tmux sessions, its crons) until the package ships and
Abel says to switch. The Python package stays `clipsdaily` internally; all
user-facing surfaces (installer, dashboard, systemd units, docs, wizard) use the
brand constant in `src/clipsdaily/branding.py` (`BRAND_NAME`, `BRAND_SLUG`). A full
Python-package rename is a follow-up after Abel confirms the name.

## Phase 1 — audit: every component, where it runs, every touchpoint

### Component map

| # | Component | Where it runs today | Trigger | Human / Friday touchpoint |
|---|---|---|---|---|
| 1 | runner.py — live watch, record, chat spikes, cut, post | indra tmux `clipsdaily` | manual start | Start after reboot (tmux dies on reboot); config edit = manual restart; no config reload |
| 2 | hourly_poster.py — YT 8 slots/day, TikTok, IG staging | indra tmux `clipsdaily-hourly` | manual start | Same reboot problem; hardcoded `/home/abel/clipsdaily` paths; never reads campaign_queue.json |
| 3 | queue_seed.py — VOD throwback maintainer | indra tmux `clipsdaily-queue` | manual start | Same reboot problem; hardcoded paths; does NOT honor STOP; no retention on queue/clips |
| 4 | watchdog.py — restarts dead sessions, health checks | indra systemd user service (abel) | boot (linger on) | Alert delivery is an operator-VM cron (Friday reads health-alerts.log, messages Abel) |
| 5 | IG posting | OPERATOR VM cron every 30 min (ig-post-staged.sh + instagram-cli) | cron | **Biggest external dependency**: instagram-cli exists only on the operator VM (glibc 2.39 + privsep socket); instagrapi login on indra is BROKEN (see below) |
| 6 | auto-submit scan + submit | operator VM cron 15 min (submit_cron.sh) + Friday browser submit | cron | **Browser submit is Friday by hand**; submit window is 30 min from post |
| 7 | campaign watch + join | operator VM cron daily (watcher on indra + Friday browser join) | cron | **Join click is Friday by hand** |
| 8 | earnings | operator VM cron daily (Friday browser dump + earnings.py) | cron | **Dashboard dump is Friday by hand** |
| 9 | watchdog alerts | operator VM cron 30 min | cron | Friday is the messenger |
| 10 | cleanup.py | inside runner (startup + hourly) | automatic | Covers clips/ (posted 24h, unposted 48h), recordings backstop 48h, temps, logs 7d. Does NOT cover queue/clips (1.1G, 134 files, never deleted), queue/work (291M), ig-outbox (97M, 12 dirs), vod/ (5.8G) |
| 11 | code updates | manual | human | Live files edited directly; sync_repo.py copies live→repo by hand; deploy.sh exists but never run; live still runs flat `python3 *.py`, not the `clipsdaily` CLI |
| 12 | credentials | .auth/ (0700) on indra | human | YouTube OAuth auto-refresh works (token refreshed Nov 16 18:00). TikTok cookies valid to May 2027 but the cookie upload path is BLOCKED by TikTok throttle. TikTok API built, no dev app yet. IG has no session file on indra at all |

### Touchpoint verdicts

- **CLOSED by the package**: reboot restarts (systemd units for 1–3 + watchdog), IG posting (on-box ig_poster worker), alert delivery (on-box notifier), queue/clips + outbox + vod retention (extended cleanup), campaign wiring (hourly poster reads campaign_queue.json), config reload without restart (runner reconciles watchlist every 60s), code updates (opt-in auto-update with rollback).
- **CLOSED with an opt-in**: campaign join/submit/earnings browser automation (new contentrewards.py, Playwright, stored session; default OFF — see risks).
- **OPEN, cannot be automated**: one-time setup (OAuth flows, TikTok developer review/audit, platform approvals), credential re-approval when a platform expires a session, TikTok audit outcome, fixing a broken third-party parser (Content Rewards discover HTML, Kick Pusher endpoints) when the site changes.

### Hard facts the design must respect

- instagrapi 3.1.0 is the LATEST on PyPI — no upgrade fixes the IG login failure
  (`password_publickeys` gets no `ig-set-password-encryption-key-id` header, Nov 15).
  On-box IG options, in order: (a) session-cookie import (bypass password login,
  same pattern as the TikTok cookie route), (b) official Meta Content Publishing
  API (FB Page + app review), (c) manual outbox. The package implements (a) with
  (b)/(c) documented. Live IG verification is a manual step (no test IG account).
- YouTube OAuth app is in Testing mode per docs/AUTH.md (test user added).
  Testing-mode refresh tokens expire after 7 days. The wizard must publish the
  app to Production or warn loudly. Token auto-refresh itself works.
- TikTok cookie upload path is blocked in practice (all Nov 16 attempts failed).
  The durable TikTok route is the official Content Posting API (built, off by
  default, needs dev-app sign-in + review + audit). Draft mode needs no audit.
- Repo src is already ported (relative imports + `runtime_home()`) and
  logic-identical to live (normalized diff = 0 lines except imports). NOT ported:
  hourly_poster.py + watchdog.py (hardcoded `/home/abel/clipsdaily`),
  auth_youtube_manual.py (hardcoded .auth), chat.py (`YT_DLP` hardcoded),
  eligibility_gate.py (ffmpeg/ffprobe fallback paths). Dev-only scripts
  (cut_speed_expedia, diag_tiktok, framing_test, motion_test, patch_*) keep
  hardcoded paths and are EXCLUDED from the package.
- Live Python env: system python3 3.10.12 + `--user` site-packages (no venv).
  Deps: streamlink 8.6.3, faster-whisper 1.2.1, instagrapi 3.1.0,
  tiktok-uploader 1.2.0, google-api-python-client, playwright 1.65.2 + chromium,
  yt-dlp, PyYAML. ffmpeg: system 4.4.2 is TOO OLD; live route is micromamba
  ffmpeg 9 via ~/.local/bin symlink. TwitchDownloaderCLI binary in ~/.local/bin
  (queue_seed VOD downloads). faster-whisper model downloads on first run.
- Kick chat uses unofficial endpoints (kick.com/api/v2 + web.kick.com realtime
  Pusher credentials, hardcoded Pusher key died Oct 2026 once already). Twitch
  chat via yt-dlp. GQL client ID in queue_seed is the public Twitch web client ID.
- Disk: indra 627G free. recordings/ is 114G transient (concurrent 1080p60
  recordings). Disk guard 50GB in runner. A customer box needs 500GB+ free
  recommended; installer warns below that and lowers default concurrency.
- STOP kill switch: honored by runner + hourly_poster; NOT by queue_seed.
  Package: every service honors STOP.
- Caps/limits enforced in code (keep): YT 8/day (slots 00/03/06/09/12/15/18/21),
  TikTok API ~15 Direct Posts/day + 5 drafts/24h, max 20 clips/day, 1 clip per
  streamer per 5 min, TikTok 60–90s only (30s fallback allowed in hourly poster).
- Posting rules (keep): full frame 1080x1920, no burned-in word captions, one
  hook overlay first ~3s, one-line captions, campaign gate (window + caption +
  framing) with borderline = blocked, never double-post, never submit the same
  clip+platform twice, jobs expire 30 min after posted_at.

## Phase 2 — design

### Layout (single host, customer's box, no Friday VM)

```
~/clipforge/                      # runtime home (default; $CLIPFORGE_HOME overrides)
  config.yaml                    # ONE config file (template + wizard)
  .auth/                         # 0700, never leaves the box
  queue/queue.json  queue/clips/ queue/work/ queue/state.json
  campaign_queue.json            # NEW: read by hourly poster (see below)
  ig-outbox/  clips/  vod/  recordings/  logs/  campaign_work/  submit-outbox/
  health.json  watchdog-state.json  STOP
~/clipforge-release/              # installed package (pip install from release tarball)
~/.config/systemd/user/clipforge-*.service (+ .timer)
```

### Services (systemd user units, all `Restart=on-failure`, linger on)

| Unit | Runs | Notes |
|---|---|---|
| clipforge-runner | runner | config reload every 60s (see below) |
| clipforge-hourly | hourly poster | + campaign_queue preference |
| clipforge-queue | queue maintainer | honors STOP (new) |
| clipforge-ig | ig_poster (new) | polls ig-outbox every 5 min, instagrapi session |
| clipforge-watchdog | watchdog (ported) | restarts dead units, health checks, notifier |
| clipforge-dashboard | dashboard (new) | FastAPI, 127.0.0.1 only |
| clipforge-campaign-watch.timer | daily | watcher --check |
| clipforge-submit.timer | 15 min | auto_submit --scan (+ contentrewards submit when opted in) |
| clipforge-earnings.timer | daily | earnings --update (+ contentrewards dump when opted in) |
| clipforge-cleanup.timer | hourly | extended retention pass |

### Installer (`install.sh`, idempotent)

Refuses to run against the live directory (`/home/abel/clipsdaily`) or any dir
containing `queue/queue.json` with existing entries. Checks python ≥3.10, disk
(warn <500G free, reduce default concurrency), ffmpeg ≥6.1 (else micromamba /
static-build guidance — never silently uses 4.4), creates venv (fallback
`--user`), installs pinned requirements + the package, installs
TwitchDownloaderCLI, creates the runtime home + config from template, installs
units + timers, enables linger, pre-warms the faster-whisper model, runs
`clipforge status` as a smoke check. Re-running updates in place.

### Setup wizard (`clipforge setup`, interactive; `--yes` + env vars for scripted)

System checks → venv/deps → config (watchlist, caps, retention, platforms off
by default) → auth flows: YouTube OAuth (prints URL, localhost redirect;
WARN + publish-to-Production step), IG session-cookie import (paste/export
cookies → build session file → verify with account_info; password login kept
as a fallback attempt), TikTok API (prints the app-packet steps, runs
--auth-url/--exchange; or cookie fallback with a blocked-path warning) →
campaign automation opt-in (default OFF, one-strike warning) → notifier
(email SMTP / Discord webhook / none) → enable units → `clipforge status`.

### Config reload without restart (dashboard contract)

- Dashboard writes config.yaml atomically (tmp + replace, YAML validated first).
- Runner reloads config every 60s, reconciles watch threads (spawn new
  streamers, exit removed ones), and writes `logs/runner-state.json`
  `{watchlist, platforms, config_loaded_at, config_mtime}`.
- Dashboard test: toggle a streamer → within 90s runner-state.json reflects
  it, no manual restart, no service restart.

### IG worker (`ig_poster.py`, new)

Polls ig-outbox for `staged` metas (ig_slot within window), posts via
instagrapi session, marks posted exactly like the operator script does
(`.posted` with media_fbid + posted_at_utc, meta flipped to `posted`).
Session failure → keep staged, alert, never lose the clip, never retry in a
tight loop. Never posts a clip whose meta is `posted`.

### Campaign wiring (hourly_poster change)

When a campaign is active, the poster prefers campaign_queue.json entries
(gate re-checked at post time via eligibility_gate; a gate failure blocks the
entry, never posts it). Live entries otherwise unchanged.

### Content Rewards browser automation (`contentrewards.py`, new, OPT-IN)

Playwright, stored session from a guided one-time login
(`clipforge auth contentrewards` opens a headed browser, customer logs in,
storage state saved 0600). Join: read join_requests.json, click Join, verify
the green Joined badge, append join_results.json. Submit: read pending
submit-outbox jobs, re-gate, submit, verify dashboard shows Pending WITH a
submission ID, mark submitted; any failure → mark failed, never double-submit.
Earnings: scrape the submissions dashboard to earnings_dump.json.
Default OFF (`campaign_automation: false`). Fail closed on every path. Live
verification is a manual step (no test Content Rewards account).

### Notifier (watchdog addition)

`notify:` in config — `none` (default, log-only), `email` (SMTP host/port/user/
pass via env, TLS), `discord` (webhook URL). One alert per failure episode,
re-alert only after recovery. Never alerts on TikTok known-broken.

### Cleanup extension (cleanup.py)

Keep existing rules; add: queue/clips (delete files of posted entries after
`queue_clip_retention_days` (7d), unposted after 48h — never delete files
referenced by pending/partial entries), queue/work (delete work dirs of done
entries), ig-outbox (delete staged copies 7d after posted), vod/ (delete video
files older than retention; keep chat JSONs). All knobs in config.yaml.

### Auto-update (`clipforge update`, opt-in, default off)

Checks the release channel (git remote tag; repo not pushed yet — channel does
not exist until the repo is public). Stages the new version, runs the test
suite, swaps, restarts units, health-checks for 10 min; on failure restores
the previous checkout and restarts. Rollback is automatic, never silent.

### Graceful degradation

Any platform unconfigured/blocked → skip it silently, keep the others posting,
never lose a clip, never stall the queue. A dead IG session, a dead TikTok
session, a dead Content Rewards session, or a 0-parse campaign discover all
degrade to "that leg paused + health.json flags it" — the core loop never stops.

## One-time human setup steps that CANNOT be automated

1. Create the Google Cloud project + YouTube Data API v3 + Desktop OAuth client;
   approve the OAuth consent in a browser; publish the OAuth app to Production
   (else the refresh token dies in 7 days).
2. TikTok developer app: create at developers.tiktok.com, submit for review
   (days to ~2 weeks), then request the Content Posting API audit. Outcome is
   TikTok's call; a one-account pipeline may be refused (draft mode is the
   no-audit fallback).
3. Instagram: export the session cookies from a signed-in browser (or approve
   the Meta app for the official API route). Re-approve when Instagram expires
   the session.
4. Content Rewards account + login (for the opt-in browser automation);
   re-login when the session expires.
5. Choosing the watchlist, the posting schedule, and the campaign opt-in.
6. Putting the dashboard behind a tunnel for remote access (localhost by default).

## What remains before a real customer can install it

- License: MIT exists in the repo. Pricing + terms of sale: not built.
- Push the repo to GitHub (no remote yet) + a release channel for auto-update.
- Live verification steps that need real credentials: IG session login, TikTok
  API end-to-end post, Content Rewards join/submit/earnings, YouTube OAuth in
  Production mode. All are documented as manual verification steps, not faked.
- Dashboard auth beyond localhost (token) if remote access is ever enabled.
- A full Python-package rename (clipsdaily → clipforge) if Abel confirms the name.
