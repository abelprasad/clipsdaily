# Roadmap

## v0.1.0 — first release (this repackaging)

- CLI (`clipsdaily` command) + `src/` layout + `pyproject.toml`
- Claude Code plugin + clipsdaily skill
- Docs site (quickstart, installation, CLI reference, config, operations,
  campaigns, FAQ) under `docs/`
- Makefile, GitHub Actions CI, CONTRIBUTING, LICENSE (MIT), GOVERNANCE
- `deploy.sh` updated for the new layout (pip install from the repo)

## Next (in rough order)

1. **Wire the hourly poster to `campaign_queue.json`** — known gap: the
   campaign watcher + cutter work, but the hourly poster does not prefer
   the campaign queue when a campaign is active, so campaign cuts sit
   unposted. See docs/CAMPAIGNS.md.
2. **Fix TikTok auto-posting** — currently blocked: Playwright sync/async
   bug in the hourly TikTok path, plus the automated session is throttled
   after the Nov 15 submit burst. Manual phone post works; the account
   is fine. Needs a fresh cookie export + the Playwright fix. See
   docs/TIKTOK.md.
3. **YouTube delete scope** — re-run OAuth with the full `youtube` scope
   so flawed Shorts can be deleted via the API instead of from Studio.
4. **Short 5–15s TikTok variant** — viral clips are 5–17s; the current
   30s default is long. Keep 30s for Shorts/Reels, 60–90s for TikTok
   Creator Rewards pay.
5. **YouTube VOD mode** — paused, not built. Design notes in
   docs/youtube-vod-notes.md; the clip-brain approach (scrape the 100
   latest clips, reverse-engineer moment selection) is the plan.
6. **Release packaging** — PyPI release, macOS/Windows install testing,
   prebuilt release binaries (PyInstaller or similar).
7. **Runner hook** — the live runner's clips currently ship hook-less
   (hook=None default); wire the hook generator into the runner path.

## Out of scope

- Posting to personal accounts — this is the clipsdaily accounts only.
- Paying to join any clipping platform — never.
- Live-money anything — campaigns are the only money path, behind the gate.
