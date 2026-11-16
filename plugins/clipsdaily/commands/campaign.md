---
description: Watch Content Rewards for new campaigns, or cut clips for a joined campaign
---

## Watch for campaigns

```bash
clipsdaily campaign watch --check
```

Fetches the Content Rewards discover page as anonymous HTML and writes `join_requests.json` for any campaign passing all 7 join rules. Joining is a human step: the operator verifies the Joined badge in the browser and writes `join_results.json`.

```bash
clipsdaily campaign watch --discover-only   # list campaigns, join nothing
clipsdaily campaign watch --dry-run         # parse + report, write nothing
```

## Cut clips for a joined campaign

```bash
clipsdaily campaign cut --campaign <campaign-id> [--max-clips N] [--dry-run]
```

Cuts 30s + TikTok-variant clips (full frame, big hook), builds campaign captions, and runs the eligibility gate. Passed clips go to `campaign_queue.json` — never `queue.json`.

## Rules — read before touching campaigns

- **The eligibility gate is never bypassed.** `eligibility_gate.py` must PASS (window + caption + framing) before any campaign clip posts or submits. Borderline = blocked.
- **Known gap:** the hourly poster does NOT yet prefer `campaign_queue.json`, so campaign cuts sit unposted until the wiring lands (ROADMAP.md item 1). Do not hand-post campaign cuts around the gate.
- **One-strike rule:** one bad submission (wrong footage window, missing mention/hashtag, AI-gamed content) bans the account from every campaign permanently.
- Never pay to join any platform. Never submit a clip twice, or past 30 minutes after posting.
