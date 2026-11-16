"""Auto-submit outbox: turns posted campaign clips into submit jobs
for the parent VM's browser submitter. This module NEVER submits
anything itself — it only writes job files. The parent cron (every
15 min) picks up pending jobs, submits them in the cloud browser
(Content Rewards submit flow), verifies the dashboard shows Pending
with a submission ID, and marks the job submitted via --mark-submitted.

Job lifecycle: pending -> submitted | failed | expired
  - A job is written only for a clip that (1) belongs to a campaign,
    (2) has a live URL on that platform, (3) passes the eligibility
    gate again at write time (window + caption re-verified from the
    entry; framing re-verified on the clip file).
  - A job is only complete when the dashboard shows it Pending WITH a
    submission ID; otherwise it stays pending for retry.
  - Jobs older than 30 minutes past posted_at are marked expired —
    Content Rewards only accepts submissions within 30 min of posting,
    so an expired job must never be submitted.
  - Idempotency: write_job returns the existing job when one already
    exists for the same clip+platform. A submitted job is never
    rewritten or resubmitted. --scan never writes a duplicate.

Job schema (submit-outbox/<clip_id>-<platform>.json):
  {"job_id", "clip_id", "platform", "clip_url", "campaign_id",
   "campaign_title", "posted_at", "created_at", "status",
   "attempts", "submission_id", "submitted_at", "notes", "history": []}

Usage:
  python3 auto_submit.py --scan [--campaigns campaigns.json]
      scan queue.json + campaign_queue.json (+ ig-outbox meta) for
      newly posted campaign clips and write pending jobs.
  python3 auto_submit.py --list-pending   # JSON list for the parent cron
  python3 auto_submit.py --write-job <entry.json> <platform>
  python3 auto_submit.py --mark-submitted <job_id> --submission-id <id>
  python3 auto_submit.py --mark-failed <job_id> --reason <text>
"""
import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path


from .campaigns import load_campaigns  # noqa: E402
from .eligibility_gate import gate_clip  # noqa: E402

from .paths import runtime_home
HERE = runtime_home()
QUEUE_FILE = HERE / "queue" / "queue.json"
CAMPAIGN_QUEUE_FILE = HERE / "campaign_queue.json"
OUTBOX_DIR = HERE / "submit-outbox"
IG_OUTBOX = HERE / "ig-outbox"
SUBMIT_WINDOW_MINUTES = 30


def log(msg):
    # Logs go to stderr: stdout stays pure JSON (--list-pending,
    # --scan, and the final result dict are machine-read by the parent
    # cron). Human-readable logs still show in the terminal.
    print("[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg),
          flush=True, file=sys.stderr)


def _parse_ts(s):
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(str(s), fmt)
        except Exception:
            continue
    return None


def posted_at_for(entry, platform):
    """When this platform's URL first appeared (history), else None."""
    key = {"youtube": "yt_url", "tiktok": "tt_url"}.get(platform)
    if key:
        for h in entry.get("history") or []:
            url = h.get(key)
            if url and url != "FAILED":
                at = _parse_ts(h.get("at"))
                if at:
                    return at
    return None


def job_path(clip_id, platform):
    return OUTBOX_DIR / ("%s-%s.json" % (clip_id, platform))


def load_job(clip_id, platform):
    p = job_path(clip_id, platform)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def save_job(job):
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    tmp = job_path(job["clip_id"], job["platform"]).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, indent=2))
    tmp.replace(job_path(job["clip_id"], job["platform"]))
    return job


def write_job(entry, platform, clip_url, posted_at, campaigns):
    """Write a submit job if none exists. Returns (job, created_bool)."""
    clip_id = entry["id"]
    existing = load_job(clip_id, platform)
    if existing:
        if existing.get("status") == "submitted":
            return existing, False
        # A pending/failed job stays as-is (retries use the same job).
        return existing, False
    campaign = campaigns.get(entry.get("campaign_id") or "")
    if not campaign:
        return None, False
    # Re-gate at write time: window + caption from the entry, framing
    # from the clip file. A gate failure means NO job is written.
    verdict = gate_clip(entry, campaign)
    if not verdict["ok"]:
        log("%s/%s: GATE BLOCKED, no submit job: %s"
            % (clip_id, platform, verdict["block_reason"]))
        return None, False
    now = datetime.now()
    posted = posted_at or now
    job = {
        "job_id": "%s-%s" % (clip_id, platform),
        "clip_id": clip_id,
        "platform": platform,
        "clip_url": clip_url,
        "campaign_id": campaign["id"],
        "campaign_title": campaign.get("title"),
        "posted_at": posted.strftime("%Y-%m-%dT%H:%M:%S"),
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "pending",
        "attempts": 0,
        "submission_id": None,
        "submitted_at": None,
        "notes": "",
        "history": [],
    }
    save_job(job)
    log("%s/%s: submit job written (%s)" % (clip_id, platform, clip_url))
    return job, True


def expire_stale_jobs(jobs, now=None):
    """Mark pending jobs past the 30-min submit window as expired."""
    now = now or datetime.now()
    changed = 0
    for job in jobs:
        if job.get("status") != "pending":
            continue
        posted = _parse_ts(job.get("posted_at"))
        if posted and now - posted > timedelta(minutes=SUBMIT_WINDOW_MINUTES):
            job["status"] = "expired"
            job["notes"] = ("submit window (30 min from post) passed at %s"
                            % (posted + timedelta(
                                minutes=SUBMIT_WINDOW_MINUTES)
                               ).strftime("%Y-%m-%dT%H:%M:%S"))
            job["history"].append({"at": now.strftime("%Y-%m-%dT%H:%M:%S"),
                                   "event": "expired"})
            save_job(job)
            changed += 1
            log("%s: EXPIRED (posted %s)" % (job["job_id"], job["posted_at"]))
    return changed


