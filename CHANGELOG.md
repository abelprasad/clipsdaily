# Changelog

All notable changes to clipsdaily, in reverse chronological order. Versioning: `vX.Y.Z` tags on main. The first release is v0.1.0.

## [Unreleased]

## [0.1.0] — 2026-11-15

First packaged release. The pipeline itself was built and run live on Nov 15, 2026; this release is the repackaging of that working system into a real CLI product.

### Added

- `clipsdaily` CLI (`pyproject.toml` + `src/` layout, console_scripts entry point): `run`, `post` (now/one/hourly), `queue` (status/maintain/seed), `campaign` (watch/cut), `submit` (scan/list-pending/mark-submitted/mark-failed), `earnings`, `auth`.
- Claude Code plugin (`plugins/clipsdaily/`): manifest + 7 slash commands, installable via `/plugin marketplace add abelprasad/clipsdaily` + `/plugin install clipsdaily@abelprasad`.
- Marketplace manifest (`.claude-plugin/marketplace.json`, name `abelprasad`).
- Copy-installers: `scripts/install.sh` (macOS/Linux) and `scripts/install.ps1` (Windows), with `--all` / `-All` multi-harness support (Claude Code, OpenCode/Codex, Hermes, Gemini).
- `skills/clipsdaily/SKILL.md`: the standing rules (full frame, one-line captions, strict gate, TikTok blocked, never submit without the gate / twice / past 30 min).
- Docs: `INSTALL.md`, `USAGE.md`, `CHANGELOG.md`, `SECURITY.md`, plus `docs/` (quickstart, installation, CLI reference, config, operations, campaigns, FAQ) and `docs/adr/` (15 ADRs).
- `CONTRIBUTING.md`, `LICENSE` (MIT), `ROADMAP.md`, `GOVERNANCE.md`, `Makefile`, GitHub Actions CI (compile + CLI smoke test + secret scan), `VERSION` file.
- `examples/` (sanitized config + campaign JSON), `scripts/check-secrets.sh`, `scripts/gen-cli-reference.sh`, `scripts/gen_star_history.py` (+ daily workflow).
- `deploy.sh` updated for the packaged layout (pip install from the repo, console-script restarts).

### Fixed (pipeline, Nov 15, 2026 — carried into this release)

- Full-frame vertical video: whole 16:9 frame, blurred darkened copy behind, nothing cropped.
- Captions: one-line post captions, no boilerplate, no hashtags except campaign-required ones; hook overlay lowered to y=300; burned-in word captions removed (one big hook at the start only).
- TikTok poster: modal + guided-tour overlay handling (the 19:33 post proved it); hourly TikTok path still blocked (throttled session + Playwright sync/async bug) — see `docs/TIKTOK.md`.
- Eligibility gate: strict window + caption + framing checks; borderline = blocked.
- Auto-submit outbox with 30-minute job expiry; jobs complete only on a dashboard submission ID.

### Known gaps

- Hourly poster does not yet prefer `campaign_queue.json` — campaign cuts sit unposted.
- Runner's clips ship hook-less (hook=None default).
- YouTube token lacks delete scope — flawed Shorts are deleted from Studio.
- YouTube daily upload limit (~8/day) hit Nov 15; 2 staged Shorts wait for the reset.
