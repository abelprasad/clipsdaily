# Governance

## Maintainer

I (Abel Prasad, abelprasad4@gmail.com) am the maintainer and decide
releases, merges, and what ships. The clipsdaily accounts are mine;
no one else posts, joins, or submits from them.

## Decisions

Architecture decisions go in `docs/adr/` (one file per decision,
Nygard template, immutable — supersede with a new ADR, don't rewrite).
See `docs/adr/README.md`.

## Releases

- Version lives in `src/clipsdaily/__init__.py` (`__version__`) and is
  mirrored in `VERSION` (`make check` verifies they match).
- Tag releases `vX.Y.Z` on main. The first release is **v0.1.0**.
- No GitHub release yet — the repo has no remote. When the push
  decision lands (public vs private), create the remote, push, then
  tag v0.1.0.
- `deploy.sh` is the only way code reaches the live runtime on indra.

## Money rules

- The eligibility gate (`eligibility_gate.py`) is never bypassed for
  speed. One bad submission bans the account from every campaign
  permanently (one-strike rule).
- Campaign submissions happen within 30 minutes of posting, never
  twice, never without the gate passing.
- Whop payout setup and withdrawals are the maintainer's job by hand.

## Security

- Never commit credentials, tokens, cookies, or secrets. The CI
  secret scan (`scripts/check-secrets.sh`) runs on every push.
- Report a suspected secret leak to the maintainer directly; rotate
  first, then remove from history.
- `.auth/`, live config, campaigns/earnings state, logs, and all video
  files are gitignored and stay private. Code, docs, and config
  templates are public-safe.
