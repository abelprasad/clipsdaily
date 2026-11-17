#!/usr/bin/env python3
"""clipsdaily watchdog + health alerts.

Watches the three live tmux sessions (runner, hourly poster, queue
maintainer) and restarts any that died. Every 30 minutes verifies each
platform actually posted recently, using only on-disk evidence, and
writes health.json. A NEW failure appends one alert line to
logs/health-alerts.log (one alert per failure episode; re-alerts only
after a recovery).

Run as abel (the tmux server belongs to abel). Modes:
  (default)  loop forever: 60s watchdog cycle, health check every 30 min
  --once     one watchdog + health pass, then exit (testing / cron)
  --test-detect
             prove the dead-session path works with a throwaway
             session named clipsdaily-watchdog-test; never touches
             the real sessions.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE = os.path.dirname(os.path.abspath(__file__))
NY = ZoneInfo("America/New_York")
LOGS = os.path.join(BASE, "logs")
HEALTH_FILE = os.path.join(BASE, "health.json")
STATE_FILE = os.path.join(BASE, "watchdog-state.json")
ALERTS_FILE = os.path.join(LOGS, "health-alerts.log")

# (session name, process pattern, start command). The $(date ...) in the
# start commands is expanded by the pane's shell at restart time, so the
# log file always matches the restart day. These are the exact commands
# the sessions were started with on 2026-11-16 (verified via tmux
# list-panes pane_start_command).
SESSIONS = {
    "clipsdaily": {
        "proc": "python3 runner.py",
        "start": "cd /home/abel/clipsdaily && python3 runner.py 2>&1 | tee -a logs/runner-$(date +%Y%m%d).log",
    },
    "clipsdaily-hourly": {
        "proc": "python3 hourly_poster.py",
        "start": "cd /home/abel/clipsdaily && python3 hourly_poster.py 2>&1 | tee -a logs/hourly-$(date +%Y%m%d).log",
    },
    "clipsdaily-queue": {
        "proc": "python3 queue_seed.py --maintain",
        "start": "cd /home/abel/clipsdaily && python3 queue_seed.py --maintain 2>&1 | tee -a logs/queue-$(date +%Y%m%d).log",
    },
}

YT_SLOTS = [0, 3, 6, 9, 12, 15, 18, 21]  # YouTube posts at these hours


def log(msg):
    os.makedirs(LOGS, exist_ok=True)
    line = "[%s] %s" % (datetime.now(NY).strftime("%Y-%m-%d %H:%M:%S"), msg)
    path = os.path.join(LOGS, "watchdog-%s.log" % datetime.now(NY).strftime("%Y%m%d"))
    with open(path, "a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return -1, "", str(e)


def session_alive(name, proc):
    rc, _, _ = run(["tmux", "has-session", "-t", name])
    if rc != 0:
        return False, "no tmux session %s" % name
    rc, out, _ = run(["pgrep", "-f", proc])
    if rc != 0 or not out:
        return False, "session %s exists but process '%s' is gone" % (name, proc)
    return True, "session %s alive (pid %s)" % (name, out.split()[0])


def ensure_session(name, proc, start):
    """Check one session; restart it if dead. Returns (status, detail)."""
    alive, detail = session_alive(name, proc)
    if alive:
        return "alive", detail
    log("WATCHDOG %s dead: %s; restarting" % (name, detail))
    # Never leave a duplicate: kill any remnant, then start fresh.
    run(["tmux", "kill-session", "-t", name])
    rc, _, err = run(["tmux", "new-session", "-d", "-s", name, start])
    if rc != 0:
        log("WATCHDOG %s restart FAILED: %s" % (name, err))
        return "failed", "restart failed: %s" % err
    time.sleep(2)
    alive2, detail2 = session_alive(name, proc)
    if alive2:
        log("WATCHDOG %s restarted OK: %s" % (name, detail2))
        return "restarted", detail2
    log("WATCHDOG %s restart did not come up: %s" % (name, detail2))
    return "failed", detail2


def watchdog_pass():
    """Check all three sessions. Returns {name: (status, detail)}."""
    out = {}
    for name, cfg in SESSIONS.items():
        out[name] = ensure_session(name, cfg["proc"], cfg["start"])
    return out


# ---------------- health check ----------------

def read_hourly_logs():
    """Yield (timestamp, line) for today + yesterday's hourly logs."""
    today = datetime.now(NY).date()
    for back in (0, 1):
        day = today - timedelta(days=back)
        path = os.path.join(LOGS, "hourly-%s.log" % day.strftime("%Y%m%d"))
        if not os.path.exists(path):
            continue
        with open(path, errors="replace") as f:
            for line in f:
                m = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
                if m:
                    ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=NY)
                    yield ts, line.rstrip("\n")


