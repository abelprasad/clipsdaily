# Run fully automatic with kill switch

## Status

Accepted — 2026-11-15

## Context

Abel was explicit: "no review i want it to be fully automatic pipeline", "let's make new accounts for these", and "u will have complete control over these accounts btw". A review queue would stall the hourly cadence and put a human in the loop for every clip, which defeats the purpose of an automatic pipeline. At the same time, fully automatic posting to paid campaigns carries real risk: a wrong clip submitted to a campaign can get rejected, and Content Rewards' one-strike rule can end every campaign at once.

## Decision

No review queue. The pipeline auto-posts, with a STOP kill-switch file in the clipsdaily directory (`touch STOP` halts the runner) plus a daily cap of 48 posts. Borderline clips pause and ask a human instead of auto-posting. Campaign clips additionally require the eligibility gate to pass (see `enforce-strict-eligibility-gate.md`).

## Consequences

- The pipeline posts while Abel sleeps; the kill switch is the emergency brake.
- Cleanup is part of the automation, not an afterthought: raw recordings are deleted immediately after cutting, posted clips after 24 hours, unposted clips after 48 hours, and the runner stops new recordings below 50 GB free disk (Abel required the device not to get cluttered).
- Whop payout setup and withdrawals stay human-only (Abel), as do TikTok cookie and YouTube token re-auths.
- Abel's standing permission covers posting without per-post approval; it does not cover joining campaigns, submitting links, or spending money, which stay gated or human.
