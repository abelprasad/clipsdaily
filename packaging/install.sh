#!/usr/bin/env bash
# ClipForge installer — idempotent.
#
# Installs the ClipForge pipeline into a runtime home (default
# ~/clipforge) with a venv, config template, systemd user units, and
# a release checkout for `clipforge update` rollbacks.
#
#   ./install.sh [--home DIR] [--release DIR] [--license KEYFILE]
#                  [--accept-license] [--no-systemd] [--yes]
#
# License: ClipForge is PROPRIETARY (see LICENSE). The installer shows
# the LICENSE + BETA_TERMS.md and installs only after acceptance
# (--accept-license, or interactive "I ACCEPT"). A signed license key
# is required: --license KEYFILE, $CLIPFORGE_LICENSE_FILE, or pasted
# interactively. The key is verified offline (Ed25519 signature +
# expiry) before anything is installed; a leaked copy without a key
# does not run. Test override (test-only): $CLIPFORGE_LICENSE_PUBLIC_KEY
# points at a PEM public key used instead of the baked-in vendor key.
#
# Safety:
#  - REFUSES to run against the live ClipsDaily directory
#    (/home/abel/clipsdaily) or any directory that already holds a
#    live queue.json / .auth tokens without the ClipForge marker.
#  - Re-running against an existing ClipForge home is a no-op for
#    state: config.yaml, queue/, .auth/, logs/ are never touched.
#  - No posts are made, no accounts are created, no money is spent.
set -euo pipefail

HOME_DIR="${CLIPFORGE_HOME:-$HOME/clipforge}"
RELEASE_DIR=""
LICENSE_FILE="${CLIPFORGE_LICENSE_FILE:-}"
ACCEPT_LICENSE=0
NO_SYSTEMD=0
ASSUME_YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --home) HOME_DIR="$2"; shift 2 ;;
    --release) RELEASE_DIR="$2"; shift 2 ;;
    --license) LICENSE_FILE="$2"; shift 2 ;;
    --accept-license) ACCEPT_LICENSE=1; shift ;;
    --no-systemd) NO_SYSTEMD=1; shift ;;
    --yes) ASSUME_YES=1; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# install.sh lives in packaging/; the release dir (repo checkout) is
# its parent, unless --release overrides it.
RELEASE_DIR="${RELEASE_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PACKAGING_DIR="$RELEASE_DIR/packaging"
VENV_DIR="${CLIPFORGE_VENV_DIR:-$HOME/.clipforge-venv}"
MARKER="$HOME_DIR/.clipforge-home"
LIVE_DIR="/home/abel/clipsdaily"

say() { echo "[install] $*"; }
die() { echo "[install] ERROR: $*" >&2; exit 1; }

# --- refusal checks -------------------------------------------------------
RESOLVED_HOME="$(python3 -c 'import sys,os; print(os.path.realpath(sys.argv[1]))' "$HOME_DIR")"
[ "$RESOLVED_HOME" = "$(python3 -c 'import sys,os; print(os.path.realpath(sys.argv[1]))' "$LIVE_DIR")" ] \
  && die "refusing to install into the live ClipsDaily directory ($LIVE_DIR)"
if [ -e "$HOME_DIR/queue/queue.json" ] && [ ! -f "$MARKER" ]; then
  die "refusing: $HOME_DIR already holds a queue.json but is not a ClipForge home (no .clipforge-home marker). Pick an empty --home."
fi
if [ -e "$HOME_DIR/.auth" ] && [ ! -f "$MARKER" ] && [ -n "$(ls -A "$HOME_DIR/.auth" 2>/dev/null)" ]; then
  die "refusing: $HOME_DIR/.auth already holds credentials but is not a ClipForge home. Pick an empty --home."
fi

