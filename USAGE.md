# Usage

## The three sessions

The pipeline runs as three tmux sessions on the server (indra), all from the runtime home (`/home/abel/clipsdaily`):

```bash
tmux new -s clipsdaily
clipsdaily run               # live runner: record + spikes + cut + post

tmux new -s clipsdaily-queue
clipsdaily queue maintain    # VOD-seeded hourly queue (seed >= 24)

tmux new -s clipsdaily-hourly
clipsdaily post hourly       # 2 clips/hour poster (slots :00/:30)
```

Instagram is staged to `ig-outbox/` and posted from the operator machine by the 30-min cron (`scripts/ig-post-staged.sh`). Detach with Ctrl-B then D.

## Everyday commands

```bash
clipsdaily queue status              # queue counts + next clip
clipsdaily post now                  # post the next pending clip now
clipsdaily post one <clip-id>        # post one queue clip by id
clipsdaily campaign watch --check    # watch Content Rewards for campaigns
clipsdaily campaign cut --campaign <id> [--max-clips N] [--dry-run]
clipsdaily submit scan               # scan queue for submittable clips
clipsdaily submit list-pending       # pending submit jobs (JSON)
clipsdaily earnings                  # one-line earnings summary
clipsdaily auth check                # read-only auth check
```

Full reference: [docs/cli-reference.md](docs/cli-reference.md) (generated from the real CLI — `make docs` regenerates it).

## Via the Claude Code plugin

| Command | What it does |
|---|---|
| `/clipsdaily:run` | Run / check the live runner |
| `/clipsdaily:post` | Post now / one clip / hourly poster |
| `/clipsdaily:queue` | Queue status / maintainer / seed |
| `/clipsdaily:campaign` | Watch for campaigns / cut campaign clips |
| `/clipsdaily:submit` | Auto-submit outbox (scan / list / mark) |
| `/clipsdaily:earnings` | Earnings summary / update |
| `/clipsdaily:status` | Whole-pipeline health check |

## Stopping

Kill switch — never `kill` the process directly:

```bash
touch STOP        # in the runtime home; the runner exits cleanly on the next loop
rm STOP           # before restarting
```

## Campaigns (the money path)

1. `clipsdaily campaign watch --check` finds campaigns passing all 7 join rules and writes `join_requests.json`.
2. A human joins in the browser (verifies the Joined badge).
3. `clipsdaily campaign cut --campaign <id>` cuts gated clips into `campaign_queue.json`.
4. Post, then submit within 30 minutes: `clipsdaily submit scan` writes the job, the operator submits in the browser, then `clipsdaily submit mark-submitted <job> --submission-id <id>`.

**Never submit without the gate passing, never submit twice, never submit past 30 minutes.** The full rules: [docs/CAMPAIGNS.md](docs/CAMPAIGNS.md) and [SECURITY.md](SECURITY.md).

## Limits

- 2 clips/hour, 48/day max (daily cap 20 in config; YouTube's own daily upload limit is ~8/day on this channel — `uploadLimitExceeded` means wait until ~03:00 EST).
- TikTok auto-posting is currently blocked (throttled session + Playwright bug). Manual phone post works. Do not retry repeatedly. See [docs/TIKTOK.md](docs/TIKTOK.md).
- Disk guard: the runner stops new recordings below 50 GB free.
