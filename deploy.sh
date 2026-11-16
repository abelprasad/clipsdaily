#!/bin/bash
# deploy.sh — deploy the clipsdaily dev-copy repo to the live runtime.
#
# Copies *.py + test_e2e.sh from this repo to the live dir on indra,
# backs up the current live .py files first, then restarts the three
# tmux sessions (clipsdaily, clipsdaily-queue, clipsdaily-hourly).
#
# It does NOT touch live state: queue/, ig-outbox/, .auth/,
# config.yaml, campaigns.json, clips/, vod/, recordings/, logs/.
# It does NOT post, join, or submit anything.
#
# Usage:
#   bash deploy.sh --dry-run      # show the plan, change nothing (safe for anyone)
#   bash deploy.sh                # live deploy (run as abel on indra)
#   bash deploy.sh --no-restart   # copy files only, restart sessions yourself
#   bash deploy.sh --live-dir DIR # deploy to a different live dir
#
# Live deploy requires running as abel (the tmux server is abel's):
#   sudo -n -u abel bash deploy.sh
set -u

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LIVE_DIR="${CLIPSDAILY_LIVE_DIR:-/home/abel/clipsdaily}"
DRY_RUN=0
NO_RESTART=0

usage() {
  sed -n '2,17p' "$0" | sed 's/^# \?//'
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
if [ ! -f "$LIVE_DIR/runner.py" ]; then
  echo "refusing: $LIVE_DIR does not look like the live dir (no runner.py)" >&2
  exit 1
fi
if [ ! -f "$REPO_DIR/runner.py" ]; then
  echo "refusing: $REPO_DIR does not look like the repo (no runner.py)" >&2
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
for f in "$REPO_DIR"/*.py; do
  python3 -c "compile(open('$f').read(), '$f', 'exec')" || {
    echo "COMPILE FAILED: $f" >&2; exit 1; }
done
echo "   compile OK ($(ls "$REPO_DIR"/*.py | wc -l) files)"

if [ "$DRY_RUN" = 1 ]; then
  say "DRY RUN — nothing will change"
fi

# --- backup current live .py files ------------------------------------------
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$(dirname "$LIVE_DIR")/clipsdaily-backups/$TS"
say "backup live .py -> $BACKUP_DIR"
if [ "$DRY_RUN" = 1 ]; then
  echo "   [dry-run] mkdir -p $BACKUP_DIR && cp $LIVE_DIR/*.py $BACKUP_DIR/"
else
  mkdir -p "$BACKUP_DIR"
  cp "$LIVE_DIR"/*.py "$BACKUP_DIR"/
  [ -f "$LIVE_DIR/test_e2e.sh" ] && cp "$LIVE_DIR/test_e2e.sh" "$BACKUP_DIR"/
  echo "   backed up $(ls "$BACKUP_DIR"/*.py | wc -l) files"
fi

# --- copy repo -> live -------------------------------------------------------
say "copy repo -> $LIVE_DIR"
for f in "$REPO_DIR"/*.py "$REPO_DIR/test_e2e.sh"; do
  [ -f "$f" ] || continue
  base="$(basename "$f")"
  if [ -f "$LIVE_DIR/$base" ] && cmp -s "$f" "$LIVE_DIR/$base"; then
    echo "   same:    $base"
  else
    echo "   copy:    $base"
    run cp "$f" "$LIVE_DIR/$base"
  fi
done
echo "   state NOT touched: queue/ ig-outbox/ .auth/ config.yaml campaigns.json clips/ logs/"

# --- restart tmux sessions --------------------------------------------------
# Same commands the live sessions were started with. Only restart
# sessions that are currently running; a stopped session may be
# deliberate, so it is skipped, never started.
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
  restart_session "clipsdaily" "cd $LIVE_DIR && python3 runner.py"
  restart_session "clipsdaily-queue" "cd $LIVE_DIR && python3 queue_seed.py --maintain 2>&1 | tee -a logs/queue-$TODAY.log"
  restart_session "clipsdaily-hourly" "cd $LIVE_DIR && python3 hourly_poster.py 2>&1 | tee -a logs/hourly-$TODAY.log"
fi

if [ -f "$LIVE_DIR/STOP" ]; then
  echo "NOTE: STOP file exists in the live dir — posting stays paused after restart (rm STOP to resume)"
fi

# --- verify -----------------------------------------------------------------
if [ "$DRY_RUN" = 0 ] && [ "$NO_RESTART" = 0 ]; then
  say "verify"
  sleep 5
  tmux ls 2>/dev/null | grep -E "clipsdaily|clipsdaily-queue|clipsdaily-hourly" || echo "   WARN: a session is missing from tmux ls"
  for pat in "python3 runner.py" "queue_seed.py --maintain" "hourly_poster.py"; do
    if pgrep -f "$pat" >/dev/null; then echo "   running: $pat"; else echo "   MISSING: $pat"; fi
  done
fi

say "done"
if [ "$DRY_RUN" = 1 ]; then
  echo "   dry-run complete — nothing changed. Run without --dry-run (as abel) to deploy."
else
  echo "   rollback: cp $BACKUP_DIR/*.py $LIVE_DIR/ && restart the sessions above"
fi
