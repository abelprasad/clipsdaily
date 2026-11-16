#!/bin/bash
# deploy.sh — deploy the clipsdaily dev-copy repo to the live runtime.
#
# Installs the packaged CLI from this repo into the live environment
# (pip install --user --no-deps .), backs up the current live flat
# .py files first, removes them after a successful install+verify,
# copies test_e2e.sh, then restarts the three tmux sessions
# (clipsdaily, clipsdaily-queue, clipsdaily-hourly) with the
# `clipsdaily` console script.
#
# It does NOT touch live state: queue/, ig-outbox/, .auth/,
# config.yaml, campaigns.json, clips/, vod/, recordings/, logs/.
# It does NOT post, join, or submit anything.
#
# Usage:
#   bash deploy.sh --dry-run      # show the plan, change nothing (safe for anyone)
#   bash deploy.sh                # live deploy (run as abel on indra)
#   bash deploy.sh --no-restart   # install + copy only, restart sessions yourself
#   bash deploy.sh --live-dir DIR # deploy to a different live dir
#
# Live deploy requires running as abel (the tmux server is abel's):
#   sudo -n -u abel bash deploy.sh
#
# Rollback (flat .py layout): cp <BACKUP_DIR>/*.py <LIVE_DIR>/ and
# restart the sessions with the old commands (python3 runner.py,
# python3 queue_seed.py --maintain, python3 hourly_poster.py).
set -u

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LIVE_DIR="${CLIPSDAILY_LIVE_DIR:-/home/abel/clipsdaily}"
CLI_BIN="/home/abel/.local/bin/clipsdaily"
DRY_RUN=0
NO_RESTART=0

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \?//'
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1; shift ;;
    --no-restart) NO_RESTART=1; shift ;;
    --live-dir) LIVE_DIR="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1" >&2; usage >&2; exit 2 ;;
  esac
done

say() { echo "== $*"; }
run() {
  if [ "$DRY_RUN" = 1 ]; then
    echo "   [dry-run] $*"
  else
    "$@"
  fi
}

# --- safety checks (read-only, run in both modes) ---------------------------
if [ "$REPO_DIR" = "$LIVE_DIR" ]; then
  echo "refusing: repo dir and live dir are the same ($REPO_DIR)" >&2
  exit 1
fi
if [ ! -f "$REPO_DIR/src/clipsdaily/runner.py" ]; then
  echo "refusing: $REPO_DIR does not look like the repo (no src/clipsdaily/runner.py)" >&2
  exit 1
fi
# The live dir is valid in either layout: flat .py files (pre-migration)
# or the installed console script (post-migration).
if [ ! -f "$LIVE_DIR/runner.py" ] && [ ! -x "$CLI_BIN" ]; then
  echo "refusing: $LIVE_DIR does not look like the live dir (no runner.py, no $CLI_BIN)" >&2
  exit 1
fi
if [ "$DRY_RUN" = 0 ] && [ "$(whoami)" != "abel" ]; then
  echo "refusing: run live deploys as abel (sudo -n -u abel bash deploy.sh)" >&2
  exit 1
fi

# Dirty tree: refuse a live deploy, warn on dry-run.
if command -v git >/dev/null 2>&1 && [ -d "$REPO_DIR/.git" ]; then
  if [ -n "$(git -C "$REPO_DIR" status --porcelain 2>/dev/null)" ]; then
    if [ "$DRY_RUN" = 1 ]; then
      echo "WARN: repo has uncommitted changes (live deploy would refuse)" >&2
    else
      echo "refusing: repo has uncommitted changes — commit first" >&2
      git -C "$REPO_DIR" status --short >&2
      exit 1
    fi
  fi
fi

# Compile check without writing bytecode (no __pycache__ left behind).
say "compile check (repo)"
python3 -m compileall -q "$REPO_DIR/src" || { echo "COMPILE FAILED" >&2; exit 1; }
echo "   compile OK ($(ls "$REPO_DIR"/src/clipsdaily/*.py | wc -l) files)"

if [ "$DRY_RUN" = 1 ]; then
  say "DRY RUN — nothing will change"
fi

# --- backup current live flat .py files -------------------------------------
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$(dirname "$LIVE_DIR")/clipsdaily-backups/$TS"
say "backup live flat .py -> $BACKUP_DIR"
if [ "$DRY_RUN" = 1 ]; then
  echo "   [dry-run] mkdir -p $BACKUP_DIR && cp $LIVE_DIR/*.py $BACKUP_DIR/ (if any)"
