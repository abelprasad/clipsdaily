# Operations — tmux sessions, cadence, crons, runbook

## Processes (tmux, on the pipeline host)

| Session | Command | What it does |
|---|---|---|
| `clipsdaily` | `python3 runner.py` | Live loop: records live streams, detects spikes, cuts, posts via `poster.py`. |
| `clipsdaily-queue` | `python3 queue_seed.py --maintain` | Maintainer: seeds the hourly queue from recent VODs (chat-spike ranking, throwback labels), cuts 30s + TikTok variants. Target 24 pending. |
| `clipsdaily-hourly` | `python3 hourly_poster.py` | Posts 2 clips/hour at :00 and :30 (YouTube + TikTok), stages Instagram to `ig-outbox/`. |

Start each in its own tmux session so it survives disconnects.
Restart by killing the session and starting a fresh one with the
same command. (Do NOT use `restart_maintainer.py` — stale one-off
that wipes `queue.json`.) The runner and maintainer hold their
modules in memory: after editing `cutter.py`, `poster.py`, or
`queue_seed.py`, restart the affected sessions or the change will
not take effect.

## Cadence

- 2 clips/hour: slots :00 and :30. YouTube + TikTok post from
  the pipeline host; Instagram is staged to
  `ig-outbox/<clip-id>/` and posted at :05/:35 by the
  operator-machine script `scripts/ig-post-staged.sh` (cron
  every 30 min, needs `instagram-cli`).
- Queue targets: seed ≥24 pending, keep cutting whenever
  pending drops below 12. 48 posts/day at full cadence.
- A platform marked FAILED in a slot is resolved, not retried
  forever — the entry must not sit "partial" forever and block
  the queue. Failed platforms do not retry indefinitely.
- The hourly poster does NOT yet prefer `campaign_queue.json`
  when a campaign is active (wiring pending approval). Campaign
  cuts would sit unposted — see `docs/AUTOMATION.md`.

## Limits

- Max 20 clips/day (posting cap in `config.yaml`).
- Max 1 clip per streamer per 5 minutes (cooldown, shared
  across platforms).
- 8 concurrent recordings max (8 cores, 11 GB RAM).
- YouTube daily upload limit: observed Nov 15 (9th upload of
  the day failed with `uploadLimitExceeded`). Resets ~03:00
  EST. Staged clips wait for the next day.
- Disk guard: 50 GB free. Below it, the runner stops new
  recordings, finishes and posts what is queued, cleans up
  aggressively.

## Kill switch

`touch STOP` in the repo root pauses all posting immediately.
`rm STOP` resumes. The runner checks for the file each loop.

## Cleanup (cleanup.py, hourly + on startup)

- Raw recordings: deleted immediately after cutting (48h sweep
  is a crash backstop).
- Posted clips: deleted after 24h max. Unposted clips: max 48h.
- Temp files every run; logs older than 7 days deleted.
- Log: `logs/cleanup.log`. Manual run: `python3 cleanup.py`.

## Crons (operator machine)

| Job | Schedule | What it does |
|---|---|---|
| Instagram poster | Every 30 min | `scripts/ig-post-staged.sh` — posts the most recently staged Reel, marks it posted on the host. Silent unless a post fails. |
| Auto-submit | Every 15 min | `scripts/submit_cron.sh` — scans the host for newly posted campaign clips (re-gating each), prints pending jobs; the operator submits each in the browser, verifies Pending + submission ID, marks via `scripts/submit_mark.sh`. |
| Campaign watch | Daily ~09:53 | `campaign_watcher.py --check` on the host; one browser task per join request (verify the green Joined badge). |
| Earnings | Daily ~21:53 | Browser dump of the submissions dashboard → `earnings_dump.json` on the host → `earnings.py --update` → one-line summary. |

Full install instructions: `docs/SUBMIT_CRON_BODY.md`.
Earnings dump format: `docs/earnings_dump_spec.md`.

## Logs

- `logs/runner-<date>.log`, `logs/hourly-<date>.log`,
  `logs/queue-<date>.log`, `logs/cleanup.log`,
  `logs/posted.jsonl`, `campaigns.log`, `campaign_cut.log`.
- Queue state: `queue/queue.json` (manifest) +
  `queue/state.json` (done spikes, VOD cursors). Never edit
  these by hand while the maintainer is running.

## VOD batch (manual)

```bash
python3 vod_batch.py   # latest completed VODs, top spikes, batch cap 6
python3 vod.py https://www.twitch.tv/videos/<id> --max-clips 5
```

VOD clips are throwbacks: captions lead with
`Throwback — <streamer>: <moment>` + stream date when known.
Old footage is a feature, not a flaw. Do not submit VOD clips
to Content Rewards unless they are campaign clips that pass
the gate.

## First-run checklist

1. `bash setup.sh`, copy `config/config.yaml.example` to
   `config.yaml` (platforms all false).
2. Auth per `docs/AUTH.md`; `python3 poster.py --check`.
3. Flip one platform to `true` in `config.yaml`, only after
   `--check` reports it OK.
4. Start the three tmux sessions. Watch `logs/` for the first
   spike-to-clip round trip.
5. Instagram needs the operator cron (`scripts/ig-post-staged.sh`)
   on a machine with `instagram-cli`; TikTok needs a fresh
   cookie export when a post fails on auth.
