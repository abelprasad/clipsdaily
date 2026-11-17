"""Content Rewards browser automation for ClipForge (OPT-IN ONLY).

Replaces the three Friday/browser touchpoints of the money loop with
on-box Playwright automation:

  1. join    -- click Join on requested campaigns, verify the Joined badge
  2. submit  -- submit pending outbox jobs, verify Pending + submission ID
  3. earnings-dump -- scrape the submissions dashboard to earnings_dump.json

OPT-IN: every command refuses to run unless ``campaign_automation: true``
is set in the runtime home's config.yaml. Default is OFF.

ONE-STRIKE RULE: Content Rewards bans an account from EVERY campaign
permanently for a single bad submission. This module is paranoid by
design and FAILS CLOSED on every path:

  * No session file -> refuse, touch nothing.
  * Gate failure (re-run before EVERY submit) -> mark failed, never submit.
  * Job past the 30-minute submit window -> never submit late.
  * Join badge not verifiably visible -> status failed, never claim a join.
  * Dashboard row without a submission ID -> mark failed, never claim
    a submit.
  * A clip already on the dashboard (or a job already submitted) is
    never submitted twice.
  * Any doubt at any step -> do nothing to the remote site, record
    failed, move on.

The module never stores a password. Auth is a guided one-time login:
``clipforge auth contentrewards`` opens a headed browser, the operator
logs in by hand, and only the Playwright storage state is saved
(0600) at <runtime-home>/.auth/contentrewards_state.json.

REAL-SITE WARNING: the campaign-page / submit-form / dashboard
selectors in SELECTORS below were written against the Nov 15, 2026
browser sessions' descriptions, NOT against a live inspected page.
No test account exists, so the selectors are UNVERIFIED against the
real site. See docs/CONTENTREWARDS_AUTO.md for the manual verification
steps that must pass before this is ever enabled against
contentrewards.com. The unit tests run against a local fixture that
implements these same selectors.

Usage (standalone; the clipforge CLI wires these in later):
  python3 -m clipsdaily.contentrewards auth
  python3 -m clipsdaily.contentrewards join [--dry-run]
  python3 -m clipsdaily.contentrewards submit [--dry-run]
  python3 -m clipsdaily.contentrewards earnings-dump [--dry-run]

Runtime home resolves exactly like clipsdaily.paths.runtime_home():
$CLIPSDAILY_HOME else the current working directory. Never hardcoded.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import auto_submit as _auto_submit
from .branding import BRAND_NAME
from .campaigns import load_campaigns
from .eligibility_gate import gate_clip
from .paths import runtime_home

BASE_URL_DEFAULT = "https://contentrewards.com"
BASE_URL_ENV = "CLIPFORGE_CONTENTREWARDS_BASE_URL"
SUBMIT_WINDOW_MINUTES = 30

# Selectors for the real site. UNVERIFIED (see module docstring): the
# fixture in tests/test_contentrewards.py implements these exact
# selectors, but the real contentrewards.com DOM has never been
# inspected by this module. Each entry is a list of candidates tried
# in order; the first visible match wins. If none matches, the step
# fails closed. Update these ONLY after the manual verification steps
# in docs/CONTENTREWARDS_AUTO.md, and update the fixture to match.
SELECTORS = {
    # Campaign page: the Join button.
    "join_button": ["#join-btn", "button:has-text(\"Join\")"],
    # Campaign page: the green Joined badge, visible only after a join.
    "joined_badge": ["#joined-badge", "text=Joined"],
    # Campaign page: the submit form's clip-URL field.
    "clip_url_input": ["#clip-url-input", "input[name=\"clipUrl\"]",
                       "input[type=\"url\"]"],
    # Campaign page: the form's submit button.
    "submit_button": ["#submit-clip-btn", "button:has-text(\"Submit\")"],
    # Campaign page: confirmation shown after a successful submit.
    "submit_confirmation": ["#submit-confirmation",
                            "text=/clip submitted/i"],
    # Submissions dashboard: the submissions table / rows.
    "dashboard_table": ["#submissions-table", "table"],
    "dashboard_rows": ["#submissions-table tbody tr",
                       "table tbody tr", "tr[data-submission-id]"],
}

DASHBOARD_PATH = "/dashboard/submissions"


class AutomationDisabled(Exception):
    """campaign_automation is not true in config.yaml."""


class SessionMissing(Exception):
    """No Content Rewards storage-state session file exists."""


class DashboardError(Exception):
    """The submissions dashboard could not be read."""


# ---------------------------------------------------------------- paths


def _home(home=None):
    return Path(home) if home is not None else runtime_home()


def config_path(home):
    return _home(home) / "config.yaml"


def session_path(home):
    return _home(home) / ".auth" / "contentrewards_state.json"


def join_requests_path(home):
    return _home(home) / "join_requests.json"


def join_results_path(home):
    return _home(home) / "join_results.json"


def earnings_dump_path(home):
    return _home(home) / "earnings_dump.json"


def log_path(home):
    home = _home(home)
    return home / "logs" / ("contentrewards-%s.log"
                            % time.strftime("%Y%m%d"))


def base_url(home=None, override=None):
    """Base URL for Content Rewards. Env/test override, else the live site."""
    if override:
        return override.rstrip("/")
    return os.environ.get(BASE_URL_ENV, BASE_URL_DEFAULT).rstrip("/")


def campaign_url(campaign_id, base=None):
    return "%s/c/campaigns/%s" % (base or BASE_URL_DEFAULT, campaign_id)


def dashboard_url(base=None):
    return "%s%s" % (base or BASE_URL_DEFAULT, DASHBOARD_PATH)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def log(home, msg):
    """Append to logs/contentrewards-YYYYMMDD.log and mirror to stderr."""
    home = _home(home)
    line = "[%s] %s" % (_now(), msg)
    try:
        p = log_path(home)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True, file=sys.stderr)


# ------------------------------------------------------- config + session


def automation_enabled(home):
    """True only when config.yaml sets `campaign_automation: true`.

    Default False. Missing/unreadable config is False. The flag is read
    fresh on every call so flipping config.yaml takes effect without
    a restart.
    """
    home = _home(home)
    try:
        text = config_path(home).read_text()
    except Exception:
        return False
    try:
        import yaml
        data = yaml.safe_load(text) or {}
        if isinstance(data, dict) and "campaign_automation" in data:
            return bool(data.get("campaign_automation"))
    except Exception:
        pass
    m = re.search(r"(?m)^\s*campaign_automation\s*:\s*(true|false)\s*$",
                  text)
    return bool(m and m.group(1) == "true")


def require_enabled(home):
    home = _home(home)
    if not automation_enabled(home):
        raise AutomationDisabled(
            "%s campaign automation is OFF: set "
            "`campaign_automation: true` in %s to opt in (see "
            "docs/CONTENTREWARDS_AUTO.md for the one-strike warning)"
            % (BRAND_NAME, config_path(home)))


def session_exists(home):
    p = session_path(home)
    return p.exists() and p.stat().st_size > 0


def ensure_session(home):
    """Return the storage-state path, or raise SessionMissing."""
    home = _home(home)
    if not session_exists(home):
        raise SessionMissing(
            "no Content Rewards session at %s — run "
            "`python3 -m clipsdaily.contentrewards auth` first"
            % session_path(home))
    return session_path(home)


def login_headed(home, base=None, timeout_s=600):
    """Guided one-time login. Opens a headed browser; the operator logs
    in by hand in the window, then presses Enter here. Only the
    Playwright storage state is saved (0600). Never stores a password.

    Refuses to run unless campaign_automation is true.
    """
    from playwright.sync_api import sync_playwright

    home = _home(home)
    require_enabled(home)
    base = base_url(home, base)
    state = session_path(home)
    state.parent.mkdir(parents=True, exist_ok=True)
    print("Opening %s in a headed browser." % base)
    print("Log in as the %s Content Rewards account in the window,"
          " then press Enter here." % BRAND_NAME)
    print("Nothing is submitted or joined during this step.")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(base, timeout=60000)
        try:
            input("Press Enter once you are logged in "
                  "(Ctrl-C to abort without saving): ")
        except KeyboardInterrupt:
            browser.close()
            log(home, "auth aborted by operator; no session saved")
            return None
        context.storage_state(path=str(state))
        browser.close()
    try:
        os.chmod(state, 0o600)
    except Exception:
        pass
    if not session_exists(home):
        raise SessionMissing("storage state was not saved at %s" % state)
    log(home, "auth: session saved to %s (0600)" % state)
    return state


# ------------------------------------------------------------ json helpers


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default


def _atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def _parse_ts(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(str(s), fmt)
        except Exception:
            continue
    return None


def _platform_from_url(url):
    u = (url or "").lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "tiktok.com" in u:
        return "tiktok"
    if "instagram.com" in u:
        return "instagram"
    return "unknown"


def _parse_int(value):
    try:
        return int(str(value).replace(",", "").strip())
    except Exception:
        m = re.search(r"(\d+)", str(value or ""))
        return int(m.group(1)) if m else 0


def _parse_money_cents(value):
    """Cell text -> cents. Plain ints are already cents; $x.xx is dollars."""
    s = str(value or "").strip()
    if "$" in s:
        try:
            return int(round(float(s.replace("$", "").replace(",", "")) * 100))
        except Exception:
            return 0
    return _parse_int(s)


# ------------------------------------------------- auto_submit integration


def _rebind_auto_submit(home):
    """Point the imported auto_submit module at this runtime home.

    auto_submit binds its OUTBOX_DIR at import time from the ambient
    runtime home; rebind it explicitly so calls below always operate
    on the home the caller passed, never on an import-time default.
    """
    home = _home(home)
    _auto_submit.HERE = home
    _auto_submit.OUTBOX_DIR = home / "submit-outbox"
    _auto_submit.QUEUE_FILE = home / "queue" / "queue.json"
    _auto_submit.CAMPAIGN_QUEUE_FILE = home / "campaign_queue.json"
    _auto_submit.IG_OUTBOX = home / "ig-outbox"


def _pending_jobs(home):
    """Pending outbox jobs via auto_submit's own --list-pending logic
    (imported, not reimplemented): it expires stale jobs as a side
    effect, exactly like the CLI. Returns the pending list."""
    home = _home(home)
    _rebind_auto_submit(home)
    _auto_submit.expire_stale_jobs(_auto_submit.list_jobs())
    return [j for j in _auto_submit.list_jobs()
            if j.get("status") == "pending"]


def _read_outbox_jobs(home):
    """Read-only outbox scan (dry-run path): no expiry, no writes."""
    home = _home(home)
    outbox = home / "submit-outbox"
    jobs = []
    if not outbox.exists():
        return jobs
    for p in sorted(outbox.glob("*.json")):
        try:
            jobs.append(json.loads(p.read_text()))
        except Exception:
            continue
    return jobs


def _auto_submit_cli(home, args):
    """Run `python -m clipsdaily.auto_submit <args>` as a subprocess
    with CLIPSDAILY_HOME set, so --mark-submitted / --mark-failed run
    through auto_submit's own CLI code, not a copy of it."""
    home = _home(home)
    env = dict(os.environ)
    env["CLIPSDAILY_HOME"] = str(home)
    src = str(Path(__file__).resolve().parent.parent)
    pp = env.get("PYTHONPATH", "")
    if src not in pp.split(os.pathsep):
        env["PYTHONPATH"] = src + (os.pathsep + pp if pp else "")
    r = subprocess.run(
        [sys.executable, "-m", "clipsdaily.auto_submit"] + args,
        capture_output=True, text=True, timeout=120, env=env)
    try:
        out = json.loads(r.stdout) if r.stdout.strip() else {}
    except Exception:
        out = {}
    return r.returncode, out, r.stderr


