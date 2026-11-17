# Restart clipsdaily from scratch

This is the full restart guide for the clipsdaily pipeline. It is written
so a stranger (or a future Abel) can rebuild the whole system on a fresh
server without asking anyone anything. It covers the live pipeline, the
ClipForge package, and the ClipForge ads.

**Status at shutdown: November 17, 2026.** The pipeline was shut down
that day after Instagram flagged `@clippedaily31` for unoriginal content
(see [Shutdown state](#shutdown-state-november-17-2026)). Everything
below describes the system as it was running, plus what is broken and
what a restart must change. Do not just turn it back on and resume
posting plain reposts — read the Instagram section first.

## What the pipeline is

Fully automatic clip pipeline for Twitch, Kick, and YouTube Live. It
records live streams, finds the moments chat erupts, cuts 30-second
vertical clips, and posts them to YouTube Shorts, TikTok, and Instagram
Reels on an hourly cadence — no review queue, no human step. General
purpose: any streamer on the watchlist, any game, any event.

It also joins and submits clipping campaigns (Content Rewards) behind a
strict eligibility gate, because one bad submission bans the account
from every campaign permanently.

### Architecture

| Piece | File | Runs where | What it does |
|---|---|---|---|
| Runner (live clipping) | `src/clipsdaily/runner.py` | tmux `clipsdaily` on indra | Watches the watchlist, records live streams (streamlink), detects chat spikes, cuts 30s clips + TikTok variants, stages them in `queue/` |
| Hourly poster | `src/clipsdaily/hourly_poster.py` | tmux `clipsdaily-hourly` on indra | Every 30 min, takes the next pending queue entry, posts to YouTube / TikTok / stages for Instagram |
| Queue maintainer | `src/clipsdaily/queue_seed.py` | tmux `clipsdaily-queue` on indra | Keeps >= 24 pending clips by cutting chat-spike moments from completed Twitch VODs (throwbacks) and top Twitch clips by views (famous clips) |
| Watchdog + health | `src/clipsdaily/watchdog.py` | systemd `clipsdaily-watchdog.service` on indra | Every 60s restarts dead tmux sessions; every 30 min verifies each platform actually posted recently from on-disk evidence only, writes `health.json`, appends new failures to `logs/health-alerts.log` |
| IG poster (indra) | `src/clipsdaily/ig_post_staged.py` | systemd `clipsdaily-ig-post.service` + `.timer` (`*:05,35`) on indra | Posts the most recently staged Reel from `ig-outbox/` via instagrapi; needs a session file (see Auth) |
| IG poster (operator VM) | `scripts/ig-post-staged.sh` | operator-machine cron, every 30 min | Same job as the indra poster, but via `instagram-cli` (Meta Accounts Center link). This was the live route until the indra poster was built Nov 17, 2026. Only one poster should run — the indra one replaces this one once its session exists |
| Campaign watcher | `src/clipsdaily/campaign_watcher.py` | operator cron, daily | Discovers new Content Rewards campaigns |
| Campaign cutter | `src/clipsdaily/campaign_cut.py` | manual / watcher | Cuts campaign clips from the campaign VOD inside the allowed window |
| Eligibility gate | `src/clipsdaily/eligibility_gate.py` | before every submit | Blocks ineligible clips (wrong footage, wrong window, missing mention/hashtag) |
| Auto-submit | `src/clipsdaily/auto_submit.py` | operator cron, every 15 min | Submits eligible posted campaign clips within 30 min of posting |
| Earnings | `src/clipsdaily/earnings.py` | operator cron, daily | Dumps campaign earnings to `earnings.json` / `earnings_dump.json` |
| TikTok API route | `src/clipsdaily/tiktok_api.py` | off by default (`tiktok_api: false`) | Official TikTok Content Posting API: OAuth + PKCE, Direct Post + draft mode, caps enforced. Needs a developer app + review + audit (see Auth) |
| ClipForge package | `packaging/` + `src/clipsdaily/` (packaging branch) | customer host | Zero-intervention install of the same pipeline: installer, setup wizard, systemd units, license-key check, localhost dashboard. See [ClipForge](#clipforge-the-packaged-product) |
| Ads | `clipforge-ads/` | indra (render host) | Remotion project that renders ClipForge promo reels. See [Ads](#ads-clipforge-ads) |

### Data flow

```
Twitch/Kick live  ->  recorder  ->  chat spikes  ->  cutter (30s + TikTok variant)
                                                      ->  queue/queue.json (pending)
                                                      ->  hourly poster (YT / TikTok / IG stage)
                                                      ->  ig-outbox/ (staged) -> IG poster -> Instagram
Completed VODs    ->  queue maintainer (throwbacks + famous clips) -> queue/
Campaign VOD      ->  campaign cutter -> campaign queue -> eligibility gate -> auto-submit
```

Queue entries carry `id`, `streamer`, `platform`, `vod_id`, `spike_seconds`,
`intensity`, `clip30`, `tiktok`, `title`, `caption_yt` / `caption_tiktok` /
`caption_ig`, `status` (`pending` / `posted` / `failed`), retry counters,
and `history`. The poster reads `queue.json` every slot; the maintainer
tops it up to the target. A `STOP` file in the runtime home pauses
everything (runner, poster, maintainer, and the IG poster all honor it).

### Watchlist (at shutdown)

Twitch: kaicenat, ishowspeed, sykkuno, jynxzi, stableronaldo, zackrawrr,
hasanabi, clix. Kick: xqc, adinross. Kick is live-only (no VOD backfill;
throwbacks are Twitch-only). The Speed Expedia campaign VOD
(`2921253522`) is excluded from the queue everywhere — campaign footage,
never queued.

### Limits and rules (at shutdown)

- 2 clips/hour max, 20 clips/day max. YouTube 8/day. TikTok API ~15
  Direct Posts/day + 5 drafts/24h (when enabled).
- Cut window: spike -20s / +10s. Full frame, no cropping (blurred /
  darkened fill). No burned-in word captions on clips (ads are the
  exception — see Ads).
- One hook overlay in the first ~3s. Captions are one line, no hashtags
  (except campaign-required ones), no boilerplate, no date. Live:
  `clipsdaily • <streamer>`. Throwback: `Throwback — <streamer>:
  <moment>`. Famous: `<streamer>: <moment>` (no THROWBACK label).
- Disk guard: 50 GB free minimum. Recordings retained 48h; queue clips,
  outbox, and VODs retained 7 days (packaged cleanup).
- Kill switch: `touch STOP` in the runtime home.

## Shutdown state (November 17, 2026)

Record this before restarting — several things were broken, and the
restart must fix them or work around them.

| Item | State at shutdown |
|---|---|
| TikTok auto-posting | **Blocked account-wide since Nov 15.** Cookie path dead ("no confirmation" on every post). Manual phone post works, proving the account is fine. The official API route is built but off; it needs Abel's developer sign-in + review + audit. |
| YouTube uploads | **OAuth client DISABLED.** Uploads fail with `disabled_client: The OAuth client was disabled.` Last successful Short Nov 16, 21:00. Fix: re-enable the OAuth client in Google Cloud Console (disabled_client is not a token-expiry problem; a token refresh does nothing). |
| Instagram | **Flagged Nov 17 for unoriginal content.** "This content may not be original to you" — profile and content not recommended to non-followers (no Explore, Reels tab, or suggested posts). Followers still see posts. Recovery needs most posts in a rolling 30-day window to be original; deleting/archiving does NOT fix it. See [Instagram originality](#instagram-originality-read-this-before-restarting). |
| IG login to indra | **Never tested.** The indra poster (`ig_post_staged.py` + systemd timer) is built and dry-run verified, but no login was ever completed, so it has no session. The VM `instagram-cli` route kept posting in the meantime. |
| Queue | 44 entries: 36 pending (8 famous at the front, 28 throwbacks), 7 posted, 1 failed. |
| Famous clips | New source added Nov 17 (see below). First famous clip posted to IG Nov 17, 13:37: jynxzi "kiss on the lips", 2.3M views (fbid 17969070510247215). |
| Speed Expedia campaign | All 6 clips submitted, all **Pending**, 0 approved. YT Japan, YT Hong Kong, IG Japan, IG Hong Kong, TikTok Japan, TikTok Hong Kong. |
| Earnings | $0.00 realized (0 approved), $0.02 projected (6 pending). |
| Watchdog / health | Watchdog + health alerts live. `health.json` at shutdown: YouTube unhealthy (last post Nov 16 21:00), Instagram healthy (last post Nov 17 13:37), TikTok `known_broken` (never alerts). |
| Accounts | IG `@clippedaily31`, TikTok `@clips.daily548`, YouTube `@Clippedaily31`, email `clippedaily31@gmail.com`. Post ONLY to these accounts, never a personal account. |
| License key | ClipForge signing key at `/home/abel/.config/clipforge/license-private.key` (0600, abel-only). **Never committed, never deleted.** Back it up to a 1Password Secure Note named "ClipForge license signing key" (paste from `sudo -n -u abel cat` — never into chat or a file). |

### Famous clips source (added Nov 17, 2026)

`queue_seed.py` gained a second source alongside throwbacks: each
watchlist Twitch channel's top clips by view count, fetched via the
existing Twitch GQL path with the same client ID. Verified live: the
GQL `ClipsSort` enum has no `VIEWS` value, and `TRENDING` returns recent
low-view clips — but **no sort criteria at all returns clips in
views-descending order**. Round-robin across the 8 Twitch channels, top
30 per channel per fetch, 6h cache. Downloads via TwitchDownloaderCLI
`clipdownload`, cut 30s + TikTok variant with the current cutter
framing. The clip title doubles as the on-screen hook (no Whisper run).
TikTok variant only for clips >= 110s; shorter ones use the poster's
30s fallback. Famous entries carry `source: "famous"`, `views`,
`clip_slug`, insert at the **front** of the pending queue (the FIFO
poster picks one next with no poster change), and the maintainer keeps
>= 8 famous pending. Throwbacks keep running behind them — famous mixes
in, it does not replace throwbacks. Campaign exclusion extends to famous
clips: iShowSpeed clips from 2026-11-06 or with Expedia in the title are
skipped (GQL clips carry no source-VOD id, so date + title is the
guard). Run it by hand: `python3 queue_seed.py --seed-famous N`.
Supply is the top 30 per channel (~240 clips, ~5 days at full post
rate); when exhausted the queue falls back to throwbacks until new clips
crack the top 30.

## Instagram originality — read this before restarting

On Nov 17, 2026 Instagram flagged `@clippedaily31` as unoriginal and
removed recommendation eligibility to non-followers. This was not a
one-post problem: the account mostly reposts other people's clips, and
Instagram's rule (April 30, 2024 for Reels, extended to photos and
carousels April 30, 2026) removes accounts that primarily post
unoriginal content from recommendations until most of their posts in a
rolling 30-day window are original. Famous clips are the easiest for
Instagram to match to the original, so the famous-clips source made the
flag more likely, not less.

What Instagram counts as original (from its own Original Content
Guidelines, verified Nov 17, 2026):

- **Counts:** content you wholly created or that reflects your unique
  perspective; third-party content "materially edited" when "your
  addition meaningfully enhances" it. Examples that count: overlaid text
  that does more than describe, narration / storyline / creative
  graphics that re-contextualise or add information, meme transformation
  (humour, social commentary, cultural reference, relatable take),
  a new voiceover, a Remix expressing a reaction, a parody compilation.
  Instagram's removal test: "if someone could remove your contribution
  … and the content would virtually be the same, it probably needs more
  of you in it."
- **Does NOT count** (Instagram's named list of six "minor and immaterial
  edits"): (1) borders, (2) logos / watermarks / attribution in the reel
  or caption, (3) overlaid reactions with minimal or superficial
  commentary, (4) purely descriptive text summaries, (5) stickers / GIFs
  / unrelated visuals, (6) same-language subtitle transcripts. Plus
  speed changes. Caption credit and the streamer's permission do NOT make
  a repost original. The clipsdaily hook overlay (which restates the
  moment) and the caption naming the streamer are both on this list.

What this means for a restart:

1. **Do not resume plain reposts.** The account will stay out of
   recommendations, and every new repost keeps the 30-day window full of
   unoriginal posts. The way back Instagram documents is a month where
   most posts are original.
2. **Deleting or archiving the flagged posts does not fix it.** The flag
   screen says so, and Instagram's guidance agrees — recovery is about
   what you post next, not what you remove.
3. **Requesting a review is weak on these facts.** The review ("Disagree
   with decision") is for mistakes; the content genuinely is reposted.
   No clip account with a documented successful appeal was found.
4. **Collabs credit the creator but do not cure the flag.** Instagram
   lists collabs for posts you had a role in creating. It has never said
   a collab counts as original in the 30-day majority, and no account was
   found recovering via collabs. Use collabs selectively for credit and
   relationships, not as the fix.
5. **Formats that can work** (ranked for this pipeline): (a) voiceover
   commentary with a per-clip, fact-specific script that adds context or
   a point of view — the best automatable bet (human voiceover is
   stronger than AI; an AI voiceover needs Meta's AI label, and
   Instagram has never said an AI voice counts as a "new voiceover");
   narrating what happens on screen does not count. (b) Narrated Top-5
   compilations (60–90s) with a storyline, 2–3x/week. (c) Filmed
   green-screen / face-cam commentary in your own words — strongest,
   not automatable. Silent or superficial reactions do not count.
6. **YouTube and TikTok are separate.** YouTube's reused-content rules
   affect monetization more than Shorts discovery; TikTok was already
   blocked for unrelated reasons. The Instagram fix does not have to
   block the other platforms — but the same clip posted to Instagram
   must be transformed if Instagram is to recommend it again.

## Fresh-server restart procedure

### 0. Prerequisites (operator)

- A Linux host ("indra" in the original setup) with 8+ cores, 12 GB
  RAM, 500 GB+ free disk (59 GB of live state at shutdown, mostly
  video), and a stable IP. The pipeline posts 2 clips/hour; the
  heaviest job is Whisper transcription (CPU).
- SSH access to that host. In the original setup indra was reached over
  Tailscale (`100.78.151.90`, user `friday`, key
  `~/.ssh/id_ed25519`, `UserKnownHostsFile=/home/hatch/.ssh/known_hosts`)
  through an HTTP CONNECT proxy helper (`ssh-tail-proxy.py`, port 3130).
  Any SSH route works; the proxy is specific to the original operator VM.
- An operator machine (any machine with a browser) for the Instagram
  `instagram-cli` route and the Content Rewards browser tasks, if you
  use them. The indra IG poster replaces the operator route once its
  session exists.
- Git, `uv` (Python package manager), Node 24 (ads only).

### 1. Clone and install the CLI

```bash
git clone https://github.com/abelprasad/clipsdaily.git
cd clipsdaily
bash install.sh --local        # pip install -e . from this checkout
# or: pipx install git+https://github.com/abelprasad/clipsdaily.git
./setup.sh                     # heavy system deps: ffmpeg, playwright
                               # chromium, TwitchDownloaderCLI
```

`install.sh` and `setup.sh` are idempotent. The console scripts are
`clipsdaily` and `clipforge` (both point at `clipsdaily.cli:main`).
Verify: `clipsdaily --help` lists run, post, queue, campaign, submit,
earnings, auth. `make check` verifies VERSION matches the package;
`make test` runs the suite; `bash scripts/check-secrets.sh` must pass
before any commit.

### 2. System dependencies

- `ffmpeg` (v9 in `setup.sh`), `streamlink==8.6.3` (recording),
  `TwitchDownloaderCLI` at `~/.local/bin/TwitchDownloaderCLI` (VOD
  downloads and clip downloads), `yt-dlp` (helper binary).
- Python packages: `requirements.txt` (pinned where the live versions
  are known). Transcription uses `faster-whisper` (CPU, ~4x faster than
  openai-whisper; the old `openai-whisper` pin remains in requirements
  only for reference — the cutter imports `faster_whisper`).
- `uv` + uv-managed Python 3.13: `uv` at `~/.local/bin/uv`, Python
  3.13.18 at `~/.local/share/uv/python/cpython-3.13-linux-x86_64-gnu/`.
  System Python 3.10 works for the main pipeline; the IG poster venv
  needs Python >= 3.11.
- Node 24 + npm (ads only, see below).

### 3. Runtime home and config

```bash
# Runtime home (deploy.sh does this; by hand:
mkdir -p /home/abel/clipsdaily
cp config/config.yaml.example /home/abel/clipsdaily/config.yaml
cp config/campaigns.example.json /home/abel/clipsdaily/campaigns.json   # if using campaigns
```

Edit `config.yaml`: the watchlist (10 streamers, Twitch + Kick),
`max_clips_per_day: 20`, `clip_length_seconds: 30`, spike thresholds,
`platforms:` (youtube / tiktok / instagram toggles),
`tiktok_api: false` / `tiktok_api_mode: direct` (see Auth), and the
retention / cleanup settings. The example file documents every key.
Never commit the live `config.yaml` — it is gitignored; the example is
the template.

Deploy from the repo (preferred — backs up, copies, restarts):

```bash
bash deploy.sh --dry-run   # prints the plan, changes nothing
bash deploy.sh             # deploy + restart tmux sessions
```

Never edit the live dir by hand; the repo is the dev copy and
`deploy.sh` is the only way code reaches the runtime home.

### 4. Auth — recreate every credential from scratch

`.auth/` (mode 0700) is gitignored and was never copied. Nothing below
has a value in this repo; recreate each on the machine that will run
the pipeline, per `docs/AUTH.md` (and `TIKTOK_API_SETUP.md`,
`TIKTOK_APP_PACKET.md` for TikTok).

| Credential | Where it lives | How to create it |
|---|---|---|
| YouTube OAuth client | `.auth/youtube_client_secrets.json` | Google Cloud Console: create a Desktop-app OAuth client for the channel's Google account. **Re-enable the client first** — it was DISABLED at shutdown (see above). Scopes: `youtube.upload` + `youtube.readonly` only (delete needs the full `youtube` scope; the pipeline deletes from Studio instead). Then run the OAuth flow (`auth_youtube.py`); the refresh token lands in `.auth/youtube_token.json`. |
| YouTube OAuth token | `.auth/youtube_token.json` | Created by the flow above. Auto-refreshes; in Testing-mode apps the refresh token expires in 7 days, so publish the OAuth app to Production or re-auth weekly. |
| TikTok cookies (legacy route) | `.auth/tiktok_cookies.txt` | Netscape-format cookie export from the operator's browser, signed in to `@clips.daily548`. **Dead at shutdown** — TikTok blocked auto-posting account-wide; do not rely on this route. |
| TikTok API client | `.auth/tiktok_api_client.json` | developers.tiktok.com: sign in as `@clips.daily548` via Google (`clippedaily31@gmail.com`) — never the saved `tiktok.com` password. Create app "Clips Daily" with the packet values in `TIKTOK_APP_PACKET.md` (scopes `user.info.basic` + `video.upload` + `video.publish` only, redirect `http://localhost:8080/`). Submit for review, then separately request the Content Posting API audit. Until the audit passes, every Direct Post is forced private (`SELF_ONLY`) and the account must be private — **do not flip `@clips.daily548` to private** (it is public). Fallbacks if refused: draft mode (no audit, 5/day, tap publish by hand), cookies, or a paid scheduler. Privacy/terms pages for the app live at `abelprasad.dev/clipsdaily/` (`/privacy.html`, `/terms.html`). |
| TikTok API token | `.auth/tiktok_api_token.json` (managed by `tiktok_api.py`) | Created by the OAuth + PKCE flow in `tiktok_api.py`. Access token 2h, auto-refreshed; refresh token rotates, 180 days. |
| Instagram session (indra poster) | `.auth/instagram_session.json` (0600) | Export a `cookies.txt` from a desktop browser signed in to `@clippedaily31`, then on indra: `python3 auth_ig_session.py <cookies.txt>`. It imports the sessionid only (verifies the account id), writes the session file, never prints the sessionid and never copies the cookies file. Delete the exported cookies file afterwards. Sessions last days–weeks; re-import when the poster logs "session missing". |
| Instagram password login (fallback) | env `CLIPSDAILY_IG_PASS` (never on disk) | `CLIPSDAILY_IG_PASS='...' python3 auth_instagram.py` — needs instagrapi >= 3.2.15 (see below). Password login can still be blocked by Instagram (CAA/Bloks 404s, HTTP 429 on fresh logins, datacentre IPs). The session-cookie import above is the recommended route. |
| Instagram (operator VM route) | Meta Accounts Center link + `instagram-cli` | `instagram-cli` needs glibc 2.39 and a local privsep socket — it only runs on the original operator VM. Sign in via the Accounts Center link, not a password. This route is superseded by the indra poster once its session exists. |
| Twitch GQL client ID | Hardcoded in `queue_seed.py` / `find_vods.py` | `kimne78kx3ncx6brgo4mv6wki5h1ko` — Twitch's public web client ID (the same one the Twitch web client uses). It is a public identifier, not a secret; replace it with any other public web client ID if it stops working. |

Verify auth without posting: `python -m clipsdaily.cli` / `clipsdaily
auth` / `poster.py --check` reports each platform READY / NOT READY.

### 5. IG poster venv (instagrapi 3.2.15)

The system Python is 3.10 and system instagrapi is 3.1.0 — do not use
either for Instagram. instagrapi 3.1.0 cannot log in: its
`password_publickeys` call hits the dead `qe/sync/` endpoint. The bug
was fixed upstream in 3.2.3 (key now fetched from `launcher/sync/`),
and 3.2.15 (Nov 15, 2026, Python >= 3.11) is the pinned version.

```bash
cd /home/abel/clipsdaily
uv venv .venv-ig --python 3.13
.venv-ig/bin/pip install "instagrapi==3.2.15"
.venv-ig/bin/python -c "from instagrapi import Client; print(Client().password_publickeys())"
# ^ prints a (key id, public key) tuple — that proves the launcher/sync
# fetch works from this host. It logs in with no credentials.
```

Systemd units (in `systemd/`, installed by `deploy.sh` or by hand
under `~/.config/systemd/user/`; enable linger first:
`loginctl enable-linger $USER`):

- `clipsdaily-ig-post.service` — oneshot,
  `ExecStart=/home/abel/clipsdaily/.venv-ig/bin/python
  /home/abel/clipsdaily/ig_post_staged.py`
- `clipsdaily-ig-post.timer` — `OnCalendar=*:05,35`, `Persistent=true`

### 6. Start the pipeline (tmux)

```bash
cd /home/abel/clipsdaily
tmux new-session -d -s clipsdaily \
  'python3 runner.py 2>&1 | tee -a logs/runner-$(date +%Y%m%d).log'
tmux new-session -d -s clipsdaily-hourly \
  'python3 hourly_poster.py 2>&1 | tee -a logs/hourly-$(date +%Y%m%d).log'
tmux new-session -d -s clipsdaily-queue \
  'python3 queue_seed.py --maintain 2>&1 | tee -a logs/queue-$(date +%Y%m%d).log'
```

The watchdog restarts any of these if they die (see below). To stop
everything: `touch STOP` in the runtime home, then kill the sessions.

Seed the queue by hand if it is empty:

```bash
python3 queue_seed.py --seed 24            # throwbacks, until 24 pending
python3 queue_seed.py --seed-famous 8      # famous clips, until 8 pending
```

### 7. Watchdog + health

```bash
systemctl --user enable --now clipsdaily-watchdog.service
# unit: ExecStart=/usr/bin/python3 /home/abel/clipsdaily/watchdog.py, Restart=always
```

The watchdog loops every 60s (restarts dead tmux sessions with the exact
commands above) and every 30 min runs a health check from on-disk
evidence only: YouTube = a YOUTUBE LIVE line within the last 3 slots;
Instagram = a Reel posted within the last 2h; queue = parses, entries >
0, no id vanished since the last check. Results go to `health.json`;
new failures append one line per episode to `logs/health-alerts.log`.
TikTok is always `known_broken` and never alerts. Note the window-based
check can miss an auth failure for hours (it did for the YouTube
`disabled_client` failure) — check `logs/hourly-*.log` directly when a
platform goes quiet.

### 8. Operator-machine crons (VM side)

These ran as scheduled jobs on the original operator VM. Recreate them
on whatever scheduler the operator uses (cron, systemd, or the
operator's own scheduler). They are the only pieces that run off indra.

| Job | Schedule | What it runs |
|---|---|---|
| IG post (operator route) | every 30 min | `bash scripts/ig-post-staged.sh` — posts the most recently staged Reel from `ig-outbox/` (status `staged`, `ig_slot` within the last hour) via `instagram-cli`. Exit 0 with nothing staged = silent. Only run this OR the indra timer, never both — the `.posted` marker prevents double-posting, but two posters racing is still a bug waiting to happen. |
| Watchdog alerts | every 30 min | Reads `logs/health-alerts.log`, messages the operator only on new alert lines (watermark file, so it stays silent otherwise). |
| Campaign auto-submit | every 15 min | `python3 auto_submit.py` — submits eligible posted campaign clips. |
| Campaign watch | daily | Discovers new Content Rewards campaigns. |
| Earnings | daily | `python3 earnings.py --update && python3 earnings.py --summary`. |

The campaign submit loop needs a logged-in browser session for the
Content Rewards dashboard (Join, submit links, verify Pending +
submission ID). Those steps are human-operated by design — see
`docs/SUBMIT_CRON_BODY.md`, `scripts/submit_cron.sh`,
`scripts/submit_mark.sh`.

### 9. Campaigns (Content Rewards)

- Join in the dashboard first; the pipeline never joins by itself.
- Only the campaign's own footage, inside its allowed window. For the
  Expedia x IShowSpeed campaign: Speed's Nov 6, 2026 stream (Twitch VOD
  `2921253522`) from 2:56:29 to the end of stream. Must mention Expedia
  (major focus) + the destination accurately + `#IShowSpeed`.
- Submit within 30 min of posting. One-strike rule: one bad submission
  bans the account from every campaign permanently — the eligibility
  gate exists for this reason, do not bypass it.
- Payout: $1/1K views, min $10 / max $500 per clip per platform, MVR
  10,000 views. Earnings show once a clip starts paying out.

## ClipForge — the packaged product

The `packaging/` directory + the `packaging/zero-intervention` branch
hold ClipForge, the zero-intervention product built from this pipeline:
one host, no operator VM, no crons on the operator side. Runtime home
`~/clipforge/` (one `config.yaml`, `.auth/` 0700, `queue/`,
`campaign_queue.json`, `ig-outbox/`, `health.json`, `STOP`). Systemd
user units in `systemd/` (`clipforge-runner`, `clipforge-hourly`,
`clipforge-queue`, `clipforge-ig`, `clipforge-watchdog`,
`clipforge-dashboard`, plus campaign-watch / submit / earnings /
cleanup timers). Installer `packaging/install.sh` (idempotent, refuses
the live dir); setup wizard `clipforge setup` (interactive, `--yes` +
env for scripted runs). Dashboard: FastAPI, single server-rendered
page, `127.0.0.1` only. Opt-in auto-update with rollback. Graceful
degradation (TikTok blocked/unconfigured → skip, keep IG/YT).

**License: ClipForge Proprietary License** (root `LICENSE`, "licensed,
not sold"). The repo is public to read; the license forbids
redistribution, resale, and sublicensing. The installer requires
acceptance; beta terms are in `packaging/BETA_TERMS.md`. The signing
keypair: private key `/home/abel/.config/clipforge/license-private.key`
(0600, abel-only, **never committed, never deleted**), public key
`license-public.pem`. The key is not in this repo and must never be.
Back it up to a 1Password Secure Note named "ClipForge license signing
key". If the private key is ever exposed, rotate the public key in
`src/clipsdaily/license.py` and reissue every key. Honest limit: Python
source is readable once shipped; the real moat is the license +
updates/support + speed. Third-party licenses are untouched (e.g.
`skills/motion-design` stays MIT, carved out in the license).

**What cannot be automated** (even in the package): one-time setup
(OAuth flows, TikTok developer review/audit, platform approvals),
credential re-approval when a platform expires a session, and fixing
broken third-party parsers when sites change (Content Rewards HTML,
Kick Pusher endpoints).

## Ads (clipforge-ads/)

The Remotion project in `clipforge-ads/` renders ClipForge promo reels.
Full docs are in `clipforge-ads/README.md`; the short version:

```bash
cd clipforge-ads
npm install
npm run voiceover   # regenerate narration WAVs + timings (after any script edit)
npm run render      # -> out/receipt-reel-v6.mp4
npm run retention-check   # heuristic pre-post check -> docs/retention-v6.txt
```

- A new variant = edit `src/script.json`, then `npm run voiceover` +
  `npm run render`. Voice is Kokoro `af_heart` at speed 1.1 (AI voice
  only, never Abel's voice), in `.venv-kokoro/` (torch CPU,
  `misaki[en]`, spaCy `en_core_web_sm`, espeak-ng).
- v1–v5 are the receipt format (hook → on-screen bill math → cheaper
  alternative → comment-keyword CTA). v6 is the animated-explainer
  format (hook number + rising bar → four-part build → live-vs-VOD
  mechanism → result screen → CTA), 38.1s.
- Run the retention check before posting an ad: it flags pace (>200
  wpm), silence gaps >= 0.5s, end tails > 1.0s, beat holds > 1.0s, visual
  stasis > 4s, and estimates hook payoff. It does NOT score the ad and
  there is no "out of 100" number. It cannot catch layout, claim truth,
  or hook quality — watch the render once by eye.
- **IP rule for ads:** show the outcome only — never source code,
  paths, queue internals, or cutter/ranking logic. Architecture
  diagrams are allowed ONLY at outcome level: named stages (Watcher,
  Cutter, Ranker, Poster), no code/paths/config/thresholds/weights.
- Ads are NOT posted automatically. Abel eyeballs every ad before it
  goes out. No ad version has been posted yet (v1–v6 rendered, none
  live as of Nov 17, 2026).

## What was NOT preserved (and where it lived)

The public repo preserves code, docs, config templates, and state
schemas — never live state, media, or credentials. The following lived
only on indra / the operator VM and were deliberately excluded by
`.gitignore`. They are re-creatable from source (VODs and top clips
still exist on Twitch); the queue contents below are recorded here so a
restart knows what was in flight.

| Not preserved | Where it lived | Size at shutdown | How to rebuild it |
|---|---|---|---|
| Cut clips + TikTok variants | `/home/abel/clipsdaily/queue/clips/` | 1.5 GB | Re-cut: `queue_seed.py --seed` / `--seed-famous` |
| IG outbox (staged Reels) | `/home/abel/clipsdaily/ig-outbox/` (22 dirs) | part of the 59 GB | Re-staged by the hourly poster from the queue |
| Raw recordings + VOD batch clips | `/home/abel/clipsdaily/recordings/`, `clips/` | part of the 59 GB | Re-recorded live; VODs re-downloaded via TwitchDownloaderCLI |
| Chat JSONs for spike detection | `/home/abel/clipsdaily/vod/` | small | Re-downloaded per VOD by `vod.py` |
| Campaign work + submit outbox | `campaign_work/`, `submit-outbox/` | small | Rebuilt by the campaign watcher/cutter |
| Logs + health state | `logs/`, `health.json`, `watchdog-state.json` | small | Regenerated on first run |
| Auth + sessions | `.auth/` (YouTube token + client secrets, TikTok cookies, IG session) | small | Recreated per [Auth](#4-auth--recreate-every-credential-from-scratch) |
| IG poster venv | `.venv-ig/` | ~hundreds of MB | Rebuilt per [step 5](#5-ig-poster-venv-instagrapi-3215) |
| Queue state (snapshot) | `queue/queue.json`, `queue/state.json` | 44 entries | Recorded here: 36 pending (8 famous at front, 28 throwbacks), 7 posted, 1 failed. The pending clips themselves are gone with the media; the famous ones are re-fetchable from Twitch top clips, the throwbacks re-cuttable from their VODs |
| Campaign state | `campaigns.json`, `earnings.json` | small | 6 Expedia clips Pending, 0 approved; $0 realized. Rebuilt by the campaign watcher + earnings job |
| Ads renders + voice models | `clipforge-ads/out/`, `.venv-kokoro/`, `node_modules/`, `voices/` | ~2.3 GB | `npm install`, re-run voiceover + render (see Ads) |
| TikTok no-confirmation screenshots | `tt_*_noconfirm.png` in the live dir | ~15 files, 95 KB each | Diagnostic only; they documented the Nov 15–17 TikTok block. Not needed for a restart |

Total live dir at shutdown: ~59 GB (`/home/abel/clipsdaily/`). The repo
itself is ~8 MB.

## Verification after a restart

1. `python -m compileall -q src` — everything compiles.
2. `clipsdaily --help` and every subcommand `--help` — CLI smoke test
   (the same list CI runs; see `.github/workflows/ci.yml`).
3. `make test` — unit tests (mocked; no network, no live calls).
4. `bash scripts/check-secrets.sh` — must print `secret scan OK`.
5. `python3 watchdog.py --once` — one watchdog + health pass; check
   `health.json` parses and the three tmux sessions are up.
6. `python3 queue_seed.py --seed-famous 1` — one famous clip cuts and
   queues; check `queue/queue.json` has it with `source: "famous"`.
7. Post one clip by hand (`post_one.py` / `clipsdaily post one`) and
   verify it lands on the target platform before letting the hourly
   poster run unattended.
8. For Instagram specifically: post one transformed clip (see the
   originality section) and check Account Status → recommendation
   eligibility before resuming any cadence.

## Repo map

| Path | What it is |
|---|---|
| `src/clipsdaily/` | Pipeline code (package layout). Core: `runner.py`, `recorder.py`, `chat.py`, `cutter.py`, `poster.py`, `cleanup.py`, `vod.py`, `queue_seed.py`, `hourly_poster.py`, `campaign_watcher.py`, `campaigns.py`, `campaign_cut.py`, `eligibility_gate.py`, `auto_submit.py`, `earnings.py`, `auth_*.py`, `tiktok_api.py`, `ig_post_staged.py`, `auth_ig_session.py`. `patch_*.py`, `post_*.py`, `tt_*.py`, `recut_*.py` are historical one-offs, already applied — do not re-run blindly. `restart_maintainer.py` is stale and destructive (wipes `queue.json`) — **never run it**. `sync_repo.py` syncs the live dir into this repo (preservation tool, not a runtime piece). |
| `clipforge-ads/` | Remotion ad project (v1–v6 + retention check). Its own README, its own ADRs under `clipforge-ads/docs/adr/`. |
| `packaging/` | ClipForge product distribution: installer, LICENSE, BETA_TERMS.md, keygen tool. |
| `systemd/` | User units + timers (live clipsdaily units and ClipForge units). |
| `scripts/` | Operator-machine helpers: `ig-post-staged.sh` (Instagram cron), `submit_cron.sh`, `submit_mark.sh`, `check-secrets.sh`. |
| `config/` | `config.yaml.example`, `campaigns.example.json` (templates; copy to `config.yaml` / `campaigns.json`). |
| `docs/` | `adr/` (architecture decision log, `adr/README.md` is the index), `RESTART.md` (this file), `AUTOMATION.md`, `CAPTIONS.md`, `campaigns.md`, `TIKTOK.md`, `AUTH.md`, `operations.md`, `PATHS.md`, `SUBMIT_CRON_BODY.md`, `earnings_dump_spec.md`, `youtube-vod-notes.md`. |
| `tests/` | Unit tests (mocked; `test_queue_seed_famous.py` covers the famous-clips source). |
| `skills/` | `clipsdaily/` skill + `motion-design/` (vendored, MIT). |
| `plugins/clipsdaily/` | Claude Code plugin (slash commands + skill). |
| `deploy.sh`, `install.sh`, `setup.sh` | Deploy to live, install the CLI, install system deps. |
| `assets/` | `clipsdaily-logo.jpg` (brand logo). |
