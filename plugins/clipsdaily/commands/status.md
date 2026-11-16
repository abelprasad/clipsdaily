---
description: clipsdaily status — queue, processes, auth, and earnings in one look
---

Quick health check for the clipsdaily pipeline. Run the checks, then report what is actually running vs what should be.

## Queue

```bash
clipsdaily queue status
```

## Processes (on indra)

```bash
tmux ls
tail -5 /home/abel/clipsdaily/logs/runner-*.log
tail -5 /home/abel/clipsdaily/logs/hourly-*.log
```

Expected sessions: `clipsdaily` (runner), `clipsdaily-queue` (maintainer), `clipsdaily-hourly` (hourly poster).

## Auth

```bash
clipsdaily auth check
```

Read-only: reports whether YouTube / TikTok / Instagram auth is ready. Posts nothing.

## Earnings

```bash
clipsdaily earnings
```

## Rules

- Report what you observed, not what should be true. A session missing from `tmux ls` is down — say so, don't assume it will come back.
- If TikTok shows failed posts, that is the known block (docs/TIKTOK.md) — report it, don't retry.
- If the runner is mid-cadence, do not restart anything to "fix" the status output.
