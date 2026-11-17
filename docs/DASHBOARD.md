# ClipForge dashboard

Local web GUI for the ClipForge pipeline running on the customer's own
box. One page, six sections: **Watchlist, Queue, Post history, Health,
Settings, Logs**. No frontend build step: FastAPI serves one
server-rendered page (`src/clipsdaily/dashboard.py`).

## What it covers

| Section | Source (read) | What you see |
|---|---|---|
| Watchlist | `config.yaml` + `logs/runner-state.json` | Streamers (platform + channel), add/remove. Shows the runner's *effective* watchlist plus `config_mtime` / `config_loaded_at`, so you can see a change land without a restart. |
| Queue | `queue/queue.json` (**read-only**) | Entries grouped pending / posted / failed / partial, with per-platform status (`yt_url`, `tt_url`, retries, streamer, `created_at`). |
| Post history | `logs/hourly-*.log` + `ig-outbox/*/.posted` | Latest 50 posts: clip id, platform, link, time. Log lines are the `YOUTUBE LIVE` / `TIKTOK LIVE` lines; IG entries carry `media_fbid` + `posted_at_utc`. |
| Health | `health.json` (+ `watchdog-state.json` if present) | Each platform + last-post time + status color (green healthy/idle, red unhealthy, amber known-broken). |
| Settings | `config.yaml` | YouTube slot hours (shown, not editable in v1 — they are fixed in the hourly poster), `max_clips_per_day`, spike cooldown, queue-clip retention, platform toggles, captions rule (one line, no hashtags — displayed, not editable), kill switch. |
| Logs | `logs/*.log` | Latest 200 lines total, HTML-escaped. |

## How to start it

```bash
cd ~/clipforge            # the runtime home (or set CLIPSDAILY_HOME)
python3 -m clipsdaily.dashboard --port 8787
# -> http://127.0.0.1:8787
```

Port: `--port` (default `8787`, or `CLIPFORGE_DASHBOARD_PORT`).
Runtime home: exactly like the rest of the package,
`$CLIPSDAILY_HOME` else the current working directory
(`clipsdaily.paths.runtime_home()`). Never point it at the repo
checkout.

As a service (installed by the installer; do not enable by hand
against the live directory):

```bash
systemctl --user enable --now clipforge-dashboard.service
```

Unit: `systemd/clipforge-dashboard.service` (`Restart=on-failure`,
`WorkingDirectory=%h/clipforge`).

## Localhost-only, and remote access

The dashboard binds **127.0.0.1 only** and refuses any non-loopback
`--host`. There is **no auth in v1**: anything that can reach the
port is trusted, and on this box that means only local processes.

For remote access, put it behind a tunnel — do not expose the port
directly. Documented route (not implemented by the dashboard):

```bash
# Example: Cloudflare Tunnel (or Tailscale Serve / ssh -L).
# Tunnel a hostname to http://127.0.0.1:8787, then put the tunnel
# itself behind Cloudflare Access / Tailscale ACLs so only you can
# reach it. The dashboard must never listen on 0.0.0.0.
```

Dashboard auth beyond localhost (a token) is a follow-up, not v1.

## Read-safety rules (v1, hard)

- **No queue mutations at all.** No delete, no retry, no re-post.
  The dashboard only ever *reads* `queue/queue.json`.
- **No post buttons, no submit buttons.** Nothing in the GUI can
  post a clip or submit to a campaign, so nothing can post a clip
  twice or bypass the campaign eligibility gate.
- **The only writes are:**
  1. `config.yaml` — validated first (bad YAML / bad channel /
     out-of-range cap is rejected, old file untouched), then written
     atomically (tmp file + `os.replace` in the same directory).
     The runner re-reads it every 60s; no restart needed.
  2. The `STOP` file — create/delete via the kill-switch toggle.
     Reversible by design: delete `STOP` to resume posting.
- Logs are HTML-escaped before rendering. The dashboard never
  prints file contents that could hold secrets, and never echoes
  credentials (it does not read `.auth/` at all).

## Endpoints

| Route | Method | What it does |
|---|---|---|
| `/` | GET | The dashboard page (all six sections). |
| `/api/state` | GET | JSON: config, config_mtime, runner-state, queue counts, health, watchdog-state, stop flag. |
| `/api/queue` | GET | JSON: raw queue entries (read-only). |
| `/api/history` | GET | JSON: latest 50 posts. |
| `/api/logs` | GET | JSON: latest 200 log lines. |
| `/api/watchlist/add` | POST | Form/JSON `{platform: twitch\|kick, channel}` — validates, appends to `config.yaml` (atomic). |
| `/api/watchlist/remove` | POST | Form/JSON `{platform, channel}` — removes from `config.yaml` (atomic). |
| `/api/settings` | POST | Form/JSON: `max_clips_per_day` (1–100), `spike_cooldown_seconds` (0–3600), `queue_clip_retention_days` (0–90), `platform_youtube/tiktok/instagram` toggles. |
| `/api/stop` | POST | Form/JSON `{action: on\|off}` — create/delete `STOP`. |

Anything else (including any `/api/queue/*` mutation) is a 404.
Form posts redirect back to `/` with a notice; JSON posts get
`{"ok": true, ...}` / `{"ok": false, "error": ...}`.

## Tests

```bash
python3 tests/test_dashboard.py   # or: python3 -m unittest tests.test_dashboard -v
```

Spins up the real dashboard on `127.0.0.1:18787` against a scratch
runtime home, checks the page/queue/health/history, then starts the
real branch runner against the same scratch home, adds a streamer
via HTTP POST, and asserts `logs/runner-state.json` shows it within
90s. Also verifies no route mutates `queue.json` (source check +
404s + hash before/after) and that the STOP toggle reverses.
