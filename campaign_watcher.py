"""Campaign watcher: discovers new clipping campaigns, evaluates them
against the join rules, and queues join requests for the parent VM.

READ-ONLY against the sites by design. Content Rewards has no public
API; the discover page (https://contentrewards.com/c/discover) is a
Next.js app whose campaign list is embedded in the HTML as RSC flight
payload chunks (self.__next_f.push([1,"..."])). This module fetches
that page anonymously, unescapes the chunks, and parses the embedded
{"campaign": {...}} records — verified live Nov 16, 2026: the page
embeds id, title, brand, description (footage window text),
ratePer1kLabel, budgetSpent/Total/availableRaw, platforms,
requiresApplication, isVerified, launchedAtMs, submissionCountRaw.
Detail pages (https://contentrewards.com/c/campaigns/<uuid>) embed a
dehydrated query whose data object adds status, payouts[] per
platform {rateCents, minPayoutCents, maxPayoutCents}, budgetCents,
metrics, and referenceMaterials.

Joining is NOT done here: it needs the signed-in Whop session, which
only the parent VM's cloud browser has. The watcher writes
join_requests.json; the parent's cron runs a browser task that clicks
Join on each requested campaign, verifies the Joined badge, and writes
join_results.json. This module reconciles join_results.json on the
next run (requested -> joined / failed).

Vyro has no public campaign data (campaigns live behind login), so
Vyro is consumed from a parent browser dump (vyro_dump.json) when
present; otherwise it is skipped with a reason. Dump format:
  {"campaigns": [{"id": ..., "title": ..., "rate_per_1k": 1.0,
    "budget_available_cents": 500000, "platforms": [...],
    "requires_application": false, "status": "active",
    "description": "...", "url": "..."}]}

Usage:
  python3 campaign_watcher.py --check      # full run, writes files
  python3 campaign_watcher.py --dry-run    # fetch + evaluate, no writes
  python3 campaign_watcher.py --discover-only  # list only, no detail fetch

Exit 0 even when nothing is joinable. Never joins, never posts.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaigns import (CAMPAIGNS_FILE, JOIN_REQUESTS_FILE,  # noqa: E402
                       JOIN_RESULTS_FILE, evaluate_join_rules,
                       enrich_from_detail, load_campaigns, load_watchlist,
                       match_streamer, normalize_discover_record,
                       save_campaigns)

HERE = Path(__file__).resolve().parent
LOG_FILE = HERE / "campaigns.log"
VYRO_DUMP = HERE / "vyro_dump.json"
DISCOVER_URL = "https://contentrewards.com/c/discover"
DETAIL_URL = "https://contentrewards.com/c/campaigns/%s"
UA = {"User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")}

_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_CAMPAIGN_RE = re.compile(r'\{"campaign":')


def log(msg):
    # Logs go to stderr: stdout stays pure JSON for machine consumers.
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True, file=sys.stderr)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def unescape_flight(html):
    """Join the RSC flight-payload chunks into one text blob."""
    parts = []
    for m in _CHUNK_RE.finditer(html):
        try:
            parts.append(json.loads('"' + m.group(1) + '"'))
        except Exception:
            continue
    return "".join(parts)


def extract_campaign_objects(text):
    """All {"campaign": {...}} records in flight text, parsed as JSON."""
    dec = json.JSONDecoder()
    out = []
    for m in _CAMPAIGN_RE.finditer(text):
        start = m.start()  # the '{' opening the {"campaign": ...} record
        try:
            obj, _ = dec.raw_decode(text[start:])
        except Exception:
            continue
        rec = obj.get("campaign") if isinstance(obj, dict) else None
        if isinstance(rec, dict) and rec.get("id"):
            out.append(rec)
    return out


def extract_detail_data(text, campaign_id):
    """Dehydrated query data object for one campaign id, or None."""
    dec = json.JSONDecoder()
    for m in re.finditer(r'"state":\{"data":\{', text):
        start = m.end() - 1
        try:
            obj, _ = dec.raw_decode(text[start:])
        except Exception:
            continue
        if isinstance(obj, dict) and obj.get("id") == campaign_id:
            return obj
    return None


def fetch_discover():
    html = fetch(DISCOVER_URL)
    text = unescape_flight(html)
    if not text:
        # Fallback: the records may be inline JSON in the raw HTML.
        text = html
    recs = extract_campaign_objects(text)
    # Deduplicate by id (the same record can appear twice in flight data).
    seen, uniq = set(), []
    for r in recs:
        if r["id"] not in seen:
            seen.add(r["id"])
            uniq.append(r)
    return uniq


def fetch_detail(campaign_id):
    html = fetch(DETAIL_URL % campaign_id)
    text = unescape_flight(html)
    if not text:
        text = html
    return extract_detail_data(text, campaign_id)


def run(dry_run=False, discover_only=False):
    watchlist = load_watchlist()
    log("watcher start (watchlist: %s)" % ", ".join(watchlist))
    existing = load_campaigns()
    try:
        raw_records = fetch_discover()
    except Exception as e:
        log("discover fetch FAILED: %s" % e)
        return {"ok": False, "error": str(e)}
    log("discover: %d campaign records parsed" % len(raw_records))
    decisions = []
    join_requests = []
    if not dry_run:
        try:
            join_requests = json.loads(JOIN_REQUESTS_FILE.read_text())
        except Exception:
            join_requests = []
    requested_ids = {j.get("campaign_id") for j in join_requests}
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for raw in raw_records:
        rec = normalize_discover_record(raw)
        rec["streamer"] = match_streamer(rec["title"], rec["window_text"],
                                         watchlist)
        rec["discovered_at"] = rec.get("discovered_at") or now
        rec["updated_at"] = now
        old = existing.get(rec["id"])
        if old:
            # Preserve workflow state + human-filled fields.
            for k in ("state", "state_reason", "vod_id", "vod_date",
                      "stream_date_text", "required_mentions",
                      "required_hashtag", "caption_must_name",
                      "exclude_ranges", "moments", "hook_by_destination",
                      "local_video", "local_video_offset_s", "discovered_at"):
                if old.get(k) is not None:
                    rec[k] = old[k]
            if old.get("state") in ("joined", "ended"):
                decisions.append((rec["id"], old["state"],
                                  "already %s" % old["state"]))
                existing[rec["id"]] = rec
                continue
        if not discover_only and rec.get("id"):
            # Detail fetch is expensive (one HTTP round trip + 2s
            # politeness delay), so it runs ONLY for records that pass
            # the discover screen. A join candidate whose detail fetch
            # fails is downgraded to needs_review: unverified payouts
            # must not auto-join.
            decision0, reason0 = evaluate_join_rules(rec, watchlist)
            if decision0 == "join":
                try:
                    detail = fetch_detail(rec["id"])
                    if detail:
                        enrich_from_detail(rec, detail)
                        rec["raw_detail"] = detail
                    else:
                        raise RuntimeError("no detail data parsed")
                    time.sleep(2)  # polite: one detail fetch per 2s
                except Exception as e:
                    log("%s: detail fetch failed: %s" % (rec["id"], e))
                    decision0, reason0 = (
                        "needs_review",
                        "detail fetch failed, payouts unverified: %s" % e)
                decision, reason = evaluate_join_rules(rec, watchlist)
                # Re-evaluation after enrichment must not upgrade a
                # downgrade made for an unverifiable detail fetch.
                if "detail fetch failed" in reason0:
                    decision, reason = decision0, reason0
            else:
                decision, reason = decision0, reason0
        else:
            decision, reason = evaluate_join_rules(rec, watchlist)
        if decision == "join":
            rec["state"] = "join_requested"
            rec["state_reason"] = reason
            if rec["id"] not in requested_ids:
                join_requests.append({
                    "campaign_id": rec["id"], "source": "content_rewards",
                    "title": rec["title"], "url": rec["url"],
                    "rate_per_1k": rec["rate_per_1k"],
                    "window_text": rec["window_text"],
                    "window_start_s": rec["window_start_s"],
                    "window_end_s": rec["window_end_s"],
                    "streamer": rec["streamer"],
                    "requested_at": now, "status": "requested",
                })
                requested_ids.add(rec["id"])
        elif decision == "needs_review":
            rec["state"] = "needs_review"
            rec["state_reason"] = reason
        else:
            rec["state"] = "skipped"
            rec["state_reason"] = reason
        decisions.append((rec["id"], rec["state"], reason))
        existing[rec["id"]] = rec
    # Reconcile join results reported by the parent browser task.
    if JOIN_RESULTS_FILE.exists() and not dry_run:
        try:
            results = json.loads(JOIN_RESULTS_FILE.read_text())
            for r in results:
                cid = r.get("campaign_id")
                if cid in existing:
                    if r.get("status") == "joined":
                        existing[cid]["state"] = "joined"
                        existing[cid]["state_reason"] = (
                            "joined %s" % r.get("at", ""))
                    elif r.get("status") == "failed":
                        existing[cid]["state"] = "needs_review"
                        existing[cid]["state_reason"] = (
                            "join failed: %s" % r.get("reason", ""))
        except Exception as e:
            log("join_results reconcile failed: %s" % e)
    # Vyro: only from a parent browser dump (no public data to fetch).
    if VYRO_DUMP.exists():
        try:
            dump = json.loads(VYRO_DUMP.read_text())
            for d in dump.get("campaigns", []):
                log("vyro dump entry %s (manual review path)" % d.get("id"))
        except Exception as e:
            log("vyro dump unreadable: %s" % e)
    else:
        log("vyro: no dump file, skipped (campaigns behind login)")
    joins = [d for d in decisions if d[1] == "join_requested"]
    reviews = [d for d in decisions if d[1] == "needs_review"]
    log("decisions: %d join_requested, %d needs_review, %d skipped/known"
        % (len(joins), len(reviews),
           len(decisions) - len(joins) - len(reviews)))
    for cid, state, reason in decisions:
        if state in ("join_requested", "needs_review"):
            log("  %s -> %s: %s" % (cid, state, reason))
    if not dry_run:
        save_campaigns(existing)
        tmp = JOIN_REQUESTS_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(join_requests, indent=2))
        tmp.replace(JOIN_REQUESTS_FILE)
        log("wrote %s (%d campaigns), %s (%d requests)"
            % (CAMPAIGNS_FILE, len(existing),
               JOIN_REQUESTS_FILE, len(join_requests)))
    return {"ok": True, "parsed": len(raw_records), "decisions": decisions,
            "join_requests": len(join_requests)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="full run (default)")
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch + evaluate, write nothing")
    ap.add_argument("--discover-only", action="store_true",
                    help="list only, no detail fetch")
    args = ap.parse_args()
    res = run(dry_run=args.dry_run, discover_only=args.discover_only)
    print(json.dumps({k: v for k, v in res.items()
                      if k != "decisions"}, indent=2))
