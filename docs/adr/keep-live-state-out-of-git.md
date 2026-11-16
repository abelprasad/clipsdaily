# Keep live state out of git

## Status

Accepted — 2026-11-15

## Context

The pipeline's working state changes constantly and contains credentials and real operational data. The queue rewrites every few minutes as clips are cut, posted, and marked. Auth files hold live session cookies and OAuth tokens. Earnings and campaign files hold real submission IDs, view counts, and payout figures. Video files are large binaries.

## Decision

`queue/`, `.auth/`, `clips/`, `vod/`, `recordings/`, `logs/`, `earnings.json`, `campaigns.json`, `submit-outbox/`, and all media (`.mp4`, `.srt`, `.png`, `.log`) stay out of git via `.gitignore`. The repo ships the code that builds the state, not the state itself. Config ships as examples (`config/config.yaml.example`, `config/campaigns.example.json`); the live `config.yaml` and `campaigns.json` stay on the machine.

## Consequences

- A fresh clone regenerates its own queue by running the maintainer; git history stays clean and small.
- No credential, session cookie, submission ID, view count, or payout value ever lands in git history.
- The live directory on indra (`/home/abel/clipsdaily/`) remains the single source of runtime truth; the repo is the single source of code truth.
- Cloning the repo does not clone the pipeline's state: a new operator must run setup, recreate auth from scratch (see `docs/AUTH.md`), and let the queue build itself.
- This is also why the queue is left out of the repo even though it is the pipeline's most active data structure: it is live state, not source code. Recipe versus food in the fridge.