def mark_submitted(home, job_id, submission_id):
    rc, out, err = _auto_submit_cli(
        home, ["--mark-submitted", job_id,
               "--submission-id", submission_id])
    if rc != 0 or not out.get("ok"):
        log(home, "%s: MARK-SUBMITTED FAILED (rc=%s): %s %s"
            % (job_id, rc, out, err.strip()[-300:]))
        return False
    return True


def mark_failed(home, job_id, reason):
    rc, out, err = _auto_submit_cli(
        home, ["--mark-failed", job_id, "--reason", reason])
    if rc != 0 or not out.get("ok"):
        log(home, "%s: MARK-FAILED FAILED (rc=%s): %s %s"
            % (job_id, rc, out, err.strip()[-300:]))
        return False
    return True


# ------------------------------------------------------------- queue/gate


def find_queue_entry(home, clip_id):
    """Find the queue/campaign-queue entry for a clip, or None."""
    home = _home(home)
    for f in (home / "queue" / "queue.json", home / "campaign_queue.json"):
        for entry in _read_json(f, []):
            if isinstance(entry, dict) and entry.get("id") == clip_id:
                return entry
    return None


def _resolve_clip_paths(home, entry):
    """Copy an entry, resolving relative clip file paths against home."""
    home = _home(home)
    entry = dict(entry)
    for key in ("clip30", "tiktok"):
        p = entry.get(key)
        if p and not Path(p).is_absolute():
            entry[key] = str(home / p)
    return entry


