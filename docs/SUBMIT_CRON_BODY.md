# Clipsdaily auto-submit cron — install instructions for the parent

## Cron job (every 15 minutes, America/New_York)
Run `bash ~/workspace/clipsdaily-build/submit_cron.sh`. It scans indra
for newly posted campaign clips (re-gating each one), expires stale
jobs, and prints pending submit jobs as JSON.

## What the cron agent does each run
1. Run submit_cron.sh. Read the pending jobs list.
2. For EACH pending job (job_id, clip_url, platform, campaign_id):
   - Check posted_at: if more than 30 minutes have passed since
     posted_at, do NOT submit. Mark it failed with reason "expired"
     via submit_mark.sh (the scan usually expires it already).
   - Open the campaign page (job has no campaign URL — use
     https://contentrewards.com/c/campaigns/<campaign_id>) in the cloud
     browser as Clips Daily, paste the clip URL into the submit form,
     complete the 3 form checks, and confirm it shows "Clip submitted".
   - Verify on the submissions dashboard that the clip shows Pending
     WITH a submission ID. Only then run:
     `bash ~/workspace/clipsdaily-build/submit_mark.sh <job_id> submitted <submission_id>`
   - If the submit fails, the page errors, or no submission ID appears,
     run: `bash ~/workspace/clipsdaily-build/submit_mark.sh <job_id> failed "<reason>"`
     and leave the job pending for the next run (it retries until the
     30-min window passes, then expires).
3. Never submit the same clip+platform twice: a job with status
   "submitted" is done. Never submit a job whose status is "expired".
4. Silent when there is nothing pending (no message needed).

## Campaign watcher cron (daily, America/New_York)
Run on indra: `python3 /home/abel/clipsdaily/campaign_watcher.py --check`
via /tmp/indra.sh as abel. It discovers campaigns, evaluates join
rules, and writes join_requests.json. The parent then runs ONE browser
task per requested join: open the campaign URL, click Join Campaign,
verify the green Joined badge, and append to join_results.json on
indra ({"campaign_id": ..., "status": "joined"|"failed",
"reason": ..., "at": ...}). The watcher reconciles it next run.

## Earnings dump cron (daily, America/New_York)
Run a browser task on the Content Rewards submissions dashboard as
Clips Daily, dump the submissions table to earnings_dump.json on indra
(see earnings_dump_spec.md), then run on indra:
`python3 /home/abel/clipsdaily/earnings.py --update`
and report the one-line summary.
