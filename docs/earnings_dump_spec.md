# Earnings + Vyro dump specs (parent browser tasks)

## earnings_dump.json — Content Rewards submissions dashboard
The parent's daily browser task opens the submissions dashboard as
Clips Daily (contentrewards.com — the submissions page the Nov 15
session used; URL is the "Submissions" page in the creator dashboard)
and records every submission row, then writes this file to indra at
/home/abel/clipsdaily/earnings_dump.json (via indra.sh + sudo tee):
```json
{"dumped_at": "2026-11-16T07:00:00",
 "submissions": [
   {"submission_id": "f9ecabc2-8f5b-44ef-8ad3-341e0865ed14",
    "clip_url": "https://youtube.com/shorts/dsOVbm03FoI",
    "platform": "youtube",
    "campaign_id": "afeca1a0-f44c-46ad-8194-09d62b56589e",
    "campaign_title": "$$8,000 Expedia x IShowSpeed Campaign",
    "status": "Pending",
    "views": 0,
    "payout_cents": 0,
    "submitted_at": "2026-11-15T14:26:00"}
 ]}
```
- status is the dashboard text: Pending / Awaiting review / Approved /
  Rejected. views and payout_cents are the dashboard numbers (0 when
  the dashboard shows none yet). submission_id is the dashboard's ID
  for the submission (match by clip_url when the ID is not shown).
- Then run on indra: `/home/abel/.local/bin/clipsdaily earnings --update`
  and report the one-line summary it prints.

## vyro_dump.json — Vyro campaigns (no public data to fetch)
Vyro's campaign list lives behind login, so the watcher cannot fetch
it directly. The parent's daily browser task opens Vyro as Clips Daily,
lists open campaigns, and writes /home/abel/clipsdaily/vyro_dump.json:
```json
{"dumped_at": "2026-11-16T07:00:00",
 "campaigns": [
   {"id": "vyro-...", "title": "...", "rate_per_1k": 2.0,
    "budget_available_cents": 200000, "platforms": ["tiktok"],
    "requires_application": false, "status": "active",
    "description": "full rules text incl. footage window",
    "url": "https://vyro.com/..."}
 ]}
```
The watcher logs each Vyro entry for manual review (Vyro joins stay
manual until a Vyro join flow is proven in the browser).
