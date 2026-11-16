# Architecture Decision Log

This is the architecture decision log (ADL) for clipsdaily: the collection of all architecture decision records (ADRs) for this project. Each ADR is one file, one decision, written in the Michael Nygard template (Title, Status, Context, Decision, Consequences).

## Rules

- **One decision per file.** Filename is a present-tense imperative verb phrase, lowercase with dashes, `.md` extension (for example `use-full-frame-vertical-video.md`).
- **ADRs are immutable.** Never rewrite an existing ADR. A changed decision gets a NEW ADR that supersedes the old one, and the old one's Status is updated to `Superseded` with a pointer to the new file.
- **Status values:** `Accepted`, `Superseded`, `Deprecated`, `Proposed`.
- **Dates** are the date the decision was made, in the Status section.

## Writing ADRs with Claude Code

The upstream ADR project ships a Claude Code skill, [`architecture-decision-record-skill`](https://github.com/architecture-decision-record/architecture-decision-record/tree/main/skills/architecture-decision-record-skill). It is **linked here, not vendored** into this repo: the skill has no license of its own, and the repo's license is CC BY-NC-SA 4.0 (non-commercial, share-alike). Clipsdaily is a revenue-seeking pipeline, so reuse of that skill inside this repo is not clearly permitted. To use it, copy its folder into `.claude/skills/` in your own checkout (or `~/.claude/skills/` for every project) and ask Claude Code to write or review an ADR. If its license ever becomes clearly permissive, vendor it here and update this note.

Reference: [architecture-decision-record/architecture-decision-record](https://github.com/architecture-decision-record/architecture-decision-record).

## Index

| # | Decision | Status | Date |
|---|----------|--------|------|
| 001 | [Use full-frame vertical video](use-full-frame-vertical-video.md) | Accepted | 2026-11-15 |
| 002 | [Use one-line post captions](use-one-line-post-captions.md) | Accepted | 2026-11-15 |
| 003 | [Remove burned-in word captions](remove-burned-in-word-captions.md) | Accepted | 2026-11-15 |
| 004 | [Enforce strict eligibility gate](enforce-strict-eligibility-gate.md) | Accepted | 2026-11-15 |
| 005 | [Build live clipping first](build-live-clipping-first.md) | Accepted | 2026-11-15 |
| 006 | [Post Instagram via operator CLI](post-instagram-via-operator-cli.md) | Accepted | 2026-11-15 |
| 007 | [Post TikTok via cookie export](post-tiktok-via-cookie-export.md) | Accepted | 2026-11-15 |
| 008 | [Use YouTube OAuth upload scope](use-youtube-oauth-upload-scope.md) | Accepted | 2026-11-15 |
| 009 | [Post two clips per hour](post-two-clips-per-hour.md) | Accepted | 2026-11-15 |
| 010 | [Automate campaign discovery](automate-campaign-discovery.md) | Accepted | 2026-11-15 |
| 011 | [Run fully automatic with kill switch](run-fully-automatic-with-kill-switch.md) | Accepted | 2026-11-15 |
| 012 | [Cut before chat spikes](cut-before-chat-spikes.md) | Accepted | 2026-11-15 |
| 013 | [Label old VOD clips as throwbacks](label-old-vod-clips-as-throwbacks.md) | Accepted | 2026-11-15 |
| 014 | [Keep live state out of git](keep-live-state-out-of-git.md) | Accepted | 2026-11-15 |
| 015 | [Use repo as dev copy](use-repo-as-dev-copy.md) | Accepted | 2026-11-15 |
