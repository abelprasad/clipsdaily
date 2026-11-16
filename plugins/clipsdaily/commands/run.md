---
description: Run the live clipsdaily runner (record + chat spikes + cut + post) or check its state
---

Run the live clipsdaily pipeline. The runner records the watchlist streams, finds chat spikes, cuts 30s vertical clips, and posts them.

## Run it

```bash
clipsdaily run
```

Run detached in tmux on the server (indra), from the runtime home:

```bash
tmux new -s clipsdaily
cd /home/abel/clipsdaily && clipsdaily run
# Ctrl-B then D to detach
```

## Check it is running

```bash
tmux ls | grep clipsdaily
tail -50 /home/abel/clipsdaily/logs/runner-*.log | tail -20
```

## Stop it

Kill switch — never `kill` the process directly:

```bash
touch /home/abel/clipsdaily/STOP
```

The runner exits cleanly on the next loop. Remove the STOP file before restarting.

## Rules

- The repo is the dev copy; the live dir is `/home/abel/clipsdaily`. Never edit the live dir by hand — deploy with `bash deploy.sh`.
- The runner's clips currently ship hook-less (known gap, see ROADMAP.md) — do not "fix" that by editing the live dir.
- If the runner is mid-cadence, do not restart it for a code change. Restart at a slot boundary.