# --- license acceptance + key ---------------------------------------------
# Proprietary license: show LICENSE + BETA_TERMS.md, require acceptance.
if [ "$ACCEPT_LICENSE" -eq 0 ]; then
  if [ -t 0 ]; then
    for f in "$PACKAGING_DIR/LICENSE" "$PACKAGING_DIR/BETA_TERMS.md"; do
      [ -f "$f" ] && { echo "----- $f -----"; cat "$f"; echo; }
    done
    printf 'Type I ACCEPT to accept the license + beta terms: '
    read -r ANSWER
    [ "$ANSWER" = "I ACCEPT" ] || die "license not accepted — refusing to install"
  else
    die "non-interactive install requires --accept-license"
  fi
fi
# Key: --license FILE, $CLIPFORGE_LICENSE_FILE, or paste interactively.
KEY_TMP=""
if [ -z "$LICENSE_FILE" ]; then
  if [ -t 0 ]; then
    printf 'Paste your ClipForge license key: '
    read -rs KEY_PASTED; echo
    KEY_TMP="$(mktemp)"
    printf '%s' "$KEY_PASTED" > "$KEY_TMP"
    LICENSE_FILE="$KEY_TMP"
  else
    die "no license key: pass --license KEYFILE or set CLIPFORGE_LICENSE_FILE"
  fi
fi
[ -f "$LICENSE_FILE" ] || die "license key file not found: $LICENSE_FILE"

# --- prerequisites ---------------------------------------------------------
command -v python3 >/dev/null || die "python3 not found"
PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
  || die "python3 >= 3.10 required (found $PYVER)"
# ffmpeg >= 6.1: the system ffmpeg is often too old (Ubuntu ships 4.4);
# the live route is a newer ffmpeg in ~/.local/bin (micromamba). Check
# every candidate and take the first new enough one; remember it so the
# installer can symlink it into the venv (the systemd units run with
# the venv bin on PATH, so they find it even when it is not on PATH).
find_ffmpeg() {
  for cand in "$HOME/.local/bin/ffmpeg" "$(command -v ffmpeg || true)" \
      "$HOME/.micromamba/envs/ffmpeg-env/bin/ffmpeg" /usr/local/bin/ffmpeg; do
    [ -n "$cand" ] && [ -x "$cand" ] || continue
    ver="$("$cand" -version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1)"
    [ -n "$ver" ] || continue
    if python3 -c "import sys; sys.exit(0 if tuple(map(int, '$ver'.split('.'))) >= (6, 1) else 1)"; then
      echo "$cand"
      return 0
    fi
  done
  return 1
}
FFMPEG_BIN="$(find_ffmpeg || true)"
[ -n "$FFMPEG_BIN" ] || die "ffmpeg >= 6.1 required and none found (system ffmpeg is $(ffmpeg -version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1)). Install ffmpeg 6.1+ (e.g. via micromamba/conda) or symlink it to ~/.local/bin/ffmpeg"
say "ffmpeg: $FFMPEG_BIN ($("$FFMPEG_BIN" -version 2>/dev/null | head -1))"
command -v git >/dev/null || die "git not found"
FREE_GB="$(df --output=avail -BG "$HOME" | tail -1 | tr -dc '0-9')"
[ "${FREE_GB:-0}" -ge 20 ] || die "need >= 20 GB free disk (found ${FREE_GB} GB)"
command -v streamlink >/dev/null || say "warning: streamlink not on PATH (venv install below provides it)"
command -v yt-dlp >/dev/null || say "warning: yt-dlp not on PATH — VOD backfill needs it (pip install yt-dlp, or the venv provides it if listed in pyproject)"

# --- venv + package ---------------------------------------------------------
# Test/dev knobs (env): CLIPFORGE_VENV_SYSTEM_SITE=1 (reuse system
# site-packages), CLIPFORGE_PIP_NO_DEPS=1 (skip dependency downloads),
# CLIPFORGE_SKIP_PLAYWRIGHT=1, CLIPFORGE_SKIP_PREWARM=1.
if [ ! -x "$VENV_DIR/bin/python" ]; then
  say "creating venv at $VENV_DIR"
  if [ "${CLIPFORGE_VENV_SYSTEM_SITE:-0}" = "1" ]; then
    python3 -m venv --system-site-packages "$VENV_DIR"
  else
    python3 -m venv "$VENV_DIR"
  fi
