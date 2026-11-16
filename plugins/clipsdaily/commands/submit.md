---
description: Scan the queue for submittable campaign clips, list pending submit jobs, or mark jobs submitted/failed
---

The auto-submit outbox: `clipsdaily submit scan` finds campaign clips that are posted, gated, and inside the 30-minute window, and writes pending jobs to `submit-outbox/`. The operator (or the 15-min cron) submits each job in the browser, then marks it.

## Scan for submittable clips

```bash
clipsdaily submit scan
```

## List pending jobs (JSON)

```bash
clipsdaily submit list-pending
```

## Mark a job submitted (needs the dashboard submission ID)

```bash
clipsdaily submit mark-submitted <job-id> --submission-id <id>
```

## Mark a job failed

```bash
clipsdaily submit mark-failed <job-id> --reason "<why>"
```

Jobs expire 30 minutes after `posted_at`. A job is complete ONLY when the Content Rewards dashboard shows Pending WITH a submission ID — never mark submitted on a "looks posted" guess.

## Rules

- **Audit before submitting:** watch/read the actual clip, check captions, credit, titles, and that the post is really live — before any link goes to a campaign.
- **Never submit without the gate passing, never submit twice, never submit past 30 minutes.**
- If a job expired, it stays failed. Do not re-scan it into a new job — the 30-minute window is a campaign rule, not a retry timer.