def last_n_yt_slots(now, n=3):
    slots = []
    for back in range(0, 3):
        day = now.date() - timedelta(days=back)
        for h in sorted(YT_SLOTS, reverse=True):
            t = datetime.combine(day, datetime.min.time().replace(hour=h), tzinfo=NY)
            if t <= now:
                slots.append(t)
            if len(slots) >= n:
                return slots
    return slots


def check_youtube(now, pending):
    if pending == 0:
        return "idle", None, "no pending clips, nothing expected"
    last = None
    for ts, line in read_hourly_logs():
        if "YOUTUBE LIVE" in line and (last is None or ts > last):
            last = ts
    slots = last_n_yt_slots(now, 3)
    window_start = slots[-1] if slots else now
    if last is not None and last >= window_start:
        return "healthy", last, "last Short %s (window starts %s)" % (
            last.strftime("%H:%M"), window_start.strftime("%m-%d %H:%M"))
    detail = "no YOUTUBE LIVE since %s; last 3 slots start %s" % (
        last.strftime("%m-%d %H:%M") if last else "never",
        window_start.strftime("%m-%d %H:%M"))
    return "unhealthy", last, detail


def check_instagram(now, pending):
    if pending == 0:
        return "idle", None, "no pending clips, nothing expected"
    outbox = os.path.join(BASE, "ig-outbox")
    last = None
    last_clip = None
    last_fbid = None
    if os.path.isdir(outbox):
        for clip in os.listdir(outbox):
            d = os.path.join(outbox, clip)
            posted = os.path.join(d, ".posted")
            if os.path.exists(posted):
                try:
                    with open(posted) as f:
                        meta = json.load(f)
                    ts = datetime.strptime(
                        meta["posted_at_utc"], "%Y-%m-%dT%H:%M:%SZ"
                    ).replace(tzinfo=timezone.utc).astimezone(NY)
                    if last is None or ts > last:
                        last, last_clip = ts, clip
                        last_fbid = meta.get("media_fbid")
                except Exception:
                    pass
            else:
                meta_path = os.path.join(d, "meta.json")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path) as f:
                            meta = json.load(f)
                        if meta.get("status") == "posted":
                            ts = datetime.fromtimestamp(
                                os.path.getmtime(meta_path), tz=NY)
                            if last is None or ts > last:
                                last, last_clip = ts, clip
                    except Exception:
                        pass
    if last is not None and (now - last) <= timedelta(hours=2):
        return "healthy", last, "last Reel %s at %s (fbid %s)" % (
            last_clip, last.strftime("%H:%M"), last_fbid or "?")
    detail = "no IG post in last 2h; last was %s%s" % (
        last.strftime("%m-%d %H:%M") if last else "never",
        " (%s)" % last_clip if last_clip else "")
    return "unhealthy", last, detail


def check_queue(state):
    path = os.path.join(BASE, "queue", "queue.json")
    try:
        with open(path) as f:
            entries = json.load(f)
    except Exception as e:
        return "unhealthy", 0, 0, [], "queue.json unreadable: %s" % e
    ids = [str(e.get("id")) for e in entries if isinstance(e, dict)]
    pending = sum(1 for e in entries
                  if isinstance(e, dict) and e.get("status") == "pending")
    if not ids:
        return "unhealthy", 0, 0, ids, "queue is empty"
    prev_ids = set(state.get("queue_ids", []))
    vanished = [i for i in prev_ids - set(ids)] if prev_ids else []
    if vanished:
        # Did the hourly log mention the vanished entry at all? Nothing
        # legitimately removes ids (the maintainer never prunes), so any
        # disappearance is a failure; the log note is context, not proof.
        log_text = ""
        for ts, line in read_hourly_logs():
            log_text += line + "\n"
        noted = [i for i in vanished if i in log_text]
        detail = "entries vanished from queue: %s (in hourly log: %s)" % (
            ", ".join(vanished), ", ".join(noted) if noted else "none")
        return "unhealthy", len(ids), pending, ids, detail
    return "healthy", len(ids), pending, ids, "%d entries, %d pending" % (
        len(ids), pending)