fi
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
say "installing ClipForge into the venv (from $RELEASE_DIR)"
if [ "${CLIPFORGE_PIP_NO_DEPS:-0}" = "1" ]; then
  "$VENV_DIR/bin/pip" install --quiet --no-deps "$RELEASE_DIR"
else
  "$VENV_DIR/bin/pip" install --quiet "$RELEASE_DIR"
fi
"$VENV_DIR/bin/python" -c "import clipsdaily; print('package OK:', clipsdaily.__version__)"
# Make the good ffmpeg/ffprobe visible to the services (venv bin is on
# their PATH). Only when the PATH ffmpeg is not already good enough.
PATH_FFMPEG="$(command -v ffmpeg || true)"
if [ "$FFMPEG_BIN" != "$PATH_FFMPEG" ]; then
  for tool in ffmpeg ffprobe; do
    src="$(dirname "$FFMPEG_BIN")/$tool"
    [ -x "$src" ] && ln -sf "$src" "$VENV_DIR/bin/$tool"
  done
  say "linked $FFMPEG_BIN (+ffprobe) into the venv bin"
fi
# --- license key validation (offline) --------------------------------------
# Runs now that the venv has cryptography. Refuses BEFORE any runtime
# state is created, so a bad key leaves nothing behind but the venv.
PUBKEY_ARGS=()
[ -n "${CLIPFORGE_LICENSE_PUBLIC_KEY:-}" ] && PUBKEY_ARGS=(--public-key "$CLIPFORGE_LICENSE_PUBLIC_KEY")
if ! "$VENV_DIR/bin/clipforge" license check --key-file "$LICENSE_FILE" "${PUBKEY_ARGS[@]}"; then
  die "license key invalid — refusing to install (see above)"
fi
[ -n "$KEY_TMP" ] && rm -f "$KEY_TMP"

# --- runtime home ----------------------------------------------------------
mkdir -p "$HOME_DIR"/{queue/clips,queue/work,ig-outbox,clips,vod,recordings,logs,.auth}
chmod 700 "$HOME_DIR/.auth"
# Install the verified key (0600) + license docs + acceptance record.
cp "$LICENSE_FILE" "$HOME_DIR/.auth/license.key"
chmod 600 "$HOME_DIR/.auth/license.key"
for f in LICENSE BETA_TERMS.md; do
  [ -f "$PACKAGING_DIR/$f" ] && cp "$PACKAGING_DIR/$f" "$HOME_DIR/$f"
done
echo "accepted $(date -u +%Y-%m-%dT%H:%M:%SZ) (installer)" > "$HOME_DIR/.accepted-terms"
if [ ! -f "$HOME_DIR/config.yaml" ]; then
  if [ -f "$RELEASE_DIR/config/config.yaml.example" ]; then
    cp "$RELEASE_DIR/config/config.yaml.example" "$HOME_DIR/config.yaml"
    chmod 600 "$HOME_DIR/config.yaml"
    say "wrote config.yaml from the template — run 'clipforge setup' next"
  else
    say "warning: no config template found at $RELEASE_DIR/config/config.yaml.example"
  fi
else
  say "config.yaml already exists — leaving it alone"
fi

# TwitchDownloaderCLI (VOD downloads only; live cutting does not need it)
if ! command -v TwitchDownloaderCLI >/dev/null && [ ! -x "$HOME/.local/bin/TwitchDownloaderCLI" ]; then
  say "warning: TwitchDownloaderCLI not found — VOD backfill is unavailable until you install it (https://github.com/lay295/TwitchDownloader/releases)"
fi
# Playwright chromium (TikTok cookie route + Content Rewards automation)
if [ "${CLIPFORGE_SKIP_PLAYWRIGHT:-0}" = "1" ]; then
  say "skipping Playwright chromium (CLIPFORGE_SKIP_PLAYWRIGHT=1)"
elif "$VENV_DIR/bin/python" -m playwright --version >/dev/null 2>&1; then
  say "installing Playwright chromium (one-time download)"
  "$VENV_DIR/bin/python" -m playwright install chromium || \
    say "warning: playwright chromium install failed — TikTok cookie route and campaign automation will not work until it succeeds"