# -------------------------------------------------------------- playwright


def _launch(home, base=None):
    """Start Playwright with the saved session. Caller closes it."""
    from playwright.sync_api import sync_playwright

    home = _home(home)
    state = ensure_session(home)
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(storage_state=str(state))
    return pw, browser, context


def _first_visible(page, selectors, timeout_ms=15000):
    """First selector (in order) whose locator becomes visible, else None."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            return loc
        except Exception:
            continue
    return None


def _badge_visible(page, timeout_ms=15000):
    for sel in SELECTORS["joined_badge"]:
        try:
            if page.locator(sel).first.is_visible():
                return True
            page.locator(sel).first.wait_for(state="visible",
                                            timeout=timeout_ms)
            return True
        except Exception:
            continue
    return False


def _scrape_dashboard(page):
    """Scrape the submissions dashboard into earnings_dump rows.

    Prefers data-* attributes on each row; falls back to cell text in
    column order: submission_id, clip_url, platform, campaign, status,
    views, payout, submitted_at. Raises DashboardError if no table or
    no rows can be read.
    """
    table = _first_visible(page, SELECTORS["dashboard_table"],
                           timeout_ms=15000)
    if table is None:
        raise DashboardError("submissions dashboard table not found")
    rows = None
    for sel in SELECTORS["dashboard_rows"]:
        candidate = page.locator(sel)
        if candidate.count() > 0:
            rows = candidate
            break
    if rows is None:
        # Table exists but has no submission rows yet: a valid empty
        # dashboard, not an error (the submit pre-check relies on this).
        return []
    count = rows.count()
    out = []
    for i in range(count):
        row = rows.nth(i)
        cells = [c.strip() for c in row.locator("td").all_inner_texts()]
        data = {
            "submission_id": row.get_attribute("data-submission-id")
                               or (cells[0] if len(cells) > 0 else ""),
            "clip_url": row.get_attribute("data-clip-url")
                        or (cells[1] if len(cells) > 1 else ""),
            "platform": row.get_attribute("data-platform")
                        or (cells[2] if len(cells) > 2 else ""),
            "campaign_id": row.get_attribute("data-campaign-id") or "",
            "campaign_title": (row.get_attribute("data-campaign-title")
                               or (cells[3] if len(cells) > 3 else "")),
            "status": row.get_attribute("data-status")
                      or (cells[4] if len(cells) > 4 else ""),
            "views": _parse_int(row.get_attribute("data-views")
                                or (cells[5] if len(cells) > 5 else 0)),
            "payout_cents": _parse_money_cents(
                row.get_attribute("data-payout-cents")
                or (cells[6] if len(cells) > 6 else 0)),
            "submitted_at": row.get_attribute("data-submitted-at")
                            or (cells[7] if len(cells) > 7 else ""),
        }
        if not data["submission_id"] and not data["clip_url"]:
            continue
        if not data["platform"]:
            data["platform"] = _platform_from_url(data["clip_url"])
        if not data["submission_id"]:
            # earnings.py matches by clip_url when no ID is shown.
            data["submission_id"] = data["clip_url"]
        out.append(data)
    return out


def _find_row(rows, clip_url):
    for row in rows:
        if row.get("clip_url") and clip_url in row["clip_url"]:
            return row
    return None


# ------------------------------------------------------------------- join


def join_campaigns(home=None, base=None, dry_run=False):
    """Join every campaign in join_requests.json not already joined.

    Verifies the green Joined badge before recording a join. Any
    failure records {status: failed, reason} and moves on.
    Returns a summary dict. Dry-run prints the plan and writes nothing.
    """
    home = _home(home)
    base = base_url(home, base)
    require_enabled(home)
    requests = _read_json(join_requests_path(home), [])
    results = _read_json(join_results_path(home), [])
    already = {r.get("campaign_id") for r in results
               if r.get("status") == "joined"}
    summary = {"requested": len(requests), "joined": 0, "failed": 0,
               "skipped": 0, "results": []}
    todo = []
    for req in requests:
        cid = req.get("campaign_id")
        if not cid:
            summary["failed"] += 1
            summary["results"].append(
                {"campaign_id": None, "status": "failed",
                 "reason": "join request has no campaign_id", "at": _now()})
        elif cid in already:
            summary["skipped"] += 1
        else:
            todo.append(req)
    if dry_run:
        for req in todo:
            cid = req.get("campaign_id")
            print("DRY-RUN join: WOULD open %s and click Join"
                  % (req.get("url") or campaign_url(cid, base)))
        for req in requests:
            if req.get("campaign_id") in already:
                print("DRY-RUN join: SKIP %s (already joined)"
                      % req.get("campaign_id"))
        log(home, "join dry-run: %d requested, %d already joined"
            % (len(requests), summary["skipped"]))
        return summary
    if not todo:
        log(home, "join: nothing to do (%d already joined, %d failed)"
            % (summary["skipped"], summary["failed"]))
        return summary
    ensure_session(home)
    pw = browser = context = None
    try:
        pw, browser, context = _launch(home, base)
        page = context.new_page()
        for req in todo:
            cid = req.get("campaign_id")
            url = req.get("url") or campaign_url(cid, base)
            result = {"campaign_id": cid, "status": "failed",
                      "reason": "", "at": _now()}
            try:
                page.goto(url, timeout=30000)
                btn = _first_visible(page, SELECTORS["join_button"])
                if btn is None:
                    raise RuntimeError("Join button not found on %s" % url)
                btn.click(timeout=10000)
                if not _badge_visible(page):
                    raise RuntimeError(
                        "Joined badge not visible after clicking Join")
                result["status"] = "joined"
                result["reason"] = "Joined badge verified"
                summary["joined"] += 1
                log(home, "join %s: JOINED (badge verified)" % cid)
            except Exception as e:
                result["reason"] = str(e)[:300]
                summary["failed"] += 1
                log(home, "join %s: FAILED: %s" % (cid, result["reason"]))
            results.append(result)
            summary["results"].append(result)
            _atomic_write_json(join_results_path(home), results)
            already.add(cid) if result["status"] == "joined" else None
    finally:
        if context is not None:
            context.close()
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()
    return summary


# ----------------------------------------------------------------- submit


def submit_pending(home=None, base=None, dry_run=False):
    """Submit every pending outbox job, with the full paranoid chain.

    Per job: expiry check -> queue entry lookup -> eligibility gate
    re-run -> dashboard pre-check (already submitted?) -> fill the
    submit form -> confirm on-page -> verify dashboard Pending WITH a
    submission ID -> mark submitted with that ID. Any failure marks
    the job failed (never submitted) and moves on. Dry-run parses jobs,
    runs gates, prints the plan, and writes nothing / opens no browser.
    """
    home = _home(home)
    base = base_url(home, base)
    require_enabled(home)
    campaigns = load_campaigns(home / "campaigns.json")
    if dry_run:
        jobs = [j for j in _read_outbox_jobs(home)
                if j.get("status") == "pending"]
        summary = {"pending": len(jobs), "would_submit": 0,
                   "would_fail": 0, "plan": []}
        for job in jobs:
            posted = _parse_ts(job.get("posted_at"))
            if posted and datetime.now() - posted > timedelta(
                    minutes=SUBMIT_WINDOW_MINUTES):
                summary["would_fail"] += 1
                summary["plan"].append((job["job_id"], "EXPIRED"))
                print("DRY-RUN submit: %s EXPIRED (posted %s)"
                      % (job["job_id"], job.get("posted_at")))
                continue
            entry = find_queue_entry(home, job.get("clip_id"))
            campaign = campaigns.get(job.get("campaign_id") or "")
            if not entry or not campaign:
                summary["would_fail"] += 1
                summary["plan"].append((job["job_id"],
                                        "NO ENTRY/CAMPAIGN TO RE-GATE"))
                print("DRY-RUN submit: %s would FAIL (no queue entry or "
                      "campaign to re-gate)" % job["job_id"])
                continue
            verdict = gate_clip(_resolve_clip_paths(home, entry), campaign)
            if not verdict["ok"]:
                summary["would_fail"] += 1
                summary["plan"].append((job["job_id"], "GATE BLOCKED"))
                print("DRY-RUN submit: %s would FAIL gate: %s"
                      % (job["job_id"], verdict["block_reason"]))
                continue
            summary["would_submit"] += 1
            summary["plan"].append((job["job_id"], "WOULD SUBMIT"))
            print("DRY-RUN submit: %s WOULD submit %s to campaign %s"
                  % (job["job_id"], job.get("clip_url"),
                     job.get("campaign_id")))
        log(home, "submit dry-run: %d pending, %d would submit, %d fail"
            % (summary["pending"], summary["would_submit"],
               summary["would_fail"]))
        return summary
    ensure_session(home)
    jobs = _pending_jobs(home)
    summary = {"pending": len(jobs), "submitted": 0, "failed": 0,
               "skipped": 0, "results": []}
    if not jobs:
        log(home, "submit: no pending jobs")
        return summary
    pw = browser = context = None
    try:
        pw, browser, context = _launch(home, base)
        page = context.new_page()
        for job in jobs:
            job_id = job.get("job_id")
            clip_url = job.get("clip_url") or ""
            campaign_id = job.get("campaign_id") or ""
            result = {"job_id": job_id, "status": "failed", "reason": ""}
            try:
                posted = _parse_ts(job.get("posted_at"))
                if posted and datetime.now() - posted > timedelta(
                        minutes=SUBMIT_WINDOW_MINUTES):
                    raise RuntimeError(
                        "expired: submit window (30 min from post) passed")
                if job.get("status") != "pending":
                    summary["skipped"] += 1
                    log(home, "submit %s: skipped (status %s)"
                        % (job_id, job.get("status")))
                    continue
                entry = find_queue_entry(home, job.get("clip_id"))
                campaign = campaigns.get(campaign_id)
                if not entry:
                    raise RuntimeError(
                        "no queue entry for clip %s; cannot re-gate"
                        % job.get("clip_id"))
                if not campaign:
                    raise RuntimeError(
                        "campaign %s not in campaigns.json; cannot re-gate"
                        % campaign_id)
                verdict = gate_clip(_resolve_clip_paths(home, entry),
                                    campaign)
                if not verdict["ok"]:
                    raise RuntimeError("gate BLOCKED: %s"
                                       % verdict["block_reason"])
                log(home, "submit %s: gate PASS, window OK"
                    % job_id)
                # Anti-double-submit: already on the dashboard?
                page.goto(dashboard_url(base), timeout=30000)
                rows = _scrape_dashboard(page)
                existing = _find_row(rows, clip_url)
                if existing and existing.get("submission_id"):
                    sid = existing["submission_id"]
                    if mark_submitted(home, job_id, sid):
                        result["status"] = "submitted"
                        result["submission_id"] = sid
                        result["reason"] = ("already on dashboard; "
                                            "marked submitted, not re-filed")
                        summary["submitted"] += 1
                        log(home, "submit %s: already on dashboard (%s); "
                            "marked submitted, NOT re-filed" % (job_id, sid))
                    else:
                        raise RuntimeError(
                            "dashboard already shows this clip but "
                            "mark-submitted failed; left pending")
                    summary["results"].append(result)
                    continue
                # Fill the submit form on the campaign page.
                page.goto(campaign_url(campaign_id, base), timeout=30000)
                field = _first_visible(page, SELECTORS["clip_url_input"])
                if field is None:
                    raise RuntimeError("clip URL field not found on %s"
                                       % campaign_url(campaign_id, base))
                field.fill(clip_url)
                btn = _first_visible(page, SELECTORS["submit_button"])
                if btn is None:
                    raise RuntimeError("submit button not found on %s"
                                       % campaign_url(campaign_id, base))
                btn.click(timeout=10000)
                conf = _first_visible(page,
                                      SELECTORS["submit_confirmation"])
                if conf is None:
                    raise RuntimeError(
                        "no submit confirmation shown after filing")
                # Verify on the dashboard: Pending WITH a submission ID.
                page.goto(dashboard_url(base), timeout=30000)
                rows = _scrape_dashboard(page)
                row = _find_row(rows, clip_url)
                if not row or not row.get("submission_id"):
                    raise RuntimeError(
                        "submitted on-page but dashboard shows no row "
                        "with a submission ID for %s" % clip_url)
                sid = row["submission_id"]
                if mark_submitted(home, job_id, sid):
                    result["status"] = "submitted"
                    result["submission_id"] = sid
                    result["reason"] = "dashboard Pending, id %s" % sid
                    summary["submitted"] += 1
                    log(home, "submit %s: SUBMITTED (dashboard id %s)"
                        % (job_id, sid))
                else:
                    raise RuntimeError(
                        "dashboard shows submission %s but mark-submitted "
                        "failed; left for next run (dashboard pre-check "
                        "will catch it)" % sid)
            except Exception as e:
                result["reason"] = str(e)[:300]
                summary["failed"] += 1
                log(home, "submit %s: FAILED: %s" % (job_id, result["reason"]))
                mark_failed(home, job_id, result["reason"])
            summary["results"].append(result)
    finally:
        if context is not None:
            context.close()
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()
    return summary


# --------------------------------------------------------------- earnings


def dump_earnings(home=None, base=None, dry_run=False):
    """Scrape the submissions dashboard into earnings_dump.json.

    Writes nothing if the dashboard is unreachable or unreadable.
    The caller then runs `earnings.py --update`. Dry-run prints the
    plan and writes nothing / opens no browser.
    """
    home = _home(home)
    base = base_url(home, base)
    require_enabled(home)
    if dry_run:
        print("DRY-RUN earnings: WOULD open %s and scrape every "
              "submission row into %s (then run earnings.py --update)"
              % (dashboard_url(base), earnings_dump_path(home)))
        log(home, "earnings dry-run: plan printed, nothing written")
        return {"dry_run": True, "submissions": 0}
    ensure_session(home)
    pw = browser = context = None
    try:
        pw, browser, context = _launch(home, base)
        page = context.new_page()
        page.goto(dashboard_url(base), timeout=30000)
        rows = _scrape_dashboard(page)
    finally:
        if context is not None:
            context.close()
        if browser is not None:
            browser.close()
        if pw is not None:
            pw.stop()
    dump = {"dumped_at": _now(), "submissions": rows}
    _atomic_write_json(earnings_dump_path(home), dump)
    log(home, "earnings: dumped %d submissions to %s"
        % (len(rows), earnings_dump_path(home)))
    return {"submissions": len(rows), "dumped_at": dump["dumped_at"]}


# -------------------------------------------------------------------- CLI


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="clipsdaily.contentrewards",
        description="%s Content Rewards browser automation (opt-in; "
                    "fails closed). See docs/CONTENTREWARDS_AUTO.md."
                    % BRAND_NAME)
    ap.add_argument("--home", default=None,
                    help="runtime home (default: $CLIPSDAILY_HOME or cwd)")
    ap.add_argument("--base-url", default=None,
                    help="Content Rewards base URL (default: "
                         "https://contentrewards.com; env "
                         "CLIPFORGE_CONTENTREWARDS_BASE_URL also works)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan only: parse jobs, run gates, print what "
                         "WOULD happen; touch no remote site, write nothing")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth", help="guided headed login; saves session only")
    sub.add_parser("join", help="join requested campaigns (badge-verified)")
    sub.add_parser("submit", help="submit pending outbox jobs")
    sub.add_parser("earnings-dump",
                   help="scrape dashboard to earnings_dump.json")
    args = ap.parse_args(argv)
    home = _home(args.home)
    try:
        if args.cmd == "auth":
            state = login_headed(home, base=args.base_url)
            print("session saved: %s" % state if state else "auth aborted")
            return 0 if state else 1
        if args.cmd == "join":
            res = join_campaigns(home, base=args.base_url,
                                 dry_run=args.dry_run)
            print(json.dumps(res, indent=2))
            return 0
        if args.cmd == "submit":
            res = submit_pending(home, base=args.base_url,
                                 dry_run=args.dry_run)
            print(json.dumps(res, indent=2))
            return 0 if res.get("failed", 0) == 0 else 1
        if args.cmd == "earnings-dump":
            res = dump_earnings(home, base=args.base_url,
                                dry_run=args.dry_run)
            print(json.dumps(res, indent=2))
            return 0
    except AutomationDisabled as e:
        print("REFUSED: %s" % e, file=sys.stderr)
        log(home, "refused: %s" % e)
        return 2
    except SessionMissing as e:
        print("REFUSED: %s" % e, file=sys.stderr)
        log(home, "refused: %s" % e)
        return 2
    except DashboardError as e:
        print("FAILED: %s (nothing written)" % e, file=sys.stderr)
        log(home, "earnings FAILED: %s (nothing written)" % e)
        return 1
    except Exception as e:
        print("FAILED: %s" % e, file=sys.stderr)
        log(home, "FAILED: %s" % e)
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
