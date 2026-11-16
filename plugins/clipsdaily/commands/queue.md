---
description: Check the clip queue, run the queue maintainer, or seed clips
---

## Status

```bash
clipsdaily queue status
```

Shows entry counts by status and the next pending clip.

## Maintainer loop (seed >= 24 pending)

```bash
clipsdaily queue maintain
```

Run detached in tmux:

```bash
tmux new -s clipsdaily-queue
cd /home/abel/clipsdaily && clipsdaily queue maintain
```

## Seed once, then exit

```bash
clipsdaily queue seed [N]
```

Cuts clips until N pending (default 24), then exits.

## Rules

- **Never run `restart_maintainer.py`.** It wipes `queue.json` and resets state. Restart the maintainer with a plain tmux restart.
- Queue state (`queue/queue.json`) is live state — it is gitignored and never committed.
- If the queue is empty or stuck, check the maintainer log first (`logs/` in the runtime home) before seeding by hand.
