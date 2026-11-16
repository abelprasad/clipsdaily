# Security

## Campaign licensing — the one rule that matters most

**Only post content a campaign licenses, or content you have rights to.**

- A clipping campaign (e.g. Content Rewards) licenses **only that campaign's footage, only inside its stated footage window**. Footage from any other stream, video, or post is not licensed — posting it as a campaign clip will be rejected, and gaming the system gets the account removed from **every** campaign permanently.
- The eligibility gate (`eligibility_gate.py`) exists to enforce this: it checks the clip's full VOD range against the campaign window, the required mentions/hashtag/destination in the caption, and the framing. **Never bypass the gate for speed. Borderline = blocked.**
- **One-strike rule:** one bad submission (wrong footage window, missing mention/hashtag, manipulated views, AI-generated content) bans the account from every Reach campaign permanently. There is no appeal path in the product — the gate is the appeal.
- Outside campaigns, reposted stream clips are not original content. TikTok requires original content and YouTube has a reused-content rule; both can demonetize or take down clips even with credit. Credit the streamer in every post — credit is a courtesy, not a licence.
- **Never pay to join any clipping platform.** Never automate Whop payout setup or withdrawals (the maintainer's job by hand).
- **Never submit a clip twice, or past 30 minutes after posting.** A job is complete ONLY when the dashboard shows Pending WITH a submission ID.

## Secrets

- Never commit credentials, tokens, cookies, or secrets. `.auth/`, live config, campaigns/earnings state, logs, and all video files are gitignored and stay private. Code, docs, and config templates are public-safe.
- The CI secret scan (`scripts/check-secrets.sh`) runs on every push, and `make lint` runs it locally.
- If a secret is leaked: **rotate first, then remove it from history**. Do not just delete the file and move on — a rotated secret is useless; an unrotated one is still live in git history.

## Reporting a vulnerability

Report security issues (including a suspected secret leak) directly to the maintainer, Abel Prasad (abelprasad4@gmail.com). Do not open a public issue with secret material in it.
