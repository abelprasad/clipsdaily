# Keep ClipForge ads in the same repo

## Status

Accepted. 2026-11-17.

## Context

The ClipForge ads lived in a separate local git repo
(`/home/abel/clipforge-ads/`, Remotion project, main branch, 8 commits,
no remote). The pipeline repo was being preserved as the single public
repo `abelprasad/clipsdaily`. Two options: a second public repo
(`abelprasad/clipforge-ads`) or the ads as a subdirectory of the one
repo. I picked one repo, ads inside.

## Decision

Merge the ads repo into `clipsdaily` as `clipforge-ads/` with its full
git history preserved via `git subtree add --prefix=clipforge-ads
/home/abel/clipforge-ads main`. No second repo is created. The ads keep
their own README, their own ADRs under `clipforge-ads/docs/adr/`, and
their own `.gitignore` (node_modules, out, voices, .env); the root
`.gitignore` still applies on top. The ads' license is the same
ClipForge Proprietary License as the repo root (`clipforge-ads/LICENSE`
is a copy of it) — the ads are ClipForge product assets, not MIT code.
The ads README's old "stays private: no public repo" line was updated
to reflect the merge.

## Consequences

- One repo to clone, one public URL, one license. The ads' history
  (v1–v6, retention check, IP-rule amendment) stays readable in the
  main repo's log as a merged branch.
- The ads' Remotion tooling (Node 24, npm) is separate from the
  pipeline's Python tooling; the subdirectory keeps that boundary
  clean. `clipforge-ads/` does not import or depend on `src/`.
- Future ad work happens in this repo, on any branch; the old
  standalone ads repo on indra is redundant once the push is verified.
