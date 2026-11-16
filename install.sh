#!/bin/bash
# clipsdaily installer — one-command install.
#
#   pipx install git+https://github.com/abelprasad/clipsdaily.git
#
# is the one-command install once the repo is pushed to GitHub
# (no remote yet — until then use --local from a clone). This script
# is a convenience wrapper for that plus a from-source install.
#
#   bash install.sh            # pipx install from the git URL
#   bash install.sh --local    # install from this checkout (pip install -e .)
#   bash install.sh --help
#
# The install itself posts, joins, or submits nothing. After it,
# run ./setup.sh for the heavy system deps (ffmpeg 9, playwright
# chromium, TwitchDownloaderCLI) and see docs/AUTH.md for auth.
set -e
REPO_URL="https://github.com/abelprasad/clipsdaily.git"
MODE="${1:-}"

if [ "$MODE" = "--help" ] || [ "$MODE" = "-h" ]; then
    echo "usage: bash install.sh [--local]"
    echo "  (no flag)  pipx install from $REPO_URL"
    echo "  --local    pip install -e . from this checkout"
    exit 0
fi

if [ "$MODE" = "--local" ]; then
    # pip >= 23 is required (Debian's pip 22.0.2 cannot build a PEP 621
    # pyproject). Upgrade once in the user site if needed.
    PIP_MAJOR="$(python3 -m pip --version 2>/dev/null | sed -E 's/^pip ([0-9]+)\..*/\1/')"
    if [ -n "$PIP_MAJOR" ] && [ "$PIP_MAJOR" -lt 23 ]; then
        echo "pip is too old ($PIP_MAJOR) — upgrading pip in the user site"
        python3 -m pip install --user -q -U pip
    fi
    python3 -m pip install -e . --no-deps
    echo "Installed editable from this checkout."
elif [ "$MODE" = "" ]; then
    if ! command -v pipx >/dev/null 2>&1; then
        echo "pipx not found. Installing it:"
        python3 -m pip install --user pipx
        python3 -m pipx ensurepath
        export PATH="$HOME/.local/bin:$PATH"
    fi
    pipx install "git+$REPO_URL"
    echo "Installed from $REPO_URL."
else
    echo "unknown option: $MODE (try --help)" >&2
    exit 1
fi

if command -v clipsdaily >/dev/null 2>&1; then
    echo "clipsdaily: $(clipsdaily --version)"
else
    echo "clipsdaily is installed but not on PATH yet."
    echo "Add ~/.local/bin to PATH, or open a new shell."
fi
echo "Next: bash setup.sh   (system deps) and docs/AUTH.md (auth)."
