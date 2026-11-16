# Use repo as dev copy

## Status

Accepted — 2026-11-15

## Context

The pipeline lived only in `/home/abel/clipsdaily/` on indra, with no portable copy and no way for another agent to work on it. Abel asked to package it for Claude Code so the agent is interchangeable, not just Muse: "can everything be contained in a repo". He then decided the repo is the canonical dev copy.

## Decision

This repo is the canonical dev copy where work happens. `/home/abel/clipsdaily/` on indra is the live runtime. `deploy.sh` copies the repo's `.py` files and config to the live directory and restarts the tmux sessions (`clipsdaily`, `clipsdaily-queue`, `clipsdaily-hourly`). Deploy is dry-run verified; a live deploy never runs without Abel's go.

## Consequences

- Never edit the live directory by hand; edit the repo and deploy.
- Never run `restart_maintainer.py`: it is stale, it wipes `queue.json` and resets maintainer state.
- `deploy.sh` refuses on a dirty tree, refuses if the repo is the live directory, and skips (never starts) a session that isn't running.
- The repo documents the Muse/Friday-specific dependencies in the README: Instagram posting runs on the operator VM, the crons assume Muse's scheduler, auth is recreated from scratch, and 98 lines hardcode `/home/abel` paths (full table in `docs/PATHS.md`). A Claude Code user must replace those on their own machine.
- Pushing to GitHub (public vs private) is still undecided; the repo has no remote.
