# Configuration

## Runtime home

Runtime state lives in the **runtime home**: `$CLIPSDAILY_HOME` when set, else the current working directory. Run the CLI from the runtime home, or pass `--home`:

```bash
clipsdaily --home /home/abel/clipsdaily run
```

The runtime home holds `config.yaml`, `campaigns.json`, `queue/`, `ig-outbox/`, `clips/`, `vod/`, `recordings/`, `logs/`, `campaign_queue.json`, `submit-outbox/`, `earnings.json`, `.auth/`, and the `STOP` file. None of it is in git — a fresh clone generates its own state by running the pipeline.

## config.yaml

See `examples/config.yaml` (same as `config/config.yaml.example`). Key knobs:

| Key | What it does |
|---|---|
| `streamers` | Watchlist: Twitch channels (by name + numeric id) and Kick channels (by chatroom id). 8 concurrent recordings max. |
| `platforms.youtube / .tiktok / .instagram` | Flip a platform on only after its auth is ready. All start `false`. |
| `accounts.instagram / .tiktok / .youtube` | The clipsdaily account handles. Never point these at a personal account. |
| `limits.daily_uploads` | Daily cap (default 20). YouTube also has its own daily upload limit (~8/day on this channel). |
| `limits.disk_min_gb` | Disk guard (default 50 GB free) — below it, the runner stops new recordings. |
| `clips.tiktok_min_seconds` | TikTok variant minimum (60s — Creator Rewards only pays 60s+ videos). The poster refuses any file under 60s for TikTok. |
| `clips.default_length` | 30s for Shorts/Reels. |

## campaigns.json

Campaign state, written by the watcher (`clipsdaily campaign watch --check`). Starts as an empty object; do not hand-edit it. The schema example is in `config/campaigns.example.json` (marked EXAMPLE ONLY — do not submit against it).

## Environment

| Variable | What it does |
|---|---|
| `CLIPSDAILY_HOME` | Runtime home (default: cwd). |
| `CLIPSDAILY_LIVE_DIR` | Live dir for `deploy.sh` (default `/home/abel/clipsdaily`). |
