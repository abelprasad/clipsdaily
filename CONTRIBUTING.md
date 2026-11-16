# Contributing

## Setup

```bash
git clone https://github.com/abelprasad/clipsdaily.git   # once pushed; until then clone the local repo
cd clipsdaily
bash setup.sh        # system deps (ffmpeg 9, streamlink, whisper, posters)
make install         # editable install: `clipsdaily` on PATH
```

Auth is per-operator and never committed: see `docs/AUTH.md`.

## Before you push

```bash
make lint            # compile all .py + secret scan
make check           # VERSION file matches the package version
make test            # full e2e smoke test (needs network)
```

`make lint` is the minimum before every commit. CI runs the same
checks on every push.

## How work happens here

- **This repo is the dev copy.** The live pipeline runs at
  `/home/abel/clipsdaily` on indra. Never edit the live dir by hand;
  deploy with `bash deploy.sh` (dry-run first: `make deploy`).
- **Keep the CLI thin.** New behaviour goes in the pipeline modules
  under `src/clipsdaily/`; `src/clipsdaily/cli.py` only maps
  subcommands to module entry points.
- **Runtime state is not in git.** `queue/`, `ig-outbox/`, `clips/`,
  `vod/`, `recordings/`, `logs/`, `campaign_queue.json`,
  `campaigns.json`, `earnings.json`, `.auth/` are all gitignored.
  A fresh clone generates its own state by running the pipeline.
  See `docs/adr/use-repo-as-dev-copy.md` and
  `docs/adr/keep-live-state-out-of-git.md`.
- **One-off scripts stay one-offs.** The `patch_*.py`, `recut_*.py`,
  `tt_*.py`, `fail_9805_tt.py`, `recover_9805.py`, `diag_tiktok.py`,
  `check_tiktok_profile.py`, `vod_batch.py`, `vod_cut*.py`,
  `make_speech.py`, `cut_speed_expedia.py`, `post_speed.py`,
  `post_tiktok_only.py`, `post_yt_batch.py`, `post_tt_one.py`,
  `motion_test.py`, `framing_test.py`, `find_vods.py`,
  `find_tiktok_video.py`, `tt_verify_hk.py`, `delete_shorts.py`,
  `restart_maintainer.py` files are snapshots of one-time operations
  (Nov 15, 2026). Do not "clean them up" into the pipeline, and do
  not run them against the live dir — several have hardcoded live
  paths and `restart_maintainer.py` wipes `queue.json`.
- **Never run `restart_maintainer.py`.** Restart the maintainer with a
  plain tmux restart instead (see `docs/OPERATIONS.md`).

## Standing rules (do not break these)

- **Full frame, no cropping** — every clip shows the whole 16:9 source
  frame on a 1080x1920 canvas, blurred darkened copy behind it.
- **One-line post captions, no boilerplate, no hashtags** except the
  ones a campaign requires (`#IShowSpeed`).
- **No burned-in word captions** — one big hook overlay at the start
  only (~3s), hook at y=300.
- **Strict eligibility gate** — `eligibility_gate.py` must PASS before
  any campaign clip posts or submits. Borderline = blocked.
- **Never submit a clip twice, or past 30 minutes after posting.**
- **Credit the streamer** in every post.
- **Clipsdaily accounts only** — never point this at a personal account.
- **TikTok auto-posting is blocked** (see `docs/TIKTOK.md`) — don't
  "fix" it by hammering retries; retries deepen the throttle.

## Architecture decisions

Any decision that changes how the pipeline works gets an ADR in
`docs/adr/` (Nygard template, immutable — supersede, don't rewrite).
See `docs/adr/README.md`.

## Releases

Version in `src/clipsdaily/__init__.py` + `VERSION` (keep in sync,
`make check` verifies). Tag `vX.Y.Z` on main. First release: v0.1.0.