else
  mkdir -p "$BACKUP_DIR"
  if ls "$LIVE_DIR"/*.py >/dev/null 2>&1; then
    cp "$LIVE_DIR"/*.py "$BACKUP_DIR"/
    echo "   backed up $(ls "$BACKUP_DIR"/*.py | wc -l) files"
  else
    echo "   no flat .py files in the live dir (already on the packaged layout)"
  fi
  [ -f "$LIVE_DIR/test_e2e.sh" ] && cp "$LIVE_DIR/test_e2e.sh" "$BACKUP_DIR"/
fi

# --- install the package from the repo (live only) --------------------------
say "install package from repo"
# pip >= 23 is required: Debian's pip 22.0.2 cannot build a PEP 621
# pyproject (its editable-hook check fails and its wheel builds as
# UNKNOWN). Upgrade once in the user site if needed (idempotent).
if [ "$DRY_RUN" = 1 ]; then
  echo "   [dry-run] check pip >= 23 (upgrade in the user site if older)"
else
  PIP_MAJOR="$(python3 -m pip --version 2>/dev/null | sed -E 's/^pip ([0-9]+)\..*/\1/')"
  if [ -n "$PIP_MAJOR" ] && [ "$PIP_MAJOR" -lt 23 ]; then
    echo "   pip is too old ($PIP_MAJOR) — upgrading pip in the user site"
    python3 -m pip install --user -q -U pip || {
      echo "pip upgrade failed — upgrade pip to >= 23 and retry" >&2
      exit 1
    }
  fi
fi
if [ "$DRY_RUN" = 1 ]; then
  echo "   [dry-run] pip install --user --force-reinstall --no-deps $REPO_DIR"
  echo "   [dry-run] (dry-run cannot verify the install; live deploy verifies --version)"
else
  python3 -m pip install --user --force-reinstall --no-deps "$REPO_DIR" || {
    echo "INSTALL FAILED — live dir untouched, fix the package and retry" >&2
    exit 1
  }
  "$CLI_BIN" --version || {
    echo "VERIFY FAILED: $CLI_BIN --version did not run — live dir untouched" >&2
    exit 1
  }
fi

# --- remove the old flat .py files, copy test_e2e.sh ------------------------
say "remove live flat .py files, copy test_e2e.sh"
if [ "$DRY_RUN" = 1 ]; then
  echo "   [dry-run] rm $LIVE_DIR/*.py (backed up above) && cp $REPO_DIR/test_e2e.sh $LIVE_DIR/"
else
  rm -f "$LIVE_DIR"/*.py
  cp "$REPO_DIR/test_e2e.sh" "$LIVE_DIR/test_e2e.sh"
fi
echo "   state NOT touched: queue/ ig-outbox/ .auth/ config.yaml campaigns.json clips/ logs/"

# --- restart tmux sessions --------------------------------------------------
# Same commands the live sessions were started with, now via the
# console script. Only restart sessions that are currently running;
# a stopped session may be deliberate, so it is skipped, never started.
restart_session() {
  local name="$1" cmd="$2"
  if tmux has-session -t "$name" 2>/dev/null; then
    echo "   restart: $name"
    echo "            $cmd"
    if [ "$DRY_RUN" = 0 ]; then
      tmux kill-session -t "$name" 2>/dev/null
      sleep 1
      tmux new-session -d -s "$name" "$cmd"
    fi
  else
    echo "   skip:    $name (not running)"
  fi
}

if [ "$NO_RESTART" = 1 ]; then
  say "restart skipped (--no-restart)"
else
  say "restart tmux sessions"
  TODAY="$(date +%Y%m%d)"
  restart_session "clipsdaily" "cd $LIVE_DIR && $CLI_BIN run"
  restart_session "clipsdaily-queue" "cd $LIVE_DIR && $CLI_BIN queue maintain 2>&1 | tee -a logs/queue-$TODAY.log"
  restart_session "clipsdaily-hourly" "cd $LIVE_DIR && $CLI_BIN post hourly 2>&1 | tee -a logs/hourly-$TODAY.log"
fi

if [ -f "$LIVE_DIR/STOP" ]; then
  echo "NOTE: STOP file exists in the live dir — posting stays paused after restart (rm STOP to resume)"
fi

# --- verify -----------------------------------------------------------------
if [ "$DRY_RUN" = 0 ] && [ "$NO_RESTART" = 0 ]; then
  say "verify"
  sleep 5
  tmux ls 2>/dev/null | grep -E "clipsdaily|clipsdaily-queue|clipsdaily-hourly" || echo "   WARN: a session is missing from tmux ls"
  for pat in "clipsdaily run" "queue maintain" "post hourly"; do
    if pgrep -f "$pat" >/dev/null; then echo "   running: $pat"; else echo "   MISSING: $pat"; fi
  done
fi

say "done"
if [ "$DRY_RUN" = 1 ]; then
  echo "   dry-run complete — nothing changed. Run without --dry-run (as abel) to deploy."
else
  echo "   rollback: cp $BACKUP_DIR/*.py $LIVE_DIR/ && restart the sessions with the old flat commands"
fi
