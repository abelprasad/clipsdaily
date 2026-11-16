# Installation

## Plugin first (Claude Code)

The plugin is the recommended install for Claude Code users — see [INSTALL.md](../INSTALL.md):

```
/plugin marketplace add abelprasad/clipsdaily
/plugin install clipsdaily@abelprasad
```

Copy-install instead: `bash scripts/install.sh` (or `.\scripts\install.ps1` on Windows), `--all` / `-All` for every detected harness.

## Requirements

- Python 3.10+
- ffmpeg 9+ (the cutter needs modern filters; system ffmpeg 4.4 is too old)
- streamlink, yt-dlp, TwitchDownloaderCLI (in `~/.local/bin/`)
- Playwright + Chromium (TikTok poster)
- ~11 GB RAM for Whisper; 50 GB free disk (the runner stops below that)

## One-command install (once pushed)

```bash
pipx install git+https://github.com/abelprasad/clipsdaily.git
```

Or the convenience wrapper (same thing, plus a local mode):

```bash
bash install.sh            # pipx install from the git URL
bash install.sh --local    # pip install -e . from this checkout
```

## From source

```bash
git clone https://github.com/abelprasad/clipsdaily.git
cd clipsdaily
bash setup.sh        # system deps (ffmpeg 9 via micromamba, streamlink,
                     # whisper, posters, runtime dirs) + editable install
```

`setup.sh` installs the package editable (`pip install --user -e . --no-deps`), so `clipsdaily` is on PATH and edits to the repo take effect immediately.

## System deps, in detail

- **ffmpeg 9:** installed via micromamba (conda-forge) at `~/.micromamba/envs/ffmpeg-env/`, symlinked as `~/.local/bin/ffmpeg` and `~/.local/bin/ffprobe` (first on PATH via `.bashrc`; non-interactive contexts need `PATH=$HOME/.local/bin:$PATH`). Includes drawtext, libsvtav1, libass, fontconfig. System `/usr/bin/ffmpeg` stays 4.4.2.
- **streamlink 8.6.3** at `~/.local/bin/streamlink`.
- **Whisper** (openai-whisper, torch CPU) — installed by `setup.sh`.
- **Playwright + Chromium** — `playwright install chromium` (TikTok poster).
- **TwitchDownloaderCLI 1.56.5** at `~/.local/bin/TwitchDownloaderCLI` (VOD fallback).

## Verify

```bash
clipsdaily --help
clipsdaily --version        # 0.1.0
clipsdaily auth check       # read-only
bash test_e2e.sh            # full smoke test (needs network)
```

## Uninstall

```bash
pipx uninstall clipsdaily
# or: pip uninstall clipsdaily
```

Runtime state (clips, queue, auth) lives in the runtime home and is untouched by uninstalling the package.