def list_jobs():
    jobs = []
    if not OUTBOX_DIR.exists():
        return jobs
    for p in sorted(OUTBOX_DIR.glob("*.json")):
        try:
            jobs.append(json.loads(p.read_text()))
        except Exception:
            continue
    return jobs


def scan(campaigns):
    """Find posted campaign clips without submit jobs and write them."""
    written, skipped = [], []
    entries = []
    for f in (QUEUE_FILE, CAMPAIGN_QUEUE_FILE):
        if f.exists():
            try:
                entries.extend(json.loads(f.read_text()))
            except Exception as e:
                log("cannot read %s: %s" % (f, e))
    for entry in entries:
        cid = entry.get("campaign_id")
        if not cid or cid not in campaigns:
            continue
        if entry.get("status") == "blocked":
            skipped.append((entry["id"], "blocked by gate"))
            continue
        for platform, url_key in (("youtube", "yt_url"),
                                  ("tiktok", "tt_url")):
            url = entry.get(url_key)
            if not url or url == "FAILED":
                continue
            if load_job(entry["id"], platform):
                continue
            posted = posted_at_for(entry, platform)
            job, created = write_job(entry, platform, url, posted, campaigns)
            if created:
                written.append(job["job_id"])
    # Instagram: URL lives in ig-outbox meta (parent posts the Reel).
    if IG_OUTBOX.exists():
        for meta_path in IG_OUTBOX.glob("*/meta.json"):
            try:
                meta = json.loads(meta_path.read_text())
            except Exception:
                continue
            if meta.get("status") != "posted":
                continue
            ig_url = meta.get("instagram_url")
            clip_id = meta.get("clip_id")
            if not ig_url or not clip_id:
                continue
            if load_job(clip_id, "instagram"):
                continue
            entry = next((e for e in entries if e["id"] == clip_id), None)
            if not entry or not entry.get("campaign_id"):
                continue
            posted = _parse_ts(meta.get("posted_at"))
            job, created = write_job(entry, "instagram", ig_url, posted,
                                     campaigns)
            if created:
                written.append(job["job_id"])
    expired = expire_stale_jobs(list_jobs())
    return {"written": written, "skipped": skipped, "expired": expired}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--list-pending", action="store_true")
    ap.add_argument("--write-job", nargs=2, metavar=("ENTRY_JSON", "PLATFORM"))
    ap.add_argument("--mark-submitted", metavar="JOB_ID")
    ap.add_argument("--mark-failed", metavar="JOB_ID")
    ap.add_argument("--submission-id")
    ap.add_argument("--reason")
    ap.add_argument("--campaigns", default=str(HERE / "campaigns.json"))
    args = ap.parse_args()
    campaigns = load_campaigns(args.campaigns)
    if args.scan:
        res = scan(campaigns)
        print(json.dumps(res, indent=2))
        return 0
    if args.list_pending:
        expire_stale_jobs(list_jobs())
        pending = [j for j in list_jobs() if j.get("status") == "pending"]
        print(json.dumps(pending, indent=2))
        return 0
    if args.write_job:
        entry = json.loads(Path(args.write_job[0]).read_text())
        platform = args.write_job[1]
        url = {"youtube": entry.get("yt_url"),
               "tiktok": entry.get("tt_url")}.get(platform)
        if not url:
            print(json.dumps({"ok": False, "error": "no URL for platform"}))
            return 1
        job, created = write_job(entry, platform, url,
                                 posted_at_for(entry, platform), campaigns)
        print(json.dumps({"ok": bool(job), "created": created,
                          "job": job}, indent=2))
        return 0 if job else 1
    if args.mark_submitted:
        job = None
        for p in OUTBOX_DIR.glob("*.json"):
            try:
                j = json.loads(p.read_text())
            except Exception:
                continue
            if j.get("job_id") == args.mark_submitted:
                job = j
                break
        if not job:
            print(json.dumps({"ok": False, "error": "job not found"}))
            return 1
        if not args.submission_id:
            print(json.dumps({"ok": False,
                              "error": "--submission-id required"}))
            return 1
        job["status"] = "submitted"
        job["submission_id"] = args.submission_id
        job["submitted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        job["attempts"] = job.get("attempts", 0) + 1
        job["history"].append({"at": job["submitted_at"],
                               "event": "submitted",
                               "submission_id": args.submission_id})
        save_job(job)
        print(json.dumps({"ok": True, "job": job}, indent=2))
        return 0
    if args.mark_failed:
        job = None
        for p in OUTBOX_DIR.glob("*.json"):
            try:
                j = json.loads(p.read_text())
            except Exception:
                continue
            if j.get("job_id") == args.mark_failed:
                job = j
                break
        if not job:
            print(json.dumps({"ok": False, "error": "job not found"}))
            return 1
        job["status"] = "failed"
        job["attempts"] = job.get("attempts", 0) + 1
        job["notes"] = args.reason or ""
        job["history"].append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                               "event": "failed",
                               "reason": args.reason or ""})
        save_job(job)
        print(json.dumps({"ok": True, "job": job}, indent=2))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
