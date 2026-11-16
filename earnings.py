"""Earnings tracker: turns the parent's submissions-dashboard dump into
per-clip / per-campaign / total earnings, and a one-line daily summary.

Input: earnings_dump.json, written by the parent's scheduled browser
task from the Content Rewards submissions dashboard (signed-in session
required — no public API exposes per-creator submissions). Dump format:
  {"dumped_at": "2026-11-16T07:00:00",
   "submissions": [{"submission_id": "f9ecabc2-...",
     "clip_url": "https://youtube.com/shorts/...",
     "platform": "youtube", "campaign_id": "afeca1a0-...",
     "campaign_title": "$$8,000 Expedia x IShowSpeed Campaign",
     "status": "Pending" | "Approved" | "Rejected",
     "views": 0, "payout_cents": 0, "submitted_at": "..."}]}
Status is normalized: pending/awaiting review -> pending,
approved -> approved, rejected -> rejected. Unknown -> pending.
Payout: the dump's payout_cents when present; otherwise approved clips
are estimated as views/1000 * campaign rate, pending clips count as
projected (not realized) earnings.

Output: earnings.json (full record) + --summary one-liner:
  "Clipsdaily earnings 2026-11-16: $0.00 realized (0 approved),
   $0.00 projected (5 pending), 5 clips, top clip <url> (0 views)"

Usage:
  python3 earnings.py --update [--dump earnings_dump.json]
  python3 earnings.py --summary
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaigns import load_campaigns  # noqa: E402

HERE = Path(__file__).resolve().parent
DUMP_FILE = HERE / "earnings_dump.json"
EARNINGS_FILE = HERE / "earnings.json"


def normalize_status(s):
    s = (s or "").strip().lower()
    if s in ("approved", "approve", "paid"):
        return "approved"
    if s in ("rejected", "reject", "denied"):
        return "rejected"
    return "pending"


def build_earnings(dump, campaigns):
    subs = dump.get("submissions", []) if isinstance(dump, dict) else []
    clips = {}
    per_campaign = {}
    for s in subs:
        sid = s.get("submission_id") or s.get("clip_url")
        if not sid:
            continue
        status = normalize_status(s.get("status"))
        views = int(s.get("views") or 0)
        cid = s.get("campaign_id")
        camp = campaigns.get(cid or "") or {}
        rate = camp.get("rate_per_1k")
        payout = s.get("payout_cents")
        if payout is None:
            if status == "approved" and rate:
                payout = int(views / 1000.0 * rate * 100)
            else:
                payout = 0
        projected = 0
        if status == "pending" and rate:
            projected = int(views / 1000.0 * rate * 100)
        clips[sid] = {
            "submission_id": s.get("submission_id"),
            "clip_url": s.get("clip_url"),
            "platform": s.get("platform"),
            "campaign_id": cid,
            "campaign_title": (s.get("campaign_title")
                               or camp.get("title")),
            "status": status,
            "views": views,
            "payout_cents": int(payout),
            "projected_cents": projected,
            "submitted_at": s.get("submitted_at"),
        }
        agg = per_campaign.setdefault(cid or "unknown", {
            "campaign_id": cid,
            "campaign_title": clips[sid]["campaign_title"],
            "clips": 0, "views": 0, "approved": 0, "pending": 0,
            "rejected": 0, "payout_cents": 0, "projected_cents": 0,
        })
        agg["clips"] += 1
        agg["views"] += views
        agg[status] += 1
        agg["payout_cents"] += int(payout)
        agg["projected_cents"] += projected
    totals = {
        "clips": len(clips),
        "views": sum(c["views"] for c in clips.values()),
        "approved": sum(1 for c in clips.values()
                        if c["status"] == "approved"),
        "pending": sum(1 for c in clips.values()
                       if c["status"] == "pending"),
        "rejected": sum(1 for c in clips.values()
                        if c["status"] == "rejected"),
        "payout_cents": sum(c["payout_cents"] for c in clips.values()),
        "projected_cents": sum(c["projected_cents"]
                               for c in clips.values()),
    }
    top = None
    if clips:
        top = max(clips.values(), key=lambda c: c["views"])
    return {
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "dumped_at": dump.get("dumped_at") if isinstance(dump, dict) else None,
        "clips": clips,
        "campaigns": per_campaign,
        "totals": totals,
        "top_clip": top,
    }


def summary_line(data):
    t = data["totals"]
    date = data["updated_at"][:10]
    top = data.get("top_clip") or {}
    line = ("Clipsdaily earnings %s: $%.2f realized (%d approved), "
            "$%.2f projected (%d pending), %d clips, %d views"
            % (date, t["payout_cents"] / 100.0, t["approved"],
               t["projected_cents"] / 100.0, t["pending"],
               t["clips"], t["views"]))
    if top:
        line += (", top clip %s (%d views)"
                 % (top.get("clip_url"), top.get("views")))
    if t["rejected"]:
        line += " [%d REJECTED — check dashboard]" % t["rejected"]
    return line


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--dump", default=str(DUMP_FILE))
    args = ap.parse_args()
    campaigns = load_campaigns()
    if args.update:
        if not Path(args.dump).exists():
            print(json.dumps({"ok": False,
                              "error": "no earnings dump yet: %s"
                              % args.dump}))
            return 1
        dump = json.loads(Path(args.dump).read_text())
        data = build_earnings(dump, campaigns)
        tmp = EARNINGS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(EARNINGS_FILE)
        print(summary_line(data))
        return 0
    if args.summary:
        if not EARNINGS_FILE.exists():
            print("No earnings data yet — run --update after a dashboard dump.")
            return 1
        data = json.loads(EARNINGS_FILE.read_text())
        print(summary_line(data))
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
