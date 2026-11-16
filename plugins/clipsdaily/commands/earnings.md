---
description: Show the clipsdaily earnings summary (one line) or update it from a dashboard dump
---

## Summary

```bash
clipsdaily earnings
clipsdaily earnings --summary
```

Prints one line, e.g.:

```
Clipsdaily earnings 2026-11-15: $0.00 realized (0 approved), $0.00 projected (6 pending), 6 clips, 0 views
```

## Update from a dashboard dump

```bash
clipsdaily earnings --update
```

Reads `earnings_dump.json` (a browser dump of the Content Rewards submissions dashboard — see `docs/earnings_dump_spec.md`), merges per-clip views/status/payout + campaign totals into `earnings.json`, then prints the summary.

## Notes

- Earnings are $0 until a clip is approved AND passes 10,000 views (MVR). Pending clips earn nothing yet.
- Whop payout setup and withdrawals are the maintainer's job by hand — never automate them.
