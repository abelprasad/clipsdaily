# Enforce strict eligibility gate

## Status

Accepted — 2026-11-15

## Context

Content Rewards campaigns license specific footage for a specific window; submitting out-of-window footage, or a caption missing a required mention, gets the clip rejected. Worse, Content Rewards' rule is "one strike and you're out": botting views, AI-generated content, or gaming the system removes you from every Reach campaign permanently. The pipeline cuts and posts automatically, so a bad clip could be submitted before a human sees it.

## Decision

Every campaign clip passes `eligibility_gate.py` before posting or submitting. Three checks, any fail or unverifiable result means BLOCKED, exit 2: (a) window — the clip's full VOD range sits inside the campaign window, including exclude ranges; (b) caption — every posted caption has all required mentions plus the required hashtag plus the destination; (c) full-frame — frames at t=5/15/25s are checked for gradient energy in the top, center, and bottom bands (pass only if top < 0.4, bottom < 1.0, center > 2.0). The gate is never bypassed for speed.

## Consequences

- Borderline clips pause and ask a human instead of auto-posting.
- The gate is calibrated against real clips and re-validated against both ground truths if the cutter's filter chain changes: new full-frame clips pass, legacy center-crop clips fail framing, an out-of-window clip fails the window check, a bad-caption clip fails the caption check.
- An early version of the framing check false-passed a center-crop clip on a top-vs-center ratio; it was replaced with absolute band energies.
- Legacy Speed clips posted before the gate existed are grandfathered (already posted and submitted, no action); they are NOT seeded into `campaign_queue.json`, which would duplicate submits.
- The gate is what makes the full automation safe to run unattended.
