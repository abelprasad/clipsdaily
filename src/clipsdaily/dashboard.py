"""ClipForge dashboard — local web GUI for the pipeline on this box.

Single-page dashboard served by FastAPI on 127.0.0.1 ONLY (no auth in
v1; the localhost trust boundary is the auth). No frontend build step;
the page is one inline template rendered server-side.

What it does (read-first, write-almost-never):
  * Watchlist — streamers from config.yaml; add/remove (Twitch + Kick).
    Writes config.yaml ATOMICALLY (tmp + replace, YAML validated first).
    The runner re-reads config.yaml every 60s and writes
    logs/runner-state.json; the dashboard shows the effective watchlist
    from runner-state.json plus config_mtime / config_loaded_at so a
    change is visibly landed.
  * Queue — READ-ONLY view of queue/queue.json, grouped by status.
  * Post history — logs/hourly-*.log "YOUTUBE LIVE" / "TIKTOK LIVE"
    lines plus ig-outbox .posted files.
  * Health — health.json (+ watchdog-state.json if present).
  * Settings — schedule/caps/retention knobs that live in config.yaml,
    and the STOP kill-switch toggle.
  * Logs — tail of logs/*.log (latest 200 lines), HTML-escaped.

Read-safety rules (hard, v1):
  * NO queue mutations at all. NO post buttons. NO submit buttons.
  * The ONLY writes this module ever performs are config.yaml
    (validated, atomic) and the STOP file (create/delete, reversible
    by design). Nothing here can post a clip twice, delete an
    unposted queue entry, or bypass the campaign eligibility gate —
    there is no code path that does any of those things.
  * All state is resolved through clipsdaily.paths.runtime_home()
    ($CLIPSDAILY_HOME else cwd). No path is hardcoded.

Run:  python3 -m clipsdaily.dashboard [--port 8787]
"""

import argparse
import html
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .branding import BRAND_NAME
from .paths import runtime_home

DEFAULT_YT_SLOT_HOURS = [0, 3, 6, 9, 12, 15, 18, 21]
CAPTION_RULE = (
    "Captions are one line, no hashtags, no boilerplate, no date. "
    "Same one-liner on YouTube, TikTok, and Instagram. "
    "(Campaign clips carry the one campaign-required hashtag only.)"
)
PLATFORMS = ("twitch", "kick")
QUEUE_GROUPS = ("pending", "posted", "failed", "partial")
CHANNEL_RE = re.compile(r"^[A-Za-z0-9_]{1,25}$")
LIVE_RE = re.compile(
    r"^(?:\[(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})\]\s*)?"
    r"(\S+?):\s+(YOUTUBE LIVE|TIKTOK LIVE)\s+(https?://\S+)?"
)
HEALTH_OK = {"healthy", "idle"}
HEALTH_BAD = {"unhealthy", "failed"}


# ---------------------------------------------------------------- helpers

def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _read_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def load_config(home):
    """config.yaml as a dict ({} when missing/empty). Raises on bad YAML."""
    path = Path(home) / "config.yaml"
    if not path.exists():
        return {}
    cfg = _read_yaml(path)
    return cfg if isinstance(cfg, dict) else {}


