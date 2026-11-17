#!/usr/bin/env python3
"""ClipForge watchdog + health alerts.

Watches the ClipForge systemd user units (runner, hourly poster, queue
maintainer, IG worker) and restarts any that is not active. Every 30
minutes verifies each platform actually posted recently, using only
on-disk evidence, and writes health.json. A NEW failure appends one
alert line to logs/health-alerts.log (one alert per failure episode;
re-alerts only after a recovery) and notifies via the configured
channel (see notifier.py; default is log-only).

Run as the user who owns the units. Modes:
  (default)  loop forever: 60s watchdog cycle, health check every 30 min
  --once     one watchdog + health pass, then exit (testing / cron)
  --test-detect
             prove the dead-unit path works with a throwaway unit
             named clipforge-watchdog-test; never touches the real units.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .branding import BRAND_SLUG
from .paths import runtime_home

BASE = str(runtime_home())
NY = ZoneInfo("America/New_York")
LOGS = os.path.join(BASE, "logs")
HEALTH_FILE = os.path.join(BASE, "health.json")
STATE_FILE = os.path.join(BASE, "watchdog-state.json")
ALERTS_FILE = os.path.join(LOGS, "health-alerts.log")

# (unit name, start command). Units are systemd user units installed by
# the ClipForge installer; Restart=on-failure already restarts a
# crashed process, and this watchdog is the second layer: it catches a
# unit that is stopped, failed, or stuck (e.g. after a bad deploy or a
# manual stop nobody resumed). Unit names come from the brand slug.
UNITS = {
    "%s-runner" % BRAND_SLUG: {
        "start": "%s run" % BRAND_SLUG,
    },
    "%s-hourly" % BRAND_SLUG: {
        "start": "%s post hourly" % BRAND_SLUG,
    },
    "%s-queue" % BRAND_SLUG: {
        "start": "%s queue maintain" % BRAND_SLUG,
    },
    "%s-ig" % BRAND_SLUG: {
        "start": "%s ig post" % BRAND_SLUG,
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


def session_alive(name, proc=None):
    """Kept name for callers: checks a systemd unit, not a tmux session.
    Returns (alive, detail). proc is ignored (systemd tracks the process)."""
    rc, out, _ = run(["systemctl", "--user", "is-active", name])
    if rc == 0 and out.strip() == "active":
        return True, "unit %s active" % name
    return False, "unit %s is %s" % (name, out.strip() or "unknown")


def ensure_session(name, proc=None, start=None):
    """Check one unit; restart it if not active. Returns (status, detail)."""
    alive, detail = session_alive(name)
    if alive:
        return "alive", detail
    # Auth-dead marker (written by a worker whose session died, e.g.
    # the IG worker): restarting cannot fix it — report failed and
    # wait for a human to re-auth. The auth flow clears the marker.
    marker = os.path.join(LOGS, name + ".auth-dead")
    if os.path.exists(marker):
        log("WATCHDOG %s not active, auth-dead marker present; "
            "NOT restarting (re-auth needed)" % name)
        return "failed", "auth dead (see %s)" % marker
    log("WATCHDOG %s not active: %s; restarting" % (name, detail))
    rc, _, err = run(["systemctl", "--user", "restart", name])
    if rc != 0:
        log("WATCHDOG %s restart FAILED: %s" % (name, err))
        return "failed", "restart failed: %s" % err
    time.sleep(2)
    alive2, detail2 = session_alive(name)
    if alive2:
        log("WATCHDOG %s restarted OK: %s" % (name, detail2))
        return "restarted", detail2
    log("WATCHDOG %s restart did not come up: %s" % (name, detail2))
    return "failed", detail2


def watchdog_pass():
    """Check all units. Returns {name: (status, detail)}."""
    out = {}
    for name in UNITS:
        out[name] = ensure_session(name)
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
    try:
        from .notifier import notify_alert
        notify_alert(platform, detail)
    except Exception as e:
        log("NOTIFY failed (alert still logged): %s" % e)


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
        "watchdog": {"units": {n: s[0] for n, s in sessions.items()}},
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
    """Prove the dead-unit path with a throwaway unit.

    Creates clipforge-watchdog-test.service (sleep 120) in the user
    systemd dir, then: missing -> restart fails gracefully (no crash);
    stopped -> restart brings it back; alive -> no duplicate restart.
    Cleans the unit file up afterwards. Never touches the real units.
    """
    import shutil
    name = "%s-watchdog-test" % BRAND_SLUG
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_path = unit_dir / (name + ".service")
    unit_body = ("[Unit]\nDescription=ClipForge watchdog test unit\n\n"
                 "[Service]\nExecStart=/bin/sleep 120\n\n"
                 "[Install]\nWantedBy=default.target\n")
    try:
        unit_dir.mkdir(parents=True, exist_ok=True)
        run(["systemctl", "--user", "stop", name])
        print("TEST 1: unit missing -> ensure_session must fail gracefully")
        st, detail = ensure_session(name)
        print("  -> %s: %s" % (st, detail))
        assert st == "failed", "expected failed, got %s" % st
        unit_path.write_text(unit_body)
        run(["systemctl", "--user", "daemon-reload"])
        run(["systemctl", "--user", "start", name])
        time.sleep(1)
        print("TEST 2: unit alive -> ensure_session must NOT restart it")
        st, detail = ensure_session(name)
        print("  -> %s: %s" % (st, detail))
        assert st == "alive", "expected alive, got %s" % st
        print("TEST 3: stop the unit -> ensure_session should restart it")
        run(["systemctl", "--user", "stop", name])
        time.sleep(1)
        st, detail = ensure_session(name)
        print("  -> %s: %s" % (st, detail))
        assert st == "restarted", "expected restarted, got %s" % st
        rc, out, _ = run(["systemctl", "--user", "show", name,
                          "--property=MainPID"])
        assert rc == 0 and out.strip() not in ("MainPID=0", ""), \
            "test unit has no main process after restart"
        print("TEST 4: alive again -> ensure_session must NOT duplicate")
        st, detail = ensure_session(name)
        print("  -> %s: %s" % (st, detail))
        assert st == "alive", "expected alive, got %s" % st
    finally:
        run(["systemctl", "--user", "stop", name])
        try:
            unit_path.unlink()
        except OSError:
            pass
        run(["systemctl", "--user", "daemon-reload"])
    print("TEST PASS: dead-unit detection + restart + no-duplicate proven")


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