fi
# faster-whisper model pre-warm (base); failure is non-fatal.
if [ "${CLIPFORGE_SKIP_PREWARM:-0}" = "1" ]; then
  say "skipping whisper pre-warm (CLIPFORGE_SKIP_PREWARM=1)"
else
"$VENV_DIR/bin/python" -c "
from faster_whisper import WhisperModel
WhisperModel('base', device='cpu', compute_type='int8')
print('whisper base model cached')
" 2>/dev/null || say "warning: faster-whisper base model pre-warm failed (no network?) — first cut will download it"
fi

# --- release checkout (for clipforge update + rollback) ---------------------
RELEASE_HOME="${CLIPFORGE_RELEASE_HOME:-$HOME/clipforge-release}"
if [ -d "$RELEASE_DIR/.git" ]; then
  if [ ! -d "$RELEASE_HOME/.git" ]; then
    say "cloning release checkout to $RELEASE_HOME"
    git clone --quiet "$RELEASE_DIR" "$RELEASE_HOME"
  else
    say "release checkout already exists — leaving it alone"
  fi
  (cd "$RELEASE_HOME" && git describe --tags --exact-match 2>/dev/null || true) | \
    sed 's/^/[install] release checkout at /'
else
  say "warning: $RELEASE_DIR is not a git checkout — auto-update needs a release channel (see docs)"
fi

# --- systemd user units ------------------------------------------------------
if [ "$NO_SYSTEMD" -eq 0 ]; then
  UNIT_DIR="$HOME/.config/systemd/user"
  mkdir -p "$UNIT_DIR"
  if [ -d "$RELEASE_DIR/systemd" ]; then
    for f in "$RELEASE_DIR"/systemd/*; do
      base="$(basename "$f")"
      sed -e "s|@CLIPFORGE_HOME@|$HOME_DIR|g" \
          -e "s|@CLIPFORGE_VENV@|$VENV_DIR|g" \
          -e "s|/usr/bin/env python3|$VENV_DIR/bin/python|g" \
          -e "s|CLIPSDAILY_HOME|CLIPFORGE_HOME|g" \
          -e "s|%h/clipforge|$HOME_DIR|g" \
          "$f" > "$UNIT_DIR/$base"
      # Every service needs the venv bin + ~/.local/bin on PATH (ffmpeg,
      # yt-dlp, TwitchDownloaderCLI live there on many boxes).
      if ! grep -q "^Environment=PATH=" "$UNIT_DIR/$base"; then
        sed -i "/^\[Service\]/a Environment=PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/bin:/bin:$HOME_DIR/.local/bin" "$UNIT_DIR/$base"
      fi
    done
    say "installed $(ls "$RELEASE_DIR"/systemd | wc -l) systemd units to $UNIT_DIR"
    systemctl --user daemon-reload || say "warning: systemctl --user daemon-reload failed — is systemd running as your user?"
    if loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q "Linger=yes"; then
      say "user linger is on — services survive logout"
    else
      if loginctl enable-linger "$USER" 2>/dev/null; then
        say "enabled user linger"
      else
        say "warning: user linger is OFF — run 'loginctl enable-linger $USER' so services survive logout"
      fi
    fi
  else
    say "warning: no systemd/ dir in $RELEASE_DIR — units not installed"
  fi
else
  say "skipping systemd units (--no-systemd)"
fi

# --- marker + smoke check -----------------------------------------------------
touch "$MARKER"
say "running smoke check: clipforge status"
CLIPFORGE_HOME="$HOME_DIR" "$VENV_DIR/bin/clipforge" status || \
  say "warning: smoke check reported a problem (expected before setup — auth is not configured yet)"

echo
echo "ClipForge installed at $HOME_DIR"
echo "  venv:    $VENV_DIR"
echo "  next:    CLIPFORGE_HOME=$HOME_DIR $VENV_DIR/bin/clipforge setup"
echo "  dashboard (after setup): http://127.0.0.1:8787"
echo "  docs:    $PACKAGING_DIR/README.md"