def validate_config(cfg):
    """Return an error string, or None when the config is safe to write."""
    if not isinstance(cfg, dict):
        return "config must be a YAML mapping"
    streamers = cfg.get("streamers", [])
    if not isinstance(streamers, list):
        return "streamers must be a list"
    seen = set()
    for item in streamers:
        if isinstance(item, str):
            platform, channel = "twitch", item
        elif isinstance(item, dict):
            platform = item.get("platform", "twitch")
            channel = item.get("channel")
        else:
            return "each streamer must be a name or {platform, channel}"
        if platform not in PLATFORMS:
            return "streamer platform must be twitch or kick, got %r" % platform
        if not isinstance(channel, str) or not CHANNEL_RE.match(channel):
            return "bad channel name: %r" % (channel,)
        key = (platform, channel.lower())
        if key in seen:
            return "duplicate streamer: %s/%s" % (platform, channel)
        seen.add(key)
    # NOTE (IP protection, Nov 16, 2026): the dashboard deliberately
    # does NOT validate or expose spike-tuning knobs (spike_cooldown_seconds,
    # spike_threshold_multiplier, spike_min_messages, spike_window_seconds)
    # or any other cutter internals. Those live in config.yaml only.
    if "max_clips_per_day" in cfg and cfg["max_clips_per_day"] is not None:
        if not isinstance(cfg["max_clips_per_day"], int) or isinstance(
                cfg["max_clips_per_day"], bool):
            return "max_clips_per_day must be an integer"
        if not 1 <= cfg["max_clips_per_day"] <= 100:
            return "max_clips_per_day must be 1-100"
    if cfg.get("queue_clip_retention_days") is not None:
        v = cfg["queue_clip_retention_days"]
        if not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 90:
            return "queue_clip_retention_days must be an integer 0-90"
    platforms = cfg.get("platforms")
    if platforms is not None:
        if not isinstance(platforms, dict):
            return "platforms must be a mapping"
        for name in ("youtube", "tiktok", "instagram"):
            if name in platforms and not isinstance(platforms[name], bool):
                return "platforms.%s must be true/false" % name
    return None


