# Preserve and shut down the pipeline

## Status

Accepted. 2026-11-17.

## Context

By Nov 17, 2026 every leg of the pipeline was fighting Abel at once:
TikTok auto-posting blocked account-wide since Nov 15, YouTube OAuth
client disabled, Instagram posting stalled overnight on per-run
approvals, and then Instagram flagged `@clippedaily31` for unoriginal
content (recommendations to non-followers off). The famous-clips change
shipped the same morning likely accelerated the flag. Abel's call was
"let's kill it all, I'm tired of this" — shut the pipeline down, but
preserve everything first so it can be restarted later.

## Decision

Shut down the live pipeline and preserve it in one public repo,
`abelprasad/clipsdaily`, with the ClipForge ads merged in as
`clipforge-ads/` (history preserved via subtree merge). The repo is
public to read under the ClipForge Proprietary License ("licensed, not
sold" — no redistribution, resale, or sublicensing). Preservation
means: reconcile the live code into the repo, add the live-only files
(IG session import, indra IG poster, patch scripts, sync tool, systemd
units), write a comprehensive restart guide (`docs/RESTART.md`), record
the shutdown state and the Instagram originality findings, and verify
the push with a clean clone. Nothing is deleted in this step: the live
dir, the operator-VM crons, and the systemd units stay until Abel
verifies the push himself, and the removal list is recorded in the
shutdown report. Live state, media, and credentials are deliberately
NOT preserved in the repo (`.gitignore`); the restart guide records
what they were and how to rebuild them.

## Consequences

- The pipeline stops posting. The IG account keeps its followers but
  no recommendation reach until a restart posts mostly-original content
  for 30 days (see `docs/RESTART.md`).
- The repo becomes the single source of truth for a future restart.
  The ClipForge package and the ads travel with it, so a restart can
  also resume the product work.
- Public visibility changes the privacy posture: the repo was built
  assuming private distribution (see the old "Private by rule" section
  in `packaging/README.md`, now rewritten). The full-history secrets
  audit before the push found no tokens, cookies, keys, Cloudflare
  tokens, phone number, or home address in either repo's history or
  working tree — only path/name mentions (fine), public contact emails
  (by design, and already present as commit author emails), and
  function-call false positives in the secret scanner (fixed). The
  ClipForge license private key was never in any repo and stays at
  `/home/abel/.config/clipforge/license-private.key`.
- The shutdown does not delete the Instagram, TikTok, or YouTube
  accounts, the ClipForge key, or any live file. Deletion is a separate
  step with its own list, done only after the push is verified.
