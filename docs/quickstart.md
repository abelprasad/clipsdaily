# Quickstart

Get from zero to a running pipeline in about 15 minutes (plus auth, which is the slow part — see [Installation](installation.md) and [AUTH](AUTH.md)).

## 1. Install

```bash
pipx install git+https://github.com/abelprasad/clipsdaily.git
```

Once the repo is pushed to GitHub. Until then, from a clone:

```bash
git clone <repo> clipsdaily
cd clipsdaily
bash install.sh --local
```

Then the system deps:

```bash
bash setup.sh
```

## 2. Configure

```bash
cp config/config.yaml.example config.yaml
cp config/campaigns.example.json campaigns.json   # starts empty; the watcher fills it
```

Edit `config.yaml` for your watchlist. All platforms start OFF — nothing posts until you flip one on and auth it.

## 3. Auth (human steps)

See [AUTH](AUTH.md): YouTube OAuth (Desktop app, `youtube.upload` scope), TikTok cookie export, Instagram via the operator CLI. Then:

```bash
clipsdaily auth check        # read-only, posts nothing
```

## 4. Run

```bash
tmux new -s clipsdaily
clipsdaily run               # live recorder + poster
# Ctrl-B then D to detach
```

Start the other two sessions too:

```bash
tmux new -s clipsdaily-queue
clipsdaily queue maintain    # VOD-seeded hourly queue

tmux new -s clipsdaily-hourly
clipsdaily post hourly       # 2 clips/hour poster
```

## 5. Check it works

```bash
clipsdaily queue status
clipsdaily status            # (Claude Code plugin) whole-pipeline health check
```

Stop everything with the kill switch: `touch STOP` in the runtime home.