def save_config_atomic(home, cfg):
    """Validate, then write config.yaml via tmp file + os.replace."""
    err = validate_config(cfg)
    if err:
        raise ValueError(err)
    # Round-trip through YAML first: never write what we cannot parse.
    text = yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True)
    yaml.safe_load(text)
    path = Path(home) / "config.yaml"
    tmp = path.with_suffix(".yaml.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def config_mtime(home):
    try:
        return (Path(home) / "config.yaml").stat().st_mtime
    except OSError:
        return None


def normalize_streamers(cfg):
    """config streamers -> [(platform, channel)] preserving order."""
    out = []
    for item in cfg.get("streamers", []) or []:
        if isinstance(item, str):
            out.append(("twitch", item))
        elif isinstance(item, dict) and item.get("channel"):
            out.append((item.get("platform", "twitch"), item["channel"]))
    return out


def read_runner_state(home):
    state = _read_json(Path(home) / "logs" / "runner-state.json")
    return state if isinstance(state, dict) else {}


def read_queue(home):
    """READ-ONLY. Returns the queue entries list ([] when absent/bad)."""
    data = _read_json(Path(home) / "queue" / "queue.json")
    return data if isinstance(data, list) else []


def group_queue(entries):
    groups = {g: [] for g in QUEUE_GROUPS}
    for e in entries:
        if not isinstance(e, dict):
            continue
        status = e.get("status") or "pending"
        if status not in groups:
            # Unknown status: posted somewhere -> partial, else pending.
            status = "partial" if e.get("yt_url") or e.get("tt_url") else "pending"
        groups[status].append(e)
    return groups


def read_health(home):
    health = _read_json(Path(home) / "health.json")
    return health if isinstance(health, dict) else {}


def read_watchdog_state(home):
    state = _read_json(Path(home) / "watchdog-state.json")
    return state if isinstance(state, dict) else {}


def post_history(home, limit=50):
    """Latest LIVE posts from hourly logs + IG .posted files, newest first.

    Each item: {clip_id, platform, url, time, detail}.
    """
    items = []
    logs_dir = Path(home) / "logs"
    if logs_dir.is_dir():
        for path in sorted(logs_dir.glob("hourly-*.log")):
            try:
                lines = path.read_text(errors="replace").splitlines()
            except OSError:
                continue
            for line in lines:
                m = LIVE_RE.search(line)
                if not m:
                    continue
                ts, clip_id, kind, url = m.groups()
                items.append({
                    "clip_id": clip_id,
                    "platform": ("youtube" if kind.startswith("YOUTUBE")
                                 else "tiktok"),
                    "url": (url or "").rstrip(")"),
                    "time": ts or "",
                    "detail": line.strip(),
                })
    outbox = Path(home) / "ig-outbox"
    if outbox.is_dir():
        for clip_dir in outbox.iterdir():
            if not clip_dir.is_dir():
                continue
            posted = _read_json(clip_dir / ".posted")
            if not isinstance(posted, dict):
                continue
            items.append({
                "clip_id": clip_dir.name,
                "platform": "instagram",
                "url": "",
                "time": posted.get("posted_at_utc") or "",
                "detail": "media_fbid=%s" % posted.get("media_fbid", "?"),
            })
    items.sort(key=lambda i: i["time"], reverse=True)
    return items[:limit]


def tail_logs(home, max_lines=200):
    """Latest lines across logs/*.log, oldest-first, newest files first."""
    logs_dir = Path(home) / "logs"
    if not logs_dir.is_dir():
        return []
    files = sorted(logs_dir.glob("*.log"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    lines = []
    for path in files:
        try:
            chunk = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        lines.extend("%s: %s" % (path.name, ln) for ln in chunk)
        if len(lines) >= max_lines:
            break
    return lines[-max_lines:]


def stop_active(home):
    return (Path(home) / "STOP").exists()


def set_stop(home, active):
    """Create/delete the STOP kill-switch file. The only destructive-ish
    action in v1, reversible by design (delete STOP to resume)."""
    path = Path(home) / "STOP"
    if active:
        path.touch(exist_ok=True)
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return stop_active(home)


def health_status_class(status):
    if status in HEALTH_OK:
        return "ok"
    if status in HEALTH_BAD:
        return "bad"
    if status == "known_broken":
        return "warn"
    return "idle"


def _fmt_ts(ts):
    """Epoch float or ISO string -> readable local time, else as-is."""
    if ts is None:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return str(ts)


# ---------------------------------------------------------------- page

def render_dashboard(home, notice=""):
    cfg = {}
    cfg_error = None
    try:
        cfg = load_config(home)
    except Exception as e:  # bad YAML: show the page, flag the error
        cfg_error = str(e)
    streamers = normalize_streamers(cfg)
    runner = read_runner_state(home)
    queue = read_queue(home)
    groups = group_queue(queue)
    health = read_health(home)
    watchdog = read_watchdog_state(home)
    history = post_history(home)
    logs = tail_logs(home)
    stopped = stop_active(home)
    yt_slots = cfg.get("youtube_slot_hours") or DEFAULT_YT_SLOT_HOURS
    esc = html.escape

    def watchlist_rows():
        rows = ""
        for platform, channel in streamers:
            rows += (
                '<tr><td>%s</td><td>%s</td>'
                '<td><form method="post" action="/api/watchlist/remove"'
                ' style="display:inline">'
                '<input type="hidden" name="platform" value="%s">'
                '<input type="hidden" name="channel" value="%s">'
                '<button type="submit">Remove</button></form></td></tr>'
                % (esc(platform), esc(channel), esc(platform), esc(channel)))
        return rows or '<tr><td colspan="3">No streamers watched.</td></tr>'

    def queue_rows(entries):
        rows = ""
        for e in entries:
            rows += (
                '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td>'
                '<td>%s</td><td>%s</td><td>%s</td></tr>'
                % (esc(str(e.get("id", "?"))), esc(str(e.get("streamer", "?"))),
                   esc(str(e.get("platform", "?"))),
                   esc(str(e.get("created_at", "—"))),
                   esc(str(e.get("yt_url") or "—")),
                   esc(str(e.get("tt_url") or "—")),
                   esc(str(e.get("retries", e.get("yt_retries", 0))))))
        return rows or '<tr><td colspan="7">None.</td></tr>'

    def history_rows():
        rows = ""
        for h in history:
            link = ('<a href="%s">%s</a>' % (esc(h["url"]), esc(h["url"]))) \
                if h["url"] else "—"
            rows += ('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                     % (esc(h["clip_id"]), esc(h["platform"]), link,
                        esc(h["time"] or "—")))
        return rows or '<tr><td colspan="4">No posts found yet.</td></tr>'

    def health_rows():
        rows = ""
        for name in ("youtube", "instagram", "tiktok", "queue"):
            entry = health.get(name) or {}
            status = entry.get("status", "unknown")
            last = entry.get("last_post") or entry.get("last_failure") or "—"
            rows += ('<tr><td>%s</td>'
                     '<td><span class="status-%s">%s</span></td>'
                     '<td>%s</td><td>%s</td></tr>'
                     % (esc(name), health_status_class(status),
                        esc(str(status)), esc(str(last)),
                        esc(str(entry.get("detail", "")))))
        return rows

    platforms = cfg.get("platforms") or {}
    retention = cfg.get("queue_clip_retention_days", "not set")
    runner_watchlist = ", ".join(runner.get("watchlist") or []) or "—"
    checked_at = esc(str(health.get("checked_at", "—")))
    wd_sessions = watchdog.get("watchdog", {}).get("sessions") \
        or watchdog.get("sessions") or {}
    wd_text = (", ".join("%s: %s" % (k, v) for k, v in wd_sessions.items())
               if wd_sessions else "no watchdog-state.json yet")

    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>%s dashboard</title>
<style>
body{font-family:system-ui,sans-serif;max-width:960px;margin:0 auto;padding:16px}
h1{margin-bottom:0}h2{border-bottom:1px solid #ccc;padding-bottom:4px}
table{border-collapse:collapse;width:100%%}td,th{border:1px solid #ddd;padding:4px 8px;text-align:left}
.status-ok{color:green;font-weight:bold}.status-bad{color:red;font-weight:bold}
.status-warn{color:#b60;font-weight:bold}.status-idle{color:#666}
.notice{background:#ffe;padding:8px;border:1px solid #cc0}
pre{background:#111;color:#ddd;padding:8px;overflow:auto;max-height:300px}
.stop-on{color:red;font-weight:bold}.stop-off{color:green;font-weight:bold}
</style></head><body>
<h1>%s</h1><p>Fully automatic stream clip pipeline: record, cut, post.
Local dashboard only — bound to 127.0.0.1, no remote access in v1.</p>
%s
<section id="health"><h2>Health</h2>
<p>Checked at: %s</p>
<table><tr><th>Platform</th><th>Status</th><th>Last post / failure</th><th>Detail</th></tr>%s</table>
<p>Watchdog: %s</p></section>
<section id="watchlist"><h2>Watchlist</h2>
<p>Config file: config.yaml (mtime %s). Runner effective watchlist
(from logs/runner-state.json): %s. Runner loaded config at: %s.</p>
%s
<table><tr><th>Platform</th><th>Channel</th><th></th></tr>%s</table>
<form method="post" action="/api/watchlist/add">
<input name="platform" placeholder="twitch or kick" required>
<input name="channel" placeholder="channel" required>
<button type="submit">Add streamer</button></form></section>
<section id="queue"><h2>Queue</h2>
<p>Read-only. %d entries: %d pending, %d posted, %d failed, %d partial.
No delete or retry in v1.</p>
<h3>Pending</h3><table><tr><th>ID</th><th>Streamer</th><th>Platform</th><th>Created</th><th>YouTube</th><th>TikTok</th><th>Retries</th></tr>%s</table>
<h3>Posted</h3><table><tr><th>ID</th><th>Streamer</th><th>Platform</th><th>Created</th><th>YouTube</th><th>TikTok</th><th>Retries</th></tr>%s</table>
<h3>Failed</h3><table><tr><th>ID</th><th>Streamer</th><th>Platform</th><th>Created</th><th>YouTube</th><th>TikTok</th><th>Retries</th></tr>%s</table>
<h3>Partial</h3><table><tr><th>ID</th><th>Streamer</th><th>Platform</th><th>Created</th><th>YouTube</th><th>TikTok</th><th>Retries</th></tr>%s</table>
</section>
<section id="history"><h2>Post history</h2>
<table><tr><th>Clip</th><th>Platform</th><th>Link</th><th>Time</th></tr>%s</table></section>
<section id="settings"><h2>Settings</h2>
<p>YouTube slot hours: %s (fixed in the hourly poster in v1; shown, not editable).
Max clips/day is read live by the runner.</p>
<p>Captions: %s</p>
<form method="post" action="/api/settings">
<label>Max clips per day <input type="number" name="max_clips_per_day" min="1" max="100" value="%s"></label><br>
<label>Queue clip retention (days) <input type="number" name="queue_clip_retention_days" min="0" max="90" value="%s"></label><br>
<label><input type="checkbox" name="platform_youtube" %s> YouTube posting</label><br>
<label><input type="checkbox" name="platform_tiktok" %s> TikTok posting</label><br>
<label><input type="checkbox" name="platform_instagram" %s> Instagram posting</label><br>
<button type="submit">Save settings</button></form>
<h3>Kill switch</h3>
<p>Status: <span class="%s">%s</span> — creating STOP pauses all
posting immediately; deleting it resumes. Recordings in progress are left alone.</p>
<form method="post" action="/api/stop">
<input type="hidden" name="action" value="%s">
<button type="submit">%s</button></form></section>
<section id="logs"><h2>Logs</h2><pre>%s</pre></section>
</body></html>""" % (
        esc(BRAND_NAME), esc(BRAND_NAME),
        ('<p class="notice">%s</p>' % esc(notice)) if notice else "",
        checked_at, health_rows(), esc(wd_text),
        esc(_fmt_ts(config_mtime(home))), esc(runner_watchlist),
        esc(str(runner.get("config_loaded_at", "—"))),
        ('<p class="notice">config.yaml is invalid YAML and was NOT '
         'changed: %s</p>' % esc(cfg_error)) if cfg_error else "",
        watchlist_rows(),
        len(queue), len(groups["pending"]), len(groups["posted"]),
        len(groups["failed"]), len(groups["partial"]),
        queue_rows(groups["pending"]), queue_rows(groups["posted"]),
        queue_rows(groups["failed"]), queue_rows(groups["partial"]),
        history_rows(),
        esc(", ".join("%02d:00" % h for h in yt_slots)),
        esc(CAPTION_RULE),
        esc(str(cfg.get("max_clips_per_day", ""))),
        esc("" if retention == "not set" else str(retention)),
        "checked" if platforms.get("youtube") else "",
        "checked" if platforms.get("tiktok") else "",
        "checked" if platforms.get("instagram") else "",
        "stop-on" if stopped else "stop-off",
        "STOPPED — posting paused" if stopped else "Running",
        "off" if stopped else "on",
        "Resume posting (delete STOP)" if stopped else "Pause posting (create STOP)",
        esc("\n".join(logs)),
    )


# ---------------------------------------------------------------- app

def create_app(home=None):
    home = Path(home) if home is not None else runtime_home()
    app = FastAPI(title="%s dashboard" % BRAND_NAME)
    app.state.home = home

    def _home(request):
        return request.app.state.home

    def _is_json(request):
        return "application/json" in request.headers.get("content-type", "")

    async def _params(request):
        if _is_json(request):
            try:
                return await request.json()
            except Exception:
                return {}
        return dict(await request.form())

    def _done(request, notice):
        if _is_json(request):
            return JSONResponse({"ok": True, "notice": notice})
        return RedirectResponse(url="/?notice=" + notice, status_code=303)

    def _fail(request, message, status=400):
        if _is_json(request):
            return JSONResponse({"ok": False, "error": message},
                                status_code=status)
        return RedirectResponse(url="/?notice=" + message, status_code=303)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request, notice: str = ""):
        return render_dashboard(_home(request), notice=notice)

    @app.get("/api/state")
    async def api_state(request: Request):
        home = _home(request)
        try:
            cfg = load_config(home)
        except Exception as e:
            cfg = {"_error": str(e)}
        queue = read_queue(home)
        groups = group_queue(queue)
        return {
            "brand": BRAND_NAME,
            "home": str(home),
            "config": cfg,
            "config_mtime": config_mtime(home),
            "runner_state": read_runner_state(home),
            "queue_counts": {g: len(v) for g, v in groups.items()},
            "health": read_health(home),
            "watchdog_state": read_watchdog_state(home),
            "stop_active": stop_active(home),
        }

    @app.get("/api/queue")
    async def api_queue(request: Request):
        return {"entries": read_queue(request.app.state.home)}

    @app.get("/api/history")
    async def api_history(request: Request):
        return {"posts": post_history(request.app.state.home)}

    @app.get("/api/logs")
    async def api_logs(request: Request):
        return {"lines": tail_logs(request.app.state.home)}

    @app.post("/api/watchlist/add")
    async def watchlist_add(request: Request):
        home = _home(request)
        params = await _params(request)
        platform = str(params.get("platform", "")).strip().lower()
        channel = str(params.get("channel", "")).strip()
        if platform not in PLATFORMS:
            return _fail(request, "platform must be twitch or kick")
        if not CHANNEL_RE.match(channel):
            return _fail(request, "bad channel name: %r" % channel)
        try:
            cfg = load_config(home)
        except Exception as e:
            return _fail(request, "config.yaml is invalid YAML: %s" % e)
        streamers = normalize_streamers(cfg)
        if (platform, channel.lower()) in [(p, c.lower()) for p, c in streamers]:
            return _fail(request, "%s/%s is already watched" % (platform, channel))
        cfg["streamers"] = ([{"platform": p, "channel": c} for p, c in streamers]
                            + [{"platform": platform, "channel": channel}])
        try:
            save_config_atomic(home, cfg)
        except ValueError as e:
            return _fail(request, str(e))
        return _done(request, "Added %s/%s — runner picks it up within 60s."
                     % (platform, channel))

    @app.post("/api/watchlist/remove")
    async def watchlist_remove(request: Request):
        home = _home(request)
        params = await _params(request)
        platform = str(params.get("platform", "")).strip().lower()
        channel = str(params.get("channel", "")).strip()
        try:
            cfg = load_config(home)
        except Exception as e:
            return _fail(request, "config.yaml is invalid YAML: %s" % e)
        before = normalize_streamers(cfg)
        after = [(p, c) for p, c in before
                 if not (p == platform and c.lower() == channel.lower())]
        if len(after) == len(before):
            return _fail(request, "%s/%s is not on the watchlist"
                         % (platform, channel), status=404)
        cfg["streamers"] = [{"platform": p, "channel": c} for p, c in after]
        try:
            save_config_atomic(home, cfg)
        except ValueError as e:
            return _fail(request, str(e))
        return _done(request, "Removed %s/%s — runner stops it within 60s."
                     % (platform, channel))

    @app.post("/api/settings")
    async def settings(request: Request):
        home = _home(request)
        params = await _params(request)
        try:
            cfg = load_config(home)
        except Exception as e:
            return _fail(request, "config.yaml is invalid YAML: %s" % e)
        try:
            if params.get("max_clips_per_day") not in (None, ""):
                cfg["max_clips_per_day"] = int(params["max_clips_per_day"])
            # IP protection: spike-tuning params are never accepted
            # from the GUI (a stale form/bookmark sending one is ignored,
            # not an error). See validate_config note above.
            if params.get("queue_clip_retention_days") not in (None, ""):
                cfg["queue_clip_retention_days"] = int(
                    params["queue_clip_retention_days"])
        except (TypeError, ValueError):
            return _fail(request, "settings values must be integers")
        platforms = dict(cfg.get("platforms") or {})
        # HTML checkboxes only send a value when checked; JSON sends bools.
        for name in ("youtube", "tiktok", "instagram"):
            key = "platform_" + name
            if key in params:
                raw = params[key]
                platforms[name] = raw in ("on", True, "true", "1", 1)
        cfg["platforms"] = platforms
        try:
            save_config_atomic(home, cfg)
        except ValueError as e:
            return _fail(request, str(e))
        return _done(request, "Settings saved — runner picks them up "
                     "within 60s.")

    @app.post("/api/stop")
    async def stop_toggle(request: Request):
        home = _home(request)
        params = await _params(request)
        action = str(params.get("action", "")).strip().lower()
        if action not in ("on", "off"):
            return _fail(request, "action must be on or off")
        active = set_stop(home, action == "on")
        return _done(request, "Posting PAUSED (STOP created)."
                     if active else "Posting resumed (STOP deleted).")

    return app


app = create_app()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="%s dashboard (localhost only)" % BRAND_NAME)
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address; loopback only (default 127.0.0.1)")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get(
                            "CLIPFORGE_DASHBOARD_PORT", "8787")))
    args = parser.parse_args(argv)
    if args.host not in ("127.0.0.1", "::1", "localhost"):
        parser.error("refusing non-loopback bind address %r: the dashboard "
                     "is localhost-only in v1" % args.host)
    import uvicorn
    print("[%s] dashboard at http://%s:%d (runtime home: %s)"
          % (BRAND_NAME, args.host, args.port, runtime_home()), flush=True)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
