# ClipForge — Install

One box, one command, then one setup wizard. After that the pipeline
runs with zero human or agent intervention: it watches, records, cuts,
posts, cleans up after itself, restarts its own dead services, and
alerts you only when something needs a human (a dead login, a failed
health check).

## Requirements

- Linux box that stays on (a homelab server, a VPS, a spare laptop).
  8 cores / 11 GB RAM supports 8 concurrent recordings; Whisper on CPU
  is the bottleneck (~1 min per 30s clip).
- Python 3.10+, ffmpeg **≥ 6.1**, git, systemd (user services).
- ≥ 20 GB free disk (recordings are transient, but spikes need room).
- A Twitch/Kick account is NOT needed to watch public streams.
  You DO need accounts for each platform you post to (below).

## Install

You get the installer + a license key from me directly — there is
no public download. (ClipForge is proprietary and private.)

```bash
./packaging/install.sh --license key.txt --accept-license
# ./packaging/install.sh --home /srv/clipforge --license key.txt --accept-license
```

The installer shows the LICENSE + beta terms, requires acceptance
(`--accept-license`, or type `I ACCEPT` interactively), and verifies
your license key offline (signature + expiry) before installing
anything. A bad, tampered, or expired key refuses the install.
Your key is installed to `~/.auth/license.key` (0600) and checked
again every time a service starts — a leaked copy without a key
does not run.

The installer is idempotent: re-running it against an existing
ClipForge home upgrades the code and units and leaves config.yaml,
queue/, .auth/, and logs/ alone. It **refuses** to run against the
live ClipsDaily directory (/home/abel/clipsdaily) or any directory
that already holds a queue.json / credentials without the ClipForge
marker file.

What it does: creates `~/.clipforge-venv`, installs the package,
pre-warms the faster-whisper base model, installs Playwright
chromium, creates the runtime home (`queue/`, `ig-outbox/`, `clips/`,
`vod/`, `recordings/`, `logs/`, `.auth/` 0700), writes config.yaml
from the template, installs the systemd user units, enables user
linger, and runs a smoke check (`clipforge status`).

## One-time setup

```bash
clipforge setup
```

The wizard asks for your accounts, watchlist, platforms, alerts, and
campaign opt-in, then runs each platform's auth flow, then enables
and starts all units. Non-interactive: `clipforge setup --yes`
(defaults + `CLIPFORGE_*` env vars; auth steps print as manual
instructions instead).

## The honest boundary — what a human still has to do, once

These cannot be automated; the wizard walks you through each one:

1. **YouTube OAuth.** Create a Google Cloud project, enable the
   YouTube Data API v3, create a Desktop OAuth client, paste the
   client-secrets file, and consent in the browser. **Publish the
   OAuth app to Production** — in Testing mode the refresh token
   expires after 7 days and posting silently stops.
2. **TikTok developer app.** Create the app at developers.tiktok.com,
   request the Content Posting API, wait for review (days to ~2
   weeks), then the separate audit. TikTok may refuse a one-account
   pipeline; if it does, draft mode (no audit, 5/day, you tap
   publish on your phone) is the fallback, and cookie upload is
   currently blocked by TikTok. Until the audit passes, Direct Posts
   are forced private.
3. **Instagram session.** Export a session cookie from a browser
   signed in to the account (recommended — password login is
   currently broken against Instagram's endpoint), or log in with a
   password. Sessions expire; when one dies the IG worker stops
   cleanly, the watchdog alerts you, and you re-run
   `clipforge auth instagram --cookies cookies.txt`.
4. **Content Rewards (only if you enable campaign automation).**
   Create the account, log in once in the headed browser
   (`clipforge auth contentrewards`), and join campaigns. Campaigns
   have a ONE-STRIKE rule: a wrong clip can get the account banned
   from the program. Read `docs/CONTENTREWARDS_AUTO.md` first.
5. **Your choices:** watchlist, posting schedule, caps, campaign
   opt-in, alert channel. All editable later in config.yaml or the
   dashboard — the runner re-reads config every 60s, no restart.
6. **Remote dashboard access (optional).** The dashboard binds
   127.0.0.1:8787 only. For remote access put it behind a tunnel
   (e.g. Cloudflare Tunnel, Tailscale Serve) — there is no auth in
   v1, so never expose the port directly.

## After setup

- Dashboard: http://127.0.0.1:8787 — watchlist, queue, post history,
  per-platform health, settings, logs, kill switch.
- Status any time: `clipforge status`
- Auth check: `clipforge auth check` (read-only, posts nothing)
- Kill switch: `touch ~/clipforge/STOP` (or the dashboard toggle) —
  posting pauses; remove the file to resume.
- Updates: `clipforge update --check`, then `clipforge update`
  (opt-in, `auto_update: false` by default; tests run first, and a
  failed health check rolls back automatically).

## What the package does on its own

- Runner watches the watchlist, records live streams, cuts clips on
  chat spikes, stages them in the queue.
- Hourly poster posts to YouTube (8 slots/day) and TikTok, stages
  Instagram Reels; the IG worker posts them.
- Queue maintainer keeps the pending queue seeded from past VODs.
- Campaign watcher joins campaigns; the cutter cuts eligible clips
  behind the eligibility gate; auto-submit files them within the
  30-minute window.
- Watchdog restarts any dead unit within 60s and writes health.json
  every 30 min; the notifier alerts on new failures (one per episode).
- Cleanup runs hourly: raw footage after clipping, posted clips
  after the retention window, logs after 7 days. Pending/partial
  queue entries and staged IG clips are never deleted.
- Graceful degradation: a platform that is unconfigured or blocked
  is skipped silently; the other platforms keep posting, no clip is
  lost, the queue never stalls.

The design + audit doc (`docs/AUDIT_AND_DESIGN.md`) is internal-only
and is not part of the customer install.
