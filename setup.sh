#!/bin/bash
# clipsdaily setup — installs deps and creates runtime dirs.
# Tested on Ubuntu 22.04 (indra) with Python 3.10. Safe to re-run.
# It installs nothing that posts, joins, or submits anything.
set -e
cd "$(dirname "$0")"

echo "== python =="
python3 --version || { echo "python3 not found"; exit 1; }
python3 -c "import sys; assert sys.version_info >= (3, 10), 'need python >= 3.10'" \
  || { echo "need python >= 3.10"; exit 1; }
python3 -m pip --version >/dev/null 2>&1 || { echo "pip not found: apt install python3-pip"; exit 1; }

echo "== python deps =="
python3 -m pip install --user -r requirements.txt

echo "== playwright chromium (TikTok poster) =="
python3 -m playwright install chromium 2>/dev/null \
  || echo "WARN: playwright chromium install failed — run 'python3 -m playwright install chromium' manually"

echo "== ffmpeg (need >= 6.1; live route is conda-forge 9.0.2) =="
if command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg on PATH: $(ffmpeg -version 2>/dev/null | head -1)"
else
  echo "no ffmpeg on PATH"
fi
if command -v micromamba >/dev/null 2>&1; then
  echo "micromamba found — installing conda-forge ffmpeg 9 into ffmpeg-env:"
  micromamba create -y -n ffmpeg-env -c conda-forge ffmpeg=9.0.2 || true
  ENV_BIN="$(micromamba env list 2>/dev/null | awk '/ffmpeg-env/ {print $2}')/bin/ffmpeg"
  if [ -x "$ENV_BIN" ]; then
    mkdir -p "$HOME/.local/bin"
    ln -sf "$ENV_BIN" "$HOME/.local/bin/ffmpeg"
    ln -sf "$(dirname "$ENV_BIN")/ffprobe" "$HOME/.local/bin/ffprobe"
    echo "linked $HOME/.local/bin/ffmpeg -> $ENV_BIN"
    echo "make sure ~/.local/bin is first on PATH (add to ~/.bashrc if needed)"
  fi
else
  echo "micromamba not found. Install ffmpeg >= 6.1 yourself:"
  echo "  sudo apt install ffmpeg     # Ubuntu 22.04 ships 4.4 — TOO OLD"
  echo "  or: micromamba create -n ffmpeg-env -c conda-forge ffmpeg=9.0.2"
  echo "  then symlink it to ~/.local/bin/ffmpeg (first on PATH)"
fi

echo "== helper binaries -> ~/.local/bin =="
mkdir -p "$HOME/.local/bin"
# streamlink + yt-dlp come from pip above; make sure the user base bin is on PATH.
python3 -m site --user-base 2>/dev/null | xargs -I{} echo "pip user base: {} (add {}/bin to PATH if streamlink/yt-dlp are not found)"
if [ ! -x "$HOME/.local/bin/TwitchDownloaderCLI" ]; then
  echo "TwitchDownloaderCLI NOT found at ~/.local/bin/TwitchDownloaderCLI"
  echo "  download the linux-x64 release from https://github.com/lay295/TwitchDownloader/releases"
  echo "  place the TwitchDownloaderCLI binary in ~/.local/bin/ and chmod +x it"
  echo "  (vod.py will not work without it; live mode does not need it)"
fi

echo "== runtime dirs =="
mkdir -p queue ig-outbox clips vod recordings logs campaign_work submit-outbox .auth
chmod 700 .auth
[ -f config.yaml ] || cp config/config.yaml.example config.yaml
[ -f campaigns.json ] || printf '{\n  "campaigns": {}\n}\n' > campaigns.json
[ -f STOP ] && echo "NOTE: STOP file exists — posting is paused until you remove it"

echo "== done =="
echo "Next: docs/AUTH.md (YouTube OAuth, TikTok cookies, Instagram),"
echo "then: python3 poster.py --check   (read-only, posts nothing)"
echo "then: tmux new -s clipsdaily && python3 runner.py"