def check_tiktok():
    last_fail = None
    for ts, line in read_hourly_logs():
        if "tiktok FAILED" in line or "tiktok retries exhausted" in line:
            if last_fail is None or ts > last_fail:
                last_fail = ts
    return "known_broken", last_fail, (
        "cookie path blocked (known, no alert); last failure %s"
        % (last_fail.strftime("%m-%d %H:%M") if last_fail else "n/a"))


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"queue_ids": [], "health": {}}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)


def alert(platform, detail):
    os.makedirs(LOGS, exist_ok=True)
    line = "[%s] ALERT %s: %s" % (
        datetime.now(NY).strftime("%Y-%m-%d %H:%M:%S"), platform, detail)
    with open(ALERTS_FILE, "a") as f:
        f.write(line + "\n")
    log("HEALTH ALERT %s: %s" % (platform, detail))


def health_pass(sessions):
    now = datetime.now(NY)
    state = load_state()
    yt_status, yt_last, yt_detail = None, None, None
    q_status, total, pending, ids, q_detail = check_queue(state)
    yt_status, yt_last, yt_detail = check_youtube(now, pending)
    ig_status, ig_last, ig_detail = check_instagram(now, pending)
    tt_status, tt_last, tt_detail = check_tiktok()

    health = {
        "checked_at": now.isoformat(),
        "youtube": {"status": yt_status,
                    "last_post": yt_last.isoformat() if yt_last else None,
                    "detail": yt_detail},
        "instagram": {"status": ig_status,
                      "last_post": ig_last.isoformat() if ig_last else None,
                      "detail": ig_detail},
        "queue": {"status": q_status, "entries": total, "pending": pending,
                  "detail": q_detail},
        "tiktok": {"status": tt_status,
                   "last_failure": tt_last.isoformat() if tt_last else None,
                   "detail": tt_detail},
        "watchdog": {"sessions": {n: s[0] for n, s in sessions.items()}},
    }

    # One alert per failure episode: alert only on healthy/idle -> unhealthy.
    prev = state.get("health", {})
    for platform in ("youtube", "instagram", "queue"):
        new = health[platform]["status"]
        old = prev.get(platform)
        if new == "unhealthy" and old != "unhealthy":
            alert(platform, health[platform]["detail"])
        elif new != "unhealthy" and old == "unhealthy":
            log("HEALTH RECOVERED %s: %s" % (platform, health[platform]["detail"]))
    state["health"] = {p: health[p]["status"]
                       for p in ("youtube", "instagram", "queue")}
    state["queue_ids"] = ids
    save_state(state)

    tmp = HEALTH_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(health, f, indent=2)
    os.replace(tmp, HEALTH_FILE)
    log("HEALTH youtube=%s instagram=%s queue=%s tiktok=%s (%s)" % (
        yt_status, ig_status, q_status, tt_status, q_detail))
    return health


def test_detect():
    """Prove the dead-session path with a throwaway session."""
    name, proc, start = "clipsdaily-watchdog-test", "sleep 120", "sleep 120"
    run(["tmux", "kill-session", "-t", name])
    print("TEST 1: session missing -> ensure_session should create it")
    st, detail = ensure_session(name, proc, start)
    print("  -> %s: %s" % (st, detail))
    assert st == "restarted", "expected restart, got %s" % st
    rc, _, _ = run(["tmux", "has-session", "-t", name])
    assert rc == 0, "test session not running after create"
    print("TEST 2: kill the session -> ensure_session should recreate it")
    run(["tmux", "kill-session", "-t", name])
    time.sleep(1)
    st, detail = ensure_session(name, proc, start)
    print("  -> %s: %s" % (st, detail))
    assert st == "restarted", "expected restart, got %s" % st
    print("TEST 3: session alive -> ensure_session must NOT duplicate")
    st, detail = ensure_session(name, proc, start)
    print("  -> %s: %s" % (st, detail))
    assert st == "alive", "expected alive, got %s" % st
    rc, out, _ = run(["tmux", "list-sessions", "-F", "#{session_name}"])
    assert out.splitlines().count(name) == 1, "duplicate test session!"
    run(["tmux", "kill-session", "-t", name])
    print("TEST PASS: dead-session detection + restart + no-duplicate proven")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--test-detect", action="store_true")
    args = ap.parse_args()

    if args.test_detect:
        test_detect()
        return 0

    log("WATCHDOG starting (pid %d)" % os.getpid())
    if args.once:
        sessions = watchdog_pass()
        health_pass(sessions)
        return 0

    cycle = 0
    while True:
        try:
            sessions = watchdog_pass()
            if cycle % 30 == 0:
                health_pass(sessions)
            cycle += 1
        except Exception as e:
            log("WATCHDOG error: %s" % e)
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
